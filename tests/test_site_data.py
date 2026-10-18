"""src/site/make_site_data.py and docs/data/: the website's map data (#111).

The committed data is the boundary as the build draws it: 104 steps that run
from the Beginning point, each ending at its own point, around to the
Beginning again; only the properties a reader needs; the area the README
gives; a status the site can show. The generator rounds, keeps and refuses
as it should, and the check tells stale files from platform drift (#116), on
a small made-up build. Standard library only, so the lint workflow runs
these.
"""

import json
import math
import os
import re
import sys

import pytest

from src import revision
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
    n = len(steps)
    assert [f["properties"]["step"] for f in steps] == list(range(1, n + 1))
    assert [f["properties"]["point"] for f in points] == ["Beginning"] + [
        str(k) for k in range(1, n + 1)
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
        readme = fh.read()
    assert re.search(rf"\b{re.escape(area)}\b", readme), f"{area} not in README"


def test_status_is_one_the_site_can_show():
    status = load("status.json")
    assert set(status) == {"name", "status", "established_on", "cfr_section"}
    assert status["status"] in msd.STATUSES


PROPOSED = {"Name": "Hickory Sands District", "Status": "Proposed"}


@pytest.mark.parametrize(
    ("record", "message"),
    [
        ({**PROPOSED, "Status": "Approved"}, "Status must be one of"),
        ({**PROPOSED, "Status": None}, "Status must be one of"),
        (
            {
                **PROPOSED,
                "Status": "Established",
                "CFR_Section": "27 CFR 9.300",
            },
            "needs its Established date and CFR_Section",
        ),
        (
            {
                **PROPOSED,
                "Status": "Established",
                "Established": "2027-01-01",
                "CFR_Section": "27 CFR 9.XXX",
            },
            "needs its Established date and CFR_Section",
        ),
    ],
)
def test_a_status_the_site_cannot_show_is_refused(record, message):
    with pytest.raises(SystemExit, match=message):
        msd.record_status(record)


@pytest.mark.parametrize(
    ("value", "date"),
    [
        (1798761600000, "2027-01-01"),  # epoch ms, as TTB's REST record gives
        ("2027-01-01T05:00:00Z", "2027-01-01"),
        ("2027-01-01", "2027-01-01"),
        ("soon", None),
        (True, None),
        (None, None),
    ],
)
def test_as_date_reads_the_record_s_dates(value, date):
    assert msd.as_date(value) == date


def test_a_placeholder_cfr_section_in_any_case_is_refused():
    record = {
        **PROPOSED,
        "Status": "Established",
        "Established": 1798761600000,
        "CFR_Section": "27 CFR 9.xxx",
    }
    with pytest.raises(SystemExit, match="needs its Established date"):
        msd.record_status(record)
    record["CFR_Section"] = "27 CFR 9.300"
    assert msd.record_status(record)["established_on"] == "2027-01-01"


def test_the_status_follows_the_record():
    assert msd.record_status({**PROPOSED, "CFR_Section": "27 CFR 9.XXX"}) == {
        "name": "Hickory Sands District",
        "status": "proposed",
        "established_on": None,
        "cfr_section": None,
    }
    established = {
        **PROPOSED,
        "Status": "Established",
        "Established": "2027-01-01",
        "CFR_Section": "27 CFR 9.300",
    }
    assert msd.record_status(established) == {
        "name": "Hickory Sands District",
        "status": "established",
        "established_on": "2027-01-01",
        "cfr_section": "27 CFR 9.300",
    }


def test_files_fit_the_commit_hook():
    for name in os.listdir(DATA):
        assert os.path.getsize(os.path.join(DATA, name)) < MAX_BYTES, name


COMMON = {"Name": "Hickory Sands District", "Counties": "Mason"}


def chain(n):
    """A made-up boundary of n steps: positions 0..n, closing at the start."""
    xy = [
        [-99.0 - 0.01 * k - 0.0000004, 30.0 + 0.01 * (k % 3)] for k in range(n)
    ]
    return [*xy, xy[0]]


def out_of_order(features):
    """The features shuffled: every second one first, then the rest."""
    return features[1::2] + features[::2]


def made_up_build(gis, n=10, step_hook=None, point_hook=None, areas=1):
    """Writes a made-up build's GIS files; the hooks may spoil one feature."""
    xy = chain(n)
    area = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    **COMMON,
                    "area_sqmi": "1.234",
                    "Status": "Proposed",
                    "Established": None,
                    "CFR_Section": "27 CFR 9.XXX",
                    "source": "x",
                },
                "geometry": {"type": "Polygon", "coordinates": [xy]},
            }
        ]
        * areas,
    }
    steps = [
        {
            "type": "Feature",
            "properties": {
                **COMMON,
                "step": k,
                "kind": "straight line",
                "endpoint": f"mark {k}",
                "quad": "Grit",
                "length_m": "1234.5678",
                "narrative": f"({k}) Proceed.",
                "change": "unchanged",
                "txt_source": "TTB",
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [*xy[k - 1], 500.0],
                    [(xy[k - 1][0] + xy[k][0]) / 2, xy[k - 1][1] + 0.001],
                    xy[k],
                ],
            },
        }
        for k in range(1, n + 1)
    ]
    points = [
        {
            "type": "Feature",
            "properties": {
                **COMMON,
                "point": "Beginning" if k == 0 else str(k),
                "step": k,
                "kind": "Beginning point" if k == 0 else "End of step",
                "point_name": f"mark {k}",
                "quad": "Grit",
            },
            "geometry": {"type": "Point", "coordinates": xy[k]},
        }
        for k in range(n + 1)
    ]
    if step_hook:
        step_hook(steps)
    if point_hook:
        point_hook(points)
    for kind, feats in (
        ("area", area["features"]),
        ("line", out_of_order(steps)),
        ("points", out_of_order(points)),
    ):
        path = os.path.join(gis, f"x-{revision.ISO}-{kind}-EPSG4269.geojson")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "features": feats}, fh)


