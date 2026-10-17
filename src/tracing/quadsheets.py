"""Open scanned USGS topographic quadrangles (GeoTIFF, bare or inside a .zip, read in place) and map NAD83 lon/lat to
each sheet's pixels, the way the sheet itself is drawn.

- NAD27 sheets (all historical topoView/HTMC scans) are reached through NADCON 5.0 (NAD83(1986) -> NAD27, the CONUS
  grid by default), then the sheet's own projection (polyconic for most), straight from its GeoTIFF CRS.
- NAD83/WGS84 sheets (US Topo) are reached with an ordinary transform.
- Each sheet knows its neatline cell (7.5' = 0.125 deg for 1:24,000; 15' for 1:62,500; 30' for 1:125,000), so a point
  is read from the sheet whose map face holds it, never from a neighbour's collar, and points within a few metres of
  a neatline can be flagged (neatline ink is not a feature).
Requires GDAL/OSR Python bindings with PROJ able to find the NADCON grid (bundled with proj-data, or PROJ_NETWORK=ON)."""
import glob, math, os, re
import numpy as np
from osgeo import gdal, osr
gdal.UseExceptions()

NADCON = "us_noaa_nadcon5_nad27_nad83_1986_conus.tif"
CELL_BY_SCALE = {"24000": 0.125, "25000": 0.125, "62500": 0.25, "125000": 0.5}

def _nad83():
    s = osr.SpatialReference(); s.ImportFromEPSG(4269); s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER); return s

def _open(path):
    if path.lower().endswith(".zip"):
        inner = [n for n in gdal.ReadDir(f"/vsizip/{path}") or [] if n.lower().endswith((".tif", ".tiff"))]
        if not inner: raise ValueError(f"no GeoTIFF inside {path}")
        return gdal.Open(f"/vsizip/{path}/{inner[0]}"), inner[0]
    return gdal.Open(path), os.path.basename(path)

class Sheet:
    def __init__(self, path, cell_deg=None, nadcon=NADCON):
        self.path = path
        self.ds, fname = _open(path)
        self.gt = self.ds.GetGeoTransform()
        m = re.match(r"[A-Z]{2}_(.+?)_\d+_(\d{4})_(\d+)_", fname)          # topoView: TX_Grit_118976_1967_24000_geo.tif
        self.name = m.group(1).replace("_", " ") if m else os.path.splitext(fname)[0]
        self.year = m.group(2) if m else None
        self.cell_deg = cell_deg or (CELL_BY_SCALE.get(m.group(3)) if m else None) or 0.125
        srs = osr.SpatialReference(wkt=self.ds.GetProjection()); srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        self.srs = srs
        geo = srs.CloneGeogCS(); geo.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        datum = (srs.GetAttrValue("DATUM") or "").upper()
        self.nad27 = "1927" in datum or "NAD27" in datum or "NAD_1927" in datum
        if self.nad27:
            proj4 = " ".join(t for t in srs.ExportToProj4().split() if not t.startswith(("+datum", "+towgs84", "+no_defs", "+ellps", "+nadgrids")))
            pipe = ("+proj=pipeline +step +proj=axisswap +order=2,1 +step +proj=unitconvert +xy_in=deg +xy_out=rad "
                    f"+step +inv +proj=hgridshift +grids={nadcon} +step {proj4} +ellps=clrk66")
            o = osr.CoordinateTransformationOptions(); o.SetOperation(pipe)
            self.ct = osr.CoordinateTransformation(_nad83(), srs, o)
        else:
            self.ct = osr.CoordinateTransformation(_nad83(), srs)
        self.to_geo = osr.CoordinateTransformation(srs, geo)       # sheet projection -> the sheet's own geographic (NAD27)
        g = self.gt; cx, cy = g[0] + g[1] * self.ds.RasterXSize / 2, g[3] + g[5] * self.ds.RasterYSize / 2
        lo, la = self.to_geo.TransformPoint(cx, cy)[:2]
        d = self.cell_deg
        self.cell = (math.floor(lo / d) * d, math.floor(la / d) * d)

    def pixels(self, lons, lats, edge_m=0.0):
        """float pixel col, row for NAD83 points, plus inside-the-neatline and within-edge_m-of-the-neatline flags"""
        pts = np.column_stack([lons, lats]).tolist()
        xy = np.array(self.ct.TransformPoints(pts))[:, :2]
        ll = np.array(self.to_geo.TransformPoints(xy.tolist()))[:, :2]
        x0, y0 = self.cell; d = self.cell_deg
        inside = (ll[:, 0] >= x0) & (ll[:, 0] < x0 + d) & (ll[:, 1] >= y0) & (ll[:, 1] < y0 + d)
        dlon = edge_m / (111320 * math.cos(math.radians(y0 + d / 2))); dlat = edge_m / 110574
        near = inside & ((ll[:, 0] - x0 < dlon) | (x0 + d - ll[:, 0] < dlon) | (ll[:, 1] - y0 < dlat) | (y0 + d - ll[:, 1] < dlat))
        g = self.gt
        return (xy[:, 0] - g[0]) / g[1], (xy[:, 1] - g[3]) / g[5], inside, near

    def pixel(self, lon, lat):
        c, r, inside, _ = self.pixels([lon], [lat]); return float(c[0]), float(r[0]), bool(inside[0])

    def read(self, c0, r0, c1, r1):
        """RGB window (3, rows, cols), clipped to the raster"""
        c0, r0 = max(0, int(c0)), max(0, int(r0)); c1 = min(self.ds.RasterXSize, int(c1)); r1 = min(self.ds.RasterYSize, int(r1))
        return self.ds.ReadAsArray(c0, r0, c1 - c0, r1 - r0)[:3], c0, r0

def open_sheets(patterns, cell_deg=None, nadcon=NADCON):
    """Sheets from paths or glob patterns (GeoTIFFs or zips holding one)"""
    paths = []
    for p in ([patterns] if isinstance(patterns, str) else patterns):
        paths += sorted(glob.glob(p)) or [p]
    return [Sheet(p, cell_deg, nadcon) for p in paths]

def sheet_of(sheets, lon, lat):
    for s in sheets:
        if s.pixel(lon, lat)[2]: return s
    return None
