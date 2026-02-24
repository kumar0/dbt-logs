"""Tab 5: Glue Metrics."""

import streamlit as st
import pandas as pd
import plotly.express as px

from helpers import get_glue_entities, format_bytes, get_metric_summary_for_session
from data_provider import GLUE_METRIC_CATEGORIES, ALL_METRICS_FLAT, last_run_config


def render(glue_df: pd.DataFrame, enabled: bool = False):
    st.markdown("### ⚡ Glue Interactive Session Metrics")
    st.caption("CloudWatch metrics from Glue sessions with `--conf enable_metrics=true`. Each entity runs in its own session.")

    if not enabled:
        st.info("Glue metrics are disabled by default to speed up initial load.")
        if st.button("⚡ Load Glue Metrics", type="primary"):
            st.session_state.glue_metrics_enabled = True
            st.session_state.fetch_requested = True
            st.rerun()
        return

    if glue_df.empty:
        st.warning("No Glue metrics data found. Use the filter above or adjust the main date range and click Fetch Data.")
        return

    glue_entities = get_glue_entities(glue_df)
    if not glue_entities:
        st.info("No entity data found in Glue metrics.")
        return

    gcol1, gcol2 = st.columns([1, 1])
    with gcol1:
        selected_entity_glue = st.selectbox("Select Entity", glue_entities, key="glue_entity_select")
    with gcol2:
        entity_rows = glue_df[glue_df["entity"] == selected_entity_glue]
        if not entity_rows.empty:
            run_count = glue_df[(glue_df["entity"] == selected_entity_glue) & (glue_df["job_run_id"] != "ALL")]["job_run_id"].nunique()
            st.markdown(f"**Entity:** `{selected_entity_glue}`")
            st.markdown(f"**Sessions:** `{run_count}`")
        else:
            st.markdown("**Entity:** N/A")

    metrics_df = glue_df[glue_df["entity"] == selected_entity_glue].copy()

    if metrics_df.empty:
        st.info(f"No metrics found for entity `{selected_entity_glue}`.")
        return

    summary = get_metric_summary_for_session(metrics_df)
    _render_health_kpis(summary)
    st.divider()
    _render_metric_details(summary, metrics_df)
    st.divider()
    _render_dpu_estimation(metrics_df)
    st.divider()
    _render_cross_entity(glue_df)


def _render_health_kpis(summary: pd.DataFrame):
    st.markdown("#### Key Health Indicators")
    kpi_metrics = {
        "glue.ALL.jvm.heap.usage": ("Heap Usage", "peak", "{:.1%}"),
        "glue.ALL.system.cpuSystemLoad": ("CPU Load", "peak", "{:.1%}"),
        "glue.ALL.s3.filesystem.read_bytes": ("S3 Read Total", "peak", "bytes"),
        "glue.ALL.s3.filesystem.write_bytes": ("S3 Write Total", "peak", "bytes"),
        "glue.driver.aggregate.numFailedTasks": ("Failed Tasks", "peak", "{:.0f}"),
        "glue.driver.aggregate.shuffleBytesWritten": ("Shuffle Written", "peak", "bytes"),
    }

    kpi_cols = st.columns(len(kpi_metrics))
    for i, (mname, (label, stat, fmt)) in enumerate(kpi_metrics.items()):
        row = summary[summary["metric_name"] == mname]
        if not row.empty:
            val = row.iloc[0][stat]
            display_val = format_bytes(val) if fmt == "bytes" else fmt.format(val)
        else:
            display_val = "N/A"
        with kpi_cols[i]:
            st.metric(label, display_val)


