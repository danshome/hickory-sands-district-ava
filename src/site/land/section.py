"""The slice through the district: part of TWDB's section line A-A'.

From TWDB's Llano Uplift groundwater model (GAM v1.01: model row 239, its
cells' layer tops and bottoms), its row 239 line and fault lines (source
geodatabase, committed in resources/aquifer/), USGS 3DEP 1 arc-second
elevation, the shifted USGS geology, the site's boundary and the 3D aquifer
page's well reports, make() gives what the page draws along the slice, as
docs/assets/land/section.json holds it:

    length_ft, ve, rule_ft, z_top, z_base
        The slice's length (its cells' count times CELL_FT, exactly), the
        vertical exaggeration, the rule's elevation, and the drawing's top
        and base (feet above sea level).
    classes, colours, hickory_layer, precambrian_layer
        The well classes and the colour each is drawn in, and the model's
        layers of the Hickory and the Precambrian: land.js draws by these,
        so they are the parameters', never typed again in the script.
    ground
        [[s, z], ...]: the ground every GROUND_STEP_FT * GROUND_KEEP feet
        along the slice from its north-west end, in feet.
    cols
        [[s0, s1, hickory top, hickory bottom, base top, top layer], ...]:
        each model column (a quarter-mile cell, flat), its Hickory (layer 7;
        null where the model has none), the top of the Precambrian (layer 8)
        or else the base of the rock above it, and its topmost layer.
    district, surface_hickory, core
        [[s0, s1], ...]: where the slice runs inside the proposed revision,
        across the formation at the surface (the shifted geologic map), and
        where the model's topmost layer is the Precambrian.
    faults
        [s, ...]: where the fault lines of TWDB's model data cross it.
    wells
        [{uid, s, depth, ground, log: [[top, bottom, class, words]]}]: the
        wells on the slice, each with its report number and the driller's
        words only.

All distances are along the row 239 line, which is straight in the model's
own projection (TWDB's GAM Albers, US survey feet), from column COL_NW's
north-west edge.
"""

import itertools
import json
import math

from osgeo import gdal
from osgeo import ogr
from osgeo import osr

from . import params
from . import rules

gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()


def nad83():
    """NAD83 geographic, longitude first."""
    sr = osr.SpatialReference()
    sr.ImportFromEPSG(4269)
    sr.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return sr


def read_geojson(path):
    """A GeoJSON file's features."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["features"]


def geometry(feature, srs=None):
    """A GeoJSON feature's geometry as an OGR geometry, valid."""
    geom = ogr.CreateGeometryFromJson(json.dumps(feature["geometry"]))
    if srs is not None:
        geom.AssignSpatialReference(srs)
    return geom if geom.IsValid() else geom.MakeValid()


def parts(geom):
    """A geometry's parts (itself when it is a single geometry)."""
    count = geom.GetGeometryCount()
    if geom.GetGeometryName() in ("LINESTRING", "POINT") or not count:
        return [geom]
    out = []
    for i in range(count):
        out += parts(geom.GetGeometryRef(i))
    return out


