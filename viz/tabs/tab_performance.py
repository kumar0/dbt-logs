"""Tab 3: Performance Analytics."""

import streamlit as st
import pandas as pd
import plotly.express as px


def render(classified: pd.DataFrame):
    if classified.empty or "final_status" not in classified.columns:
        st.info("No performance data available for the selected date range.")
        return

    completed = classified[classified["final_status"] != "running"].copy()

    if completed.empty:
        st.info("No duration data available.")
        return

    # --- Entity-level wall-clock duration (max end_time - min start_time) ---
    def entity_wall_clock(grp):
        start = grp["start_time"].dropna().min()
        end = grp["end_time"].dropna().max()
        if pd.isna(start) or pd.isna(end):
            return float("nan")
        return (end - start).total_seconds()

    entity_dur = (
        completed.groupby("entity")
        .apply(entity_wall_clock)
        .dropna()
        .reset_index()
    )
    entity_dur.columns = ["entity", "wall_clock_s"]
    entity_dur = entity_dur.sort_values("wall_clock_s", ascending=False)

    st.markdown("### ⏱ Entity Duration (Wall-Clock)")
    st.caption("Wall-clock = last view end − first view start, accounting for parallel dbt threads.")

    fig_entity = px.bar(
        entity_dur, x="wall_clock_s", y="entity", orientation="h",
        text="wall_clock_s",
        labels={"wall_clock_s": "Duration (seconds)", "entity": "Entity"},
        color="wall_clock_s",
        color_continuous_scale="Blues",
    )
    fig_entity.update_traces(texttemplate="%{text:.1f}s", textposition="outside")
    fig_entity.update_layout(
        yaxis=dict(categoryorder="total ascending"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0", height=max(300, len(entity_dur) * 45),
        coloraxis_showscale=False,
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

    # Average duration per model across invocations
    model_agg = (
        model_data.groupby("model_name")["duration_s"]
        .agg(avg_s="mean", max_s="max", min_s="min", runs="count")
        .reset_index()
        .sort_values("avg_s", ascending=False)
    )

    fig_models = px.bar(
        model_agg, x="avg_s", y="model_name", orientation="h",
        text="avg_s",
        labels={"avg_s": "Avg Duration (seconds)", "model_name": "View"},
        color="avg_s",
        color_continuous_scale="Oranges",
        hover_data={"min_s": ":.1f", "max_s": ":.1f", "runs": True},
    )
    fig_models.update_traces(texttemplate="%{text:.1f}s", textposition="outside")
    fig_models.update_layout(
        yaxis=dict(categoryorder="total ascending"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0", height=max(300, len(model_agg) * 35),
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig_models, use_container_width=True)

    # Summary table
    model_agg_display = model_agg.rename(columns={
        "model_name": "View", "avg_s": "Avg (s)", "min_s": "Min (s)",
        "max_s": "Max (s)", "runs": "Runs",
    })
    model_agg_display[["Avg (s)", "Min (s)", "Max (s)"]] = model_agg_display[
        ["Avg (s)", "Min (s)", "Max (s)"]
    ].round(1)
    st.dataframe(model_agg_display, use_container_width=True, hide_index=True)
