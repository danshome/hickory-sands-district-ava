"""The Hickory Aquifer in 3D (#135): docs/aquifer.html and its data.

The page's data, docs/assets/aquifer/, is made by src/site/make_aquifer_3d.py
from the downloads resources/aquifer/inputs.csv pins and committed inputs.
These check, on the committed files: that the data is up to date with its
record (the build's own check, which needs no download); that the page and
its scripts read only files that exist; that the page loads the site's one
pinned SDK release; that no well report holds a removed field, or free text
with a title, a company's name, a phone number, an e-mail or street address,
or (in a note about people) a role word or initials; that stats.json holds
every figure the page shows; that every file is under the hooks' 2 MB; and
the wording. And, on made-up records, what the check calls stale.
Standard library only, so the lint workflow runs these.
"""

import json
import os
import re

import pytest

from src.site.aquifer import params
from src.site.aquifer import privacy
from src.site.aquifer import record
from src.site.aquifer import vineyards

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
DATA = os.path.join(DOCS, "assets", "aquifer")
SCRIPTS = ("aquifer3d.js", "aquifer-wells.js")
SDK = "https://js.arcgis.com/5.1/"
FORMATS = ("int", "pct", "num", "deg", "date", "scale")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def load(*parts):
    return json.loads(read(DATA, *parts))


@pytest.fixture(scope="module")
def page():
    return read(DOCS, "aquifer.html")


@pytest.fixture(scope="module")
def scripts():
    return {name: read(DOCS, "assets", name) for name in SCRIPTS}


@pytest.fixture(scope="module")
def index():
    return load("wells", "index.json")


def test_the_committed_data_is_up_to_date():
    # What ./build.sh checks (make_aquifer_3d.py --check): no download needed.
    new = record.expected(record.read_manifest(), record.local_digests())
    old = record.read_record(DATA)
    assert record.differences(old, new, record.listing(DATA)) == [], (
        "run ./build.sh site-data"
    )


def test_the_manifest_pins_https_downloads():
    rows = record.read_manifest()
    assert rows
    for row in rows:
        assert row["url"].startswith("https://"), row["name"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["snapshot"]), row
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["fetched"]), row


def test_the_page_loads_the_pinned_sdk_then_its_script(page):
    found = re.findall(r'<script type="module" src="([^"]+)"', page)
    assert found == [SDK, "assets/aquifer3d.js"]
    assert not re.findall(r"js\.arcgis\.com/(?!5\.1/)", page)


def test_the_page_stays_out_of_search_engines(page):
    assert '<meta name="robots" content="noindex">' in page


def test_the_page_says_so_when_its_view_cannot_load(page):
    assert '<p class="map-nojs' in page
    assert "<noscript>" not in page


def test_the_land_page_links_here():
    assert 'href="aquifer.html"' in read(DOCS, "land.html")


@pytest.mark.parametrize("name", SCRIPTS)
def test_scripts_never_parse_text_as_html(scripts, name):
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "write("):
        assert sink not in scripts[name], f"{name} uses {sink}"


def test_every_file_the_scripts_name_exists(scripts):
    # Each script names its files after its own DATA folder; the tiles and
    # the reports, named by key, are the next test's.
    named = set()
    for name, folder in (("aquifer3d.js", ""), ("aquifer-wells.js", "wells/")):
        found = re.findall(
            r'(?:\$\{DATA\}|")([\w.-]+\.(?:json|geojson|bin))\b', scripts[name]
        )
        named |= {folder + f for f in found}
    assert {
        "stats.json",
        "hickory-k2.json",
        "hickory-k4.json",
        "drill-grid.bin",
        "vineyard-wells.json",
        "wells/index.json",
    } <= named
    for name in named:
        assert os.path.isfile(os.path.join(DATA, name)), name
    assert '"data/boundary.geojson"' in scripts["aquifer3d.js"]
    assert os.path.isfile(os.path.join(DOCS, "data", "boundary.geojson"))


def test_every_tile_and_report_cell_exists(index):
    wells = os.path.join(DATA, "wells")
    cells = set()
    for key in index["tiles"]:
        records = load("wells", f"draw-{key}.json")
        assert len(records) == index["tiles"][key]["count"], key
        cells |= {r[8] for r in records}
    cells |= {r[8] for r in index["overview"]}
    near = load("vineyard-wells.json")["vineyards"]
    cells |= {r[9] for found in near.values() for r in found}
    for cell in cells:
        assert os.path.isfile(os.path.join(wells, f"detail-{cell}.json")), cell
    drawn = sum(t["count"] for t in index["tiles"].values())
    assert drawn == len(index["filter_keys"])


