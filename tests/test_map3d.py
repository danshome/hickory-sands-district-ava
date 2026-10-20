"""The map (docs/map.html): the site's one map, made from the 3D aquifer page.

It opens on the proposed revision alone, straight down, with a popup for every
step and point; every other group (places, wells, vineyards, boundaries,
geology, the Hickory Aquifer) is off until it is turned on, and loads its data
only then. The menu's "The aquifer" opens it with the aquifer, the vineyards and
the places on (map.html?layers=aquifer,vineyards,places). These check, on the
committed files: that the page loads the site's one pinned SDK release and its
script; that its scripts read only files that exist; that only the district's
group starts on; that stats.json holds every figure it marks; the wells'
controls and the filter they start at; and the wording. Its data is
test_aquifer_3d.py's; its address, test_map_url.py's. Standard library only,
so the lint workflow runs these.
"""

import json
import os
import re

import pytest

from src.site.aquifer import vineyards

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
DATA = os.path.join(DOCS, "assets", "aquifer")
SCRIPTS = (
    "map3d.js",
    "map3d-district.js",
    "map-url.js",
    "aquifer-wells.js",
)
SDK = "https://js.arcgis.com/5.1/"
FORMATS = ("int", "pct", "num", "deg", "date", "scale")
WATER = "map.html?layers=aquifer,vineyards,places"
GROUPS = [
    "view",
    "district",
    "places",
    "wells",
    "vineyards",
    "boundaries",
    "geology",
    "aquifer",
]
VINEYARDS = os.path.join(
    ROOT, "resources", "vineyards", "vineyards-EPSG4269.geojson"
)
# The vineyards' data, made by src/site/make_vineyards.py.
VINES = os.path.join(DOCS, "assets", "vineyards")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def load(*parts):
    return json.loads(read(DATA, *parts))


@pytest.fixture(scope="module")
def page():
    return read(DOCS, "map.html")


@pytest.fixture(scope="module")
def scripts():
    return {name: read(DOCS, "assets", name) for name in SCRIPTS}


def test_the_page_loads_the_pinned_sdk_then_its_script(page):
    found = re.findall(r'<script type="module" src="([^"]+)"', page)
    # Its own script carries a version stamp (#138).
    assert [u.split("?v=")[0] for u in found] == [SDK, "assets/map3d.js"]
    assert not re.findall(r"js\.arcgis\.com/(?!5\.1/)", page)


def test_search_engines_may_index_the_page(page):
    # Dan, 2026-10-19 (#167): the site's pages are indexed.
    assert 'name="robots"' not in page


def test_the_page_says_so_when_its_view_cannot_load(page):
    note = re.search(r'<p class="map-nojs[^"]*">(.*?)</p>', page, re.S)
    assert note
    assert "<noscript>" not in page
    # Without the map, The boundary and Walk the line read on their own.
    assert 'href="boundary.html"' in note.group(1)
    assert 'href="walk.html"' in note.group(1)


def test_every_menu_lists_the_maps():
    # "The maps" (#179): The map, The aquifer (the map with the aquifer on)
    # and Walk the line, in that order, on every page.
    pages = [
        name
        for name in sorted(os.listdir(DOCS))
        if name.endswith(".html")
        and name not in ("explore.html", "aquifer.html")
    ]
    for name in pages:
        text = read(DOCS, name)
        nav = re.search(r'<nav aria-label="Main navigation">(.*?)</nav>', text)
        assert nav, name
        group = re.search(r'<div class="nav-group"[^>]*>(.*?)</div>', nav[1])
        assert group and ">The maps<" in group[1], name
        maps = re.findall(r'<a href="(/?)([^"]+)"[^>]*>([^<]+)</a>', group[1])
        root = "/" if name == "404.html" else ""
        assert maps == [
            (root, "map.html", "The map"),
            (root, WATER, "The aquifer"),
            (root, "walk.html", "Walk the line"),
        ], name
        # The aquifer is marked by the map's script, from its address.
        assert 'aria-current="page">The aquifer<' not in text, name
    template = read(ROOT, "src", "site", "walk.template.html")
    assert f'<a href="{WATER}">The aquifer</a>' in template


def test_the_land_page_links_the_water():
    assert f'href="{WATER}"' in read(DOCS, "land.html")


@pytest.mark.parametrize("name", SCRIPTS)
def test_scripts_never_parse_text_as_html(scripts, name):
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "write("):
        assert sink not in scripts[name], f"{name} uses {sink}"


