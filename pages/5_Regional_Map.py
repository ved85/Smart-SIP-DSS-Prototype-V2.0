"""
Title: SMART-SIP+ DSS Prototype Regional Map (Policymaker View) Page.

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from streamlit_folium import st_folium
from utils.maps import build_regional_map, TILE_OPTIONS
from data.bangladesh_data import DISTRICTS, DISTRICTS_SOURCE
from utils.climate import district_climate_table, gee_status
import numpy as np
from utils.footer import inject_footer


st.set_page_config(page_title="Regional Map | SMART-SIP+", layout="wide")
inject_footer()
GREEN = "#3fb950"; AMBER = "#d29922"; RED = "#f85149"
TEAL  = "#39c5cf"; BLUE  = "#58a6ff"
PAPER = "#161b22"; PLOT  = "#0d1117"; GRID = "#30363d"; TEXT = "#e6edf3"

def plotly_dark(fig):
    fig.update_layout(
        plot_bgcolor=PLOT, paper_bgcolor=PAPER,
        font=dict(color=TEXT, family="IBM Plex Mono, monospace", size=11),
        xaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
        yaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
        margin=dict(l=10, r=10, t=30, b=10),
    )
    return fig

st.title("🗺 Regional Overview")
st.caption("Macro-level geospatial analysis · District GIS data · Aquifer vulnerability layer")

# District GHI: ERA5-Land where fetched/cached, otherwise the table value
if "reg_ghi" not in st.session_state:
    st.session_state["reg_ghi"] = district_climate_table(allow_fetch=False)
_live = st.session_state["reg_ghi"].set_index("district")["ghi_live"]
_D = DISTRICTS.copy()
_has_live = bool(_live.notna().any())
if _has_live:
    _D["ghi"] = _D["district"].map(_live).fillna(_D["ghi"])
DISTRICTS = _D
GHI_LABEL = "GHI (ERA5-Land)" if _has_live else "GHI (placeholder)"

st.warning(f"District attributes (solar adoption, pump counts, groundwater, aquifer risk, priority) come from: "
           f"**{DISTRICTS_SOURCE}**. Do not cite them as survey data. Add `data/districts.csv` to replace them.")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Districts in dataset", f"{len(DISTRICTS)}", help="Only the districts present in the data table are mapped.")
k2.metric("Diesel pumps (table)", f"{DISTRICTS['diesel_pumps'].sum() / 1e6:.2f}M")
k3.metric("Mean " + GHI_LABEL, f"{DISTRICTS['ghi'].mean():.2f} kWh/m²/d")
k4.metric("High aquifer risk", f"{(DISTRICTS['aquifer_risk'] == 'High').sum()} districts")
k5.metric("High-priority districts", f"{(DISTRICTS['priority'] == 'High').sum()}")

st.divider()

col_ctrl, col_map = st.columns([1, 3])

with col_ctrl:
    st.subheader("Map Layer")
    tile_choice = st.selectbox("Map type", list(TILE_OPTIONS.keys()))
    metric = st.radio("Visualise by:", [
        ("Solar Adoption (%)",      "solar_pct"),
        ("Diesel Pump Density",     "diesel_pumps"),
        ("Solar Irradiance (GHI)",  "ghi"),
        ("Subsidy Priority",        "priority"),
        ("Aquifer Vulnerability",   "aquifer_risk"),
    ], format_func=lambda x: x[0])
    metric_key = metric[1]

    if st.button("🛰 Fetch ERA5-Land GHI for all districts"):
        with st.spinner("Querying Earth Engine (cached afterwards)…"):
            st.session_state["reg_ghi"] = district_climate_table(allow_fetch=True)
        if st.session_state["reg_ghi"]["ghi_live"].isna().all():
            st.error(f"Earth Engine unavailable: {gee_status()['err']}")
        st.rerun()
    st.caption("GHI source: " + ("ERA5-Land (live/cached)" if _has_live else "placeholder table"))

    st.divider()
    div_filter = st.multiselect("Division", options=sorted(DISTRICTS["division"].unique()))
    priority_filter = st.multiselect("Priority Level", ["Low","Medium","High"])
    aq_filter = st.multiselect("Aquifer Risk", ["Low","Medium","High"])

with col_map:
    st.subheader("District-level Map")
    
    rmap = build_regional_map(
        metric=metric_key, 
        tile_choice=tile_choice,
        lat=23.8,
        lon=89.9,
        zoom=7,
        df=DISTRICTS, ghi_label=GHI_LABEL
    )
    
    # Restricting returned_objects stops the map from firing a Streamlit rerun
    # every time the user pans or zooms, fixing the stuttering/resetting bug.
    map_data = st_folium(rmap, width="100%", height=440, key="regional_map", 
                         returned_objects=["last_object_clicked"])

st.divider()
col_l, col_r = st.columns(2)

with col_l:
    st.subheader("District Comparison Table")
    display = DISTRICTS[["district","division","diesel_pumps","solar_pct","ghi",
                          "gw_depth_m","gw_trend","aquifer_risk","priority","crop_zone"]].copy()
    display.columns = ["District","Division","Diesel Pumps","Solar %","GHI",
                       "GW Depth (m)","GW Trend","Aquifer Risk","Priority","Crop Zone"]
    filt = display.copy()
    if div_filter:
        filt = filt[filt["Division"].isin(div_filter)]
    if priority_filter:
        filt = filt[filt["Priority"].isin(priority_filter)]
    if aq_filter:
        filt = filt[filt["Aquifer Risk"].isin(aq_filter)]
    st.dataframe(filt.sort_values("Solar %", ascending=False),
                 use_container_width=True, hide_index=True, height=360)

with col_r:
    st.subheader("Aquifer Risk vs Solar Adoption")
    aq_colours = {"High": RED, "Medium": AMBER, "Low": GREEN}
    fig_aq = go.Figure()
    for risk in ["High", "Medium", "Low"]:
        df_r = DISTRICTS[DISTRICTS["aquifer_risk"] == risk]
        fig_aq.add_trace(go.Scatter(
            x=df_r["gw_depth_m"], y=df_r["solar_pct"],
            mode="markers+text",
            name=f"{risk} risk",
            marker=dict(color=aq_colours[risk], size=14,
                        line=dict(color="white", width=0.5)),
            text=df_r["district"],
            textposition="top center",
        ))
    fig_aq.update_layout(
        xaxis_title="Groundwater Depth (m)",
        yaxis_title="Solar Adoption (%)",
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    st.plotly_chart(plotly_dark(fig_aq), use_container_width=True)
    st.caption("High aquifer-risk districts often also have high solar adoption — confirming that over-extraction is already occurring.")

# ── Solar adoption vs GHI scatter ─────────────────────────────────────────────
st.subheader("Solar Adoption vs GHI by District (bubble = diesel pump count)")
priority_colours = {"Low": GREEN, "Medium": AMBER, "High": RED}
fig_sc = go.Figure()
for pri in ["Low", "Medium", "High"]:
    df_p = DISTRICTS[DISTRICTS["priority"] == pri]
    fig_sc.add_trace(go.Scatter(
        x=df_p["ghi"], y=df_p["solar_pct"],
        mode="markers+text", name=f"{pri} priority",
        marker=dict(color=priority_colours[pri],
                    size=df_p["diesel_pumps"] / 8000, sizemin=8,
                    line=dict(color="white", width=0.5)),
        text=df_p["district"], textposition="top center",
    ))
fig_sc.update_layout(
    xaxis_title="Annual GHI (kWh/m²/day)",
    yaxis_title="Solar Adoption (%)",
    legend=dict(bgcolor="rgba(0,0,0,0)"),
)
st.plotly_chart(plotly_dark(fig_sc), use_container_width=True)
st.caption("Bubble size = diesel pump count. Top-left quadrant (high GHI, low adoption) = highest-value intervention targets.")

# ── Systemic barriers ────────────────────────────────────────────────────────
st.subheader("Systemic barriers (illustrative scores - replace with survey data)")
barriers = ["Finance access","Local maintenance","Flood risk",
            "Land tenure","Grid connection","Digital literacy"]
scores   = [7.8, 6.4, 5.9, 5.2, 4.8, 6.1]
colours  = [RED if s > 7 else AMBER if s > 5.5 else GREEN for s in scores]
fig_b = go.Figure(go.Bar(
    x=scores, y=barriers, orientation="h",
    marker=dict(color=colours),
    text=[str(s) for s in scores], textposition="outside",
))
fig_b.update_layout(xaxis=dict(range=[0,10], title="Severity score"), showlegend=False)
st.plotly_chart(plotly_dark(fig_b), use_container_width=True)