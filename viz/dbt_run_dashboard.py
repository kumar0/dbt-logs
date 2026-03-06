import streamlit as st

from sections import render_base_to_prepared, render_raw_to_base, render_notification

st.set_page_config(page_title="Data Flow Monitor", page_icon="🔄", layout="wide")

# --- Navigation sections ---
SECTIONS = ["Raw to Base", "Base to Prepared", "Notification"]

# --- Initialise session state ---
if "last_fetch_ts" not in st.session_state:
    st.session_state.last_fetch_ts = None
if "df_raw" not in st.session_state:
    st.session_state.df_raw = None
if "glue_raw" not in st.session_state:
    st.session_state.glue_raw = None
if "fetch_requested" not in st.session_state:
    st.session_state.fetch_requested = False
if "run_just_completed" not in st.session_state:
    st.session_state.run_just_completed = False
if "glue_metrics_enabled" not in st.session_state:
    st.session_state.glue_metrics_enabled = False

# --- Custom CSS ---
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%);
        border-radius: 10px; padding: 12px 16px; text-align: center;
        border: 1px solid #3d3d5c; margin-bottom: 6px;
    }
    .metric-card h2 { color: #e0e0e0; font-size: 12px; margin: 0; text-transform: uppercase; letter-spacing: 1px; }
    .metric-card h1 { color: #ffffff; font-size: 26px; margin: 3px 0 0 0; }
    .status-ok { color: #4ade80; }
    .status-error { color: #f87171; }
    .status-skip { color: #fbbf24; }
    .status-running { color: #60a5fa; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e1e2e; border-radius: 8px 8px 0 0;
        padding: 10px 20px; color: #a0a0b0; border: 1px solid #3d3d5c;
    }
    .stTabs [aria-selected="true"] { background-color: #2d2d44; color: #ffffff; }
    iframe[title="streamlit_autorefresh.st_autorefresh"],
    .element-container:has(iframe[title="streamlit_autorefresh.st_autorefresh"]),
    [data-testid="stComponentFrame"]:has(iframe[title*="autorefresh"]) {
        height: 0 !important; min-height: 0 !important; max-height: 0 !important;
        overflow: hidden !important; margin: 0 !important; padding: 0 !important;
        border: none !important;
    }
    div[data-baseweb="select"] input { pointer-events: none !important; }
</style>
""", unsafe_allow_html=True)

# --- Sidebar navigation ---
with st.sidebar:
    active_section = st.radio(
        "Navigation",
        SECTIONS,
        index=1,  # Default: Base to Prepared
        key="nav_section",
    )

# --- Section routing ---
SECTION_RENDERERS = {
    "Raw to Base": render_raw_to_base,
    "Base to Prepared": render_base_to_prepared,
    "Notification": render_notification,
}

SECTION_RENDERERS[active_section]()
