"""Makes the survey map under the boundary drawing on Home and The boundary.

docs/assets/survey-map.webp shows the ground the drawing's viewBox covers
(src/site/survey_frame.py) on the USGS 1:24,000 historical quadrangles: the 13
the description names (resources/quads/quads-manifest.csv, fetched by the
build) and the quads around them that fill the rest of the frame
(resources/quads/basemap-manifest.csv, fetched here into
resources/quads/basemap/ when needed). Each quad is cropped to its 7.5-minute
neatline and carried from its NAD27 polyconic projection to NAD83 UTM zone 14N
through the NADCON 5.0 CONUS grid, averaged onto a grid four times finer than
the image, then reduced to the image's size.

docs/data/survey-map.json records the frame and the quads. The image is made
again only when that record would change, so builds on machines whose GDAL
rounds differently do not rewrite it. With --check nothing is written, and the
exit status is 3 when the record is stale.

Usage:
    make_survey_map.py --pages docs [--check]
"""

import argparse
import csv
import json
import os
import sys

import numpy as np
from osgeo import gdal
from osgeo import osr
from PIL import Image

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quads"
    ),
)
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tracing"
    ),
)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # src/site
import fetch_quads
from quadsheets import NADCON
from quadsheets import Sheet
import survey_frame

gdal.UseExceptions()
osr.UseExceptions()

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # the repository (src/site/..)
QUADS = os.path.join(ROOT, "resources", "quads")
# Each manifest, and the folder its GeoTIFF zips are in.
MANIFESTS = (
    ("quads-manifest.csv", os.path.join(QUADS, "geotiff")),
    ("basemap-manifest.csv", os.path.join(QUADS, "basemap")),
)
PAGES = ("index.html", "boundary.html")
UTM14 = 26914  # NAD83 / UTM zone 14N
OVERSAMPLE = 4  # the warp's grid, this many times finer than the image
EDGE_POINTS = 32  # points along each side of a neatline cutline
QUALITY = 72  # WebP quality; the pages show the image faint
STALE = 3  # --check's exit status when the image or its record is stale


def manifest_rows():
    """Every quad the image is made from, with the folder of its zip.

    Returns:
        A list of (row, folder): the manifests' rows, in manifest order.
    """
    rows = []
    for name, folder in MANIFESTS:
        with open(os.path.join(QUADS, name), newline="", encoding="utf-8") as f:
            rows += [(row, folder) for row in csv.DictReader(f)]
    return rows


def utm_points(geojson_text):
    """The boundary's points in UTM zone 14N.

    Args:
        geojson_text: docs/data/boundary.geojson, NAD83 longitude/latitude.

    Returns:
        A list of (easting, northing) in metres, every ring's points.
    """
    nad83 = osr.SpatialReference()
    nad83.ImportFromEPSG(4269)
    nad83.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    utm = osr.SpatialReference()
    utm.ImportFromEPSG(UTM14)
    utm.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    to_utm = osr.CoordinateTransformation(nad83, utm)
    points = []
    for feature in json.loads(geojson_text)["features"]:
        geometry = feature["geometry"]
        polygons = (
            [geometry["coordinates"]]
            if geometry["type"] == "Polygon"
            else geometry["coordinates"]
        )
        for ring in (r for polygon in polygons for r in polygon):
            points += [to_utm.TransformPoint(x, y)[:2] for x, y in ring]
    return points


def the_drawing(docs):
    """Reads the boundary drawing, which Home and The boundary share.

    Args:
        docs: The website's folder.

    Returns:
        survey_frame.drawing()'s (size, href, points).

    Raises:
        ValueError: The two pages draw it differently.
    """
    drawings = []
    for page in PAGES:
        with open(os.path.join(docs, page), encoding="utf-8") as f:
            drawings.append(survey_frame.drawing(f.read()))
    if any(d != drawings[0] for d in drawings[1:]):
        raise ValueError(f"{' and '.join(PAGES)} draw the boundary differently")
    return drawings[0]


def operation(sheet):
    """The PROJ pipeline from a NAD27 sheet's projection to NAD83 UTM 14N.

    Args:
        sheet: A quadsheets.Sheet on NAD27.

    Returns:
        The pipeline: the sheet's projection inverted (Clarke 1866), NAD27 to
        NAD83 by the NADCON 5.0 CONUS grid, then UTM zone 14N (GRS 1980).
    """
    proj4 = " ".join(
        t
        for t in sheet.srs.ExportToProj4().split()
        if not t.startswith(
            ("+datum", "+towgs84", "+no_defs", "+ellps", "+nadgrids")
        )
    )
    return (
        f"+proj=pipeline +step +inv {proj4} +ellps=clrk66 "
        f"+step +proj=hgridshift +grids={NADCON} "
        "+step +proj=utm +zone=14 +ellps=GRS80"
    )


