"""
AI investigation agent.
Returns an Investigation object with the full reasoning trace + final summary.
"""

import os
import duckdb
import anthropic
from dataclasses import dataclass, field
from checks import CheckResult

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
You are given the EXACT result and the EXACT SQL that produced it.

CRITICAL RULES:
- Do NOT try to reproduce or verify the flagged number — it is correct and you already have it.
- Always start your first query using the EXACT same filters as the replication SQL provided — this ensures you are looking at the same dataset the check was built on.
- After establishing that baseline, you are free to use any additional filtering (LIKE, contains, different groupings, subsets) if it helps explain the root cause.
- Start immediately with WHY the metric changed, not whether it changed.

Investigation strategy (5 queries maximum):
1. Run the replication SQL for the current year AND prior year to see the absolute count change.
2. Break down by titleType (movie, tvSeries, tvMovie, etc.) — did one type drive the shift?
3. Find the top titles by vote count with this genre/category — which specific titles are new or growing?
4. If still unclear: compare the title count and avg votes between current and prior year for this category.
5. Conclude.

Your final summary must include:
- The specific numbers: how many titles, how the count changed vs prior year
- The most likely driver (specific title types, new releases, a few high-vote outliers, or a data issue)
- Whether this is a legitimate trend or a data quality concern
- Exactly 3 verification queries on their own lines starting with "VERIFY:"

After at most 5 queries you MUST write your final summary."""


@dataclass
class InvestigationStep:
    sql: str
    result: str
    reasoning: str  # any text Claude wrote before this tool call


INPUT_PRICE_PER_TOKEN = 3.0 / 1_000_000   # $3 per million input tokens
OUTPUT_PRICE_PER_TOKEN = 15.0 / 1_000_000  # $15 per million output tokens


@dataclass
class Investigation:
    steps: list[InvestigationStep] = field(default_factory=list)
    summary: str = ""
    completed: bool = False
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens * INPUT_PRICE_PER_TOKEN
            + self.output_tokens * OUTPUT_PRICE_PER_TOKEN
        )


def _run_sql(con: duckdb.DuckDBPyConnection, query: str) -> str:
    try:
        cursor = con.execute(query)
        rows = cursor.fetchall()
        if not rows:
            return "Query returned no rows."
        cols = [desc[0] for desc in cursor.description]
        col_widths = [
            max(len(c), max((len(str(r[i])) for r in rows), default=0))
            for i, c in enumerate(cols)
        ]
        header = "  ".join(c.ljust(col_widths[i]) for i, c in enumerate(cols))
        sep = "  ".join("-" * w for w in col_widths)
        body = "\n".join(
            "  ".join(str(r[i]).ljust(col_widths[i]) for i in range(len(cols)))
            for r in rows[:25]
        )
        suffix = f"\n... ({len(rows)} rows total, showing 25)" if len(rows) > 25 else ""
        return f"{header}\n{sep}\n{body}{suffix}"
    except Exception as e:
        return f"SQL Error: {e}"


def _build_initial_prompt(check: CheckResult) -> str:
    ctx = check.context
    unit = f" {check.unit}" if check.unit else ""
    hist_summary = "  ".join(
        f"{y}: {v}{unit}"
        for y, v in sorted(ctx.get("by_year", {}).items())
        if int(y) != ctx.get("current_year")
    )
    replication_sql = ctx.get("replication_sql", "-- replication SQL not available")
    prior_year = ctx.get("prior_year", ctx.get("current_year", 0) - 1)

    return f"""A monitoring check is flagged. Your job is to explain WHY — not to verify the number.

=== CHECK DETAILS ===
Check name: {check.name}
Current period ({ctx.get('current_year')}): {check.current_val}{unit}  ← FLAGGED {check.flag_direction}
Normal range (Tukey IQR fences): {check.fence_low}{unit} – {check.fence_high}{unit}
Prior year ({prior_year}): {ctx.get('by_year', {}).get(prior_year, 'N/A')}{unit}

Historical trend (oldest → newest):
{hist_summary}

=== EXACT SQL THAT PRODUCED THIS RESULT ===
Use this SQL as your starting point. Run it for {prior_year} and {ctx.get('current_year')} to see absolute counts.
DO NOT modify the WHERE clause filters — especially do not use LIKE instead of =.

{replication_sql}

=== YOUR TASK ===
Start with Step 1: run the replication SQL above to get the absolute title counts for both years.
Then investigate what drove the change — specific title types, new releases, or a few high-influence records."""


def investigate(check: CheckResult, con: duckdb.DuckDBPyConnection) -> Investigation:
    """Run the agentic investigation and return the full trace + summary."""
    result = Investigation()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        result.summary = "Error: ANTHROPIC_API_KEY environment variable not set."
        return result

    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": _build_initial_prompt(check)}]

    for _ in range(8):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[SQL_TOOL],
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        # Accumulate token usage
        result.input_tokens += response.usage.input_tokens
        result.output_tokens += response.usage.output_tokens

        # Collect any text Claude wrote in this turn (reasoning between tool calls)
        turn_text = " ".join(
            block.text for block in response.content if hasattr(block, "text")
        ).strip()

        if response.stop_reason == "end_turn":
            result.summary = turn_text
            result.completed = True
            return result

        # Process tool calls, recording each as a step
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            query = block.input.get("query", "")
            sql_result = _run_sql(con, query)
            result.steps.append(InvestigationStep(
                sql=query,
                result=sql_result,
                reasoning=turn_text,
            ))
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": sql_result,
            })

        messages.append({"role": "user", "content": tool_results})

    result.summary = (
        "Agent reached the query limit without a final conclusion. "
        "Review the steps below to draw your own conclusion."
    )
    return result
