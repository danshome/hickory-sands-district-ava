"""The website's maps (#112, #113): Explore and Walk the line, in docs/.

The pages load one pinned release of Esri's ArcGIS Maps SDK; the basemap key
is empty or an API key; no script parses text as HTML (the step text is set
as text); the walk page lists every step of docs/data/ with its own text, in
order; the Explore page's figures are the build's. Standard library only, so
the lint workflow runs these.
"""

import html
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
SDK = "https://js.arcgis.com/5.1/"
MAP_PAGES = ("explore.html", "walk.html")


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
    assert scripts[1] == f"assets/{page.replace('.html', '.js')}"
    assert not re.findall(r"js\.arcgis\.com/(?!5\.1/)", text)


def test_the_basemap_key_is_empty_or_an_api_key():
    key = re.search(
        r'apiKey =\s*"([^"]*)"', read("docs", "assets", "map-config.js")
    )
    assert key, "map-config.js exports apiKey"
    assert key.group(1) == "" or re.fullmatch(r"AAPT[\w.-]+", key.group(1))


@pytest.mark.parametrize(
    "script", ["maps.js", "explore.js", "walk.js", "map-config.js"]
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


def test_explore_page_figures_are_the_build_s():
    page = read("docs", "explore.html")
    (boundary,) = data("boundary.geojson")
    area = f"{boundary['properties']['area_sqmi']:.2f}"
    steps, points = len(data("steps.geojson")), len(data("points.geojson"))
    assert (
        f"{area} square miles inside {steps} steps and {points} points" in page
    )
