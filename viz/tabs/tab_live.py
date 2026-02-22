"""Tab 1: Live / In Progress models."""

import streamlit as st
import pandas as pd


def render(classified: pd.DataFrame):
    if classified.empty or "final_status" not in classified.columns:
        st.info("No data available for live monitoring. Enable auto-refresh (10s or 30s) to track a running execution.")
        return

    running = classified[classified["final_status"] == "running"]
    if running.empty:
        st.info("No views currently in progress. All views have completed. "
                "To monitor a new run, enable auto-refresh before starting the Step Function.")
        return

    st.markdown(f"### 🔄 {len(running)} View(s) Currently Running")
    for entity_name, entity_group in running.groupby("entity"):
        with st.expander(f"🏷️ {entity_name} — {len(entity_group)} view(s)", expanded=False):
            for _, row in entity_group.iterrows():
                elapsed = (pd.Timestamp.now(tz="UTC") - row["start_time"]).total_seconds() if pd.notna(row["start_time"]) else 0
                c1, c2, c3 = st.columns([3, 2, 1])
                c1.markdown(f"**View:** `{row['model_name']}`")
                c2.markdown(f"**Started:** {row['start_time'].strftime('%H:%M:%S') if pd.notna(row['start_time']) else 'N/A'}")
                c3.markdown(f"**Thread:** `{row['thread']}`")
                st.progress(min(elapsed / 120, 1.0), text=f"Running ~{elapsed:.0f}s")
                st.divider()
