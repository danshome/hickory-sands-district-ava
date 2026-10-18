"""The survey map under the boundary drawing on Home and The boundary.

The drawing's image, docs/assets/survey-map.webp, is made by the build
(src/site/make_survey_map.py) from the quads both manifests list, onto the
ground the drawing's viewBox covers; docs/data/survey-map.json records that
frame and those quads. These check the committed image and record against the
pages and the manifests, and the frame's fit and the staleness rule on made-up
drawings. Standard library only, so the lint workflow runs these.
"""

import csv
import json
import os
import struct

import pytest

from src.site import survey_frame as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
MANIFESTS = ("quads-manifest.csv", "basemap-manifest.csv")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def webp_size(path):
    """A WebP image's (width, height), read from its header."""
    with open(path, "rb") as fh:
        head = fh.read(30)
    assert head[:4] == b"RIFF" and head[8:12] == b"WEBP", path
    chunk = head[12:16]
    if chunk == b"VP8 ":
        w, h = struct.unpack("<HH", head[26:30])
        return [w & 0x3FFF, h & 0x3FFF]
    if chunk == b"VP8L":
        bits = int.from_bytes(head[21:25], "little")
        return [(bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1]
    if chunk == b"VP8X":
        return [
            int.from_bytes(head[24:27], "little") + 1,
            int.from_bytes(head[27:30], "little") + 1,
        ]
    raise AssertionError(f"{path}: unknown WebP chunk {chunk!r}")


@pytest.fixture(scope="module")
def committed():
    return json.loads(read(DOCS, "data", "survey-map.json"))


def test_home_and_the_boundary_draw_alike():
    home = sf.drawing(read(DOCS, "index.html"))
    boundary = sf.drawing(read(DOCS, "boundary.html"))
    assert home == boundary


def test_the_image_fills_the_drawing_at_the_records_size(committed):
    size, href, _ = sf.drawing(read(DOCS, "index.html"))
    assert committed["image"] == href
    assert committed["pixels"] == [round(v) for v in size]
    assert webp_size(os.path.join(DOCS, href)) == committed["pixels"]


def test_the_record_lists_exactly_the_manifests_quads(committed):
    rows = []
    for name in MANIFESTS:
        path = os.path.join(ROOT, "resources", "quads", name)
        with open(path, newline="", encoding="utf-8") as fh:
            rows += list(csv.DictReader(fh))
    assert (
        committed["quads"] == sf.record((0, 0, 0, 0), (0, 0), "", rows)["quads"]
    )
    names = [r["quad"] for r in rows]
    assert len(names) == len(set(names)), "a quad is in both manifests"


def test_the_record_is_on_utm_14n(committed):
    assert committed["crs"] == "EPSG:26914"
    frame = committed["frame_m"]
    assert frame["west"] < frame["east"]
    assert frame["south"] < frame["north"]


def drawn(ground, scale, offset):
    """Draws ground points north-up: x right, y down, in viewBox units."""
    return [
        ((e - offset[0]) * scale, (offset[1] - n) * scale) for e, n in ground
    ]


GROUND = [(500000.0, 3400000.0), (510000.0, 3410000.0), (505000.0, 3420000.0)]


def test_fit_finds_the_viewbox_on_the_ground():
    scale, offset, size = 0.02, (495000.0, 3425000.0), (600.0, 500.0)
    west, south, east, north = sf.fit(
        drawn(GROUND, scale, offset), GROUND, size
    )
    assert west == pytest.approx(offset[0])
    assert north == pytest.approx(offset[1])
    assert east == pytest.approx(offset[0] + size[0] / scale)
    assert south == pytest.approx(offset[1] - size[1] / scale)


def test_fit_refuses_a_drawing_at_two_scales():
    points = [(x * 1.01, y) for x, y in drawn(GROUND, 0.02, (0, 3425000))]
    with pytest.raises(ValueError, match="scales differ"):
        sf.fit(points, GROUND, (600.0, 500.0))


def test_drawing_refuses_an_image_that_does_not_fill_the_viewbox():
    page = (
        '<svg class="boundary-map" viewBox="0 0 100 80">'
        '<image class="survey-layer" href="a.webp" width="100" height="70"/>'
        '<path class="boundary-line" d="M1,2 L3,4"/>'
    )
    with pytest.raises(ValueError, match="does not fill"):
        sf.drawing(page)


ROWS = [
    {
        "quad": "B, TX",
        "edition": "1960",
        "geotiff": "TX_B_2_1960_24000_geo.tif",
    },
    {
        "quad": "A, TX",
        "edition": "1955",
        "geotiff": "TX_A_1_1955_24000_geo.tif",
    },
]


def test_a_frame_within_two_metres_is_up_to_date():
    old = sf.record((1000, 2000, 3000, 4000), (10, 8), "x.webp", ROWS)
    new = sf.record((1001.4, 2000, 3000, 3998.6), (10, 8), "x.webp", ROWS)
    assert sf.differences(old, new) == []


def test_a_moved_frame_or_changed_quad_is_stale():
    old = sf.record((1000, 2000, 3000, 4000), (10, 8), "x.webp", ROWS)
    moved = sf.record((1010, 2000, 3000, 4000), (10, 8), "x.webp", ROWS)
    assert sf.differences(old, moved) == ["frame west 1000 -> 1010"]
    reprinted = [dict(ROWS[0], edition="1970"), ROWS[1]]
    changed = sf.record((1000, 2000, 3000, 4000), (10, 8), "x.webp", reprinted)
    assert sf.differences(old, changed) == ["quads"]
    assert sf.differences(None, old) == ["no record"]
