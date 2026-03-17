import streamlit as st
from datetime import datetime, timedelta

from streamlit_autorefresh import st_autorefresh
from sections.step_functions import render_step_functions
from sections.glue_job import render_glue_job


def _render_shared_controls():
    """Render shared date/time range controls and auto-refresh selector.

    Returns (start_date, start_time, end_date, end_time, auto_refresh).
    """
    _local_tz = datetime.now().astimezone().tzinfo
    _now_local = datetime.now(_local_tz)
    _default_from_time = (_now_local - timedelta(minutes=60)).time().replace(second=0, microsecond=0)
    _default_to_time = _now_local.time().replace(second=0, microsecond=0)
    _default_date = _now_local.date()

    # Effective end time — updated by auto-refresh without touching widget state
    if "r2b_effective_to_time" not in st.session_state:
        st.session_state.r2b_effective_to_time = _default_to_time
    if "r2b_effective_to_date" not in st.session_state:
        st.session_state.r2b_effective_to_date = _default_date

    # Resolve refresh interval early so widgets can use it
    refresh_seconds_map = {"Off": 0, "30s": 30, "1m": 60, "5m": 300}
    _current_auto_refresh = st.session_state.get("r2b_auto_refresh", "Off")
    refresh_interval_s = refresh_seconds_map.get(_current_auto_refresh, 0)

    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([2.5, 1, 1, 1.5])

    with ctrl_col1:
        date_range = st.date_input(
            "Date Range",
            value=(_default_date, _default_date),
            key="r2b_date_range",
        )
    with ctrl_col2:
        from_time = st.time_input(
            "From Time",
            value=_default_from_time,
            key="r2b_from_time",
        )
    with ctrl_col3:
        if refresh_interval_s > 0:
            st.markdown(
                '<div style="margin-top:4px"><label style="font-size:14px;color:#a0a0b0">To Time</label></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="padding:6px 0;font-size:15px">🔄 {st.session_state.r2b_effective_to_time.strftime("%H:%M")}</div>',
                unsafe_allow_html=True,
            )
            to_time = st.session_state.r2b_effective_to_time
        else:
            to_time = st.time_input(
                "To Time",
                value=_default_to_time,
                key="r2b_to_time",
            )
    with ctrl_col4:
        auto_refresh = st.selectbox(
            "Auto Refresh",
            ["Off", "30s", "1m", "5m"],
            index=0,
            key="r2b_auto_refresh",
        )

    # Auto-refresh (JS-based timer via sidebar to avoid layout shift)
    refresh_interval_s = refresh_seconds_map.get(auto_refresh, 0)
    if refresh_interval_s > 0:
        with st.sidebar:
            st_autorefresh(interval=refresh_interval_s * 1000, key="r2b_auto_refresh_timer")
        # Update effective end time on auto-refresh
        _now_local = datetime.now(_local_tz)
        st.session_state.r2b_effective_to_time = _now_local.time().replace(second=0, microsecond=0)
        st.session_state.r2b_effective_to_date = _now_local.date()

    # Resolve date range (handle partial selection)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = _default_date

    return start_date, from_time, end_date, to_time, auto_refresh


def render() -> None:
    """Render the Raw to Base section with sub-tabs for Step Functions and Glue Job."""
    st.markdown("### Raw to Base")

    # Shared date/time controls above the sub-tabs
    start_date, start_time, end_date, end_time, auto_refresh = _render_shared_controls()

    # Sub-tabs
    tab_sfn, tab_glue = st.tabs(["Step Functions", "Glue Job"])

    with tab_sfn:
        render_step_functions(start_date, start_time, end_date, end_time, auto_refresh)

    with tab_glue:
        render_glue_job(start_date, start_time, end_date, end_time, auto_refresh)
