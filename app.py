"""
IMDB Data Quality Dashboard
Run: streamlit run app.py
"""

import streamlit as st
from data_loader import ensure_data
from checks import get_connection, run_all_checks, CheckResult
from investigator import investigate

st.set_page_config(
    page_title="IMDB Data Quality Monitor",
    page_icon="📊",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📊 DQ Monitor")
    st.markdown("---")
    current_year = st.selectbox(
        "Current period (year)",
        options=list(range(2024, 2009, -1)),
        index=0,
    )
    n_hist = st.slider("Historical periods", min_value=6, max_value=15, value=12)
    st.markdown("---")
    st.caption(
        "Each check compares the selected year against the preceding N years "
        "using Tukey's IQR fences (Q1−1.5×IQR, Q3+1.5×IQR)."
    )

# ---------------------------------------------------------------------------
# Shared resources (cached)
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_con():
    with st.spinner("Checking data files..."):
        ensure_data()
    return get_connection()

@st.cache_data(show_spinner="Running checks...", ttl=300)
def load_checks(year: int, n: int):
    return run_all_checks(get_con(), current_year=year, n_hist=n)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "investigations" not in st.session_state:
    st.session_state.investigations = {}
if "sql_query" not in st.session_state:
    st.session_state.sql_query = (
        "-- Available views: basics, ratings\n"
        "-- basics columns: tconst, titleType, primaryTitle, startYear, endYear, runtimeMinutes, genres\n"
        "-- ratings columns: tconst, averageRating, numVotes\n\n"
        "SELECT b.titleType, COUNT(*) AS cnt, ROUND(AVG(r.averageRating), 2) AS avg_rating\n"
        "FROM basics b JOIN ratings r USING (tconst)\n"
        "WHERE b.startYear = 2024\n"
        "GROUP BY b.titleType\n"
        "ORDER BY cnt DESC"
    )

# ---------------------------------------------------------------------------
# Title and tabs
# ---------------------------------------------------------------------------
st.title("IMDB Data Quality Monitor")
st.caption(f"Current period: **{current_year}**  |  Baseline: {current_year - n_hist}–{current_year - 1}")

tab_dashboard, tab_sql = st.tabs(["📋 Dashboard", "🔍 SQL Playground"])

# ===========================================================================
# TAB 1 — DASHBOARD
# ===========================================================================
with tab_dashboard:
    with st.spinner("Running all checks..."):
        checks = load_checks(current_year, n_hist)

    flagged = [c for c in checks if c.flagged]
    ok = [c for c in checks if not c.flagged]

    col1, col2, col3 = st.columns(3)
    col1.metric("Checks run", len(checks))
    col2.metric("Flagged", len(flagged),
                delta=f"+{len(flagged)}" if flagged else None,
                delta_color="inverse")
    col3.metric("OK", len(ok))
    st.markdown("---")

    def send_to_playground(query: str):
        """Put a query in the SQL playground and switch focus there."""
        st.session_state.sql_query = query

    def render_check_row(check: CheckResult, section_key: str):
        key = f"{section_key}_{check.name}"
        inv_key = key + "_inv"

        cols = st.columns([3, 1.5, 2.5, 1.2, 1.5])

        if check.flagged:
            cols[0].markdown(f"**{check.name}**")
            badge = f"🔴 {check.flag_direction}"
        else:
            cols[0].markdown(check.name)
            badge = "✅ OK"

        cols[1].markdown(f"`{check.current_val}{check.unit}`")
        cols[2].markdown(f"`{check.fence_low}{check.unit}` – `{check.fence_high}{check.unit}`")
        cols[3].markdown(badge)

        if check.flagged:
            if cols[4].button("Investigate", key=key):
                with st.spinner(f"Investigating {check.name}..."):
                    result = investigate(check, get_con())
                    st.session_state.investigations[inv_key] = result

        if inv_key in st.session_state.investigations:
            inv = st.session_state.investigations[inv_key]

            with st.expander(f"Investigation: {check.name}", expanded=True):

                # Token usage & cost banner
                tcol1, tcol2, tcol3, tcol4 = st.columns(4)
                tcol1.metric("Input tokens", f"{inv.input_tokens:,}")
                tcol2.metric("Output tokens", f"{inv.output_tokens:,}")
                tcol3.metric("Total tokens", f"{inv.total_tokens:,}")
                tcol4.metric("Cost", f"${inv.cost_usd:.4f}")
                st.markdown("---")

                # Step-by-step trace
                if inv.steps:
                    st.markdown("#### Reasoning trace")
                    for i, step in enumerate(inv.steps, 1):
                        st.markdown(f"**Step {i}**")
                        if step.reasoning:
                            st.info(step.reasoning)
                        scol1, scol2 = st.columns([5, 1])
                        scol1.code(step.sql, language="sql")
                        if scol2.button("▶ Run", key=f"{inv_key}_step_{i}"):
                            send_to_playground(step.sql)
                            st.info("Sent to SQL Playground — click the tab above.")
                        st.code(step.result)
                    st.markdown("---")

                # Final summary
                st.markdown("#### Summary")
                lines = inv.summary.split("\n")
                summary_lines = [l for l in lines if not l.startswith("VERIFY:")]
                verify_lines = [l[len("VERIFY:"):].strip() for l in lines if l.startswith("VERIFY:")]

                if inv.completed:
                    st.success("\n".join(summary_lines))
                else:
                    st.warning("\n".join(summary_lines))

                if verify_lines:
                    st.markdown("**Verification queries** — click ▶ Run to open in SQL Playground:")
                    for i, q in enumerate(verify_lines):
                        vcol1, vcol2 = st.columns([5, 1])
                        vcol1.code(q, language="sql")
                        if vcol2.button("▶ Run", key=f"{inv_key}_verify_{i}"):
                            send_to_playground(q)
                            st.info("Sent to SQL Playground — click the tab above.")

    def render_section(title: str, section_checks: list[CheckResult], key_prefix: str):
        st.subheader(title)
        if not section_checks:
            st.info("No checks in this category.")
            return

        h = st.columns([3, 1.5, 2.5, 1.2, 1.5])
        h[0].markdown("**Check**")
        h[1].markdown("**Current**")
        h[2].markdown("**Normal range**")
        h[3].markdown("**Status**")
        h[4].markdown("**Action**")
        st.markdown("<hr style='margin:4px 0'>", unsafe_allow_html=True)

        for check in sorted(section_checks, key=lambda c: (not c.flagged, c.name)):
            render_check_row(check, key_prefix)
            st.markdown("<hr style='margin:2px 0; opacity:0.2'>", unsafe_allow_html=True)
        st.markdown("")

    numerical_checks = [c for c in checks if c.context.get("check_type") == "numerical"]
    null_checks = [c for c in checks if c.context.get("check_type") == "null_rate"]
    cat_checks = [c for c in checks if c.context.get("check_type") == "categorical"]

    render_section("Numerical Variables", numerical_checks, "num")
    render_section("Null Rate Monitoring", null_checks, "null")
    render_section("Categorical Distribution", cat_checks, "cat")


# ===========================================================================
# TAB 2 — SQL PLAYGROUND
# ===========================================================================
with tab_sql:
    st.subheader("SQL Playground")
    st.caption("Query the IMDB data directly. Available views: `basics`, `ratings`")

    # Example queries for quick reference
    with st.expander("Example queries"):
        examples = {
            "Title counts by type and year": (
                "SELECT b.startYear, b.titleType, COUNT(*) AS cnt\n"
                "FROM basics b JOIN ratings r USING (tconst)\n"
                "WHERE b.startYear BETWEEN 2015 AND 2024\n"
                "GROUP BY b.startYear, b.titleType\n"
                "ORDER BY b.startYear, cnt DESC"
            ),
            "Top 20 highest rated movies (1000+ votes)": (
                "SELECT b.primaryTitle, b.startYear, r.averageRating, r.numVotes\n"
                "FROM basics b JOIN ratings r USING (tconst)\n"
                "WHERE b.titleType = 'movie' AND r.numVotes >= 1000\n"
                "ORDER BY r.averageRating DESC\n"
                "LIMIT 20"
            ),
            "Null rate for runtimeMinutes by year": (
                "SELECT b.startYear,\n"
                "       COUNT(*) AS total,\n"
                "       SUM(CASE WHEN b.runtimeMinutes IS NULL THEN 1 ELSE 0 END) AS nulls,\n"
                "       ROUND(100.0 * SUM(CASE WHEN b.runtimeMinutes IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS null_pct\n"
                "FROM basics b JOIN ratings r USING (tconst)\n"
                "WHERE b.titleType = 'movie' AND b.startYear BETWEEN 2012 AND 2024\n"
                "GROUP BY b.startYear ORDER BY b.startYear"
            ),
            "Genre distribution for a specific year": (
                "SELECT b.genres, COUNT(*) AS cnt,\n"
                "       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct\n"
                "FROM basics b JOIN ratings r USING (tconst)\n"
                "WHERE b.startYear = 2024 AND b.genres IS NOT NULL\n"
                "GROUP BY b.genres ORDER BY cnt DESC\n"
                "LIMIT 20"
            ),
        }
        for label, sql in examples.items():
            ecol1, ecol2 = st.columns([5, 1])
            ecol1.markdown(f"**{label}**")
            if ecol2.button("Use", key=f"ex_{label}"):
                st.session_state.sql_query = sql
            st.code(sql, language="sql")

    st.markdown("---")

    # SQL editor
    query = st.text_area(
        "Write your SQL query:",
        value=st.session_state.sql_query,
        height=200,
        key="sql_editor",
    )

    run_col, clear_col, _ = st.columns([1, 1, 6])
    run_clicked = run_col.button("▶ Run query", type="primary")
    if clear_col.button("Clear"):
        st.session_state.sql_query = ""
        st.rerun()

    if run_clicked and query.strip():
        con = get_con()
        try:
            cursor = con.execute(query)
            rows = cursor.fetchall()
            cols = [desc[0] for desc in cursor.description]

            if not rows:
                st.info("Query returned no rows.")
            else:
                # Display as a table using st.dataframe via dict-of-lists
                data = {cols[i]: [r[i] for r in rows] for i in range(len(cols))}
                st.success(f"{len(rows)} row(s) returned")
                st.dataframe(data, use_container_width=True)
        except Exception as e:
            st.error(f"SQL Error: {e}")
