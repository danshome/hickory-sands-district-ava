"""TWDB's Llano Uplift groundwater model grid, and its Hickory outline.

The model (GAM v1.01) is 478 rows by 556 columns of quarter-mile cells,
rotated 45 degrees, in NAD83 / TWDB GM Albers (US survey feet). ModelGrid
reads layers 7 (the Hickory Aquifer) and 8 (the Precambrian) from the GAM
Properties GeoPackage and fits the grid's affine transform to the cells'
centres, so a GDAL raster with that transform has one pixel per model cell,
and rasterizing a polygon onto it marks exactly the cells whose centre lies
inside the polygon. hickory() reads TWDB's 2017 official Hickory outline,
moved by the geology's shift (params.SHIFT_LON, SHIFT_LAT). The model's
cells are not moved.
"""

import math

import numpy as np
from osgeo import gdal
from osgeo import ogr
from osgeo import osr

from . import params

gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()

GAM_TABLE = "lnup_v101_flow_props"  # the GeoPackage's one table
FIT_SAMPLE = 37  # every 37th cell centre (and the first 4,000) fits the grid
MAX_FIT_RESIDUAL_FT = 1.0
MAX_CELL_ERROR_FT = 0.5


def nad83():
    """NAD83 longitude and latitude (EPSG:4269), longitude first."""
    sr = osr.SpatialReference()
    sr.ImportFromEPSG(4269)
    sr.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return sr