def _render_metric_details(summary: pd.DataFrame, metrics_df: pd.DataFrame):
    st.markdown("#### Metric Details by Category")

    for category in GLUE_METRIC_CATEGORIES.keys():
        cat_summary = summary[summary["category"] == category]
        if cat_summary.empty:
            continue

        with st.expander(f"📂 {category}", expanded=(category == "Resource Utilization")):
            display = cat_summary[["label", "avg", "peak", "total", "unit", "description"]].copy()
            for col in ["avg", "peak", "total"]:
                display[col] = display.apply(
                    lambda r: format_bytes(r[col]) if r["unit"] == "bytes" else (
                        f"{r[col]:.1%}" if r["unit"] == "ratio" else f"{r[col]:,.0f}"
                    ), axis=1
                )
            display = display.rename(columns={
                "label": "Metric", "avg": "Average", "peak": "Peak",
                "total": "Total", "unit": "Unit", "description": "What It Means",
            })
            st.dataframe(display[["Metric", "Average", "Peak", "Total", "What It Means"]], use_container_width=True, hide_index=True)

            cat_metrics = list(GLUE_METRIC_CATEGORIES[category].keys())
            cat_ts = metrics_df[
                (metrics_df["metric_name"].isin(cat_metrics)) &
                (metrics_df["run_id_type"] == "ALL")
            ]
            if cat_ts.empty:
                cat_ts = metrics_df[metrics_df["metric_name"].isin(cat_metrics)]

            if not cat_ts.empty:
                fig = px.line(
                    cat_ts, x="timestamp", y="average", color="label",
                    title=f"{category} Over Time",
                    labels={"average": "Value", "timestamp": "Time", "label": "Metric"},
                )
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font_color="#e0e0e0", height=350,
                )
                st.plotly_chart(fig, use_container_width=True)


