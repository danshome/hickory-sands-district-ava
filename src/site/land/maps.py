"""The four small maps of "Sand, height and water", and the locator.

All share one frame (params.FRAME, NAD83), drawn north up at one scale, with
the proposed district on each:

    01 Elevation   ground at RULE_FT and higher: USGS 3DEP 1 arc-second,
                   averaged onto a DEM_STEP grid, thresholded and outlined;
    02 Sand        the Hickory Sandstone Member formation at the surface (the
                   shifted USGS geology) and the Precambrian outcrop of TWDB's
                   model (the 3D aquifer page's precambrian.geojson);
    03 Water       every logged well in the frame, one dot each, coloured by
                   the page's class of the interval the 3D page colours it by
                   (src/site/land/rules.py);
    04 Together    the formation where it lies at RULE_FT and higher.

make() gives the outlines as SVG path data in the maps' own units and the
wells as dots; src/site/land/draw.py writes the SVG files.
"""

import math

import numpy as np
from osgeo import gdal
from osgeo import ogr
from osgeo import osr

from . import params
from . import rules
from .section import geometry
from .section import nad83
from .section import read_geojson

gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()


class Frame:
    """The maps' frame and their units: longitude and latitude to x, y."""

    def __init__(self):
        """Sets the scale from params.FRAME and params.MAP_W."""
        self.west, self.south, self.east, self.north = params.FRAME
        self.clat = math.cos(math.radians((self.south + self.north) / 2))
        self.k = params.MAP_W / ((self.east - self.west) * self.clat)
        self.width = params.MAP_W
        self.height = round((self.north - self.south) * self.k, 1)
        self.box = ogr.CreateGeometryFromWkt(
            f"POLYGON(({self.west} {self.south},{self.east} {self.south},"
            f"{self.east} {self.north},{self.west} {self.north},"
            f"{self.west} {self.south}))"
        )

    def xy(self, lon, lat):
        """A position in the maps' units (x right, y down)."""
        return (lon - self.west) * self.clat * self.k, (
            self.north - lat
        ) * self.k

    def contains(self, lon, lat):
        """Whether a position is inside the frame."""
        return self.west <= lon <= self.east and self.south <= lat <= self.north

    def scale_bar(self):
        """The scale bar's length in the maps' units."""
        return round(params.SCALE_KM / params.KM_PER_DEG_LAT * self.k, 1)

    def path(self, geom, tolerance):
        """A polygon geometry, clipped to the frame, as SVG path data.

        Args:
            geom: A polygon or multipolygon in NAD83, or None.
            tolerance: How much to simplify it, in degrees (0: not at all).

        Returns:
            "M x,y L ... Z" for every ring, one decimal; "" when empty.
        """
        if geom is None or geom.IsEmpty():
            return ""
        g = geom.Intersection(self.box)
        if tolerance:
            g = g.SimplifyPreserveTopology(tolerance)
        polygons = []
        stack = [g]
        while stack:
            part = stack.pop()
            name = part.GetGeometryName()
            if name == "POLYGON":
                polygons.append(part)
            elif name in ("MULTIPOLYGON", "GEOMETRYCOLLECTION"):
                stack += [
                    part.GetGeometryRef(i)
                    for i in reversed(range(part.GetGeometryCount()))
                ]
        out = []
        for poly in polygons:
            for r in range(poly.GetGeometryCount()):
                ring = poly.GetGeometryRef(r)
                pts = [
                    self.xy(ring.GetX(i), ring.GetY(i))
                    for i in range(ring.GetPointCount())
                ]
                if len(pts) < 4:
                    continue
                out.append(
                    "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z"
                )
        return "".join(out)


def polygons(geom):
    """A geometry's polygons, at any depth of a collection."""
    name = geom.GetGeometryName()
    if name == "POLYGON":
        return [geom]
    if name in ("MULTIPOLYGON", "GEOMETRYCOLLECTION"):
        out = []
        for i in range(geom.GetGeometryCount()):
            out += polygons(geom.GetGeometryRef(i))
        return out
    return []


def union(geoms):
    """The union of polygon geometries, or None."""
    multi = ogr.Geometry(ogr.wkbMultiPolygon)
    for g in geoms:
        for part in polygons(g if g.IsValid() else g.MakeValid()):
            multi.AddGeometry(part)
    return None if multi.IsEmpty() else multi.UnionCascaded()


def in_frame(frame, geoms):
    """The union of the geometries' parts inside the frame."""
    return union(
        [g.Intersection(frame.box) for g in geoms if g.Intersects(frame.box)]
    )


