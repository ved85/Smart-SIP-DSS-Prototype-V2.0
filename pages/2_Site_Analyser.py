"""
Title: SMART-SIP+ DSS Prototype Site Analyser Page

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import json, math
from streamlit_folium import st_folium

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.footer import inject_footer


from utils.maps import build_parcel_draw_map, build_site_map, TILE_OPTIONS
from utils.climate import climate_panel, get_parcel_climate, get_parcel_eo, static_climate
from data.bangladesh_data import DISTRICTS, CROP_ETC, to_hectares
from utils.db import save_parcel, load_parcels, delete_parcel, load_parcel_geojson
from models.techno_economic import MONTHS, SystemSpec, auto_design, groundwater_safeguard, size_system
from utils.geo import measure_drawings, measure_parcel, with_measurements

st.set_page_config(page_title="Site Analyser | SMART-SIP+", layout="wide")
inject_footer()

GREEN  = "#3fb950"; AMBER = "#d29922"; RED = "#f85149"
TEAL   = "#39c5cf"; BLUE  = "#58a6ff"
PAPER  = "#161b22"; PLOT  = "#0d1117"; GRID = "#30363d"; TEXT = "#e6edf3"

def plotly_dark(fig):
    fig.update_layout(
        plot_bgcolor=PLOT, paper_bgcolor=PAPER,
        font=dict(color=TEXT, family="IBM Plex Mono, monospace", size=11),
        xaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
        yaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
        margin=dict(l=10, r=10, t=30, b=10),
    )
    return fig

st.title("📍 Site Analyser")
st.caption("Draw your land parcel on the map, define crop & system, run a hydraulic and solar feasibility assessment.")

tabs = st.tabs(["🗺 Draw & Register Parcel", "📋 Saved Parcels & Analysis"])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Draw parcel
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[0]:
    col_map, col_form = st.columns([3, 2])

    with col_map:
        st.subheader("Draw Your Land Parcel")
        st.caption(
            "Use the **search bar** on the map to jump to a village, district or `lat, lon`, then the "
            "**polygon** or **rectangle** tool (left toolbar) to outline your farm. "
            "The area is measured from your outline; fill in the details on the right and click **Save Parcel**."
        )
        tile_draw = st.selectbox("🗺 Map type", list(TILE_OPTIONS.keys()),
                                  key="tile_draw")
            
        existing = []
        parcels_df = load_parcels()
        if not parcels_df.empty:
            for _, pr in parcels_df.iterrows():
                geo = load_parcel_geojson(pr["id"])
                existing.append({**pr.to_dict(), "polygon_geojson": geo})

        draw_map = build_parcel_draw_map(
            existing_parcels=existing,
            tile_choice=tile_draw,
            lat=23.8,
            lon=89.9,
            zoom=7
        )
        
        # Restrict returned_objects to ONLY 'all_drawings'
        # This prevents Streamlit from reloading on pan/zoom (fixing the stutter/reset)
        map_out  = st_folium(draw_map, width="100%", height=500,
                             key="parcel_draw_map",
                             returned_objects=["all_drawings"])

    with col_form:
        st.subheader("Parcel Details")

        # ── Measure what was drawn (geodesic, WGS-84) ─────────────────────────
        drawings = (map_out or {}).get("all_drawings") or []
        shapes   = measure_drawings(drawings)

        drawn_geo = None
        centroid_lat, centroid_lon = 23.8, 89.9
        measured_ha = None
        pg = None
        if shapes:
            if len(shapes) > 1:
                labels = [f"Shape {i + 1}" for i in range(len(shapes))]   # stable: survives editing a shape
                choice = st.selectbox("Which shape is this parcel?", labels, index=len(shapes) - 1,
                                      key=f"sa_shape_{len(shapes)}")      # new key => defaults to newest shape
                pick = labels.index(choice)
                st.caption("  ·  ".join(
                    f"{lab}: {sh.area_ha:,.3f} ha" + ("" if sh.ok else " ⚠ invalid")
                    for lab, sh in zip(labels, shapes)))
            else:
                pick = 0
            pg = shapes[pick]

            for msg in pg.errors:
                st.error(f"🚫 {msg}")
            for msg in pg.warnings:
                st.warning(f"⚠️ {msg}")

            if pg.area_m2 > 0:
                measured_ha = pg.area_ha
                g1, g2, g3 = st.columns(3)
                g1.metric("Measured area", f"{pg.area_ha:,.3f} ha")
                g2.metric("Perimeter", f"{pg.perimeter_m:,.0f} m")
                g3.metric("Vertices", f"{pg.n_vertices}")
                st.caption(
                    f"= {pg.area_m2:,.0f} m² · {pg.area_ha / to_hectares(1, 'acres'):.2f} acres · "
                    f"{pg.area_ha / to_hectares(1, 'bigha'):.1f} bigha · "
                    f"{pg.area_ha / to_hectares(1, 'katha'):.0f} katha  \n"
                    f"{pg.method}. Independent projected check differs by {pg.xcheck_rel_diff:.4%}."
                )
            if pg.ok:
                centroid_lat, centroid_lon = pg.centroid_lat, pg.centroid_lon
                drawn_geo = json.dumps(with_measurements(drawings[pick], pg))

        parcel_name = st.text_input("Parcel Name", placeholder="e.g. North Block Farm A")

        _opts = sorted(DISTRICTS["district"].tolist())
        _near = None
        if drawn_geo:
            _dd = np.hypot(DISTRICTS["lat"] - centroid_lat, DISTRICTS["lon"] - centroid_lon)
            _near = DISTRICTS["district"].iloc[int(_dd.argmin())]
        district = st.selectbox("District", options=_opts,
                                index=_opts.index(_near) if _near in _opts else 0,
                                key=f"sa_district_{_near}")
        upazila  = st.text_input("Upazila (sub-district)", placeholder="Optional")

        # Area: measured from the outline unless the user explicitly overrides it
        area_unit = st.selectbox("Area Unit", ["hectares", "acres", "bigha", "katha"])
        per_unit  = to_hectares(1.0, area_unit)          # hectares in one of the chosen unit
        override  = bool(measured_ha) and st.checkbox(
            "Enter the area manually instead of using the measured area", key="sa_override")

        if measured_ha and not override:
            area_ha  = measured_ha
            area_val = measured_ha / per_unit
            st.markdown(f"**Area used: {area_val:,.3f} {area_unit}** (measured from the drawn outline)")
        else:
            default_area = round(measured_ha / per_unit, 3) if measured_ha else (5.0 if area_unit == "acres" else 2.0)
            area_val = st.number_input(f"Area ({area_unit})", min_value=0.01,
                                       value=float(default_area), step=0.1)
            area_ha = to_hectares(area_val, area_unit)
            if measured_ha and abs(area_ha - measured_ha) / measured_ha > 0.01:
                st.warning(f"Manual area differs from the measured area by "
                           f"{(area_ha - measured_ha) / measured_ha:+.1%}. The manual value will be saved.")
        st.caption(f"= **{area_ha:.3f} ha** = **{area_ha/0.404686:.2f} acres** "
                   f"= **{area_ha/0.133546:.1f} bigha**")

        crop_type = st.selectbox("Primary Crop", list(CROP_ETC.keys()))
        notes     = st.text_area("Notes / Description", height=68,
                                 placeholder="e.g. Boro rice — deep tubewell, seasonal flooding risk")

        st.divider()
        # Quick hydraulic preview from the cell's climate (cached ERA5-Land if present)
        drow = DISTRICTS[DISTRICTS["district"] == district].iloc[0]
        pv_lat, pv_lon = (centroid_lat, centroid_lon) if drawn_geo else (float(drow["lat"]), float(drow["lon"]))
        clim_pv = get_parcel_climate(pv_lat, pv_lon, allow_fetch=False)
        pv_src = "ERA5-Land (cached)" if clim_pv else "static placeholder - ERA5-Land is fetched when you save"
        clim_pv = clim_pv or static_climate(pv_lat, pv_lon)

        gw_depth = st.number_input("Static water level (m)", 1.0, 40.0, float(drow["gw_depth_m"]), 0.5,
                                   key=f"sa_gw_{district}",
                                   help="Default is a district placeholder. Enter a measured value if you have one.")
        gw_measured = st.checkbox("This depth is a measured value (save it with the parcel)", key="sa_gwm")
        gw_trend = st.selectbox("Water-table trend (observed)", ["unknown", "stable", "declining"], key="sa_trend")

        wb, hyd = auto_design(crop_type, area_ha, CROP_ETC[crop_type]["plant_month"], clim_pv, gw_depth)
        st.markdown(f"**Quick hydraulic preview** · climate: {pv_src}")
        h1, h2, h3 = st.columns(3)
        h1.metric("Peak demand", f"{wb['peak_m3_day']:.0f} m³/day")
        h2.metric("Design flow", f"{wb['design_flow_m3h']:.1f} m³/h")
        h3.metric("TDH", f"{hyd.tdh_m:.1f} m")
        h4, h5, h6 = st.columns(3)
        h4.metric("Pump", f"{hyd.power_kw:.2f} kW")
        h5.metric("PV array", f"{hyd.panel_kwp:.1f} kWp")
        h6.metric("Season water", f"{wb['annual_gross_mm']:,.0f} mm")
        sg = groundwater_safeguard(gw_depth, 2.0, wb["annual_gross_mm"], float(np.sum(clim_pv["precip_mm"])), 0.20, gw_trend)
        {"High": st.error, "Medium": st.warning, "Low": st.success}[sg["level"]](
            f"**Groundwater screen: {sg['level']}** — " + " ".join(sg["messages"]))

        st.divider()
        save_blocked = pg is not None and not pg.ok
        if st.button("💾 Save Parcel to Database", type="primary", disabled=save_blocked,
                     help="Fix the outline error above first." if save_blocked else None):
            if not parcel_name.strip():
                st.error("Please enter a parcel name.")
            elif drawn_geo is None:
                st.warning(
                    "No polygon drawn yet. Draw your parcel on the map first, "
                    "or save without a polygon (centroid will be used)."
                )
                # Allow saving without polygon using district centroid
                row = DISTRICTS[DISTRICTS["district"] == district].iloc[0]
                pid = save_parcel(
                    name=parcel_name, district=district, upazila=upazila,
                    lat=row.lat, lon=row.lon,
                    area_ha=area_ha, area_orig=area_val, area_unit=area_unit,
                    polygon_geojson=json.dumps({"type":"Point","coordinates":[row.lon, row.lat]}),
                    crop_type=crop_type, notes=notes,
                    gw_depth_m=gw_depth if gw_measured else None, gw_trend=gw_trend,
                )
                with st.spinner("Fetching ERA5-Land climate for this parcel…"):
                    get_parcel_climate(float(row.lat), float(row.lon))
                st.success(f"✅ Parcel saved (id={pid}) — switch to **Saved Parcels** tab.")
                st.rerun()
            else:
                pid = save_parcel(
                    name=parcel_name, district=district, upazila=upazila,
                    lat=centroid_lat, lon=centroid_lon,
                    area_ha=area_ha, area_orig=area_val, area_unit=area_unit,
                    polygon_geojson=drawn_geo, crop_type=crop_type, notes=notes,
                    gw_depth_m=gw_depth if gw_measured else None, gw_trend=gw_trend,
                )
                with st.spinner("Fetching ERA5-Land climate for this parcel…"):
                    get_parcel_climate(centroid_lat, centroid_lon)
                st.success(f"✅ Parcel '{parcel_name}' saved (id={pid})")
                st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Saved parcels & full analysis
# ═══════════════════════════════════════════════════════════════════════════════
with tabs[1]:
    parcels_df = load_parcels()

    if parcels_df.empty:
        st.info("No parcels saved yet. Go to **Draw & Register Parcel** tab to create one.")
    else:
        col_list, col_analysis = st.columns([1, 2])

        with col_list:
            st.subheader(f"Saved Parcels ({len(parcels_df)})")
            for _, pr in parcels_df.iterrows():
                sel = st.session_state.get("selected_parcel_id") == pr["id"]
                label = f"{'▶ ' if sel else ''}{pr['name']}"
                if st.button(label, key=f"psel_{pr['id']}"):
                    st.session_state["selected_parcel_id"] = pr["id"]
                    st.rerun()
                st.caption(f"  {pr['district']} · {pr['area_ha']:.2f} ha · {pr['crop_type']}")

            st.divider()
            del_id = st.number_input("Delete parcel ID", min_value=1, step=1,
                                     value=int(parcels_df["id"].iloc[0]))
            if st.button("🗑 Delete Parcel", type="secondary"):
                delete_parcel(int(del_id))
                if st.session_state.get("selected_parcel_id") == int(del_id):
                    del st.session_state["selected_parcel_id"]
                st.rerun()

        with col_analysis:
            sel_id = st.session_state.get("selected_parcel_id")
            if not sel_id:
                st.info("👈 Select a parcel from the list to run analysis.")
            else:
                pr = parcels_df[parcels_df["id"] == sel_id]
                if pr.empty:
                    st.warning("Parcel not found.")
                else:
                    pr = pr.iloc[0]
                    dist_row = DISTRICTS[DISTRICTS["district"] == pr["district"]]
                    has_gw = pd.notna(pr.get("gw_depth_m"))
                    gw_d = float(pr["gw_depth_m"]) if has_gw else (float(dist_row["gw_depth_m"].values[0]) if len(dist_row) else 5.0)
                    gw_tr = pr.get("gw_trend") if pr.get("gw_trend") in ("stable", "declining") else "unknown"
                    clim = climate_panel(float(pr["lat_centroid"]), float(pr["lon_centroid"]), key=f"sa_{int(pr['id'])}")

                    st.subheader(f"🌾 {pr['name']}")
                    st.markdown(f"**{pr['district']}** · {pr.get('upazila','—')} · "
                                f"{pr['area_ha']:.2f} ha ({pr['area_orig']:.1f} {pr['area_unit_orig']})")

                    # Re-measure the saved outline so overrides / older estimates are visible
                    _geo = load_parcel_geojson(int(pr["id"]))
                    _chk = measure_parcel(_geo) if _geo else None
                    if _chk is not None and _chk.ok:
                        _d = (pr["area_ha"] - _chk.area_ha) / _chk.area_ha
                        if abs(_d) > 0.002:
                            st.caption(f"⚠️ Stored area {pr['area_ha']:.3f} ha differs from the saved outline "
                                       f"({_chk.area_ha:.3f} ha, {_d:+.1%}) - it was typed in manually or "
                                       f"saved with the earlier approximate method.")
                        else:
                            st.caption(f"📐 Stored area matches the saved outline ({_chk.area_ha:.3f} ha, geodesic).")

                    st.caption("Static water level: " + ("**measured** (saved with parcel)" if has_gw
                                                           else "district **placeholder** - edit the parcel or use the Business Case to override"))
                    crop = pr["crop_type"]; area = float(pr["area_ha"])
                    planting = CROP_ETC[crop]["plant_month"]
                    wb, hyd = auto_design(crop, area, planting, clim, gw_d)
                    res = size_system(SystemSpec(
                        district=pr["district"], crop_type=crop, area_ha=area, pump_kw=hyd.power_kw,
                        panel_kwp=hyd.panel_kwp, clim=clim, planting_month=planting, gw_depth_m=gw_d,
                        lat=float(pr["lat_centroid"]), lon=float(pr["lon_centroid"]), gw_trend=gw_tr))
                    m = res.monthly

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Pump", f"{hyd.power_kw:.2f} kW")
                    m2.metric("PV array", f"{hyd.panel_kwp:.1f} kWp")
                    m3.metric("TDH", f"{hyd.tdh_m:.1f} m")
                    m4.metric("Solar share of pumping", f"{res.solar_fraction:.0%}")
                    n1, n2, n3 = st.columns(3)
                    n1.metric("Season water", f"{res.annual_irrigation_mm:,.0f} mm")
                    n2.metric("Season volume", f"{res.annual_volume_m3:,.0f} m³")
                    n3.metric("Mean GHI", f"{res.ghi_mean:.2f} kWh/m²/d")

                    sg = res.safeguard
                    {"High": st.error, "Medium": st.warning, "Low": st.success}[sg["level"]](
                        f"**Groundwater screen: {sg['level']}** — " + " ".join(sg["messages"]))

                    st.markdown("**Rain, ETo and irrigation requirement (parcel cell)**")
                    f1 = go.Figure()
                    f1.add_bar(x=MONTHS, y=m["Rain mm"], name="Rain mm/month", marker_color=BLUE, opacity=0.6)
                    f1.add_bar(x=MONTHS, y=m["Gross irrig. mm"], name="Gross irrigation mm", marker_color=TEAL)
                    f1.add_scatter(x=MONTHS, y=m["ETo mm/d"] * 30, name="ETo ×30", line=dict(color=AMBER, dash="dot"))
                    f1.update_layout(barmode="group", yaxis_title="mm / month", legend=dict(bgcolor="rgba(0,0,0,0)"))
                    st.plotly_chart(plotly_dark(f1), use_container_width=True)

                    st.markdown("**Monthly PV generation vs pump energy**")
                    f2 = go.Figure()
                    f2.add_bar(x=MONTHS, y=m["PV kWh"], name="PV kWh", marker_color=AMBER, opacity=0.8)
                    f2.add_bar(x=MONTHS, y=m["Pump kWh"], name="Pump kWh", marker_color=GREEN, opacity=0.8)
                    f2.update_layout(barmode="group", yaxis_title="kWh / month", legend=dict(bgcolor="rgba(0,0,0,0)"))
                    st.plotly_chart(plotly_dark(f2), use_container_width=True)

                    with st.expander("🛰 Parcel satellite stats (Sentinel-2 · SRTM · JRC · MODIS)"):
                        from utils.geo import extract_geometry
                        _g = extract_geometry(_geo) if _geo else None
                        _g = _g if _g and _g.get("type") in ("Polygon", "MultiPolygon") else None
                        if st.button("Fetch from Earth Engine", key=f"sa_eo_{int(pr['id'])}"):
                            with st.spinner("Querying GEE…"):
                                st.session_state[f"sa_eo_{int(pr['id'])}_v"] = get_parcel_eo(
                                    _g, float(pr["lat_centroid"]), float(pr["lon_centroid"]))
                        eo = st.session_state.get(f"sa_eo_{int(pr['id'])}_v")
                        if eo:
                            e1, e2, e3, e4 = st.columns(4)
                            e1.metric("NDVI", eo["ndvi"] if eo["ndvi"] is not None else "no clear scene")
                            e2.metric("Elevation", f"{eo['elevation']} m")
                            e3.metric("Flood occurrence", f"{(eo['flood_risk'] or 0) * 100:.1f}%")
                            e4.metric("Land cover", eo["land_use"] or "n/a")
                        else:
                            st.caption("Averaged over the saved outline." if _g else "Point-based (no polygon saved).")

                    st.divider()
                    if st.button("→ Open Business Case for this parcel", type="primary"):
                        st.session_state["bc_parcel_id"] = int(pr["id"])
                        st.session_state["bc_district"] = pr["district"]
                        st.session_state["bc_area_ha"] = area
                        st.session_state["bc_crop"] = crop
                        st.switch_page("pages/3_Business_Case.py")