def _render_dpu_estimation(metrics_df: pd.DataFrame):
    st.markdown("#### 💰 Cost & Right-Sizing Analysis")

    # --- Worker type (auto-detected from container_start log) ---
    dpu_map = {"G.025X": 0.25, "G.1X": 1, "G.2X": 2, "Z.2X": 2}
    mem_gb_map = {"G.025X": 2, "G.1X": 16, "G.2X": 32, "Z.2X": 64}
    vcpu_map = {"G.025X": 2, "G.1X": 4, "G.2X": 8, "Z.2X": 8}

    detected_type = last_run_config.get("worker_type", "G.1X")
    if detected_type not in dpu_map:
        detected_type = "G.1X"

    st.caption(f"Worker type: **{detected_type}** (auto-detected from run config) — "
               f"{vcpu_map[detected_type]} vCPUs, {mem_gb_map[detected_type]} GB RAM, "
               f"{dpu_map[detected_type]} DPU per worker")

    # --- Executor data ---
    executor_data = metrics_df[
        (metrics_df["metric_name"] == "glue.driver.ExecutorAllocationManager.executors.numberAllExecutors") &
        (metrics_df["run_id_type"] == "session")
    ]
    if executor_data.empty:
        executor_data = metrics_df[
            metrics_df["metric_name"] == "glue.driver.ExecutorAllocationManager.executors.numberAllExecutors"
        ]

    max_needed_data = metrics_df[
        metrics_df["metric_name"] == "glue.driver.ExecutorAllocationManager.executors.numberMaxNeededExecutors"
    ]

    if executor_data.empty:
        st.info("No executor allocation metrics found.")
        return

    dpu_per_worker = dpu_map[detected_type]
    # Add 1 to average executors to account for the mandatory driver node
    total_dpu_hours = ((executor_data["average"] + 1) * (300 / 3600) * dpu_per_worker).sum()
    cost = total_dpu_hours * 0.44
    avg_executors = executor_data["average"].mean()
    peak_executors = executor_data["maximum"].max()

    # --- Cost KPIs ---
    dc1, dc2, dc3, dc4 = st.columns(4)
    dc1.metric("DPU-Hours", f"{total_dpu_hours:.2f}")
    dc2.metric("Est. Cost", f"${cost:.2f}")
    dc3.metric("Avg Executors", f"{avg_executors:.1f}")
    dc4.metric("Peak Executors", f"{peak_executors:.0f}")

    # --- Provisioning verdict ---
    heap_data = metrics_df[metrics_df["metric_name"] == "glue.ALL.jvm.heap.usage"]
    cpu_data = metrics_df[metrics_df["metric_name"] == "glue.ALL.system.cpuSystemLoad"]
    disk_spill = metrics_df[metrics_df["metric_name"] == "glue.driver.BlockManager.disk.diskSpaceUsed_MB"]
    failed_tasks = metrics_df[metrics_df["metric_name"] == "glue.driver.aggregate.numFailedTasks"]
    shuffle_data = metrics_df[metrics_df["metric_name"] == "glue.driver.aggregate.shuffleBytesWritten"]

    peak_heap = heap_data["maximum"].max() if not heap_data.empty else 0
    avg_heap = heap_data["average"].mean() if not heap_data.empty else 0
    peak_cpu = cpu_data["maximum"].max() if not cpu_data.empty else 0
    avg_cpu = cpu_data["average"].mean() if not cpu_data.empty else 0
    total_spill_mb = disk_spill["sum"].sum() if not disk_spill.empty else 0
    total_failed = failed_tasks["sum"].sum() if not failed_tasks.empty else 0
    avg_max_needed = max_needed_data["average"].mean() if not max_needed_data.empty else 0

    # Build findings
    findings: list[tuple[str, str, str]] = []  # (icon, label, detail)

    # Memory analysis
    if peak_heap > 0.9:
        findings.append(("🔴", "Memory Critical",
                         f"Peak heap {peak_heap:.0%} — OOM risk. Consider upgrading to a larger worker type or adding workers."))
    elif peak_heap > 0.75:
        findings.append(("🟡", "Memory Elevated",
                         f"Peak heap {peak_heap:.0%}, avg {avg_heap:.0%}. Approaching limits under peak load."))
    elif peak_heap > 0 and peak_heap < 0.4:
        findings.append(("🟢", "Memory Under-utilized",
                         f"Peak heap only {peak_heap:.0%}. You could downsize to a smaller worker type to save cost."))
    elif peak_heap > 0:
        findings.append(("🟢", "Memory OK", f"Peak heap {peak_heap:.0%}, avg {avg_heap:.0%}. Healthy range."))

    # CPU analysis
    if peak_cpu > 0.85:
        findings.append(("🔴", "CPU Saturated",
                         f"Peak CPU {peak_cpu:.0%}. Tasks are CPU-bound — add more workers or upgrade worker type."))
    elif peak_cpu > 0 and peak_cpu < 0.2:
        findings.append(("🟢", "CPU Under-utilized",
                         f"Peak CPU only {peak_cpu:.0%}. Workload is I/O-bound, not CPU-bound. Smaller workers may suffice."))
    elif peak_cpu > 0:
        findings.append(("🟢", "CPU OK", f"Peak CPU {peak_cpu:.0%}, avg {avg_cpu:.0%}."))

    # Disk spill
    if total_spill_mb > 0:
        findings.append(("🟡", "Disk Spill Detected",
                         f"{total_spill_mb:.0f} MB spilled to disk. Memory insufficient for shuffle/sort — "
                         "consider more memory (larger worker type) or reducing shuffle via model refactoring."))

    # Failed tasks
    if total_failed > 0:
        findings.append(("🔴", "Task Failures",
                         f"{total_failed:.0f} Spark tasks failed. Check for data skew, OOM, or corrupt data."))

    # Executor scaling
    if avg_max_needed > 0 and avg_executors > 0:
        utilization = avg_executors / avg_max_needed if avg_max_needed > 0 else 1
        if utilization < 0.5:
            findings.append(("🟡", "Scaling Lag",
                             f"Avg executors {avg_executors:.1f} vs max needed {avg_max_needed:.1f}. "
                             "Auto-scaling may be too slow — consider setting a higher min executor count."))
        elif avg_max_needed < avg_executors * 0.5:
            findings.append(("🟢", "Over-provisioned Executors",
                             f"Spark only needed ~{avg_max_needed:.1f} executors but had {avg_executors:.1f}. "
                             "Reduce NUM_WORKERS to save cost."))

    # Render findings
    if findings:
        st.markdown("##### Provisioning Verdict")
        for icon, label, detail in findings:
            st.markdown(f"{icon} **{label}** — {detail}")
    else:
        st.caption("Not enough metric data to assess provisioning. Ensure `--enable-metrics=true` is set.")

    st.divider()

    # --- Executor chart with max-needed overlay ---
    chart_df = executor_data[["timestamp", "average"]].copy().sort_values("timestamp")
    chart_df = chart_df.rename(columns={"average": "Active Executors"})

    if not max_needed_data.empty:
        max_df = max_needed_data[["timestamp", "average"]].copy().sort_values("timestamp")
        max_df = max_df.rename(columns={"average": "Max Needed"})
        chart_df = pd.merge_asof(chart_df, max_df, on="timestamp", direction="nearest")

    melted = chart_df.melt(id_vars="timestamp", var_name="Series", value_name="Count")
    fig_exec = px.line(
        melted, x="timestamp", y="Count", color="Series",
        title="Executor Allocation vs Demand",
        labels={"Count": "Executors", "timestamp": "Time"},
        color_discrete_map={"Active Executors": "#60a5fa", "Max Needed": "#f87171"},
    )
    fig_exec.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0", height=300,
    )
    st.plotly_chart(fig_exec, use_container_width=True)



