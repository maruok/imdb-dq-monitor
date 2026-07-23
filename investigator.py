"""
AI investigation agent.
Returns an Investigation object with full trace, summary, and conversation history
so the analyst can ask follow-up questions that continue from where the agent left off.
"""

import os
import duckdb
import anthropic
from dataclasses import dataclass, field
from checks import CheckResult
from prompts import load_prompt

SQL_TOOL = {
    "name": "run_sql",
    "description": (
        "Run a SQL query against the IMDB database. "
        "Available views: 'basics' (tconst, titleType, primaryTitle, originalTitle, "
        "isAdult, startYear, endYear, runtimeMinutes, genres) and "
        "'ratings' (tconst, averageRating, numVotes). "
        "Use DuckDB SQL syntax. startYear and runtimeMinutes are integers."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The SQL query to execute"}
        },
        "required": ["query"],
    },
}

SYSTEM_PROMPT = """You are a senior data quality analyst. A monitoring check has been flagged.
You are given the EXACT result and the EXACT SQL that produced it, plus the pre-run replication result.

CRITICAL RULES:
- The replication result is already provided in the prompt — do NOT re-run it. That is your baseline.
- Read the baseline counts (numerator and denominator for both years) from the replication result.
- Start immediately with WHY the metric changed, not whether it changed.
- Use the EXACT same filters as the replication SQL when comparing to prior periods.

Investigation strategy (5 queries available — all for driver analysis):
1. Break down by the most likely grouping (titleType, genres, numVotes range) to isolate the driver.
2. Find the top titles by vote count — which specific titles are new or growing in this category?
3. Test the leading driver: does excluding or isolating it explain the gap?
4. If still unclear: compare title count and avg votes between current and prior year for this category.
5. Conclude.

Your final summary must include:
- The specific numbers: how many titles, how the count changed vs prior year
- The most likely driver (specific title types, new releases, a few high-vote outliers, or a data issue)
- Whether this is a legitimate trend or a data quality concern
- Exactly 3 verification queries on their own lines starting with "VERIFY:"

After at most 5 queries you MUST write your final summary."""

FOLLOWUP_PROMPT = """You are continuing an ongoing data quality investigation.
You already have the full context of what was investigated and what was found.

The analyst has a follow-up question. Use the run_sql tool to dig deeper if needed (up to 5 queries),
then write a clear response addressing their question specifically.

You may use any SQL approach that helps answer the question — LIKE, subqueries, different groupings, etc.
End your response with a clear conclusion. Do NOT repeat the original investigation summary."""

INPUT_PRICE_PER_TOKEN  = 3.0  / 1_000_000
OUTPUT_PRICE_PER_TOKEN = 15.0 / 1_000_000


@dataclass
class InvestigationStep:
    sql: str
    result: str
    reasoning: str


@dataclass
class FollowUp:
    question: str
    steps: list = field(default_factory=list)   # list[InvestigationStep]
    response: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens  * INPUT_PRICE_PER_TOKEN
            + self.output_tokens * OUTPUT_PRICE_PER_TOKEN
        )


@dataclass
class Investigation:
    steps: list = field(default_factory=list)       # list[InvestigationStep]
    summary: str = ""
    completed: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    messages: list = field(default_factory=list)    # full conversation history
    follow_ups: list = field(default_factory=list)  # list[FollowUp]
    review: object = None                           # reviewer.Review | None — set after review() runs

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens  * INPUT_PRICE_PER_TOKEN
            + self.output_tokens * OUTPUT_PRICE_PER_TOKEN
        )


def _run_sql(con: duckdb.DuckDBPyConnection, query: str) -> str:
    try:
        cursor = con.execute(query)
        rows   = cursor.fetchall()
        if not rows:
            return "Query returned no rows."
        cols = [desc[0] for desc in cursor.description]
        col_widths = [
            max(len(c), max((len(str(r[i])) for r in rows), default=0))
            for i, c in enumerate(cols)
        ]
        header = "  ".join(c.ljust(col_widths[i]) for i, c in enumerate(cols))
        sep    = "  ".join("-" * w for w in col_widths)
        body   = "\n".join(
            "  ".join(str(r[i]).ljust(col_widths[i]) for i in range(len(cols)))
            for r in rows[:25]
        )
        suffix = f"\n... ({len(rows)} rows total, showing 25)" if len(rows) > 25 else ""
        return f"{header}\n{sep}\n{body}{suffix}"
    except Exception as e:
        return f"SQL Error: {e}"


