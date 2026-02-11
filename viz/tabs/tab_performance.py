"""Tab 3: Performance Analytics."""

import streamlit as st
import pandas as pd
import plotly.express as px


def render(classified: pd.DataFrame):
    if classified.empty or "final_status" not in classified.columns:
        st.info("No performance data available for the selected date range.")
        return

    completed_with_dur = classified[(classified["final_status"] != "running") & classified["duration_s"].notna()].copy()

    if completed_with_dur.empty:
        st.info("No duration data available.")
        return

    st.markdown("### 🐢 Slowest Models (Top 15)")
    slowest = completed_with_dur.nlargest(15, "duration_s")
    fig_bar = px.bar(
        slowest, x="duration_s", y="model_name", orientation="h",
        color="entity", text="duration_s",
        labels={"duration_s": "Duration (seconds)", "model_name": "Model", "entity": "Entity"},
    )
    fig_bar.update_traces(texttemplate="%{text:.1f}s", textposition="outside")
    fig_bar.update_layout(
        yaxis=dict(categoryorder="total ascending"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0", height=500,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("### ⏱️ Total Duration by Entity")
    entity_dur = completed_with_dur.groupby("entity")["duration_s"].agg(["sum", "mean", "count"]).reset_index()
    entity_dur.columns = ["Entity", "Total (s)", "Avg (s)", "Model Count"]
    entity_dur = entity_dur.sort_values("Total (s)", ascending=False)

    fig_entity = px.bar(
        entity_dur, x="Entity", y="Total (s)", color="Avg (s)",
        text="Model Count", color_continuous_scale="RdYlGn_r",
        labels={"Total (s)": "Total Duration (s)", "Avg (s)": "Avg Duration (s)"},
    )
    fig_entity.update_traces(texttemplate="%{text} models", textposition="outside")
    fig_entity.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0", height=400,
    )
    st.plotly_chart(fig_entity, use_container_width=True)

    st.markdown("### 📈 Model Duration Distribution")
    fig_hist = px.histogram(
        completed_with_dur, x="duration_s", nbins=20,
        color="final_status",
        color_discrete_map={"OK": "#4ade80", "pass": "#4ade80", "error": "#f87171", "skipped": "#fbbf24"},
        labels={"duration_s": "Duration (seconds)", "final_status": "Status"},
    )
    fig_hist.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0", height=350,
    )
    st.plotly_chart(fig_hist, use_container_width=True)

    st.markdown("### 🧵 Thread Utilization (4 dbt threads)")
    thread_counts = completed_with_dur.groupby("thread").agg(
        models=("model_name", "count"),
        total_time=("duration_s", "sum"),
        avg_time=("duration_s", "mean"),
    ).reset_index()
    thread_counts.columns = ["Thread", "Models Run", "Total Time (s)", "Avg Time (s)"]

    fig_thread = px.bar(
        thread_counts, x="Thread", y="Total Time (s)", color="Models Run",
        text="Models Run", color_continuous_scale="Blues",
    )
    fig_thread.update_traces(texttemplate="%{text} models", textposition="outside")
    fig_thread.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0", height=350,
    )
    st.plotly_chart(fig_thread, use_container_width=True)
