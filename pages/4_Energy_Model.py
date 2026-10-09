"""
Title: SMART-SIP+ DSS Prototype Energy Flow Model Page

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""
import os
import sys

import numpy as np
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.footer import inject_footer

st.set_page_config(page_title="Energy Model | SMART-SIP+", layout="wide")
inject_footer()

from data.bangladesh_data import CROP_ETC, DISTRICTS, to_hectares
from models.techno_economic import (CELL_TEMP_RISE, INVERTER_EFF, MONTHS, SYSTEM_EFF, auto_design,
                                    cell_temperature, temp_derate)
from utils.climate import climate_panel, day_length_h, hourly_profile
from utils.db import load_parcels

GREEN, AMBER, RED, TEAL, BLUE = "#3fb950", "#d29922", "#f85149", "#39c5cf", "#58a6ff"
PAPER, PLOT, GRID, TEXT = "#161b22", "#0d1117", "#30363d", "#e6edf3"


def dark(fig, h=340):
    fig.update_layout(plot_bgcolor=PLOT, paper_bgcolor=PAPER, height=h,
                      font=dict(color=TEXT, family="IBM Plex Mono, monospace", size=11),
                      xaxis=dict(gridcolor=GRID, zerolinecolor=GRID), yaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
                      margin=dict(l=10, r=10, t=30, b=10), legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.2))
    return fig


st.title("⚡ Energy Flow Model")
st.caption("Hourly solar vs load for one month · ERA5-Land irradiance & temperature · real daylight window · surplus routing")

with st.sidebar:
    st.header("Site")
    parcels = load_parcels()
    opts = {0: "— District centroid —"}
    for _, p in parcels.iterrows():
        opts[int(p["id"])] = f"{p['name']} ({p['area_ha']:.2f} ha)"
    sel = st.selectbox("Parcel", list(opts), format_func=lambda k: opts[k])
    P = parcels[parcels["id"] == sel].iloc[0] if sel else None
    dists = sorted(DISTRICTS["district"])
    district = st.selectbox("District", dists, index=dists.index(P["district"]) if P is not None and P["district"] in dists else 0, key=f"em_d_{sel}")
    drow = DISTRICTS[DISTRICTS["district"] == district].iloc[0]
    lat, lon = (float(P["lat_centroid"]), float(P["lon_centroid"])) if P is not None else (float(drow["lat"]), float(drow["lon"]))
    clim = climate_panel(lat, lon, key="em")

    st.header("Crop & pump")
    crops = list(CROP_ETC)
    crop = st.selectbox("Crop", crops, index=crops.index(P["crop_type"]) if P is not None and P["crop_type"] in crops else 0, key=f"em_c_{sel}")
    planting = MONTHS.index(st.selectbox("Planting month", MONTHS, index=CROP_ETC[crop]["plant_month"] - 1, key=f"em_pm_{crop}")) + 1
    unit = st.selectbox("Area unit", ["hectares", "acres", "bigha"])
    a_def = float(P["area_ha"]) if P is not None else 2.0
    area_ha = to_hectares(st.number_input(f"Area ({unit})", 0.01, 500.0, round(a_def / to_hectares(1, unit), 3), 0.1, key=f"em_a_{sel}_{unit}"), unit)
    gw = st.slider("Static water level (m)", 1.0, 30.0, float(drow["gw_depth_m"]), 0.5)
    eff_irr = {"Flood": 0.60, "Sprinkler": 0.75, "Drip": 0.90}[st.selectbox("Irrigation method", ["Flood", "Sprinkler", "Drip"])]
    window = st.slider("Pumping window (h)", 4, 10, 8)
    wb, hyd = auto_design(crop, area_ha, planting, clim, gw, irr_eff=eff_irr, pump_hours=window)
    pump_kw, panel_kwp = hyd.power_kw, hyd.panel_kwp
    if st.checkbox("Override pump / PV size"):
        pump_kw = st.slider("Pump (kW)", 0.3, 30.0, float(max(0.3, round(pump_kw, 1))), 0.1)
        panel_kwp = st.slider("PV (kWp)", 0.5, 60.0, float(max(0.5, round(panel_kwp, 1))), 0.1)

    st.header("Month & loads")
    month = MONTHS.index(st.selectbox("Month to simulate", MONTHS, index=wb["peak_month"])) + 1
    start = st.slider("Pumping start hour", 5, 11, 8)
    cold_w = st.slider("Cold storage (W)", 0, 3000, 0, 100)
    n_er = st.slider("E-rickshaw chargers (48V/100Ah)", 0, 10, 0)
    ph_kw = st.slider("Post-harvest machinery (kW)", 0.0, 5.0, 0.0, 0.5)

mi = month - 1
tcell = float(cell_temperature(clim["tmean"][mi], clim["tmax"][mi]))
derate = float(temp_derate(tcell))
ghi_m = float(clim["ghi"][mi])
hours = list(range(24))
irr_pv = hourly_profile(ghi_m, lat, month)                                    # kWh/m² per hour
gen = irr_pv * panel_kwp * derate * SYSTEM_EFF * INVERTER_EFF                 # kW

tdh = hyd.tdh_m
flow_cap = pump_kw * 0.60 * 3600 / (9.81 * tdh)                              # m³/h at rated kW (η 0.60)
vol_day = wb["daily_gross_mm"][mi] * area_ha * 10 * 1.10                      # m³/day this month
need_h = vol_day / max(flow_cap, 1e-6)
run_h = min(float(window), need_h)
irr_load = np.array([pump_kw * min(1.0, max(0.0, run_h - (h - start))) if h >= start else 0.0 for h in hours])
cold_load = np.full(24, cold_w / 1000)
er_kw = n_er * 0.6
er_load = np.array([er_kw if 7 <= h <= 22 else 0.0 for h in hours])
ph_load = np.array([ph_kw if 8 <= h <= 17 else 0.0 for h in hours])
total = irr_load + cold_load + er_load + ph_load
surplus = np.maximum(0, gen - total)
deficit = np.maximum(0, total - gen)

if clim.get("source") != "gee_era5_land":
    st.error("⚠️ Climate is a static placeholder, not Earth Engine data.")
if need_h > window + 0.05:
    st.warning(f"{MONTHS[mi]} needs {need_h:.1f} h/day of pumping at this pump size; window is {window} h.")
elif vol_day == 0:
    st.info(f"No irrigation needed in {MONTHS[mi]} for this crop calendar (rain / off-season).")

k = st.columns(5)
k[0].metric("Daylight", f"{day_length_h(lat, month):.1f} h")
k[1].metric("GHI · cell temp", f"{ghi_m:.2f} kWh/m²/d · {tcell:.0f} °C", delta=f"temp derate −{(1 - derate) * 100:.1f}%", delta_color="inverse")
k[2].metric("PV generation", f"{gen.sum():.1f} kWh/day")
k[3].metric("Pump energy", f"{irr_load.sum():.1f} kWh/day")
k[4].metric("Surplus", f"{surplus.sum():.1f} kWh/day", delta=f"{surplus.sum() / gen.sum() * 100:.0f}% of PV" if gen.sum() > 0 else None)
st.caption(f"Pump {pump_kw:.2f} kW · PV {panel_kwp:.2f} kWp · cell temp = ({clim['tmean'][mi]:.1f}+{clim['tmax'][mi]:.1f})/2 + {CELL_TEMP_RISE:.0f} °C · "
           f"pumping {run_h:.1f} h/day · climate: {clim['source']}")

st.subheader(f"24-hour balance — {MONTHS[mi]}")
f = go.Figure()
f.add_scatter(x=hours, y=gen, name="PV generation", fill="tozeroy", fillcolor="rgba(210,153,34,.12)", line=dict(color=AMBER, width=2))
f.add_scatter(x=hours, y=irr_load, name="Pump", line=dict(color=GREEN, width=2, dash="dash"))
f.add_scatter(x=hours, y=total, name="Total load", line=dict(color=RED, width=1.5, dash="dot"))
f.add_scatter(x=hours, y=surplus, name="Surplus", fill="tozeroy", fillcolor="rgba(57,197,207,.1)", line=dict(color=TEAL))
if deficit.sum() > 0:
    f.add_scatter(x=hours, y=deficit, name="Deficit", fill="tozeroy", fillcolor="rgba(248,81,73,.12)", line=dict(color=RED))
f.update_layout(xaxis_title="Hour of day", yaxis_title="kW")
st.plotly_chart(dark(f), use_container_width=True)

c1, c2 = st.columns(2)
with c1:
    st.subheader("Surplus allocation (day)")
    s_tot = surplus.sum()
    cold_a = min(cold_load.sum(), s_tot * 0.6)
    er_a = min(er_load.sum(), s_tot - cold_a)
    ph_a = min(ph_load.sum(), s_tot - cold_a - er_a)
    free = max(0.0, s_tot - cold_a - er_a - ph_a)
    pairs = [(n, v, c) for n, v, c in [("Cold storage", cold_a, TEAL), ("E-rickshaw", er_a, BLUE), ("Post-harvest", ph_a, AMBER),
                                        ("Free (grid / idle)", free, GRID)] if v > 0.01]
    if pairs:
        n, v, c = zip(*pairs)
        pie = go.Figure(go.Pie(labels=list(n), values=list(v), hole=0.55, marker=dict(colors=list(c))))
        st.plotly_chart(dark(pie, 300), use_container_width=True)
    else:
        st.info("No surplus this month at this size.")
with c2:
    st.subheader("Monthly energy, whole year")
    from models.techno_economic import DAYS, SystemSpec, size_system
    r = size_system(SystemSpec(district=district, crop_type=crop, area_ha=area_ha, pump_kw=pump_kw, panel_kwp=panel_kwp,
                               clim=clim, planting_month=planting, gw_depth_m=gw, irr_eff=eff_irr, irrigation_hours=window))
    y = go.Figure()
    y.add_bar(x=MONTHS, y=r.monthly["PV kWh"], name="PV kWh", marker_color=AMBER, opacity=0.8)
    y.add_bar(x=MONTHS, y=r.monthly["Pump kWh"], name="Pump kWh", marker_color=GREEN, opacity=0.8)
    y.update_layout(barmode="group", yaxis_title="kWh / month")
    st.plotly_chart(dark(y, 300), use_container_width=True)

st.divider()
st.subheader("Hourly table")
st.dataframe({"Hour": [f"{h:02d}:00" for h in hours], "PV kW": gen.round(2), "Pump kW": irr_load.round(2),
              "Cold kW": cold_load.round(2), "E-rickshaw kW": er_load.round(2), "Post-harvest kW": ph_load.round(2),
              "Surplus kW": surplus.round(2), "Deficit kW": deficit.round(2)}, use_container_width=True, height=300)
