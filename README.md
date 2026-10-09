# SMART-SIP+ Decision Support System Prototype

**Version:** 2.0  
**Made by:** Vedant Varma  

> *Solar-powered Irrigation Transition for Bangladesh — Pathways to Net Zero Agriculture*

A Python-based multi-page Decision Support System (DSS) that helps farmers, investors, and policymakers evaluate the transition from diesel to solar irrigation across rural Bangladesh. All spatial and climate data is retrieved live from **Google Earth Engine (GEE)**. Everything else runs locally with a SQLite cache.

---

## Table of Contents

- [Features & Capabilities](#features--capabilities)
- [Where Synthetic / Static Data Is Used](#where-synthetic--static-data-is-used)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Running the App](#running-the-app)
- [Page-by-Page Guide](#page-by-page-guide)
- [Replacing Placeholder Data](#replacing-placeholder-data)
- [Tech Stack](#tech-stack)
- [Licence](#licence)

---

## Features & Capabilities

### For Farmers & Investors
| Tool | What it does |
|---|---|
| **📍 Site Analyser** | Draw farm parcel boundaries over live GEE Sentinel-2 satellite imagery. Geodesic area (WGS-84 ellipsoid, cross-checked against a local equal-area projection), NDVI, elevation and flood risk queried from GEE. Saved to SQLite with full GeoJSON polygon. |
| **₿ Business Case** | Full hydraulic chain: ERA5-Land monthly GHI & temperature → FAO-56 crop water balance → design flow → TDH → pump kW → PV kWp (energy + power sized, temperature-derated). CAPEX/OPEX breakdown, 25-yr NPV, IRR, LCOE in BDT/kWh, CO₂ and diesel savings. Add-ons: cold storage, e-rickshaw charging hub, battery, EV charger, subsidy. |
| **⚡ Energy Model** | 24-hour hourly simulation for any selected month using the parcel's ERA5-Land GHI and real daylight window at its latitude. Surplus routed to cold storage, e-rickshaw, post-harvest machinery and grid. Full monthly generation vs irrigation bar chart for the whole year. |

### For Policymakers & Planners
| Tool | What it does |
|---|---|
| **🗺 Regional Map** | District-level GIS on live GEE satellite base map. Five selectable data layers: solar adoption, diesel pump density, GHI (live from ERA5-Land or placeholder), subsidy priority, aquifer vulnerability. GEE overlay layers (Sentinel-2 RGB, NDVI, SRTM DEM, JRC flood occurrence) toggleable via layer control. Fullscreen, map-type selector (Satellite/Roadmap/Terrain), built-in search bar (local gazetteer + Photon/Nominatim online fallback). |
| **⟳ Scenario Simulator** | National roll-out projection 2025–2040. User-editable national driver assumptions (total pumps, avg kW, pumping hours/day, irrigation days/yr, unit cost). Outputs: pumps replaced, CO₂ Mt/yr avoided, diesel GL/yr saved, BDT investment and subsidy cost, cold storage nodes, e-rickshaw charger points. Optional comparison scenario overlay. CSV export. |
| **⊞ PESTLE Analysis** | Six-dimension radar chart (Political, Economic, Social, Technological, Legal, Environmental) scored 0–10 against a 7.0 target. Waterfall composite score. Scores are expert-judgement placeholders (editable in `data/bangladesh_data.py`). |

### Data Infrastructure
| Tool | What it does |
|---|---|
| **☁ Climate & GEE** | Four tabs: daily ERA5-Land series (last 365 days), monthly climatology for any point, all-districts climatology comparison, and EO spot query (Sentinel-2 NDVI, SRTM elevation, JRC flood risk, MODIS land cover). All results cached in SQLite. |
| **🛰 GEE Test** | Step-by-step connection diagnostics: credentials file check, `ee.Initialize()`, server round-trip, and live test of all five GEE datasets (SRTM, Sentinel-2, JRC, MODIS, ERA5-Land). Results cached to SQLite. |
| **⟡ Data Pipeline** | Sankey diagram of the full ETL architecture. Live pipeline job monitor from SQLite. Technology stack table. GEE ERA5 and standard GEE code examples. |
| **📊 Dashboard** | KPIs aggregated from SQLite. Dynamic multi-location GEE ERA5 climate charts (overlay or individual drilldown). Cached EO analytics: Sentinel-2 NDVI, SRTM elevation and JRC flood risk bars for all queried points. Solar adoption and aquifer vulnerability charts. |

---

## Where Synthetic / Static Data Is Used

This prototype clearly flags every source. The table below documents what is live GEE data and what is a placeholder.

| Data | Source | Status |
|---|---|---|
| Daily GHI, temperature, wind, rainfall | GEE · `ECMWF/ERA5_LAND/DAILY_AGGR` (~9 km) | **Live** |
| Monthly climatology (GHI, ETo, rain) | GEE · ERA5-Land multi-year mean | **Live** |
| Sentinel-2 NDVI, RGB composite | GEE · `COPERNICUS/S2_SR_HARMONIZED` (10 m) | **Live** |
| SRTM elevation | GEE · `USGS/SRTMGL1_003` (30 m) | **Live** |
| JRC flood / surface water occurrence | GEE · `JRC/GSW1_4/GlobalSurfaceWater` (30 m) | **Live** |
| MODIS land cover (LC_Type1) | GEE · `MODIS/061/MCD12Q1` (500 m) | **Live** |
| District solar adoption % | **ILLUSTRATIVE PLACEHOLDER** — not survey data | ⚠️ Replace |
| District diesel pump counts | **ILLUSTRATIVE PLACEHOLDER** — not survey data | ⚠️ Replace |
| District groundwater depth / trend | **ILLUSTRATIVE PLACEHOLDER** — not survey data | ⚠️ Replace |
| Aquifer risk rating | **ILLUSTRATIVE PLACEHOLDER** — not survey data | ⚠️ Replace |
| Subsidy priority rating | **ILLUSTRATIVE PLACEHOLDER** — not survey data | ⚠️ Replace |
| PESTLE scores | Expert-judgement **placeholders** | ⚠️ Replace |
| Unit costs (panels, pump, install, BDT) | **PLACEHOLDER** ~2024 Bangladesh market estimates | ⚠️ Verify with suppliers |
| National diesel pump count (3.4 M) | BADC minor-irrigation survey reference — user-editable in Scenario Simulator | ⚠️ Verify |
| Systemic barrier severity scores | **ILLUSTRATIVE** national survey estimates | ⚠️ Replace |

> **How to replace district data:** Drop a `data/districts.csv` file with the same column names as the `DISTRICTS` DataFrame in `data/bangladesh_data.py`. The app detects it on startup and switches source label to `csv: districts.csv` everywhere it is displayed.

---

## Architecture

```
Browser
  └── Streamlit (multi-page)
        ├── pages/          ← 10 pages (1_Dashboard → 10_GEE_Test)
        ├── utils/
        │     ├── climate.py     ← All GEE calls (ERA5-Land, Sentinel-2, SRTM, JRC, MODIS)
        │     ├── maps.py        ← Folium maps + GEE raster overlay layers
        │     ├── map_search.py  ← In-map search bar (Leaflet JS, MacroElement)
        │     ├── geo.py         ← Geodesic area / centroid (pyproj.Geod, Shapely)
        │     ├── db.py          ← SQLite cache (climate, GEE results, business cases, parcels)
        │     └── footer.py      ← Global footer injection
        ├── data/
        │     ├── bangladesh_data.py  ← Reference tables (districts, crops, PESTLE)
        │     └── smartsip.db         ← Auto-created SQLite database
        ├── models/
        │     └── techno_economic.py  ← FAO-56 water balance + CAPEX/NPV/IRR engine
        └── app.py              ← Entry point
```

**Data flow:**  
`GEE ERA5-Land` → `climate.py` → `db.py` (SQLite cache) → `techno_economic.py` (monthly water balance) → `pages/` (Streamlit UI)

`GEE Sentinel-2/SRTM/JRC/MODIS` → `climate.py` → `db.py` → `pages/` + `maps.py` (Folium overlays)

---

## Project Structure

```
smartsip/
├── app.py                        # Streamlit entry point (home page)
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
├── .streamlit/
│   └── config.toml               # Dark theme config
│
├── pages/
│   ├── 1_Dashboard.py            # System KPIs, cached GEE climate charts, EO analytics
│   ├── 2_Site_Analyser.py        # Draw parcel over satellite, GEE NDVI/elevation/flood
│   ├── 3_Business_Case.py        # Full hydraulic + CAPEX/OPEX/NPV/IRR model
│   ├── 4_Energy_Model.py         # 24-h solar vs load simulation (ERA5-Land driven)
│   ├── 5_Regional_Map.py         # District GIS + GEE satellite layers
│   ├── 6_Scenario_Simulator.py   # National roll-out projection
│   ├── 7_PESTLE_Analysis.py      # Socio-technical feasibility framework
│   ├── 8_Climate_GEE.py          # ERA5-Land daily/monthly + EO spot queries
│   ├── 9_Data_Pipeline.py        # ETL architecture + job monitor
│   └── 10_GEE_Test.py            # GEE connection diagnostics
│
├── data/
│   └── bangladesh_data.py        # Reference tables (districts, crops, PESTLE)
│
├── models/
│   └── techno_economic.py        # FAO-56 water balance + financial engine
│
└── utils/
    ├── climate.py                # GEE ERA5-Land + EO functions
    ├── db.py                     # SQLite persistence layer
    ├── geo.py                    # Geodesic area measurement
    ├── maps.py                   # Folium map builders + GEE raster overlays
    ├── map_search.py             # In-map search bar (MacroElement)
    └── footer.py                 # Global footer
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.10 minimum (uses `X \| Y` type hints) |
| Google Earth Engine account | — | Free at [earthengine.google.com](https://earthengine.google.com) |
| GEE Cloud project | — | Create at [console.cloud.google.com](https://console.cloud.google.com) |
| `earthengine-api` CLI | 0.1.404+ | Installed via pip |

---

## Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/smartsip-dss.git
cd smartsip-dss
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and set:

```env
APP_MODE=production
GEE_PROJECT_ID=your-gee-cloud-project-id
```

> **`APP_MODE`** — set to `production` to enable live GEE data. Any other value (or omitting it) runs in demo mode: GEE calls are skipped and the app falls back to seasonal estimates labelled as placeholders.

> **`GEE_PROJECT_ID`** — your Google Cloud project ID that has the Earth Engine API enabled. Find it in the [Cloud Console](https://console.cloud.google.com) or the top-left of the [GEE Code Editor](https://code.earthengine.google.com).

### 5. Authenticate with Google Earth Engine

Run this once in the same terminal / user account that will run Streamlit:

```bash
earthengine authenticate
```

This opens a browser tab, asks you to sign in with the Google account that owns your GEE project, and stores credentials at `~/.config/earthengine/credentials`. No JSON key file is needed.

### 6. Verify the connection (optional but recommended)

```bash
python -c "import ee; ee.Initialize(project='your-gee-project-id'); print(ee.Number(1).add(1).getInfo())"
```

Expected output: `2`

---

## Running the App

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

On first run the SQLite database (`data/smartsip.db`) is created automatically. No data is pre-loaded — navigate to **☁ Climate & GEE** and click **Fetch / refresh** to populate the cache for your first district.

### Troubleshooting GEE connection

| Error | Fix |
|---|---|
| `Please use Project` | Add `GEE_PROJECT_ID=<your-project>` to `.env` and restart. |
| `Credentials not found` | Re-run `earthengine authenticate` as the same OS user that runs Streamlit. |
| `Behind a proxy` | Set `HTTPS_PROXY=http://your-proxy:port` before launching. |
| GEE buttons greyed out | Check `APP_MODE=production` is in `.env` and the app was restarted. |
| Use **🛰 GEE Test** page | Step-by-step diagnostics with specific error messages for each dataset. |

---

## Page-by-Page Guide

### 📊 Dashboard
Aggregates everything cached in SQLite. Shows ERA5-Land GHI/temperature charts for every fetched district (overlay or individual drilldown), Sentinel-2 NDVI bars, SRTM elevation bars, JRC flood risk bars, solar adoption by district, aquifer vulnerability, and the pipeline job log.

### 📍 Site Analyser
1. Select a district or pan the satellite map.
2. Use the **polygon** or **rectangle** draw tool to outline the farm.
3. Area is measured on the WGS-84 ellipsoid (geodesic) and cross-checked against a local equal-area projection — both methods must agree within 0.01 % or a warning is shown.
4. Fill in name, crop, upazila and notes, then **Save Parcel**. GEE is queried for NDVI, elevation and flood risk at the centroid.
5. Tab 2 lists all saved parcels with monthly ETc demand, hydraulic sizing and ERA5-Land solar/generation charts. A **→ Business Case** button pre-fills the next page.

### ₿ Business Case
- Parcel dropdown pre-fills from SQLite; or enter parameters manually.
- **Auto-size** (default): ERA5-Land monthly climatology → FAO-56 crop water balance (accounting for effective rainfall and percolation) → design flow → TDH → pump kW → PV kWp (sized for both peak power and monthly energy, derated for cell temperature).
- **Manual override**: slide pump kW and PV kWp directly.
- All costs in BDT (~2024 placeholder rates — verify with local suppliers before publishing).
- Sensitivity chart: payback vs subsidy level (0–60%).
- All runs saved to SQLite. CSV export.

### ⚡ Energy Model
Selects a month and simulates hour-by-hour using the parcel's ERA5-Land monthly mean GHI and actual sunrise/sunset times at the parcel latitude. Loads: irrigation pump, cold storage, e-rickshaw chargers (07:00–22:00), post-harvest machinery. Surplus allocation donut. Full-year monthly generation vs irrigation bar chart.

### 🗺 Regional Map
- **Map type**: Google Satellite (Hybrid), Roadmap, or Terrain.
- **Data layer**: solar adoption, diesel pump density, GHI, subsidy priority, aquifer risk — colour-coded circle markers sized by pump count.
- **GEE overlays** (layer control, top-right): Sentinel-2 true colour, Sentinel-2 NDVI, SRTM elevation, JRC flood occurrence.
- **Search bar**: type a district name, parcel name, village name, or `lat, lon` coordinates. Local gazetteer resolves instantly; place names go to Photon/Nominatim on Enter.
- **Fetch ERA5-Land GHI** button replaces placeholder GHI values in the map and table with live GEE values (cached).
- District bubble click shows popup with all attributes.

### ⟳ Scenario Simulator
Expand **National drivers** in the sidebar to see and edit all assumptions:
- Total diesel pumps (default 3.4 M — verify against the BADC minor-irrigation survey)
- Average pump kW, pumping hours/day, irrigation days/year
- Gross system cost per installation (derived from the same unit costs as Business Case by default)

The CO₂ baseline is computed from these same drivers, not a hard-coded constant, so changing assumptions keeps everything consistent. Save to SQLite with the **💾 Save this scenario** button.

### ⊞ PESTLE Analysis
Scores are editable in `data/bangladesh_data.py` → `PESTLE_SCORES`. Radar chart with a 7.0 target threshold. Waterfall composite breakdown. All scores are clearly captioned as expert-judgement placeholders.

### ☁ Climate & GEE
Four tabs:
- **Daily series**: last 365 days of GHI, Tmax/Tmean/Tmin and rainfall from ERA5-Land.
- **Monthly climatology**: 12-month mean for any point; builds the crop water balance and ETo (Hargreaves-Samani).
- **All districts**: fetch and compare ERA5-Land climatologies for all 12 districts.
- **EO spot query**: Sentinel-2 NDVI (60-day cloud-filtered median), SRTM elevation, JRC flood risk %, MODIS land cover class — all cached in SQLite.

### 🛰 GEE Test
Use this page first to confirm your setup before running the full app. Checks: earthengine-api import, credentials file, `ee.Initialize()`, server round-trip (`ee.Number(1).add(1) = 2`), and a live query of each of the five datasets with timing shown per query.

---

## Replacing Placeholder Data

### District survey data

Add `data/districts.csv` with at minimum these columns (same names as the `DISTRICTS` DataFrame):

```
district, division, lat, lon, ghi, diesel_pumps, solar_pct, priority,
area_km2, crop_zone, gw_depth_m, gw_trend, aquifer_risk
```

The app detects and loads it on startup and labels its source accordingly everywhere.

### Unit costs

Edit the constants at the top of `models/techno_economic.py`:

```python
PANEL_COST_PER_KWP     = 85_000   # BDT
INVERTER_COST_PER_KW   = 12_000
DIESEL_PRICE_PER_LITRE = 110
# ... etc.
```

### PESTLE scores

Edit `PESTLE_SCORES` in `data/bangladesh_data.py`.

### National pump count

Set in the **Scenario Simulator** sidebar → expand **National drivers** → edit **Diesel irrigation pumps (national)**.

---

## Tech Stack

| Category | Library | Version | Purpose |
|---|---|---|---|
| Web framework | Streamlit | 1.35.0 | Multi-page DSS UI |
| Earth Engine | earthengine-api | 0.1.404 | GEE Python client |
| Mapping | Folium | 0.16.0 | Leaflet.js maps |
| Mapping | streamlit-folium | 0.20.0 | Folium in Streamlit |
| Geospatial | GeoPandas | 0.14.4 | Spatial dataframes |
| Geospatial | Shapely | 2.0.4 | Geometry operations |
| Geospatial | pyproj | 3.6.1 | Geodesic measurement / CRS |
| Visualisation | Plotly | 5.22.0 | Interactive charts |
| Data | pandas | 2.2.2 | Tabular processing |
| Numerics | NumPy | 1.26.4 | Array computation |
| Finance | SciPy | 1.13.1 | IRR (Newton-Raphson) |
| Solar physics | pvlib | 0.10.5 | Solar modelling reference |
| Storage | SQLite (built-in) | — | Local cache + job log |
| Config | python-dotenv | 1.0.1 | `.env` loading |

**GEE datasets used:**

| Dataset | Collection ID | Resolution | Use |
|---|---|---|---|
| ERA5-Land daily | `ECMWF/ERA5_LAND/DAILY_AGGR` | ~9 km | GHI, temperature, rainfall, wind |
| Sentinel-2 SR | `COPERNICUS/S2_SR_HARMONIZED` | 10 m | NDVI, true-colour composite |
| SRTM elevation | `USGS/SRTMGL1_003` | 30 m | Elevation above sea level |
| JRC Global Surface Water | `JRC/GSW1_4/GlobalSurfaceWater` | 30 m | Flood / inundation history |
| MODIS Land Cover | `MODIS/061/MCD12Q1` | 500 m | Land use / crop class |

---

## Known Limitations

- District attributes (adoption %, pump counts, groundwater, aquifer risk) are **illustrative placeholders** — not BBS/BADC/BWDB survey data.
- ERA5-Land resolution is ~9 km. Two parcels within the same ERA5-Land cell share identical climate data.
- GEE ERA5-Land has a real-time lag of approximately 5–7 days.
- Sentinel-2 NDVI can return `null` if no cloud-free scene exists within the 60-day window; the app shows a clear warning when this happens.
- No user authentication — all data in SQLite is shared by everyone who runs the same instance.
- Scheduled automatic GEE refresh is not implemented; all fetches are on-demand.

---

## Licence
© Vedant Varma · All Rights Reserved 