class ModelGrid:
    """Layer 7 and 8 values on the model's row and column grid.

    Attributes:
        top7: Layer 7's top (ft above sea level), NaN where inactive.
        bot7: Layer 7's bottom, NaN where inactive.
        ib7: Layer 7's ibound (0 where inactive, 71 at the surface).
        ib8: Layer 8's ibound (81 at the surface, 82 buried).
        ground: The top of the highest active layer (the model's ground).
        srs: The model's spatial reference, longitude-first order.
        geotransform: A GDAL geotransform with one pixel per cell.
        fit_residual_ft: The affine fit's largest residual.
    """

    def __init__(self, gpkg):
        """Reads the grid from the GAM Properties GeoPackage.

        Args:
            gpkg: lnup_v101_flow_props.gpkg, extracted from the archive.

        Raises:
            SystemExit: The grid's fit is off, or its cells are not a
                quarter mile.
        """
        rows, cols = params.ROWS, params.COLS
        ds = ogr.Open(gpkg)
        layer = ds.GetLayer(0)
        self.srs = layer.GetSpatialRef().Clone()
        self.srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        self.top7 = np.full((rows, cols), np.nan)
        self.bot7 = np.full((rows, cols), np.nan)
        self.ib7 = np.zeros((rows, cols), dtype=np.int16)
        self.ib8 = np.zeros((rows, cols), dtype=np.int16)
        fit_r, fit_c, fit_x, fit_y = [], [], [], []
        layer.SetAttributeFilter(
            f"lay IN ({params.HICKORY_LAYER}, {params.PRECAMBRIAN_LAYER})"
        )
        for f in layer:
            r = f.GetField("row") - 1
            c = f.GetField("col") - 1
            if f.GetField("lay") == params.HICKORY_LAYER:
                self.top7[r, c] = f.GetField("top")
                self.bot7[r, c] = f.GetField("botm")
                self.ib7[r, c] = f.GetField("ibound")
                if len(fit_r) < 4000 or len(fit_r) % FIT_SAMPLE == 0:
                    p = f.GetGeometryRef().Centroid()
                    fit_r.append(r)
                    fit_c.append(c)
                    fit_x.append(p.GetX())
                    fit_y.append(p.GetY())
            else:
                self.ib8[r, c] = f.GetField("ibound")
        layer.SetAttributeFilter(None)
        self.ground = np.full((rows, cols), np.nan)
        if layer.GetName() != GAM_TABLE:
            raise SystemExit(f"{gpkg}: no table {GAM_TABLE}")
        result = ds.ExecuteSQL(
            "SELECT row, col, MAX(top) AS ground FROM lnup_v101_flow_props "
            "GROUP BY row, col"
        )
        for f in result:
            self.ground[f.GetField("row") - 1, f.GetField("col") - 1] = (
                f.GetField("ground")
            )
        ds.ReleaseResultSet(result)
        a = np.column_stack([np.ones(len(fit_r)), fit_c, fit_r])
        cx, *_ = np.linalg.lstsq(a, np.array(fit_x), rcond=None)
        cy, *_ = np.linalg.lstsq(a, np.array(fit_y), rcond=None)
        resid = np.hypot(a @ cx - fit_x, a @ cy - fit_y).max()
        if resid > MAX_FIT_RESIDUAL_FT:
            raise SystemExit(f"grid fit residual {resid:.2f} ft")
        for v in (np.hypot(cx[1], cy[1]), np.hypot(cx[2], cy[2])):
            if abs(v - params.CELL_FT) > MAX_CELL_ERROR_FT:
                raise SystemExit(f"cell size {v:.3f} ft, not a quarter mile")
        self.coef_x = cx
        self.coef_y = cy
        # Pixel (i, j) spans rows i - 0.5 .. i + 0.5 and columns j - 0.5 ..
        # j + 0.5 of the cell centres.
        self.geotransform = (
            cx[0] - 0.5 * cx[1] - 0.5 * cx[2],
            cx[1],
            cx[2],
            cy[0] - 0.5 * cy[1] - 0.5 * cy[2],
            cy[1],
            cy[2],
        )
        self.fit_residual_ft = float(resid)

    def xy(self, r, c):
        """Model coordinates (ft) of grid positions (0-based row, col)."""
        return (
            self.coef_x[0] + c * self.coef_x[1] + r * self.coef_x[2],
            self.coef_y[0] + c * self.coef_y[1] + r * self.coef_y[2],
        )

    def lonlat(self, r, c):
        """NAD83 longitude and latitude of grid positions.

        Args:
            r: Rows (0-based, fractional), an array.
            c: Columns, the same shape.

        Returns:
            Two arrays, longitude and latitude.
        """
        x, y = self.xy(np.asarray(r, float), np.asarray(c, float))
        to_ll = osr.CoordinateTransformation(self.srs, nad83())
        pts = np.array(
            to_ll.TransformPoints(np.column_stack([x.ravel(), y.ravel()]))
        )
        return pts[:, 0].reshape(x.shape), pts[:, 1].reshape(x.shape)

    def _raster(self):
        """An empty in-memory raster with one byte per model cell."""
        ras = gdal.GetDriverByName("MEM").Create(
            "", params.COLS, params.ROWS, 1, gdal.GDT_Byte
        )
        ras.SetGeoTransform(self.geotransform)
        ras.SetProjection(self.srs.ExportToWkt())
        return ras

    def mask_of(self, geom):
        """The cells whose centre lies inside a polygon (in the model CRS)."""
        ras = self._raster()
        mem = ogr.GetDriverByName("MEM").CreateDataSource("m")
        layer = mem.CreateLayer("p", self.srs, ogr.wkbMultiPolygon)
        feat = ogr.Feature(layer.GetLayerDefn())
        feat.SetGeometry(geom)
        layer.CreateFeature(feat)
        gdal.RasterizeLayer(ras, [1], layer, burn_values=[1])
        return ras.ReadAsArray().astype(bool)

    def polygons_of(self, mask):
        """The union of the cells of a mask, as polygons in the model CRS."""
        ras = self._raster()
        band = ras.GetRasterBand(1)
        band.WriteArray(mask.astype(np.uint8))
        mem = ogr.GetDriverByName("MEM").CreateDataSource("m")
        layer = mem.CreateLayer("p", self.srs, ogr.wkbPolygon)
        layer.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))
        gdal.Polygonize(band, band, layer, 0)
        out = ogr.Geometry(ogr.wkbMultiPolygon)
        for f in layer:
            if f.GetField("v") == 1:
                out.AddGeometry(f.GetGeometryRef().Clone())
        out.AssignSpatialReference(self.srs)
        return out


