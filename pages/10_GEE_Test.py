"""
Title: SMART-SIP+ DSS Prototype Google Earth Engine API Connection Tester Page.

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""
import streamlit as st
import os, sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.footer import inject_footer
import utils.climate  # noqa: F401  (loads .env so GEE_PROJECT_ID is visible)
from utils.db import save_gee_result
from data.bangladesh_data import DISTRICTS

st.set_page_config(page_title="GEE Test | SMART-SIP+", layout="wide")
inject_footer()

st.title("🛰 Google Earth Engine — Connection Test")
st.caption("Live diagnostics + real queries using your `earthengine authenticate` "
           "credentials. This page ignores APP_MODE.")

# ── 1 · Environment diagnostics ────────────────────────────────────────────
st.subheader("1 · Environment diagnostics")
cred_paths = [
    os.path.expanduser("~/.config/earthengine/credentials"),
    os.path.expanduser("~/.config/earthengine/credentials.json"),
]
cred_found = next((p for p in cred_paths if os.path.exists(p)), None)

try:
    import ee
    ee_version = ee.__version__
except Exception as e:
    ee = None
    ee_version = f"import failed: {e}"

d1, d2, d3, d4 = st.columns(4)
d1.metric("earthengine-api", ee_version if ee else "❌ MISSING")
d2.metric("Credentials file", "✅ found" if cred_found else "❌ not found")
d3.metric("APP_MODE", os.getenv("APP_MODE", "demo (default)"))
d4.metric("GEE_PROJECT_ID", os.getenv("GEE_PROJECT_ID", "not set"))

if ee is None:
    st.error("earthengine-api not installed → `pip install earthengine-api`")
    st.stop()
if cred_found:
    st.caption(f"Credentials: `{cred_found}`")
else:
    st.error("No EE credentials found for this OS user. Run `earthengine authenticate` "
             "in the SAME terminal / user account that runs Streamlit.")
    st.stop()

project_id = st.text_input(
    "Cloud project ID (only needed if ee.Initialize() complains about a project)",
    value=os.getenv("GEE_PROJECT_ID", ""),
    placeholder="e.g. my-gee-project-123456",
)

def ee_ready(project: str):
    """Probe → initialise if needed. Returns (ok, message)."""
    try:
        ee.Number(1).add(1).getInfo()
        return True, "already initialised in this server process"
    except Exception:
        pass
    try:
        ee.Initialize(project=project or None)
        ee.Number(1).add(1).getInfo()
        return True, "ee.Initialize() succeeded"
    except Exception as e:
        return False, str(e)

# ── 2 · Initialise ─────────────────────────────────────────────────────────
st.subheader("2 · Initialise connection")
if st.button("🔌 Initialise Earth Engine", type="primary"):
    ok, msg = ee_ready(project_id.strip())
    st.session_state["gee_ok"]  = ok
    st.session_state["gee_msg"] = msg
    if ok:
        st.success(f"✅ {msg}")
    else:
        st.error(f"❌ Initialisation failed:\n\n{msg}")
        st.info(
            "Common fixes:\n"
            "- Error mentions **project** → paste your Cloud project ID above "
            "(see https://console.cloud.google.com or Code Editor top-left).\n"
            "- Error mentions **credentials** → re-run `earthengine authenticate` "
            "as the user that runs Streamlit.\n"
            "- Behind a proxy → set HTTPS_PROXY before launching Streamlit."
        )

if "gee_ok" not in st.session_state:
    st.info("Press **Initialise Earth Engine** to continue.")
    st.stop()
if not st.session_state["gee_ok"]:
    st.warning(f"Last attempt failed: {st.session_state.get('gee_msg')} — fix and retry above.")
    st.stop()

# ── 3 · Server round-trip ──────────────────────────────────────────────────
st.subheader("3 · Server round-trip")
ok, msg = ee_ready(project_id.strip())
if not ok:
    st.error(f"❌ {msg}")
    st.stop()
st.success(f"✅ Round-trip OK — ee.Number(1).add(1).getInfo() = 2 ({msg})")

# ── 4 · Live dataset queries ───────────────────────────────────────────────
st.subheader("4 · Live dataset queries")
col_a, col_b = st.columns([1, 2])
with col_a:
    district = st.selectbox("Test location", sorted(DISTRICTS["district"].tolist()))
    row = DISTRICTS[DISTRICTS["district"] == district].iloc[0]
    lat = st.number_input("Latitude",  value=float(row["lat"]), format="%.4f")
    lon = st.number_input("Longitude", value=float(row["lon"]), format="%.4f")
    qdate = st.date_input("Query date", value=datetime.today() - timedelta(days=15))
    date_str = qdate.strftime("%Y-%m-%d")
    run = st.button("🛰 Run all GEE queries", type="primary")

with col_b:
    if not run:
        st.info("Pick a location/date on the left, then press **Run all GEE queries**.")
    else:
        point = ee.Geometry.Point(lon, lat)
        results = {}

        with st.spinner("A · SRTM 30 m elevation …"):
            t0 = datetime.now()
            try:
                elev = ee.Image("USGS/SRTMGL1_003").reduceRegion(
                    ee.Reducer.mean(), point, 30).getInfo().get("elevation")
                elev = round(elev, 1) if elev is not None else None
                results["elevation"] = elev
                st.metric("A · Elevation (SRTM 30 m)", f"{elev} m asl",
                          delta=f"{(datetime.now()-t0).total_seconds():.1f}s")
            except Exception as e:
                results["elevation"] = None
                st.error(f"A · SRTM failed: {e}")

        with st.spinner("B · Sentinel-2 SR NDVI …"):
            t0 = datetime.now()
            try:
                end_date = (qdate + timedelta(days=30)).strftime("%Y-%m-%d")
                s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                      .filterBounds(point).filterDate(date_str, end_date)
                      .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
                      .sort("CLOUDY_PIXEL_PERCENTAGE").first())
                ndvi_img = s2.select("B8").subtract(s2.select("B4")) \
                             .divide(s2.select("B8").add(s2.select("B4")))
                ndvi = ndvi_img.reduceRegion(
                    ee.Reducer.median(), point, 10).getInfo().get("B8")
                ndvi = round(ndvi, 3) if ndvi is not None else None
                results["ndvi"] = ndvi
                st.metric("B · NDVI (Sentinel-2)",
                          ndvi if ndvi is not None else "no cloud-free scene",
                          delta=f"{(datetime.now()-t0).total_seconds():.1f}s")
                if ndvi is None:
                    st.warning("No cloud-free S2 scene in ±30 d — pick an earlier date.")
            except Exception as e:
                results["ndvi"] = None
                st.error(f"B · Sentinel-2 failed: {e}")

        with st.spinner("C · JRC Global Surface Water (flood risk) …"):
            t0 = datetime.now()
            try:
                occ = (ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence")
                       .reduceRegion(ee.Reducer.mean(), point.buffer(500), 30)
                       .getInfo().get("occurrence"))
                flood = round((occ or 0) / 100, 3)
                results["flood"] = flood
                st.metric("C · Flood risk (JRC GSW)", f"{flood*100:.1f}%",
                          delta=f"{(datetime.now()-t0).total_seconds():.1f}s")
            except Exception as e:
                results["flood"] = None
                st.error(f"C · JRC GSW failed: {e}")

        with st.spinner("D · MODIS MCD12Q1 land cover …"):
            try:
                lc = (ee.ImageCollection("MODIS/061/MCD12Q1")
                      .sort("system:time_start", False).first()
                      .select("LC_Type1")
                      .reduceRegion(ee.Reducer.first(), point, 500)
                      .getInfo().get("LC_Type1"))
                results["land_use"] = str(lc) if lc is not None else None
                st.metric("D · MODIS land-cover class (LC_Type1)",
                          lc if lc is not None else "n/a")
            except Exception as e:
                results["land_use"] = None
                st.error(f"D · MODIS failed: {e}")

        with st.spinner("E · ERA5-Land daily bands …"):
            try:
                col = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")
                names = col.first().bandNames().getInfo()
                need = ["surface_solar_radiation_downwards_sum", "temperature_2m", "temperature_2m_max",
                        "temperature_2m_min", "total_precipitation_sum"]
                miss = [b for b in need if b not in names]
                last = ee.Date(col.sort("system:time_start", False).first().get("system:time_start")) \
                         .format("YYYY-MM-dd").getInfo()
                st.metric("E · ERA5-Land latest day", last,
                          delta="all required bands present" if not miss else f"MISSING: {miss}",
                          delta_color="normal" if not miss else "inverse")
            except Exception as e:
                st.error(f"E · ERA5-Land failed: {e}")

        try:
            save_gee_result(lat, lon, date_str,
                            ndvi=results["ndvi"],
                            elevation=results["elevation"],
                            flood_risk=results["flood"])
            st.success("💾 Results cached into SQLite `gee_results` table.")
        except Exception as e:
            st.warning(f"SQLite cache skipped: {e}")

# ── 5 · Switch the main app on ─────────────────────────────────────────────
st.divider()
st.subheader("5 · Enable GEE on the Climate & GEE page")
st.code(
    "# .env  (project root — now auto-loaded by utils/climate.py)\n"
    "APP_MODE=production\n"
    f"GEE_PROJECT_ID={project_id.strip() or '<your-cloud-project-id>'}\n",
    language="bash",
)
st.caption(
    "Alternatively (no .env): stop Streamlit, run "
    "`set APP_MODE=production` (Windows) or `export APP_MODE=production` (Linux/mac) "
    "in the same terminal, then `streamlit run app.py`. "
    "The Climate & GEE page will then show **✅ GEE Authenticated** and enable "
    "the *Run GEE Query* button."
)