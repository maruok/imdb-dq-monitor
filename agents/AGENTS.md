# Local DQM Agent System

Two-agent data quality investigation using Claude Code (Pro subscription).
No Anthropic API billing — all token usage comes from your Claude Code session.

---

## How it works

```
You (Claude Code)
│
├─ MCP Server: dqm-local  ← runs locally, exposes DQ data + SQL
│
├─ /dqm-investigate       ← Agent 1: Analyst
│   Investigates a flagged check using SQL, writes findings to a file
│
└─ /dqm-review            ← Agent 2: Reviewer (fresh context)
    Reads Agent 1's file, challenges the reasoning, writes a verdict
```

Agent 2 starts with **zero knowledge** of Agent 1's process — only its written output.
This is what makes it a genuine independent review, not a self-check.

---

## Setup (one-time)

```bash
pip install fastmcp
```

The MCP server (`dqm_mcp_server.py`) imports `checks.py` and `data_loader.py` from the
parent project automatically. No configuration needed beyond `pip install fastmcp`.

The server is registered in `.claude/settings.json` and starts automatically when you
open this project in Claude Code.

**Verify the MCP server is connected**: look for `dqm-local` with a green dot in the
Claude Code MCP panel (VS Code: bottom status bar or Claude Code sidebar).

---

## Usage

### Investigate a flagged check (Agent 1)

Open Claude Code, start a new conversation, then run:

```
/dqm-investigate titleType: tvMiniSeries
```

Replace `titleType: tvMiniSeries` with any check name from the dashboard.
To see all flagged checks first, ask Claude: *"use list_flagged_checks to show me what's flagged"*

Agent 1 will:
1. Pull the check data and replication SQL via MCP
2. Run up to 5 SQL queries to find the root cause
3. Write a structured findings report to `local-agents/investigations/`
4. Tell you the filename and verdict

### Review the findings (Agent 2)

**Start a new Claude Code conversation** (critical — fresh context = independent review).

```
/dqm-review local-agents/investigations/2026-07-12_tvMiniSeries.md
```

Agent 2 will:
1. Read Agent 1's findings without any shared context
2. Challenge the SQL reasoning
3. Run at least 1 independent query the Analyst didn't run
4. Write a review file: `investigations/..._review.md`
5. Give an overall verdict: ENDORSE / ENDORSE-WITH-CAVEATS / RETURN-FOR-REWORK

---

## Output files

All output goes to `local-agents/investigations/`:

```
investigations/
├── 2026-07-12_tvMiniSeries.md         ← Agent 1 findings
├── 2026-07-12_tvMiniSeries_review.md  ← Agent 2 review
└── ...
```

These files are the audit trail. Keep them — they show the reasoning chain.

---

## MCP tools available to agents

| Tool | What it does |
|---|---|
| `list_flagged_checks(year, n_hist)` | Returns all flagged checks as JSON |
| `get_check_detail(check_name, year)` | Full context + replication SQL for one check |
| `run_sql(query)` | Executes SQL against local DuckDB, returns table |
| `save_finding(filename, content)` | Saves a markdown file to `investigations/` |

You can also use these tools directly in a Claude Code conversation (no slash command needed).
Example: *"use get_check_detail to show me the Null Rate check for runtimeMinutes"*

---

## Limitations

### What the two-agent setup improves
- Reduces false confidence: Agent 2 challenges Agent 1's reasoning
- Forces SQL verification: Agent 2 must run at least one independent query
- Catches logical gaps: "the query doesn't actually prove the claim"
- Provides a written audit trail of both perspectives

### What it does NOT solve
- **Both agents can hallucinate.** The Reviewer is also an LLM. It can confirm wrong findings
  or invent new errors. Human review of both outputs remains mandatory.
- **Context isolation is partial.** Agent 2 only sees what Agent 1 wrote down.
  If Agent 1 omitted a key result, Agent 2 cannot see it.
- **Non-determinism.** The same check investigated twice may yield different conclusions.
  This is why saving the output files matters — they preserve a specific run's reasoning.
- **Rate limits.** Claude Pro has hourly usage limits. Run 2–3 investigation+review pairs
  per session. If you hit limits, wait ~1 hour.
- **Sequential only.** Agent 1 must finish before Agent 2 starts. No real-time handoff.

### Banking compliance (read this)
These agents are **decision-support tools, not decision-making systems**.

In a real banking context:
- All AI outputs require human sign-off before any operational action
- Model outputs must be documented under your firm's model risk management (MRM) framework
- Regulatory approval may be required before use in any compliance or risk process
- Never automate escalations, remediation, or reporting based solely on agent output

This PoC demonstrates the agent orchestration pattern. Production use requires additional
controls: immutable audit logs, access control, model versioning, bias testing, and MRM review.

---

## Troubleshooting

**MCP server not connecting**
- Check Claude Code MCP panel for error messages
- Run `python local-agents/dqm_mcp_server.py` manually — if it errors, fix the dependency first
- Ensure `fastmcp` is installed: `pip install fastmcp`
- Ensure `duckdb`, `anthropic` packages are installed (they're already in the project)

**"No check matching..." error**
- Run `list_flagged_checks()` to see exact check names
- Use a partial name: `tvMiniSeries` instead of the full name

**Agent doesn't use MCP tools**
- Make sure the MCP server shows as connected (green) before running the slash command
- If it shows disconnected, restart Claude Code and check the error in the MCP panel
