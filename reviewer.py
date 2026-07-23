"""
Independent peer reviewer for DQ investigations.
The reviewer sees only the written output of the Analyst — never the raw conversation history.
This preserves true context isolation: the same isolation as a human second-pair-of-eyes review.
"""

import os
import duckdb
import anthropic
from dataclasses import dataclass, field
from checks import CheckResult
from investigator import Investigation, InvestigationStep, SQL_TOOL, _run_sql

INPUT_PRICE_PER_TOKEN  = 3.0  / 1_000_000
OUTPUT_PRICE_PER_TOKEN = 15.0 / 1_000_000

REVIEWER_SYSTEM_PROMPT = """You are an independent data quality reviewer. You did NOT run the original investigation — you are a second pair of eyes reading a colleague's written findings.

Your job is to challenge, not to agree. Assume the Analyst may have stopped too early or followed the most obvious explanation.

MANDATORY: You MUST run at least one SQL query the Analyst did not run. A review without independent verification is just re-reading.

After running your challenge query (or queries, max 3), write your final review in this EXACT format — preserve the section headers:

VERDICT: [ENDORSE / ENDORSE-WITH-CAVEATS / RETURN-FOR-REWORK]
SUMMARY: [one sentence — e.g. "Root cause correctly identified; confidence overstated given thin evidence on genre trend."]

FINDINGS:
- [Finding 1 claim]: [CONFIRMED / PLAUSIBLE / NEEDS-RECHECK / DISPUTED] — [one sentence reason]
- [Finding 2 claim]: [CONFIRMED / PLAUSIBLE / NEEDS-RECHECK / DISPUTED] — [one sentence reason]

CAVEATS:
- [gap or alternative the Analyst did not test]
- [another gap if applicable]

Keep each section concise. The VERDICT line must be the first line of your response."""


@dataclass
class ReviewFinding:
    claim: str
    assessment: str     # CONFIRMED / PLAUSIBLE / NEEDS-RECHECK / DISPUTED
    reason: str


@dataclass
class Review:
    verdict: str = ""                                          # ENDORSE / ENDORSE-WITH-CAVEATS / RETURN-FOR-REWORK
    summary: str = ""
    findings: list = field(default_factory=list)              # list[ReviewFinding]
    challenge_queries: list = field(default_factory=list)     # list[InvestigationStep] — SQL the reviewer ran
    caveats: list = field(default_factory=list)               # list[str]
    completed: bool = False
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens  * INPUT_PRICE_PER_TOKEN
            + self.output_tokens * OUTPUT_PRICE_PER_TOKEN
        )

    @property
    def verdict_color(self) -> str:
        return {
            "ENDORSE":               "green",
            "ENDORSE-WITH-CAVEATS":  "orange",
            "RETURN-FOR-REWORK":     "red",
        }.get(self.verdict, "gray")


def _format_investigation_for_review(inv: Investigation, check: CheckResult) -> str:
    """Render investigation as plain text for the reviewer — no raw message history."""
    unit = f" {check.unit}" if check.unit else ""
    ctx  = check.context

    lines = [
        f"=== FLAGGED CHECK ===",
        f"Check: {check.name}",
        f"Current value: {check.current_val}{unit}  [FLAGGED {check.flag_direction}]",
        f"Normal range: {check.fence_low}{unit} – {check.fence_high}{unit}",
        f"Prior year: {ctx.get('by_year', {}).get(ctx.get('prior_year', 0), 'N/A')}{unit}",
        "",
        f"=== ANALYST SQL EVIDENCE ===",
    ]

    for i, step in enumerate(inv.steps, 1):
        lines.append(f"\nQuery {i}:")
        lines.append(f"```sql\n{step.sql}\n```")
        lines.append(f"Result:\n{step.result}")
        if step.reasoning:
            lines.append(f"Analyst note: {step.reasoning[:300]}")

    lines += [
        "",
        "=== ANALYST CONCLUSION ===",
        inv.summary or "(no summary written)",
        "",
        "=== YOUR TASK ===",
        "Review the above. Run at least one SQL query the Analyst did not run, then write your review.",
    ]
    return "\n".join(lines)


def _parse_review_text(text: str, steps: list) -> Review:
    """Extract structured fields from the reviewer's final text output."""
    rev = Review(challenge_queries=steps)
    lines = text.strip().splitlines()

    section = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("VERDICT:"):
            rev.verdict = stripped.replace("VERDICT:", "").strip()
        elif stripped.startswith("SUMMARY:"):
            rev.summary = stripped.replace("SUMMARY:", "").strip()
        elif stripped == "FINDINGS:":
            section = "findings"
        elif stripped == "CAVEATS:":
            section = "caveats"
        elif section == "findings" and stripped.startswith("-"):
            body = stripped.lstrip("- ").strip()
            # Format: "claim: ASSESSMENT — reason"
            if ":" in body:
                claim_part, rest = body.split(":", 1)
                rest = rest.strip()
                for assessment in ("CONFIRMED", "PLAUSIBLE", "NEEDS-RECHECK", "DISPUTED"):
                    if rest.startswith(assessment):
                        reason = rest[len(assessment):].lstrip(" —").strip()
                        rev.findings.append(ReviewFinding(
                            claim=claim_part.strip(),
                            assessment=assessment,
                            reason=reason,
                        ))
                        break
                else:
                    rev.findings.append(ReviewFinding(claim=body, assessment="PLAUSIBLE", reason=""))
            else:
                rev.findings.append(ReviewFinding(claim=body, assessment="PLAUSIBLE", reason=""))
        elif section == "caveats" and stripped.startswith("-"):
            rev.caveats.append(stripped.lstrip("- ").strip())

    rev.completed = bool(rev.verdict)
    return rev


def review(
    inv: Investigation,
    check: CheckResult,
    con: duckdb.DuckDBPyConnection,
) -> Review:
    """
    Run an independent peer review of an investigation.
    The reviewer sees only the written output — no shared context with the Analyst.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        r = Review()
        r.verdict  = "ERROR"
        r.summary  = "ANTHROPIC_API_KEY not set."
        return r

    client  = anthropic.Anthropic(api_key=api_key)
    content = _format_investigation_for_review(inv, check)
    messages = [{"role": "user", "content": content}]

    steps: list[InvestigationStep] = []
    input_tokens  = 0
    output_tokens = 0
    final_text    = ""

    for _ in range(6):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system=REVIEWER_SYSTEM_PROMPT,
            tools=[SQL_TOOL],
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})
        input_tokens  += response.usage.input_tokens
        output_tokens += response.usage.output_tokens

        turn_text = " ".join(
            block.text for block in response.content if hasattr(block, "text")
        ).strip()

        if response.stop_reason == "end_turn":
            final_text = turn_text
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            query      = block.input.get("query", "")
            sql_result = _run_sql(con, query)
            steps.append(InvestigationStep(sql=query, result=sql_result, reasoning=turn_text))
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": block.id,
                "content":     sql_result,
            })
        messages.append({"role": "user", "content": tool_results})

    rev = _parse_review_text(final_text, steps)
    rev.input_tokens  = input_tokens
    rev.output_tokens = output_tokens
    return rev
