"""src/site/make_site_data.py and docs/data/: the website's map data (#111).

The committed data is the boundary as the build draws it: 104 steps that run
from the Beginning point, each ending at its own point, around to the
Beginning again; only the properties a reader needs; the area the README
gives; a status the site can show. The generator rounds, keeps and flags
stale files as it should, on a small made-up build. Standard library only,
so the lint workflow runs these.
"""

import json
import math
import os

import pytest

from src.site import make_site_data as msd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "docs", "data")
MAX_BYTES = 2 * 1024 * 1024  # the commit hook's limit on added files


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def same(a, b):
    return math.dist(a, b) < 1e-9


def test_steps_and_points_are_complete():
    steps = load("steps.geojson")["features"]
    points = load("points.geojson")["features"]
    assert [f["properties"]["step"] for f in steps] == list(range(1, 105))
    assert [f["properties"]["point"] for f in points] == ["Beginning"] + [
        str(n) for n in range(1, 105)
    ]
    assert all(f["geometry"]["type"] == "LineString" for f in steps)
    assert all(tuple(f["properties"]) == msd.STEP_KEYS for f in steps)
    assert all(tuple(f["properties"]) == msd.POINT_KEYS for f in points)


def test_the_steps_run_point_to_point_around_the_boundary():
    steps = load("steps.geojson")["features"]
    at = {
        f["properties"]["point"]: f["geometry"]["coordinates"]
        for f in load("points.geojson")["features"]
    }
    lines = [f["geometry"]["coordinates"] for f in steps]
    assert same(lines[0][0], at["Beginning"])
    for n, line in enumerate(lines, start=1):
        assert same(line[-1], at[str(n)]), f"step {n} does not end at its point"
    for n in range(1, len(lines)):
        assert same(lines[n][0], lines[n - 1][-1]), f"gap before step {n + 1}"
    assert same(lines[-1][-1], at["Beginning"])


def test_boundary_area_is_the_readme_figure():
    (boundary,) = load("boundary.geojson")["features"]
    assert boundary["geometry"]["type"] == "Polygon"
    area = f"{boundary['properties']['area_sqmi']:.2f}"
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
        assert area in fh.read(), f"{area} sq mi is not the README's figure"


def test_status_is_one_the_site_can_show():
    assert msd.check_status(load("status.json"))["status"] in msd.STATUSES


@pytest.mark.parametrize(
    "status",
    [
        {"status": "approved"},
        {"status": "established", "established_on": None, "cfr_section": None},
        {"status": "established", "established_on": "2027-01-01"},
    ],
)
def test_bad_status_is_refused(status):
    with pytest.raises(SystemExit):
        msd.check_status(status)


def test_files_fit_the_commit_hook():
    for name in os.listdir(DATA):
        assert os.path.getsize(os.path.join(DATA, name)) < MAX_BYTES, name


def made_up_build(gis, status):
    common = {"Name": "Hickory Sands District", "Counties": "Mason"}
    area = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {**common, "area_sqmi": "1.234"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[-99.1234567, 30.1], [-99.2, 30.2], [-99.1, 30.3]]
                    ],
                },
            }
        ],
    }
    line = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    **common,
                    "step": 1,
                    "kind": "straight line",
                    "endpoint": "a mark",
                    "quad": "Grit",
                    "length_m": "1234.5678",
                    "narrative": "(1) Proceed east.",
                    "change": "unchanged",
                    "txt_source": "TTB",
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-99.12345678, 30.1, 500.0], [-99.2, 30.2]],
                },
            }
        ],
    }
    points = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    **common,
                    "point": p,
                    "step": s,
                    "kind": k,
                    "point_name": "a mark",
                    "quad": "Grit",
                },
                "geometry": {"type": "Point", "coordinates": xy},
            }
            for p, s, k, xy in (
                ("1", 1, "End of step", [-99.2, 30.2]),
                ("Beginning", 0, "Beginning point", [-99.12345678, 30.1]),
            )
        ],
    }
    for kind, data in (("area", area), ("line", line), ("points", points)):
        path = os.path.join(gis, f"x-{kind}-EPSG4269.geojson")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    with open(status, "w", encoding="utf-8") as fh:
        json.dump({"status": "proposed"}, fh)


def test_generator_rounds_keeps_and_orders(tmp_path):
    status = tmp_path / "status.json"
    made_up_build(str(tmp_path), str(status))
    files = msd.site_data(str(tmp_path), str(status))
    step = json.loads(files["steps.geojson"])["features"][0]
    assert step["properties"] == {
        "step": 1,
        "kind": "straight line",
        "endpoint": "a mark",
        "quad": "Grit",
        "length_m": 1234.6,
        "narrative": "(1) Proceed east.",
    }
    assert step["geometry"]["coordinates"][0] == [-99.123457, 30.1]
    points = json.loads(files["points.geojson"])["features"]
    assert [p["properties"]["point"] for p in points] == ["Beginning", "1"]
    assert msd.site_data(str(tmp_path), str(status)) == files


def test_stale_names_missing_and_changed_files(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.json").write_text("old\n", encoding="utf-8")
    (out / "b.json").write_text("same\n", encoding="utf-8")
    want = {"a.json": "new\n", "b.json": "same\n", "c.json": "x\n"}
    assert msd.stale(want, str(out)) == ["a.json", "c.json"]
