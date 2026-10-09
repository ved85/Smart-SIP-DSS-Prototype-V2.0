"""
Title: SQLite persistence layer for SMART-SIP+ DSS Prototype.

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""

import sqlite3
import os
import json
import pandas as pd
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "smartsip.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    return con


_NEW_COLS = {
    "climate_cache": [("tmax", "REAL"), ("tmin", "REAL"), ("precip_mm", "REAL")],
    "business_cases": [("climate_source", "TEXT"), ("ghi_mean", "REAL"), ("tcell_mean", "REAL"),
                       ("annual_volume_m3", "REAL"), ("annual_irrigation_mm", "REAL"),
                       ("season_days", "INTEGER"), ("solar_fraction", "REAL"), ("lat", "REAL"),
                       ("lon", "REAL"), ("planting_month", "INTEGER"), ("lcoe_subsidised", "REAL")],
    "land_parcels": [("gw_depth_m", "REAL"), ("gw_trend", "TEXT")],
}


def _migrate(con) -> None:
    """Additive, idempotent schema upgrades so existing databases keep working."""
    con.execute("""CREATE TABLE IF NOT EXISTS parcel_climate (
        key TEXT PRIMARY KEY, lat REAL, lon REAL, source TEXT, y0 INTEGER, y1 INTEGER,
        clim_json TEXT, fetched_at TEXT DEFAULT (datetime('now')))""")
    for table, cols in _NEW_COLS.items():
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        for name, typ in cols:
            if name not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")


def _num(x):
    try:
        return None if x is None or pd.isna(x) else float(x)
    except Exception:
        return None


def save_parcel_climate(key, lat, lon, source, y0, y1, clim: dict) -> None:
    con = _conn()
    con.execute("""INSERT INTO parcel_climate (key, lat, lon, source, y0, y1, clim_json)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(key) DO UPDATE SET clim_json=excluded.clim_json,
                   source=excluded.source, fetched_at=datetime('now')""",
                (key, lat, lon, source, y0, y1, json.dumps(clim)))
    con.commit()
    con.close()


def load_parcel_climate(key: str) -> dict | None:
    con = _conn()
    row = con.execute("SELECT clim_json FROM parcel_climate WHERE key=?", (key,)).fetchone()
    con.close()
    return json.loads(row[0]) if row else None


def init_db() -> None:
    con = _conn()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS climate_cache (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lat         REAL    NOT NULL,
            lon         REAL    NOT NULL,
            date        TEXT    NOT NULL,
            ghi         REAL,
            temp        REAL,
            wind_speed  REAL,
            source      TEXT    DEFAULT 'gee_era5',
            fetched_at  TEXT    DEFAULT (datetime('now')),
            UNIQUE(lat, lon, date)
        );

        CREATE TABLE IF NOT EXISTS gee_results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lat         REAL    NOT NULL,
            lon         REAL    NOT NULL,
            query_date  TEXT    NOT NULL,
            ndvi        REAL,
            elevation   REAL,
            land_use    TEXT,
            flood_risk  REAL,
            fetched_at  TEXT    DEFAULT (datetime('now')),
            UNIQUE(lat, lon, query_date)
        );

        CREATE TABLE IF NOT EXISTS business_cases (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            parcel_id       INTEGER,
            district        TEXT,
            pump_kw         REAL,
            area_ha         REAL,
            crop_type       TEXT,
            subsidy_pct     REAL,
            panel_kwp       REAL,
            total_capex     REAL,
            capex_subsidy   REAL,
            annual_opex     REAL,
            net_saving      REAL,
            payback_years   REAL,
            npv_25yr        REAL,
            irr             REAL,
            lcoe_bdt_kwh    REAL,
            co2_t_per_yr    REAL,
            diesel_l_per_yr REAL,
            cold_revenue    REAL,
            erickshaw_rev   REAL,
            tdh_m           REAL,
            flow_m3h        REAL,
            psh             REAL,
            aquifer_risk    TEXT,
            params_json     TEXT,
            created_at      TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS pipeline_jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name    TEXT    NOT NULL,
            job_type    TEXT,
            schedule    TEXT,
            started_at  TEXT,
            finished_at TEXT,
            duration_s  REAL,
            records     INTEGER,
            status      TEXT    DEFAULT 'ok',
            error_msg   TEXT
        );

        CREATE TABLE IF NOT EXISTS scenario_runs (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            target_year         INTEGER,
            replacement_rate    REAL,
            subsidy_pct         REAL,
            cold_pct            REAL,
            ev_pct              REAL,
            fin_model           TEXT,
            result_json         TEXT,
            created_at          TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS land_parcels (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT    NOT NULL,
            district        TEXT,
            upazila         TEXT,
            lat_centroid    REAL,
            lon_centroid    REAL,
            area_ha         REAL,
            area_unit_orig  TEXT,
            area_orig       REAL,
            polygon_geojson TEXT,
            crop_type       TEXT,
            notes           TEXT,
            created_at      TEXT    DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_climate_lat_lon_date
            ON climate_cache(lat, lon, date);
        CREATE INDEX IF NOT EXISTS idx_gee_lat_lon_date
            ON gee_results(lat, lon, query_date);
        CREATE INDEX IF NOT EXISTS idx_bc_district
            ON business_cases(district);
    """)
    _migrate(con)
    con.commit()
    con.close()


