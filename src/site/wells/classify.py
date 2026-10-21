"""Every drawn well, with its county, mapped rock and model cell.

The wells are the 3D aquifer page's drawing records (docs/assets/aquifer/
wells/draw-*.json; people's names and addresses already removed). Each well
takes:

- its county: the 2023 Census county (1:500,000) its position lies in;
- its mapped rock: the ORIG_LABEL of the USGS State Geologic Map
  Compilation polygon for Texas at its position less the geology's shift
  (resources/geology/README.md), so the map is moved onto the outcrops as
  the site's geology layer is;
- its model cell: the ground, the Hickory layer's top and the flags of the
  3D page's drill grid (docs/assets/aquifer/drill-grid.*).

GDAL and NumPy.
"""

import glob
import json
import os

import numpy as np
from osgeo import ogr

from ..aquifer import params as aquifer_params
from . import params

ogr.UseExceptions()

# The drawing record's fields (src/site/aquifer/wells.py, draw_record()).
DRAW_FIELDS = {
    "uid": 0,
    "lon": 1,
    "lat": 2,
    "depth": 3,
    "level": 5,
    "hickory": 7,
    "cell": 8,
    "use": 9,
    "wclass": 10,
    "wbasis": 13,
    "yield": 14,
    "ytest": 15,
}


def load(path):
    """A JSON file's data."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read_wells(folder):
    """Every drawn well, as a dict of DRAW_FIELDS.

    Args:
        folder: The 3D aquifer page's wells folder.

    Returns:
        The wells, in the tiles' order.
    """
    wells = []
    for path in sorted(glob.glob(os.path.join(folder, "draw-*.json"))):
        for row in load(path):
            wells.append({k: row[i] for k, i in DRAW_FIELDS.items()})
    return wells


def _polygons(path, field, where=None, box=None):
    """A polygon layer's features: (value, geometry, envelope)."""
    ds = ogr.Open(path)
    layer = ds.GetLayer(0)
    if where:
        layer.SetAttributeFilter(where)
    if box:
        layer.SetSpatialFilterRect(*box)
    out = []
    for feature in layer:
        geom = feature.GetGeometryRef()
        if geom is None:
            continue
        geom = geom.Clone()
        out.append((feature.GetField(field), geom, geom.GetEnvelope()))
    return out


def point_in(polys, lon, lat):
    """The value of the first polygon each point lies in, or "".

    Args:
        polys: _polygons()'s list.
        lon: The points' longitudes (NumPy array).
        lat: Their latitudes.

    Returns:
        A NumPy object array of the values.
    """
    out = np.full(len(lon), "", dtype=object)
    for value, geom, (x0, x1, y0, y1) in polys:
        idx = np.nonzero((lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1))[
            0
        ]
        for i in idx:
            if out[i]:
                continue
            point = ogr.Geometry(ogr.wkbPoint)
            point.AddPoint_2D(float(lon[i]), float(lat[i]))
            if geom.Contains(point):
                out[i] = value
    return out


def _grid(grid_json, grid_bin):
    """The drill grid's arrays and its position lookup."""
    meta = load(grid_json)
    rows, cols = meta["rows"], meta["cols"]
    with open(grid_bin, "rb") as fh:
        raw = fh.read()
    n = rows * cols
    arrays = []
    for k in range(3):
        a = np.frombuffer(raw, "<i2", n, 2 * n * k).reshape(rows, cols)
        a = a.astype(float)
        a[a == meta["null"]] = np.nan
        arrays.append(a)
    flags = np.frombuffer(raw, "<u1", n, 6 * n).reshape(rows, cols)
    return meta, arrays, flags


def rowcol(poly, lon, lat):
    """Model rows and columns of positions, by the grid's polynomial."""
    u = lon - poly["lon_c"]
    v = lat - poly["lat_c"]
    terms = [
        u ** (k - j) * v**j
        for k in range(poly["degree"] + 1)
        for j in range(k + 1)
    ]
    r = sum(a * b for a, b in zip(poly["row"], terms, strict=True))
    c = sum(a * b for a, b in zip(poly["col"], terms, strict=True))
    return np.round(r).astype(int), np.round(c).astype(int)