@pytest.fixture
def build(tmp_path):
    gis = tmp_path / "gis"
    gis.mkdir()
    made_up_build(str(gis))
    return str(gis)


def test_generator_keeps_rounds_and_orders(build):
    files = msd.site_data(build)
    steps = json.loads(files["steps.geojson"])["features"]
    assert [s["properties"]["step"] for s in steps] == list(range(1, 11))
    assert steps[0]["properties"] == {
        "step": 1,
        "kind": "straight line",
        "endpoint": "mark 1",
        "quad": "Grit",
        "length_m": 1234.6,
        "narrative": "(1) Proceed.",
    }
    assert steps[0]["geometry"]["coordinates"][0] == [-99.0, 30.0]
    points = json.loads(files["points.geojson"])["features"]
    assert [p["properties"]["point"] for p in points] == ["Beginning"] + [
        str(k) for k in range(1, 11)
    ]
    (boundary,) = json.loads(files["boundary.geojson"])["features"]
    assert boundary["properties"] == {
        "name": "Hickory Sands District",
        "area_sqmi": 1.234,
        "counties": "Mason",
        "revision": revision.ISO,
    }
    assert boundary["geometry"]["coordinates"][0][1] == [-99.01, 30.01]
    assert msd.site_data(build) == files


@pytest.mark.parametrize(
    ("spoil", "message"),
    [
        (
            {"step_hook": lambda s: s[3]["properties"].update(quad="")},
            "step 4: quad",
        ),
        (
            {"step_hook": lambda s: s[4]["properties"].update(step=4)},
            "steps are not",
        ),
        ({"point_hook": lambda p: p.pop()}, "need 11 points"),
        ({"areas": 2}, "one boundary polygon, found 2"),
    ],
)
def test_generator_refuses_a_spoiled_build(tmp_path, spoil, message):
    made_up_build(str(tmp_path), **spoil)
    with pytest.raises(SystemExit, match=message):
        msd.site_data(str(tmp_path))


@pytest.mark.parametrize(("copies", "found"), [(0, "found 0"), (2, "found 2")])
def test_one_wants_exactly_one_file(build, copies, found):
    gis = build
    line = os.path.join(gis, f"x-{revision.ISO}-line-EPSG4269.geojson")
    if copies == 0:
        os.remove(line)
    else:
        with open(line, encoding="utf-8") as fh:
            text = fh.read()
        with open(os.path.join(gis, "y-line-EPSG4269.geojson"), "w") as fh:
            fh.write(text)
    with pytest.raises(SystemExit, match=found):
        msd.one(gis, "-line-EPSG4269.geojson")


def run_main(monkeypatch, capsys, build, out, *extra):
    argv = ["make_site_data.py", "--gis", build, "--out", str(out), *extra]
    monkeypatch.setattr(sys, "argv", argv)
    msd.main()
    return capsys.readouterr().out