def _render_cross_entity(glue_df: pd.DataFrame):
    st.markdown("#### 📊 Cross-Entity Comparison")
    compare_metric = st.selectbox(
        "Compare metric across all entities",
        [
            "glue.ALL.jvm.heap.usage",
            "glue.ALL.system.cpuSystemLoad",
            "glue.ALL.s3.filesystem.read_bytes",
            "glue.ALL.s3.filesystem.write_bytes",
            "glue.driver.aggregate.shuffleBytesWritten",
            "glue.driver.aggregate.numFailedTasks",
            "glue.driver.aggregate.recordsRead",
            "glue.driver.ExecutorAllocationManager.executors.numberAllExecutors",
        ],
        format_func=lambda m: ALL_METRICS_FLAT.get(m, {}).get("label", m),
        key="cross_entity_metric",
    )

    cross_df = glue_df[
        (glue_df["metric_name"] == compare_metric) &
        (glue_df["run_id_type"] == "ALL")
    ]
    if cross_df.empty:
        cross_df = glue_df[glue_df["metric_name"] == compare_metric]

    if not cross_df.empty:
        is_cumulative = compare_metric in [
            "glue.ALL.s3.filesystem.read_bytes",
            "glue.ALL.s3.filesystem.write_bytes",
            "glue.driver.aggregate.shuffleBytesWritten",
            "glue.driver.aggregate.numFailedTasks",
            "glue.driver.aggregate.recordsRead"
        ]
        if is_cumulative:
            entity_avg = cross_df.groupby("entity")["average"].max().reset_index()
            agg_label = "Peak"
        else:
            entity_avg = cross_df.groupby("entity")["average"].mean().reset_index()
            agg_label = "Average"
            
        entity_avg.columns = ["Entity", "Value"]
        entity_avg = entity_avg.sort_values("Value", ascending=False)

        metric_label = ALL_METRICS_FLAT.get(compare_metric, {}).get("label", compare_metric)
        fig_cross = px.bar(
            entity_avg, x="Entity", y="Value", color="Value",
            color_continuous_scale="Viridis",
            title=f"{metric_label} — {agg_label} per Entity",
            labels={"Value": f"{metric_label} ({agg_label})"},
        )
        fig_cross.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e0e0e0", height=400,
        )
        st.plotly_chart(fig_cross, use_container_width=True)
