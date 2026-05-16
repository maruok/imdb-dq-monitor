"""
IMDB Data Quality Dashboard
Run: streamlit run app.py
"""

import streamlit as st
import plotly.graph_objects as go
from data_loader import ensure_data
from checks import get_connection, run_all_checks, CheckResult
from investigator import investigate

st.set_page_config(
    page_title="IMDB Data Quality Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Global CSS — dark theme inspired by the design reference
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* ── Hide Streamlit chrome ── */
#MainMenu, header, footer { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }

/* ── Base ── */
html, body, [data-testid="stAppViewContainer"], .stApp {
    background-color: #0d0f1a !important;
    color: #e8eaf0 !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: #13152a !important;
    border-right: 1px solid #1e2140;
}
[data-testid="stSidebar"] * { color: #c8cadc !important; }
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stSlider label { color: #7b7fa8 !important; font-size: 0.78rem !important; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent;
    border-bottom: 1px solid #1e2140;
    gap: 8px;
}
.stTabs [data-baseweb="tab"] {
    background: #13152a;
    border-radius: 8px 8px 0 0;
    color: #7b7fa8 !important;
    padding: 8px 20px;
    border: 1px solid #1e2140;
    border-bottom: none;
}
.stTabs [aria-selected="true"] {
    background: #1a1d35 !important;
    color: #b5e550 !important;
    border-color: #b5e550 !important;
}

/* ── Cards ── */
.dq-card {
    background: #13152a;
    border: 1px solid #1e2140;
    border-radius: 16px;
    padding: 20px 24px;
    margin-bottom: 12px;
}
.dq-card-accent {
    background: linear-gradient(135deg, #1a2a0a 0%, #13152a 60%);
    border: 1px solid #3a5c10;
    border-radius: 16px;
    padding: 20px 24px;
    margin-bottom: 12px;
}

/* ── Summary metric cards ── */
.summary-card {
    background: #13152a;
    border: 1px solid #1e2140;
    border-radius: 16px;
    padding: 20px;
    text-align: center;
}
.summary-number {
    font-size: 2.8rem;
    font-weight: 800;
    line-height: 1;
    margin: 8px 0 4px 0;
}
.summary-label {
    font-size: 0.78rem;
    color: #7b7fa8;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
.color-green  { color: #b5e550; }
.color-red    { color: #ff4b6e; }
.color-white  { color: #e8eaf0; }
.color-muted  { color: #7b7fa8; }

/* ── Section headers ── */
.section-header {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #7b7fa8;
    margin: 28px 0 12px 0;
    padding-bottom: 8px;
    border-bottom: 1px solid #1e2140;
}

/* ── Check row ── */
.check-name { font-size: 0.9rem; font-weight: 500; color: #c8cadc; }
.check-name-flagged { font-size: 0.9rem; font-weight: 700; color: #e8eaf0; }
.check-value { font-size: 1.1rem; font-weight: 700; }
.check-range { font-size: 0.78rem; color: #7b7fa8; }

/* ── Status pills ── */
.pill {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.pill-ok {
    background: rgba(181, 229, 80, 0.12);
    color: #b5e550;
    border: 1px solid rgba(181, 229, 80, 0.35);
}
.pill-high {
    background: rgba(255, 75, 110, 0.12);
    color: #ff4b6e;
    border: 1px solid rgba(255, 75, 110, 0.35);
}
.pill-low {
    background: rgba(84, 160, 255, 0.12);
    color: #54a0ff;
    border: 1px solid rgba(84, 160, 255, 0.35);
}

/* ── Investigate button ── */
.stButton > button {
    background: #1a1d35 !important;
    color: #b5e550 !important;
    border: 1px solid #b5e550 !important;
    border-radius: 8px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    padding: 4px 14px !important;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: #b5e550 !important;
    color: #0d0f1a !important;
}

/* Primary button (Run query) */
.stButton > button[kind="primary"] {
    background: #b5e550 !important;
    color: #0d0f1a !important;
    border: none !important;
    font-weight: 700 !important;
}
.stButton > button[kind="primary"]:hover {
    background: #c8f060 !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #0d0f1a !important;
    border: 1px solid #1e2140 !important;
    border-radius: 12px !important;
}

/* ── Code blocks ── */
.stCodeBlock, pre {
    background: #090b17 !important;
    border: 1px solid #1e2140 !important;
    border-radius: 8px !important;
}

/* ── Text area ── */
.stTextArea textarea {
    background: #090b17 !important;
    color: #c8cadc !important;
    border: 1px solid #1e2140 !important;
    border-radius: 8px !important;
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
}

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: #13152a;
    border: 1px solid #1e2140;
    border-radius: 12px;
    padding: 12px 16px;
}
[data-testid="stMetricValue"] { color: #e8eaf0 !important; }
[data-testid="stMetricLabel"] { color: #7b7fa8 !important; font-size: 0.75rem !important; }

/* ── Info/success/warning boxes ── */
.stInfo, .stSuccess, .stWarning {
    border-radius: 10px !important;
    border: none !important;
}

/* ── Dividers ── */
hr { border-color: #1e2140 !important; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("""
    <div style='padding: 8px 0 24px 0;'>
        <div style='font-size:1.3rem; font-weight:800; color:#b5e550; letter-spacing:0.04em;'>
            📊 DQ Monitor
        </div>
        <div style='font-size:0.72rem; color:#7b7fa8; margin-top:2px;'>IMDB Data Quality</div>
    </div>
    """, unsafe_allow_html=True)

    current_year = st.selectbox(
        "CURRENT PERIOD", options=list(range(2024, 2009, -1)), index=0
    )
    n_hist = st.slider("HISTORICAL PERIODS", min_value=6, max_value=15, value=12)
    st.markdown("---")
    st.markdown("""
    <div style='font-size:0.72rem; color:#7b7fa8; line-height:1.6;'>
        Flags anomalies using <b style='color:#c8cadc'>Tukey IQR fences</b>.<br>
        Current period vs preceding N years.<br><br>
        <b style='color:#b5e550'>Click Investigate</b> to launch the AI agent for a flagged check.
    </div>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Shared resources
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_con():
    with st.spinner("Checking data files..."):
        ensure_data()
    return get_connection()

@st.cache_data(show_spinner=False, ttl=300)
def load_checks(year: int, n: int):
    return run_all_checks(get_con(), current_year=year, n_hist=n)

if "investigations" not in st.session_state:
    st.session_state.investigations = {}
if "sql_query" not in st.session_state:
    st.session_state.sql_query = (
        "-- Available views: basics, ratings\n"
        "-- basics: tconst, titleType, primaryTitle, startYear, endYear, runtimeMinutes, genres\n"
        "-- ratings: tconst, averageRating, numVotes\n\n"
        "SELECT b.titleType, COUNT(*) AS cnt, ROUND(AVG(r.averageRating), 2) AS avg_rating\n"
        "FROM basics b JOIN ratings r USING (tconst)\n"
        "WHERE b.startYear = 2024\n"
        "GROUP BY b.titleType\n"
        "ORDER BY cnt DESC"
    )


# ---------------------------------------------------------------------------
# Sparkline chart for a check row
# ---------------------------------------------------------------------------
def make_sparkline(check: CheckResult) -> go.Figure:
    by_year = check.context.get("by_year", {})
    curr = check.context.get("current_year")
    years = sorted(by_year.keys())
    values = [by_year[y] for y in years]
    labels = [str(y) for y in years]

    bar_colors = []
    for y in years:
        if y == curr and check.flagged:
            bar_colors.append("#ff4b6e")
        elif y == curr:
            bar_colors.append("#b5e550")
        else:
            bar_colors.append("#2a2d4a")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=values,
        marker_color=bar_colors,
        marker_line_width=0,
        hovertemplate="%{x}: %{y:.2f}<extra></extra>",
    ))

    # Tukey fence lines
    fig.add_hline(y=check.fence_high, line_dash="dot", line_color="#ff9f43", line_width=1.2,
                  annotation_text="", annotation_position="right")
    if check.fence_low > 0:
        fig.add_hline(y=check.fence_low, line_dash="dot", line_color="#54a0ff", line_width=1.2)

    # Normal range shading
    fig.add_hrect(y0=check.fence_low, y1=check.fence_high,
                  fillcolor="rgba(181,229,80,0.04)", line_width=0)

    fig.update_layout(
        height=70,
        margin=dict(l=0, r=0, t=4, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        bargap=0.15,
    )
    return fig


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------
st.markdown(f"""
<div style='padding: 8px 0 4px 0;'>
    <div style='font-size:1.6rem; font-weight:800; color:#e8eaf0;'>Data Quality Monitor</div>
    <div style='font-size:0.8rem; color:#7b7fa8; margin-top:2px;'>
        Period <b style='color:#b5e550'>{current_year}</b> &nbsp;·&nbsp;
        Baseline {current_year - n_hist}–{current_year - 1} &nbsp;·&nbsp;
        IMDB dataset
    </div>
</div>
""", unsafe_allow_html=True)

tab_dashboard, tab_sql = st.tabs(["📋  Dashboard", "🔍  SQL Playground"])


# ===========================================================================
# TAB 1 — DASHBOARD
# ===========================================================================
with tab_dashboard:
    with st.spinner("Running checks..."):
        checks = load_checks(current_year, n_hist)

    flagged = [c for c in checks if c.flagged]
    ok_checks = [c for c in checks if not c.flagged]

    # Summary banner
    s1, s2, s3, s4 = st.columns(4)
    for col, number, label, cls in [
        (s1, len(checks), "Checks Run", "color-white"),
        (s2, len(flagged), "Flagged", "color-red"),
        (s3, len(ok_checks), "Passed", "color-green"),
        (s4, f"{len(flagged)/len(checks)*100:.0f}%", "Failure Rate", "color-red" if flagged else "color-green"),
    ]:
        col.markdown(f"""
        <div class="summary-card">
            <div class="summary-label">{label}</div>
            <div class="summary-number {cls}">{number}</div>
        </div>
        """, unsafe_allow_html=True)

    def send_to_playground(q):
        st.session_state.sql_query = q

    def render_check_row(check: CheckResult, section_key: str):
        key = f"{section_key}_{check.name}"
        inv_key = key + "_inv"

        c_name, c_chart, c_val, c_range, c_status, c_action = st.columns([2.4, 2, 1, 1.6, 0.9, 1.1])

        name_cls = "check-name-flagged" if check.flagged else "check-name"
        c_name.markdown(f"<div class='{name_cls}' style='padding-top:18px'>{check.name}</div>",
                        unsafe_allow_html=True)

        c_chart.plotly_chart(make_sparkline(check), use_container_width=True,
                             config={"displayModeBar": False})

        val_color = "#ff4b6e" if check.flagged else "#b5e550"
        c_val.markdown(
            f"<div class='check-value' style='color:{val_color}; padding-top:18px'>"
            f"{check.current_val}{check.unit}</div>",
            unsafe_allow_html=True,
        )
        c_range.markdown(
            f"<div class='check-range' style='padding-top:20px'>"
            f"{check.fence_low}{check.unit} – {check.fence_high}{check.unit}</div>",
            unsafe_allow_html=True,
        )

        if check.flagged:
            pill_cls = "pill-high" if check.flag_direction == "HIGH" else "pill-low"
            c_status.markdown(
                f"<div style='padding-top:18px'><span class='pill {pill_cls}'>"
                f"{check.flag_direction}</span></div>",
                unsafe_allow_html=True,
            )
            if c_action.button("Investigate", key=key):
                with st.spinner(f"AI investigating..."):
                    inv = investigate(check, get_con())
                    st.session_state.investigations[inv_key] = inv
        else:
            c_status.markdown(
                "<div style='padding-top:18px'><span class='pill pill-ok'>OK</span></div>",
                unsafe_allow_html=True,
            )

        # Investigation result
        if inv_key in st.session_state.investigations:
            inv = st.session_state.investigations[inv_key]
            with st.expander(f"Investigation: {check.name}", expanded=True):
                # Token cost banner
                t1, t2, t3, t4 = st.columns(4)
                t1.metric("Input tokens", f"{inv.input_tokens:,}")
                t2.metric("Output tokens", f"{inv.output_tokens:,}")
                t3.metric("Total tokens", f"{inv.total_tokens:,}")
                t4.metric("Cost", f"${inv.cost_usd:.4f}")

                st.markdown("---")

                # Steps
                if inv.steps:
                    st.markdown("#### Reasoning trace")
                    for i, step in enumerate(inv.steps, 1):
                        st.markdown(f"**Step {i}**")
                        if step.reasoning:
                            st.info(step.reasoning)
                        sc1, sc2 = st.columns([5, 1])
                        sc1.code(step.sql, language="sql")
                        if sc2.button("▶ Run", key=f"{inv_key}_step_{i}"):
                            send_to_playground(step.sql)
                            st.info("Sent to SQL Playground ↑")
                        st.code(step.result)
                    st.markdown("---")

                # Summary
                st.markdown("#### Summary")
                lines = inv.summary.split("\n")
                summary_lines = [l for l in lines if not l.startswith("VERIFY:")]
                verify_lines = [l[len("VERIFY:"):].strip() for l in lines if l.startswith("VERIFY:")]

                if inv.completed:
                    st.success("\n".join(summary_lines))
                else:
                    st.warning("\n".join(summary_lines))

                if verify_lines:
                    st.markdown("**Verification queries:**")
                    for i, q in enumerate(verify_lines):
                        vc1, vc2 = st.columns([5, 1])
                        vc1.code(q, language="sql")
                        if vc2.button("▶ Run", key=f"{inv_key}_verify_{i}"):
                            send_to_playground(q)
                            st.info("Sent to SQL Playground ↑")

        st.markdown("<hr style='border-color:#1a1d35; margin:4px 0'>", unsafe_allow_html=True)

    def render_section(title: str, section_checks: list[CheckResult], key_prefix: str):
        if not section_checks:
            return
        st.markdown(f"<div class='section-header'>{title}</div>", unsafe_allow_html=True)

        # Column headers
        h = st.columns([2.4, 2, 1, 1.6, 0.9, 1.1])
        for col, label in zip(h, ["Check", "12-period trend", "Current", "Normal range", "Status", "Action"]):
            col.markdown(f"<div style='font-size:0.72rem; color:#7b7fa8; font-weight:600; "
                         f"text-transform:uppercase; letter-spacing:0.08em;'>{label}</div>",
                         unsafe_allow_html=True)

        # Flagged first
        for check in sorted(section_checks, key=lambda c: (not c.flagged, c.name)):
            render_check_row(check, key_prefix)

    numerical = [c for c in checks if c.context.get("check_type") == "numerical"]
    nulls = [c for c in checks if c.context.get("check_type") == "null_rate"]
    categorical = [c for c in checks if c.context.get("check_type") == "categorical"]

    render_section("Numerical Variables", numerical, "num")
    render_section("Null Rate Monitoring", nulls, "null")
    render_section("Categorical Distribution", categorical, "cat")


# ===========================================================================
# TAB 2 — SQL PLAYGROUND
# ===========================================================================
with tab_sql:
    st.markdown("<div class='section-header'>SQL Playground</div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:0.8rem; color:#7b7fa8; margin-bottom:16px;'>"
        "Query the IMDB data directly. Views: <code>basics</code>, <code>ratings</code></div>",
        unsafe_allow_html=True,
    )

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
            ec1, ec2 = st.columns([5, 1])
            ec1.markdown(f"<div style='font-size:0.85rem; font-weight:600; color:#c8cadc; "
                         f"padding:6px 0'>{label}</div>", unsafe_allow_html=True)
            if ec2.button("Use", key=f"ex_{label}"):
                st.session_state.sql_query = sql
                st.rerun()
            st.code(sql, language="sql")

    query = st.text_area("Write your SQL query:", value=st.session_state.sql_query, height=200)

    rc1, rc2, _ = st.columns([1.2, 1, 6])
    run_clicked = rc1.button("▶  Run query", type="primary")
    if rc2.button("Clear"):
        st.session_state.sql_query = ""
        st.rerun()

    if run_clicked and query.strip():
        con = get_con()
        try:
            cursor = con.execute(query)
            rows = cursor.fetchall()
            cols_names = [desc[0] for desc in cursor.description]
            if not rows:
                st.info("Query returned no rows.")
            else:
                data = {cols_names[i]: [r[i] for r in rows] for i in range(len(cols_names))}
                st.markdown(
                    f"<div style='font-size:0.78rem; color:#b5e550; margin:8px 0'>"
                    f"✓ {len(rows)} row(s) returned</div>",
                    unsafe_allow_html=True,
                )
                st.dataframe(data, use_container_width=True)
        except Exception as e:
            st.error(f"SQL Error: {e}")
