import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone

from streamlit_autorefresh import st_autorefresh
from sfn_data_provider import list_matching_state_machines, fetch_executions
import plotly.express as px

STATUS_COLORS = {
    "SUCCEEDED": "green",
    "FAILED": "red",
    "TIMED_OUT": "orange",
    "RUNNING": "blue",
    "ABORTED": "grey",
}


def status_color(status: str) -> str:
    """Map an execution status to its display color."""
    return STATUS_COLORS.get(status, "grey")


def render() -> None:
    """Render the Step Functions monitoring section."""

    # --- Default time window: local now - 60min to now ---
    _local_tz = datetime.now().astimezone().tzinfo
    _now_local = datetime.now(_local_tz)
    _default_from_time = (_now_local - timedelta(minutes=60)).time().replace(second=0, microsecond=0)
    _default_to_time = _now_local.time().replace(second=0, microsecond=0)
    _default_date = _now_local.date()

    # Effective end time — updated by auto-refresh without touching widget state
    if "sfn_effective_to_time" not in st.session_state:
        st.session_state.sfn_effective_to_time = _default_to_time
    if "sfn_effective_to_date" not in st.session_state:
        st.session_state.sfn_effective_to_date = _default_date

    # --- Session state initialisation ---
    if "sfn_state_machines" not in st.session_state:
        st.session_state.sfn_state_machines = None
    if "sfn_executions" not in st.session_state:
        st.session_state.sfn_executions = None
    if "sfn_last_fetch_ts" not in st.session_state:
        st.session_state.sfn_last_fetch_ts = None
    if "sfn_fetch_requested" not in st.session_state:
        st.session_state.sfn_fetch_requested = False

    # --- Header ---
    st.markdown("### Step Functions Monitor")
    st.caption("Monitoring dashboard for raw-to-base Step Functions executions")

    # --- Discover state machines on load ---
    if st.session_state.sfn_state_machines is None:
        try:
            st.session_state.sfn_state_machines = list_matching_state_machines()
        except Exception as e:
            st.error(f"Failed to discover state machines: {e}")
            st.session_state.sfn_state_machines = pd.DataFrame(
                columns=["state_machine_arn", "name", "environment", "creation_date"]
            )

    sm_df = st.session_state.sfn_state_machines

    if sm_df is None or sm_df.empty:
        st.info("No state machines matching pattern `raw-to-base-*-eu-west-1` were found.")
        return

    # Resolve refresh interval early so widgets can use it
    refresh_seconds_map = {"Off": 0, "30s": 30, "1m": 60, "5m": 300}
    _current_auto_refresh = st.session_state.get("sfn_auto_refresh", "Off")
    refresh_interval_s = refresh_seconds_map.get(_current_auto_refresh, 0)

    # --- Date Range & Controls ---
    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4, ctrl_col5 = st.columns([2.5, 1, 1, 1.5, 1])

    with ctrl_col1:
        date_range = st.date_input(
            "Date Range",
            value=(_default_date, _default_date),
            key="sfn_date_range",
        )
    with ctrl_col2:
        from_time = st.time_input(
            "From Time",
            value=_default_from_time,
            key="sfn_from_time",
        )
    with ctrl_col3:
        if refresh_interval_s > 0:
            st.markdown(
                '<div style="margin-top:4px"><label style="font-size:14px;color:#a0a0b0">To Time</label></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="padding:6px 0;font-size:15px">🔄 {st.session_state.sfn_effective_to_time.strftime("%H:%M")}</div>',
                unsafe_allow_html=True,
            )
            to_time = st.session_state.sfn_effective_to_time
        else:
            to_time = st.time_input(
                "To Time",
                value=_default_to_time,
                key="sfn_to_time",
            )
    with ctrl_col4:
        auto_refresh = st.selectbox(
            "Auto Refresh",
            ["Off", "30s", "1m", "5m"],
            index=0,
            key="sfn_auto_refresh",
        )
    with ctrl_col5:
        st.markdown('<div style="margin-top: 25px;"></div>', unsafe_allow_html=True)
        if st.button("🔍 Fetch Data", use_container_width=True, type="primary", key="sfn_fetch_btn"):
            st.session_state.sfn_fetch_requested = True
            st.rerun()

    # Auto-refresh (JS-based timer via sidebar to avoid layout shift)
    refresh_interval_s = refresh_seconds_map.get(auto_refresh, 0)
    if refresh_interval_s > 0:
        with st.sidebar:
            st_autorefresh(interval=refresh_interval_s * 1000, key="sfn_auto_refresh_timer")

    # Resolve date range (handle partial selection)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        date_from, date_to = date_range
    else:
        date_from = date_to = _default_date

    # --- Fetch data when requested (button or auto-refresh) ---
    _should_fetch = st.session_state.sfn_fetch_requested or (
        refresh_interval_s > 0 and st.session_state.sfn_executions is not None
    )

    if _should_fetch:
        _local_tz = datetime.now().astimezone().tzinfo
        _now_local = datetime.now(_local_tz)
        _start_local = datetime.combine(date_from, from_time).replace(tzinfo=_local_tz)

        # Update end boundary to current time on auto-refresh cycles
        if refresh_interval_s > 0 and not st.session_state.sfn_fetch_requested:
            _end_local = _now_local
            st.session_state.sfn_effective_to_time = _now_local.time().replace(second=0, microsecond=0)
            st.session_state.sfn_effective_to_date = _now_local.date()
            date_to = st.session_state.sfn_effective_to_date
        else:
            _end_local = datetime.combine(date_to, to_time).replace(tzinfo=_local_tz)

        _start_utc = _start_local.astimezone(timezone.utc)
        _end_utc = _end_local.astimezone(timezone.utc)
        _start_iso = _start_utc.isoformat()
        _end_iso = _end_utc.isoformat()

        if _start_iso >= _end_iso:
            st.warning("⚠️ 'From' time must be before 'To' time. Please adjust the time range.")
            st.session_state.sfn_fetch_requested = False
            return

        try:
            arns = sm_df["state_machine_arn"].tolist()
            st.session_state.sfn_executions = fetch_executions(arns, _start_iso, _end_iso)
            st.session_state.sfn_last_fetch_ts = pd.Timestamp.now(tz="UTC").isoformat()
        except Exception as e:
            st.error(f"Failed to fetch executions: {e}")

        st.session_state.sfn_fetch_requested = False

    exec_df = st.session_state.sfn_executions

    # --- Guard: if no data yet, prompt user to fetch ---
    if exec_df is None or exec_df.empty:
        st.info("Set your date/time range above and click **Fetch Data** to load Step Functions executions.")
        return

    # --- Environment filter ---
    all_envs = sorted(exec_df["environment"].unique().tolist())
    selected_envs = st.multiselect(
        "Filter by Environment",
        options=all_envs,
        default=all_envs,
        key="sfn_env_filter",
    )

    # Apply environment filter
    if selected_envs:
        filtered_df = exec_df[exec_df["environment"].isin(selected_envs)].copy()
    else:
        filtered_df = exec_df.copy()

    # --- KPI Cards: Execution Status Summary ---
    total_count = len(filtered_df)
    running_count = len(filtered_df[filtered_df["status"] == "RUNNING"])
    succeeded_count = len(filtered_df[filtered_df["status"] == "SUCCEEDED"])
    failed_count = len(filtered_df[filtered_df["status"] == "FAILED"])
    timed_out_count = len(filtered_df[filtered_df["status"] == "TIMED_OUT"])
    aborted_count = len(filtered_df[filtered_df["status"] == "ABORTED"])

    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
    with kpi1:
        st.markdown(f'<div class="metric-card"><h2>Total</h2><h1>{total_count}</h1></div>', unsafe_allow_html=True)
    with kpi2:
        st.markdown(f'<div class="metric-card"><h2>Running</h2><h1 class="status-running">{running_count}</h1></div>', unsafe_allow_html=True)
    with kpi3:
        st.markdown(f'<div class="metric-card"><h2>Succeeded</h2><h1 class="status-ok">{succeeded_count}</h1></div>', unsafe_allow_html=True)
    with kpi4:
        st.markdown(f'<div class="metric-card"><h2>Failed</h2><h1 class="status-error">{failed_count}</h1></div>', unsafe_allow_html=True)
    with kpi5:
        st.markdown(f'<div class="metric-card"><h2>Timed Out</h2><h1 class="status-skip">{timed_out_count}</h1></div>', unsafe_allow_html=True)
    with kpi6:
        st.markdown(f'<div class="metric-card"><h2>Aborted</h2><h1 style="color:#9ca3af;">{aborted_count}</h1></div>', unsafe_allow_html=True)

    st.divider()

    # --- Error Analysis ---
    st.subheader("Error Analysis")

    error_df = filtered_df[filtered_df["status"].isin(["FAILED", "TIMED_OUT"])].copy()

    if error_df.empty:
        st.info("All executions succeeded — no errors found.")
    else:
        # Error frequency summary grouped by error_name
        st.markdown("**Error Frequency**")
        error_freq = (
            error_df.groupby("error_name", dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
        st.dataframe(error_freq, use_container_width=True, hide_index=True)

        # Detailed error table
        st.markdown("**Failed & Timed-Out Executions**")
        error_table = error_df[
            ["environment", "execution_name", "start_time", "stop_time", "error_name", "error_cause"]
        ].sort_values("start_time", ascending=False)
        st.dataframe(error_table, use_container_width=True, hide_index=True)

    st.divider()

    # --- Execution Duration ---
    st.subheader("Execution Duration")

    completed_df = filtered_df[filtered_df["duration_seconds"].notna()].copy()

    if completed_df.empty:
        st.info("No completed executions to display duration metrics.")
    else:
        # Scatter chart: duration over time by environment
        fig = px.scatter(
            completed_df,
            x="start_time",
            y="duration_seconds",
            color="environment",
            labels={
                "start_time": "Start Time",
                "duration_seconds": "Duration (seconds)",
                "environment": "Environment",
            },
            title="Execution Duration Over Time",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Summary statistics per environment
        st.markdown("**Duration Statistics by Environment**")
        duration_stats = (
            completed_df.groupby("environment")["duration_seconds"]
            .agg(["min", "max", "mean", "median"])
            .rename(columns={
                "min": "Min (s)",
                "max": "Max (s)",
                "mean": "Average (s)",
                "median": "Median (s)",
            })
            .reset_index()
        )
        st.dataframe(duration_stats, use_container_width=True, hide_index=True)

    st.divider()

    # --- Execution Status Distribution ---
    st.subheader("Execution Status Distribution")

    status_counts = (
        filtered_df.groupby(["environment", "status"])
        .size()
        .reset_index(name="count")
    )

    if status_counts.empty:
        st.info("No execution data to display status distribution.")
    else:
        unique_envs = filtered_df["environment"].nunique()
        # Consistent color mapping for statuses
        color_map = {s: c for s, c in STATUS_COLORS.items() if s in status_counts["status"].values}

        if unique_envs <= 1:
            # Single environment — pie chart
            agg = status_counts.groupby("status")["count"].sum().reset_index()
            fig = px.pie(
                agg,
                names="status",
                values="count",
                color="status",
                color_discrete_map=color_map,
                title="Status Distribution",
            )
        else:
            # Multiple environments — stacked bar chart
            fig = px.bar(
                status_counts,
                x="environment",
                y="count",
                color="status",
                color_discrete_map=color_map,
                title="Status Distribution by Environment",
                labels={"count": "Executions", "environment": "Environment", "status": "Status"},
                barmode="stack",
            )

        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # --- Execution History Table ---
    st.subheader("Execution History")

    history_df = filtered_df[
        ["environment", "execution_name", "status", "start_time", "stop_time", "duration_seconds"]
    ].sort_values("start_time", ascending=False)

    if history_df.empty:
        st.info("No executions to display.")
    else:
        # Build styled HTML for color-coded status column
        def _color_status(val: str) -> str:
            color = status_color(val)
            return f"color: {color}; font-weight: bold"

        styled = history_df.style.map(_color_status, subset=["status"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