def test_check_exits_stale_and_write_fixes_it(
    monkeypatch, capsys, build, tmp_path
):
    out = tmp_path / "data"
    with pytest.raises(SystemExit) as stop:
        run_main(monkeypatch, capsys, build, out, "--check")
    assert stop.value.code == msd.STALE
    assert "missing: boundary.geojson, points.geojson, status.json" in (
        capsys.readouterr().out
    )
    run_main(monkeypatch, capsys, build, out)
    (out / "extra.json").write_text("{}\n", encoding="utf-8")
    (out / "steps.geojson").write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        run_main(monkeypatch, capsys, build, out, "--check")
    said = capsys.readouterr().out
    assert stop.value.code == msd.STALE
    assert "differs from the build: steps.geojson" in said
    assert "not made by the build: extra.json" in said
    run_main(monkeypatch, capsys, build, out)
    assert sorted(os.listdir(out)) == sorted(msd.site_data(build))
    (out / ".DS_Store").write_bytes(b"\0")  # a Mac's Finder file is not stale
    assert "matches the build" in run_main(
        monkeypatch, capsys, build, out, "--check"
    )


def test_a_malformed_committed_shape_is_stale_not_a_traceback(
    monkeypatch, capsys, build, tmp_path
):
    out = tmp_path / "data"
    run_main(monkeypatch, capsys, build, out)
    steps = json.loads((out / "steps.geojson").read_text(encoding="utf-8"))
    steps["features"][2]["geometry"]["coordinates"] = []
    (out / "steps.geojson").write_text(json.dumps(steps), encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        run_main(monkeypatch, capsys, build, out, "--check")
    assert stop.value.code == msd.STALE


def nudge(degrees):
    """Moves the middle vertex of step 3 (not a pin) north by degrees."""

    def spoil(steps):
        steps[2]["geometry"]["coordinates"][1][1] += degrees

    return spoil


def on_the_line(fraction):
    """Adds a vertex on step 3's first segment, fraction of the way along."""

    def spoil(steps):
        (x1, y1, *_), (x2, y2), _ = steps[2]["geometry"]["coordinates"]
        at = [x1 + (x2 - x1) * fraction, y1 + (y2 - y1) * fraction]
        steps[2]["geometry"]["coordinates"].insert(1, at)

    return spoil


def drop_middle(steps):
    """Takes out step 3's middle vertex, straightening it by about 110 m."""
    del steps[2]["geometry"]["coordinates"][1]


@pytest.mark.parametrize(
    ("before", "after", "stale"),
    [
        # #116: a vertex slides along the line; the line does not move.
        (on_the_line(0.25), on_the_line(0.75), False),
        (None, on_the_line(0.5), False),  # one more vertex, on the line
        (None, nudge(0.00002), False),  # the line moves about 2 m
        (None, nudge(0.0001), True),  # about 11 m: more than drift
        (None, drop_middle, True),
        (
            None,
            lambda s: s[2]["properties"].update(narrative="(3) Elsewhere."),
            True,
        ),
    ],
)
def test_check_tells_drift_from_a_changed_boundary(
    monkeypatch, capsys, tmp_path, before, after, stale
):
    committed, other = tmp_path / "committed", tmp_path / "other"
    for gis in (committed, other):
        gis.mkdir()
    made_up_build(str(committed), step_hook=before)
    made_up_build(str(other), step_hook=after)
    out = tmp_path / "data"
    run_main(monkeypatch, capsys, str(committed), out)
    if stale:
        with pytest.raises(SystemExit) as stop:
            run_main(monkeypatch, capsys, str(other), out, "--check")
        assert stop.value.code == msd.STALE
        said = capsys.readouterr().out
        assert "differs from the build: steps.geojson" in said
    else:
        said = run_main(monkeypatch, capsys, str(other), out, "--check")
        apart = re.search(r"steps.geojson: lines up to ([0-9.]+) m apart", said)
        assert apart and float(apart.group(1)) < msd.MAX_DRIFT_M
        assert "matches the build" in said


def test_line_distance_ignores_where_vertices_fall():
    line = [[-99.0, 30.0], [-99.0, 30.01]]
    more = [[-99.0, 30.0], [-99.0, 30.004], [-99.0, 30.01]]
    assert msd.apart_m(line, more, 5.0) == pytest.approx(0.0, abs=1e-6)
    beside = [[-99.0, 30.0], [-99.00003, 30.005], [-99.0, 30.01]]
    assert 2.5 < msd.apart_m(line, beside, 5.0) < 3.0  # 0.00003 deg east
    assert msd.apart_m(line, [[-99.001, 30.0], [-99.0, 30.01]], 5.0) is None
    # Every vertex of each lies on the other, but one leaves a 1 km gap.
    pieces = [[line[0], [-99.0, 30.0001]], [[-99.0, 30.0099], line[1]]]
    assert msd.apart_m(line, pieces, 5.0) is None


WALK = (
    '<h1><span data-figure="step_count">0</span> steps, '
    '<span data-figure="miles">0</span> miles</h1><ol>@STEPS@</ol>'
)


def test_walk_page_lists_the_steps_escaped_with_coarse_lengths(build):
    made_up_build(
        build,
        step_hook=lambda s: s[1]["properties"].update(narrative="A <b> & C"),
    )
    page = msd.walk_page(msd.site_data(build), WALK)
    assert page.startswith('<h1><span data-figure="step_count">10</span> steps')
    assert page.count('<li class="walk-step"') == 11
    assert 'id="beginning" data-step="0"' in page
    assert "A &lt;b&gt; &amp; C" in page
    assert "<b>" not in page
    assert "0.8 mi" in page  # 1234.5678 m, to a tenth of a mile


def test_walk_template_needs_each_token_once(build):
    with pytest.raises(SystemExit, match="needs @STEPS@ once"):
        msd.walk_page(msd.site_data(build), "<h1>no list</h1>")


def test_check_covers_the_walk_page(monkeypatch, capsys, build, tmp_path):
    template = tmp_path / "walk.template.html"
    template.write_text(WALK, encoding="utf-8")
    page = tmp_path / "walk.html"
    out = tmp_path / "data"
    walk = ("--walk", str(template), str(page))
    run_main(monkeypatch, capsys, build, out, *walk)
    assert "matches the build" in run_main(
        monkeypatch, capsys, build, out, *walk, "--check"
    )
    page.write_text("edited by hand", encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        run_main(monkeypatch, capsys, build, out, *walk, "--check")
    assert stop.value.code == msd.STALE
    assert "walk.html: differs from the build" in capsys.readouterr().out
    page.unlink()
    with pytest.raises(SystemExit) as stop:
        run_main(monkeypatch, capsys, build, out, *walk, "--check")
    assert stop.value.code == msd.STALE
    assert "walk.html: missing" in capsys.readouterr().out


def test_a_length_drifting_across_a_rounding_edge_leaves_the_page(
    monkeypatch, capsys, tmp_path
):
    # 0.75 mi is 1207.008 m: one build rounds step 3 up, the other down.
    def length(metres):
        return lambda s: s[2]["properties"].update(length_m=str(metres))

    committed, other = tmp_path / "committed", tmp_path / "other"
    for gis in (committed, other):
        gis.mkdir()
    made_up_build(str(committed), step_hook=length(1207.2))
    made_up_build(str(other), step_hook=length(1206.9))
    template = tmp_path / "walk.template.html"
    template.write_text(WALK, encoding="utf-8")
    walk = ("--walk", str(template), str(tmp_path / "walk.html"))
    out = tmp_path / "data"
    run_main(monkeypatch, capsys, str(committed), out, *walk)
    assert "Step 3 · Grit · 0.8 mi" in (tmp_path / "walk.html").read_text(
        encoding="utf-8"
    )
    said = run_main(monkeypatch, capsys, str(other), out, *walk, "--check")
    assert "matches the build" in said


def test_walk_page_escapes_every_field_and_wants_each_token_once(build):
    def spoil(points):
        points[3]["properties"].update(point_name="Gate <3> & 4")

    made_up_build(
        build,
        step_hook=lambda s: s[2]["properties"].update(quad="Grit <i>"),
        point_hook=spoil,
    )
    page = msd.walk_page(msd.site_data(build), WALK)
    assert "Step 3 · Grit &lt;i&gt; · " in page
    assert "Gate &lt;3&gt; &amp; 4" in page
    with pytest.raises(SystemExit, match="needs @STEPS@ once"):
        msd.walk_page(msd.site_data(build), WALK + "@STEPS@")


def test_figures_come_from_the_data(build):
    figs = msd.figures(msd.site_data(build))
    assert figs["area_sqmi"] == ("1.23", None)
    assert figs["area_whole"] == ("1", None)
    assert figs["step_count"] == ("10", None)
    assert figs["point_count"] == ("11", None)
    assert figs["revision_date"] == (revision.LONG, revision.ISO)


def test_area_whole_rounds_half_up():
    files = {
        "boundary.geojson": json.dumps(
            {
                "features": [
                    {
                        "properties": {
                            "area_sqmi": 193.5,
                            "revision": "2026-10-15",
                        }
                    }
                ]
            }
        ),
        "steps.geojson": json.dumps({"features": []}),
        "points.geojson": json.dumps({"features": []}),
    }
    assert msd.figures(files)["area_whole"] == ("194", None)


def test_fill_figures_writes_text_and_a_time_s_date():
    figs = {
        "area_sqmi": ("193.83", None),
        "revision_date": ("October 15, 2026", "2026-10-15"),
        "evil": ("<b>&", None),
    }
    page = (
        '<p><span data-figure="area_sqmi">1.00</span> sq mi, '
        '<time data-figure="revision_date" datetime="2020-01-01">old</time>, '
        '<em data-figure="evil">x</em></p>'
    )
    filled = msd.fill_figures(page, figs, "page")
    assert '<span data-figure="area_sqmi">193.83</span>' in filled
    assert (
        '<time data-figure="revision_date" datetime="2026-10-15">'
        "October 15, 2026</time>"
    ) in filled
    assert '<em data-figure="evil">&lt;b&gt;&amp;</em>' in filled
    assert msd.fill_figures(filled, figs, "page") == filled


@pytest.mark.parametrize(
    ("page", "message"),
    [
        ('<span data-figure="nope">1</span>', "no figure called nope"),
        ('<span data-figure="area_sqmi"><b>1</b></span>', "only text"),
    ],
)
def test_fill_figures_refuses_an_unknown_or_nested_figure(page, message):
    with pytest.raises(SystemExit, match=message):
        msd.fill_figures(page, {"area_sqmi": ("1", None)}, "page")


def test_revision_comes_from_the_area_file_s_name(tmp_path):
    (tmp_path / "x-area-EPSG4269.geojson").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="no dated area file"):
        msd.revision_of(str(tmp_path))


def test_compared_areas_come_from_the_review_stats(build, tmp_path):
    stats = tmp_path / "grit-change-stats.json"
    stats.write_text(
        json.dumps({"sqmi": {"notice_243": 198.17, "petition": 194.03}}),
        encoding="utf-8",
    )
    files = msd.site_data(build, str(stats))
    (boundary,) = json.loads(files["boundary.geojson"])["features"]
    assert boundary["properties"]["petition_sqmi"] == 194.03
    figs = msd.figures(files)
    assert figs["petition_area_whole"] == ("194", None)
    assert figs["notice_243_area_whole"] == ("198", None)
    stats.write_text(json.dumps({"sqmi": {}}), encoding="utf-8")
    with pytest.raises(SystemExit, match="no petition and notice_243 areas"):
        msd.site_data(build, str(stats))


def test_check_and_write_cover_the_pages(monkeypatch, capsys, build, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    out = docs / "data"
    stale = '<p><span data-figure="step_count">99</span> steps</p>\n'
    (docs / "a.html").write_text(stale, encoding="utf-8")
    (docs / "b.html").write_text("<p>no figures</p>\n", encoding="utf-8")
    run_main(monkeypatch, capsys, build, out)  # the data first
    pages = ("--pages", str(docs))
    with pytest.raises(SystemExit) as stop:
        run_main(monkeypatch, capsys, build, out, *pages, "--check")
    assert stop.value.code == msd.STALE
    assert (
        "figures differ from the build: step_count" in capsys.readouterr().out
    )
    untouched = (docs / "b.html").stat().st_mtime_ns
    said = run_main(monkeypatch, capsys, build, out, *pages)
    assert "wrote the figures in" in said and "a.html" in said
    assert "b.html" not in said
    assert (docs / "b.html").stat().st_mtime_ns == untouched
    assert (docs / "a.html").read_text(encoding="utf-8") == (
        '<p><span data-figure="step_count">10</span> steps</p>\n'
    )
    assert "matches the build" in run_main(
        monkeypatch, capsys, build, out, *pages, "--check"
    )


def test_a_build_for_another_revision_is_refused(tmp_path):
    other = "1999-01-02"
    assert other != revision.ISO
    (tmp_path / f"x-{other}-area-EPSG4269.geojson").write_text(
        "{}", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match=r"run \./build\.sh"):
        msd.revision_of(str(tmp_path))