def neatline(sheet):
    """A sheet's 7.5-minute neatline as WKT in the sheet's own projection.

    Args:
        sheet: A quadsheets.Sheet.

    Returns:
        A polygon, its sides densified so the projection bends them true.
    """
    w, s = sheet.cell
    d = sheet.cell_deg
    steps = [i / EDGE_POINTS for i in range(EDGE_POINTS)]
    corners = (
        [(w + d * t, s) for t in steps]
        + [(w + d, s + d * t) for t in steps]
        + [(w + d - d * t, s + d) for t in steps]
        + [(w, s + d - d * t) for t in steps]
    )
    geo = sheet.srs.CloneGeogCS()
    geo.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    to_sheet = osr.CoordinateTransformation(geo, sheet.srs)
    ring = [to_sheet.TransformPoint(x, y)[:2] for x, y in corners]
    ring.append(ring[0])
    return "POLYGON ((" + ", ".join(f"{x!r} {y!r}" for x, y in ring) + "))"


def render(frame, pixels, zips):
    """Mosaics the quads onto the frame.

    Args:
        frame: (west, south, east, north) in metres, UTM zone 14N.
        pixels: The image's (width, height).
        zips: The quads' GeoTIFF zips.

    Returns:
        A PIL RGB image of the frame.

    Raises:
        ValueError: A quad is not on NAD27, or part of the frame is on no quad.
    """
    west, south, east, north = frame
    w, h = pixels[0] * OVERSAMPLE, pixels[1] * OVERSAMPLE
    grid = gdal.GetDriverByName("MEM").Create("", w, h, 4, gdal.GDT_Byte)
    grid.SetGeoTransform(
        (west, (east - west) / w, 0, north, 0, -(north - south) / h)
    )
    utm = osr.SpatialReference()
    utm.ImportFromEPSG(UTM14)
    grid.SetProjection(utm.ExportToWkt())
    grid.GetRasterBand(4).SetColorInterpretation(gdal.GCI_AlphaBand)
    for path in zips:
        sheet = Sheet(path)
        if not sheet.nad27:
            raise ValueError(f"{path}: not on NAD27")
        gdal.Warp(
            grid,
            sheet.ds,
            options=gdal.WarpOptions(
                cutlineWKT=neatline(sheet),
                cutlineSRS=sheet.srs.ExportToWkt(),
                coordinateOperation=operation(sheet),
                resampleAlg="average",
                dstAlpha=True,
            ),
        )
        print(f"warped {sheet.name} {sheet.year}")
    rgba = np.dstack(
        [grid.GetRasterBand(b).ReadAsArray() for b in (1, 2, 3, 4)]
    )
    bare = np.argwhere(rgba[:, :, 3] == 0)
    if len(bare):
        row, col = bare[0]
        raise ValueError(
            f"{len(bare)} of the frame's cells are on no quad, the first at "
            f"E {west + (col + 0.5) * (east - west) / w:.0f} "
            f"N {north - (row + 0.5) * (north - south) / h:.0f} (UTM 14N): "
            "add the quad there to resources/quads/basemap-manifest.csv"
        )
    image = Image.fromarray(np.ascontiguousarray(rgba[:, :, :3]), "RGB")
    return image.resize(tuple(pixels), Image.Resampling.BOX)


def image_pixels(path):
    """An image's (width, height), or None when there is no image."""
    if not os.path.exists(path):
        return None
    with Image.open(path) as image:
        return list(image.size)


def main():
    """Writes or checks the survey image and its record."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--pages", required=True, help="the website's folder")
    parser.add_argument(
        "--check", action="store_true", help="exit 3 if stale; write nothing"
    )
    args = parser.parse_args()
    docs = args.pages
    size, href, points = the_drawing(docs)
    with open(
        os.path.join(docs, "data", "boundary.geojson"), encoding="utf-8"
    ) as f:
        ground = utm_points(f.read())
    frame = survey_frame.fit(points, ground, size)
    rows = manifest_rows()
    new = survey_frame.record(frame, size, href, [row for row, _ in rows])
    record_path = os.path.join(docs, "data", "survey-map.json")
    image_path = os.path.join(docs, href)
    old = None
    if os.path.exists(record_path):
        with open(record_path, encoding="utf-8") as f:
            old = json.load(f)
    stale = survey_frame.differences(old, new)
    if image_pixels(image_path) != new["pixels"]:
        stale.append(f"{href} is missing or not {new['pixels']} pixels")
    if not stale:
        print(f"survey map up to date: {href}, {len(rows)} quads")
        return 0
    if args.check:
        print(
            f"STALE survey map ({'; '.join(stale)}): run ./build.sh site-data",
            file=sys.stderr,
        )
        return STALE
    zips = []
    for row, folder in rows:
        os.makedirs(folder, exist_ok=True)
        if not fetch_quads.fetch_geotiff(row, folder):
            raise SystemExit(f"cannot fetch {row['geotiff']}")
        zips.append(os.path.join(folder, row["geotiff"] + ".zip"))
    image = render(frame, new["pixels"], zips)
    image.save(image_path, "WEBP", quality=QUALITY, method=6)
    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(new, f, indent=1)
        f.write("\n")
    print(f"survey map: {href} ({', '.join(stale)}), {len(rows)} quads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
