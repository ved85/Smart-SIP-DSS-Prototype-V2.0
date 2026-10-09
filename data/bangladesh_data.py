"""
Title: Bangladesh reference tables for SMART-SIP+.

DATA STATUS - read before publishing anything:
  * Crop Kc stages (CROP_ETC)  : FAO-56 style values; percolation / land-prep are
                                 typical-paddy assumptions. Verify locally.
  * DISTRICTS                  : ILLUSTRATIVE PLACEHOLDERS (adoption %, pump counts,
                                 groundwater depth/trend, aquifer risk, GHI). They are
                                 NOT survey data. Drop a file `data/districts.csv` with the
                                 same columns to replace them with real BBS / BADC / BWDB
                                 figures - the app then reports the CSV as its source.
  * MONTHLY_GHI / ETO_BY_MONTH : offline fallback only; live climate comes from GEE ERA5-Land.
  * PESTLE_SCORES              : expert-judgement placeholders, edit as needed.

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""

import pandas as pd
import numpy as np

# ── District-level reference data ─────────────────────────────────────────────
DISTRICTS = pd.DataFrame([
    {"district": "Rajshahi",   "division": "Rajshahi",   "lat": 24.37, "lon": 88.60,
     "ghi": 5.1, "diesel_pumps": 142000, "solar_pct": 87, "priority": "Low",
     "area_km2": 2407, "crop_zone": "Boro Rice / Wheat",
     "gw_depth_m": 6.5,  "gw_trend": "declining", "aquifer_risk": "High"},
    {"district": "Bogura",     "division": "Rajshahi",   "lat": 24.85, "lon": 89.37,
     "ghi": 4.9, "diesel_pumps": 98000,  "solar_pct": 74, "priority": "Low",
     "area_km2": 2920, "crop_zone": "Boro Rice / Maize",
     "gw_depth_m": 5.8,  "gw_trend": "stable",    "aquifer_risk": "Medium"},
    {"district": "Mymensingh", "division": "Mymensingh", "lat": 24.74, "lon": 90.41,
     "ghi": 4.7, "diesel_pumps": 210000, "solar_pct": 61, "priority": "Medium",
     "area_km2": 4395, "crop_zone": "Boro Rice / Jute",
     "gw_depth_m": 4.2,  "gw_trend": "stable",    "aquifer_risk": "Low"},
    {"district": "Dinajpur",   "division": "Rangpur",    "lat": 25.62, "lon": 88.63,
     "ghi": 4.8, "diesel_pumps": 178000, "solar_pct": 55, "priority": "Medium",
     "area_km2": 3437, "crop_zone": "Wheat / Potato",
     "gw_depth_m": 8.1,  "gw_trend": "declining", "aquifer_risk": "High"},
    {"district": "Rangpur",    "division": "Rangpur",    "lat": 25.74, "lon": 89.25,
     "ghi": 4.6, "diesel_pumps": 165000, "solar_pct": 42, "priority": "Medium",
     "area_km2": 2308, "crop_zone": "Jute / Maize",
     "gw_depth_m": 5.1,  "gw_trend": "stable",    "aquifer_risk": "Medium"},
    {"district": "Khulna",     "division": "Khulna",     "lat": 22.84, "lon": 89.55,
     "ghi": 4.4, "diesel_pumps": 89000,  "solar_pct": 31, "priority": "High",
     "area_km2": 4394, "crop_zone": "Rice / Shrimp",
     "gw_depth_m": 3.0,  "gw_trend": "stable",    "aquifer_risk": "Low"},
    {"district": "Sylhet",     "division": "Sylhet",     "lat": 24.88, "lon": 91.88,
     "ghi": 4.2, "diesel_pumps": 45000,  "solar_pct": 22, "priority": "High",
     "area_km2": 3490, "crop_zone": "Tea / Rice",
     "gw_depth_m": 3.5,  "gw_trend": "stable",    "aquifer_risk": "Low"},
    {"district": "Barisal",    "division": "Barisal",    "lat": 22.70, "lon": 90.37,
     "ghi": 4.3, "diesel_pumps": 67000,  "solar_pct": 18, "priority": "High",
     "area_km2": 2784, "crop_zone": "Rice / Vegetables",
     "gw_depth_m": 2.8,  "gw_trend": "stable",    "aquifer_risk": "Low"},
    {"district": "Faridpur",   "division": "Dhaka",      "lat": 23.60, "lon": 89.84,
     "ghi": 4.9, "diesel_pumps": 112000, "solar_pct": 67, "priority": "Low",
     "area_km2": 2073, "crop_zone": "Jute / Rice",
     "gw_depth_m": 4.8,  "gw_trend": "stable",    "aquifer_risk": "Medium"},
    {"district": "Comilla",    "division": "Chattogram", "lat": 23.46, "lon": 91.18,
     "ghi": 4.6, "diesel_pumps": 135000, "solar_pct": 49, "priority": "Medium",
     "area_km2": 3085, "crop_zone": "Boro Rice / Vegetables",
     "gw_depth_m": 4.5,  "gw_trend": "stable",    "aquifer_risk": "Low"},
    {"district": "Jessore",    "division": "Khulna",     "lat": 23.17, "lon": 89.21,
     "ghi": 4.7, "diesel_pumps": 103000, "solar_pct": 38, "priority": "Medium",
     "area_km2": 2567, "crop_zone": "Wheat / Jute",
     "gw_depth_m": 5.3,  "gw_trend": "declining", "aquifer_risk": "Medium"},
    {"district": "Pabna",      "division": "Rajshahi",   "lat": 24.00, "lon": 89.23,
     "ghi": 5.0, "diesel_pumps": 88000,  "solar_pct": 72, "priority": "Low",
     "area_km2": 2371, "crop_zone": "Sugarcane / Rice",
     "gw_depth_m": 7.2,  "gw_trend": "declining", "aquifer_risk": "High"},
])


# -- optional real-data override ------------------------------------------------
from pathlib import Path as _Path
DISTRICTS_SOURCE = "placeholder (illustrative values, not survey data)"
_csv = _Path(__file__).with_name("districts.csv")
if _csv.exists():
    try:
        _df = pd.read_csv(_csv)
        if set(DISTRICTS.columns).issubset(_df.columns):
            DISTRICTS = _df[list(DISTRICTS.columns)].copy()
            DISTRICTS_SOURCE = f"csv: {_csv.name}"
    except Exception:
        pass

# ── Monthly GHI profiles (offline fallback only) (kWh/m²/day) per district ───────────────────────────
MONTHLY_GHI = {
    "Rajshahi":   [4.8, 5.2, 5.8, 6.1, 5.9, 4.2, 3.8, 4.0, 4.6, 5.0, 4.9, 4.6],
    "Bogura":     [4.6, 5.0, 5.6, 5.9, 5.7, 4.0, 3.6, 3.8, 4.4, 4.8, 4.7, 4.4],
    "Mymensingh": [4.4, 4.8, 5.3, 5.7, 5.4, 3.8, 3.4, 3.6, 4.2, 4.6, 4.5, 4.2],
    "Dinajpur":   [4.5, 4.9, 5.5, 5.8, 5.6, 3.9, 3.5, 3.7, 4.3, 4.7, 4.6, 4.3],
    "Rangpur":    [4.3, 4.7, 5.2, 5.6, 5.3, 3.7, 3.3, 3.5, 4.1, 4.5, 4.4, 4.1],
    "Khulna":     [4.2, 4.6, 5.0, 5.4, 5.1, 3.6, 3.2, 3.5, 4.0, 4.4, 4.2, 4.0],
    "Sylhet":     [3.9, 4.2, 4.7, 5.0, 4.7, 3.3, 3.0, 3.2, 3.8, 4.1, 3.9, 3.7],
    "Barisal":    [4.0, 4.4, 4.8, 5.2, 4.9, 3.4, 3.1, 3.3, 3.9, 4.2, 4.0, 3.8],
    "Faridpur":   [4.6, 5.0, 5.5, 5.8, 5.6, 3.9, 3.5, 3.7, 4.3, 4.7, 4.6, 4.3],
    "Comilla":    [4.3, 4.7, 5.2, 5.5, 5.2, 3.7, 3.3, 3.5, 4.1, 4.4, 4.3, 4.0],
    "Jessore":    [4.4, 4.8, 5.3, 5.6, 5.4, 3.8, 3.4, 3.6, 4.2, 4.5, 4.4, 4.1],
    "Pabna":      [4.7, 5.1, 5.7, 6.0, 5.8, 4.1, 3.7, 3.9, 4.5, 4.9, 4.8, 4.5],
}

ETO_BY_MONTH = [3.5, 4.2, 5.1, 5.5, 5.3, 4.0, 3.6, 3.7, 4.0, 4.3, 3.8, 3.4]

CROP_ETC = {
    "Boro Rice": {
        "season": "Dec–May", "total_days": 150,
        "stages": [
            ("Nursery/Transplant", 30, 1.10),
            ("Vegetative",         45, 1.15),
            ("Reproductive",       35, 1.20),
            ("Maturation",         40, 0.95),
        ],
        "peak_kc": 1.20,
    },
    "Wheat": {
        "season": "Nov–Mar", "total_days": 120,
        "stages": [
            ("Germination",  20, 0.40),
            ("Tillering",    30, 0.70),
            ("Jointing",     25, 1.10),
            ("Heading",      25, 1.15),
            ("Ripening",     20, 0.65),
        ],
        "peak_kc": 1.15,
    },
    "Jute": {
        "season": "Mar–Jul", "total_days": 120,
        "stages": [
            ("Germination", 15, 0.35),
            ("Vegetative",  60, 0.90),
            ("Flowering",   30, 1.00),
            ("Maturation",  15, 0.80),
        ],
        "peak_kc": 1.00,
    },
    "Maize": {
        "season": "Nov–Mar", "total_days": 120,
        "stages": [
            ("Emergence",    20, 0.30),
            ("Vegetative",   35, 0.70),
            ("Tasselling",   30, 1.20),
            ("Grain fill",   25, 1.15),
            ("Maturation",   10, 0.70),
        ],
        "peak_kc": 1.20,
    },
    "Vegetables": {
        "season": "Year-round", "total_days": 90,
        "stages": [
            ("Establishment", 20, 0.50),
            ("Development",   30, 0.85),
            ("Mid-season",    30, 1.05),
            ("Late",          10, 0.90),
        ],
        "peak_kc": 1.05,
    },
    "Sugarcane": {
        "season": "Feb–Dec", "total_days": 365,
        "stages": [
            ("Germination",   40, 0.40),
            ("Tillering",     90, 0.80),
            ("Grand growth", 180, 1.25),
            ("Maturation",    55, 0.75),
        ],
        "peak_kc": 1.25,
    },
    "Tea": {
        "season": "Mar–Nov", "total_days": 270,
        "stages": [
            ("Flush 1", 90, 0.90),
            ("Flush 2", 90, 1.00),
            ("Flush 3", 90, 0.85),
        ],
        "peak_kc": 1.00,
    },
}


_CROP_EXTRA = {
    "Boro Rice":  dict(perc_mm_day=3.0, landprep_mm=150.0, plant_month=12),
    "Wheat":      dict(plant_month=11),
    "Jute":       dict(plant_month=3),
    "Maize":      dict(plant_month=11),
    "Vegetables": dict(plant_month=11),
    "Sugarcane":  dict(plant_month=2),
    "Tea":        dict(plant_month=3),
}
for _c, _e in _CROP_EXTRA.items():
    CROP_ETC[_c].update(_e)

AQUIFER_RISK_THRESHOLDS = {
    "High":   {"gw_depth_m": 7.0, "message": "⚠️ Critical: Barind Tract aquifer under stress. New permit restrictions advised. Consider water-saving drip/sprinkler."},
    "Medium": {"gw_depth_m": 5.0, "message": "⚠️ Moderate: Groundwater trending down. Monitor extraction rate. Recommended: rain harvesting supplement."},
    "Low":    {"gw_depth_m": 3.0, "message": "✅ Aquifer appears stable. Standard extraction limits apply."},
}

PESTLE_SCORES = {
    "Political":     {"score": 7.2, "factors": [
        "SREDA mandate for rural solar expansion",
        "BREB grid infrastructure support",
        "Mujib Climate Prosperity Plan alignment",
        "Moderate political will for subsidy reform",
    ]},
    "Economic":      {"score": 6.5, "factors": [
        "Diesel prices rising as subsidies removed",
        "Solar panel costs down 78% since 2013",
        "Microfinance access limited in haor regions",
        "Farmer income volatility poses repayment risk",
    ]},
    "Social":        {"score": 5.8, "factors": [
        "Low digital literacy in target districts",
        "Women's cooperative engagement positive",
        "Pump operator employment displacement risk",
        "Community trust-building investment needed",
    ]},
    "Technological": {"score": 7.8, "factors": [
        "Mature SPIS technology commercially available",
        "GEE + geospatial tools operationally ready",
        "Local O&M capacity gap identified",
        "Battery storage remains cost barrier",
    ]},
    "Legal":         {"score": 6.9, "factors": [
        "Land tenure complexity in flood plains",
        "Energy trading regulations currently unclear",
        "Groundwater extraction laws broadly supportive",
        "Import duty waivers for solar equipment active",
    ]},
    "Environmental": {"score": 8.1, "factors": [
        "High solar irradiance (4.2–5.5 kWh/m²/day)",
        "Flood risk to ground-mounted panel infrastructure",
        "Groundwater depletion reduction co-benefit",
        "Arsenic risk reduced with less groundwater draw",
    ]},
}

# ── Native GEE Dataset Catalogue ──────────────────────────────────────────────
GEE_DATASETS = pd.DataFrame([
    {"name": "Solar radiation, temperature, rain (daily)", "source": "ECMWF ERA5-Land",
     "collection": "ECMWF/ERA5_LAND/DAILY_AGGR", "resolution": "~9 km", "update": "Daily", "status": "Used"},
    {"name": "Crop Health (NDVI)", "source": "Sentinel-2 SR Harmonized",
     "collection": "COPERNICUS/S2_SR_HARMONIZED", "resolution": "10 m", "update": "5 days", "status": "Used"},
    {"name": "Elevation (DEM)", "source": "SRTMGL1",
     "collection": "USGS/SRTMGL1_003", "resolution": "30 m", "update": "Static", "status": "Used"},
    {"name": "Surface water / flood history", "source": "JRC Global Surface Water",
     "collection": "JRC/GSW1_4/GlobalSurfaceWater", "resolution": "30 m", "update": "Annual", "status": "Used"},
    {"name": "Land cover", "source": "MODIS MCD12Q1",
     "collection": "MODIS/061/MCD12Q1", "resolution": "500 m", "update": "Annual", "status": "Used"},
    {"name": "Groundwater depth / trend", "source": "BWDB / BADC (not connected)",
     "collection": "-", "resolution": "-", "update": "-", "status": "Not connected"},
    {"name": "Pump locations", "source": "BADC survey (not connected)",
     "collection": "-", "resolution": "-", "update": "-", "status": "Not connected"},
])

def to_hectares(value: float, unit: str) -> float:
    return {
        "hectares": value,
        "acres":    value * 0.404686,
        "bigha":    value * 0.133546,
        "katha":    value * 0.00667731,
    }.get(unit, value)

def get_etc_demand(crop: str, area_ha: float, month_idx: int) -> dict:
    info = CROP_ETC.get(crop, CROP_ETC["Boro Rice"])
    eto  = ETO_BY_MONTH[month_idx]
    kc   = info["peak_kc"]
    etc  = eto * kc
    area_m2 = area_ha * 10_000
    vol_m3_day = etc * area_m2 / 1000
    flow_m3h = vol_m3_day / 8.0
    return {
        "eto_mm_day":   round(eto,  2),
        "kc":           round(kc,   2),
        "etc_mm_day":   round(etc,  2),
        "vol_m3_day":   round(vol_m3_day, 1),
        "flow_m3h":     round(flow_m3h,   2),
        "pumping_hours": 8,
    }

def get_aquifer_flag(district: str) -> dict:
    row = DISTRICTS[DISTRICTS["district"] == district]
    if row.empty:
        return {"risk": "Unknown", "gw_depth_m": None, "trend": "unknown", "message": "No data"}
    r = row.iloc[0]
    level = r["aquifer_risk"]
    return {
        "risk":        level,
        "gw_depth_m":  r["gw_depth_m"],
        "trend":       r["gw_trend"],
        "message":     AQUIFER_RISK_THRESHOLDS.get(level, {}).get("message", ""),
        "source":      DISTRICTS_SOURCE,
    }