def test_every_file_the_scripts_name_exists(scripts):
    # Each script names its files after its own DATA folder (and map3d.js
    # the vineyards' through vineyard-data.js's vineyardJson and vineyardUrl);
    # the tiles and the reports, named by key, are test_aquifer_3d.py's.
    named = set()
    for name, folder in (("map3d.js", ""), ("aquifer-wells.js", "wells/")):
        found = re.findall(
            r'(?:\$\{DATA\}|(?<!vineyardJson\()(?<!vineyardUrl\()")'
            r"([\w.-]+\.(?:json|geojson|bin))\b",
            scripts[name],
        )
        named |= {folder + f for f in found}
    assert {
        "stats.json",
        "hickory-k2.json",
        "hickory-k4.json",
        "drill-grid.bin",
        "wells/index.json",
        "context.geojson",
        "llano-uplift.geojson",
        "hickory-member.geojson",
        "precambrian.geojson",
        "precambrian-buried.geojson",
    } <= named
    for name in named:
        assert os.path.isfile(os.path.join(DATA, name)), name
    vines = set(
        re.findall(
            r'vineyard(?:Json|Url)\("([\w.-]+\.(?:json|geojson))"\)',
            scripts["map3d.js"],
        )
    )
    assert vines == {"stats.json", "vineyard-wells.json", "vineyards.geojson"}
    for name in vines:
        assert os.path.isfile(os.path.join(VINES, name)), name
    district = re.findall(
        r'"(data/[\w.-]+\.geojson)"', scripts["map3d-district.js"]
    )
    assert sorted(district) == [
        "data/boundary.geojson",
        "data/points.geojson",
        "data/steps.geojson",
    ]
    for name in district:
        assert os.path.isfile(os.path.join(DOCS, name)), name


def test_every_figure_the_page_shows_is_in_the_stats(page):
    # The aquifer's figures and the vineyards' (src/site/make_vineyards.py),
    # which the page merges; no name is in both.
    figures = load("stats.json")["figures"]
    with open(os.path.join(VINES, "stats.json"), encoding="utf-8") as fh:
        vines = json.load(fh)["figures"]
    assert not set(figures) & set(vines)
    figures.update(vines)
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


def test_the_district_s_figures_are_marked(page):
    # The build writes them (./build.sh site-data; test_site_figures.py).
    for name in ("area_sqmi", "step_count", "point_count", "revision_date"):
        assert f'data-figure="{name}"' in page, name


def test_the_wells_scales_come_from_the_stats(scripts):
    # Every well's head from about the district's scale in, the lines closer
    # in (#135): the page reads both scales from stats.json, never types them.
    figures = load("stats.json")["figures"]
    assert figures["wells_all_scale"] > figures["wells_lines_scale"] > 0
    main = scripts["map3d.js"]
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
    # Water levels start off; so do "Show wells" and the group's switch: the
    # wells load only when they are turned on.
    assert '<input type="checkbox" data-switch="wells-water">' in page
    assert re.search(r'id="aq-wells-show">', page)
    assert re.search(
        r'data-switch="wells" data-group-switch="wells" aria-label', page
    )


def test_the_page_says_which_wells_it_shows_at_first(page, scripts):
    # The wells start filtered (#148): irrigation wells that tested at 25 gpm
    # or more, none with an unreported yield. The panel's note before they
    # load is written from DEFAULT_FILTER; the filters' note and About say it
    # in words, which must be the script's.
    wells = scripts["aquifer-wells.js"]
    found = re.search(
        r'export const DEFAULT_FILTER = \{ use: "(\w+)", yieldLo: (\d+), '
        r"noYield: (true|false) \};",
        wells,
    )
    assert found
    use, low, no_yield = found.groups()
    assert no_yield == "false"
    defaults = wells[wells.index("const DEFAULTS") :]
    defaults = defaults[: defaults.index("};")]
    assert "index.use_groups.indexOf(DEFAULT_FILTER.use)" in wells
    assert "uses: new Set(IRRIGATION >= 0 ? [IRRIGATION]" in defaults
    assert "yieldLo: DEFAULT_FILTER.yieldLo," in defaults
    assert "noYield: DEFAULT_FILTER.noYield," in defaults
    # The data has the use group, and the yield slider a stop at the default.
    index = json.loads(read(DATA, "wells", "index.json"))
    assert use in index["use_groups"]
    stops = re.search(
        r"const YIELD_STOPS = \[([^\]]+)\];", scripts["map3d.js"]
    ).group(1)
    assert low in [s.strip() for s in stops.split(",")], stops
    said = (
        f"Shown at first: {use.lower()} wells that tested at {low} gpm or "
        "more; widen the filters to see the rest."
    )
    assert page.count(said) == 2
    assert page.count("data-wells-default") == 2
    # "Include wells with no value" starts unticked for the yield.
    assert '<input type="checkbox" id="aq-yield-none">' in page
    assert '<span id="aq-wells-start">' in page
    main = scripts["map3d.js"]
    assert re.search(
        r'setText\(\s*"aq-wells-start",\s*`\$\{DEFAULT_FILTER', main
    )
    # The far-out limit on every head is the script's, set as text.
    assert 'id="aq-wells-far-max"' in page
    assert re.search(r"export const FAR_HEADS_MAX = \d+;", wells)
    assert 'setText("aq-wells-far-max", n(FAR_HEADS_MAX))' in main


def test_the_panel_lists_the_groups_in_drawing_order(page):
    groups = re.findall(
        r'<section class="lp-group[^"]*" data-group="(\w+)"', page
    )
    assert groups == GROUPS


