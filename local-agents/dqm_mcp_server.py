"""
Local DQM MCP Server — exposes DQ check data and SQL to Claude Code agents.
Runs as a stdio subprocess registered in .claude/settings.json.
No Anthropic API calls — all token usage comes from your Claude Code subscription.
"""
import sys
import json
from pathlib import Path
from datetime import date

# Import checks.py and data_loader.py from the parent project folder
sys.path.insert(0, str(Path(__file__).parent.parent))
from checks import get_connection, run_all_checks, CheckResult
from data_loader import ensure_data

from fastmcp import FastMCP

# ── One-time setup at server start ──────────────────────────────────────────
ensure_data()
_CON = get_connection()
mcp  = FastMCP("dqm-local")


# ── Internal helpers ─────────────────────────────────────────────────────────

def _run_sql(query: str) -> str:
    """Execute SQL, return formatted ASCII table (max 25 rows) or error string."""
    try:
        cursor = _CON.execute(query)
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


def _check_summary(c: CheckResult) -> dict:
    ctx  = c.context
    unit = f" {c.unit}" if c.unit else ""
    return {
        "name":           c.name,
        "metric":         c.metric,
        "flagged":        c.flagged,
        "flag_direction": c.flag_direction,
        "current_val":    f"{c.current_val}{unit}",
        "fence_low":      f"{c.fence_low}{unit}",
        "fence_high":     f"{c.fence_high}{unit}",
        "check_type":     ctx.get("check_type"),
        "current_year":   ctx.get("current_year"),
    }


# ── MCP tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def list_flagged_checks(year: int = 2024, n_hist: int = 12) -> str:
    """
    Return all flagged DQ checks as JSON.
    Call this first to see what needs investigation.
    """
    checks  = run_all_checks(_CON, current_year=year, n_hist=n_hist)
    flagged = [_check_summary(c) for c in checks if c.flagged]
    return json.dumps(flagged, indent=2)


@mcp.tool()
def get_check_detail(check_name: str, year: int = 2024, n_hist: int = 12) -> str:
    """
    Return full detail for a named check: historical trend, fences, and replication SQL.
    check_name: partial or full name (case-insensitive match on name or metric field).
    """
    checks     = run_all_checks(_CON, current_year=year, n_hist=n_hist)
    name_lower = check_name.lower()
    match = next(
        (c for c in checks
         if name_lower in c.name.lower() or name_lower in c.metric.lower()),
        None,
    )
    if match is None:
        available = [c.name for c in checks]
        return json.dumps({"error": f"No check matching '{check_name}'",
                           "available": available})

    ctx  = match.context
    unit = f" {match.unit}" if match.unit else ""
    hist = {str(y): f"{v}{unit}" for y, v in sorted(ctx.get("by_year", {}).items())}

    return json.dumps({
        "name":             match.name,
        "metric":           match.metric,
        "flagged":          match.flagged,
        "flag_direction":   match.flag_direction,
        "current_val":      f"{match.current_val}{unit}",
        "fence_low":        f"{match.fence_low}{unit}",
        "fence_high":       f"{match.fence_high}{unit}",
        "current_year":     ctx.get("current_year"),
        "prior_year":       ctx.get("prior_year"),
        "prior_year_val":   f"{ctx.get('by_year', {}).get(ctx.get('prior_year', 0), 'N/A')}{unit}",
        "historical_trend": hist,
        "check_type":       ctx.get("check_type"),
        "replication_sql":  ctx.get("replication_sql"),
    }, indent=2)


@mcp.tool()
def run_sql(query: str) -> str:
    """
    Execute a SQL query against the local IMDB DuckDB database.
    Available views:
      basics  — tconst, titleType, primaryTitle, startYear, endYear, runtimeMinutes, genres
      ratings — tconst, averageRating, numVotes
    Use DuckDB SQL syntax. startYear and runtimeMinutes are integers.
    Returns up to 25 rows as a formatted table, or an error message.
    """
    return _run_sql(query)


@mcp.tool()
def save_finding(filename: str, content: str) -> str:
    """
    Save investigation or review output to local-agents/investigations/.
    filename: e.g. "2026-07-12_tvMiniSeries.md" or "2026-07-12_tvMiniSeries_review.md"
    Returns the path where the file was saved.
    """
    out_dir = Path(__file__).parent / "investigations"
    out_dir.mkdir(exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in filename).strip()
    if not safe.endswith(".md"):
        safe += ".md"
    path = out_dir / safe
    path.write_text(content, encoding="utf-8")
    return f"Saved → {path}"


if __name__ == "__main__":
    mcp.run()
