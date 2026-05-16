"""
Statistical monitoring checks using Tukey's IQR fences.
Each check compares the current period against a 12-period historical baseline.
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import duckdb

DATA = str(Path(__file__).parent / "data")


@dataclass
class CheckResult:
    name: str           # Human-readable check name
    metric: str         # Field or category being checked
    current_val: float  # Value in the current period
    hist_vals: list     # One value per historical period (for sparkline)
    fence_low: float    # Tukey lower fence
    fence_high: float   # Tukey upper fence
    flagged: bool
    flag_direction: str # "HIGH", "LOW", or ""
    unit: str = ""      # e.g. "%", "votes", "min"
    context: dict = field(default_factory=dict)  # Extra info for the AI agent


def _tukey_fences(values: list) -> tuple[float, float]:
    """Return (lower_fence, upper_fence) using Tukey's 1.5×IQR rule."""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    q1 = sorted_vals[n // 4]
    q3 = sorted_vals[(3 * n) // 4]
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def get_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"""
        CREATE VIEW basics AS
        SELECT * FROM read_csv(
            '{DATA}/title.basics.tsv.gz',
            delim='\t', header=true, nullstr='\\N'
        )
    """)
    con.execute(f"""
        CREATE VIEW ratings AS
        SELECT
            tconst,
            CAST(averageRating AS DOUBLE) AS averageRating,
            CAST(numVotes AS INTEGER) AS numVotes
        FROM read_csv(
            '{DATA}/title.ratings.tsv.gz',
            delim='\t', header=true, nullstr='\\N'
        )
    """)
    return con


# ---------------------------------------------------------------------------
# CHECK TYPE 1: Numerical variable monitoring
# For each numeric field, compute the annual mean per period and apply
# Tukey fences. Flagged if the current year mean is outside the fences.
# ---------------------------------------------------------------------------

def run_numerical_checks(
    con: duckdb.DuckDBPyConnection,
    current_year: int,
    hist_years: list[int],
) -> list[CheckResult]:
    all_years = hist_years + [current_year]
    year_list = ", ".join(str(y) for y in all_years)
    results = []

    checks = [
        # (label, SQL expression for the value, unit, title_type filter)
        ("Avg Rating (movies)", "AVG(r.averageRating)", "rating", "b.titleType = 'movie'"),
        ("Avg Vote Count (movies)", "AVG(r.numVotes)", "votes", "b.titleType = 'movie'"),
        ("Avg Runtime (movies)", "AVG(CAST(b.runtimeMinutes AS DOUBLE))", "min",
         "b.titleType = 'movie' AND b.runtimeMinutes IS NOT NULL"),
    ]

    for label, agg_expr, unit, where in checks:
        rows = con.execute(f"""
            SELECT b.startYear AS yr, {agg_expr} AS val
            FROM basics b
            JOIN ratings r USING (tconst)
            WHERE b.startYear IN ({year_list})
              AND {where}
            GROUP BY b.startYear
            ORDER BY b.startYear
        """).fetchall()

        by_year = {int(r[0]): r[1] for r in rows if r[1] is not None}
        hist_vals = [by_year[y] for y in hist_years if y in by_year]
        current_val = by_year.get(current_year)

        if not hist_vals or current_val is None:
            continue

        low, high = _tukey_fences(hist_vals)
        flagged = current_val < low or current_val > high
        direction = "HIGH" if current_val > high else ("LOW" if current_val < low else "")

        results.append(CheckResult(
            name=label,
            metric=label,
            current_val=round(current_val, 2),
            hist_vals=[round(v, 2) for v in hist_vals],
            fence_low=round(low, 2),
            fence_high=round(high, 2),
            flagged=flagged,
            flag_direction=direction,
            unit=unit,
            context={
                "check_type": "numerical",
                "current_year": current_year,
                "hist_years": hist_years,
                "by_year": {k: round(v, 2) for k, v in by_year.items()},
                "sql_hint": f"SELECT b.startYear, {agg_expr} FROM basics b JOIN ratings r USING (tconst) WHERE {where} GROUP BY b.startYear ORDER BY b.startYear",
            },
        ))

    return results


# ---------------------------------------------------------------------------
# CHECK TYPE 2: Null rate monitoring
# For each field, compute % null per period and flag if the current year's
# null rate is above the Tukey upper fence (spike = suspicious).
# ---------------------------------------------------------------------------

def run_null_checks(
    con: duckdb.DuckDBPyConnection,
    current_year: int,
    hist_years: list[int],
) -> list[CheckResult]:
    all_years = hist_years + [current_year]
    year_list = ", ".join(str(y) for y in all_years)
    results = []

    null_checks = [
        ("Null Rate: runtimeMinutes (movies)",
         "SUM(CASE WHEN b.runtimeMinutes IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*)",
         "b.titleType = 'movie'"),
        ("Null Rate: genres (all titles)",
         "SUM(CASE WHEN b.genres IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*)",
         "1=1"),
    ]

    for label, null_expr, where in null_checks:
        rows = con.execute(f"""
            SELECT b.startYear AS yr, {null_expr} AS null_pct
            FROM basics b
            JOIN ratings r USING (tconst)
            WHERE b.startYear IN ({year_list})
              AND {where}
            GROUP BY b.startYear
            ORDER BY b.startYear
        """).fetchall()

        by_year = {int(r[0]): r[1] for r in rows if r[1] is not None}
        hist_vals = [by_year[y] for y in hist_years if y in by_year]
        current_val = by_year.get(current_year)

        if not hist_vals or current_val is None:
            continue

        low, high = _tukey_fences(hist_vals)
        # For null rates, only flag increases (decrease in nulls is fine)
        flagged = current_val > high
        direction = "HIGH" if flagged else ""

        results.append(CheckResult(
            name=label,
            metric=label,
            current_val=round(current_val, 2),
            hist_vals=[round(v, 2) for v in hist_vals],
            fence_low=round(low, 2),
            fence_high=round(high, 2),
            flagged=flagged,
            flag_direction=direction,
            unit="%",
            context={
                "check_type": "null_rate",
                "current_year": current_year,
                "hist_years": hist_years,
                "by_year": {k: round(v, 2) for k, v in by_year.items()},
            },
        ))

    return results


