"""
Title: SMART-SIP+ DSS Prototype Business Case Builder Page

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""
import io
import os
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.footer import inject_footer

st.set_page_config(page_title="Business Case | SMART-SIP+", layout="wide")
inject_footer()

from data.bangladesh_data import CROP_ETC, DISTRICTS, DISTRICTS_SOURCE, get_aquifer_flag, to_hectares
from models.techno_economic import (COLD_KG_PER_KW, DIESEL_PRICE_PER_LITRE, DISCOUNT_RATE, GRID_TARIFF_PER_KWH,
                                    MONTHS, PANEL_COST_PER_KWP, SystemSpec, auto_design, size_system)
from utils.climate import climate_panel, get_parcel_eo
from utils.db import load_parcel_geojson, load_parcels, load_recent_business_cases, save_business_case
from utils.geo import extract_geometry

GREEN, AMBER, RED, TEAL, BLUE = "#3fb950", "#d29922", "#f85149", "#39c5cf", "#58a6ff"
PAPER, PLOT, GRID, TEXT = "#161b22", "#0d1117", "#30363d", "#e6edf3"


def dark(fig, h=320):
    fig.update_layout(plot_bgcolor=PLOT, paper_bgcolor=PAPER, height=h,
                      font=dict(color=TEXT, family="IBM Plex Mono, monospace", size=11),
                      xaxis=dict(gridcolor=GRID, zerolinecolor=GRID), yaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
                      margin=dict(l=10, r=10, t=30, b=10), legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.2))
    return fig


# ── PDF report ───────────────────────────────────────────────────────────────
def build_pdf(spec, r, area_label, eo) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from datetime import datetime
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=17, textColor=colors.HexColor("#1a7f37"))
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11.5, textColor=colors.HexColor("#0b5cad"), spaceBefore=8)
    B = ParagraphStyle("b", parent=ss["Normal"], fontSize=8.5, leading=11)
    S = ParagraphStyle("s", parent=ss["Normal"], fontSize=7, textColor=colors.grey, leading=9)
    bdt = lambda v: f"BDT {v:,.0f}"

    def kv(rows):
        t = Table([[Paragraph(f"<b>{k}</b>", B), Paragraph(str(v), B)] for k, v in rows], colWidths=[6.5 * cm, 10.5 * cm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                               ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f6f9")),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        return t

    def fig_png(draw, w=8.4, h=3.0):
        f, ax = plt.subplots(figsize=(w / 2.54 * 1.0, h / 2.54 * 1.0), dpi=170)
        draw(ax)
        f.tight_layout()
        b = io.BytesIO()
        f.savefig(b, format="png")
        plt.close(f)
        b.seek(0)
        return Image(b, width=w * cm, height=h * cm)

    m = r.monthly

    def energy(ax):
        x = np.arange(12)
        ax.bar(x - 0.2, m["Pump kWh"], 0.4, label="Pump demand", color="#d29922")
        ax.bar(x + 0.2, m["PV kWh"], 0.4, label="PV generation", color="#3fb950")
        ax.set_xticks(x); ax.set_xticklabels(MONTHS, fontsize=6); ax.set_ylabel("kWh / month", fontsize=7)
        ax.tick_params(labelsize=6); ax.legend(fontsize=6); ax.set_title("Monthly pump energy vs PV", fontsize=8)

    def cash(ax):
        ax.plot(r.cashflow["year"], r.cashflow["cumulative"] / 1000, color="#1a7f37")
        ax.axhline(0, color="red", lw=0.7, ls="--")
        ax.set_xlabel("Year", fontsize=7); ax.set_ylabel("BDT '000", fontsize=7)
        ax.tick_params(labelsize=6); ax.set_title("Cumulative cash flow (after subsidy)", fontsize=8)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            title="SMART-SIP+ Business Case")
    st_ = [Paragraph("SMART-SIP+ Business Case Report", H1),
           Paragraph(f"Generated {datetime.now():%d %B %Y %H:%M} · UKRI-funded · Birmingham City University", S),
           HRFlowable(width="100%", color=colors.lightgrey), Spacer(1, 4)]
    if r.climate_source != "gee_era5_land":
        st_.append(Paragraph("<font color='red'><b>WARNING: climate inputs are a static placeholder, not Earth Engine data. "
                             "Results are illustrative only.</b></font>", B))

    st_ += [Paragraph("1. Site, crop and climate", H2), kv([
        ("District / location", f"{spec.district} ({spec.lat:.4f}, {spec.lon:.4f})" if spec.lat else spec.district),
        ("Crop / planting month", f"{spec.crop_type} / {MONTHS[spec.planting_month - 1]} ({r.season_days}-day season)"),
        ("Area", area_label),
        ("Climate source", "Google Earth Engine - ECMWF ERA5-Land (cell ~9 km at the parcel centroid)"
         if r.climate_source == "gee_era5_land" else r.climate_source),
        ("Mean GHI / mean cell temperature", f"{r.ghi_mean:.2f} kWh/m2/day (x{spec.ghi_factor:.2f} calibration) / {r.tcell_mean:.1f} C"),
        ("Irrigation efficiency", f"{spec.irr_eff:.2f}"),
    ])]
    if eo:
        st_.append(kv([("Parcel NDVI (Sentinel-2)", eo.get("ndvi")), ("Elevation (SRTM)", f"{eo.get('elevation')} m"),
                       ("Flood occurrence (JRC)", f"{(eo.get('flood_risk') or 0) * 100:.1f}%"), ("Land cover (MODIS)", eo.get("land_use"))]))
    st_ += [Paragraph("2. Water and hydraulic design", H2), kv([
        ("Season irrigation depth / volume", f"{r.annual_irrigation_mm:,.0f} mm / {r.annual_volume_m3:,.0f} m3"),
        ("Peak daily demand / design flow", f"{r.water_vol_m3_per_day:,.0f} m3/day / {r.flow_m3h:.1f} m3/h"),
        ("Static level + drawdown + friction + 1 m", f"{spec.gw_depth_m} + {spec.drawdown_m} + {spec.pipe_friction_m} + 1 = {r.tdh_m:.1f} m TDH"),
        ("Pump / PV array", f"{r.pump_kw:.2f} kW / {r.panel_kwp:.2f} kWp"),
        ("Share of pumping energy from solar", f"{r.solar_fraction:.0%}"),
        ("Land preparation", f"about {r.landprep_days:.0f} pumping days" if r.landprep_days > 0 else "n/a"),
    ]), fig_png(energy)]
    st_ += [Paragraph("3. Financial results", H2), kv([
        ("CAPEX (gross / after subsidy)", f"{bdt(r.total_capex)} / {bdt(r.total_capex_after_subsidy)} ({spec.subsidy_pct:.0%} subsidy)"),
        ("Annual benefits", f"diesel {bdt(r.annual_diesel_cost_saved)}; cold {bdt(r.annual_cold_revenue)}; "
                            f"e-rickshaw {bdt(r.annual_erickshaw_revenue)}; grid {bdt(r.annual_grid_income)}"),
        ("Annual O&M + grid import", bdt(r.annual_opex)),
        ("Net annual saving / simple payback", f"{bdt(r.net_annual_saving)} / {r.payback_years:.1f} years"),
        ("NPV 25 yr @ %.0f%% / IRR" % (spec.discount_rate * 100), f"{bdt(r.npv_25yr)} / {r.irr:.1%}"),
        ("LCOE solar (gross / subsidised)", f"BDT {r.lcoe_bdt_per_kwh:.1f} / {r.lcoe_subsidised:.1f} per kWh; diesel fuel only BDT {r.diesel_cost_per_kwh:.1f}"),
        ("Loan", f"{spec.loan_share:.0%} financed; service {bdt(r.annual_debt_service)}/yr; equity payback {r.equity_payback_years:.1f} yr"
         if spec.loan_share > 0 else "none"),
    ]), fig_png(cash)]
    st_ += [Paragraph("4. Environment and groundwater screen", H2), kv([
        ("Diesel displaced / CO2 avoided", f"{r.diesel_litres_per_year:,.0f} L/yr / {r.co2_tonnes_per_year:.2f} t/yr"),
        ("Groundwater screen", f"{r.safeguard['level']} (score {r.safeguard['score']}) - extraction ratio {r.safeguard['extraction_ratio']:.1f}x, lift {r.safeguard['lift_m']:.1f} m"),
    ])]
    for msg in r.safeguard["messages"]:
        st_.append(Paragraph("• " + msg, B))
    st_.append(Paragraph("5. Monthly balance", H2))
    cols = ["Month", "GHI kWh/m²/d", "ETo mm/d", "Rain mm", "Gross irrig. mm", "Volume m³", "Pump kWh", "PV kWh", "Surplus kWh"]
    hdr = ["Month", "GHI", "ETo", "Rain", "Irrig mm", "Vol m3", "Pump kWh", "PV kWh", "Surplus"]
    td = [hdr] + [[str(v) if i == 0 else f"{v:,.1f}" if i < 3 else f"{v:,.0f}" for i, v in enumerate(row)] for row in m[cols].values.tolist()]
    t = Table(td, repeatRows=1)
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f0e8")), ("ALIGN", (1, 0), (-1, -1), "RIGHT")]))
    st_ += [t, Paragraph("6. Components", H2)]
    c = r.components
    t2 = Table([["Component", "Specification", "Total (BDT)"]] + [[a, b, f"{x:,}" if x else ""] for a, b, x in
                                                                    zip(c["Component"], c["Specification"], c["Total (BDT)"])], repeatRows=1)
    t2.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f0e8")), ("ALIGN", (2, 0), (2, -1), "RIGHT")]))
    st_ += [t2, Spacer(1, 6), HRFlowable(width="100%", color=colors.lightgrey), Paragraph(
        "<b>Data status.</b> Unit costs, prices, cold-storage and e-rickshaw parameters are placeholder assumptions to be replaced by "
        "supplier quotes. ERA5-Land is a ~9 km reanalysis: calibrate GHI against local measurements where possible. The groundwater "
        "screen is an indicator, not a hydrogeological assessment. Hargreaves-Samani ETo can run high in humid monsoon months.", S)]
    doc.build(st_)
    return buf.getvalue()


# ── Page ─────────────────────────────────────────────────────────────────────
st.title("₿ Business Case Builder")
st.caption("Parcel-level Earth Engine climate drives water demand → pump → PV → cash flow · all money in BDT")
col_in, col_out = st.columns([1, 2])

with col_in:
    st.subheader("1 · Site")
    parcels_df = load_parcels()
    opts = {0: "— Manual location —"}
    for _, p in parcels_df.iterrows():
        opts[int(p["id"])] = f"{p['name']} ({p['district']}, {p['area_ha']:.2f} ha)"
    want = st.session_state.get("bc_parcel_id") or 0
    sel = st.selectbox("Parcel", list(opts), index=list(opts).index(want) if want in opts else 0,
                       format_func=lambda k: opts[k])
    P = parcels_df[parcels_df["id"] == sel].iloc[0] if sel else None

    districts = sorted(DISTRICTS["district"])
    d_def = P["district"] if P is not None and P["district"] in districts else st.session_state.get("bc_district", "Rajshahi")
    district = st.selectbox("District", districts, index=districts.index(d_def) if d_def in districts else 0, key=f"bc_d_{sel}")
    drow = DISTRICTS[DISTRICTS["district"] == district].iloc[0]
    lat0, lon0 = (float(P["lat_centroid"]), float(P["lon_centroid"])) if P is not None else (float(drow["lat"]), float(drow["lon"]))
    c1, c2 = st.columns(2)
    lat = c1.number_input("Latitude", value=lat0, format="%.4f", key=f"bc_lat_{sel}_{district}")
    lon = c2.number_input("Longitude", value=lon0, format="%.4f", key=f"bc_lon_{sel}_{district}")

    crops = list(CROP_ETC)
    c_def = P["crop_type"] if P is not None and P["crop_type"] in crops else st.session_state.get("bc_crop", "Boro Rice")
    crop = st.selectbox("Crop", crops, index=crops.index(c_def) if c_def in crops else 0, key=f"bc_crop_{sel}")
    planting = MONTHS.index(st.selectbox("Planting month", MONTHS, index=CROP_ETC[crop]["plant_month"] - 1,
                                         key=f"bc_pm_{crop}")) + 1
    unit = st.selectbox("Area unit", ["hectares", "acres", "bigha", "katha"])
    a_def = float(P["area_ha"]) if P is not None else float(st.session_state.get("bc_area_ha", 2.0))
    area_val = st.number_input(f"Farm area ({unit})", min_value=0.01, value=round(a_def / to_hectares(1, unit), 3),
                               step=0.1, key=f"bc_area_{sel}_{unit}")
    area_ha = to_hectares(area_val, unit)
    st.caption(f"= {area_ha:.3f} ha · {area_ha / 0.404686:.2f} acres · {area_ha / 0.133546:.1f} bigha")
    method = st.selectbox("Irrigation method", ["Flood (η 0.60)", "Sprinkler (η 0.75)", "Drip (η 0.90)"])
    irr_eff = {"Flood": 0.60, "Sprinkler": 0.75, "Drip": 0.90}[method.split()[0]]

    st.subheader("2 · Climate")
    clim = climate_panel(lat, lon, key="bc")

    st.subheader("3 · Water & pump")
    has_gw = P is not None and pd.notna(P.get("gw_depth_m"))
    gw_ref = float(P["gw_depth_m"]) if has_gw else float(drow["gw_depth_m"])
    st.caption("Static water level source: " + ("**measured, saved with the parcel**" if has_gw
                                                else f"district **placeholder** ({DISTRICTS_SOURCE}) - replace with a measured value"))
    gw_depth = st.slider("Static water level (m)", 1.0, 30.0, float(min(max(gw_ref, 1.0), 30.0)), 0.5, key=f"bc_gw_{sel}_{district}")
    trends = ["unknown", "stable", "declining"]
    t_def = P.get("gw_trend") if P is not None and P.get("gw_trend") in trends else "unknown"
    gw_trend = st.selectbox("Water-table trend (observed)", trends, index=trends.index(t_def), key=f"bc_tr_{sel}")
    drawdown = st.slider("Drawdown while pumping (m)", 0.5, 8.0, 2.0, 0.5)
    friction = st.slider("Pipe friction head (m)", 0.5, 8.0, 2.0, 0.5)
    pump_eff = st.slider("Pump + motor efficiency", 0.35, 0.75, 0.60, 0.01)
    hours = st.slider("Pumping window (h/day)", 4, 10, 8)
    ghi_factor = st.slider("GHI calibration factor", 0.80, 1.10, 1.00, 0.01,
                           help="ERA5-Land is a ~9 km reanalysis. Set <1 or >1 if you have local irradiance measurements.")

    wb, hyd = auto_design(crop, area_ha, planting, clim, gw_depth, drawdown, friction, pump_eff, irr_eff, hours, ghi_factor)
    auto = st.checkbox("Auto-size pump and PV from the water balance", value=True)
    if auto:
        pump_kw, panel_kwp = hyd.power_kw, hyd.panel_kwp
        st.caption(f"Design month **{MONTHS[wb['peak_month']]}** · {wb['peak_m3_day']:.0f} m³/day · {wb['design_flow_m3h']:.1f} m³/h "
                   f"→ **{pump_kw:.2f} kW** pump, **{panel_kwp:.2f} kWp** PV")
    else:
        pump_kw = st.slider("Pump power (kW)", 0.3, 30.0, float(max(0.3, round(hyd.power_kw, 1))), 0.1)
        panel_kwp = st.slider("PV array (kWp)", 0.5, 60.0, float(max(0.5, round(hyd.panel_kwp, 1))), 0.1)

    st.subheader("4 · Finance & add-ons")
    subsidy = st.slider("Government subsidy (%)", 0, 70, 30)
    loan_share = st.slider("Share financed by loan (%)", 0, 90, 0)
    fin_rate = st.slider("Loan interest (%)", 6, 24, 12)
    loan_years = st.slider("Loan term (years)", 2, 10, 5)
    cold_w = st.select_slider("Cold storage", [0, 500, 1500, 3000],
                              format_func=lambda x: {0: "None", 500: "500 W", 1500: "1.5 kW", 3000: "3 kW"}[x])
    cold_cap = None
    if cold_w:
        cold_cap = st.number_input("Cold-room capacity (kg)", 100.0, 100000.0, float(cold_w / 1000 * COLD_KG_PER_KW), 100.0,
                                   help="Placeholder default. Enter the real figure from your supplier.")
    n_er = st.slider("E-rickshaw charge points (48 V / 100 Ah)", 0, 10, 0)
    battery = st.slider("Battery (kWh)", 0.0, 20.0, 0.0, 1.0)
    ev = st.checkbox("Type-2 EV charger (3.3 kW)")
    with st.expander("Price & screening assumptions (placeholders — edit)"):
        diesel_price = st.number_input("Diesel (BDT/L)", 50.0, 250.0, float(DIESEL_PRICE_PER_LITRE), 1.0)
        grid_tariff = st.number_input("Grid tariff (BDT/kWh)", 1.0, 30.0, float(GRID_TARIFF_PER_KWH), 0.5)
        panel_cost = st.number_input("PV module cost (BDT/kWp)", 30000.0, 200000.0, float(PANEL_COST_PER_KWP), 1000.0)
        disc = st.slider("Discount rate (%)", 3, 15, int(DISCOUNT_RATE * 100))
        recharge = st.slider("Assumed net recharge (% of rainfall)", 5, 50, 20,
                             help="Screening assumption only. Replace with aquifer-specific recharge when known.")
    save_run = st.button("💾 Save this run to the database", type="primary")

spec = SystemSpec(
    district=district, crop_type=crop, area_ha=area_ha, pump_kw=pump_kw, panel_kwp=panel_kwp, clim=clim,
    planting_month=planting, irr_eff=irr_eff, lat=lat, lon=lon, gw_depth_m=gw_depth, drawdown_m=drawdown,
    pipe_friction_m=friction, pump_efficiency=pump_eff, irrigation_hours=hours, subsidy_pct=subsidy / 100,
    financing_rate=fin_rate / 100, loan_share=loan_share / 100, loan_years=loan_years, cold_storage_w=cold_w,
    cold_capacity_kg=cold_cap, n_erickshaw_chargers=n_er, battery_kwh=battery, ev_charger=ev,
    diesel_price=diesel_price, grid_tariff=grid_tariff, panel_cost_kwp=panel_cost, discount_rate=disc / 100,
    ghi_factor=ghi_factor, recharge_frac=recharge / 100, gw_trend=gw_trend)
r = size_system(spec)

if save_run:
    rid = save_business_case(spec, r, parcel_id=sel or None)
    st.sidebar.success(f"✅ Saved run #{rid}")

with col_out:
    if r.climate_source != "gee_era5_land":
        st.error("⚠️ **Climate is a static placeholder, not Earth Engine data.** Treat every number below as illustrative.")
    sg = r.safeguard
    {"High": st.error, "Medium": st.warning, "Low": st.success}[sg["level"]](
        f"**Groundwater screen: {sg['level']}** — " + " ".join(sg["messages"]))
    if r.peak_hours_needed > hours + 0.05:
        st.warning(f"Pump is undersized: peak month needs {r.peak_hours_needed:.1f} h/day at rated flow (window {hours} h).")
    if r.solar_fraction < 0.95:
        short = r.monthly.loc[r.monthly["Pump kWh"] > r.monthly["PV kWh"], "Month"].tolist()
        st.info(f"PV covers {r.solar_fraction:.0%} of pumping energy. Shortfall in: {', '.join(short)} (diesel/grid back-up or a larger array).")

    t_sum, t_clim, t_en, t_fin, t_rep = st.tabs(["Summary", "Climate & water", "Energy", "Finance", "Report"])

    with t_sum:
        a = st.columns(4)
        a[0].metric("TDH", f"{r.tdh_m:.1f} m")
        a[1].metric("Design flow", f"{r.flow_m3h:.1f} m³/h")
        a[2].metric("Pump / PV", f"{r.pump_kw:.2f} kW / {r.panel_kwp:.2f} kWp")
        a[3].metric("Solar share of pumping", f"{r.solar_fraction:.0%}")
        b = st.columns(4)
        b[0].metric("Season water", f"{r.annual_irrigation_mm:,.0f} mm")
        b[1].metric("Season volume", f"{r.annual_volume_m3:,.0f} m³")
        b[2].metric("Mean GHI (calibrated)", f"{r.ghi_mean:.2f} kWh/m²/d")
        b[3].metric("Mean cell temp", f"{r.tcell_mean:.1f} °C")
        c = st.columns(4)
        c[0].metric("CAPEX after subsidy", f"৳{r.total_capex_after_subsidy:,.0f}")
        c[1].metric("Net saving / yr", f"৳{r.net_annual_saving:,.0f}")
        c[2].metric("Payback", f"{r.payback_years:.1f} yr", delta="viable" if r.payback_years < 8 else "review", delta_color="normal" if r.payback_years < 8 else "off")
        c[3].metric("NPV 25 yr", f"৳{r.npv_25yr:,.0f}")
        d = st.columns(4)
        d[0].metric("IRR", f"{r.irr:.1%}")
        d[1].metric("LCOE solar", f"৳{r.lcoe_bdt_per_kwh:.1f}/kWh", help=f"Subsidised: ৳{r.lcoe_subsidised:.1f}. Diesel fuel alone: ৳{r.diesel_cost_per_kwh:.1f}/kWh.")
        d[2].metric("Diesel displaced", f"{r.diesel_litres_per_year:,.0f} L/yr")
        d[3].metric("CO₂ avoided", f"{r.co2_tonnes_per_year:.2f} t/yr")
        if r.landprep_days > 0:
            st.caption(f"Land preparation takes about **{r.landprep_days:.0f} pumping days** at rated flow (volume counted, not used for sizing).")
        if loan_share:
            st.caption(f"Loan: service ৳{r.annual_debt_service:,.0f}/yr · equity payback {r.equity_payback_years:.1f} yr · lowest debt-service cover {r.min_dscr:.2f}"
                       + ("  ⚠️ below 1.0 — repayments exceed savings in some year" if r.min_dscr < 1 else ""))
        with st.expander("🛰 Parcel satellite stats (Sentinel-2 · SRTM · JRC · MODIS)"):
            geo = extract_geometry(load_parcel_geojson(int(sel))) if sel else None
            if geo and geo.get("type") not in ("Polygon", "MultiPolygon"):
                geo = None
            loc_key = f"{lat:.4f},{lon:.4f}"
            if st.button("Fetch from Earth Engine", key="bc_eo_btn"):
                with st.spinner("Querying GEE…"):
                    st.session_state["bc_eo"] = {"key": loc_key, "val": get_parcel_eo(geo, lat, lon)}
            _s = st.session_state.get("bc_eo")
            eo = _s["val"] if _s and _s["key"] == loc_key else None      # never show another site's stats
            if eo:
                e = st.columns(4)
                e[0].metric("NDVI", eo["ndvi"] if eo["ndvi"] is not None else "no clear scene")
                e[1].metric("Elevation", f"{eo['elevation']} m")
                e[2].metric("Flood occurrence", f"{(eo['flood_risk'] or 0) * 100:.1f}%")
                e[3].metric("Land cover", eo["land_use"] or "n/a")
                if (eo["flood_risk"] or 0) > 0.3:
                    st.warning("High surface-water occurrence: use raised PV mounting and protect the inverter.")
            else:
                st.caption("Not fetched yet." if geo else "Link a saved parcel with a drawn outline for polygon-averaged values; otherwise a 50 m buffer is used.")

    with t_clim:
        m = r.monthly
        f = go.Figure()
        f.add_bar(x=m["Month"], y=m["GHI kWh/m²/d"], name="GHI kWh/m²/d", marker_color=AMBER)
        f.add_scatter(x=m["Month"], y=m["T cell °C"], name="Cell temp °C", yaxis="y2", line=dict(color=RED))
        f.update_layout(yaxis2=dict(overlaying="y", side="right", gridcolor=GRID), title="Solar resource and cell temperature (ERA5-Land)")
        st.plotly_chart(dark(f), use_container_width=True)
        f = go.Figure()
        f.add_bar(x=m["Month"], y=m["Rain mm"], name="Rain mm/month", marker_color=BLUE, opacity=0.6)
        f.add_bar(x=m["Month"], y=m["Gross irrig. mm"], name="Gross irrigation mm", marker_color=TEAL)
        f.add_scatter(x=m["Month"], y=m["ETo mm/d"] * 30, name="ETo ×30 (mm/month)", line=dict(color=AMBER, dash="dot"))
        f.update_layout(barmode="group", title="Rain, ETo and irrigation requirement")
        st.plotly_chart(dark(f), use_container_width=True)
        for n in clim.get("notes", []):
            st.caption("• " + n)

    with t_en:
        m = r.monthly
        f = go.Figure()
        f.add_bar(x=m["Month"], y=m["PV kWh"], name="PV generation", marker_color=GREEN)
        f.add_bar(x=m["Month"], y=m["Pump kWh"], name="Pump demand", marker_color=AMBER)
        f.add_scatter(x=m["Month"], y=m["Surplus kWh"], name="Surplus", line=dict(color=TEAL))
        f.update_layout(barmode="group", yaxis_title="kWh / month")
        st.plotly_chart(dark(f), use_container_width=True)
        st.dataframe(m, use_container_width=True, hide_index=True)

    with t_fin:
        cf = r.cashflow
        f = go.Figure(go.Scatter(x=cf["year"], y=cf["cumulative"], fill="tozeroy", line=dict(color=GREEN), name="Cumulative"))
        f.add_hline(y=0, line=dict(color=RED, dash="dash"))
        f.update_layout(title="Cumulative cash flow (BDT) — dip at year 12 = inverter replacement", xaxis_title="Year")
        st.plotly_chart(dark(f), use_container_width=True)
        items = [("Diesel saved", r.annual_diesel_cost_saved), ("Cold storage", r.annual_cold_revenue),
                 ("E-rickshaw", r.annual_erickshaw_revenue), ("Grid export", r.annual_grid_income),
                 ("O&M", -(r.total_capex * 0.015)), ("Grid import (cold)", -r.annual_grid_import_cost)]
        f = go.Figure(go.Bar(x=[v for _, v in items], y=[k for k, _ in items], orientation="h",
                             marker_color=[GREEN if v >= 0 else RED for _, v in items]))
        f.update_layout(title="Annual cash items (BDT)", showlegend=False)
        st.plotly_chart(dark(f, 280), use_container_width=True)

        s1, s2 = st.columns(2)
        subs = list(range(0, 75, 5))
        pb = [min(size_system(SystemSpec(**{**spec.__dict__, "subsidy_pct": s / 100})).payback_years, 30) for s in subs]
        f = go.Figure(go.Scatter(x=subs, y=pb, line=dict(color=TEAL)))
        f.add_hline(y=7, line=dict(color=AMBER, dash="dash"))
        f.update_layout(title="Payback vs subsidy", xaxis_title="Subsidy %", yaxis_title="years", showlegend=False)
        s1.plotly_chart(dark(f, 280), use_container_width=True)
        dps = list(range(70, 190, 10))
        pb = [min(size_system(SystemSpec(**{**spec.__dict__, "diesel_price": d})).payback_years, 30) for d in dps]
        f = go.Figure(go.Scatter(x=dps, y=pb, line=dict(color=AMBER)))
        f.update_layout(title="Payback vs diesel price", xaxis_title="BDT/L", yaxis_title="years", showlegend=False)
        s2.plotly_chart(dark(f, 280), use_container_width=True)
        st.dataframe(r.components, use_container_width=True, hide_index=True)

    with t_rep:
        area_label = f"{area_ha:.3f} ha ({area_ha / 0.404686:.2f} acres / {area_ha / 0.133546:.1f} bigha)"
        d1, d2 = st.columns(2)
        d1.download_button("⬇ Components + monthly (CSV)", pd.concat([r.components, r.monthly], axis=1).to_csv(index=False),
                           f"smartsip_{district.lower()}_case.csv", "text/csv")
        try:
            pdf = build_pdf(spec, r, area_label, eo)
            d2.download_button("📄 Download PDF report", pdf, f"smartsip_report_{district.lower()}.pdf", "application/pdf", type="primary")
        except Exception as exc:
            d2.error(f"PDF failed: {exc}")
        st.caption(f"Data status — climate: **{r.climate_source}** · district table: {DISTRICTS_SOURCE} · prices & add-on parameters: placeholders.")
        st.subheader("Saved runs")
        hist = load_recent_business_cases(50)
        if hist.empty:
            st.info("No saved runs yet.")
        else:
            st.dataframe(hist, use_container_width=True, hide_index=True)