def high_ground(frame, tiles):
    """Ground at RULE_FT and higher in the frame, outlined (NAD83).

    Args:
        frame: The Frame.
        tiles: The 3DEP GeoTIFFs' paths (DEM_TILES).

    Returns:
        A multipolygon, or None.
    """
    vrt = gdal.BuildVRT("", list(tiles))
    nx = round((frame.east - frame.west) / params.DEM_STEP)
    ny = round((frame.north - frame.south) / params.DEM_STEP)
    dem = gdal.Warp(
        "",
        vrt,
        format="MEM",
        outputBounds=params.FRAME,
        width=nx,
        height=ny,
        resampleAlg="average",
        dstSRS="EPSG:4269",
    )
    arr = dem.GetRasterBand(1).ReadAsArray()
    mask = (arr >= params.RULE_FT * params.M_PER_FT).astype(np.uint8)
    mem = gdal.GetDriverByName("MEM").Create("", nx, ny, 1, gdal.GDT_Byte)
    mem.SetGeoTransform(dem.GetGeoTransform())
    mem.SetProjection(dem.GetProjection())
    mem.GetRasterBand(1).WriteArray(mask)
    out = ogr.GetDriverByName("MEM").CreateDataSource("land-high")
    layer = out.CreateLayer("high", nad83(), ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))
    gdal.Polygonize(mem.GetRasterBand(1), mem.GetRasterBand(1), layer, 0)
    return union(
        [f.GetGeometryRef().Clone() for f in layer if f.GetField("v") == 1]
    )


def map_wells(frame, heads, details):
    """Every logged well in the frame, classed by the page's rule.

    The interval is the one the 3D page colours the well's head by (the one
    overlapping its deepest water-bearing zone most, else the deepest), and
    its class is the first rock its driller names (rules.classify()).

    Args:
        frame: The Frame.
        heads: The 3D page's well heads.
        details: A function from (cell, uid) to the well's report.

    Returns:
        (dots, counts): [[x, y, class], ...] in the drawing order
        (params.MAP_DRAW_ORDER, sandstone and sand last), and {"classes":
        {name: count}, "reclassed": {"3d->page": count}}.
    """
    dots, reclassed = [], {}
    for h in heads:
        uid, lon, lat, depth = h[0], h[1], h[2], h[3]
        cls_3d, wtop, wbot, basis = h[6], h[7], h[8], h[9]
        if not frame.contains(lon, lat) or cls_3d == rules.UNLOGGED:
            continue
        report = details(rules.detail_cell(lon, lat), uid)
        pick = rules.water_interval(
            rules.log_of(report, depth), wtop, wbot, basis
        )
        cls = cls_3d if pick is None else pick[2]
        key = f"{params.CLASSES[cls_3d]}->{params.CLASSES[cls]}"
        if cls != cls_3d:
            reclassed[key] = reclassed.get(key, 0) + 1
        x, y = frame.xy(lon, lat)
        dots.append([round(x, 1), round(y, 1), cls])
    order = {
        params.CLASSES.index(n): i for i, n in enumerate(params.MAP_DRAW_ORDER)
    }
    dots.sort(key=lambda d: (order[d[2]], d[1], d[0]))
    classes = {
        name: sum(1 for d in dots if params.CLASSES[d[2]] == name)
        for name in params.MAP_DRAW_ORDER
    }
    return dots, {
        "classes": classes,
        "reclassed": dict(sorted(reclassed.items())),
    }


def make(paths, heads, details, ends):
    """The maps' outlines and dots.

    Args:
        paths: The inputs by name: "site-boundary", "usgs-sgmc-shifted",
            "aquifer-precambrian" and the DEM_TILES' names.
        heads: The 3D page's well heads.
        details: A function from (cell, uid) to the well's report.
        ends: The slice's ends, [[lon, lat], [lon, lat]] (north-west first).

    Returns:
        (maps, figures, counts): the outlines (SVG path data) and dots in the
        maps' units, with the frame's size; the figures the page shows; and
        the class counts.
    """
    frame = Frame()
    (district_f,) = read_geojson(paths["site-boundary"])
    district = geometry(district_f)
    geo = ogr.Open(paths["usgs-sgmc-shifted"])
    hickory = in_frame(
        frame,
        [
            f.GetGeometryRef().Clone()
            for f in geo.GetLayerByName(params.GEOLOGY_LAYER)
        ],
    )
    geo = None
    precambrian = in_frame(
        frame, [geometry(f) for f in read_geojson(paths["aquifer-precambrian"])]
    )
    high = high_ground(frame, [paths[t] for t in params.DEM_TILES])
    together = hickory.Intersection(high) if hickory and high else None
    dots, counts = map_wells(frame, heads, details)
    tol = params.SIMPLIFY
    (ax, ay), (bx, by) = (frame.xy(*p) for p in ends)
    maps = {
        "w": frame.width,
        "h": frame.height,
        "district": frame.path(district, tol["district"]),
        "hickory": frame.path(hickory, tol["hickory"]),
        "precambrian": frame.path(precambrian, tol["precambrian"]),
        "high": frame.path(high, tol["high"]),
        "together": frame.path(together, tol["together"]),
        "wells": dots,
        "line": [[round(ax, 1), round(ay, 1)], [round(bx, 1), round(by, 1)]],
        "scale": frame.scale_bar(),
    }
    return maps, {"wells_on_map": len(dots)}, counts
