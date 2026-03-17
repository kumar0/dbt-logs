"""Glue Job monitoring tab for the Raw to Base section."""

import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from glue_job_data_provider import fetch_glue_job_runs, list_matching_glue_jobs
import plotly.express as px

GLUE_JOB_PATTERN = "raw-to-base-*-eu-west-1"

GLUE_STATUS_COLORS = {
    "SUCCEEDED": "green",
    "FAILED": "red",
    "TIMEOUT": "orange",
    "RUNNING": "blue",
    "STOPPED": "grey",
}


def status_color(status: str) -> str:
    """Map a Glue job run status to its display color."""
    return GLUE_STATUS_COLORS.get(status, "grey")


def compute_status_counts(df: pd.DataFrame) -> dict[str, int]:
    """Compute run counts per status and total from a DataFrame of Glue job runs."""
    counts = {"Total": len(df)}
    for status in ("SUCCEEDED", "FAILED", "TIMEOUT", "RUNNING", "STOPPED"):
        counts[status] = int((df["status"] == status).sum())
    return counts


def compute_duration_stats(execution_times: pd.Series) -> dict[str, float]:
    """Compute min, max, average, median from a Series of execution times."""
    return {
        "Min (s)": float(execution_times.min()),
        "Max (s)": float(execution_times.max()),
        "Average (s)": float(execution_times.mean()),
        "Median (s)": float(execution_times.median()),
    }


def filter_error_runs(df: pd.DataFrame) -> pd.DataFrame:
    """Return only FAILED and TIMEOUT runs."""
    return df[df["status"].isin(["FAILED", "TIMEOUT"])].copy()


def sort_runs_by_start_time(df: pd.DataFrame) -> pd.DataFrame:
    """Sort runs by start_time descending."""
    return df.sort_values("start_time", ascending=False).copy()


def compute_run_cost(dpu_count: float, execution_time_sec: float) -> float:
    """Calculate estimated cost for a single Glue job run."""
    return dpu_count * (execution_time_sec / 3600) * 0.44


def compute_cost_summary(df: pd.DataFrame) -> dict[str, float]:
    """Compute total and average cost across all runs."""
    costs = df.apply(
        lambda row: compute_run_cost(row["dpu_count"], row["execution_time_sec"]),
        axis=1,
    )
    total = float(costs.sum())
    count = len(df)
    average = total / count if count > 0 else 0.0
    return {"total_cost": total, "average_cost": average, "run_count": count}