# ---------------------------------------------------------------------------
# CHECK TYPE 3: Categorical distribution monitoring
# For each category value, compute its proportion per period and flag
# if the current year proportion shifts significantly outside Tukey fences.
# ---------------------------------------------------------------------------

def run_categorical_checks(
    con: duckdb.DuckDBPyConnection,
    current_year: int,
    hist_years: list[int],
) -> list[CheckResult]:
    all_years = hist_years + [current_year]
    year_list = ", ".join(str(y) for y in all_years)
    results = []

    # titleType distribution
    type_rows = con.execute(f"""
        WITH totals AS (
            SELECT startYear, COUNT(*) AS total
            FROM basics b
            JOIN ratings r USING (tconst)
            WHERE startYear IN ({year_list})
            GROUP BY startYear
        )
        SELECT b.startYear, b.titleType, COUNT(*) * 100.0 / t.total AS pct
        FROM basics b
        JOIN ratings r USING (tconst)
        JOIN totals t ON b.startYear = t.startYear
        WHERE b.startYear IN ({year_list})
          AND b.titleType IS NOT NULL
        GROUP BY b.startYear, b.titleType, t.total
        ORDER BY b.startYear, b.titleType
    """).fetchall()

    # Group by titleType
    from collections import defaultdict
    type_by_cat: dict[str, dict[int, float]] = defaultdict(dict)
    for yr, cat, pct in type_rows:
        type_by_cat[cat][int(yr)] = pct

    for cat, by_year in type_by_cat.items():
        hist_vals = [by_year[y] for y in hist_years if y in by_year]
        current_val = by_year.get(current_year)
        if len(hist_vals) < 6 or current_val is None:
            continue

        low, high = _tukey_fences(hist_vals)
        flagged = current_val < low or current_val > high
        direction = "HIGH" if current_val > high else ("LOW" if current_val < low else "")

        results.append(CheckResult(
            name=f"titleType: {cat}",
            metric=f"titleType={cat}",
            current_val=round(current_val, 2),
            hist_vals=[round(v, 2) for v in hist_vals],
            fence_low=round(low, 2),
            fence_high=round(high, 2),
            flagged=flagged,
            flag_direction=direction,
            unit="%",
            context={
                "check_type": "categorical",
                "category_field": "titleType",
                "category_value": cat,
                "current_year": current_year,
                "hist_years": hist_years,
                "by_year": {k: round(v, 2) for k, v in by_year.items()},
            },
        ))

    # Top genres distribution (treat genres string as-is for simplicity)
    genre_rows = con.execute(f"""
        WITH totals AS (
            SELECT startYear, COUNT(*) AS total
            FROM basics b
            JOIN ratings r USING (tconst)
            WHERE startYear IN ({year_list})
              AND b.genres IS NOT NULL
            GROUP BY startYear
        ),
        top_genres AS (
            SELECT b.genres
            FROM basics b
            JOIN ratings r USING (tconst)
            WHERE b.startYear IN ({year_list}) AND b.genres IS NOT NULL
            GROUP BY b.genres
            ORDER BY COUNT(*) DESC
            LIMIT 15
        )
        SELECT b.startYear, b.genres, COUNT(*) * 100.0 / t.total AS pct
        FROM basics b
        JOIN ratings r USING (tconst)
        JOIN totals t ON b.startYear = t.startYear
        WHERE b.startYear IN ({year_list})
          AND b.genres IN (SELECT genres FROM top_genres)
        GROUP BY b.startYear, b.genres, t.total
        ORDER BY b.startYear, b.genres
    """).fetchall()

    genre_by_cat: dict[str, dict[int, float]] = defaultdict(dict)
    for yr, cat, pct in genre_rows:
        genre_by_cat[cat][int(yr)] = pct

    for cat, by_year in genre_by_cat.items():
        hist_vals = [by_year[y] for y in hist_years if y in by_year]
        current_val = by_year.get(current_year)
        if len(hist_vals) < 6 or current_val is None:
            continue

        low, high = _tukey_fences(hist_vals)
        flagged = current_val < low or current_val > high
        direction = "HIGH" if current_val > high else ("LOW" if current_val < low else "")

        results.append(CheckResult(
            name=f"Genre: {cat}",
            metric=f"genre={cat}",
            current_val=round(current_val, 2),
            hist_vals=[round(v, 2) for v in hist_vals],
            fence_low=round(low, 2),
            fence_high=round(high, 2),
            flagged=flagged,
            flag_direction=direction,
            unit="%",
            context={
                "check_type": "categorical",
                "category_field": "genres",
                "category_value": cat,
                "current_year": current_year,
                "hist_years": hist_years,
                "by_year": {k: round(v, 2) for k, v in by_year.items()},
            },
        ))

    return results


def run_all_checks(
    con: duckdb.DuckDBPyConnection,
    current_year: int = 2024,
    n_hist: int = 12,
) -> list[CheckResult]:
    hist_years = list(range(current_year - n_hist, current_year))
    numerical = run_numerical_checks(con, current_year, hist_years)
    nulls = run_null_checks(con, current_year, hist_years)
    categorical = run_categorical_checks(con, current_year, hist_years)
    return numerical + nulls + categorical
