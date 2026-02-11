"""Tab 2: Completed Runs with error drill-down."""

import streamlit as st
import pandas as pd
import plotly.express as px

from helpers import status_icon, build_invocation_labels


def render(classified: pd.DataFrame, exec_summary: pd.DataFrame, raw_df: pd.DataFrame | None = None):
    """Render completed runs tab.

    Parameters
    ----------
    raw_df : pd.DataFrame, optional
        Full raw log DataFrame — used to look up error_message for
        failed models so users can drill into root causes.
    """
    if classified.empty or "final_status" not in classified.columns:
        st.info("No completed run data available for the selected date range.")
        return

    completed = classified[classified["final_status"] != "running"].copy()

    inv_labels = build_invocation_labels(completed)
    label_to_inv = {v: k for k, v in inv_labels.items()}
    inv_display = ["All Invocations"] + sorted(inv_labels.values())
    selected_label = st.selectbox("Filter by Invocation ID", inv_display, key="completed_inv")
    if selected_label != "All Invocations":
        selected_inv = label_to_inv[selected_label]
        completed = completed[completed["invocation_id"] == selected_inv]

    entity_options = ["All Entities"] + sorted(completed["entity"].unique().tolist())
    selected_entity = st.selectbox("Filter by Entity", entity_options, key="completed_entity")
    if selected_entity != "All Entities":
        completed = completed[completed["entity"] == selected_entity]

    if completed.empty:
        st.info("No completed models match the current filters.")
    else:
        status_counts = completed["final_status"].value_counts().reset_index()
        status_counts.columns = ["Status", "Count"]

        col_a, col_b = st.columns([1, 2])
        with col_a:
            fig_pie = px.pie(
                status_counts, values="Count", names="Status",
                color="Status",
                color_discrete_map={"OK": "#4ade80", "pass": "#4ade80", "error": "#f87171", "skipped": "#fbbf24"},
                title="Model Status Distribution", hole=0.4,
            )
            fig_pie.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#e0e0e0")
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_b:
            display_df = completed[["entity", "model_name", "final_status", "start_time", "end_time", "duration_s", "thread"]].copy()
            display_df["Status"] = display_df["final_status"].apply(lambda s: f"{status_icon(s)} {s}")
            display_df["start_time"] = display_df["start_time"].dt.strftime("%H:%M:%S")
            display_df["end_time"] = display_df["end_time"].dt.strftime("%H:%M:%S")
            display_df["duration_s"] = display_df["duration_s"].apply(lambda x: f"{x:.1f}s" if pd.notna(x) else "N/A")
            display_df = display_df.rename(columns={
                "entity": "Entity", "model_name": "Model", "start_time": "Started",
                "end_time": "Ended", "duration_s": "Duration", "thread": "Thread",
            })
            st.dataframe(
                display_df[["Entity", "Model", "Status", "Started", "Ended", "Duration", "Thread"]],
                use_container_width=True, hide_index=True, height=400,
            )

        # --- Error drill-down ---
        _render_error_drilldown(completed, raw_df)

    if not exec_summary.empty:
        st.markdown("### Execution Summary per Invocation")
        disp_exec = exec_summary.copy()
        disp_exec["total_duration_s"] = disp_exec["total_duration_s"].apply(lambda x: f"{x:.0f}s ({x/60:.1f}m)")
        disp_exec["start_time"] = disp_exec["start_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        disp_exec["end_time"] = disp_exec["end_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(
            disp_exec[["invocation_id", "start_time", "end_time", "total_duration_s", "status_message"]].rename(columns={
                "invocation_id": "Invocation", "start_time": "Start", "end_time": "End",
                "total_duration_s": "Total Duration", "status_message": "Result",
            }),
            use_container_width=True, hide_index=True,
        )


def _render_error_drilldown(completed: pd.DataFrame, raw_df: pd.DataFrame | None):
    """Show expandable error details for every failed model."""
    failed = completed[completed["final_status"] == "error"]
    if failed.empty:
        return

    st.markdown("### ❌ Failed Models — Error Details")

    # Build a lookup of error messages from the raw log data
    error_lookup: dict[tuple[str, str], str] = {}
    if raw_df is not None and "error_message" in raw_df.columns:
        err_rows = raw_df[
            (raw_df["error_message"].notna())
            & (raw_df["error_message"] != "")
        ]
        for _, r in err_rows.iterrows():
            key = (r.get("invocation_id", ""), r.get("model_name", ""))
            error_lookup[key] = r["error_message"]

    for _, row in failed.iterrows():
        model = row["model_name"]
        entity = row["entity"]
        inv = row["invocation_id"]
        err_msg = error_lookup.get((inv, model), "")

        with st.expander(f"🔴 {entity} / {model}", expanded=False):
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**Invocation:** `{inv[:16]}…`")
            c2.markdown(f"**Started:** {row['start_time'].strftime('%H:%M:%S') if pd.notna(row['start_time']) else 'N/A'}")
            c3.markdown(f"**Thread:** `{row['thread']}`")

            if err_msg:
                st.code(err_msg, language="text")
            else:
                st.caption("No error message captured — check CloudWatch logs directly.")