def terms(u, v, degree):
    """A bivariate polynomial's terms, in the order the page uses.

    For each total power from 0 to degree, u's power falls as v's rises:
    1, u, v, u^2, uv, v^2, u^3, u^2 v, ...

    Args:
        u: An array.
        v: An array of the same shape.
        degree: The polynomial's degree.

    Returns:
        A matrix with a column per term.
    """
    return np.column_stack(
        [
            u ** (total - j) * v**j
            for total in range(degree + 1)
            for j in range(total + 1)
        ]
    )


def corner_polynomial(grid):
    """The polynomial from model row and column to NAD83 longitude, latitude.

    The page builds the aquifer's block corners with it instead of reading
    a lattice of corners. Fitted on every fourth grid line, from the grid's
    outer edge, and checked on an offset, denser set.

    Args:
        grid: A ModelGrid.

    Returns:
        A JSON-ready dict: the centres and scales of row and column, the
        coefficients for longitude and for latitude, and the largest error
        found, in metres.

    Raises:
        SystemExit: The fit is worse than params.CORNER_MAX_ERROR_M.
    """
    rows, cols, degree = params.ROWS, params.COLS, params.CORNER_DEGREE
    rc, rs, cc, cs = rows / 2, rows / 2, cols / 2, cols / 2
    rr, cl = np.meshgrid(
        np.arange(-0.5, rows + 0.5, 4.0),
        np.arange(-0.5, cols + 0.5, 4.0),
        indexing="ij",
    )
    lon, lat = grid.lonlat(rr.ravel(), cl.ravel())
    t = terms((cl.ravel() - cc) / cs, (rr.ravel() - rc) / rs, degree)
    clon, *_ = np.linalg.lstsq(t, lon, rcond=None)
    clat, *_ = np.linalg.lstsq(t, lat, rcond=None)
    rr2, cl2 = np.meshgrid(
        np.arange(-0.3, rows, 1.7), np.arange(-0.1, cols, 1.9), indexing="ij"
    )
    lon2, lat2 = grid.lonlat(rr2.ravel(), cl2.ravel())
    t2 = terms((cl2.ravel() - cc) / cs, (rr2.ravel() - rc) / rs, degree)
    m_lat = 110_900.0  # metres per degree of latitude, near enough here
    m_lon = m_lat * np.cos(np.radians(lat2))
    err = np.hypot((t2 @ clon - lon2) * m_lon, (t2 @ clat - lat2) * m_lat)
    worst = float(err.max())
    if worst > params.CORNER_MAX_ERROR_M:
        raise SystemExit(f"corner polynomial off by {worst:.2f} m")
    return {
        "degree": degree,
        "terms": "u = (col - col_c) / col_s, v = (row - row_c) / row_s; "
        "for each total power n from 0 up, u^(n-j) v^j for j = 0..n",
        "row_c": rc,
        "row_s": rs,
        "col_c": cc,
        "col_s": cs,
        "lon": [float(x) for x in clon],
        "lat": [float(x) for x in clat],
        "max_error_m": round(worst, 3),
    }


