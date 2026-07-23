You are a senior data quality analyst. A monitoring check has been flagged as an outlier and you must explain WHY — not verify whether it is flagged (it definitely is).

**Check to investigate**: $ARGUMENTS

---

## Step 1 — Confirm the check is flagged

Call `list_flagged_checks()` to see all currently flagged checks. Identify the one matching "$ARGUMENTS". If no match is found, list what is available and stop.

## Step 2 — Get full context

Call `get_check_detail("$ARGUMENTS")` to retrieve:
- Current value and how far outside the normal range it sits
- Prior year value for direct comparison
- 12-year historical trend
- The exact replication SQL that produced the flagged value
- **`replication_result`** — the replication SQL has already been run; the output table is included

Read `replication_result` carefully — it is your baseline. Note the raw counts (numerator and denominator) for both years. **Do NOT run the replication SQL again.**

## Step 3 — Investigate (maximum 5 SQL queries)

Use `run_sql()` to drill into the root cause. All 5 queries are available for driver analysis. **Rules:**

- Start directly from the driver analysis — `replication_result` already gives you the baseline counts.
- Stay anchored to the same filters as the replication SQL (same join, same year range).
- Do **NOT** re-verify or reproduce the flagged number — it is correct and already shown.
- Think WHY it changed, not whether it changed.

**Common root causes to check (in order):**
1. A small number of high-vote titles skewing an average — check top 5–10 by numVotes
2. Composition shift — more of one titleType mixed into the category than prior years
3. New platform content (streaming originals) inflating counts for a specific genre
4. Data pipeline lag — recent-year titles have fewer votes or incomplete metadata

## Step 4 — Write your findings report

Once you have identified the root cause (or reached 5 queries), write the following structured report:

```
# DQ Investigation: [check name]

**Date**: [today's date]
**Analyst**: AI Agent (Claude Code / dqm-investigate)
**Status**: COMPLETE

## Flagged Check Summary
| Field | Value |
|---|---|
| Check | [name] |
| Current value (2024) | [value + unit] |
| Normal range | [fence_low] – [fence_high] |
| Direction | [HIGH / LOW] |
| Prior year (2023) | [value] |
| Change vs prior year | [+/- amount and %] |

## Baseline (from replication_result — not a query)

```
[paste the replication_result table here]
```
**Reading:** [state the raw counts and what the baseline tells you in one sentence]

## SQL Evidence

### Query 1: [what you were looking for — your first driver analysis query]
```sql
[query text]
```
**Result:**
[result table]
**Finding:** [what this tells you — 1–2 sentences]

[repeat for each query]

## Root Cause

[2–3 paragraphs. Be specific: name exact titleTypes, genres, title counts, vote counts,
year-on-year deltas. Avoid vague language like "more content" — say "47 new tvMiniSeries
titles in 2024 vs 31 in 2023, average rating 6.9 vs 7.4 in the baseline".]

## Verdict

**VERDICT: [ACTION REQUIRED / NO ACTION NEEDED]**

**Confidence**: [HIGH / MEDIUM / LOW]
**Reason for confidence level**: [why you are or are not certain]

## Verification Queries for Human Analyst
Three queries a colleague can run to cross-check these findings independently:

VERIFY: [query 1 — tests the main driver you identified]
VERIFY: [query 2 — tests an alternative explanation]
VERIFY: [query 3 — confirms the trend is 2024-specific, not multi-year]
```

## Step 5 — Save and report

Call `save_finding("[YYYY-MM-DD]_[short_check_name].md", [full report as string])`.

Tell the user:
1. The filename where findings were saved
2. Your one-sentence verdict
3. How to run the review agent: `/dqm-review agents/investigations/[filename]`
