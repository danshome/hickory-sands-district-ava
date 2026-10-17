"""src/review/compare_ttb.py: a big difference's acres are those of the whole pieces of land its ring touches, even where
the ring's outline has a hole (issue #26); and the small helpers that find the stretches farther apart than the noise."""

import pytest

pytest.importorskip(
    "osgeo",
    reason="GDAL's Python bindings are in the build's .venv (./build.sh env), not the lint tools",
)
pytest.importorskip(
    "scipy",
    reason="SciPy is in the build's .venv (./build.sh env), not the lint tools",
)
import numpy as np  # noqa: E402
from osgeo import ogr  # noqa: E402
from src.review import compare_ttb  # noqa: E402

pytestmark = pytest.mark.build
REV, MAPX = "in the proposed revision only", "in the Map Explorer polygon only"
wkt = ogr.CreateGeometryFromWkt


def test_a_ring_counts_the_whole_pieces_it_touches_even_inside_its_hole():
    # a long stretch's ring: an outline 1 km square with a hole (EPSG:5070 metres)
    ring = wkt(
        "POLYGON ((0 0, 1000 0, 1000 1000, 0 1000, 0 0), (200 200, 800 200, 800 800, 200 800, 200 200))"
    )
    in_hole = wkt(
        "POLYGON ((300 300, 700 300, 700 700, 300 700, 300 300))"
    )  # 160,000 m2, all in the hole
    across = wkt(
        "POLYGON ((900 400, 3000 400, 3000 600, 900 600, 900 400))"
    )  # 420,000 m2, 20,000 inside
    touching = wkt(
        "POLYGON ((1000 0, 1100 0, 1100 100, 1000 100, 1000 0))"
    )  # shares only an edge
    away = wkt(
        "POLYGON ((5000 5000, 5100 5000, 5100 5100, 5000 5100, 5000 5000))"
    )
    pieces = [(in_hole, REV), (across, MAPX), (touching, REV), (away, MAPX)]
    add, rem = compare_ttb.touched_areas(ring, pieces, REV)
    assert (add, rem) == pytest.approx((160000.0, 420000.0))


def test_a_short_place_circle():
    circle = wkt("POINT (0 0)").Buffer(100.0, 24)
    near = wkt("POLYGON ((50 -10, 400 -10, 400 10, 50 10, 50 -10))")
    assert compare_ttb.touched_areas(
        circle, [(near, REV)], REV
    ) == pytest.approx((near.GetArea(), 0.0))


def test_runs_bridge_gaps_shorter_than_gap():
    s = np.arange(0, 20, 2.0)  # samples every 2 m
    mask = np.zeros(len(s), bool)
    mask[[1, 2, 3, 5, 6, 9]] = True
    assert compare_ttb.runs(mask, s, 5.0) == [
        (1, 6),
        (9, 9),
    ]  # 6 m -> 10 m bridged; 12 m -> 18 m not
    assert compare_ttb.runs(mask, s, 3.0) == [(1, 3), (5, 6), (9, 9)]
    assert compare_ttb.runs(np.zeros(3, bool), s[:3], 5.0) == []


def test_densify_every_2_m():
    q, s = compare_ttb.densify(np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 4.0]]))
    assert s.tolist() == [0, 2, 4, 6, 8, 10, 12, 14]
    assert q.tolist()[-3:] == [[10.0, 0.0], [10.0, 2.0], [10.0, 4.0]]


def test_polygons_and_poly_area_of_a_collection():
    g = wkt(
        "GEOMETRYCOLLECTION (POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0)), LINESTRING (0 0, 5 5), "
        "MULTIPOLYGON (((20 0, 22 0, 22 2, 20 2, 20 0))))"
    )
    assert [p.GetArea() for p in compare_ttb.polygons(g)] == [100.0, 4.0]
    assert (
        compare_ttb.poly_area(g) == 104.0 and compare_ttb.poly_area(None) == 0.0
    )