# ── Climate Cache ─────────────────────────────────────────────────────────────

def cache_climate(df: pd.DataFrame, lat: float, lon: float,
                  source: str = "gee_era5_land") -> None:
    con = _conn()
    rows = [(lat, lon, str(r["date"])[:10], float(r["ghi"]), float(r["temp"]),
             float(r.get("wind_speed", 0) or 0), source, _num(r.get("tmax")), _num(r.get("tmin")),
             _num(r.get("precip_mm"))) for _, r in df.iterrows()]
    con.executemany("""
        INSERT INTO climate_cache (lat, lon, date, ghi, temp, wind_speed, source, tmax, tmin, precip_mm)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(lat, lon, date) DO UPDATE SET
            ghi=excluded.ghi, temp=excluded.temp, wind_speed=excluded.wind_speed,
            source=excluded.source, tmax=excluded.tmax, tmin=excluded.tmin,
            precip_mm=excluded.precip_mm, fetched_at=datetime('now')
    """, rows)
    con.commit()
    con.close()


def load_climate_cache(lat: float, lon: float,
                       start: str, end: str) -> pd.DataFrame | None:
    con = _conn()
    df = pd.read_sql_query("""
        SELECT date, ghi, temp, tmax, tmin, precip_mm, wind_speed, source, fetched_at
        FROM climate_cache
        WHERE lat=? AND lon=? AND date BETWEEN ? AND ?
        ORDER BY date
    """, con, params=(lat, lon, start, end))
    con.close()
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_all_cached_climate() -> pd.DataFrame:
    """Retrieve all cached climate records across all districts and coordinates."""
    con = _conn()
    df = pd.read_sql_query("""
        SELECT lat, lon, date, ghi, temp, wind_speed, source, fetched_at
        FROM climate_cache
        ORDER BY date ASC
    """, con)
    con.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def get_cached_climate_locations() -> pd.DataFrame:
    """Retrieve distinct cached locations with record counts and date ranges."""
    con = _conn()
    df = pd.read_sql_query("""
        SELECT lat, lon, COUNT(*) as record_count, MIN(date) as min_date, MAX(date) as max_date, source
        FROM climate_cache
        GROUP BY lat, lon
    """, con)
    con.close()
    return df


# ── GEE Results Cache ─────────────────────────────────────────────────────────

def save_gee_result(lat: float, lon: float, query_date: str,
                    ndvi: float = None, elevation: float = None,
                    land_use: str = None, flood_risk: float = None) -> None:
    con = _conn()
    con.execute("""
        INSERT INTO gee_results (lat, lon, query_date, ndvi, elevation, land_use, flood_risk)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(lat, lon, query_date) DO UPDATE SET
            ndvi=excluded.ndvi, elevation=excluded.elevation,
            land_use=excluded.land_use, flood_risk=excluded.flood_risk,
            fetched_at=datetime('now')
    """, (lat, lon, query_date, ndvi, elevation, land_use, flood_risk))
    con.commit()
    con.close()