class Line:
    """The row 239 line in the model's projection, and distances along it.

    Attributes:
        geom: The line, an OGR geometry in the model's projection.
        start: Its first point (x, y), the north-west end of row 239.
        unit: Its direction, a unit vector.
        to_gam: NAD83 to the model's projection.
        to_ll: The model's projection to NAD83.
        offset: Where the slice starts along the line (set by Section).
    """

    def __init__(self, line_path, gam_srs):
        """Reads the committed line and puts it in the model's projection.

        Args:
            line_path: resources/aquifer/twdb-gam-row239-EPSG4269.geojson.
            gam_srs: The model's projection (its GeoPackage's).

        Raises:
            SystemExit: The file is not one line of two points.
        """
        ll = nad83()
        self.to_gam = osr.CoordinateTransformation(ll, gam_srs)
        self.to_ll = osr.CoordinateTransformation(gam_srs, ll)
        (feature,) = read_geojson(line_path)
        points = [
            p for part in parts(geometry(feature)) for p in part.GetPoints()
        ]
        if len(points) != 2:
            raise SystemExit(f"{line_path}: not a straight line of 2 points")
        (x0, y0, _), (x1, y1, _) = (
            self.to_gam.TransformPoint(*p[:2]) for p in points
        )
        length = math.hypot(x1 - x0, y1 - y0)
        self.start = (x0, y0)
        self.unit = ((x1 - x0) / length, (y1 - y0) / length)
        self.geom = ogr.Geometry(ogr.wkbLineString)
        self.geom.AddPoint_2D(x0, y0)
        self.geom.AddPoint_2D(x1, y1)
        self.geom.AssignSpatialReference(gam_srs)
        self.offset = 0.0

    def along(self, x, y):
        """A model position's distance along the line and off it (feet).

        Returns:
            (s, d): s from the slice's start, d to the line's right.
        """
        dx, dy = x - self.start[0], y - self.start[1]
        ux, uy = self.unit
        return dx * ux + dy * uy - self.offset, -dx * uy + dy * ux

    def at(self, s):
        """The NAD83 longitude and latitude s feet along the slice."""
        ux, uy = self.unit
        x = self.start[0] + ux * (s + self.offset)
        y = self.start[1] + uy * (s + self.offset)
        lon, lat, _ = self.to_ll.TransformPoint(x, y)
        return lon, lat

    def lonlat(self, lon, lat):
        """A NAD83 position's (s, d) along the slice, in feet."""
        x, y, _ = self.to_gam.TransformPoint(lon, lat)
        return self.along(x, y)

    def crossings(self, geom):
        """The intervals [s0, s1] of the line inside a polygon (model CRS).

        Args:
            geom: A polygon geometry in the model's projection.

        Returns:
            Sorted [s0, s1] pairs, from the slice's start.
        """
        out = []
        if not geom.Intersects(self.geom):
            return out
        for part in parts(geom.Intersection(self.geom)):
            if part.GetGeometryName() != "LINESTRING":
                continue
            n = part.GetPointCount()
            a = self.along(part.GetX(0), part.GetY(0))[0]
            b = self.along(part.GetX(n - 1), part.GetY(n - 1))[0]
            out.append(sorted((a, b)))
        return sorted(out)

    def points(self, geom):
        """The distances s where a line geometry crosses the line."""
        if not geom.Intersects(self.geom):
            return []
        return sorted(
            self.along(p.GetX(), p.GetY())[0]
            for p in parts(geom.Intersection(self.geom))
            if p.GetGeometryName() == "POINT"
        )


def clip_join(intervals, length):
    """Intervals clipped to [0, length], touching ones joined, rounded."""
    out = []
    for lo, hi in sorted(intervals):
        a, b = max(0.0, lo), min(length, hi)
        if b <= a:
            continue
        if out and a - out[-1][1] < params.JOIN_FT:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [[round(a), round(b)] for a, b in out]


def columns(gpkg, line):
    """The model's cells of the slice, by column, and the slice's start.

    Args:
        gpkg: The model's GAM Properties GeoPackage.
        line: The Line.

    Returns:
        A list of {"col", "s0", "s1", "layers": {layer: (top, bottom)}},
        north-west first, with s from column COL_NW's edge (line.offset is
        set to that edge).

    Raises:
        SystemExit: The line does not cross each column's cells once.
    """
    ds = ogr.Open(gpkg)
    cells = ds.GetLayer(0)
    cells.SetAttributeFilter(
        f"row = {params.ROW} AND col >= {params.COL_NW} "
        f"AND col <= {params.COL_SE}"
    )
    layers, span = {}, {}
    for f in cells:
        col = f.GetField("col")
        layers.setdefault(col, {})[f.GetField("lay")] = (
            f.GetField("top"),
            f.GetField("botm"),
        )
        if col not in span:
            span[col] = line.crossings(f.GetGeometryRef())
    out = []
    for col in range(params.COL_NW, params.COL_SE + 1):
        if len(span.get(col, ())) != 1:
            raise SystemExit(
                f"model row {params.ROW}, column {col}: the line crosses its "
                f"cells {span.get(col)}, not once"
            )
        ((s0, s1),) = span[col]
        out.append({"col": col, "s0": s0, "s1": s1, "layers": layers[col]})
    line.offset = out[0]["s0"]
    for c in out:
        c["s0"] -= line.offset
        c["s1"] -= line.offset
    return out


