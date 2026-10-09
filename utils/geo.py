"""
Title: Accurate parcel geometry for SMART-SIP+ DSS Prototype.

MADE BY: VEDANT VARMA
©Vedant Varma | All Rights Reserved
CREATED AT: 05/10/26
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pyproj import Geod, Transformer
from shapely.geometry import shape
from shapely.ops import transform as shp_transform
from shapely.validation import explain_validity, make_valid

_GEOD = Geod(ellps="WGS84")

# Generous bounding box around Bangladesh (lat_min, lat_max, lon_min, lon_max)
_BD_BBOX = (20.3, 26.9, 87.8, 93.0)

LARGE_PARCEL_HA = 500.0     # warn above this - probably a village / block, not a farm
TINY_PARCEL_M2 = 10.0       # warn below this - probably a mis-click
XCHECK_TOL = 1e-4           # 0.01 % allowed disagreement between the two methods


@dataclass
class ParcelGeometry:
    """Result of measuring one drawn shape."""
    ok: bool = False                       # False => do not save (see ``errors``)
    area_m2: float = 0.0
    area_ha: float = 0.0
    perimeter_m: float = 0.0
    centroid_lat: float | None = None
    centroid_lon: float | None = None
    n_vertices: int = 0
    projected_area_m2: float | None = None  # independent cross-check
    xcheck_rel_diff: float | None = None    # |geodesic - projected| / geodesic
    method: str = "Geodesic area, WGS-84 ellipsoid (pyproj.Geod)"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def extract_geometry(obj) -> dict | None:
    """Return a GeoJSON *geometry* dict from a Feature / geometry / JSON string."""
    if obj is None:
        return None
    if isinstance(obj, (str, bytes)):
        try:
            obj = json.loads(obj)
        except (ValueError, TypeError):
            return None
    if not isinstance(obj, dict):
        return None
    t = obj.get("type")
    if t == "Feature":
        return obj.get("geometry")
    if t == "FeatureCollection":
        for f in obj.get("features", []):
            if (f.get("geometry") or {}).get("type") in ("Polygon", "MultiPolygon"):
                return f["geometry"]
        return None
    return obj if t else None


def _ring_area_perimeter(coords) -> tuple[float, float]:
    """Geodesic |area| (m²) and perimeter (m) of one ring (closing vertex dropped)."""
    pts = list(coords)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    area, perim = _GEOD.polygon_area_perimeter(lons, lats)
    return abs(area), abs(perim)


def _polygon_area_perimeter(poly) -> tuple[float, float]:
    area, perim = _ring_area_perimeter(poly.exterior.coords)
    for hole in poly.interiors:                       # holes subtract area
        h_area, h_perim = _ring_area_perimeter(hole.coords)
        area -= h_area
        perim += h_perim
    return area, perim


def _polygon_parts(geom) -> list:
    """Flatten any shapely geometry into a list of Polygon parts."""
    if geom.geom_type == "Polygon":
        return [geom]
    if hasattr(geom, "geoms"):
        parts = []
        for g in geom.geoms:
            parts.extend(_polygon_parts(g))
        return parts
    return []


def _laea_crs(lat0: float, lon0: float) -> str:
    return (f"+proj=laea +lat_0={lat0:.8f} +lon_0={lon0:.8f} "
            "+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs")


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #

def measure_parcel(geojson) -> ParcelGeometry:
    """
    Measure a drawn shape.  ``geojson`` may be a Feature, a geometry, or a JSON
    string of either.  Never raises - problems are reported in ``.errors``.
    """
    res = ParcelGeometry()

    geom_dict = extract_geometry(geojson)
    if not geom_dict:
        res.errors.append("No geometry found.")
        return res
    gtype = geom_dict.get("type")
    if gtype not in ("Polygon", "MultiPolygon"):
        res.errors.append(
            f"A {gtype or 'unknown'} shape has no area - draw a polygon or rectangle.")
        return res

    try:
        geom = shape(geom_dict)
    except Exception as exc:                                    # malformed coords
        res.errors.append(f"Could not read the shape: {exc}")
        return res
    if geom.is_empty:
        res.errors.append("The shape is empty.")
        return res

    # --- validity (bow-ties etc.) ------------------------------------------
    measure_geom = geom
    if not geom.is_valid:
        res.errors.append(
            "The outline crosses itself (" + explain_validity(geom).split("[")[0].strip()
            + "). Area would be unreliable - delete it and redraw without crossing lines.")
        measure_geom = make_valid(geom)        # still measured, so the user sees a number

    parts = _polygon_parts(measure_geom)
    if not parts:
        res.errors.append("The shape has no enclosed area.")
        return res

    # --- geodesic area / perimeter -----------------------------------------
    area = perim = 0.0
    for p in parts:
        a, pm = _polygon_area_perimeter(p)
        area += a
        perim += pm
    if area <= 0:
        res.errors.append("The shape encloses zero area.")
        return res

    # --- independent cross-check + true centroid (local equal-area CRS) ----
    minx, miny, maxx, maxy = measure_geom.bounds
    lat0, lon0 = (miny + maxy) / 2.0, (minx + maxx) / 2.0
    crs = _laea_crs(lat0, lon0)
    fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    proj_geom = shp_transform(fwd.transform, measure_geom)
    proj_area = proj_geom.area
    c = proj_geom.centroid
    c_lon, c_lat = inv.transform(c.x, c.y)

    res.area_m2 = area
    res.area_ha = area / 10_000.0
    res.perimeter_m = perim
    res.centroid_lat, res.centroid_lon = c_lat, c_lon
    res.n_vertices = sum(len(p.exterior.coords) - 1 for p in parts)
    res.projected_area_m2 = proj_area
    res.xcheck_rel_diff = abs(area - proj_area) / area

    if res.xcheck_rel_diff > XCHECK_TOL:
        res.warnings.append(
            f"Two independent area methods disagree by {res.xcheck_rel_diff:.3%} - "
            "check the outline.")

    # --- plausibility warnings ----------------------------------------------
    if area < TINY_PARCEL_M2:
        res.warnings.append(f"Very small shape ({area:.1f} m²) - was that a mis-click?")
    if res.area_ha > LARGE_PARCEL_HA:
        res.warnings.append(
            f"{res.area_ha:,.0f} ha is very large for one farm parcel - "
            "did you outline a whole village or block?")
    la0, la1, lo0, lo1 = _BD_BBOX
    if not (la0 <= c_lat <= la1 and lo0 <= c_lon <= lo1):
        res.warnings.append("This shape is outside Bangladesh.")

    res.ok = not res.errors
    return res


def measure_drawings(drawings: list | None) -> list[ParcelGeometry]:
    """Measure every shape returned by streamlit-folium's ``all_drawings``."""
    return [measure_parcel(d) for d in (drawings or [])]


def with_measurements(feature, pg: ParcelGeometry) -> dict:
    """
    Return the drawn Feature with the measurement stored in its ``properties``
    so the saved GeoJSON documents how its area was obtained.
    """
    feat = feature if isinstance(feature, dict) else json.loads(feature)
    props = dict(feat.get("properties") or {})
    props.update({
        "area_ha": round(pg.area_ha, 6),
        "perimeter_m": round(pg.perimeter_m, 2),
        "area_method": "geodesic_wgs84",
    })
    return {**feat, "properties": props}