def load_gee_result(lat: float, lon: float, query_date: str) -> dict | None:
    con = _conn()
    cur = con.execute("""
        SELECT ndvi, elevation, land_use, flood_risk, fetched_at
        FROM gee_results WHERE lat=? AND lon=? AND query_date=?
    """, (lat, lon, query_date))
    row = cur.fetchone()
    con.close()
    if row:
        return {
            "ndvi": row[0],
            "elevation": row[1],
            "land_use": row[2],
            "flood_risk": row[3],
            "fetched_at": row[4],
        }
    return None


def load_all_gee_results() -> pd.DataFrame:
    """Retrieve all cached GEE satellite extractions (Sentinel-2, SRTM, JRC)."""
    con = _conn()
    df = pd.read_sql_query("""
        SELECT id, lat, lon, query_date, ndvi, elevation, land_use, flood_risk, fetched_at
        FROM gee_results
        ORDER BY query_date DESC, fetched_at DESC
    """, con)
    con.close()
    return df


# ── Business Cases ────────────────────────────────────────────────────────────

def save_business_case(spec, result, parcel_id: int = None) -> int:
    cols = {
        "parcel_id": parcel_id, "district": spec.district, "pump_kw": spec.pump_kw,
        "area_ha": spec.area_ha, "crop_type": spec.crop_type, "subsidy_pct": spec.subsidy_pct,
        "panel_kwp": spec.panel_kwp, "total_capex": result.total_capex,
        "capex_subsidy": result.total_capex_after_subsidy, "annual_opex": result.annual_opex,
        "net_saving": result.net_annual_saving, "payback_years": result.payback_years,
        "npv_25yr": result.npv_25yr, "irr": result.irr, "lcoe_bdt_kwh": result.lcoe_bdt_per_kwh,
        "co2_t_per_yr": result.co2_tonnes_per_year, "diesel_l_per_yr": result.diesel_litres_per_year,
        "cold_revenue": result.annual_cold_revenue, "erickshaw_rev": result.annual_erickshaw_revenue,
        "tdh_m": result.tdh_m, "flow_m3h": result.flow_m3h, "psh": result.psh,
        "aquifer_risk": result.aquifer_risk,
        "params_json": json.dumps({k: v for k, v in spec.__dict__.items() if k != "clim"}, default=str),
        "climate_source": result.climate_source, "ghi_mean": result.ghi_mean,
        "tcell_mean": result.tcell_mean, "annual_volume_m3": result.annual_volume_m3,
        "annual_irrigation_mm": result.annual_irrigation_mm, "season_days": result.season_days,
        "solar_fraction": result.solar_fraction, "lat": spec.lat, "lon": spec.lon,
        "planting_month": spec.planting_month, "lcoe_subsidised": result.lcoe_subsidised,
    }
    con = _conn()
    cur = con.execute(f"INSERT INTO business_cases ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                      list(cols.values()))
    row_id = cur.lastrowid
    con.commit()
    con.close()
    return row_id


def load_recent_business_cases(limit: int = 50) -> pd.DataFrame:
    con = _conn()
    df = pd.read_sql_query("""
        SELECT id, district, pump_kw, area_ha, crop_type, subsidy_pct,
               panel_kwp, payback_years, npv_25yr, irr, lcoe_bdt_kwh,
               co2_t_per_yr, diesel_l_per_yr, cold_revenue, erickshaw_rev,
               tdh_m, flow_m3h, psh, aquifer_risk, climate_source, ghi_mean, tcell_mean,
               annual_volume_m3, annual_irrigation_mm, solar_fraction, lat, lon, created_at
        FROM business_cases ORDER BY created_at DESC LIMIT ?
    """, con, params=(limit,))
    con.close()
    return df


# ── Land Parcels ──────────────────────────────────────────────────────────────

def save_parcel(name: str, district: str, upazila: str,
                lat: float, lon: float,
                area_ha: float, area_orig: float, area_unit: str,
                polygon_geojson: str, crop_type: str,
                notes: str = "", gw_depth_m: float = None, gw_trend: str = None) -> int:
    con = _conn()
    cur = con.execute("""
        INSERT INTO land_parcels
          (name, district, upazila, lat_centroid, lon_centroid,
           area_ha, area_unit_orig, area_orig, polygon_geojson,
           crop_type, notes, gw_depth_m, gw_trend)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (name, district, upazila, lat, lon,
          area_ha, area_unit, area_orig, polygon_geojson, crop_type, notes, gw_depth_m, gw_trend))
    row_id = cur.lastrowid
    con.commit()
    con.close()
    return row_id


def load_parcels() -> pd.DataFrame:
    con = _conn()
    df = pd.read_sql_query("""
        SELECT id, name, district, upazila, lat_centroid, lon_centroid,
               area_ha, area_unit_orig, area_orig, crop_type, notes, gw_depth_m, gw_trend, created_at
        FROM land_parcels ORDER BY created_at DESC
    """, con)
    con.close()
    return df


def load_parcel_geojson(parcel_id: int) -> str | None:
    con = _conn()
    cur = con.execute("SELECT polygon_geojson FROM land_parcels WHERE id=?", (parcel_id,))
    row = cur.fetchone()
    con.close()
    return row[0] if row else None


def delete_parcel(parcel_id: int) -> None:
    con = _conn()
    con.execute("DELETE FROM land_parcels WHERE id=?", (parcel_id,))
    con.commit()
    con.close()


# ── Pipeline Jobs ─────────────────────────────────────────────────────────────

def log_job_start(job_name: str, job_type: str, schedule: str) -> int:
    con = _conn()
    cur = con.execute("""
        INSERT INTO pipeline_jobs (job_name, job_type, schedule, started_at, status)
        VALUES (?, ?, ?, datetime('now'), 'running')
    """, (job_name, job_type, schedule))
    row_id = cur.lastrowid
    con.commit()
    con.close()
    return row_id


def log_job_end(job_id: int, records: int = 0, status: str = "ok",
                error_msg: str = None, duration_s: float = None) -> None:
    con = _conn()
    con.execute("""
        UPDATE pipeline_jobs
        SET finished_at=datetime('now'), records=?, status=?, error_msg=?, duration_s=?
        WHERE id=?
    """, (records, status, error_msg, duration_s, job_id))
    con.commit()
    con.close()


def load_pipeline_jobs(limit: int = 20) -> pd.DataFrame:
    con = _conn()
    df = pd.read_sql_query("""
        SELECT job_name, job_type, schedule, started_at,
               duration_s, records, status, error_msg
        FROM pipeline_jobs ORDER BY started_at DESC LIMIT ?
    """, con, params=(limit,))
    con.close()
    return df


# ── Dashboard KPIs ────────────────────────────────────────────────────────────

def get_dashboard_kpis() -> dict:
    con = _conn()
    bc = pd.read_sql_query(
        "SELECT payback_years, co2_t_per_yr, district, diesel_l_per_yr FROM business_cases", con
    )
    climate_rows = con.execute("SELECT COUNT(*) FROM climate_cache").fetchone()[0]
    gee_rows     = con.execute("SELECT COUNT(*) FROM gee_results").fetchone()[0]
    job_rows     = con.execute("SELECT COUNT(*) FROM pipeline_jobs WHERE status='ok'").fetchone()[0]
    parcel_rows  = con.execute("SELECT COUNT(*) FROM land_parcels").fetchone()[0]
    con.close()

    n = len(bc)
    return {
        "n_business_cases":    n,
        "avg_payback_years":   round(bc["payback_years"].mean(), 1) if n else None,
        "total_co2_t":         round(bc["co2_t_per_yr"].sum(), 1) if n else 0,
        "total_diesel_l":      round(bc["diesel_l_per_yr"].sum(), 0) if n else 0,
        "districts_covered":   bc["district"].nunique() if n else 0,
        "climate_rows_cached": climate_rows,
        "gee_queries_stored":  gee_rows,
        "pipeline_jobs_ok":    job_rows,
        "n_parcels":           parcel_rows,
    }


# ── Scenario Runs ─────────────────────────────────────────────────────────────

def save_scenario(params: dict, results: dict) -> int:
    con = _conn()
    cur = con.execute("""
        INSERT INTO scenario_runs
          (target_year, replacement_rate, subsidy_pct, cold_pct, ev_pct,
           fin_model, result_json)
        VALUES (?,?,?,?,?,?,?)
    """, (params.get("target_year"), params.get("replacement_rate_pct"),
          params.get("subsidy_pct"), params.get("cold_integration_pct"),
          params.get("ev_adoption_pct"), params.get("fin_model"),
          json.dumps(results)))
    row_id = cur.lastrowid
    con.commit()
    con.close()
    return row_id


init_db()