def test_every_figure_the_page_shows_is_in_the_stats(page):
    figures = load("stats.json")["figures"]
    marks = re.findall(
        r'data-stat="([a-z0-9_]+)"(?: data-format="(\w+)")?', page
    )
    assert marks
    for name, form in marks:
        assert name in figures, f"stats.json has no {name}"
        assert (form or "int") in FORMATS, form
        assert figures[name] is not None, name
    assert page.count("data-stat") == len(marks), (
        "write data-stat, then data-format"
    )


def test_the_wells_scales_come_from_the_stats(scripts):
    # Every well's head from about the district's scale in, the lines closer
    # in (#135): the page reads both scales from stats.json, never types them.
    figures = load("stats.json")["figures"]
    assert figures["wells_all_scale"] > figures["wells_lines_scale"] > 0
    main = scripts["aquifer3d.js"]
    assert "allScale: stats.wells_all_scale" in main
    assert "linesScale: stats.wells_lines_scale" in main
    assert "detailScale" not in main
    wells = scripts["aquifer-wells.js"].replace("_", "")
    for name in ("wells_all_scale", "wells_lines_scale"):
        assert f"{figures[name]:.0f}" not in wells, name


def test_the_wells_group_has_the_controls_asked_for(page):
    for label in (
        ">Show wells<",
        ">Well use (the report's WellUse)<",
        ">Water volume, highest tested yield (gpm)<",
        ">Reported depth<",
        ">Hickory Aquifer only<",
        ">Water levels<",
    ):
        assert label in page, label
    assert page.count(">Include wells with no value<") == 2
    # Water levels start off; "Show wells" and the group's switch start on.
    assert '<input type="checkbox" data-switch="wells-water">' in page
    assert 'id="aq-wells-show" checked' in page
    assert 'data-switch="wells" data-group-switch="wells" checked' in page


def test_the_panel_lists_the_groups_in_drawing_order(page):
    groups = re.findall(r'<section class="lp-group" data-group="(\w+)"', page)
    assert groups == [
        "view",
        "places",
        "wells",
        "vineyards",
        "boundaries",
        "geology",
        "aquifer",
    ]


def test_no_figure_is_typed_in_the_page(page):
    figures = load("stats.json")["figures"]
    text = re.sub(r"<[^>]+>", " ", page)
    for name in ("wells_drawn", "official_sqmi", "layer7_sqmi", "k2_blocks"):
        value = figures[name]
        typed = (f"{round(value):,}", f"{round(value)}")
        assert not any(t in text for t in typed), (name, value)


def test_no_well_report_keeps_a_name_or_contact():
    # The generator's own check also tests every name in the area; this is the
    # part that needs no names list.
    assert privacy.scan(DATA) == []


@pytest.mark.parametrize(
    ("text", "field"),
    [
        ("Mr. Smith's well", "LithologyDescription"),
        ("call 830-555-0123", "WaterType"),
        ("A&W Well Service", "PumpTypeOtherDesc"),
        ("Pump by Ramm", "PumpTypeOtherDesc"),
        ("Logged by DT", "Comments"),
        ("^JLO", "Comments"),
        ("Land Owner", "DistanceVerificationMethod"),
        ("1201 County Road 102", "Remarks"),
    ],
)
def test_the_scan_catches_names_and_contacts(text, field):
    assert privacy.scan_record({field: text})


def test_the_scan_keeps_well_terms():
    assert not privacy.scan_record(
        {
            "LithologyDescription": "red granite, hard",
            "WaterType": "good (500 ppmTDS)",
            "Comments": "Well collapsed at 228'",
            "SealedByDriller": "Yes",
        }
    )


def test_a_removed_field_is_caught_at_any_depth():
    found = privacy.scan_record({"GWDB": [{"Owner": ""}], "x": "y"})
    assert found == ["field Owner"]
    assert privacy.scan_record({"LocationVerifiedByDriller": "Smith"})


VINEYARDS = os.path.join(
    ROOT, "resources", "vineyards", "vineyards-EPSG4269.geojson"
)


