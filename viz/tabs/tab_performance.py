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

    with st.expander("🐢 Slowest Views (Top 15)", expanded=True):
        slowest = completed_with_dur.nlargest(15, "duration_s")
        fig_bar = px.bar(
            slowest, x="duration_s", y="model_name", orientation="h",
            color="entity", text="duration_s",
            labels={"duration_s": "Duration (seconds)", "model_name": "View", "entity": "Entity"},
        )
        fig_bar.update_traces(texttemplate="%{text:.1f}s", textposition="outside")
        fig_bar.update_layout(
            yaxis=dict(categoryorder="total ascending"),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e0e0e0", height=500,
        )
        st.plotly_chart(fig_bar, use_container_width=True)


