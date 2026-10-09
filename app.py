"""
Title: SMART-SIP+ Decision Support System Prototype

Version: 2.0

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""

import streamlit as st
from utils.footer import inject_footer

st.set_page_config(
    page_title="SMART-SIP+ DSS Prototype",
    page_icon="🌞",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": (
            "**SMART-SIP+ Decision Support System Prototype** v2.0\n\n"
            "Discription: Made for UKRI-funded project to reduce CO₂ emissions in rural Bangladesh "
            "by transitioning diesel irrigation infrastructure to solar power.\n\n"
            "MADE BY: VEDANT VARMA"
            "©Vedant Varma | All Rights Reserved\n\n"
        ),
    },
)

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Dark sidebar */
    [data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #30363d;
    }
    /* Monospace font for labels */
    .stMetric label {
        font-family: 'IBM Plex Mono', monospace !important;
        font-size: 0.7rem !important;
        color: #7d8590 !important;
    }
    /* Green metric delta */
    [data-testid="metric-container"] [data-testid="stMetricDelta"] {
        font-size: 0.7rem;
    }
    /* Tighten padding */
    .block-container { padding-top: 1.5rem !important; }
    /* Dataframe styling */
    [data-testid="stDataFrame"] { font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# ── Inject the Global Footer ───────────────────────────────────────────────────
inject_footer()

# ── Home page content ──────────────────────────────────────────────────────────
st.title("🌞 SMART-SIP+ Decision Support System")
st.markdown("""
**UKRI-funded · Birmingham City University, Department of Engineering**  
*Solar-powered Irrigation Transition for Bangladesh — Pathways to Net Zero Agriculture*
""")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("🌾 For Farmers & Investors")
    st.markdown("""
    Use the tools in this section to evaluate a specific site or investment:

    - **📍 Site Analyser** — Trace farm boundaries over GEE Sentinel-2 satellite imagery,
      inspect NDVI & elevation, and run hydraulic sizing
    - **₿ Business Case** — Interactive CAPEX/OPEX calculator: input your
      farm parameters, get payback period, NPV, and CO₂ savings
    - **⚡ Energy Model** — Visualise hourly solar generation vs. irrigation
      load, and see how surplus energy can power cold storage or EVs
    """)

with col2:
    st.subheader("🏛 For Policymakers & Planners")
    st.markdown("""
    Use these tools to analyse regional trends and simulate policy scenarios:

    - **🗺 Regional Map** — District-level GIS view of solar adoption,
      diesel pump density, GEE GHI, and aquifer vulnerability
    - **⟳ Scenario Simulator** — Model the national impact of different
      subsidy regimes, replacement rates, and technology integration targets
    - **⊞ PESTLE Analysis** — Socio-technical feasibility framework with
      scores across Political, Economic, Social, Technical, Legal, Environmental
    """)

st.divider()

col3, col4 = st.columns(2)
with col3:
    st.subheader("📡 Earth Engine Infrastructure")
    st.markdown("""
    - **☁ Climate & GEE** — Direct Google Earth Engine pipelines:
      ECMWF ERA5-Land climate, Sentinel-2 NDVI, SRTM 30m elevation, and JRC flood risk
    - **⟡ Data Pipeline** — ETL architecture overview, GEE job execution logs,
      and SQLite cache monitoring
    """)

with col4:
    st.subheader("ℹ️️ Quick Start")
    st.markdown("""
    1. Authenticate once: `earthengine authenticate`
    2. Create `.env` in the project root: `GEE_PROJECT_ID=<your-project>`
    3. Check the connection on the **🛰 GEE Test** page
    4. Start: `streamlit run app.py`

    If Earth Engine is unreachable, pages say so and fall back to a
    clearly-labelled placeholder - never silently.

    Navigate using the **sidebar pages** on the left →
    """)

st.divider()
st.caption(
    "SMART-SIP+ DSS Prototype v2.0 · "
    "Powered by Google Earth Engine · Streamlit · Python based GIS and Data analysis Tools"
)
