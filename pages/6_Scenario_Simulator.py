"""
Title: SMART-SIP+ DSS Prototype Scenario Simulator Page

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.techno_economic import run_national_scenario
from utils.db import save_scenario
from utils.footer import inject_footer


st.set_page_config(page_title="Scenario Simulator | SMART-SIP+", layout="wide")
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

st.title("⟳ Scenario Simulator")
st.caption("National roll-out arithmetic on explicit, editable assumptions (sidebar → National drivers). Not a forecast.")

with st.sidebar:
    st.header("Scenario Parameters")
    target_year      = st.slider("Target Year", 2026, 2040, 2035)
    replacement_rate = st.slider("Annual Pump Replacement Rate (%)", 2, 20, 8)
    subsidy_pct      = st.slider("Subsidy Level (%)", 0, 70, 35)
    cold_pct         = st.slider("Cold Storage Integration (%)", 0, 100, 25)
    ev_pct           = st.slider("E-Rickshaw Charger Adoption (% of sites)", 0, 50, 15)
    with st.expander("National drivers (placeholder assumptions — edit)", expanded=False):
        total_pumps = st.number_input("Diesel irrigation pumps (national)", 100_000, 10_000_000, 3_400_000, 50_000,
                                      help="Placeholder. Verify against the BADC minor-irrigation survey.")
        avg_kw = st.number_input("Average pump (kW)", 1.0, 20.0, 3.7, 0.1)
        hrs_day = st.number_input("Pumping hours per day", 1.0, 16.0, 8.0, 0.5)
        days_yr = st.number_input("Irrigation days per year", 30, 365, 120, 5,
                                  help="Boro ≈ 150 d, wheat ≈ 120 d; a pump serving one season ≈ 100-150.")
        from models.techno_economic import reference_system_cost
        unit_cost = st.number_input("Gross cost per system (BDT)", 50_000, 3_000_000,
                                    int(reference_system_cost(avg_kw)), 10_000,
                                    help="Default is derived from the same unit costs as the Business Case.")
    A = dict(total_pumps=int(total_pumps), avg_pump_kw=avg_kw, hours_per_day=hrs_day,
             days_per_year=float(days_yr), unit_cost_bdt=float(unit_cost))
    st.divider()
    compare = st.checkbox("Add comparison scenario")
    if compare:
        rate2 = st.slider("Comparison: Replacement Rate (%)", 2, 20, 4, key="r2")
        sub2  = st.slider("Comparison: Subsidy (%)", 0, 70, 20, key="s2")

results = run_national_scenario(
    target_year=target_year, replacement_rate_pct=replacement_rate,
    subsidy_pct=subsidy_pct, cold_integration_pct=cold_pct,
    ev_adoption_pct=ev_pct, **A,
)
with st.sidebar:
    if st.button("💾 Save this scenario"):
        sid = save_scenario({"target_year": target_year, "replacement_rate_pct": replacement_rate,
                             "subsidy_pct": subsidy_pct, "cold_integration_pct": cold_pct,
                             "ev_adoption_pct": ev_pct, "fin_model": "n/a"}, results)
        st.success(f"Saved scenario #{sid}")

final = {k: v[-1] for k, v in results.items() if isinstance(v, list) and k != "years"}

# ── KPIs ─────────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric(f"Pumps Replaced by {target_year}",
          f"{final['replaced_cumulative']/1e6:.2f}M",
          delta=f"{final['adoption_pct']:.0f}% of {A['total_pumps'] / 1e6:.1f}M")
k2.metric("CO₂ Avoided (Mt/yr)", f"{final['co2_saved_mt']:.2f} Mt")
k3.metric("Diesel Saved (GL/yr)", f"{final['diesel_saved_gl']:.2f} GL")
k4.metric("Total Investment (BDT bn)", f"৳{final['investment_bdt_bn']:.0f}bn")
k5.metric("Subsidy Cost (BDT bn)", f"৳{final['subsidy_cost_bdt_bn']:.0f}bn")
k6.metric("E-Rickshaw Chargers", f"{final['ev_charging_points']/1000:.0f}K")

st.divider()
col_l, col_r = st.columns(2)

# ── CO₂ trajectory ───────────────────────────────────────────────────────────
with col_l:
    st.subheader("CO₂ Reduction vs Diesel Baseline")
    baseline_co2 = results["baseline_co2_mt"]      # derived from the same per-pump assumptions
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=results["years"], y=[baseline_co2] * len(results["years"]),
        name="Diesel baseline",
        line=dict(color=RED, dash="dash", width=1.5), mode="lines"))
    fig.add_trace(go.Scatter(
        x=results["years"],
        y=[baseline_co2 - v for v in results["co2_saved_mt"]],
        name=f"SMART-SIP+ ({replacement_rate}%/yr, {subsidy_pct}% subsidy)",
        line=dict(color=GREEN, width=2),
        fill="tonexty", fillcolor="rgba(63,185,80,0.08)", mode="lines"))
    if compare:
        r2 = run_national_scenario(target_year, rate2, sub2, cold_pct, ev_pct, **A)
        fig.add_trace(go.Scatter(
            x=r2["years"],
            y=[baseline_co2 - v for v in r2["co2_saved_mt"]],
            name=f"Comparison ({rate2}%/yr, {sub2}% subsidy)",
            line=dict(color=TEAL, width=2, dash="dot"), mode="lines"))
    fig.update_layout(yaxis_title="Mt CO₂/yr (remaining)",
                      legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.2))
    st.plotly_chart(plotly_dark(fig), use_container_width=True)

with col_r:
    st.subheader("Diesel Litres Saved (Gigalitres/yr)")
    fig_d = go.Figure(go.Scatter(
        x=results["years"], y=results["diesel_saved_gl"],
        fill="tozeroy", fillcolor="rgba(210,153,34,0.08)",
        line=dict(color=AMBER, width=2), mode="lines", name="Diesel saved",
    ))
    if compare:
        r2_d = run_national_scenario(target_year, rate2, sub2, cold_pct, ev_pct, **A)
        fig_d.add_trace(go.Scatter(
            x=r2_d["years"], y=r2_d["diesel_saved_gl"],
            line=dict(color=TEAL, width=2, dash="dot"),
            name="Comparison", mode="lines"))
    fig_d.update_layout(yaxis_title="Gigalitres diesel/yr",
                        legend=dict(bgcolor="rgba(0,0,0,0)"))
    st.plotly_chart(plotly_dark(fig_d), use_container_width=True)

# ── Investment & subsidy ──────────────────────────────────────────────────────
col_i, col_s = st.columns(2)
with col_i:
    st.subheader("Cumulative Investment (BDT bn)")
    fig2 = go.Figure(go.Scatter(
        x=results["years"], y=results["investment_bdt_bn"],
        fill="tozeroy", fillcolor="rgba(88,166,255,0.08)",
        line=dict(color=BLUE, width=2), mode="lines"))
    fig2.update_layout(yaxis_title="BDT Billion")
    st.plotly_chart(plotly_dark(fig2), use_container_width=True)

with col_s:
    st.subheader("Cumulative Subsidy Cost (BDT bn)")
    fig_sub = go.Figure(go.Scatter(
        x=results["years"], y=results["subsidy_cost_bdt_bn"],
        fill="tozeroy", fillcolor="rgba(248,81,73,0.08)",
        line=dict(color=RED, width=2), mode="lines"))
    fig_sub.update_layout(yaxis_title="BDT Billion")
    st.plotly_chart(plotly_dark(fig_sub), use_container_width=True)

# ── Rollout bar ───────────────────────────────────────────────────────────────
st.subheader("Year-by-year Pump Replacement Rollout")
adop = results["adoption_pct"]
fig3 = go.Figure(go.Bar(
    x=results["years"], y=adop,
    marker=dict(color=[GREEN if a > 60 else AMBER if a > 30 else RED for a in adop]),
    text=[f"{a:.0f}%" for a in adop], textposition="outside",
))
fig3.add_hline(y=60, line=dict(color=AMBER, dash="dash"),
               annotation_text="60% national target", annotation_font_color=AMBER)
fig3.update_layout(yaxis=dict(range=[0, 105], title="% pumps converted"), showlegend=False)
st.plotly_chart(plotly_dark(fig3), use_container_width=True)

# ── Data table ────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Scenario Output Table")
df_out = pd.DataFrame({
    "Year":                   results["years"],
    "Pumps Replaced":         [f"{v:,.0f}" for v in results["replaced_cumulative"]],
    "Adoption (%)":           [f"{v:.1f}%" for v in results["adoption_pct"]],
    "CO₂ Saved (Mt/yr)":     [f"{v:.3f}" for v in results["co2_saved_mt"]],
    "Diesel Saved (GL/yr)":   [f"{v:.3f}" for v in results["diesel_saved_gl"]],
    "Investment (BDT bn)":    [f"৳{v:.1f}bn" for v in results["investment_bdt_bn"]],
    "Subsidy Cost (BDT bn)":  [f"৳{v:.1f}bn" for v in results["subsidy_cost_bdt_bn"]],
    "Cold Storage Nodes":     [f"{v:,.0f}" for v in results["cold_storage_nodes"]],
    "E-Rickshaw Points":      [f"{v:,.0f}" for v in results["ev_charging_points"]],
})
st.dataframe(df_out, use_container_width=True, hide_index=True)
st.download_button(
    "⬇ Download Scenario Data (CSV)",
    data=df_out.to_csv(index=False),
    file_name=f"smartsip_scenario_{target_year}_{replacement_rate}pct.csv",
    mime="text/csv",
)