def classify(paths):
    """Every drawn well, with county, mapped rock and model cell.

    Args:
        paths: "wells" (the 3D page's wells folder), "counties" and
            "geology" (GDAL paths of the Census counties and the SGMC
            polygons), "grid_json" and "grid_bin" (the drill grid).

    Returns:
        The wells (read_wells()), each with "county", "unit" (the mapped
        rock's label, "" off the map), "ground", "top7", "bot7" (feet above
        sea level, None off the grid) and "flags".
    """
    wells = read_wells(paths["wells"])
    lon = np.array([w["lon"] for w in wells], float)
    lat = np.array([w["lat"] for w in wells], float)
    box = (
        float(lon.min()) - 0.01,
        float(lat.min()) - 0.01,
        float(lon.max()) + 0.01,
        float(lat.max()) + 0.01,
    )
    counties = _polygons(
        paths["counties"], "NAME", f"STATEFP = '{params.STATEFP}'", box
    )
    county = point_in(counties, lon, lat)
    geo_lon = lon - aquifer_params.SHIFT_LON
    geo_lat = lat - aquifer_params.SHIFT_LAT
    units = point_in(
        _polygons(paths["geology"], "ORIG_LABEL", None, box), geo_lon, geo_lat
    )
    meta, (ground, top7, bot7), flags = _grid(
        paths["grid_json"], paths["grid_bin"]
    )
    rr, cc = rowcol(meta["lonlat_to_rowcol"], lon, lat)
    ok = (rr >= 0) & (rr < meta["rows"]) & (cc >= 0) & (cc < meta["cols"])
    for i, w in enumerate(wells):
        w["county"] = county[i]
        w["unit"] = units[i]
        if ok[i]:
            cell = (rr[i], cc[i])
            for key, grid in (
                ("ground", ground),
                ("top7", top7),
                ("bot7", bot7),
            ):
                w[key] = None if np.isnan(grid[cell]) else float(grid[cell])
            w["flags"] = int(flags[cell])
        else:
            w["ground"], w["top7"], w["bot7"], w["flags"] = None, None, None, 0
    return wells


def unit_class(label):
    """The mapped rock's class.

    Returns:
        outcrop, granite, precambrian, quaternary, cover or none.
    """
    if not label:
        return "none"
    if label in params.OUTCROP_UNITS:
        return "outcrop"
    if label in params.GRANITE_UNITS:
        return "granite"
    if label.startswith(params.PRECAMBRIAN_PREFIX):
        return "precambrian"
    if label.startswith(params.QUATERNARY_PREFIXES):
        return "quaternary"
    return "cover"


def top_depth(w):
    """Feet from the model's ground down to its Hickory top, or None."""
    if w["ground"] is None or w["top7"] is None:
        return None
    if not w["flags"] & params.FLAG_LAYER7:
        return None
    return w["ground"] - w["top7"]


def downdip(w):
    """Whether a well is a downdip Hickory well (params' rule)."""
    if unit_class(w["unit"]) != "cover":
        return False
    if w["hickory"]:
        return True
    d = top_depth(w)
    subcrop = bool(w["flags"] & params.FLAG_LAYER7) and not (
        w["flags"] & params.FLAG_OUTCROP
    )
    return d is not None and subcrop and bool(w["depth"]) and w["depth"] >= d


def groups(wells):
    """The four groups the page shows, of the wells in its counties.

    Returns:
        A dict: "outcrop", "outcrop_irrigation", "granite" and "deep", each
        a list of wells.
    """
    near = [w for w in wells if w["county"] in params.COUNTIES]
    low, high = params.DEEP_TOP_FT
    out = {
        "outcrop": [w for w in near if unit_class(w["unit"]) == "outcrop"],
        "granite": [w for w in near if unit_class(w["unit"]) == "granite"],
        "deep": [
            w for w in near if downdip(w) and low <= (top_depth(w) or -1) < high
        ],
    }
    out["outcrop_irrigation"] = [
        w for w in out["outcrop"] if w["use"] == params.IRRIGATION_USE
    ]
    return out
