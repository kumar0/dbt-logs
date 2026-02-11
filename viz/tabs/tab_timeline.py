"""Tab 4: Execution Timeline (Gantt)."""

import streamlit as st
import pandas as pd
import plotly.express as px

from helpers import build_invocation_labels


def render(classified: pd.DataFrame):
    if classified.empty or "start_time" not in classified.columns:
        st.info("No timeline data available for the selected date range.")
        return

    timeline_data = classified[classified["start_time"].notna()].copy()

    if timeline_data.empty:
        st.info("No timeline data available — no models have a recorded start time.")
        return

    inv_labels = build_invocation_labels(timeline_data)
    label_to_inv = {v: k for k, v in inv_labels.items()}
    inv_display = sorted(inv_labels.values())
    if not inv_display:
        st.info("No invocations found in the timeline data.")
        return

    selected_label = st.selectbox("Select Invocation", inv_display, key="timeline_inv")
    selected_inv_tl = label_to_inv[selected_label]

    inv_data = timeline_data[timeline_data["invocation_id"] == selected_inv_tl].copy()

    if inv_data.empty:
        st.info("No timeline data for this invocation.")
        return

    now = pd.Timestamp.now(tz="UTC")
    inv_data["end_display"] = inv_data["end_time"].fillna(now)
    inv_data["duration_display"] = inv_data.apply(
        lambda r: f"{r['duration_s']:.1f}s" if pd.notna(r["duration_s"]) else "running...", axis=1
    )

    color_map = {"OK": "#4ade80", "pass": "#4ade80", "error": "#f87171", "skipped": "#fbbf24", "running": "#60a5fa", "unknown": "#9ca3af"}

    fig_gantt = px.timeline(
        inv_data, x_start="start_time", x_end="end_display",
        y="model_name", color="final_status",
        color_discrete_map=color_map,
        hover_data=["entity", "duration_display", "thread"],
        labels={"model_name": "Model", "final_status": "Status"},
        title=f"Execution Timeline — {selected_label}",
    )
    fig_gantt.update_yaxes(categoryorder="array", categoryarray=inv_data.sort_values("start_time")["model_name"].tolist()[::-1])
    fig_gantt.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0", height=max(400, len(inv_data) * 28),
        xaxis_title="Time", yaxis_title="",
    )
    st.plotly_chart(fig_gantt, use_container_width=True)

    st.markdown("### 🧵 Thread Concurrency Over Time")
    events = []
    for _, r in inv_data.iterrows():
        if pd.notna(r["start_time"]):
            events.append({"time": r["start_time"], "delta": 1})
        if pd.notna(r["end_time"]):
            events.append({"time": r["end_time"], "delta": -1})
    if events:
        ev_df = pd.DataFrame(events).sort_values("time")
        ev_df["concurrent"] = ev_df["delta"].cumsum()
        fig_conc = px.area(
            ev_df, x="time", y="concurrent",
            labels={"time": "Time", "concurrent": "Concurrent Models"},
            line_shape="hv",
        )
        fig_conc.add_hline(y=4, line_dash="dash", line_color="#f87171", annotation_text="Max Threads (4)")
        fig_conc.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e0e0e0", height=300,
        )
        st.plotly_chart(fig_conc, use_container_width=True)
