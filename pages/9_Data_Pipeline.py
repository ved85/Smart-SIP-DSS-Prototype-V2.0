"""
Title: SMART-SIP+ DSS Prototype Data Pipeline Page.

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.db import load_pipeline_jobs, get_dashboard_kpis
from data.bangladesh_data import GEE_DATASETS
from utils.footer import inject_footer


st.set_page_config(page_title="Data Pipeline | SMART-SIP+", layout="wide")
inject_footer()

GREEN  = "#3fb950"; AMBER = "#d29922"; RED   = "#f85149"
TEAL   = "#39c5cf"; BLUE  = "#58a6ff"; PURPLE= "#bc8cff"
PAPER  = "#161b22"; PLOT  = "#0d1117"; GRID  = "#30363d"; TEXT = "#e6edf3"

def plotly_dark(fig):
    fig.update_layout(
        plot_bgcolor=PLOT, paper_bgcolor=PAPER,
        font=dict(color=TEXT, family="IBM Plex Mono, monospace", size=11),
        margin=dict(l=10, r=10, t=30, b=10),
    )
    return fig

st.title("⟡ Data Pipeline")
st.caption("ETL architecture · live job log from SQLite · data quality from real cache")

# ── Pipeline architecture Sankey ──────────────────────────────────────────────
st.subheader("Data Flow Architecture")
label = [
    "GEE ERA5 (GHI/Temp)", "GEE Sentinel-2 (NDVI)", "GEE SRTM (Elevation)",
    "GEE JRC GSW (Flood)", "GEE MODIS (Land Cover)", "BADC Survey DB (not connected)",
    "OSM / Admin Boundaries (search only)",
    "GEE Python API\n(earthengine-api)",
    "GeoData Loader\n(GeoPandas / Fiona)",
    "Climate Processor\n(pandas / pvlib)", "Spatial Processor\n(GeoPandas / Shapely)",
    "Techno-Econ Engine\n(NumPy / SciPy)",
    "SQLite Cache\n(data/smartsip.db)",
    "Farmer DSS\n(Streamlit)", "Policy DSS\n(Plotly Dash)",
]
source = [0,1,2,3,4,  5,6,  7,7,8,  9,10,11,  12,12]
target = [7,7,7,7,7,  8,8,  9,10,9, 11,11,12,  13,14]
value  = [5,5,3,3,3,  4,2,  5,4,4,   4,4,5,     5,4]
colours= [
    "rgba(63,185,80,.4)","rgba(57,197,207,.4)","rgba(88,166,255,.4)",
    "rgba(248,81,73,.3)","rgba(210,153,34,.3)",
    "rgba(88,166,255,.3)","rgba(88,166,255,.3)",
    "rgba(57,197,207,.5)","rgba(57,197,207,.4)",
    "rgba(210,153,34,.5)","rgba(210,153,34,.5)",
    "rgba(210,153,34,.5)",
    "rgba(63,185,80,.6)","rgba(63,185,80,.6)","rgba(57,197,207,.6)",
]
fig_sankey = go.Figure(go.Sankey(
    node=dict(
        pad=20, thickness=20,
        line=dict(color=GRID, width=0.5),
        label=label,
        color=[GREEN,TEAL,BLUE,RED,AMBER, BLUE,BLUE,
               TEAL,BLUE,
               AMBER,AMBER,AMBER, PURPLE, GREEN,TEAL],
    ),
    link=dict(source=source, target=target, value=value, color=colours),
))
fig_sankey.update_layout(
    paper_bgcolor=PAPER,
    font=dict(color=TEXT, family="IBM Plex Mono, monospace", size=10),
    height=420, margin=dict(l=10,r=10,t=10,b=10),
)
st.plotly_chart(fig_sankey, use_container_width=True)
st.divider()

# ── Live job monitor from SQLite ───────────────────────────────────────────────
col_jobs, col_stack = st.columns(2)

with col_jobs:
    st.subheader("Pipeline Job Monitor — Live (SQLite)")
    jobs_df = load_pipeline_jobs(limit=30)

    if jobs_df.empty:
        st.info(
            "No jobs logged yet.\n\n"
            "Jobs are recorded automatically when you:\n"
            "- Fetch ERA5-Land climate (Business Case, Site Analyser or Climate & GEE page)\n"
            "- Run a GEE query\n"
            "- Save a Business Case"
        )
    else:
        def _icon(s):
            return {"ok":"🟢 OK","running":"🔵 Running","error":"❌ Error"}.get(s, f"⚠️ {s}")
        jobs_df["Status"]   = jobs_df["status"].map(_icon)
        jobs_df["Duration"] = jobs_df["duration_s"].apply(
            lambda x: f"{x:.1f}s" if pd.notna(x) else "—")
        jobs_df["Records"]  = jobs_df["records"].apply(
            lambda x: f"{int(x):,}" if pd.notna(x) else "—")

        st.dataframe(
            jobs_df[["job_name","job_type","schedule","started_at",
                     "Duration","Records","Status","error_msg"]].rename(columns={
                "job_name":"Job","job_type":"Type","schedule":"Schedule",
                "started_at":"Started","error_msg":"Error"}),
            use_container_width=True, hide_index=True, height=340
        )
        ok   = (jobs_df["status"] == "ok").sum()
        warn = (jobs_df["status"].isin(["stale","warning"])).sum()
        err  = (jobs_df["status"] == "error").sum()
        run  = (jobs_df["status"] == "running").sum()
        st.markdown(
            f"**Pipeline health:** 🟢 {ok} OK &nbsp;|&nbsp; "
            f"❌ {err} error &nbsp;|&nbsp; 🔵 {run} running",
            unsafe_allow_html=True)

with col_stack:
    st.subheader("Technology Stack")
    stack = {
        "🌍 Geospatial": [
            ("GeoPandas",       "0.14.4", "Core spatial dataframes"),
            ("Shapely",         "2.0.4",  "Geometry operations"),
            ("Fiona",           "1.9.x",  "Shapefile / GeoJSON I/O"),
            ("PyProj",          "3.6.1",  "CRS transformations"),
            ("Rasterio",        "1.3.x",  "Raster / satellite data I/O"),
            ("earthengine-api", "0.1.404","GEE (auth via CLI, no key file)"),
            ("geemap",          "0.32.1", "GEE interactive mapping"),
            ("Folium",          "0.16.0", "Leaflet.js maps — free CARTO tiles"),
        ],
        "📊 Data & Modelling": [
            ("pandas",   "2.2.2",  "Tabular data"),
            ("NumPy",    "1.26.4", "Numerical computation"),
            ("SciPy",    "1.13.1", "IRR / optimisation"),
            ("pvlib",    "0.10.5", "Solar energy modelling"),
            ("ERA5/GEE", "ECMWF/ERA5/DAILY", "GHI + temperature via GEE"),
        ],
        "🗄 Storage": [
            ("SQLite",   "built-in","Live job log, climate cache, GEE results"),
            ("PostGIS",  "3.x",     "Production spatial DB (optional)"),
            ("GeoJSON",  "spec",    "Geometry interchange"),
            ("dotenv",   "1.0.1",   "APP_MODE env var only"),
        ],
        "📈 Visualisation": [
            ("Plotly",          "5.22.0","Interactive charts + Sankey"),
            ("Streamlit",       "1.35.0","Multi-page DSS framework"),
            ("streamlit-folium","0.20.0","Folium maps in Streamlit"),
        ],
    }
    for category, libs in stack.items():
        with st.expander(category, expanded=True):
            st.dataframe(
                pd.DataFrame(libs, columns=["Library","Version","Purpose"]),
                use_container_width=True, hide_index=True)

# ── SQLite data quality dashboard ─────────────────────────────────────────────
st.divider()
st.subheader("SQLite Data Quality")

kpis = get_dashboard_kpis()
qc1, qc2, qc3, qc4 = st.columns(4)
qc1.metric("Climate rows cached",  f"{kpis['climate_rows_cached']:,}")
qc2.metric("GEE results stored",   f"{kpis['gee_queries_stored']}")
qc3.metric("Business cases saved", f"{kpis['n_business_cases']}")
qc4.metric("Pipeline jobs logged", f"{kpis['pipeline_jobs_ok']} OK")

# ── GEE auth info ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("GEE Authentication — No Key File Needed")
st.code("""# One-time setup (run in your terminal):
earthengine authenticate