def _build_initial_prompt(check: CheckResult, replication_result: str = "") -> str:
    ctx  = check.context
    unit = f" {check.unit}" if check.unit else ""
    hist_summary = "  ".join(
        f"{y}: {v}{unit}"
        for y, v in sorted(ctx.get("by_year", {}).items())
        if int(y) != ctx.get("current_year")
    )
    replication_sql = ctx.get("replication_sql", "-- replication SQL not available")
    prior_year      = ctx.get("prior_year", ctx.get("current_year", 0) - 1)

    return f"""A monitoring check is flagged. Your job is to explain WHY — not to verify the number.

=== CHECK DETAILS ===
Check name: {check.name}
Current period ({ctx.get('current_year')}): {check.current_val}{unit}  ← FLAGGED {check.flag_direction}
Normal range (Tukey IQR fences): {check.fence_low}{unit} – {check.fence_high}{unit}
Prior year ({prior_year}): {ctx.get('by_year', {}).get(prior_year, 'N/A')}{unit}

Historical trend (oldest → newest):
{hist_summary}

=== REPLICATION SQL (for reference — already run below) ===
{replication_sql}

=== BASELINE RESULT (pre-run — do NOT re-run this SQL) ===
{replication_result or '(not available)'}

=== YOUR TASK ===
The baseline counts above are your starting point. Do NOT re-run the replication SQL.
Investigate what drove the change — specific title types, new releases, or a few high-influence records.
All 5 query slots are available for driver analysis."""


def _run_agent_loop(
    client: anthropic.Anthropic,
    messages: list,
    system: str,
    max_rounds: int = 8,
) -> tuple[list, str, bool, int, int]:
    """
    Run the agentic loop. Returns (updated_messages, final_text, completed, input_tok, output_tok).
    Caller is responsible for building steps from tool calls.
    """
    steps_out = []
    input_tokens  = 0
    output_tokens = 0

    for _ in range(max_rounds):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system,
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
            return messages, turn_text, True, input_tokens, output_tokens, steps_out

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            query      = block.input.get("query", "")
            sql_result = _run_sql(client._client if hasattr(client, "_client") else None, query)
            steps_out.append(InvestigationStep(sql=query, result=sql_result, reasoning=turn_text))
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": sql_result,
            })
        messages.append({"role": "user", "content": tool_results})

    return messages, "Agent reached query limit without conclusion.", False, input_tokens, output_tokens, steps_out


def investigate(
    check: CheckResult,
    con: duckdb.DuckDBPyConnection,
    system_prompt: str | None = None,
) -> "Investigation":
    """Run the initial investigation and return an Investigation with full conversation history."""
    inv = Investigation()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        inv.summary = "Error: ANTHROPIC_API_KEY environment variable not set."
        return inv

    effective_prompt = system_prompt if system_prompt is not None else load_prompt()
    client   = anthropic.Anthropic(api_key=api_key)
    replication_sql    = check.context.get("replication_sql", "")
    replication_result = _run_sql(con, replication_sql) if replication_sql else ""
    messages = [{"role": "user", "content": _build_initial_prompt(check, replication_result)}]

    for _ in range(8):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=effective_prompt,
            tools=[SQL_TOOL],
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})
        inv.input_tokens  += response.usage.input_tokens
        inv.output_tokens += response.usage.output_tokens

        turn_text = " ".join(
            block.text for block in response.content if hasattr(block, "text")
        ).strip()

        if response.stop_reason == "end_turn":
            inv.summary   = turn_text
            inv.completed = True
            inv.messages  = messages
            return inv

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            query      = block.input.get("query", "")
            sql_result = _run_sql(con, query)
            inv.steps.append(InvestigationStep(sql=query, result=sql_result, reasoning=turn_text))
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": sql_result,
            })
        messages.append({"role": "user", "content": tool_results})

    inv.summary  = "Agent reached query limit. Review steps below."
    inv.messages = messages
    return inv