@pytest.mark.parametrize(
    "path", [VINEYARDS, os.path.join(DATA, "vineyards.geojson")]
)
def test_the_vineyards_name_no_one(path):
    features = json.loads(read(path))["features"]
    for f in features:
        text = json.dumps(f["properties"], ensure_ascii=False)
        assert not vineyards.named(text), f["properties"]["name"]
        assert not re.search(r"\b\d{3,6} (E\.|W\.|N\.|S\.)? ?Hwy", text)


def test_the_vineyard_check_refuses_a_name():
    assert vineyards.named('{"source": "the layer of Dan McLaughlin"}')
    assert vineyards.named('{"source": "per the owner"}')
    assert vineyards.named('{"source": "Quillfeather"}', ["quillfeather"])
    assert not vineyards.named('{"name": "Robert Clay Vineyards"}')


def test_every_vineyard_has_a_category_and_a_layer(page, scripts):
    categories = [c for c, _ in params.VINEYARD_CATEGORIES]
    features = json.loads(read(VINEYARDS))["features"]
    assert {f["properties"]["category"] for f in features} <= set(categories)
    for f in features:
        assert f["properties"]["source"], f["properties"]["name"]
    for category in categories:
        assert f'vineyardLayer("{category}"' in scripts["aquifer3d.js"]
    assert page.count('data-switch="vineyards-') == len(categories)


def test_every_file_is_under_the_hooks_limit():
    big = {
        path: size
        for path, size in record.listing(DATA).items()
        if size >= params.MAX_FILE_BYTES
    }
    assert not big


def test_the_wording():
    text = re.sub(r"<[^>]+>", " ", read(DOCS, "aquifer.html"))
    text += read(DOCS, "assets", "aquifer3d.js")
    assert "agreed" not in text.lower()
    assert not re.search(r"Hickory Sandstone(?! Member)", text)
    assert not re.search(r"\bDan\b(?! McLaughlin)", text)
    assert "proposed" in text


# ---- What the check calls stale, on made-up records.

ROWS = [
    {
        "name": "model",
        "file": "m.7z",
        "url": "https://example.invalid/m.7z",
        "snapshot": "2026-07-16",
        "fetched": "2026-10-18",
        "bytes": 10,
        "sha256": "a" * 64,
    },
]
LOCAL = {"faults": {"file": "f.geojson", "sha256": "sha256:" + "b" * 64}}
FILES = {"stats.json": 100, "wells/index.json": 200}


def committed():
    return record.expected(ROWS, LOCAL, FILES)


def test_the_same_inputs_and_files_are_up_to_date():
    new = record.expected(ROWS, LOCAL)
    assert record.differences(committed(), new, dict(FILES)) == []


def test_a_new_snapshot_or_parameter_is_stale():
    rows = [dict(ROWS[0], sha256="c" * 64)]
    assert record.differences(
        committed(), record.expected(rows, LOCAL), dict(FILES)
    ) == ["inputs model"]
    new = record.expected(ROWS, LOCAL)
    new["parameters"]["tile_deg"] = 0.3
    assert record.differences(committed(), new, dict(FILES)) == [
        "parameters tile_deg"
    ]
    local = {"faults": dict(LOCAL["faults"], sha256="sha256:" + "d" * 64)}
    assert record.differences(
        committed(), record.expected(ROWS, local), dict(FILES)
    ) == ["local faults"]


def test_a_missing_resized_or_unlisted_file_is_stale():
    new = record.expected(ROWS, LOCAL)
    assert record.differences(committed(), new, {"stats.json": 100}) == [
        "wells/index.json is missing"
    ]
    assert record.differences(
        committed(), new, {**FILES, "stats.json": 101}
    ) == ["stats.json is 101 bytes, not 100"]
    assert record.differences(committed(), new, {**FILES, "x.json": 1}) == [
        "x.json is not in the record"
    ]


def test_no_record_is_stale():
    assert record.differences(None, record.expected(ROWS, LOCAL)) == [
        "no record"
    ]


def test_the_record_holds_no_bare_hex_digest():
    # detect-secrets takes a bare 64-character hex string for a secret.
    text = read(DATA, "record.json")
    assert not re.search(r'"[0-9a-f]{32,}"', text)
    assert '"sha256:' in text
