"""Tab 4: Execution Timeline."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go


# Distinct palette for per-entity colouring
_PALETTE = [
    "#60a5fa", "#f472b6", "#34d399", "#fbbf24", "#a78bfa", "#fb923c",
    "#22d3ee", "#e879f9", "#4ade80", "#f87171", "#818cf8", "#facc15",
    "#2dd4bf", "#c084fc", "#86efac", "#fca5a5", "#67e8f9", "#d8b4fe",
    "#6ee7b7", "#fcd34d", "#93c5fd", "#f9a8d4", "#a5f3fc", "#bbf7d0",
]

_STATUS_COLOR = {
    "OK": "#4ade80",
    "pass": "#4ade80",
    "error": "#f87171",
    "skipped": "#fbbf24",
    "running": "#60a5fa",
    "unknown": "#94a3b8",
}


def _entity_status(statuses: pd.Series) -> str:
    """Derive a single status for an entity from its model statuses."""
    vals = statuses.dropna().tolist()
    if "error" in vals:
        return "error"
    if "running" in vals:
        return "running"
    if all(v in ("OK", "pass", "skipped") for v in vals) and vals:
        return "OK"
    return "unknown"


def render(classified: pd.DataFrame):
    if classified.empty or "start_time" not in classified.columns:
        st.info("No timeline data available for the selected date range.")
        return

    timeline_data = classified[classified["start_time"].notna()].copy()

    if timeline_data.empty:
        st.info("No timeline data available — no entities have a recorded start time.")
        return

    st.markdown("### 📊 View Run History (All Invocations)")

    now = pd.Timestamp.now(tz="UTC")

    # Aggregate to entity level: one row per (invocation_id, entity)
    def agg_entity(grp):
        status = _entity_status(grp["final_status"])
        end_vals = grp["end_time"].dropna()
        return pd.Series({
            "start_time": grp["start_time"].min(),
            "end_time": end_vals.max() if not end_vals.empty else pd.NaT,
            "final_status": status,
            "model_count": len(grp),
            "error_count": (grp["final_status"] == "error").sum(),
        })

    entity_df = (
        timeline_data
        .groupby(["invocation_id", "entity"], sort=False)
        .apply(agg_entity)
        .reset_index()
    )

    entity_df["end_display"] = entity_df["end_time"].fillna(now)
    entity_df["duration_s"] = (
        entity_df["end_display"] - entity_df["start_time"]
    ).dt.total_seconds()
    entity_df["duration_display"] = entity_df["duration_s"].apply(
        lambda x: f"{x:.0f}s" if pd.notna(x) else "running..."
    )

    # Sort entities alphabetically; each entity gets one Y slot
    entity_order = sorted(entity_df["entity"].dropna().unique().tolist())
    entity_color = {e: _PALETTE[i % len(_PALETTE)] for i, e in enumerate(entity_order)}

    fig = go.Figure()
    seen_entities = set()

    for _, row in entity_df.iterrows():
        entity = row["entity"]
        status = row["final_status"]
        color = _STATUS_COLOR.get(status, entity_color.get(entity, "#94a3b8"))
        y_idx = entity_order.index(entity)

        inv_short = str(row["invocation_id"])[:10]
        label = f"{entity} ({inv_short})"

        fig.add_trace(go.Scatter(
            x=[row["start_time"], row["end_display"], row["end_display"], row["start_time"], row["start_time"]],
            y=[y_idx - 0.38, y_idx - 0.38, y_idx + 0.38, y_idx + 0.38, y_idx - 0.38],
            fill="toself",
            fillcolor=color,
            opacity=0.85,
            line=dict(width=0),
            mode="lines",
            name=entity,
            legendgroup=entity,
            showlegend=entity not in seen_entities,
            hovertemplate=(
                f"<b>{entity}</b><br>"
                f"Invocation: {inv_short}<br>"
                f"Status: {status}<br>"
                f"Models: {int(row['model_count'])} ({int(row['error_count'])} errors)<br>"
                f"Duration: {row['duration_display']}<br>"
                f"Start: {row['start_time']}<extra></extra>"
            ),
        ))
        seen_entities.add(entity)

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#e0e0e0",
        height=max(300, len(entity_order) * 40),
        xaxis_title="Time",
        yaxis=dict(
            tickmode="array",
            tickvals=list(range(len(entity_order))),
            ticktext=entity_order,
            title="",
        ),
        legend_title="Entity",
        margin=dict(l=180),
    )
    st.plotly_chart(fig, use_container_width=True)
