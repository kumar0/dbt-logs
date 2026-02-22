"""Tab 4: Execution Timeline."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go


# Distinct palette for per-model colouring
_PALETTE = [
    "#60a5fa", "#f472b6", "#34d399", "#fbbf24", "#a78bfa", "#fb923c",
    "#22d3ee", "#e879f9", "#4ade80", "#f87171", "#818cf8", "#facc15",
    "#2dd4bf", "#c084fc", "#86efac", "#fca5a5", "#67e8f9", "#d8b4fe",
    "#6ee7b7", "#fcd34d", "#93c5fd", "#f9a8d4", "#a5f3fc", "#bbf7d0",
]


def render(classified: pd.DataFrame):
    if classified.empty or "start_time" not in classified.columns:
        st.info("No timeline data available for the selected date range.")
        return

    timeline_data = classified[classified["start_time"].notna()].copy()

    if timeline_data.empty:
        st.info("No timeline data available — no views have a recorded start time.")
        return

    entity_options = ["All Entities"] + sorted(timeline_data["entity"].dropna().unique().tolist())
    selected_entity = st.selectbox("Filter by Entity", entity_options, key="timeline_entity")
    if selected_entity != "All Entities":
        timeline_data = timeline_data[timeline_data["entity"] == selected_entity]

    if timeline_data.empty:
        st.info("No timeline data for this entity.")
        return

    st.markdown("### 📊 View Run History (All Invocations)")

    now = pd.Timestamp.now(tz="UTC")
    timeline_data["end_display"] = timeline_data["end_time"].fillna(now)
    timeline_data["duration_display"] = timeline_data["duration_s"].apply(
        lambda x: f"{x:.1f}s" if pd.notna(x) else "running..."
    )

    # Sort models: entity then model name
    model_order = (
        timeline_data[["entity", "model_name"]]
        .drop_duplicates()
        .sort_values(["entity", "model_name"])["model_name"]
        .tolist()
    )

    # Assign a unique colour per model
    model_color = {m: _PALETTE[i % len(_PALETTE)] for i, m in enumerate(model_order)}

    fig = go.Figure()
    seen_models = set()

    for _, row in timeline_data.iterrows():
        model = row["model_name"]
        color = model_color[model]
        y_idx = model_order.index(model)

        fig.add_trace(go.Scatter(
            x=[row["start_time"], row["end_display"], row["end_display"], row["start_time"], row["start_time"]],
            y=[y_idx - 0.38, y_idx - 0.38, y_idx + 0.38, y_idx + 0.38, y_idx - 0.38],
            fill="toself",
            fillcolor=color,
            line=dict(width=0),
            mode="lines",
            name=model,
            legendgroup=model,
            showlegend=model not in seen_models,
            hovertemplate=(
                f"<b>{model}</b><br>"
                f"Entity: {row['entity']}<br>"
                f"Status: {row['final_status']}<br>"
                f"Duration: {row['duration_display']}<br>"
                f"Start: {row['start_time']}<extra></extra>"
            ),
        ))
        seen_models.add(model)

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0",
        height=max(300, len(model_order) * 24),
        xaxis_title="Time",
        yaxis=dict(
            tickmode="array",
            tickvals=list(range(len(model_order))),
            ticktext=model_order,
            title="",
        ),
        legend_title="View",
        margin=dict(l=180),
    )
    st.plotly_chart(fig, use_container_width=True)