def lookup_polynomial(grid):
    """The polynomial from NAD83 longitude, latitude to model row, column.

    "My location" finds its model cell with it, so the page needs no
    projection library.

    Args:
        grid: A ModelGrid.

    Returns:
        A JSON-ready dict: the centre longitude and latitude, the
        coefficients for row and for column (0-based, fractional) and the
        largest error found, in cells.

    Raises:
        SystemExit: The fit is worse than params.LOOKUP_MAX_ERROR_CELLS.
    """
    rows, cols, degree = params.ROWS, params.COLS, params.LOOKUP_DEGREE
    rr, cl = np.meshgrid(
        np.arange(-1, rows + 1, 4.0),
        np.arange(-1, cols + 1, 4.0),
        indexing="ij",
    )
    lon, lat = grid.lonlat(rr.ravel(), cl.ravel())
    lon_c, lat_c = float(lon.mean()), float(lat.mean())
    t = terms(lon - lon_c, lat - lat_c, degree)
    crow, *_ = np.linalg.lstsq(t, rr.ravel(), rcond=None)
    ccol, *_ = np.linalg.lstsq(t, cl.ravel(), rcond=None)
    rr2, cl2 = np.meshgrid(
        np.arange(0.3, rows, 1.7), np.arange(0.7, cols, 1.9), indexing="ij"
    )
    lon2, lat2 = grid.lonlat(rr2.ravel(), cl2.ravel())
    t2 = terms(lon2 - lon_c, lat2 - lat_c, degree)
    worst = float(
        np.hypot(t2 @ crow - rr2.ravel(), t2 @ ccol - cl2.ravel()).max()
    )
    if worst > params.LOOKUP_MAX_ERROR_CELLS:
        raise SystemExit(f"lookup polynomial off by {worst:.4f} cells")
    return {
        "degree": degree,
        "terms": "u = lon - lon_c, v = lat - lat_c; for each total power n "
        "from 0 up, u^(n-j) v^j for j = 0..n",
        "lon_c": lon_c,
        "lat_c": lat_c,
        "row": [float(x) for x in crow],
        "col": [float(x) for x in ccol],
        "max_error_cells": round(worst, 5),
    }


def _shift(geom):
    """Moves every vertex of a longitude-latitude geometry by the shift."""
    if geom.GetGeometryCount():
        for i in range(geom.GetGeometryCount()):
            _shift(geom.GetGeometryRef(i))
        return
    for i in range(geom.GetPointCount()):
        geom.SetPoint_2D(
            i, geom.GetX(i) + params.SHIFT_LON, geom.GetY(i) + params.SHIFT_LAT
        )


def hickory(zip_path, which="all", srs=None):
    """TWDB's 2017 official Hickory outline, shifted onto the geology.

    TWDB's Minor Aquifers shapefile (December 2017) carries the same
    misregistration as the USGS geologic map it was drawn from, so it is
    moved by the geology's own shift, in NAD83 degrees, before anything else.

    Args:
        zip_path: TWDB's minor_aquifers.zip.
        which: "all" (outcrop and subsurface) or "outcrop".
        srs: The spatial reference wanted; NAD83 longitude-latitude if None.

    Returns:
        The union of the Hickory polygons.
    """
    ds = ogr.Open(f"/vsizip/{zip_path}/Minor_Aquifers.shp")
    layer = ds.GetLayer(0)
    src = layer.GetSpatialRef().Clone()
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ll = nad83()
    to_ll = osr.CoordinateTransformation(src, ll)
    codes = {"all": (1, 2), "outcrop": (1,)}[which]
    layer.SetAttributeFilter("AQU_NAME = 'HICKORY'")
    parts = ogr.Geometry(ogr.wkbMultiPolygon)
    for f in layer:
        if f.GetField("AQUIFER") not in codes:
            continue
        g = f.GetGeometryRef().Clone()
        g.Transform(to_ll)
        _shift(g)
        for part in ogr.ForceToMultiPolygon(g):
            parts.AddGeometry(part)
    union = parts.UnionCascaded()
    union.AssignSpatialReference(ll)
    if srs is not None:
        out = srs.Clone()
        out.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        union.Transform(osr.CoordinateTransformation(ll, out))
        union.AssignSpatialReference(out)
    return union


def shift_metres():
    """The geology shift in metres, west and north, at the model's middle.

    Returns:
        (west, north): the shift's length east-west and north-south at
        30.75 N, 99.23 W (Mason), measured in UTM zone 14N.
    """
    utm = osr.SpatialReference()
    utm.ImportFromEPSG(26914)
    utm.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(nad83(), utm)
    lon, lat = -99.23, 30.75
    x0, y0, _ = ct.TransformPoint(lon, lat)
    x1, y1, _ = ct.TransformPoint(lon + params.SHIFT_LON, lat)
    x2, y2, _ = ct.TransformPoint(lon, lat + params.SHIFT_LAT)
    return math.hypot(x1 - x0, y1 - y0), math.hypot(x2 - x0, y2 - y0)