def render_glue_job(start_date, start_time, end_date, end_time, auto_refresh) -> None:
    """Render the Glue Job monitoring section.

    Receives shared date/time controls from the parent Raw to Base section.
    """

    # --- Session state initialisation ---
    if "glue_discovered_jobs" not in st.session_state:
        st.session_state.glue_discovered_jobs = None
    if "glue_job_runs" not in st.session_state:
        st.session_state.glue_job_runs = None
    if "glue_last_fetch_ts" not in st.session_state:
        st.session_state.glue_last_fetch_ts = None
    if "glue_fetch_requested" not in st.session_state:
        st.session_state.glue_fetch_requested = False

    # --- Header ---
    st.markdown("### Glue Job Monitor")
    st.caption("Monitoring dashboard for raw-to-base Glue job executions")

    # --- Discover Glue jobs on first load ---
    if st.session_state.glue_discovered_jobs is None:
        try:
            st.session_state.glue_discovered_jobs = list_matching_glue_jobs(GLUE_JOB_PATTERN)
        except Exception as e:
            st.error(f"Failed to discover Glue jobs: {e}")
            st.session_state.glue_discovered_jobs = []

    discovered_jobs = st.session_state.glue_discovered_jobs

    if not discovered_jobs:
        st.info(f"No Glue jobs matching pattern `{GLUE_JOB_PATTERN}` were found.")
        return

    # --- Job selector (supports multiple envs per account) ---
    selected_jobs = st.multiselect(
        "Glue Jobs",
        options=discovered_jobs,
        default=discovered_jobs,
        key="glue_job_selector",
    )

    if not selected_jobs:
        st.info("Select at least one Glue job above.")
        return

    # Resolve refresh interval
    refresh_seconds_map = {"Off": 0, "30s": 30, "1m": 60, "5m": 300}
    refresh_interval_s = refresh_seconds_map.get(auto_refresh, 0)

    # Fetch button
    if st.button("🔍 Fetch Data", use_container_width=True, type="primary", key="glue_fetch_btn"):
        st.session_state.glue_fetch_requested = True
        st.rerun()

    # --- Fetch data when requested (button or auto-refresh) ---
    _should_fetch = st.session_state.glue_fetch_requested or (
        refresh_interval_s > 0 and st.session_state.glue_job_runs is not None
    )

    if _should_fetch:
        _local_tz = datetime.now().astimezone().tzinfo
        _now_local = datetime.now(_local_tz)
        _start_local = datetime.combine(start_date, start_time).replace(tzinfo=_local_tz)

        if refresh_interval_s > 0 and not st.session_state.glue_fetch_requested:
            _end_local = _now_local
        else:
            _end_local = datetime.combine(end_date, end_time).replace(tzinfo=_local_tz)

        _start_utc = _start_local.astimezone(timezone.utc)
        _end_utc = _end_local.astimezone(timezone.utc)
        _start_iso = _start_utc.isoformat()
        _end_iso = _end_utc.isoformat()

        if _start_iso >= _end_iso:
            st.warning("⚠️ 'From' time must be before 'To' time. Please adjust the time range.")
            st.session_state.glue_fetch_requested = False
            return

        try:
            all_runs = []
            for job_name in selected_jobs:
                job_runs = fetch_glue_job_runs(job_name, _start_iso, _end_iso)
                if not job_runs.empty:
                    job_runs = job_runs.copy()
                    job_runs["job_name"] = job_name
                    all_runs.append(job_runs)
            if all_runs:
                st.session_state.glue_job_runs = pd.concat(all_runs, ignore_index=True)
            else:
                st.session_state.glue_job_runs = pd.DataFrame()
            st.session_state.glue_last_fetch_ts = pd.Timestamp.now(tz="UTC").isoformat()
        except Exception as e:
            st.error(f"Failed to fetch Glue job runs: {e}")

        st.session_state.glue_fetch_requested = False

    runs_df = st.session_state.glue_job_runs

    # --- Guard: if no data yet, prompt user to fetch ---
    if runs_df is None or runs_df.empty:
        st.info("Set your date/time range above and click **Fetch Data** to load Glue job runs.")
        return

    # =====================================================================
    # KPI Cards: Execution Status Summary
    # =====================================================================
    counts = compute_status_counts(runs_df)

    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
    with kpi1:
        st.markdown(
            f'<div class="metric-card"><h2>Total</h2><h1>{counts["Total"]}</h1></div>',
            unsafe_allow_html=True,
        )
    with kpi2:
        st.markdown(
            f'<div class="metric-card"><h2>Succeeded</h2><h1 class="status-ok">{counts["SUCCEEDED"]}</h1></div>',
            unsafe_allow_html=True,
        )
    with kpi3:
        st.markdown(
            f'<div class="metric-card"><h2>Failed</h2><h1 class="status-error">{counts["FAILED"]}</h1></div>',
            unsafe_allow_html=True,
        )
    with kpi4:
        st.markdown(
            f'<div class="metric-card"><h2>Timeout</h2><h1 class="status-skip">{counts["TIMEOUT"]}</h1></div>',
            unsafe_allow_html=True,
        )
    with kpi5:
        st.markdown(
            f'<div class="metric-card"><h2>Running</h2><h1 class="status-running">{counts["RUNNING"]}</h1></div>',
            unsafe_allow_html=True,
        )
    with kpi6:
        st.markdown(
            f'<div class="metric-card"><h2>Stopped</h2><h1 style="color:#9ca3af;">{counts["STOPPED"]}</h1></div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # =====================================================================
    # Duration Metrics
    # =====================================================================
    st.subheader("Duration Metrics")

    completed_df = runs_df[runs_df["execution_time_sec"].notna() & (runs_df["execution_time_sec"] > 0)].copy()

    if completed_df.empty:
        st.info("No completed runs to display duration metrics.")
    else:
        fig = px.scatter(
            completed_df,
            x="start_time",
            y="execution_time_sec",
            color="job_name" if "job_name" in completed_df.columns else None,
            labels={
                "start_time": "Start Time",
                "execution_time_sec": "Duration (seconds)",
                "job_name": "Glue Job",
            },
            title="Run Duration Over Time",
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Duration Statistics**")
        stats = compute_duration_stats(completed_df["execution_time_sec"])
        stats_df = pd.DataFrame([stats])
        st.dataframe(stats_df, use_container_width=True, hide_index=True)

    st.divider()

    # =====================================================================
    # Error Analysis
    # =====================================================================
    st.subheader("Error Analysis")

    error_df = filter_error_runs(runs_df)

    if error_df.empty:
        st.info("All runs succeeded — no errors found.")
    else:
        error_table = error_df[
            ["job_run_id", "start_time", "completion_time", "execution_time_sec", "error_message"]
        ].sort_values("start_time", ascending=False)
        st.dataframe(error_table, use_container_width=True, hide_index=True)

    st.divider()

    # =====================================================================
    # Run History Table
    # =====================================================================
    st.subheader("Run History")

    history_df = sort_runs_by_start_time(runs_df)[
        ["job_name", "job_run_id", "status", "start_time", "completion_time", "execution_time_sec", "dpu_count"]
    ]

    if history_df.empty:
        st.info("No runs to display.")
    else:
        def _color_status(val: str) -> str:
            color = status_color(val)
            return f"color: {color}; font-weight: bold"

        styled = history_df.style.map(_color_status, subset=["status"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    st.divider()

    # =====================================================================
    # Cost Estimation
    # =====================================================================
    st.subheader("Cost Estimation")

    cost_summary = compute_cost_summary(runs_df)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            f'<div class="metric-card"><h2>Total Estimated Cost</h2><h1>${cost_summary["total_cost"]:.4f}</h1></div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f'<div class="metric-card"><h2>Average Cost / Run</h2><h1>${cost_summary["average_cost"]:.4f}</h1></div>',
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f'<div class="metric-card"><h2>Total Runs</h2><h1>{cost_summary["run_count"]}</h1></div>',
            unsafe_allow_html=True,
        )