def continue_investigation(
    inv: "Investigation",
    question: str,
    con: duckdb.DuckDBPyConnection,
) -> None:
    """
    Append a follow-up question to an existing investigation in-place.
    The agent has full context of everything investigated so far.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        fu = FollowUp(question=question, response="Error: ANTHROPIC_API_KEY not set.")
        inv.follow_ups.append(fu)
        return

    client = anthropic.Anthropic(api_key=api_key)
    fu     = FollowUp(question=question)

    # Append analyst question to the existing conversation
    messages = inv.messages + [{
        "role": "user",
        "content": (
            f"Follow-up from the analyst:\n\n{question}\n\n"
            "Please investigate this further using additional SQL queries if needed (up to 5). "
            "Build on what you already found — do not repeat the original investigation."
        ),
    }]

    for _ in range(8):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=FOLLOWUP_PROMPT,
            tools=[SQL_TOOL],
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})
        fu.input_tokens   += response.usage.input_tokens
        fu.output_tokens  += response.usage.output_tokens
        inv.input_tokens  += response.usage.input_tokens
        inv.output_tokens += response.usage.output_tokens

        turn_text = " ".join(
            block.text for block in response.content if hasattr(block, "text")
        ).strip()

        if response.stop_reason == "end_turn":
            fu.response  = turn_text
            inv.messages = messages   # update history so next follow-up has full context
            inv.follow_ups.append(fu)
            return

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            query      = block.input.get("query", "")
            sql_result = _run_sql(con, query)
            fu.steps.append(InvestigationStep(sql=query, result=sql_result, reasoning=turn_text))
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": sql_result,
            })
        messages.append({"role": "user", "content": tool_results})

    fu.response  = "Follow-up reached query limit. Review steps above."
    inv.messages = messages
    inv.follow_ups.append(fu)


_META_PROMPT = """You are reviewing a batch of AI data quality investigation summaries.
Your job is to identify common patterns and suggest targeted improvements to the
AIQ system prompt — the instructions given to the AI agent before each investigation.

Analyse all summaries and produce four sections:

## Common Patterns Found
Bullet list of the 2-4 recurring root causes or themes you see across investigations.

## Investigation Gaps
What angles did the agent consistently miss or under-investigate?

## Suggested Prompt Additions
Write 2-4 concrete, ready-to-paste lines to add to the system prompt.
Format each as a plain bullet starting with a dash (no surrounding quotes), e.g.:
- Always check whether a small number of high-vote outlier titles (top 5-10 by numVotes) account for more than 50% of the anomaly before concluding a broader trend.

Be specific and actionable. Do not repeat guidance that is already in the current prompt.

## Revised Full Prompt
Write a complete, improved version of the current system prompt.
Start from the provided current prompt as the base. Integrate the suggested additions coherently.
Remove or replace any guidance that the investigation gaps suggest is incomplete or misleading.
Keep all sections and structure of the original. Do not add commentary — output the full prompt text only."""


def meta_analyze(summaries: list[str], current_prompt: str = "") -> tuple[str, int, int]:
    """
    Review all investigation summaries and suggest AIQ prompt improvements.
    Returns (suggestion_text, input_tokens, output_tokens).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "Error: ANTHROPIC_API_KEY not set.", 0, 0

    client = anthropic.Anthropic(api_key=api_key)

    summaries_text = "\n\n---\n\n".join(
        f"Investigation {i + 1}:\n{s}" for i, s in enumerate(summaries)
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=_META_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"Current AIQ system prompt:\n\n{current_prompt}\n\n"
                f"=== Investigation Summaries ({len(summaries)} total) ===\n\n"
                f"{summaries_text}"
            ),
        }],
    )

    text = response.content[0].text if response.content else ""
    return text, response.usage.input_tokens, response.usage.output_tokens
