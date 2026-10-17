"""src/review/grit_change.py: lengths, acres and the pieces of a difference.

Line lengths geodesic on GRS 1980, as the boundary layer's (issue #35); the
acres of each kind of piece summed unrounded and rounded once (issue #33); the
pieces of a difference, largest first, slivers dropped.
"""

import math

import pytest

pytest.importorskip(
    "osgeo",
    reason="GDAL's Python bindings are in the build's .venv (./build.sh env), "
    "not the lint tools",
)
from osgeo import ogr

from src.review import grit_change

pytestmark = pytest.mark.build
A, F = 6378137.0, 1 / 298.257222101  # GRS 1980
E2 = F * (2 - F)


def test_glen_along_the_equator():
    assert grit_change.glen([(0, 0), (1, 0)]) == pytest.approx(
        A * math.pi / 180, abs=1e-3
    )


def test_glen_along_a_meridian():
    n, h = (
        2000,
        math.radians(1) / 2000,
    )  # the meridian arc from 0 to 1 degree north, by Simpson's rule

    def meridian_radius(p):  # of curvature, at latitude p
        return A * (1 - E2) / (1 - E2 * math.sin(p) ** 2) ** 1.5

    arc = (
        h
        / 3
        * sum(
            (1 if i in (0, n) else 4 if i % 2 else 2) * meridian_radius(i * h)
            for i in range(n + 1)
        )
    )
    assert grit_change.glen([(-99.2, 0), (-99.2, 1)]) == pytest.approx(
        arc, abs=1e-3
    )


def test_glen_is_geodesic_not_albers_at_the_ava():
    """0.1 degree east-west at 30.8 N: the parallel's arc.

    The geodesic is 0.3 mm shorter; NAD83 / Conus Albers says 9,545 m, 25 m
    short: the planar length issue #35 found in the Grit lines layer.
    """
    pts = [(-99.2, 30.8), (-99.1, 30.8)]
    phi = math.radians(30.8)
    arc = (
        A
        / math.sqrt(1 - E2 * math.sin(phi) ** 2)
        * math.cos(phi)
        * math.radians(0.1)
    )
    assert grit_change.glen(pts) == pytest.approx(arc, abs=1e-3)
    assert abs(grit_change.line(pts).Length() - grit_change.glen(pts)) > 20


def test_totals_summed_unrounded_and_rounded_once():
    stats = {}
    for _ in range(3):
        grit_change.tally(
            stats,
            "granite lobe",
            {"acres": 0.334, "granite_acres": 0.004, "sandstone_acres": 0.0},
        )
    grit_change.tally(
        stats,
        "put back",
        {"acres": 6.0, "granite_acres": 0.0, "sandstone_acres": 0.0},
    )
    assert grit_change.rounded(stats) == {
        "granite lobe": {
            "pieces": 3,
            "acres": 1.0,
            "granite_acres": 0.01,
            "sandstone_acres": 0.0,
        },  # not 0.99 and 0.0
        "put back": {
            "pieces": 1,
            "acres": 6.0,
            "granite_acres": 0.0,
            "sandstone_acres": 0.0,
        },
    }


@pytest.mark.parametrize(
    "exact, whole", [(2596.4724, 2596), (27.4521, 27)]
)  # issue #33's figures: not 2,597 and 28
def test_whole_acres_from_the_totals_round_once(exact, whole):
    stats = {}
    grit_change.tally(
        stats,
        "x",
        {"acres": exact, "granite_acres": exact, "sandstone_acres": 0.0},
    )
    assert (
        int(grit_change.rounded(stats)["x"]["granite_acres"] + 0.5) == whole
    )  # as the publishing code shows them


def square(x, y, side):
    return (
        f"(({x} {y}, {x + side} {y}, {x + side} {y + side}, "
        f"{x} {y + side}, {x} {y}))"
    )


def test_pieces_largest_first_slivers_dropped():
    acre = grit_change.SQM_PER_ACRE**0.5  # metres (EPSG:5070)
    two, ten, fifth = (
        square(0, 0, acre * 2**0.5),
        square(1000, 0, acre * 10**0.5),
        square(2000, 0, acre * 0.2**0.5),
    )  # 2, 10 and 0.2 acres
    g = ogr.CreateGeometryFromWkt(f"MULTIPOLYGON ({two}, {ten}, {fifth})")
    assert [
        round(p.GetArea() / grit_change.SQM_PER_ACRE, 6)
        for p in grit_change.pieces(g, 0.5)
    ] == [10, 2]
    one = ogr.CreateGeometryFromWkt(f"POLYGON {square(0, 0, acre)}")
    assert (
        len(grit_change.pieces(one, 0.5)) == 1
        and grit_change.pieces(one, 1.5) == []
    )
