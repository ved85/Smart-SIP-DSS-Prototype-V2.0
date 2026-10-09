"""
Title: climate & Earth-Observation data fetcher via Google Earth Engine.

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""
import json
import math
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

try:                                     # .env is loaded here so every page sees it
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    load_dotenv()
except Exception:
    pass

GEE_PROJECT = os.getenv("GEE_PROJECT_ID", "dsstestv5")
ERA5L = "ECMWF/ERA5_LAND/DAILY_AGGR"
SCALE_M = 11132                          # ERA5-Land native cell
_B = {"ghi": "surface_solar_radiation_downwards_sum", "tmean": "temperature_2m",
      "tmax": "temperature_2m_max", "tmin": "temperature_2m_min",
      "precip": "total_precipitation_sum",
      "u": "u_component_of_wind_10m", "v": "v_component_of_wind_10m"}
DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
IGBP = {1: "Evergreen needleleaf forest", 2: "Evergreen broadleaf forest", 3: "Deciduous needleleaf forest",
        4: "Deciduous broadleaf forest", 5: "Mixed forest", 6: "Closed shrubland", 7: "Open shrubland",
        8: "Woody savanna", 9: "Savanna", 10: "Grassland", 11: "Permanent wetland", 12: "Cropland",
        13: "Urban / built-up", 14: "Cropland / natural vegetation mosaic", 15: "Snow and ice",
        16: "Barren", 17: "Water"}

_STATE = {"ok": None, "err": "", "t": 0.0}
_BANDS = {"v": None}


# ── GEE session ──────────────────────────────────────────────────────────────
def init_gee(force: bool = False) -> bool:
    """Initialise Earth Engine once per process. A failure is remembered for 45 s."""
    if _STATE["ok"] and not force:
        return True
    if _STATE["ok"] is False and not force and time.time() - _STATE["t"] < 45:
        return False
    try:
        import ee
        ee.Initialize(project=GEE_PROJECT)
        ee.Number(1).add(1).getInfo()
        _STATE.update(ok=True, err="")
    except Exception as exc:
        _STATE.update(ok=False, err=str(exc)[:400], t=time.time())
    return bool(_STATE["ok"])


def gee_status() -> dict:
    return {"ok": _STATE["ok"], "err": _STATE["err"], "project": GEE_PROJECT}


_init_gee = init_gee                                     # legacy names
_init_ee = init_gee


def gee_authenticate(mode=None) -> bool:                  # legacy signature
    return init_gee()


def _bands() -> list:
    """ERA5-Land bands that actually exist (checked once against the live catalogue)."""
    if _BANDS["v"] is None:
        import ee
        names = ee.ImageCollection(ERA5L).first().bandNames().getInfo()
        _BANDS["v"] = [b for b in _B.values() if b in names]
        for need in (_B["ghi"], _B["tmean"], _B["precip"]):
            if need not in _BANDS["v"]:
                _BANDS["v"] = None
                raise RuntimeError(f"ERA5-Land band '{need}' not found in {ERA5L}")
    return _BANDS["v"]


def _fail(exc) -> None:
    _STATE["err"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    print(f"[GEE] {_STATE['err']}")


# ── Solar geometry / ETo (pure python, testable offline) ─────────────────────
def extraterrestrial_radiation(lat_deg: float, doy: int) -> float:
    """FAO-56 eq. 21, MJ m-2 day-1."""
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi / 365 * doy)
    dec = 0.409 * math.sin(2 * math.pi / 365 * doy - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(dec))))
    return 24 * 60 / math.pi * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.sin(ws))


def hargreaves_eto(tmax: float, tmin: float, tmean: float, lat_deg: float, doy: int) -> float:
    """Hargreaves-Samani ETo (mm/day) from ERA5-Land temperatures. Tends to run high
    in humid monsoon months - calibrate against local pan / station data when available."""
    ra_mm = 0.408 * extraterrestrial_radiation(lat_deg, doy)
    return max(0.0, 0.0023 * (tmean + 17.8) * math.sqrt(max(tmax - tmin, 0.0)) * ra_mm)


def day_length_h(lat_deg: float, month: int) -> float:
    doy = date(2021, month, 15).timetuple().tm_yday
    phi = math.radians(lat_deg)
    dec = 0.409 * math.sin(2 * math.pi / 365 * doy - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(dec))))
    return 24 / math.pi * ws


def hourly_profile(ghi_daily: float, lat_deg: float, month: int) -> np.ndarray:
    """24-h irradiance (kWh/m2 per hour): half-sine over the real daylight window."""
    n = day_length_h(lat_deg, month)
    t = np.arange(24) + 0.5
    sr = 12 - n / 2
    shape = np.where((t > sr) & (t < 12 + n / 2), np.sin(np.pi * (t - sr) / n), 0.0)
    return shape / shape.sum() * ghi_daily if shape.sum() > 0 else shape


def simulate_hourly_generation(peak_kw: float, ghi_daily: float, panel_efficiency: float = 0.78,
                               lat: float | None = None, month: int | None = None) -> np.ndarray:
    if lat is not None and month is not None:
        irr = hourly_profile(ghi_daily, lat, month)
    else:
        h = np.arange(24)
        irr = np.exp(-0.5 * ((h - 12) / 2.5) ** 2)
        irr = irr / irr.sum() * ghi_daily
    return irr * peak_kw * panel_efficiency


# ── Parcel climatology (monthly) ─────────────────────────────────────────────
def clim_key(lat: float, lon: float, years: int = 3) -> str:
    y1 = date.today().year - 1
    return f"{lat:.3f}_{lon:.3f}_{y1 - years + 1}_{y1}"


def _build_clim(feats: list, lat: float, lon: float, y0: int, y1: int, bands: list) -> dict:
    by_m = {int(f["properties"]["month"]): f["properties"] for f in feats}
    ghi, tmean, tmax, tmin, rain, eto = [], [], [], [], [], []
    approx_dtr = _B["tmax"] not in bands
    for m in range(1, 13):
        p = by_m.get(m) or {}
        if p.get(_B["ghi"]) is None or p.get(_B["tmean"]) is None or p.get(_B["precip"]) is None:
            raise ValueError(f"ERA5-Land returned no data for month {m}")
        g = p[_B["ghi"]] / 3.6e6                                  # J m-2 -> kWh m-2 per day
        tm = p[_B["tmean"]] - 273.15
        tx = p[_B["tmax"]] - 273.15 if p.get(_B["tmax"]) is not None else tm + 4.0
        tn = p[_B["tmin"]] - 273.15 if p.get(_B["tmin"]) is not None else tm - 4.0
        doy = date(2021, m, 15).timetuple().tm_yday
        ghi.append(round(g, 3)); tmean.append(round(tm, 2)); tmax.append(round(tx, 2)); tmin.append(round(tn, 2))
        rain.append(round(max(0.0, p[_B["precip"]]) * 1000 * DAYS[m - 1], 1))   # m/day -> mm/month
        eto.append(round(hargreaves_eto(tx, tn, tm, lat, doy), 2))
    notes = [f"ERA5-Land cell (~9 km) containing the point, mean of {y0}-{y1}.",
             "ETo: Hargreaves-Samani from ERA5-Land Tmax/Tmin/Tmean."]
    if approx_dtr:
        notes.append("Tmax/Tmin bands unavailable: diurnal range approximated as +/-4 C.")
    return {"source": "gee_era5_land", "lat": lat, "lon": lon, "y0": y0, "y1": y1, "ghi": ghi,
            "tmean": tmean, "tmax": tmax, "tmin": tmin, "precip_mm": rain, "eto": eto, "notes": notes}


def get_parcel_climate(lat: float, lon: float, years: int = 3, allow_fetch: bool = True,
                       refresh: bool = False) -> dict | None:
    """
    Monthly climatology (Jan..Dec) at a point from GEE ERA5-Land: GHI kWh/m2/day, T mean/max/min,
    rain mm/month, ETo mm/day. Cached in SQLite. Returns None if unavailable (see gee_status()).
    One server-side call builds all 12 months.
    """
    from utils.db import load_parcel_climate, save_parcel_climate, log_job_start, log_job_end
    key = clim_key(lat, lon, years)
    if not refresh:
        hit = load_parcel_climate(key)
        if hit:
            return hit
    if not allow_fetch or not init_gee():
        return None
    y1 = date.today().year - 1
    y0 = y1 - years + 1
    jid = log_job_start("GEE ERA5-Land climatology", "GEE", "on demand")
    t0 = time.time()
    try:
        import ee
        bands = _bands()
        pt = ee.Geometry.Point([lon, lat])
        col = ee.ImageCollection(ERA5L).filterDate(f"{y0}-01-01", f"{y1 + 1}-01-01").select(bands)

        def per_month(m):
            m = ee.Number(m)
            img = col.filter(ee.Filter.calendarRange(m, m, "month")).mean()
            return ee.Feature(None, img.reduceRegion(ee.Reducer.first(), pt, SCALE_M)).set("month", m)

        feats = ee.FeatureCollection(ee.List.sequence(1, 12).map(per_month)).getInfo()["features"]
        clim = _build_clim(feats, lat, lon, y0, y1, bands)
        save_parcel_climate(key, lat, lon, clim["source"], y0, y1, clim)
        log_job_end(jid, records=12, duration_s=round(time.time() - t0, 2))
        return clim
    except Exception as exc:
        _fail(exc)
        log_job_end(jid, status="error", error_msg=str(exc)[:200])
        return None


def static_climate(lat: float, lon: float) -> dict:
    """
    OFFLINE PLACEHOLDER climatology (nearest district GHI + generic monsoon pattern).
    Used only when GEE is unreachable. Always labelled source='static_placeholder'.
    """
    from data.bangladesh_data import DISTRICTS, MONTHLY_GHI, ETO_BY_MONTH
    d = np.hypot(DISTRICTS["lat"] - lat, DISTRICTS["lon"] - lon)
    near = DISTRICTS.iloc[int(d.argmin())]["district"]
    tm = [19.5, 22.5, 27.0, 29.5, 29.5, 29.5, 29.0, 29.0, 29.0, 27.5, 24.0, 20.0]
    return {"source": "static_placeholder", "lat": lat, "lon": lon,
            "ghi": list(MONTHLY_GHI.get(near, MONTHLY_GHI["Rajshahi"])), "tmean": tm,
            "tmax": [t + 5.5 for t in tm], "tmin": [t - 5.5 for t in tm],
            "precip_mm": [8, 25, 60, 140, 300, 450, 520, 420, 300, 160, 30, 6],
            "eto": list(ETO_BY_MONTH),
            "notes": [f"STATIC PLACEHOLDER (nearest district: {near}). Not Earth Engine data."]}


# ── Daily ERA5-Land series ───────────────────────────────────────────────────
def _iso(s: str) -> str:
    s = str(s)
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 and s.isdigit() else s[:10]


def fetch_gee_climate(lat: float, lon: float, start: str, end: str,
                      use_cache: bool = True) -> pd.DataFrame | None:
    """Daily ERA5-Land series at a point. Returns None if GEE is unavailable."""
    from utils.db import load_climate_cache, cache_climate, log_job_start, log_job_end
    s, e = _iso(start), _iso(end)
    days = (datetime.strptime(e, "%Y-%m-%d") - datetime.strptime(s, "%Y-%m-%d")).days + 1
    if use_cache:
        c = load_climate_cache(lat, lon, s, e)
        if c is not None and len(c) >= 0.9 * days and "tmax" in c and c["tmax"].notna().any():
            return c
    if not init_gee():
        return None
    jid = log_job_start("GEE ERA5-Land daily", "GEE", "on demand")
    t0 = time.time()
    try:
        import ee
        bands = _bands()
        pt = ee.Geometry.Point([lon, lat])
        rows, cur = [], datetime.strptime(s, "%Y-%m-%d")
        end_dt = datetime.strptime(e, "%Y-%m-%d") + timedelta(days=1)
        while cur < end_dt:                                    # chunks stay under the 5000-feature cap
            nxt = min(cur + timedelta(days=1500), end_dt)
            col = ee.ImageCollection(ERA5L).filterDate(cur.strftime("%Y-%m-%d"), nxt.strftime("%Y-%m-%d")).select(bands)
            fc = col.map(lambda img: ee.Feature(None, img.reduceRegion(ee.Reducer.first(), pt, SCALE_M))
                         .set("date", img.date().format("YYYY-MM-dd")))
            for f in fc.getInfo()["features"]:
                p = f["properties"]
                if p.get(_B["ghi"]) is None:
                    continue
                u, v = p.get(_B["u"]) or 0.0, p.get(_B["v"]) or 0.0
                tm = p[_B["tmean"]] - 273.15
                rows.append({"date": pd.to_datetime(p["date"]), "ghi": max(0.0, p[_B["ghi"]] / 3.6e6),
                             "temp": tm,
                             "tmax": (p[_B["tmax"]] - 273.15) if p.get(_B["tmax"]) is not None else None,
                             "tmin": (p[_B["tmin"]] - 273.15) if p.get(_B["tmin"]) is not None else None,
                             "precip_mm": max(0.0, (p.get(_B["precip"]) or 0.0) * 1000),
                             "wind_speed": math.hypot(u, v), "source": "gee_era5_land"})
            cur = nxt
        if not rows:
            raise RuntimeError("ERA5-Land returned no rows for this period")
        df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        cache_climate(df, lat, lon, source="gee_era5_land")
        log_job_end(jid, records=len(df), duration_s=round(time.time() - t0, 2))
        return df
    except Exception as exc:
        _fail(exc)
        log_job_end(jid, status="error", error_msg=str(exc)[:200])
        return None


fetch_nasa_power = fetch_gee_climate                          # legacy alias (now GEE)


def get_monthly_irradiance(district: str) -> list:             # offline fallback only
    from data.bangladesh_data import MONTHLY_GHI
    return MONTHLY_GHI.get(district, MONTHLY_GHI["Rajshahi"])


def district_climate_table(allow_fetch: bool = False) -> pd.DataFrame:
    """Annual-mean GHI per district: ERA5-Land where cached/fetched, else NaN."""
    from data.bangladesh_data import DISTRICTS
    rows = []
    for _, r in DISTRICTS.iterrows():
        c = get_parcel_climate(float(r["lat"]), float(r["lon"]), allow_fetch=allow_fetch)
        rows.append({"district": r["district"],
                     "ghi_live": float(np.average(c["ghi"], weights=DAYS)) if c else np.nan,
                     "precip_mm": float(np.sum(c["precip_mm"])) if c else np.nan})
    return pd.DataFrame(rows)


# ── Parcel Earth-Observation summary ─────────────────────────────────────────
def get_parcel_eo(geometry: dict | None, lat: float, lon: float, date_str: str | None = None,
                  allow_fetch: bool = True, buffer_m: int = 50) -> dict | None:
    """
    Sentinel-2 NDVI (60-day median to date_str), SRTM elevation, JRC flood occurrence and MODIS
    land cover, averaged over the parcel polygon (or a small buffer if no polygon). SQLite-cached.
    """
    from utils.db import load_gee_result, save_gee_result, log_job_start, log_job_end
    date_str = date_str or (date.today() - timedelta(days=15)).isoformat()
    la, lo = round(lat, 4), round(lon, 4)
    c = load_gee_result(la, lo, date_str)
    if c and (c["ndvi"] is not None or c["elevation"] is not None):
        return {"ndvi": c["ndvi"], "elevation": c["elevation"], "flood_risk": c["flood_risk"],
                "land_use": c["land_use"], "source": f"cache ({c['fetched_at']})"}
    if not allow_fetch or not init_gee():
        return None
    jid = log_job_start("GEE parcel EO summary", "GEE", "on demand")
    t0 = time.time()
    try:
        import ee
        geom = ee.Geometry(geometry) if geometry else ee.Geometry.Point([lon, lat]).buffer(buffer_m)
        d1 = datetime.strptime(date_str, "%Y-%m-%d")
        s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(geom)
              .filterDate((d1 - timedelta(days=60)).strftime("%Y-%m-%d"), (d1 + timedelta(days=1)).strftime("%Y-%m-%d"))
              .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30)))
        n_scenes = s2.size().getInfo()
        red = dict(reducer=ee.Reducer.mean(), geometry=geom, bestEffort=True, maxPixels=1e9)
        parts = {
            "elev": ee.Image("USGS/SRTMGL1_003").reduceRegion(scale=30, **red).get("elevation"),
            "flood": ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)
                       .reduceRegion(scale=30, **red).get("occurrence"),
            "lc": ee.ImageCollection("MODIS/061/MCD12Q1").sort("system:time_start", False).first()
                    .select("LC_Type1").reduceRegion(ee.Reducer.first(), ee.Geometry.Point([lon, lat]), 500).get("LC_Type1"),
        }
        if n_scenes:
            parts["ndvi"] = s2.median().normalizedDifference(["B8", "B4"]).rename("NDVI") \
                              .reduceRegion(scale=10, **red).get("NDVI")
        v = ee.Dictionary(parts).getInfo()
        out = {"ndvi": round(v["ndvi"], 3) if v.get("ndvi") is not None else None,
               "elevation": round(v["elev"], 1) if v.get("elev") is not None else None,
               "flood_risk": round((v.get("flood") or 0) / 100, 3),
               "land_use": IGBP.get(int(v["lc"]), str(v["lc"])) if v.get("lc") is not None else None,
               "n_scenes": n_scenes, "source": "gee"}
        save_gee_result(la, lo, date_str, ndvi=out["ndvi"], elevation=out["elevation"],
                        land_use=out["land_use"], flood_risk=out["flood_risk"])
        log_job_end(jid, records=1, duration_s=round(time.time() - t0, 2))
        return out
    except Exception as exc:
        _fail(exc)
        log_job_end(jid, status="error", error_msg=str(exc)[:200])
        return None


# ── Streamlit helper shared by pages ─────────────────────────────────────────
def climate_panel(lat: float, lon: float, key: str = "clim") -> dict:
    """
    Resolve monthly climate for a point and show where it came from.
    Order: SQLite cache -> GEE (once; failure is remembered until 'Retry') -> static placeholder.
    Always returns a usable dict; clim['source'] says which one it is.
    """
    import streamlit as st
    ck = clim_key(lat, lon)
    failed = st.session_state.setdefault("_clim_failed", {})
    clim = get_parcel_climate(lat, lon, allow_fetch=False)
    if clim is None and not failed.get(ck):
        with st.spinner("Fetching ERA5-Land climate from Google Earth Engine…"):
            clim = get_parcel_climate(lat, lon)
        if clim is None:
            failed[ck] = gee_status()["err"] or "Earth Engine unavailable"
    if clim is None:
        st.warning(f"⚠️ Earth Engine unavailable: {failed.get(ck)}\n\nUsing a **static placeholder** climate - "
                   "results are illustrative only. Check the 🛰 GEE Test page.")
        if st.button("↻ Retry Earth Engine", key=f"{key}_retry"):
            failed.pop(ck, None)
            init_gee(force=True)
            st.rerun()
        return static_climate(lat, lon)
    st.caption(f"🛰 **ERA5-Land** · cell containing {lat:.4f}, {lon:.4f} · mean {clim['y0']}–{clim['y1']} · ~9 km grid")
    if st.button("↻ Re-fetch from GEE", key=f"{key}_refetch"):
        with st.spinner("Re-fetching…"):
            if get_parcel_climate(lat, lon, refresh=True) is None:
                st.error(f"Re-fetch failed: {gee_status()['err']}")
        st.rerun()
    return clim
