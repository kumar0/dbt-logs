"""Base to Prepared section with sub-tab navigation.

Mirrors the Raw to Base pattern: shared date/time controls above two sub-tabs
(Step Functions and dbt Monitor).
"""

import streamlit as st
from datetime import datetime, timedelta

from streamlit_autorefresh import st_autorefresh
from sections.b2p_step_functions import render_b2p_step_functions
from sections.b2p_dbt_monitor import render_b2p_dbt_monitor


def _render_shared_controls():
    """Render shared date/time range controls and auto-refresh selector.

    Uses session state keys prefixed with 'b2p_' to avoid conflicts.
    Returns (start_date, start_time, end_date, end_time, auto_refresh).
    """
    _local_tz = datetime.now().astimezone().tzinfo
    _now_local = datetime.now(_local_tz)
    _default_from_time = (_now_local - timedelta(minutes=60)).time().replace(second=0, microsecond=0)
    _default_to_time = _now_local.time().replace(second=0, microsecond=0)
    _default_date = _now_local.date()

    # Effective end time — updated by auto-refresh without touching widget state
    if "b2p_effective_to_time" not in st.session_state:
        st.session_state.b2p_effective_to_time = _default_to_time
    if "b2p_effective_to_date" not in st.session_state:
        st.session_state.b2p_effective_to_date = _default_date

    # Resolve refresh interval early so widgets can use it
    refresh_seconds_map = {"Off": 0, "10s": 10, "30s": 30, "1m": 60, "5m": 300, "10m": 600}
    _current_auto_refresh = st.session_state.get("b2p_auto_refresh", "Off")
    refresh_interval_s = refresh_seconds_map.get(_current_auto_refresh, 0)

    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([2.5, 1, 1, 1.5])

    with ctrl_col1:
        date_range = st.date_input(
            "Date Range",
            value=(_default_date, _default_date),
            key="b2p_date_range",
        )
    with ctrl_col2:
        from_time = st.time_input(
            "From Time",
            value=_default_from_time,
            key="b2p_from_time",
        )
    with ctrl_col3:
        if refresh_interval_s > 0:
            st.markdown(
                '<div style="margin-top:4px"><label style="font-size:14px;color:#a0a0b0">To Time</label></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="padding:6px 0;font-size:15px">🔄 {st.session_state.b2p_effective_to_time.strftime("%H:%M")}</div>',
                unsafe_allow_html=True,
            )
            to_time = st.session_state.b2p_effective_to_time
        else:
            to_time = st.time_input(
                "To Time",
                value=_default_to_time,
                key="b2p_to_time",
            )
    with ctrl_col4:
        auto_refresh = st.selectbox(
            "Auto Refresh",
            ["Off", "10s", "30s", "1m", "5m", "10m"],
            index=0,
            key="b2p_auto_refresh",
        )

    # Auto-refresh (JS-based timer via sidebar to avoid layout shift)
    refresh_interval_s = refresh_seconds_map.get(auto_refresh, 0)
    if refresh_interval_s > 0:
        with st.sidebar:
            st_autorefresh(interval=refresh_interval_s * 1000, key="b2p_auto_refresh_timer")
        # Update effective end time on auto-refresh
        _now_local = datetime.now(_local_tz)
        st.session_state.b2p_effective_to_time = _now_local.time().replace(second=0, microsecond=0)
        st.session_state.b2p_effective_to_date = _now_local.date()

    # Resolve date range (handle partial selection)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = _default_date

    return start_date, from_time, end_date, to_time, auto_refresh


def render() -> None:
    """Render the Base to Prepared section with sub-tabs."""
    st.markdown("### Base to Prepared")

    # Shared date/time controls above the sub-tabs
    start_date, start_time, end_date, end_time, auto_refresh = _render_shared_controls()

    # Sub-tabs
    tab_sfn, tab_dbt = st.tabs(["Step Functions", "dbt Monitor"])

    with tab_sfn:
        render_b2p_step_functions(start_date, start_time, end_date, end_time, auto_refresh)

    with tab_dbt:
        render_b2p_dbt_monitor(start_date, start_time, end_date, end_time, auto_refresh)