class Ground:
    """The ground along the slice, from USGS 3DEP 1 arc-second (bilinear).

    Attributes:
        samples: [[s, z_ft], ...] every GROUND_STEP_FT, and at the end.
    """

    def __init__(self, tiles, line, length):
        """Samples the ground.

        Args:
            tiles: The 3DEP GeoTIFFs' paths (LINE_TILES).
            line: The Line.
            length: The slice's length, feet.

        Raises:
            SystemExit: A sample falls where the tiles have no data.
        """
        vrt = gdal.BuildVRT("", list(tiles))
        band = vrt.GetRasterBand(1)
        nodata = band.GetNoDataValue()
        gt = vrt.GetGeoTransform()
        step = params.GROUND_STEP_FT
        where = [i * step for i in range(int(length // step) + 1)]
        if where[-1] < length:
            where.append(length)
        self.samples = []
        for s in where:
            lon, lat = line.at(s)
            px = (lon - gt[0]) / gt[1] - 0.5
            py = (lat - gt[3]) / gt[5] - 0.5
            ix, iy = math.floor(px), math.floor(py)
            fx, fy = px - ix, py - iy
            win = band.ReadAsArray(ix, iy, 2, 2).astype(float)
            if nodata is not None and (win == nodata).any():
                raise SystemExit(f"no 3DEP elevation at {lat:.5f}, {lon:.5f}")
            z = (
                win[0, 0] * (1 - fx) * (1 - fy)
                + win[0, 1] * fx * (1 - fy)
                + win[1, 0] * (1 - fx) * fy
                + win[1, 1] * fx * fy
            )
            self.samples.append([s, z / params.M_PER_FT])

    def at(self, s):
        """The ground at s, interpolated between the samples (feet)."""
        pts = self.samples
        if s <= pts[0][0]:
            return pts[0][1]
        for (sa, za), (sb, zb) in itertools.pairwise(pts):
            if sa <= s <= sb:
                return za + (zb - za) * (s - sa) / (sb - sa)
        return pts[-1][1]


def column_record(c):
    """A column as section.json holds it (see the module's docstring)."""
    lay = c["layers"]
    top_layer = min(lay)
    hickory = lay.get(params.HICKORY_LAYER)
    if params.PRECAMBRIAN_LAYER in lay:
        base_top = lay[params.PRECAMBRIAN_LAYER][0]
    else:
        base_top = min(bot for _, bot in lay.values())
    return [
        round(c["s0"]),
        round(c["s1"]),
        round(hickory[0], 1) if hickory else None,
        round(hickory[1], 1) if hickory else None,
        round(base_top, 1),
        top_layer,
    ]


def near_wells(heads, line, length):
    """The logged wells with a depth near the slice.

    Args:
        heads: The 3D page's well heads (wells/heads-<n>.json rows: uid, lon,
            lat, depth_ft, ..., water_basis at index 9).
        line: The Line.
        length: The slice's length, feet.

    Returns:
        A list of {"uid", "lon", "lat", "s", "off_ft", "depth"}.
    """
    buffer_ft = params.WELL_BUFFER_M / params.M_PER_US_FT
    out = []
    for h in heads:
        uid, lon, lat, depth, basis = h[0], h[1], h[2], h[3], h[9]
        if not depth or basis == 2:  # no depth, or no log
            continue
        s, d = line.lonlat(lon, lat)
        if 0 <= s <= length and abs(d) <= buffer_ft:
            out.append(
                {
                    "uid": uid,
                    "lon": lon,
                    "lat": lat,
                    "s": s,
                    "off_ft": abs(d),
                    "depth": depth,
                }
            )
    return out


def one_per_mile(wells):
    """The deepest well in each mile of the slice that has one.

    On a tie, the first in the 3D page's heads files (TWDB's own order).

    Args:
        wells: near_wells()'s list, in the heads files' order.

    Returns:
        The chosen wells, north-west first.
    """
    chosen = {}
    every = params.WELL_EVERY_MI * params.FT_PER_MI
    for i, w in enumerate(wells):
        k = int(w["s"] // every)
        rank = (-w["depth"], i)
        if k not in chosen or rank < chosen[k][0]:
            chosen[k] = (rank, w)
    return sorted((w for _, w in chosen.values()), key=lambda w: w["s"])


def make(paths, details):
    """Everything the page draws along the slice, and its figures.

    Args:
        paths: The inputs by name: "gpkg" (the model's GeoPackage),
            "twdb-gam-row239", "twdb-gam-faults", "usgs-sgmc-shifted",
            "site-boundary", the LINE_TILES' names, and "heads" (the heads
            files).
        details: A function from (cell, uid) to the well's report.

    Returns:
        (section, figures, counts): section.json's dict; the figures the
        page shows, by name; and further counts for the record of the run.
    """
    ds = ogr.Open(paths["gpkg"])
    gam = ds.GetLayer(0).GetSpatialRef().Clone()
    gam.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ds = None
    line = Line(paths["twdb-gam-row239"], gam)
    cols = columns(paths["gpkg"], line)
    length = len(cols) * params.CELL_FT  # exact: never rounds across a tie
    if abs(cols[-1]["s1"] - length) > 1:
        raise SystemExit(f"the columns span {cols[-1]['s1']} ft, not {length}")
    ground = Ground([paths[t] for t in params.LINE_TILES], line, length)
    ll = nad83()

    def in_model(geom):
        g = geom.Clone()
        g.AssignSpatialReference(ll)
        g.TransformTo(gam)
        return g

    # The proposed district, and the formation at the surface.
    (district_f,) = read_geojson(paths["site-boundary"])
    district = clip_join(line.crossings(in_model(geometry(district_f))), length)
    geo = ogr.Open(paths["usgs-sgmc-shifted"])
    surface = []
    for f in geo.GetLayerByName(params.GEOLOGY_LAYER):
        g = f.GetGeometryRef().Clone()
        g = g if g.IsValid() else g.MakeValid()
        surface += line.crossings(in_model(g))
    surface = clip_join(surface, length)
    geo = None
    # The faults of TWDB's model data that cross the slice.
    faults = []
    for f in read_geojson(paths["twdb-gam-faults"]):
        faults += [
            s for s in line.points(in_model(geometry(f))) if 0 <= s <= length
        ]
    faults = sorted(round(s) for s in faults)

    records = [column_record(c) for c in cols]
    core = clip_join(
        [[c[0], c[1]] for c in records if c[5] == params.PRECAMBRIAN_LAYER],
        length,
    )
    kept = ground.samples[:: params.GROUND_KEEP]
    if kept[-1][0] != ground.samples[-1][0]:
        kept.append(ground.samples[-1])
    drawn = [[round(s), round(z, 1)] for s, z in kept]
    z_top = (
        math.ceil(
            (max(z for _, z in drawn) + params.Z_ABOVE_FT) / params.Z_ROUND_FT
        )
        * params.Z_ROUND_FT
    )
    bottoms = [c[3] for c in records if c[3] is not None]
    z_base = (
        math.floor((min(bottoms) - params.Z_BELOW_FT) / params.Z_ROUND_FT)
        * params.Z_ROUND_FT
    )

    # The wells.
    heads = []
    for path in paths["heads"]:
        with open(path, encoding="utf-8") as fh:
            heads += json.load(fh)
    near = near_wells(heads, line, length)
    picked = one_per_mile(near)
    wells = []
    for w in picked:
        report = details(rules.detail_cell(w["lon"], w["lat"]), w["uid"])
        log = [
            [round(a, 1), round(b, 1), cls, words]
            for a, b, cls, words in rules.log_of(report, w["depth"])
        ]
        wells.append(
            {
                "uid": w["uid"],
                "s": round(w["s"]),
                "depth": w["depth"],
                "ground": round(ground.at(w["s"]), 1),
                "log": log,
            }
        )

    nw_ground = ground.samples[0][1]
    nw_hickory = records[0][2]
    if nw_hickory is None:
        raise SystemExit("the model has no Hickory at the slice's NW end")
    depth = nw_ground - nw_hickory
    inside = [
        z for s, z in ground.samples if any(a <= s <= b for a, b in district)
    ]
    section = {
        "length_ft": length,
        "ve": params.VE,
        "rule_ft": params.RULE_FT,
        "classes": list(params.CLASSES),
        "colours": list(params.CLASS_COLOURS),
        "hickory_layer": params.HICKORY_LAYER,
        "precambrian_layer": params.PRECAMBRIAN_LAYER,
        "z_top": z_top,
        "z_base": z_base,
        "ground": drawn,
        "cols": records,
        "district": district,
        "surface_hickory": surface,
        "core": core,
        "faults": faults,
        "wells": wells,
    }
    # Step 5's last one-mile stretch, in whole model cells.
    cells_left = (length % params.FT_PER_MI) / params.CELL_FT
    if cells_left not in params.LAST_STRETCH_WORDS:
        raise SystemExit(
            f"the slice's last stretch is {cells_left} cells: step 5 says "
            "it is shorter than a mile, in words for 1 to 3 cells; reword it"
        )
    figures = {
        "rule_ft": params.RULE_FT,
        "last_stretch": params.LAST_STRETCH_WORDS[cells_left],
        "ve": params.VE,
        "model_row": params.ROW,
        "line_mi": round(length / params.FT_PER_MI, 2),
        "mile_stretches": math.ceil(length / params.FT_PER_MI),
        "cell_ft": params.CELL_FT,
        "district_stretches": len(district),
        "depth_top_nw_ft": round(depth / params.DEPTH_ROUND_FT)
        * params.DEPTH_ROUND_FT,
        "wells_on_section": len(wells),
        "well_buffer_m": params.WELL_BUFFER_M,
    }
    (nw_lon, nw_lat), (se_lon, se_lat) = line.at(0), line.at(length)
    counts = {
        "columns": len(cols),
        "ends_nad83": [
            [round(nw_lon, 6), round(nw_lat, 6)],
            [round(se_lon, 6), round(se_lat, 6)],
        ],
        "district_mi": [
            [round(a / params.FT_PER_MI, 2), round(b / params.FT_PER_MI, 2)]
            for a, b in district
        ],
        "surface_hickory_mi": [
            [round(a / params.FT_PER_MI, 2), round(b / params.FT_PER_MI, 2)]
            for a, b in surface
        ],
        "core_mi": [
            [round(a / params.FT_PER_MI, 2), round(b / params.FT_PER_MI, 2)]
            for a, b in core
        ],
        "faults": len(faults),
        "ground_nw_ft": round(nw_ground, 1),
        "hickory_top_nw_ft": nw_hickory,
        "depth_top_nw_exact_ft": round(depth, 1),
        "ground_in_district_ft": [round(min(inside), 1), round(max(inside), 1)],
        "wells_near_line": len(near),
        "wells_largest_offset_m": round(
            max(w["off_ft"] for w in picked) * params.M_PER_US_FT
        ),
        "wells_on_section_uids": [w["uid"] for w in wells],
    }
    return section, figures, counts
