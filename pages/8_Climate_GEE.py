"""
Title: SMART-SIP+ DSS Prototype Climate & Earth Observation (Google Earth Engine powered) Page.

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.footer import inject_footer

st.set_page_config(page_title="Climate & GEE | SMART-SIP+", layout="wide")
inject_footer()

from data.bangladesh_data import DISTRICTS, GEE_DATASETS
from models.techno_economic import MONTHS
from utils.climate import (GEE_PROJECT, fetch_gee_climate, gee_status, get_parcel_climate, get_parcel_eo, init_gee)
from utils.db import get_dashboard_kpis

GREEN, AMBER, RED, TEAL, BLUE = "#3fb950", "#d29922", "#f85149", "#39c5cf", "#58a6ff"
PAPER, PLOT, GRID, TEXT = "#161b22", "#0d1117", "#30363d", "#e6edf3"


def dark(fig, h=330):
    fig.update_layout(plot_bgcolor=PLOT, paper_bgcolor=PAPER, height=h,
                      font=dict(color=TEXT, family="IBM Plex Mono, monospace", size=11),
                      xaxis=dict(gridcolor=GRID, zerolinecolor=GRID), yaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
                      margin=dict(l=10, r=10, t=30, b=10), legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.2))
    return fig


st.title("☁ Climate & Earth Observation — Google Earth Engine")
st.caption("ERA5-Land (~9 km) · Sentinel-2 · SRTM · JRC · MODIS · results cached in SQLite")

with st.sidebar:
    st.header("Earth Engine")
    ok = init_gee()
    if ok:
        st.success(f"Connected · project `{GEE_PROJECT}`")
    else:
        st.error("Not connected")
        st.caption(gee_status()["err"] or "Run `earthengine authenticate`, set GEE_PROJECT_ID in .env")
        if st.button("↻ Retry connection"):
            init_gee(force=True)
            st.rerun()
    st.divider()
    district = st.selectbox("District", sorted(DISTRICTS["district"]))
    d = DISTRICTS[DISTRICTS["district"] == district].iloc[0]
    lat = st.number_input("Latitude", value=float(d["lat"]), format="%.4f", key=f"c_lat_{district}")
    lon = st.number_input("Longitude", value=float(d["lon"]), format="%.4f", key=f"c_lon_{district}")
    k = get_dashboard_kpis()
    st.metric("Daily rows cached", f"{k['climate_rows_cached']:,}")
    st.metric("EO results cached", f"{k['gee_queries_stored']}")

t1, t2, t3, t4 = st.tabs(["Daily series", "Monthly climatology", "All districts", "Parcel EO spot query"])

with t1:
    end = datetime.today().date() - timedelta(days=7)          # ERA5-Land lags real time by days
    start = end - timedelta(days=364)
    go_daily = st.button("🔄 Fetch / refresh last 365 days", type="primary", disabled=not ok)
    df = fetch_gee_climate(lat, lon, str(start), str(end), use_cache=not go_daily) if (go_daily or ok) else None
    if df is None:
        st.info("No data yet. " + (gee_status()["err"] if not ok else "Press the button to fetch."))
    else:
        c = st.columns(4)
        c[0].metric("Mean GHI", f"{df['ghi'].mean():.2f} kWh/m²/d")
        c[1].metric("Mean temp", f"{df['temp'].mean():.1f} °C")
        c[2].metric("Annual rain", f"{df['precip_mm'].sum():,.0f} mm" if "precip_mm" in df and df["precip_mm"].notna().any() else "n/a")
        c[3].metric("Days", f"{len(df)}", delta=df["source"].iloc[0])
        a, b = st.columns(2)
        f = go.Figure()
        f.add_scatter(x=df["date"], y=df["ghi"], name="Daily", line=dict(color=AMBER, width=0.6), opacity=0.4)
        f.add_scatter(x=df["date"], y=df["ghi"].rolling(7, min_periods=1).mean(), name="7-day mean", line=dict(color=AMBER, width=2))
        f.update_layout(title="GHI kWh/m²/day")
        a.plotly_chart(dark(f), use_container_width=True)
        f = go.Figure()
        if "tmax" in df and df["tmax"].notna().any():
            f.add_scatter(x=df["date"], y=df["tmax"].rolling(7, min_periods=1).mean(), name="Tmax", line=dict(color=RED))
            f.add_scatter(x=df["date"], y=df["tmin"].rolling(7, min_periods=1).mean(), name="Tmin", line=dict(color=BLUE))
        f.add_scatter(x=df["date"], y=df["temp"].rolling(7, min_periods=1).mean(), name="Tmean", line=dict(color=TEAL, width=2))
        f.update_layout(title="Temperature °C (7-day mean)")
        b.plotly_chart(dark(f), use_container_width=True)
        if "precip_mm" in df and df["precip_mm"].notna().any():
            f = go.Figure(go.Bar(x=df["date"], y=df["precip_mm"], marker_color=BLUE))
            f.update_layout(title="Daily rainfall mm", showlegend=False)
            st.plotly_chart(dark(f, 250), use_container_width=True)

with t2:
    if st.button("🔄 Build / refresh climatology for this point", disabled=not ok):
        with st.spinner("Querying ERA5-Land…"):
            clim = get_parcel_climate(lat, lon, refresh=True)
    else:
        clim = get_parcel_climate(lat, lon, allow_fetch=False)
    if clim is None:
        st.info("Not cached yet. Press the button (one Earth Engine call builds all 12 months).")
    else:
        tab = pd.DataFrame({"Month": MONTHS, "GHI kWh/m²/d": clim["ghi"], "Tmean °C": clim["tmean"], "Tmax °C": clim["tmax"],
                            "Tmin °C": clim["tmin"], "Rain mm": clim["precip_mm"], "ETo mm/d": clim["eto"]})
        f = go.Figure()
        f.add_bar(x=MONTHS, y=clim["precip_mm"], name="Rain mm/month", marker_color=BLUE, opacity=0.6)
        f.add_scatter(x=MONTHS, y=np.array(clim["ghi"]) * 30, name="GHI ×30", line=dict(color=AMBER))
        f.add_scatter(x=MONTHS, y=np.array(clim["eto"]) * 30, name="ETo ×30 (mm/month)", line=dict(color=GREEN, dash="dot"))
        st.plotly_chart(dark(f), use_container_width=True)
        st.dataframe(tab, use_container_width=True, hide_index=True)
        st.caption(" · ".join(clim.get("notes", [])))

with t3:
    st.caption("Mean annual GHI per district from cached ERA5-Land climatologies. Missing districts can be fetched (one call each).")
    if st.button("🛰 Fetch any missing districts", disabled=not ok):
        bar = st.progress(0.0)
        for i, (_, r) in enumerate(DISTRICTS.iterrows()):
            get_parcel_climate(float(r["lat"]), float(r["lon"]))
            bar.progress((i + 1) / len(DISTRICTS))
    f, rows = go.Figure(), []
    for _, r in DISTRICTS.iterrows():
        c = get_parcel_climate(float(r["lat"]), float(r["lon"]), allow_fetch=False)
        if c:
            f.add_scatter(x=MONTHS, y=c["ghi"], name=r["district"], mode="lines")
            rows.append({"District": r["district"], "Mean GHI": round(float(np.mean(c["ghi"])), 2),
                         "Annual rain mm": round(float(np.sum(c["precip_mm"])))})
    if rows:
        f.update_layout(yaxis_title="GHI kWh/m²/day")
        st.plotly_chart(dark(f, 380), use_container_width=True)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No district climatologies cached yet.")

with t4:
    qd = st.date_input("Imagery date (60-day median up to this date)", value=datetime.today().date() - timedelta(days=15))
    radius = st.slider("Buffer radius around the point (m)", 20, 500, 50)
    if st.button("🛰 Run Earth Engine query", type="primary", disabled=not ok):
        with st.spinner("Querying Sentinel-2 · SRTM · JRC · MODIS…"):
            eo = get_parcel_eo(None, lat, lon, qd.strftime("%Y-%m-%d"), buffer_m=radius)
        if eo is None:
            st.error(f"Query failed: {gee_status()['err']}")
        else:
            c = st.columns(4)
            c[0].metric("NDVI", eo["ndvi"] if eo["ndvi"] is not None else "no clear scene")
            c[1].metric("Elevation", f"{eo['elevation']} m")
            c[2].metric("Flood occurrence", f"{(eo['flood_risk'] or 0) * 100:.1f}%")
            c[3].metric("Land cover", eo["land_use"] or "n/a")
            st.caption(f"Source: {eo['source']}" + (f" · {eo.get('n_scenes')} Sentinel-2 scenes" if eo.get("n_scenes") is not None else ""))
    st.divider()
    st.subheader("Dataset catalogue")
    st.dataframe(GEE_DATASETS[["name", "source", "collection", "resolution", "status"]], use_container_width=True, hide_index=True)
