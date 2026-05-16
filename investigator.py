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

SYSTEM_PROMPT = """You are a data quality analyst investigating a statistical anomaly in IMDB data.
You have a run_sql tool to query the database.

Investigation strategy (follow in order, run one query per step):
1. Confirm the anomaly: verify the reported numbers with a direct query.
2. Find outlier cases: check if a small number of extreme records drive the result.
3. Quantify the outlier impact: re-run the metric excluding those outliers.
4. Compare to prior year: run the same metric for the previous year to see the change.
5. Conclude: write your final summary.

IMPORTANT: After at most 5 SQL queries, you MUST stop querying and write your final summary.
Your final summary must include:
- What the anomaly is (with specific numbers)
- The most likely root cause
- Whether it is a data quality issue or a legitimate data phenomenon
- Exactly 3 verification queries, each on its own line starting with "VERIFY:"

Do not run more than 5 queries."""


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
    hist_summary = ", ".join(
        f"{y}: {v}{check.unit}"
        for y, v in sorted(ctx.get("by_year", {}).items())
        if int(y) != ctx.get("current_year")
    )
    return f"""A data quality check has been flagged. Investigate following the 5-step strategy.

Check: {check.name}
Current period ({ctx.get('current_year')}): {check.current_val}{check.unit}
Normal range (Tukey fences): {check.fence_low}{check.unit} – {check.fence_high}{check.unit}
Direction: {check.flag_direction}

Historical values by year: {hist_summary}

Additional context: {ctx}

Begin with Step 1: confirm the anomaly with a direct query."""


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
