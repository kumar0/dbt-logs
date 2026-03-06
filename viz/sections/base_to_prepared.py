import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone

from streamlit_autorefresh import st_autorefresh
from data_provider import fetch_dbt_run_logs, fetch_glue_job_metrics, FetchMode, last_dbt_fetch_info, last_glue_fetch_info
from helpers import get_model_records, classify_model_status, get_execution_summary
from tabs import tab_live, tab_completed, tab_performance, tab_timeline, tab_glue


def render() -> None:
    """Render the full Base to Prepared dashboard section."""

    # --- Default time window: local now - 15min to now ---
    _local_tz = datetime.now().astimezone().tzinfo
    _now_local = datetime.now(_local_tz)
    _default_from_time = (_now_local - timedelta(minutes=15)).time().replace(second=0, microsecond=0)
    _default_to_time = _now_local.time().replace(second=0, microsecond=0)
    _default_date = _now_local.date()

    # Effective end time — updated by auto-refresh without touching widget state
    if "effective_to_time" not in st.session_state:
        st.session_state.effective_to_time = _default_to_time
    if "effective_to_date" not in st.session_state:
        st.session_state.effective_to_date = _default_date

    # --- Header ---
    st.markdown("## 🔄 Data Flow Monitor")
    st.caption("Real-time monitoring dashboard for dbt view executions")

    # Resolve refresh interval early so widgets can use it
    refresh_seconds_map = {"Off": 0, "10s": 10, "30s": 30, "1m": 60, "5m": 300, "10m": 600}
    _current_auto_refresh = st.session_state.get("auto_refresh", "Off")
    refresh_interval_s = refresh_seconds_map.get(_current_auto_refresh, 0)

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
        if refresh_interval_s > 0:
            st.markdown('<div style="margin-top:4px"><label style="font-size:14px;color:#a0a0b0">To Time</label></div>', unsafe_allow_html=True)
            st.markdown(f'<div style="padding:6px 0;font-size:15px">🔄 {st.session_state.effective_to_time.strftime("%H:%M")}</div>', unsafe_allow_html=True)
            to_time = st.session_state.effective_to_time
        else:
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
        _local_tz = datetime.now().astimezone().tzinfo
        _now_local = datetime.now(_local_tz)
        _start_local = datetime.combine(date_from, from_time).replace(tzinfo=_local_tz)
        if refresh_interval_s > 0 and fetch_mode == "delta":
            _end_local = _now_local
            st.session_state.effective_to_time = _now_local.time().replace(second=0, microsecond=0)
            st.session_state.effective_to_date = _now_local.date()
            date_to = st.session_state.effective_to_date
        else:
            _end_local = datetime.combine(date_to, to_time).replace(tzinfo=_local_tz)
        _start_utc = _start_local.astimezone(timezone.utc)
        _end_utc = _end_local.astimezone(timezone.utc)
        _start_iso = _start_utc.isoformat()
        _end_iso = _end_utc.isoformat()

        if _start_iso >= _end_iso:
            st.warning("⚠️ 'From' time must be before 'To' time. Please adjust the time range.")
            st.session_state.fetch_requested = False
            st.stop()

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

        # Fetch Glue metrics only when explicitly enabled
        if fetch_mode == "full" and st.session_state.glue_metrics_enabled:
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
        else:
            new_glue = pd.DataFrame()

        if fetch_mode == "full":
            st.session_state.df_raw = new_dbt
            if not new_glue.empty:
                st.session_state.glue_raw = new_glue
        else:
            if not new_dbt.empty:
                merged = pd.concat(
                    [st.session_state.df_raw, new_dbt]
                ).drop_duplicates().reset_index(drop=True)

                _now_utc = pd.Timestamp.now(tz="UTC")
                if "start_time" in merged.columns:
                    _oldest = merged["start_time"].dropna().min()
                    _span_mins = (_now_utc - _oldest).total_seconds() / 60 if pd.notna(_oldest) else 0
                    if _span_mins > 30:
                        _cutoff = _now_utc - pd.Timedelta(minutes=15)
                        merged = merged[
                            (merged["start_time"] >= _cutoff) | merged["start_time"].isna()
                        ].reset_index(drop=True)

                st.session_state.df_raw = merged

                if "record_type" in new_dbt.columns and new_dbt["record_type"].isin(
                    ["EXECUTION_DURATION", "EXECUTION_STATUS"]
                ).any():
                    st.session_state.run_just_completed = True

        st.session_state.last_fetch_ts = pd.Timestamp.now(tz="UTC").isoformat()
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
    _local_tz = datetime.now().astimezone().tzinfo
    filter_start = datetime.combine(date_from, from_time).replace(tzinfo=_local_tz).astimezone(timezone.utc)
    filter_start = pd.Timestamp(filter_start)
    filter_end = datetime.combine(date_to, to_time).replace(tzinfo=_local_tz).astimezone(timezone.utc)
    filter_end = pd.Timestamp(filter_end)

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
        st.markdown(f'<div class="metric-card"><h2>Entities</h2><h1>{unique_entities}</h1></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="metric-card"><h2>Total Views</h2><h1>{total_models}</h1></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="metric-card"><h2>Succeeded</h2><h1 class="status-ok">{ok_count}</h1></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="metric-card"><h2>Failed</h2><h1 class="status-error">{error_count}</h1></div>', unsafe_allow_html=True)
    with col5:
        st.markdown(f'<div class="metric-card"><h2>Skipped</h2><h1 class="status-skip">{skipped_count}</h1></div>', unsafe_allow_html=True)
    with col6:
        st.markdown(f'<div class="metric-card"><h2>In Progress</h2><h1 class="status-running">{running_count}</h1></div>', unsafe_allow_html=True)
    with col7:
        st.markdown(f'<div class="metric-card"><h2>Tests ({total_tests})</h2><h1 style="color:#a78bfa;">{tests_label}</h1></div>', unsafe_allow_html=True)

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
        tab_glue.render(glue_df_filtered, enabled=st.session_state.glue_metrics_enabled)

    # --- Footer ---
    st.divider()
    refresh_label = f" · Auto-refresh: {auto_refresh}" if auto_refresh != "Off" else ""
    _src_detail = last_dbt_fetch_info["detail"]
    _src_lg = last_dbt_fetch_info.get("log_group", "")
    dbt_source_label = f'☁️ CloudWatch ({_src_lg}) — {_src_detail}' if _src_lg else f'☁️ CloudWatch — {_src_detail}'
    _glue_detail = last_glue_fetch_info["detail"]
    glue_source_label = f'☁️ CloudWatch — {_glue_detail}'

    st.caption(f"Dashboard loaded at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC · Filtered: {range_from_str} → {range_to_str}{refresh_label}")
    st.caption(f"dbt logs: {dbt_source_label} · Glue metrics: {glue_source_label}")