def test_only_the_district_starts_on(page):
    switches = re.findall(r"<input[^>]*data-group-switch=[^>]*>", page)
    on = [
        re.search(r'data-group-switch="(\w+)"', s).group(1)
        for s in switches
        if re.search(r"\schecked\b", s)
    ]
    assert len(switches) == len(GROUPS) - 1  # View has no switch
    assert on == ["district"]
    # The others are drawn as off, closed, until the script opens them.
    for group in GROUPS[2:]:
        assert f'<section class="lp-group is-off" data-group="{group}"' in page
        assert f'id="g-{group}" hidden' in page, group


def test_the_view_rows_below_the_ground_show_only_with_it(page):
    # Go to, From and Exaggeration show only while the aquifer or the wells
    # are on (the class is-underground on .aq).
    for row in ("v-place", "v-angle", "v-ve"):
        assert re.search(rf'<span id="{row}" class="lp-under">', page), row
    assert page.count('<div class="seg lp-under"') == 3
    css = read(DOCS, "assets", "map3d.css")
    assert ".aq:not(.is-underground) .lp-under{display:none}" in css


def test_the_map_opens_straight_down_on_imagery(page):
    # 2D and Imagery pressed in the HTML, as the address's defaults; 1x.
    assert 'data-look="2d" aria-pressed="true"' in page
    assert 'data-basemap="imagery" aria-pressed="true"' in page
    assert 'data-ve="1" aria-pressed="true"' in page


def test_every_layer_is_made_when_it_is_first_turned_on(scripts):
    # A GeoJSONLayer in the map fetches its file even while hidden, so each
    # group's layers are made, and so fetched, only when turned on (layersOf,
    # from FACTORIES); only the district's are made at once.
    main = scripts["map3d.js"]
    assert not re.findall(
        r"^(?:const|let) \w+ = new GeoJSONLayer\(", main, re.M
    )
    assert main.count("map.add(") == 1
    assert "map.add(layer, indexFor(orderKey))" in main
    factories = main[main.index("const FACTORIES = {") :]
    factories = factories[: factories.index("\n};\n")]
    for key in ("member", "counties", "ava", "towns", "precambrian"):
        assert re.search(rf'^\s+"?{key}"?: \(\) =>', factories, re.M), key
    opened = main[main.index("const map = new EsriMap(") :]
    opened = opened[: opened.index("const basemapRefused")]
    assert re.findall(r'layersOf\("(\w+)"\)', opened) == ["district", "steps"]


def test_every_vineyard_has_a_category_and_a_layer(page, scripts):
    categories = [c for c, _ in vineyards.CATEGORIES]
    features = json.loads(read(VINEYARDS))["features"]
    assert {f["properties"]["category"] for f in features} <= set(categories)
    for f in features:
        assert f["properties"]["source"], f["properties"]["name"]
    for category in categories:
        assert f'vineyardLayer("{category}"' in scripts["map3d.js"]
    assert page.count('data-switch="vineyards-') == len(categories)


def test_no_figure_is_typed_in_the_page(page):
    figures = load("stats.json")["figures"]
    text = re.sub(r"<[^>]+>", " ", page)
    for name in ("wells_drawn", "official_sqmi", "layer7_sqmi", "k2_blocks"):
        value = figures[name]
        typed = (f"{round(value):,}", f"{round(value)}")
        assert not any(t in text for t in typed), (name, value)


def test_the_labels_use_what_a_scene_supports(scripts):
    # A SceneView has no "always-horizontal" label placement: the SDK warns on
    # every load.
    assert "always-horizontal" not in scripts["map3d.js"]


def test_the_wording(page, scripts):
    text = re.sub(r"<[^>]+>", " ", page)
    for name in ("map3d.js", "map3d-district.js", "map-url.js"):
        text += scripts[name]
    assert "agreed" not in text.lower()
    assert not re.search(r"Hickory Sandstone(?! Member)", text)
    assert not re.search(r"\bDan\b(?! McLaughlin)", text)
    assert "proposed" in text


@pytest.mark.parametrize("name", ["map3d.js", "map3d-district.js"])
def test_no_error_is_swallowed(scripts, name):
    # The map always says when something did not load (the review of #160):
    # a move another move took over (an AbortError) is the only error a
    # script lets pass without a word.
    assert not re.search(r"\.catch\(\(\)\s*=>\s*\{\s*\}\)", scripts[name])


def test_the_map_says_what_did_not_load(scripts):
    main = scripts["map3d.js"]
    # a layer turned on that failed: said, its switch unticked, made again
    assert "function layerFailed(layer, error)" in main
    assert "layer.load().catch((error) => layerFailed(layer, error))" in main
    # the boundary: the map fails, and says so
    assert 'document.documentElement.dataset.map = "failed"' in main
    # a step or point in the address that does not exist
    assert 'say("address", `There is no ${asked}.`)' in main
    # figures that did not load: a dash, never "…"
    assert 'element.textContent = "—"' in main
