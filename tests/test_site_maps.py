"""The website's maps: the map (map.html) and Walk the line (#112), in docs/.

The pages load one pinned release of Esri's ArcGIS Maps SDK; the basemap key
is empty or an API key; no script parses text as HTML (the step text is set
as text); the walk page lists every step of docs/data/ with its own text, in
order; the map has what its scripts use, Explore's popups for every step and
point (#113), its three downloads and its basemaps. map.html's own page and
data tests are in test_map3d.py. Standard library only, so the lint workflow
runs these.
"""

import html
import json
import os
import re

import pytest

from src.site import make_site_data as msd
from src.site.stamp_assets import unstamped

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
SDK = "https://js.arcgis.com/5.1/"
MAP_PAGES = ("walk.html",)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def data(name):
    return json.loads(read("docs", "data", name))["features"]


@pytest.mark.parametrize("page", MAP_PAGES)
def test_map_pages_load_one_pinned_sdk_and_their_script(page):
    text = read("docs", page)
    scripts = re.findall(r'<script type="module" src="([^"]+)"', text)
    assert scripts[0] == SDK
    assert unstamped(scripts[1]) == f"assets/{page.replace('.html', '.js')}"
    assert not re.findall(r"js\.arcgis\.com/(?!5\.1/)", text)


def test_the_basemap_key_is_empty_or_an_api_key():
    key = re.search(
        r'apiKey =\s*"([^"]*)"', read("docs", "assets", "map-config.js")
    )
    assert key, "map-config.js exports apiKey"
    assert key.group(1) == "" or re.fullmatch(r"AAPT[\w.-]+", key.group(1))


@pytest.mark.parametrize(
    "script",
    [
        "maps.js",
        "walk.js",
        "map-config.js",
        "map3d.js",
        "map3d-district.js",
        "map-url.js",
        "moved.js",
        "aquifer-wells.js",
    ],
)
def test_scripts_never_parse_text_as_html(script):
    text = read("docs", "assets", script)
    for sink in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
    ):
        assert sink not in text, f"{script} uses {sink}"


def test_walk_page_lists_every_step_with_its_own_text():
    page = read("docs", "walk.html")
    steps = data("steps.geojson")
    items = re.findall(
        r'<li class="walk-step" id="([^"]+)" data-step="(\d+)">'
        r'.*?<p class="walk-text">(.*?)</p>',
        page,
    )
    assert [i[0] for i in items] == ["beginning"] + [
        f"step-{f['properties']['step']}" for f in steps
    ]
    for (_, _, text), f in zip(items[1:], steps, strict=True):
        assert text == html.escape(f["properties"]["narrative"])


def test_walk_page_is_what_its_template_and_the_data_give():
    files = {
        name: read("docs", "data", name)
        for name in ("boundary.geojson", "steps.geojson", "points.geojson")
    }
    files["status.json"] = read("docs", "data", "status.json")
    page = msd.walk_page(files, read("src", "site", "walk.template.html"))
    assert read("docs", "walk.html") == page, "run ./build.sh site-data"


@pytest.mark.parametrize(
    ("page", "selectors"),
    [
        (
            "map.html",
            [
                ".aq-stage",
                "<arcgis-scene",
                '<arcgis-popup slot="popup">',
                '<arcgis-home slot="top-right">',
                'id="map-look"',
                'data-basemap="imagery"',
                'data-basemap="topo"',
                'data-basemap="dark"',
                'data-look="2d"',
                'data-look="3d"',
                'data-group-switch="district" checked',
                'id="aq-panel-body"',
                'id="aq-sheet-toggle"',
            ],
        ),
        ("walk.html", [".walk-map", "arcgis-map", 'class="walk-step"']),
    ],
)
def test_the_elements_the_scripts_use_are_on_the_page(page, selectors):
    text = read("docs", page)
    for selector in selectors:
        assert selector.lstrip(".") in text, f"{page} lacks {selector}"


@pytest.mark.parametrize("page", [*MAP_PAGES, "map.html"])
def test_a_page_says_so_when_its_map_cannot_load(page):
    text = read("docs", page)
    assert '<p class="map-nojs' in text
    assert "<noscript>" not in text  # the note must show when the map fails too


@pytest.mark.parametrize("script", ["map3d-district.js", "map3d.js"])
def test_every_popup_fetches_its_fields(script):
    # Popups built by functions get only what they ask for: without outFields
    # a point's popup read "Point NaN" (#122).
    text = read("docs", "assets", script)
    blocks = re.findall(r"popupTemplate:\s*\{(.*?)\n\s*\},", text, re.S)
    assert blocks
    for block in blocks:
        assert re.search(r'outFields:\s*\[\s*"\*"\s*\]', block), block


def test_every_step_and_point_has_a_popup_and_a_walk_link():
    # Explore's popups (#113), now the map's: a step's quadrangle, length, end
    # and text, a point's quadrangle and name, each with a link to the same
    # place in Walk the line.
    text = read("docs", "assets", "map3d-district.js")
    for field in ("quad", "length_m", "endpoint", "narrative", "point_name"):
        assert f"a.{field}" in text, field
    assert "content: stepPopup" in text
    assert "content: pointPopup" in text
    assert "a.href = `walk.html#${walk.anchor}`" in text
    walk = read("docs", "walk.html")
    assert 'id="beginning"' in walk
    assert 'id="step-1"' in walk


def test_the_map_keeps_explore_s_downloads():
    page = read("docs", "map.html")
    for name in ("boundary", "steps", "points"):
        assert page.count(f'href="data/{name}.geojson" download') == 2, name
        assert os.path.isfile(os.path.join(DOCS, "data", f"{name}.geojson"))


def test_the_map_and_walk_link_each_other():
    assert '<a class="lp-link" href="walk.html">' in read("docs", "map.html")
    template = read("src", "site", "walk.template.html")
    assert 'href="map.html">Open the map<' in template
    assert 'href="map.html">Open the map<' in read("docs", "boundary.html")