# This stores credentials at:
# ~/.config/earthengine/credentials

# Then in Python (no .env, no service account JSON):
import ee
ee.Initialize()   # picks up credentials automatically
""", language="bash")

st.subheader("Example GEE Integration Code")
st.code("""import ee

# Initialise using credentials from `earthengine authenticate`
ee.Initialize()

def get_ndvi(lat: float, lon: float, date: str) -> float:
    point = ee.Geometry.Point(lon, lat)
    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(point)
        .filterDate(date, ee.Date(date).advance(30, "day"))
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
        .first()
    )
    nir  = s2.select("B8")
    red  = s2.select("B4")
    ndvi = nir.subtract(red).divide(nir.add(red))
    val  = ndvi.reduceRegion(ee.Reducer.median(), point, 10).getInfo()
    return round(val["B8"], 3)

def get_elevation(lat: float, lon: float) -> float:
    point = ee.Geometry.Point(lon, lat)
    dem   = ee.Image("USGS/SRTMGL1_003")
    elev  = dem.reduceRegion(ee.Reducer.mean(), point, 30).getInfo()
    return round(elev["elevation"], 1)

def get_flood_risk(lat: float, lon: float) -> float:
    # JRC Global Surface Water occurrence layer
    point = ee.Geometry.Point(lon, lat)
    gsw = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence")
    val = gsw.reduceRegion(ee.Reducer.mean(), point.buffer(500), 30).getInfo()
    return round((val["occurrence"] or 0) / 100, 3)
""", language="python")

st.subheader("GEE ERA5 — Daily GHI & Temperature")
st.code("""import ee
ee.Initialize(project="dsstestv5")

point = ee.Geometry.Point(89.55, 22.84)

era5 = (ee.ImageCollection("ECMWF/ERA5/DAILY")
        .filterBounds(point)
        .filterDate("2024-01-01", "2024-12-31")
        .select(["surface_solar_radiation_downwards",
                 "mean_2m_air_temperature"]))

def extract(img):
    d = img.reduceRegion(ee.Reducer.mean(), point, 27830)
    return ee.Feature(None, {
        "date": img.date().format("YYYY-MM-dd"),
        "ghi":  ee.Number(d.get("surface_solar_radiation_downwards"))
                  .divide(3_600_000),   # J/m² → kWh/m²
        "temp": ee.Number(d.get("mean_2m_air_temperature"))
                  .subtract(273.15),    # K → °C
    })

rows = era5.map(extract).getInfo()["features"]
# → rows[i]["properties"] = {"date": "2024-01-01", "ghi": 4.7, "temp": 18.2}
""", language="python")