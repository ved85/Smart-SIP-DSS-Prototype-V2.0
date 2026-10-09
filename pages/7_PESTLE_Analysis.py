"""
Title: SMART-SIP+ DSS Prototype PESTLE Analysis Page

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""

import streamlit as st
import plotly.graph_objects as go
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.bangladesh_data import PESTLE_SCORES
from utils.footer import inject_footer


st.set_page_config(page_title="PESTLE | SMART-SIP+", layout="wide")
inject_footer()

PAPER = "#161b22"; PLOT  = "#0d1117"; GRID = "#30363d"; TEXT = "#e6edf3"
GREEN = "#3fb950"; AMBER = "#d29922"; RED   = "#f85149"
TEAL  = "#39c5cf"; BLUE  = "#58a6ff"; PURPLE= "#bc8cff"

PESTLE_COLOURS = {
    "Political": GREEN, "Economic": BLUE,
    "Social": AMBER, "Technological": TEAL,
    "Legal": PURPLE, "Environmental": RED,
}

st.title("⊞ PESTLE Analysis")
st.caption("Socio-technical feasibility framework — scores are expert-judgement placeholders (edit PESTLE_SCORES in data/bangladesh_data.py)")

# ── Radar chart ────────────────────────────────────────────────────────────────
labels = list(PESTLE_SCORES.keys())
scores = [PESTLE_SCORES[k]["score"] for k in labels]

fig = go.Figure()
fig.add_trace(go.Scatterpolar(
    r=scores + [scores[0]],
    theta=labels + [labels[0]],
    fill="toself",
    fillcolor="rgba(63,185,80,0.12)",
    line=dict(color=GREEN, width=2),
    name="Feasibility Score",
    marker=dict(color=GREEN, size=8),
))

# Add thresholds
fig.add_trace(go.Scatterpolar(
    r=[7]*6 + [7],
    theta=labels + [labels[0]],
    line=dict(color=AMBER, dash="dash", width=1),
    name="Target threshold (7.0)",
    fill=None, marker=dict(size=0)
))

fig.update_layout(
    polar=dict(
        bgcolor=PLOT,
        radialaxis=dict(
            visible=True, range=[0,10],
            gridcolor=GRID, linecolor=GRID,
            tickfont=dict(color="#7d8590", size=9),
        ),
        angularaxis=dict(
            gridcolor=GRID, linecolor=GRID,
            tickfont=dict(color=TEXT, size=12),
        ),
    ),
    paper_bgcolor=PAPER,
    font=dict(color=TEXT, family="IBM Plex Mono, monospace"),
    legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.1),
    margin=dict(t=20, b=60, l=80, r=80),
    height=420,
)
st.plotly_chart(fig, use_container_width=True)

# ── Score bar ──────────────────────────────────────────────────────────────────
st.subheader("Factor Scores")
score_cols = st.columns(6)
for i, (k, data) in enumerate(PESTLE_SCORES.items()):
    with score_cols[i]:
        colour = PESTLE_COLOURS[k]
        score = data["score"]
        st.markdown(f"""
        <div style='text-align:center;padding:10px;background:#161b22;
                    border:1px solid {colour};border-radius:6px'>
          <div style='font-size:1.6rem;font-weight:300;color:{colour}'>{score}</div>
          <div style='font-size:0.65rem;color:#7d8590;font-family:monospace'>{k.upper()}</div>
          <div style='font-size:0.65rem;color:#7d8590'>/10</div>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# ── Detailed cards ─────────────────────────────────────────────────────────────
st.subheader("Detailed Factor Analysis")

cols = st.columns(3)
for i, (dimension, data) in enumerate(PESTLE_SCORES.items()):
    col = cols[i % 3]
    colour = PESTLE_COLOURS[dimension]
    score = data["score"]
    rating = "✅ Strong" if score >= 7.5 else "⚠️ Moderate" if score >= 6.0 else "🔴 Weak"

    with col:
        with st.expander(f"{dimension} — {score}/10 — {rating}", expanded=True):
            for factor in data["factors"]:
                st.markdown(f"— {factor}")

# ── Waterfall: composite score ─────────────────────────────────────────────────
st.divider()
st.subheader("Composite Feasibility Score Breakdown")
measures = ["relative"] * 6 + ["total"]
fig2 = go.Figure(go.Waterfall(
    orientation="v",
    measure=measures,
    x=labels + ["Overall"],
    y=[s/len(labels) for s in scores] + [sum(scores)/len(scores)],
    connector=dict(line=dict(color=GRID)),
    decreasing=dict(marker_color=RED),
    increasing=dict(marker_color=GREEN),
    totals=dict(marker_color=TEAL),
    text=[f"{s/len(labels):.2f}" for s in scores] + [f"{sum(scores)/len(scores):.1f}"],
    textposition="outside",
))
fig2.update_layout(
    paper_bgcolor=PAPER, plot_bgcolor=PLOT,
    font=dict(color=TEXT, family="IBM Plex Mono", size=11),
    xaxis=dict(gridcolor=GRID),
    yaxis=dict(gridcolor=GRID, title="Contribution to composite score"),
    margin=dict(l=10,r=10,t=20,b=10),
    showlegend=False,
)
st.plotly_chart(fig2, use_container_width=True)

overall = sum(scores) / len(scores)
if overall >= 7:
    st.success(f"**Overall Feasibility: {overall:.1f}/10 — High feasibility.** Conditions are broadly supportive for solar irrigation transition.")
elif overall >= 6:
    st.warning(f"**Overall Feasibility: {overall:.1f}/10 — Moderate feasibility.** Targeted interventions needed in weaker dimensions.")
else:
    st.error(f"**Overall Feasibility: {overall:.1f}/10 — Significant barriers.** Policy reform required before large-scale deployment.")
