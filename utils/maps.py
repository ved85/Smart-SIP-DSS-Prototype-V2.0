"""
Title: Map utilities for SMART-SIP+ DSS Prototype.

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""

import os
import json
import time
import hashlib
import folium
from folium.plugins import HeatMap, Draw, Fullscreen
from data.bangladesh_data import DISTRICTS
from utils.map_search import add_map_search

from utils.climate import init_gee
try:
    import ee
except Exception:                        # earthengine-api missing: maps still work without GEE layers
    ee = None

STATUS_COLOURS   = {"Solar": "#3fb950", "Diesel": "#d29922", "Barrier": "#f85149"}
PRIORITY_COLOURS = {"Low": "#3fb950", "Medium": "#d29922", "High": "#f85149"}
AQUIFER_COLOURS  = {"High": "#f85149", "Medium": "#d29922", "Low": "#3fb950", "Unknown": "#7d8590"}

TILE_OPTIONS = {
    "🛰 Google Satellite (Hybrid)": (
        "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", "Google"),
    "🗺 Google Roadmap": (
        "https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", "Google"),
    "⛰ Google Terrain": (
        "https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}", "Google"),
}
DEFAULT_TILE = "🛰 Google Satellite (Hybrid)"

# GEE tile URLs.  getMapId() is a network round-trip and returns a *new* URL each
# call; rebuilding it on every Streamlit rerun made the map's JavaScript differ
# every run, so st_folium re-mounted the map (view reset, drawings lost).  Cache
# the URLs so the map definition stays identical between reruns.
_TILE_TTL_S = 3 * 3600
_tile_cache: dict = {}


def _tile_url(cache_key, ee_image_object, vis_params):
    hit = _tile_cache.get(cache_key) if cache_key else None
    if hit and time.time() - hit[0] < _TILE_TTL_S:
        return hit[1]
    url = ee.Image(ee_image_object).getMapId(vis_params)["tile_fetcher"].url_format
    if cache_key:
        _tile_cache[cache_key] = (time.time(), url)
    return url


# Attach ee tile adder to folium.Map
def add_ee_layer(self, ee_image_object, vis_params, name, shown=True, opacity=1.0,
                 cache_key=None):
    try:
        folium.raster_layers.TileLayer(
            tiles=_tile_url(cache_key, ee_image_object, vis_params),
            attr="Map Data © Google Earth Engine",
            name=name,
            overlay=True,
            control=True,
            show=shown,
            opacity=opacity,
            max_zoom=22,
        ).add_to(self)
    except Exception as e:
        print(f"[Maps] Could not render GEE layer '{name}': {e}")

folium.Map.add_ee_layer = add_ee_layer


def _attach_gee_satellite_layers(m: folium.Map):
    """
    Renders live Sentinel-2 RGB, NDVI, SRTM DEM, and JRC Water Occurrence
    layers from GEE onto the Folium map instance.
    """
    if ee is None or not init_gee():
        return
    try:
        from datetime import date, timedelta
        _end, _start = date.today(), date.today() - timedelta(days=365)
        _tag = f"{_end:%Y%m}"
        # 1. Sentinel-2 cloud-filtered composite, rolling last 12 months
        s2 = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterDate(_start.isoformat(), _end.isoformat())
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            .median()
        )
        rgb_vis = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000, "gamma": 1.3}
        m.add_ee_layer(s2, rgb_vis, "🛰️ GEE Sentinel-2 true colour (last 12 mo)", shown=False, opacity=1.0, cache_key=f"s2_rgb_{_tag}")

        # 2. Sentinel-2 NDVI Live Vegetation Health
        nir = s2.select("B8")
        red = s2.select("B4")
        ndvi = nir.subtract(red).divide(nir.add(red)).rename("NDVI")
        ndvi_vis = {
            "min": 0.1,
            "max": 0.8,
            "palette": ["#d73027", "#f46d43", "#fdae61", "#fee08b", "#d9ef8b", "#a6d96a", "#66bd63", "#1a9850"],
        }
        m.add_ee_layer(ndvi, ndvi_vis, "🌱 GEE Sentinel-2 NDVI (last 12 mo)", shown=False, opacity=0.85, cache_key=f"s2_ndvi_{_tag}")

        # 3. SRTM 30m Digital Elevation Model
        dem = ee.Image("USGS/SRTMGL1_003")
        dem_vis = {
            "min": 0,
            "max": 80,
            "palette": ["#006600", "#339933", "#99cc33", "#ffff66", "#cc9933", "#996633", "#ffffff"],
        }
        m.add_ee_layer(dem, dem_vis, "⛰️ GEE SRTM Elevation (DEM)", shown=False, opacity=0.75, cache_key="srtm_dem")

        # 4. JRC Global Surface Water Occurrence (Flood/Inundation History)
        jrc = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence")
        jrc_vis = {
            "min": 0,
            "max": 100,
            "palette": ["#ffffff", "#ffcc00", "#ff6600", "#0000ff"],
        }
        m.add_ee_layer(jrc, jrc_vis, "💧 GEE JRC Flood Occurrence", shown=False, opacity=0.7, cache_key="jrc_water")

    except Exception as e:
        print(f"[Maps] GEE layers skipped: {e}")


def _popup(html: str, max_width: int) -> folium.Popup:
    """
    Popup whose element id is derived from its content.  folium assigns a random
    id to every popup's HTML, which made two builds of the *same* map differ and
    forced st_folium to re-mount it (view reset) on each rerun.
    """
    el = folium.Html(html, script=True)
    el._id = hashlib.md5(html.encode("utf-8")).hexdigest()
    return folium.Popup(el, max_width=max_width)


def _parcel_places(parcels) -> list:
    """Saved parcels -> search-bar gazetteer entries."""
    out = []
    for p in parcels or []:
        try:
            out.append({"name": p["name"], "lat": p["lat_centroid"], "lon": p["lon_centroid"],
                        "kind": f"Saved parcel · {p.get('district', '')}".rstrip(" ·"), "zoom": 17})
        except (KeyError, TypeError):
            pass
    return out


def _base_map(lat: float = 23.8, lon: float = 89.9,
              zoom: int = 7, tile_choice: str = DEFAULT_TILE,
              extra_places: list = None) -> folium.Map:
    tiles, attr = TILE_OPTIONS.get(tile_choice, TILE_OPTIONS[DEFAULT_TILE])
    m = folium.Map(
        location=[lat, lon],
        zoom_start=zoom,
        tiles=tiles,
        attr=attr,
        control_scale=True,
        max_zoom=22,
    )
    # Inject GEE layers
    _attach_gee_satellite_layers(m)

    Fullscreen(
        position="topright",
        title="Expand to Fullscreen",
        title_cancel="Exit Fullscreen",
        force_separate_button=True,
    ).add_to(m)

    # Search-bar overlay: districts + saved parcels + coordinates (+ optional OSM place names)
    add_map_search(m, extra_places=extra_places)

    return m


def build_parcel_draw_map(existing_parcels: list = None,
                          tile_choice: str = DEFAULT_TILE,
                          lat: float = 23.8, lon: float = 89.9, zoom: int = 7) -> folium.Map:
    m = _base_map(lat=lat, lon=lon, zoom=zoom, tile_choice=tile_choice,
                  extra_places=_parcel_places(existing_parcels))

    draw = Draw(
        draw_options={
            "polygon": True,
            "rectangle": True,
            "polyline": False,
            "circle": False,
            "marker": False,
            "circlemarker": False,
        },
        edit_options={"edit": True, "remove": True},
    )
    draw.add_to(m)

    if existing_parcels:
        for p in existing_parcels:
            try:
                geo = json.loads(p["polygon_geojson"])
                folium.GeoJson(
                    geo,
                    name=f"Parcel: {p['name']}",
                    style_function=lambda _: {
                        "fillColor": "#3fb950",
                        "color": "#2da040",
                        "weight": 2,
                        "fillOpacity": 0.25,
                    },
                    tooltip=folium.Tooltip(
                        f"<b>{p['name']}</b><br>Crop: {p.get('crop_type','—')}<br>Area: {p.get('area_ha', 0):.2f} ha",
                        sticky=True,
                    ),
                ).add_to(m)
            except Exception:
                pass

    m.get_root().html.add_child(folium.Element("""
    <div style='position:fixed;bottom:20px;left:20px;z-index:1000;
                background:rgba(22,27,34,0.92);color:#e6edf3;padding:10px 14px;
                border-radius:6px;border:1px solid #30363d;
                font-family:monospace;font-size:11px'>
      <b style='color:#3fb950'>GEE SATELLITE CANVAS</b><br>
      Use the toolbar to trace parcel boundaries.<br>
      Use top-right layer icon to toggle GEE NDVI / DEM.
    </div>"""))

    folium.LayerControl(position="topright", collapsed=True).add_to(m)
    return m


def build_site_map(parcels: list = None, selected_id: int = None,
                   tile_choice: str = DEFAULT_TILE,
                   lat: float = 23.8, lon: float = 89.9, zoom: int = 7) -> folium.Map:
    m = _base_map(lat=lat, lon=lon, zoom=zoom, tile_choice=tile_choice,
                  extra_places=_parcel_places(parcels))
    if not parcels:
        folium.LayerControl(position="topright", collapsed=True).add_to(m)
        return m

    for p in parcels:
        is_sel = p.get("id") == selected_id
        colour = "#3fb950" if is_sel else "#58a6ff"

        try:
            if p.get("polygon_geojson"):
                geo = json.loads(p["polygon_geojson"])
                folium.GeoJson(
                    geo,
                    name=f"Boundaries: {p['name']}",
                    style_function=lambda _, c=colour: {
                        "fillColor": c,
                        "color": c,
                        "weight": 3 if is_sel else 1.5,
                        "fillOpacity": 0.35,
                    },
                ).add_to(m)
        except Exception:
            pass

        popup_html = f"""
        <div style='font-family:monospace;font-size:12px;min-width:200px;
                    color:#222;background:#fff;padding:10px;border-radius:6px'>
          <b style='color:{colour}'>{p['name']}</b><br><br>
          <b>District:</b> {p.get('district','—')}<br>
          <b>Upazila:</b> {p.get('upazila','—')}<br>
          <b>Area:</b> {p.get('area_ha',0):.2f} ha ({p.get('area_orig',0):.1f} {p.get('area_unit_orig','ha')})<br>
          <b>Crop:</b> {p.get('crop_type','—')}<br>
          <b>Notes:</b> {p.get('notes','—')}
        </div>"""

        folium.CircleMarker(
            location=[p["lat_centroid"], p["lon_centroid"]],
            radius=10 if is_sel else 7,
            color=colour,
            fill=True,
            fill_color=colour,
            fill_opacity=0.8,
            weight=3 if is_sel else 1.5,
            popup=_popup(popup_html, 260),
            tooltip=f"{p['name']} ({p.get('area_ha',0):.1f} ha)",
        ).add_to(m)

    folium.LayerControl(position="topright", collapsed=True).add_to(m)
    return m


def build_regional_map(metric: str = "solar_pct",
                       tile_choice: str = DEFAULT_TILE,
                       lat: float = 23.8, lon: float = 89.9, zoom: int = 7,
                       df=None, ghi_label: str = "GHI (placeholder)") -> folium.Map:
    m = _base_map(lat=lat, lon=lon, zoom=zoom, tile_choice=tile_choice)
    DISTRICTS_ = df if df is not None else DISTRICTS

    import geopandas as gpd
    from shapely.geometry import Point

    districts_gdf = gpd.GeoDataFrame(
        DISTRICTS_.copy(),
        geometry=[Point(r.lon, r.lat) for _, r in DISTRICTS_.iterrows()],
        crs="EPSG:4326",
    )

    colour_fn = {
        "solar_pct":    lambda v: _green_red(v / 100),
        "diesel_pumps": lambda v: _heat(v / DISTRICTS_["diesel_pumps"].max()),
        "ghi":          lambda v: _heat((v - 4.0) / 1.5),
        "priority":     lambda v: PRIORITY_COLOURS.get(v, "#888"),
        "aquifer_risk": lambda v: AQUIFER_COLOURS.get(v, "#888"),
    }.get(metric, lambda v: "#58a6ff")

    district_group = folium.FeatureGroup(name="District Stats & Priority", show=True)

    for _, row in districts_gdf.iterrows():
        val    = row[metric] if metric in row.index else row.get("priority", "Low")
        colour = colour_fn(val)
        aq_col = AQUIFER_COLOURS.get(row["aquifer_risk"], "#888")

        popup_html = f"""
        <div style='font-family:monospace;font-size:12px;min-width:240px;
                    color:#222;background:#fff;padding:10px;border-radius:6px'>
          <b style='color:{colour}'>{row.district}</b> — {row.division} Division<br><br>
          <b>Diesel pumps:</b> {row.diesel_pumps:,}<br>
          <b>Solar adoption:</b> {row.solar_pct}%<br>
          <b>{ghi_label}:</b> {row.ghi:.2f} kWh/m²/day<br>
          <b>Crop zone:</b> {row.crop_zone}<br>
          <b>Groundwater depth:</b> {row.gw_depth_m} m ({row.gw_trend})<br>
          <b>Aquifer risk:</b> <span style='color:{aq_col}'>{row.aquifer_risk}</span><br>
          <b>Priority:</b> <span style='color:{PRIORITY_COLOURS[row.priority]}'>{row.priority}</span>
        </div>"""

        folium.CircleMarker(
            location=[row.lat, row.lon],
            radius=16 + (row.diesel_pumps / DISTRICTS_["diesel_pumps"].max()) * 18,
            color=colour,
            fill=True,
            fill_color=colour,
            fill_opacity=0.45,
            weight=1.5,
            popup=_popup(popup_html, 290),
            tooltip=f"{row.district}: {val}",
        ).add_to(district_group)

    district_group.add_to(m)

    HeatMap(
        [[r.lat, r.lon, r.diesel_pumps / 1000] for _, r in districts_gdf.iterrows()],
        radius=40,
        blur=30,
        min_opacity=0.1,
        name="Diesel Pump Density Heatmap",
        show=False,
    ).add_to(m)

    folium.LayerControl(position="topright", collapsed=True).add_to(m)
    return m


def _green_red(r):
    r = max(0, min(1, r))
    return "#3fb950" if r > 0.6 else "#d29922" if r > 0.35 else "#f85149"


def _heat(r):
    r = max(0, min(1, r))
    return "#3fb950" if r > 0.6 else "#39c5cf" if r > 0.3 else "#58a6ff"