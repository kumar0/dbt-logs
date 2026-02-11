import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from streamlit_autorefresh import st_autorefresh
from data_provider import fetch_dbt_run_logs, fetch_glue_job_metrics, FetchMode, last_dbt_fetch_info, last_glue_fetch_info
from helpers import get_model_records, classify_model_status, get_execution_summary
from tabs import tab_live, tab_completed, tab_performance, tab_timeline, tab_glue

st.set_page_config(page_title="Data Flow Monitor", page_icon="🔄", layout="wide")

# --- Initialise session state ---
if "last_fetch_ts" not in st.session_state:
    st.session_state.last_fetch_ts = None
if "df_raw" not in st.session_state:
    st.session_state.df_raw = None
if "glue_raw" not in st.session_state:
    st.session_state.glue_raw = None
if "fetch_requested" not in st.session_state:
    st.session_state.fetch_requested = True      # first load triggers fetch
if "run_just_completed" not in st.session_state:
    st.session_state.run_just_completed = False

# --- Custom CSS ---
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%);
        border-radius: 10px; padding: 12px 16px; text-align: center;
        border: 1px solid #3d3d5c; margin-bottom: 6px;
    }
    .metric-card h2 { color: #e0e0e0; font-size: 12px; margin: 0; text-transform: uppercase; letter-spacing: 1px; }
    .metric-card h1 { color: #ffffff; font-size: 26px; margin: 3px 0 0 0; }
    .status-ok { color: #4ade80; }
    .status-error { color: #f87171; }
    .status-skip { color: #fbbf24; }
    .status-running { color: #60a5fa; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e1e2e; border-radius: 8px 8px 0 0;
        padding: 10px 20px; color: #a0a0b0; border: 1px solid #3d3d5c;
    }
    .stTabs [aria-selected="true"] { background-color: #2d2d44; color: #ffffff; }
    iframe[title="streamlit_autorefresh.st_autorefresh"],
    .element-container:has(iframe[title="streamlit_autorefresh.st_autorefresh"]),
    [data-testid="stComponentFrame"]:has(iframe[title*="autorefresh"]) {
        height: 0 !important; min-height: 0 !important; max-height: 0 !important;
        overflow: hidden !important; margin: 0 !important; padding: 0 !important;
        border: none !important;
    }
    div[data-baseweb="select"] input { pointer-events: none !important; }
</style>
""", unsafe_allow_html=True)

# --- Default time window: today, from (now - 1h) to now ---
_now = datetime.now()
_default_from_time = (_now - timedelta(hours=1)).time().replace(second=0, microsecond=0)
_default_to_time = _now.time().replace(second=0, microsecond=0)
_default_date = _now.date()

# --- Header ---
st.markdown("## 🔄 Data Flow Monitor")
st.caption("Real-time monitoring dashboard for dbt model executions")

# --- Date Range & Controls ---
ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4, ctrl_col5 = st.columns([2.5, 1, 1, 1.5, 1])

with ctrl_col1:
    date_range = st.date_input(
        "Date Range",
        value=(_default_date, _default_date),
        key="date_range",
    )
with ctrl_col2:
    from_time = st.time_input(
        "From Time",
        value=_default_from_time,
        key="from_time",
    )
with ctrl_col3:
    to_time = st.time_input(
        "To Time",
        value=_default_to_time,
        key="to_time",
    )
with ctrl_col4:
    auto_refresh = st.selectbox(
        "Auto Refresh",
        ["Off", "10s", "30s", "1m", "5m", "10m"],
        index=0,
        key="auto_refresh",
    )
with ctrl_col5:
    st.markdown('<div style="margin-top: 25px;"></div>', unsafe_allow_html=True)
    if st.button("🔍 Fetch Data", use_container_width=True, type="primary"):
        st.session_state.fetch_requested = True
        st.rerun()

# Auto-refresh (JS-based timer via sidebar to avoid layout shift)
refresh_seconds_map = {"Off": 0, "10s": 10, "30s": 30, "1m": 60, "5m": 300, "10m": 600}
refresh_interval_s = refresh_seconds_map.get(auto_refresh, 0)
if refresh_interval_s > 0:
    with st.sidebar:
        st_autorefresh(interval=refresh_interval_s * 1000, key="auto_refresh_timer")

# Resolve date range (handle partial selection)
if isinstance(date_range, tuple) and len(date_range) == 2:
    date_from, date_to = date_range
else:
    date_from = date_to = _default_date

# --- Fetch data only when explicitly requested (button or first load or auto-refresh) ---
_should_fetch = st.session_state.fetch_requested or (refresh_interval_s > 0 and st.session_state.df_raw is not None)

if _should_fetch:
    # Determine fetch mode
    if st.session_state.df_raw is None or st.session_state.fetch_requested:
        fetch_mode: FetchMode = "full"
        since_ts = None
    else:
        fetch_mode = "delta"
        since_ts = st.session_state.last_fetch_ts

    _use_realtime = st.session_state.run_just_completed
    _start_iso = pd.Timestamp(datetime.combine(date_from, from_time)).isoformat()
    _end_iso = pd.Timestamp(datetime.combine(date_to, to_time)).isoformat()

    try:
        new_dbt = fetch_dbt_run_logs(
            start_time=_start_iso,
            end_time=_end_iso,
            fetch_mode=fetch_mode,
            since=since_ts,
            prefer_realtime=_use_realtime,
        )
    except Exception as e:
        new_dbt = pd.DataFrame()
        st.error(f"Failed to fetch dbt logs: {e}")

    try:
        new_glue = fetch_glue_job_metrics(
            start_time=_start_iso,
            end_time=_end_iso,
            fetch_mode=fetch_mode,
            since=since_ts,
        )
    except Exception as e:
        new_glue = pd.DataFrame()
        st.error(f"Failed to fetch Glue metrics: {e}")

    if fetch_mode == "full":
        st.session_state.df_raw = new_dbt
        st.session_state.glue_raw = new_glue
    else:
        # Merge delta into existing data
        if not new_dbt.empty:
            st.session_state.df_raw = pd.concat(
                [st.session_state.df_raw, new_dbt]
            ).drop_duplicates().reset_index(drop=True)

            if "record_type" in new_dbt.columns and new_dbt["record_type"].isin(
                ["EXECUTION_DURATION", "EXECUTION_STATUS"]
            ).any():
                st.session_state.fetch_requested = True
                st.session_state.run_just_completed = True

        if not new_glue.empty:
            st.session_state.glue_raw = pd.concat(
                [st.session_state.glue_raw, new_glue]
            ).drop_duplicates().reset_index(drop=True)

    st.session_state.last_fetch_ts = pd.Timestamp.now().isoformat()
    st.session_state.fetch_requested = False
    st.session_state.run_just_completed = False

df_raw = st.session_state.df_raw
glue_raw = st.session_state.glue_raw

# --- Guard: if no data yet, prompt user to fetch ---
_dbt_empty = df_raw is None or df_raw.empty
_glue_empty = glue_raw is None or glue_raw.empty

if _dbt_empty and _glue_empty:
    st.info("Set your date/time range above and click **Fetch Data** to load from CloudWatch.")
    st.stop()

# Ensure we have valid DataFrames even if one source is empty
if _dbt_empty:
    df_raw = pd.DataFrame(columns=["invocation_id", "timestamp", "entity", "model_name",
                                    "start_time", "end_time", "duration", "status",
                                    "message", "thread_info"])
if _glue_empty:
    glue_raw = pd.DataFrame(columns=["timestamp"])

# --- Filter data ---
filter_start = pd.Timestamp(datetime.combine(date_from, from_time), tz="UTC")
filter_end = pd.Timestamp(datetime.combine(date_to, to_time), tz="UTC")

df = df_raw[
    (df_raw["start_time"] >= filter_start) | (df_raw["start_time"].isna())
].copy()
df = df[
    (df["start_time"] <= filter_end) | (df["start_time"].isna())
].copy()

glue_df_filtered = glue_raw[
    (glue_raw["timestamp"] >= filter_start) & (glue_raw["timestamp"] <= filter_end)
].copy()

# --- Process ---
model_df = get_model_records(df)
test_df = get_model_records(df, include_tests=True)
if "resource_type" in test_df.columns:
    test_only_df = test_df[test_df["resource_type"] == "test"].copy()
else:
    test_only_df = pd.DataFrame()

exec_summary = get_execution_summary(df)

if "record_type" in df.columns:
    _done_mask = df["record_type"].isin(["EXECUTION_DURATION", "EXECUTION_STATUS"])
else:
    _done_mask = df["status"].isin(["EXECUTION_DURATION", "EXECUTION_STATUS"])
completed_invocations = set(df.loc[_done_mask, "invocation_id"].unique())

classified = classify_model_status(model_df, completed_invocations)
classified_tests = classify_model_status(test_only_df, completed_invocations) if not test_only_df.empty else pd.DataFrame()

# --- Data range banner ---
actual_min = df["start_time"].min()
actual_max = df["end_time"].max()
range_from_str = actual_min.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(actual_min) else "N/A"
range_to_str = actual_max.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(actual_max) else "N/A"

# Determine last fetch mode label
_last_mode = "full" if st.session_state.last_fetch_ts else "—"

st.markdown(
    f'<div style="text-align:center; color:#a0a0b0; font-size:13px; margin-bottom:8px;">'
    f'📅 Showing stats from <b style="color:#60a5fa;">{range_from_str}</b> to <b style="color:#60a5fa;">{range_to_str}</b>'
    f'</div>',
    unsafe_allow_html=True,
)

# --- Top-level KPIs ---
if classified.empty or "final_status" not in classified.columns:
    total_models = ok_count = error_count = skipped_count = running_count = unknown_count = unique_entities = 0
else:
    total_models = len(classified)
    ok_count = len(classified[classified["final_status"].isin(["OK", "pass"])])
    error_count = len(classified[classified["final_status"] == "error"])
    skipped_count = len(classified[classified["final_status"] == "skipped"])
    running_count = len(classified[classified["final_status"] == "running"])
    unknown_count = len(classified[classified["final_status"] == "unknown"])
    unique_entities = classified["entity"].nunique()

# Test summary
if not classified_tests.empty and "final_status" in classified_tests.columns:
    total_tests = len(classified_tests)
    tests_passed = len(classified_tests[classified_tests["final_status"].isin(["OK", "pass"])])
    tests_failed = len(classified_tests[classified_tests["final_status"] == "error"])
    tests_label = f"{tests_passed}✅"
    if tests_failed > 0:
        tests_label += f" {tests_failed}❌"
    tests_unknown = total_tests - tests_passed - tests_failed
    if tests_unknown > 0:
        tests_label += f" {tests_unknown}❓"
else:
    total_tests = 0
    tests_label = "0"

col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
with col1:
    st.markdown(f'<div class="metric-card"><h2>Total Models</h2><h1>{total_models}</h1></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="metric-card"><h2>Succeeded</h2><h1 class="status-ok">{ok_count}</h1></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="metric-card"><h2>Failed</h2><h1 class="status-error">{error_count}</h1></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div class="metric-card"><h2>Skipped</h2><h1 class="status-skip">{skipped_count}</h1></div>', unsafe_allow_html=True)
with col5:
    st.markdown(f'<div class="metric-card"><h2>In Progress</h2><h1 class="status-running">{running_count}</h1></div>', unsafe_allow_html=True)
with col6:
    st.markdown(f'<div class="metric-card"><h2>Tests ({total_tests})</h2><h1 style="color:#a78bfa;">{tests_label}</h1></div>', unsafe_allow_html=True)
with col7:
    st.markdown(f'<div class="metric-card"><h2>Entities</h2><h1>{unique_entities}</h1></div>', unsafe_allow_html=True)

st.divider()

# --- Tabs ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔴 Live / In Progress",
    "✅ Completed Runs",
    "📊 Performance Analytics",
    "🗂️ Execution Timeline",
    "⚡ Glue Metrics",
])

with tab1:
    tab_live.render(classified)
with tab2:
    tab_completed.render(classified, exec_summary, raw_df=df)
with tab3:
    tab_performance.render(classified)
with tab4:
    tab_timeline.render(classified)
with tab5:
    tab_glue.render(glue_df_filtered)

# --- Footer ---
st.divider()
refresh_label = f" · Auto-refresh: {auto_refresh}" if auto_refresh != "Off" else ""
_src_detail = last_dbt_fetch_info["detail"]
_src_lg = last_dbt_fetch_info.get("log_group", "")
dbt_source_label = f'☁️ CloudWatch ({_src_lg}) — {_src_detail}' if _src_lg else f'☁️ CloudWatch — {_src_detail}'
_glue_detail = last_glue_fetch_info["detail"]
glue_source_label = f'☁️ CloudWatch — {_glue_detail}'

st.caption(f"Dashboard loaded at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · Filtered: {range_from_str} → {range_to_str}{refresh_label}")
st.caption(f"dbt logs: {dbt_source_label} · Glue metrics: {glue_source_label}")
