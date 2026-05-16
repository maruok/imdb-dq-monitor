"""
IMDB Data Quality Dashboard
Run: streamlit run app.py
"""

import io
import datetime
import streamlit as st
import plotly.graph_objects as go
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from data_loader import ensure_data
from checks import get_connection, run_all_checks, CheckResult
from investigator import investigate, continue_investigation, Investigation

st.set_page_config(
    page_title="IMDB Data Quality Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* ── Hide Streamlit chrome ── */
#MainMenu, header, footer { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }

/* ── App shell: light main content, dark sidebar ── */
html, body { background-color: #f0f3fa !important; }
.stApp { background-color: #f0f3fa !important; }
[data-testid="stAppViewContainer"] { background-color: #f0f3fa !important; }
[data-testid="stMain"] { background-color: #f0f3fa !important; }

/* ── Sidebar stays dark ── */
[data-testid="stSidebar"] {
    background-color: #13152a !important;
    border-right: 1px solid #1e2140;
}
[data-testid="stSidebar"] * { color: #c8cadc !important; }
[data-testid="stSidebar"] label { color: #7b7fa8 !important; font-size: 0.75rem !important; }
[data-testid="stSidebar"] .stSelectbox > div > div {
    background: #1a1d35 !important;
    border-color: #2a2d4a !important;
    color: #e8eaf0 !important;
}

/* ── Sticky tab bar ── */
/* stMain is the culprit — Streamlit sets overflow:hidden there */
section[data-testid="stMain"]        { overflow: visible !important; }
[data-testid="stMainBlockContainer"] { overflow: visible !important; }
.stTabs                              { overflow: visible !important; }

[data-baseweb="tab-list"] {
    position: -webkit-sticky !important;
    position: sticky !important;
    top: 0 !important;
    z-index: 9999 !important;
    background: #f0f3fa !important;
    border-bottom: 2px solid #dde2f0;
    gap: 4px;
    padding-top: 6px;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 8px 8px 0 0;
    color: #7b7fa8 !important;
    padding: 8px 22px;
    font-weight: 600;
    font-size: 0.85rem;
}
.stTabs [aria-selected="true"] {
    background: #f0f3fa !important;
    color: #1a1d35 !important;
    border: 2px solid #b8c8e0 !important;
    border-bottom: 2px solid #f0f3fa !important;
}

/* ── Tab panel: light background, same as page ── */
.stTabs [data-baseweb="tab-panel"] {
    background: #f0f3fa;
    border-radius: 0 12px 12px 12px;
    padding: 20px 18px 28px 18px;
    margin-top: -2px;
}

/* ── Row cards: no default styling — section containers provide colour ── */
.stTabs [data-baseweb="tab-panel"] [data-testid="stHorizontalBlock"] {
    padding: 2px 14px;
    margin: 3px 0;
    transition: box-shadow 0.15s;
}

/* ── Section containers — three distinct colour zones ── */

/* Numerical Variables: lavender/purple */
[data-testid="stVerticalBlock"]:has(.section-mark-num):not(:has(.section-mark-null)):not(:has(.section-mark-cat)) {
    background: #f0ebfc;
    border-radius: 14px;
    border-left: 4px solid #9070d0;
    padding: 12px 16px 16px 16px;
    margin-bottom: 14px;
}
[data-testid="stVerticalBlock"]:has(.section-mark-num):not(:has(.section-mark-null)):not(:has(.section-mark-cat)) [data-testid="stHorizontalBlock"] {
    background: transparent !important;
    border: none !important;
    border-bottom: 1px solid rgba(144,112,208,0.18) !important;
    border-radius: 0 !important;
    box-shadow: none !important;
}
[data-testid="stVerticalBlock"]:has(.section-mark-num):not(:has(.section-mark-null)):not(:has(.section-mark-cat)) [data-testid="stHorizontalBlock"]:last-child {
    border-bottom: none !important;
}

/* Null Rate: lime green */
[data-testid="stVerticalBlock"]:has(.section-mark-null):not(:has(.section-mark-num)):not(:has(.section-mark-cat)) {
    background: #edf8e0;
    border-radius: 14px;
    border-left: 4px solid #70a820;
    padding: 12px 16px 16px 16px;
    margin-bottom: 14px;
}
[data-testid="stVerticalBlock"]:has(.section-mark-null):not(:has(.section-mark-num)):not(:has(.section-mark-cat)) [data-testid="stHorizontalBlock"] {
    background: transparent !important;
    border: none !important;
    border-bottom: 1px solid rgba(112,168,32,0.18) !important;
    border-radius: 0 !important;
    box-shadow: none !important;
}
[data-testid="stVerticalBlock"]:has(.section-mark-null):not(:has(.section-mark-num)):not(:has(.section-mark-cat)) [data-testid="stHorizontalBlock"]:last-child {
    border-bottom: none !important;
}

/* Categorical Distribution: dark navy */
[data-testid="stVerticalBlock"]:has(.section-mark-cat):not(:has(.section-mark-num)):not(:has(.section-mark-null)) {
    background: #e9eaf5;
    border-radius: 14px;
    border-left: 4px solid #2a3268;
    padding: 12px 16px 16px 16px;
    margin-bottom: 14px;
}
[data-testid="stVerticalBlock"]:has(.section-mark-cat):not(:has(.section-mark-num)):not(:has(.section-mark-null)) [data-testid="stHorizontalBlock"] {
    background: transparent !important;
    border: none !important;
    border-bottom: 1px solid rgba(42,50,104,0.15) !important;
    border-radius: 0 !important;
    box-shadow: none !important;
}
[data-testid="stVerticalBlock"]:has(.section-mark-cat):not(:has(.section-mark-num)):not(:has(.section-mark-null)) [data-testid="stHorizontalBlock"]:last-child {
    border-bottom: none !important;
}

/* ── Section header accent colours ── */
.section-header-num  { border-bottom-color: #9070d0 !important; color: #4a2090 !important; }
.section-header-null { border-bottom-color: #70a820 !important; color: #306010 !important; }
.section-header-cat  { border-bottom-color: #2a3268 !important; color: #1a2050 !important; }

/* ── Vertical centering for check rows ── */
[data-testid="stHorizontalBlock"] {
    align-items: center !important;
}
[data-testid="stHorizontalBlock"] > [data-testid="column"] {
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
}

/* ── Summary metric cards ── */
.summary-card {
    background: #ffffff;
    border-radius: 16px;
    padding: 22px 20px;
    text-align: center;
    box-shadow: 0 2px 12px rgba(26,29,53,0.10);
    border: 1px solid #b4c4de;
}
.summary-number {
    font-size: 2.8rem;
    font-weight: 800;
    line-height: 1;
    margin: 8px 0 4px 0;
}
.summary-label {
    font-size: 0.72rem;
    color: #6b7094;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-weight: 700;
}
.color-green  { color: #2e7d32; }
.color-red    { color: #c62828; }
.color-navy   { color: #1a1d35; }
.color-muted  { color: #6b7094; }

/* ── Section headers — on light panel background ── */
.section-header {
    font-size: 0.72rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: #2a3560;
    margin: 28px 0 4px 0;
    padding-bottom: 8px;
    border-bottom: 2px solid #b4c4de;
}

/* ── Column header labels — on light panel background ── */
.col-header {
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #3a4870;
}

/* ── Row separator — hidden, cards provide spacing ── */

/* ── Check row text — on slate row background ── */
.check-name        { font-size: 0.88rem; font-weight: 600; color: #1a1d35; }
.check-name-flagged{ font-size: 0.88rem; font-weight: 700; color: #0a0c1f; }
.check-value-ok    { font-size: 1.05rem; font-weight: 700; color: #1b5e20; }
.check-value-flag  { font-size: 1.05rem; font-weight: 700; color: #b71c1c; }
.check-range       { font-size: 0.78rem; color: #2a3560; font-weight: 500; }

/* ── Status pills ── */
.pill {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
.pill-ok   { background: #e8f5e9; color: #2e7d32; border: 1px solid #a5d6a7; }
.pill-high { background: #ffebee; color: #c62828; border: 1px solid #ef9a9a; }
.pill-low  { background: #e3f2fd; color: #1565c0; border: 1px solid #90caf9; }

/* ── Buttons ── */
.stButton > button {
    background: #ffffff !important;
    color: #1a1d35 !important;
    border: 1.5px solid #dde2f0 !important;
    border-radius: 8px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    padding: 5px 14px !important;
    box-shadow: 0 1px 4px rgba(26,29,53,0.07) !important;
    transition: all 0.15s !important;
}
.stButton > button:hover {
    border-color: #8bc34a !important;
    color: #4a7c0a !important;
    box-shadow: 0 2px 8px rgba(139,195,74,0.2) !important;
}
.stButton > button[kind="primary"] {
    background: rgba(255,255,255,0.72) !important;
    color: #1a1d35 !important;
    border: 1.5px solid rgba(26,29,53,0.45) !important;
    font-weight: 700 !important;
    font-size: 0.75rem !important;
    padding: 6px 18px !important;
    border-radius: 20px !important;
    white-space: nowrap !important;
    letter-spacing: 0.04em !important;
    backdrop-filter: blur(4px) !important;
    text-align: center !important;
}
.stButton > button[kind="primary"]:hover {
    background: #1a1d35 !important;
    color: #b5e550 !important;
    border-color: #1a1d35 !important;
    box-shadow: 0 2px 10px rgba(26,29,53,0.22) !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #ffffff !important;
    border: 1px solid #e4e8f5 !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 8px rgba(26,29,53,0.05) !important;
}
[data-testid="stExpander"] summary { color: #1a1d35 !important; font-weight: 600 !important; }

/* ── Code blocks ── */
.stCodeBlock, pre {
    background: #f7f8fd !important;
    border: 1px solid #e4e8f5 !important;
    border-radius: 8px !important;
}
code { color: #3a3f6e !important; }

/* ── Text area ── */
.stTextArea textarea {
    background: #f7f8fd !important;
    color: #1a1d35 !important;
    border: 1.5px solid #dde2f0 !important;
    border-radius: 8px !important;
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
    font-size: 0.85rem !important;
}

/* ── Metrics (token cost) ── */
[data-testid="metric-container"] {
    background: #f7f8fd;
    border: 1px solid #e4e8f5;
    border-radius: 10px;
    padding: 10px 14px;
}
[data-testid="stMetricValue"] { color: #1a1d35 !important; }
[data-testid="stMetricLabel"] { color: #9399b8 !important; font-size: 0.72rem !important; }

/* ── Row separator — hidden, card spacing handles this ── */
.row-sep { display: none; }

/* ── Spinner / info / success / warning ── */
.stSpinner { color: #1a1d35 !important; }
.stInfo    { background: #e3f2fd !important; color: #1565c0 !important; border-radius: 8px !important; }
.stSuccess { background: #e8f5e9 !important; color: #2e7d32 !important; border-radius: 8px !important; }
.stWarning { background: #fff8e1 !important; color: #f57f17 !important; border-radius: 8px !important; }
.stError   { background: #ffebee !important; color: #c62828 !important; border-radius: 8px !important; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("""
    <div style='padding:8px 0 24px 0'>
        <div style='font-size:1.25rem;font-weight:800;color:#b5e550;letter-spacing:0.04em'>
            📊 DQ Monitor
        </div>
        <div style='font-size:0.7rem;color:#7b7fa8;margin-top:2px'>IMDB Data Quality</div>
    </div>
    """, unsafe_allow_html=True)

    current_year = st.selectbox("CURRENT PERIOD", options=list(range(2024, 2009, -1)), index=0)
    n_hist = st.slider("HISTORICAL PERIODS", min_value=6, max_value=15, value=12)

    st.markdown("---")
    st.markdown("""
    <div style='font-size:0.72rem;color:#7b7fa8;line-height:1.7'>
        Flags anomalies using <b style='color:#c8cadc'>Tukey IQR fences</b>.<br>
        Current period vs preceding N years.<br><br>
        <b style='color:#b5e550'>Click Investigate</b> to launch the AI agent.
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
# Sparkline
# ---------------------------------------------------------------------------
def make_sparkline(check: CheckResult) -> go.Figure:
    by_year = check.context.get("by_year", {})
    curr = check.context.get("current_year")
    years = sorted(by_year.keys())
    values = [by_year[y] for y in years]
    labels = [str(y) for y in years]

    bar_colors = [
        "#e53935" if (y == curr and check.flagged)
        else "#4caf50" if y == curr
        else "#7a9cc4"
        for y in years
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=values,
        marker_color=bar_colors,
        marker_line_width=0,
        hovertemplate="%{x}: %{y:.2f}<extra></extra>",
    ))
    fig.add_hline(y=check.fence_high, line_dash="dot", line_color="#ff9f43", line_width=1.5)
    if check.fence_low > 0:
        fig.add_hline(y=check.fence_low, line_dash="dot", line_color="#54a0ff", line_width=1.5)
    fig.add_hrect(
        y0=check.fence_low, y1=check.fence_high,
        fillcolor="rgba(76,175,80,0.06)", line_width=0,
    )
    fig.update_layout(
        height=72,
        margin=dict(l=0, r=0, t=2, b=2),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        bargap=0.2,
    )
    return fig


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------
def build_excel(
    checks: list,
    investigations: dict,
    current_year: int,
    n_hist: int,
) -> bytes:
    wb = openpyxl.Workbook()

    # ── Styles ──────────────────────────────────────────────────────────────
    hdr_fill   = PatternFill("solid", fgColor="1A1D35")
    flag_fill  = PatternFill("solid", fgColor="FFEBEE")
    ok_fill    = PatternFill("solid", fgColor="E8F5E9")
    grey_fill  = PatternFill("solid", fgColor="F7F8FD")
    hdr_font   = Font(bold=True, color="FFFFFF", size=10)
    flag_font  = Font(bold=True, color="C62828", size=10)
    ok_font    = Font(bold=True, color="2E7D32", size=10)
    body_font  = Font(size=10)
    title_font = Font(bold=True, size=13, color="1A1D35")
    thin       = Side(style="thin", color="D8DDF0")
    border     = Border(left=thin, right=thin, top=thin, bottom=thin)
    center     = Alignment(horizontal="center", vertical="center")
    wrap       = Alignment(wrap_text=True, vertical="top")

    def set_col_widths(ws, widths):
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

    def hdr_row(ws, row, values):
        for c, v in enumerate(values, 1):
            cell = ws.cell(row=row, column=c, value=v)
            cell.font = hdr_font
            cell.fill = hdr_fill
            cell.alignment = center
            cell.border = border

    # ── Sheet 1: Summary ────────────────────────────────────────────────────
    ws1 = wb.active
    ws1.title = "DQ Summary"

    ws1["A1"] = "IMDB Data Quality Report"
    ws1["A1"].font = title_font
    ws1["A2"] = (
        f"Period: {current_year}  |  Baseline: {current_year - n_hist}–{current_year - 1}"
        f"  |  Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    ws1["A2"].font = Font(size=9, color="6B7094")
    ws1.row_dimensions[1].height = 22
    ws1.merge_cells("A1:G1")
    ws1.merge_cells("A2:G2")

    headers = ["Check", "Type", "Current Value", "Normal Range (Low)", "Normal Range (High)", "Status", "Direction"]
    hdr_row(ws1, 4, headers)

    type_labels = {"numerical": "Numerical", "null_rate": "Null Rate", "categorical": "Categorical"}
    for r, check in enumerate(checks, 5):
        ws1.row_dimensions[r].height = 18
        unit = f" {check.unit}" if check.unit else ""
        row_data = [
            check.name,
            type_labels.get(check.context.get("check_type", ""), ""),
            f"{check.current_val}{unit}",
            f"{check.fence_low}{unit}",
            f"{check.fence_high}{unit}",
            "FLAGGED" if check.flagged else "OK",
            check.flag_direction if check.flagged else "",
        ]
        fill = flag_fill if check.flagged else (grey_fill if r % 2 == 0 else PatternFill())
        for c, v in enumerate(row_data, 1):
            cell = ws1.cell(row=r, column=c, value=v)
            cell.font = flag_font if (check.flagged and c == 6) else (ok_font if c == 6 else body_font)
            cell.fill = fill
            cell.border = border
            cell.alignment = center if c > 1 else Alignment(vertical="center")

    set_col_widths(ws1, [38, 14, 14, 18, 18, 10, 10])

    # ── Sheet 2: Investigations ──────────────────────────────────────────────
    ws2 = wb.create_sheet("Investigations")
    ws2["A1"] = "AI Investigation Results"
    ws2["A1"].font = title_font
    ws2.merge_cells("A1:F1")
    ws2.row_dimensions[1].height = 22

    hdr_row(ws2, 3, ["Check", "Input Tokens", "Output Tokens", "Cost (USD)", "Completed", "Summary"])

    row_num = 4
    inv_key_map = {
        k.replace("num_", "").replace("null_", "").replace("cat_", "").replace("_inv", ""): v
        for k, v in investigations.items()
    }

    for check in checks:
        # Find the matching investigation by check name
        inv_key = next(
            (k for k in investigations if check.name in k and k.endswith("_inv")), None
        )
        if not inv_key:
            continue
        inv: Investigation = investigations[inv_key]

        ws2.row_dimensions[row_num].height = 15
        summary_clean = "\n".join(
            l for l in inv.summary.split("\n") if not l.startswith("VERIFY:")
        )
        row_data = [
            check.name,
            inv.input_tokens,
            inv.output_tokens,
            f"${inv.cost_usd:.4f}",
            "Yes" if inv.completed else "No",
            summary_clean,
        ]
        for c, v in enumerate(row_data, 1):
            cell = ws2.cell(row=row_num, column=c, value=v)
            cell.font = body_font
            cell.border = border
            cell.alignment = wrap if c == 6 else Alignment(vertical="top")
            if row_num % 2 == 0:
                cell.fill = grey_fill
        ws2.row_dimensions[row_num].height = max(
            60, min(15 * (summary_clean.count("\n") + 1), 200)
        )
        row_num += 1

        # SQL steps sub-rows
        for i, step in enumerate(inv.steps, 1):
            ws2.cell(row=row_num, column=1, value=f"  Step {i} SQL").font = Font(size=9, italic=True, color="6B7094")
            cell = ws2.cell(row=row_num, column=6, value=step.sql)
            cell.font = Font(name="Courier New", size=9, color="3A3F6E")
            cell.alignment = wrap
            ws2.row_dimensions[row_num].height = 30
            row_num += 1

    set_col_widths(ws2, [38, 13, 13, 12, 10, 70])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Page title
# ---------------------------------------------------------------------------
st.markdown(f"""
<div style='padding:12px 0 8px 0'>
    <div style='font-size:1.65rem;font-weight:800;color:#1a1d35'>Data Quality Monitor</div>
    <div style='font-size:0.8rem;color:#9399b8;margin-top:3px'>
        Period <b style='color:#1a1d35'>{current_year}</b> &nbsp;·&nbsp;
        Baseline {current_year - n_hist}–{current_year - 1} &nbsp;·&nbsp; IMDB dataset
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

    flagged   = [c for c in checks if c.flagged]
    ok_checks = [c for c in checks if not c.flagged]
    fail_rate = f"{len(flagged)/len(checks)*100:.0f}%" if checks else "0%"

    # Summary banner
    s1, s2, s3, s4 = st.columns(4)
    for col, number, label, cls in [
        (s1, len(checks),   "Checks Run",    "color-navy"),
        (s2, len(flagged),  "Flagged",       "color-red"),
        (s3, len(ok_checks),"Passed",        "color-green"),
        (s4, fail_rate,     "Failure Rate",  "color-red" if flagged else "color-green"),
    ]:
        col.markdown(f"""
        <div class="summary-card">
            <div class="summary-label">{label}</div>
            <div class="summary-number {cls}">{number}</div>
        </div>
        """, unsafe_allow_html=True)

    def send_to_playground(q: str):
        st.session_state.sql_query = q

    def render_check_row(check: CheckResult, section_key: str):
        key     = f"{section_key}_{check.name}"
        inv_key = key + "_inv"

        c_name, c_chart, c_val, c_range, c_status, c_action = st.columns(
            [2.4, 2.2, 0.9, 1.6, 0.85, 1.05]
        )

        name_cls = "check-name-flagged" if check.flagged else "check-name"
        c_name.markdown(f"<div class='{name_cls}'>{check.name}</div>", unsafe_allow_html=True)

        c_chart.plotly_chart(
            make_sparkline(check), use_container_width=True,
            config={"displayModeBar": False},
        )

        unit = f" {check.unit}" if check.unit else ""
        val_cls = "check-value-flag" if check.flagged else "check-value-ok"
        c_val.markdown(
            f"<div class='{val_cls}'>{check.current_val}{unit}</div>",
            unsafe_allow_html=True,
        )
        c_range.markdown(
            f"<div class='check-range'>"
            f"{check.fence_low}{unit} – {check.fence_high}{unit}</div>",
            unsafe_allow_html=True,
        )

        if check.flagged:
            pill_cls = "pill-high" if check.flag_direction == "HIGH" else "pill-low"
            c_status.markdown(
                f"<span class='pill {pill_cls}'>{check.flag_direction}</span>",
                unsafe_allow_html=True,
            )
            if c_action.button("▶ Investigate", key=key, type="primary", use_container_width=True):
                with st.spinner("AI investigating..."):
                    inv = investigate(check, get_con())
                    st.session_state.investigations[inv_key] = inv
        else:
            c_status.markdown(
                "<span class='pill pill-ok'>OK</span>",
                unsafe_allow_html=True,
            )

        # Investigation result
        if inv_key in st.session_state.investigations:
            inv = st.session_state.investigations[inv_key]
            with st.expander(f"Investigation: {check.name}", expanded=True):
                t1, t2, t3, t4 = st.columns(4)
                t1.metric("Input tokens",  f"{inv.input_tokens:,}")
                t2.metric("Output tokens", f"{inv.output_tokens:,}")
                t3.metric("Total tokens",  f"{inv.total_tokens:,}")
                t4.metric("Cost",          f"${inv.cost_usd:.4f}")
                st.markdown("---")

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
                            st.info("Sent to SQL Playground — click the tab above.")
                        st.code(step.result)
                    st.markdown("---")

                st.markdown("#### Summary")
                lines        = inv.summary.split("\n")
                summary_text = "\n".join(l for l in lines if not l.startswith("VERIFY:"))
                verify_lines = [l[len("VERIFY:"):].strip() for l in lines if l.startswith("VERIFY:")]

                if inv.completed:
                    st.success(summary_text)
                else:
                    st.warning(summary_text)

                if verify_lines:
                    st.markdown("**Verification queries:**")
                    for i, q in enumerate(verify_lines):
                        vc1, vc2 = st.columns([5, 1])
                        vc1.code(q, language="sql")
                        if vc2.button("▶ Run", key=f"{inv_key}_verify_{i}"):
                            send_to_playground(q)
                            st.info("Sent to SQL Playground — click the tab above.")

                # ── Follow-up chat ──────────────────────────────────────────
                st.markdown("---")
                st.markdown("#### Follow-up Questions")

                for fu_idx, fu in enumerate(inv.follow_ups):
                    with st.chat_message("user"):
                        st.markdown(fu.question)
                    with st.chat_message("assistant"):
                        if fu.steps:
                            for si, step in enumerate(fu.steps, 1):
                                with st.expander(f"Step {si}", expanded=False):
                                    if step.reasoning:
                                        st.info(step.reasoning)
                                    fsc1, fsc2 = st.columns([5, 1])
                                    fsc1.code(step.sql, language="sql")
                                    if fsc2.button("▶ Run", key=f"{inv_key}_fu{fu_idx}_s{si}"):
                                        send_to_playground(step.sql)
                                        st.info("Sent to SQL Playground — click the tab above.")
                                    st.code(step.result)
                        st.markdown(fu.response)
                        st.caption(
                            f"Tokens: {fu.input_tokens + fu.output_tokens:,}"
                            f"  ·  Cost: ${fu.cost_usd:.4f}"
                        )

                with st.form(key=f"{inv_key}_fu_form", clear_on_submit=True):
                    fu_col1, fu_col2 = st.columns([6, 1])
                    fu_question = fu_col1.text_input(
                        "follow-up",
                        placeholder="Ask a follow-up question, e.g. Which specific titles drove the change?",
                        label_visibility="collapsed",
                    )
                    fu_submit = fu_col2.form_submit_button("Send →", type="primary")

                if fu_submit and fu_question.strip():
                    with st.spinner("AI investigating follow-up..."):
                        continue_investigation(inv, fu_question.strip(), get_con())
                    st.rerun()

        st.markdown("<hr class='row-sep'>", unsafe_allow_html=True)

    def render_section(title: str, section_checks: list[CheckResult], key_prefix: str, section_class: str):
        if not section_checks:
            return
        with st.container():
            st.markdown(f"<div class='section-mark {section_class}'></div>", unsafe_allow_html=True)
            st.markdown(
                f"<div class='section-header section-header-{key_prefix}'>{title}</div>",
                unsafe_allow_html=True,
            )
            h = st.columns([2.4, 2.2, 0.9, 1.6, 0.85, 1.05])
            for col, label in zip(h, ["Check", "12-period trend", "Current", "Normal range", "Status", "Action"]):
                col.markdown(f"<div class='col-header'>{label}</div>", unsafe_allow_html=True)
            for check in sorted(section_checks, key=lambda c: (not c.flagged, c.name)):
                render_check_row(check, key_prefix)

    numerical  = [c for c in checks if c.context.get("check_type") == "numerical"]
    nulls      = [c for c in checks if c.context.get("check_type") == "null_rate"]
    categorical= [c for c in checks if c.context.get("check_type") == "categorical"]

    render_section("Numerical Variables",      numerical,   "num",  "section-mark-num")
    render_section("Null Rate Monitoring",     nulls,       "null", "section-mark-null")
    render_section("Categorical Distribution", categorical, "cat",  "section-mark-cat")

    # Download report — bottom of dashboard, toned down
    st.markdown("<div style='margin:24px 0 4px 0'></div>", unsafe_allow_html=True)
    _, dl_col, _ = st.columns([3, 2, 3])
    filename = f"dq_report_{current_year}_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    dl_col.download_button(
        label="⬇  Download Report (Excel)",
        data=build_excel(checks, st.session_state.investigations, current_year, n_hist),
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


# ===========================================================================
# TAB 2 — SQL PLAYGROUND
# ===========================================================================
with tab_sql:
    st.markdown("<div class='section-header'>SQL Playground</div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:0.82rem;color:#9399b8;margin-bottom:16px'>"
        "Query the IMDB data directly. Available views: "
        "<code style='background:#e8ecf8;padding:2px 6px;border-radius:4px;color:#3a3f6e'>basics</code> &nbsp;"
        "<code style='background:#e8ecf8;padding:2px 6px;border-radius:4px;color:#3a3f6e'>ratings</code>"
        "</div>",
        unsafe_allow_html=True,
    )

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
            "SELECT b.startYear, COUNT(*) AS total,\n"
            "       SUM(CASE WHEN b.runtimeMinutes IS NULL THEN 1 ELSE 0 END) AS nulls,\n"
            "       ROUND(100.0 * SUM(CASE WHEN b.runtimeMinutes IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS null_pct\n"
            "FROM basics b JOIN ratings r USING (tconst)\n"
            "WHERE b.titleType = 'movie' AND b.startYear BETWEEN 2012 AND 2024\n"
            "GROUP BY b.startYear ORDER BY b.startYear"
        ),
        "Genre distribution for a year": (
            "SELECT b.genres, COUNT(*) AS cnt,\n"
            "       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct\n"
            "FROM basics b JOIN ratings r USING (tconst)\n"
            "WHERE b.startYear = 2024 AND b.genres IS NOT NULL\n"
            "GROUP BY b.genres ORDER BY cnt DESC LIMIT 20"
        ),
    }

    with st.expander("Example queries"):
        for label, sql in examples.items():
            ec1, ec2 = st.columns([5, 1])
            ec1.markdown(
                f"<div style='font-size:0.85rem;font-weight:600;color:#3a3f6e;padding:6px 0'>{label}</div>",
                unsafe_allow_html=True,
            )
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
        try:
            cursor = get_con().execute(query)
            rows   = cursor.fetchall()
            cols_n = [desc[0] for desc in cursor.description]
            if not rows:
                st.info("Query returned no rows.")
            else:
                data = {cols_n[i]: [r[i] for r in rows] for i in range(len(cols_n))}
                st.markdown(
                    f"<div style='font-size:0.78rem;color:#4caf50;margin:8px 0'>"
                    f"✓ {len(rows)} row(s) returned</div>",
                    unsafe_allow_html=True,
                )
                st.dataframe(data, use_container_width=True)
        except Exception as e:
            st.error(f"SQL Error: {e}")
