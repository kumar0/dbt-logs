"""Tab 3: Performance Analytics."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go


def render(classified: pd.DataFrame):
    if classified.empty or "final_status" not in classified.columns:
        st.info("No performance data available for the selected date range.")
        return

    completed = classified[classified["final_status"] != "running"].copy()

    if completed.empty:
        st.info("No duration data available.")
        return

    # --- Entity-level: avg wall-clock per invocation (end - start per invocation, then avg) ---
    def inv_wall_clocks(grp):
        """One wall-clock second value per invocation for this entity."""
        records = []
        for _, inv_grp in grp.groupby("invocation_id"):
            start = inv_grp["start_time"].dropna().min()
            end = inv_grp["end_time"].dropna().max()
            if pd.notna(start) and pd.notna(end):
                records.append((end - start).total_seconds())
        return pd.Series(records)

    entity_dur_rows = []
    for entity, grp in completed.groupby("entity"):
        wc = inv_wall_clocks(grp).dropna()
        if wc.empty:
            continue
        entity_dur_rows.append({
            "entity": entity,
            "avg_s": wc.mean(),
            "min_s": wc.min(),
            "max_s": wc.max(),
            "runs": len(wc),
        })

    entity_dur = pd.DataFrame(entity_dur_rows).sort_values("avg_s", ascending=False)

    st.markdown("### ⏱ Entity Duration (Wall-Clock)")
    st.caption("Avg wall-clock per invocation = last view end − first view start, accounting for parallel dbt threads.")

    if entity_dur.empty:
        st.info("No entity duration data available.")
        return

    fig_entity = go.Figure(go.Bar(
        x=entity_dur["avg_s"],
        y=entity_dur["entity"],
        orientation="h",
        text=entity_dur["avg_s"].apply(lambda x: f"{x:.1f}s"),
        textposition="outside",
        marker_color="#60a5fa",
        customdata=entity_dur[["min_s", "max_s", "runs"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Avg: %{x:.1f}s<br>"
            "Min: %{customdata[0]:.1f}s<br>"
            "Max: %{customdata[1]:.1f}s<br>"
            "Invocations: %{customdata[2]}<extra></extra>"
        ),
    ))
    fig_entity.update_layout(
        yaxis=dict(categoryorder="total ascending"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0", height=max(300, len(entity_dur) * 45),
        xaxis_title="Avg Duration (seconds)",
    )
    st.plotly_chart(fig_entity, use_container_width=True)

    # --- Drill-down: pick an entity to see its models ---
    st.markdown("### 🔍 Drill Down by Entity")
    entity_options = entity_dur["entity"].tolist()
    if not entity_options:
        st.info("No entities with duration data.")
        return

    selected_entity = st.selectbox("Select Entity", entity_options, key="perf_entity")

    model_data = completed[
        (completed["entity"] == selected_entity) & completed["duration_s"].notna()
    ].copy()

    if model_data.empty:
        st.info(f"No model duration data for {selected_entity}.")
        return

    # Avg/min/max duration per model + comma-separated invocation IDs
    model_agg = (
        model_data.groupby("model_name")
        .agg(
            avg_s=("duration_s", "mean"),
            max_s=("duration_s", "max"),
            min_s=("duration_s", "min"),
            runs=("duration_s", "count"),
            invocation_ids=("invocation_id", lambda x: ", ".join(sorted(x.dropna().unique()))),
        )
        .reset_index()
        .sort_values("avg_s", ascending=False)
    )

    fig_models = go.Figure(go.Bar(
        x=model_agg["avg_s"],
        y=model_agg["model_name"],
        orientation="h",
        text=model_agg["avg_s"].apply(lambda x: f"{x:.1f}s"),
        textposition="outside",
        marker_color="#fb923c",
        customdata=model_agg[["min_s", "max_s", "runs", "invocation_ids"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Avg: %{x:.1f}s<br>"
            "Min: %{customdata[0]:.1f}s<br>"
            "Max: %{customdata[1]:.1f}s<br>"
            "Runs: %{customdata[2]}<br>"
            "Invocations: %{customdata[3]}<extra></extra>"
        ),
    ))
    fig_models.update_layout(
        yaxis=dict(categoryorder="total ascending"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0", height=max(300, len(model_agg) * 35),
        xaxis_title="Avg Duration (seconds)",
    )
    st.plotly_chart(fig_models, use_container_width=True)

    # Summary table with invocation IDs
    model_agg_display = model_agg.rename(columns={
        "model_name": "View", "avg_s": "Avg (s)", "min_s": "Min (s)",
        "max_s": "Max (s)", "runs": "Runs", "invocation_ids": "Invocations",
    })
    model_agg_display[["Avg (s)", "Min (s)", "Max (s)"]] = model_agg_display[
        ["Avg (s)", "Min (s)", "Max (s)"]
    ].round(1)
    st.dataframe(
        model_agg_display[["View", "Avg (s)", "Min (s)", "Max (s)", "Runs", "Invocations"]],
        use_container_width=True, hide_index=True,
    )
