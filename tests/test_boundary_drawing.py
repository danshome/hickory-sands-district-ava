"""The boundary drawing on Home and The boundary, made by the build (#126).

src/site/boundary_drawing.py draws docs/data/boundary.geojson in UTM zone 14N,
simplified by Douglas-Peucker at 12 m and fitted to the drawing's viewBox;
src/site/make_site_data.py writes the paths marked data-figure-path into the
pages. These check that the committed pages carry exactly the paths the
committed data gives; and, on made-up shapes, the projection (against PROJ's
own values), the simplification's tolerance, the fit and the paths' form.
Standard library only, so the lint workflow runs these; the one marked build
compares the projection with GDAL's for every point of the boundary.
"""

import math
import os
import re

import pytest

from src.site import boundary_drawing as bd
from src.site import make_site_data as msd
from src.site import survey_frame as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
PAGES = ("index.html", "boundary.html")  # the pages that draw the boundary


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def data():
    return read(DOCS, "data", "boundary.geojson")


@pytest.mark.parametrize("page", PAGES)
def test_the_page_draws_the_path_the_data_gives(page, data):
    text = read(DOCS, page)
    size, _, _ = sf.drawing(text)
    want = bd.paths(data, size)
    found = [
        (m["name"], re.search(r'\sd="([^"]*)"', m["attrs"])[1])
        for m in msd.FIGURE_PATH.finditer(text)
    ]
    assert sorted(name for name, _ in found) == [
        "boundary",
        "boundary",
        "scale_bar",
    ]
    for name, d in found:
        assert d == want[name], f"{page}: {name} is stale: ./build.sh site-data"
    assert msd.fill_paths(text, data, page) == text


@pytest.mark.parametrize("page", PAGES)
def test_the_drawn_line_is_the_marked_one(page):
    # survey_frame reads the line by its class; it must be the marked path.
    text = read(DOCS, page)
    line = re.search(r'<path class="boundary-line"[^>]*>', text)[0]
    assert 'data-figure-path="boundary"' in line
    fill = re.search(r'<path class="boundary-fill"[^>]*>', text)[0]
    assert 'data-figure-path="boundary"' in fill


# PROJ's own values (EPSG:4269 to EPSG:26914), to 0.1 mm: on the zone's
# central meridian, at the boundary's first point, and far out to each side.
PROJ = [
    ((-99.0, 30.0), (500000.0000, 3318785.3525)),
    ((-99.410725, 30.764679), (460693.5848, 3403594.9963)),
    ((-102.0, 34.0), (222908.7045, 3766214.7160)),
    ((-96.0, 26.0), (800318.0748, 2879132.5335)),
]


@pytest.mark.parametrize(("lonlat", "utm"), PROJ)
def test_utm14_agrees_with_proj(lonlat, utm):
    east, north = bd.utm14(*lonlat)
    assert math.dist((east, north), utm) < 0.0002


@pytest.mark.build
def test_utm14_agrees_with_gdal_on_every_point(data):
    osr = pytest.importorskip("osgeo.osr")
    osr.UseExceptions()
    nad83, utm = osr.SpatialReference(), osr.SpatialReference()
    nad83.ImportFromEPSG(4269)
    utm.ImportFromEPSG(26914)
    for srs in (nad83, utm):
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    to_utm = osr.CoordinateTransformation(nad83, utm)
    (ring,) = bd.rings_m(data)
    lonlat = re.findall(r"\[(-?[\d.]+),(-?[\d.]+)\]", data)
    assert len(lonlat) == len(ring)
    for (lon, lat), mine in zip(lonlat, ring, strict=True):
        theirs = to_utm.TransformPoint(float(lon), float(lat))[:2]
        assert math.dist(mine, theirs) < 0.001


def test_simplify_keeps_what_lies_beyond_the_tolerance():
    # 12.1 m off the chord: kept; the others then lie about 8 m from the
    # simplified line, within 12 m: dropped.
    line = [(0, 0), (500, 11.9), (1000, 0), (1500, 12.1), (2000, 0)]
    assert bd.simplify(line, 12.0) == [(0, 0), (1500, 12.1), (2000, 0)]
    assert bd.simplify(line, 13.0) == [(0, 0), (2000, 0)]
    assert bd.simplify(line, 7.0) == line


def test_simplify_keeps_a_ring_s_first_point():
    ring = [(0, 0), (1000, 0), (1000, 1000), (0, 1000), (0, 500.5), (0, 0)]
    assert bd.simplify(ring, 12.0) == [
        (0, 0),
        (1000, 0),
        (1000, 1000),
        (0, 1000),
        (0, 0),
    ]


def test_fit_centres_the_box_with_its_margin_on_the_tighter_side():
    wide = [[(0, 0), (1000, 0), (1000, 500), (0, 500), (0, 0)]]
    scale, centre = bd.fit(wide, (1200, 1056))
    assert scale == pytest.approx(1200 / ((1 + 2 * bd.MARGIN) * 1000))
    assert centre == (500, 250)
    tall = [[(0, 0), (100, 0), (100, 1000), (0, 1000), (0, 0)]]
    scale, _ = bd.fit(tall, (1200, 1056))
    assert scale == pytest.approx(1056 / ((1 + 2 * bd.MARGIN) * 1000))


# A made-up district a tenth of a degree each way (taller than wide on the
# ground), with a hole.
SQUARE = (
    '{"type":"FeatureCollection","features":[{"type":"Feature",'
    '"properties":{},"geometry":{"type":"Polygon","coordinates":['
    "[[-99.1,30.6],[-99.0,30.6],[-99.0,30.7],[-99.1,30.7],[-99.1,30.6]],"
    "[[-99.06,30.64],[-99.05,30.64],[-99.05,30.65],[-99.06,30.64]]]}}]}"
)
XY = re.compile(r"(\d+\.\d\d),(\d+\.\d\d)")


def test_paths_are_plain_closed_rings_centred_with_their_margin():
    d = bd.paths(SQUARE, (1200, 1056))["boundary"]
    assert sf.PLAIN_PATH.fullmatch(d)
    rings = d.split(" Z")[:-1]
    assert len(rings) == 2  # the polygon's hole is drawn too
    for ring in rings:
        points = XY.findall(ring)
        assert ring.strip().startswith("M")
        assert points[0] == points[-1]
    xs = [float(x) for x, _ in XY.findall(d)]
    ys = [float(y) for _, y in XY.findall(d)]
    margin = 1056 * bd.MARGIN / (1 + 2 * bd.MARGIN)  # the height fits tighter
    assert min(ys) == pytest.approx(margin, abs=0.01)
    assert max(ys) == pytest.approx(1056 - margin, abs=0.01)
    assert (min(xs) + max(xs)) / 2 == pytest.approx(600, abs=0.01)


def test_the_scale_bar_is_five_kilometres_at_the_drawing_s_scale():
    scale, _ = bd.fit(bd.rings_m(SQUARE), (1200, 1056))
    bar = bd.paths(SQUARE, (1200, 1056))["scale_bar"]
    length = float(re.search(r"H([\d.]+)", bar)[1])
    assert length == pytest.approx(bd.SCALE_BAR_M * scale, abs=0.005)
    assert re.fullmatch(r"M0 -8 V0 H[\d.]+ V-8 M[\d.]+ 0 V-8", bar)
    middle = float(re.search(r"M([\d.]+) 0", bar)[1])
    assert middle == pytest.approx(length / 2, abs=0.005)
