"""
Title: SMART-SIP+ DSS Prototype Dashboard Page

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

from utils.db import (
    get_dashboard_kpis, load_pipeline_jobs,
    load_recent_business_cases, load_all_cached_climate,
    load_all_gee_results, get_cached_climate_locations
)
from data.bangladesh_data import DISTRICTS, DISTRICTS_SOURCE
from utils.footer import inject_footer


st.set_page_config(page_title="Dashboard | SMART-SIP+", layout="wide")
inject_footer()
P = "#0d1117"; BG = "#161b22"; GR = "#30363d"; TX = "#e6edf3"
GN = "#3fb950"; TE = "#39c5cf"; AM = "#d29922"; RE = "#f85149"; BL = "#58a6ff"; PU = "#bc8cff"

def dark(fig):
    fig.update_layout(
        plot_bgcolor=P, paper_bgcolor=BG,
        font=dict(color=TX, family="IBM Plex Mono, monospace", size=11),
        xaxis=dict(gridcolor=GR, zerolinecolor=GR),
        yaxis=dict(gridcolor=GR, zerolinecolor=GR),
        margin=dict(l=10, r=10, t=30, b=10),
    )
    return fig

def get_location_name(lat: float, lon: float) -> str:
    """Matches lat/lon against known district centroids or outputs coordinate label."""
    dist_sq = (DISTRICTS["lat"] - lat) ** 2 + (DISTRICTS["lon"] - lon) ** 2
    nearest_idx = dist_sq.idxmin()
    if dist_sq.loc[nearest_idx] < 0.25:  # within ~30-40km
        return DISTRICTS.loc[nearest_idx, "district"]
    return f"Coord ({lat:.2f}, {lon:.2f})"

st.title("🌞 SMART-SIP+ Decision Support System")
st.caption(f"UKRI · Birmingham City University · GEE Core · {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
st.divider()

kpis = get_dashboard_kpis()
bc   = load_recent_business_cases(500)
df_climate_all = load_all_cached_climate()
df_gee_all = load_all_gee_results()

# ── Top-Level KPI Summary ─────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Business Cases",      f"{kpis['n_business_cases']}")
c2.metric("Land Parcels",        f"{kpis['n_parcels']}")
c3.metric("CO₂ Avoided (t/yr)",  f"{kpis['total_co2_t']:,.1f}" if kpis['total_co2_t'] else "—")
c4.metric("Diesel Saved (L/yr)", f"{kpis['total_diesel_l']:,.0f}" if kpis['total_diesel_l'] else "—")
c5.metric("Avg Payback",         f"{kpis['avg_payback_years']:.1f} yr" if kpis['avg_payback_years'] else "—",
          delta_color="inverse")
c6.metric("GEE Climate Rows",    f"{kpis['climate_rows_cached']:,}")

if not bc.empty and "climate_source" in bc.columns:
    n_ph = int((bc["climate_source"].fillna("legacy") != "gee_era5_land").sum())
    if n_ph:
        st.warning(f"{n_ph} of {len(bc)} saved business cases used placeholder / pre-GEE climate. "
                   "Re-run them on the Business Case page to base them on Earth Engine ERA5-Land.")
st.caption(f"District attribute tables (adoption, groundwater, aquifer): {DISTRICTS_SOURCE}")
st.divider()

# ── Dynamic Cached GEE Climate Graphics ───────────────────────────────────────
st.subheader("📊 Cached Climate Graphics (GEE ERA5-Land)")

if df_climate_all.empty:
    st.info(
        "No cached climate data found in the SQLite database yet.\n\n"
        "👉 Navigate to **☁ Climate & GEE** in the sidebar, pick any district, and click "
        "**Fetch live GEE Climate Data** to populate the cache."
    )
else:
    # Tag each record with its nearest district name
    df_climate_all["location"] = df_climate_all.apply(
        lambda r: get_location_name(r["lat"], r["lon"]), axis=1
    )
    available_locs = sorted(df_climate_all["location"].unique().tolist())
    
    col_sel, col_stat = st.columns([1, 2])
    with col_sel:
        view_mode = st.selectbox(
            "Select Cached View",
            options=["All Cached Locations (Comparison Overlay)"] + available_locs,
            index=0
        )
    with col_stat:
        total_locs = len(available_locs)
        date_min = df_climate_all["date"].min().strftime("%Y-%m-%d")
        date_max = df_climate_all["date"].max().strftime("%Y-%m-%d")
        st.markdown(
            f"**Cached Districts / Sites:** `{total_locs}` &nbsp;|&nbsp; "
            f"**Total Records:** `{len(df_climate_all):,}` &nbsp;|&nbsp; "
            f"**Time Horizon:** `{date_min}` → `{date_max}`"
        )

    # 1. Overlay mode: show comparisons across all cached locations
    if view_mode == "All Cached Locations (Comparison Overlay)":
        col_ghi, col_temp = st.columns(2)
        color_palette = [AM, GN, TE, BL, PU, RE, "#ff7f50", "#20b2aa", "#dda0dd", "#90ee90"]

        with col_ghi:
            st.markdown("**GHI Comparison (7-Day Rolling Avg) — All Cached Sites**")
            fig_ghi_comp = go.Figure()
            for idx, loc in enumerate(available_locs):
                sub = df_climate_all[df_climate_all["location"] == loc].sort_values("date")
                fig_ghi_comp.add_trace(go.Scatter(
                    x=sub["date"],
                    y=sub["ghi"].rolling(7, min_periods=1).mean(),
                    name=loc,
                    line=dict(color=color_palette[idx % len(color_palette)], width=2),
                    mode="lines"
                ))
            fig_ghi_comp.update_layout(
                yaxis_title="GHI (kWh/m²/day)",
                legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.2)
            )
            st.plotly_chart(dark(fig_ghi_comp), use_container_width=True)

        with col_temp:
            st.markdown("**2m Temperature Comparison (14-Day Rolling Avg)**")
            fig_temp_comp = go.Figure()
            for idx, loc in enumerate(available_locs):
                sub = df_climate_all[df_climate_all["location"] == loc].sort_values("date")
                fig_temp_comp.add_trace(go.Scatter(
                    x=sub["date"],
                    y=sub["temp"].rolling(14, min_periods=1).mean(),
                    name=loc,
                    line=dict(color=color_palette[idx % len(color_palette)], width=2),
                    mode="lines"
                ))
            fig_temp_comp.update_layout(
                yaxis_title="Temperature (°C)",
                legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.2)
            )
            st.plotly_chart(dark(fig_temp_comp), use_container_width=True)

    # 2. Individual Location Drilldown
    else:
        sub = df_climate_all[df_climate_all["location"] == view_mode].sort_values("date")
        col_l, col_r = st.columns(2)

        with col_l:
            st.markdown(f"**Daily GHI & 7-Day Trend — {view_mode}**")
            fig_loc_ghi = go.Figure()
            fig_loc_ghi.add_trace(go.Scatter(
                x=sub["date"],
                y=sub["ghi"].rolling(7, min_periods=1).mean(),
                name="7-day avg",
                line=dict(color=AM, width=2),
                mode="lines"
            ))
            fig_loc_ghi.add_trace(go.Scatter(
                x=sub["date"],
                y=sub["ghi"],
                name="Daily GHI",
                line=dict(color=AM, width=0.4),
                opacity=0.35,
                mode="lines"
            ))
            fig_loc_ghi.update_layout(yaxis_title="kWh/m²/day", legend=dict(bgcolor="rgba(0,0,0,0)"))
            st.plotly_chart(dark(fig_loc_ghi), use_container_width=True)

        with col_r:
            st.markdown(f"**Temperature Profile (°C) — {view_mode}**")
            fig_loc_temp = go.Figure()
            fig_loc_temp.add_trace(go.Scatter(
                x=sub["date"],
                y=sub["temp"].rolling(14, min_periods=1).mean(),
                name="14-day avg",
                line=dict(color=TE, width=2),
                fill="tozeroy",
                fillcolor="rgba(57,197,207,0.08)",
                mode="lines"
            ))
            fig_loc_temp.update_layout(yaxis_title="°C", legend=dict(bgcolor="rgba(0,0,0,0)"))
            st.plotly_chart(dark(fig_loc_temp), use_container_width=True)

        # Wind speed profile for this location
        if "wind_speed" in sub.columns and sub["wind_speed"].notna().any():
            st.markdown(f"**10m Wind Speed (m/s) — {view_mode}**")
            fig_wind = go.Figure()
            fig_wind.add_trace(go.Scatter(
                x=sub["date"],
                y=sub["wind_speed"].rolling(7, min_periods=1).mean(),
                name="7-day avg wind",
                line=dict(color=BL, width=1.5),
                mode="lines"
            ))
            fig_wind.update_layout(yaxis_title="m/s", height=240, margin=dict(t=20, b=20, l=10, r=10))
            st.plotly_chart(dark(fig_wind), use_container_width=True)

st.divider()

# ── Cached Earth Observation Analytics (Sentinel-2, SRTM, JRC) ───────────────
st.subheader("🛰️ Cached Earth Observation Extractions (GEE Spot Queries)")

if df_gee_all.empty:
    st.info(
        "No GEE spot extractions saved yet.\n\n"
        "👉 Open **☁ Climate & GEE**, enter coordinates, and click **Run Live GEE Spatial Query** "
        "to cache Sentinel-2 NDVI, SRTM Elevation, and JRC Flood Risk data."
    )
else:
    df_gee_all["location"] = df_gee_all.apply(
        lambda r: get_location_name(r["lat"], r["lon"]), axis=1
    )
    g1, g2, g3 = st.columns(3)

    # NDVI Bar
    with g1:
        st.markdown("**Sentinel-2 NDVI (Vegetation Index)**")
        df_ndvi = df_gee_all.dropna(subset=["ndvi"]).drop_duplicates(subset=["lat", "lon"])
        if not df_ndvi.empty:
            fig_ndvi = go.Figure(go.Bar(
                x=df_ndvi["ndvi"],
                y=df_ndvi["location"],
                orientation="h",
                marker=dict(color=[GN if v > 0.5 else AM if v > 0.3 else RE for v in df_ndvi["ndvi"]]),
                text=[f"{v:.3f}" for v in df_ndvi["ndvi"]],
                textposition="outside",
            ))
            fig_ndvi.update_layout(xaxis=dict(range=[0, 1.0], title="NDVI"), height=280)
            st.plotly_chart(dark(fig_ndvi), use_container_width=True)
        else:
            st.caption("No NDVI records logged.")

    # Elevation Bar
    with g2:
        st.markdown("**SRTM Elevation (m ASL)**")
        df_dem = df_gee_all.dropna(subset=["elevation"]).drop_duplicates(subset=["lat", "lon"])
        if not df_dem.empty:
            fig_dem = go.Figure(go.Bar(
                x=df_dem["elevation"],
                y=df_dem["location"],
                orientation="h",
                marker=dict(color=TE),
                text=[f"{v:.1f} m" for v in df_dem["elevation"]],
                textposition="outside",
            ))
            fig_dem.update_layout(xaxis=dict(title="Elevation (m)"), height=280)
            st.plotly_chart(dark(fig_dem), use_container_width=True)
        else:
            st.caption("No DEM elevation records logged.")

    # Flood Risk Bar
    with g3:
        st.markdown("**JRC Global Surface Water (Flood Risk %)**")
        df_fl = df_gee_all.dropna(subset=["flood_risk"]).drop_duplicates(subset=["lat", "lon"])
        if not df_fl.empty:
            fig_fl = go.Figure(go.Bar(
                x=df_fl["flood_risk"] * 100,
                y=df_fl["location"],
                orientation="h",
                marker=dict(color=[RE if v > 0.3 else AM if v > 0.1 else GN for v in df_fl["flood_risk"]]),
                text=[f"{v*100:.1f}%" for v in df_fl["flood_risk"]],
                textposition="outside",
            ))
            fig_fl.update_layout(xaxis=dict(range=[0, 100], title="Occurrence %"), height=280)
            st.plotly_chart(dark(fig_fl), use_container_width=True)
        else:
            st.caption("No flood risk records logged.")

st.divider()

# ── Business Cases & Adoption Metrics ─────────────────────────────────────────
col_bc1, col_bc2 = st.columns(2)

with col_bc1:
    st.subheader("Payback Distribution — Saved Business Cases")
    if bc.empty:
        st.info("No saved business cases yet.\n\n→ Go to **₿ Business Case** and click **Run & Save to Database**.")
    else:
        fig_pb = go.Figure(go.Histogram(
            x=bc["payback_years"],
            nbinsx=15,
            marker_color=GN,
            opacity=0.85
        ))
        fig_pb.update_layout(xaxis_title="Payback (years)", yaxis_title="Count", showlegend=False)
        st.plotly_chart(dark(fig_pb), use_container_width=True)
        st.caption(f"{len(bc)} saved runs · avg {bc['payback_years'].mean():.1f} yr")

with col_bc2:
    st.subheader("Solar Adoption by District — ILLUSTRATIVE placeholder data")
    ds = DISTRICTS.sort_values("solar_pct", ascending=True)
    fig_adop = go.Figure(go.Bar(
        x=ds["solar_pct"],
        y=ds["district"],
        orientation="h",
        marker=dict(color=[GN if p > 70 else AM if p > 45 else RE for p in ds["solar_pct"]]),
        text=[f"{p}%" for p in ds["solar_pct"]],
        textposition="outside",
    ))
    fig_adop.update_layout(xaxis=dict(range=[0, 100], title="Adoption %"), showlegend=False)
    st.plotly_chart(dark(fig_adop), use_container_width=True)

# ── Aquifer Vulnerability ─────────────────────────────────────────────────────
st.subheader("Aquifer Vulnerability by District — ILLUSTRATIVE placeholder data")
aq_order = {"High": 2, "Medium": 1, "Low": 0}
aq_col_m = {"High": RE, "Medium": AM, "Low": GN}
ds_aq    = DISTRICTS.sort_values("aquifer_risk", key=lambda s: s.map(aq_order))
fig_aq = go.Figure(go.Bar(
    x=ds_aq["gw_depth_m"],
    y=ds_aq["district"],
    orientation="h",
    marker=dict(color=[aq_col_m.get(r, "#888") for r in ds_aq["aquifer_risk"]]),
    text=[f"{d}m ({r})" for d, r in zip(ds_aq["gw_depth_m"], ds_aq["aquifer_risk"])],
    textposition="outside",
))
fig_aq.update_layout(
    xaxis_title="Groundwater Depth (m)",
    xaxis=dict(range=[0, max(DISTRICTS["gw_depth_m"]) * 1.25]),
    showlegend=False,
)
st.plotly_chart(dark(fig_aq), use_container_width=True)

# ── Pipeline Execution Log ────────────────────────────────────────────────────
st.divider()
st.subheader("Pipeline Job Log (live from SQLite)")
jobs = load_pipeline_jobs(20)
if jobs.empty:
    st.info("No pipeline jobs logged yet.")
else:
    icon = {"ok": "✅ OK", "running": "🔵 Running", "error": "❌ Error"}
    jobs["Status"]   = jobs["status"].map(lambda s: icon.get(s, f"⚠️ {s}"))
    jobs["Duration"] = jobs["duration_s"].apply(lambda x: f"{x:.1f}s" if pd.notna(x) else "—")
    jobs["Records"]  = jobs["records"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "—")
    st.dataframe(
        jobs[["job_name", "job_type", "schedule", "started_at", "Duration", "Records", "Status", "error_msg"]]
            .rename(columns={
                "job_name": "Job",
                "job_type": "Type",
                "schedule": "Schedule",
                "started_at": "Started",
                "error_msg": "Error"
            }),
        use_container_width=True,
        hide_index=True,
    )