import streamlit as st

from sections.step_functions import render as render_step_functions


def render() -> None:
    """Render the Raw to Base section with Step Functions monitoring."""
    st.markdown("### Raw to Base")
    render_step_functions()
