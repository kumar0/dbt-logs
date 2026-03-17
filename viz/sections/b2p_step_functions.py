"""Step Functions sub-tab for the Base to Prepared section.

Monitors base-to-prepared Step Function executions with per-BDE performance
analytics, including KPIs, error analysis, BDE summary, drill-down, and live
execution monitoring.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from sfn_data_provider import list_matching_state_machines, fetch_executions
from bde_parser import extract_bde_name
import plotly.express as px

B2P_SFN_PATTERN = "raw-to-base-*-eu-west-1"

STATUS_COLORS = {
    "SUCCEEDED": "green",
    "FAILED": "red",
    "TIMED_OUT": "orange",
    "RUNNING": "blue",
    "ABORTED": "grey",
}


def status_color(status: str) -> str:
    return STATUS_COLORS.get(status, "grey")


def _render_bde_performance(filtered_df: pd.DataFrame) -> None:
    """Render per-BDE performance analytics."""
    st.subheader("BDE Performance Analytics")

    if "bde_name" not in filtered_df.columns or filtered_df.empty:
        st.info("No execution data available for BDE performance analysis.")
        return

    completed_df = filtered_df[filtered_df["duration_seconds"].notna()].copy()

    if completed_df.empty:
        st.info("No completed executions — duration metrics unavailable.")
        return

    # BDE summary table
    bde_summary = (
        completed_df.groupby("bde_name")
        .agg(
            execution_count=("bde_name", "size"),
            avg_duration=("duration_seconds", "mean"),
            min_duration=("duration_seconds", "min"),
            max_duration=("duration_seconds", "max"),
            median_duration=("duration_seconds", "median"),
        )
        .reset_index()
    )

    # Success rate per BDE
    success_counts = (
        filtered_df[filtered_df["status"] == "SUCCEEDED"]
        .groupby("bde_name")
        .size()
        .reset_index(name="succeeded_count")
    )
    total_counts = (
        filtered_df.groupby("bde_name")
        .size()
        .reset_index(name="total_count")
    )
    rate_df = total_counts.merge(success_counts, on="bde_name", how="left").fillna(0)
    rate_df["success_rate"] = (rate_df["succeeded_count"] / rate_df["total_count"]) * 100
    bde_summary = bde_summary.merge(rate_df[["bde_name", "success_rate"]], on="bde_name", how="left").fillna(0)
    bde_summary = bde_summary.sort_values("avg_duration", ascending=False)

    st.markdown("**BDE Summary**")
    display_cols = ["bde_name", "execution_count", "avg_duration", "min_duration",
                    "max_duration", "median_duration", "success_rate"]
    st.dataframe(
        bde_summary[display_cols].rename(columns={
            "bde_name": "BDE Name",
            "execution_count": "Executions",
            "avg_duration": "Avg (s)",
            "min_duration": "Min (s)",
            "max_duration": "Max (s)",
            "median_duration": "Median (s)",
            "success_rate": "Success %",
        }),
        use_container_width=True,
        hide_index=True,
    )

    # Horizontal bar chart — average duration per BDE
    fig_bar = px.bar(
        bde_summary,
        x="avg_duration",
        y="bde_name",
        orientation="h",
        labels={"avg_duration": "Average Duration (s)", "bde_name": "BDE"},
        title="Average Execution Duration per BDE",
    )
    fig_bar.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_bar, use_container_width=True)

    # Scatter chart — duration over time colored by BDE
    fig_scatter = px.scatter(
        completed_df,
        x="start_time",
        y="duration_seconds",
        color="bde_name",
        labels={
            "start_time": "Start Time",
            "duration_seconds": "Duration (s)",
            "bde_name": "BDE",
        },
        title="Execution Duration Over Time by BDE",
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    # Drill-down: select a BDE
    bde_names = sorted(bde_summary["bde_name"].tolist())
    selected_bde = st.selectbox("Drill down into BDE", bde_names, key="b2p_bde_drilldown")
    if selected_bde:
        drill_df = filtered_df[filtered_df["bde_name"] == selected_bde][
            ["environment", "execution_name", "status", "start_time", "stop_time", "duration_seconds"]
        ].sort_values("start_time", ascending=False)
        st.dataframe(drill_df, use_container_width=True, hide_index=True)


def _render_live_executions(filtered_df: pd.DataFrame) -> None:
    """Render live monitoring for currently running executions grouped by BDE."""
    running_df = filtered_df[filtered_df["status"] == "RUNNING"].copy()
    if running_df.empty:
        return

    st.subheader("🔴 Live Executions")

    now_utc = pd.Timestamp.now(tz="UTC")
    running_df["elapsed_seconds"] = (now_utc - running_df["start_time"]).dt.total_seconds()

    for bde_name, group in running_df.groupby("bde_name"):
        st.markdown(f"**{bde_name}** ({len(group)} running)")
        display_df = group[["execution_name", "bde_name", "start_time", "elapsed_seconds"]].rename(columns={
            "execution_name": "Execution",
            "bde_name": "BDE",
            "start_time": "Started",
            "elapsed_seconds": "Elapsed (s)",
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)


def render_b2p_step_functions(start_date, start_time, end_date, end_time, auto_refresh) -> None:
    """Render Step Functions monitoring with BDE performance analytics."""

    # --- Session state initialisation ---
    if "b2p_sfn_state_machines" not in st.session_state:
        st.session_state.b2p_sfn_state_machines = None
    if "b2p_sfn_executions" not in st.session_state:
        st.session_state.b2p_sfn_executions = None
    if "b2p_sfn_last_fetch_ts" not in st.session_state:
        st.session_state.b2p_sfn_last_fetch_ts = None
    if "b2p_sfn_fetch_requested" not in st.session_state:
        st.session_state.b2p_sfn_fetch_requested = False

    st.markdown("### Step Functions Monitor")
    st.caption("Monitoring dashboard for base-to-prepared Step Functions executions (uses raw-to-base state machines)")

    # --- Discover state machines on load ---
    if st.session_state.b2p_sfn_state_machines is None:
        try:
            st.session_state.b2p_sfn_state_machines = list_matching_state_machines(pattern=B2P_SFN_PATTERN)
        except Exception as e:
            st.error(f"Failed to discover state machines: {e}")
            st.session_state.b2p_sfn_state_machines = pd.DataFrame(
                columns=["state_machine_arn", "name", "environment", "creation_date"]
            )

    sm_df = st.session_state.b2p_sfn_state_machines

    if sm_df is None or sm_df.empty:
        st.info(f"No state machines matching pattern `{B2P_SFN_PATTERN}` were found.")
        return

    # Resolve refresh interval
    refresh_seconds_map = {"Off": 0, "10s": 10, "30s": 30, "1m": 60, "5m": 300, "10m": 600}
    refresh_interval_s = refresh_seconds_map.get(auto_refresh, 0)

    # Fetch button
    if st.button("🔍 Fetch Data", use_container_width=True, type="primary", key="b2p_sfn_fetch_btn"):
        st.session_state.b2p_sfn_fetch_requested = True
        st.rerun()

    # --- Fetch data when requested ---
    _should_fetch = st.session_state.b2p_sfn_fetch_requested or (
        refresh_interval_s > 0 and st.session_state.b2p_sfn_executions is not None
    )

    if _should_fetch:
        _local_tz = datetime.now().astimezone().tzinfo
        _now_local = datetime.now(_local_tz)
        _start_local = datetime.combine(start_date, start_time).replace(tzinfo=_local_tz)

        if refresh_interval_s > 0 and not st.session_state.b2p_sfn_fetch_requested:
            _end_local = _now_local
        else:
            _end_local = datetime.combine(end_date, end_time).replace(tzinfo=_local_tz)

        _start_utc = _start_local.astimezone(timezone.utc)
        _end_utc = _end_local.astimezone(timezone.utc)
        _start_iso = _start_utc.isoformat()
        _end_iso = _end_utc.isoformat()

        if _start_iso >= _end_iso:
            st.warning("⚠️ 'From' time must be before 'To' time. Please adjust the time range.")
            st.session_state.b2p_sfn_fetch_requested = False
            return

        try:
            arns = sm_df["state_machine_arn"].tolist()
            st.session_state.b2p_sfn_executions = fetch_executions(arns, _start_iso, _end_iso)
            st.session_state.b2p_sfn_last_fetch_ts = pd.Timestamp.now(tz="UTC").isoformat()
        except Exception as e:
            st.error(f"Failed to fetch executions: {e}")

        st.session_state.b2p_sfn_fetch_requested = False

    exec_df = st.session_state.b2p_sfn_executions

    if exec_df is None or exec_df.empty:
        st.info("Set your date/time range above and click **Fetch Data** to load Step Functions executions.")
        return

    # Enrich with BDE name
    exec_df = exec_df.copy()
    exec_df["bde_name"] = exec_df["execution_name"].apply(extract_bde_name)

    # --- Environment filter ---
    all_envs = sorted(exec_df["environment"].unique().tolist())
    selected_envs = st.multiselect(
        "Filter by Environment",
        options=all_envs,
        default=all_envs,
        key="b2p_env_filter",
    )

    filtered_df = exec_df[exec_df["environment"].isin(selected_envs)].copy() if selected_envs else exec_df.copy()

    # --- KPI Cards ---
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
        st.markdown("**Error Frequency**")
        error_freq = (
            error_df.groupby("error_name", dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
        st.dataframe(error_freq, use_container_width=True, hide_index=True)

        st.markdown("**Failed & Timed-Out Executions**")
        error_table = error_df[
            ["environment", "execution_name", "bde_name", "start_time", "stop_time", "error_name", "error_cause"]
        ].sort_values("start_time", ascending=False)
        st.dataframe(error_table, use_container_width=True, hide_index=True)

    st.divider()

    # --- Execution History ---
    st.subheader("Execution History")
    history_df = filtered_df[
        ["environment", "execution_name", "bde_name", "status", "start_time", "stop_time", "duration_seconds"]
    ].sort_values("start_time", ascending=False)

    if history_df.empty:
        st.info("No executions to display.")
    else:
        def _color_status(val: str) -> str:
            color = status_color(val)
            return f"color: {color}; font-weight: bold"

        styled = history_df.style.map(_color_status, subset=["status"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    st.divider()

    # --- BDE Performance Analytics ---
    _render_bde_performance(filtered_df)

    st.divider()

    # --- Live Execution Monitoring ---
    if refresh_interval_s > 0:
        _render_live_executions(filtered_df)
