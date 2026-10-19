"""The map's address (docs/assets/map-url.js), run in node.

map.html reads what to show from its address before anything loads:
?layers= (the groups to turn on besides the district, or "all"), view, look,
basemap, and a step or point whose popup opens. As the reader turns groups on
and off and changes the basemap, the layers and the basemap are written back,
so a copied address opens the same map. A word the page does not know is left
out, never shown. map-url.js holds no Esri code, so node runs it here when it
is installed (it is on GitHub's Linux runners); without node these are
skipped.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "docs", "assets", "map-url.js")
NODE = shutil.which("node")
WATER = "map.html?layers=aquifer,vineyards,places"
# Calls readState(search) or writeState(search, {layers, basemap}) with JSON
# arguments from stdin and prints the result as JSON (a Set as a sorted list):
# node only evaluates, the tests decide.
BRIDGE = """
import { pathToFileURL } from "node:url";
const [path, name] = process.argv.slice(1);
const module = await import(pathToFileURL(path));
let input = "";
for await (const chunk of process.stdin) input += chunk;
const args = JSON.parse(input);
let result;
if (name === "readState") {
  const state = module.readState(args[0]);
  result = { ...state, layers: [...state.layers].sort() };
} else if (name === "writeState") {
  const layers = new Set(args[1].layers);
  result = module.writeState(args[0], { ...args[1], layers });
} else {
  result = module[name];
}
process.stdout.write(JSON.stringify(result ?? null));
"""


@pytest.fixture(scope="module")
def js(tmp_path_factory):
    """Returns call(name, *args): readState, writeState or a constant."""
    if NODE is None:
        pytest.skip("node is not installed")
    module = tmp_path_factory.mktemp("js") / "map-url.mjs"
    shutil.copyfile(SCRIPT, module)  # .mjs: a module, whatever node's version

    def call(name, *args):
        done = subprocess.run(
            [NODE, "--input-type=module", "-e", BRIDGE, str(module), name],
            input=json.dumps(list(args)),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=60,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return call


def test_the_plain_map_shows_the_district_alone(js):
    state = js("readState", "")
    assert state == {
        "layers": ["district"],
        "water": False,
        "place": "district",
        "look": "2d",
        "basemap": "imagery",
        "step": None,
        "point": None,
    }


def test_the_water_opens_as_the_aquifer_page_did(js):
    state = js("readState", "?" + WATER.split("?", 1)[1])
    assert state["layers"] == ["aquifer", "district", "places", "vineyards"]
    assert state["water"] is True
    assert (state["place"], state["look"], state["basemap"]) == (
        "whole",
        "3d",
        "dark",
    )
    assert js("WATER") == WATER


def test_the_wells_alone_tilt_the_view_on_the_district(js):
    state = js("readState", "?layers=wells")
    assert state["layers"] == ["district", "wells"]
    assert state["water"] is False
    assert (state["place"], state["look"], state["basemap"]) == (
        "district",
        "3d",
        "dark",
    )


def test_all_turns_on_every_group(js):
    state = js("readState", "?layers=all")
    assert state["layers"] == sorted(js("GROUPS"))


@pytest.mark.parametrize(
    "search",
    [
        "?layers=nothing,<script>,wells",
        "?layers=WELLS",
        "?layers=%20wells%20",
        "?layers=wells,,",
        "?layers=nothing,%20wells",
    ],
)
def test_unknown_words_are_dropped(js, search):
    assert js("readState", search)["layers"] == ["district", "wells"]


def test_view_look_and_basemap_take_only_their_values(js):
    state = js(
        "readState", "?layers=aquifer&view=district&look=2d&basemap=topo"
    )
    assert (state["place"], state["look"], state["basemap"]) == (
        "district",
        "2d",
        "topo",
    )
    state = js("readState", "?view=moon&look=4d&basemap=paper")
    assert (state["place"], state["look"], state["basemap"]) == (
        "district",
        "2d",
        "imagery",
    )


@pytest.mark.parametrize(
    ("search", "step", "point"),
    [
        ("?step=52", 52, None),
        ("?step=007", 7, None),
        ("?step=1234", None, None),
        ("?step=5a", None, None),
        ("?step=-3", None, None),
        ("?point=beginning", None, "Beginning"),
        ("?point=Beginning", None, "Beginning"),
        ("?point=12", None, 12),
        ("?point=start", None, None),
    ],
)
def test_a_step_or_point_is_a_number_or_the_beginning(js, search, step, point):
    state = js("readState", search)
    assert (state["step"], state["point"]) == (step, point)


def test_the_address_keeps_the_groups_on_and_a_chosen_basemap(js):
    assert (
        js("writeState", "", {"layers": ["district"], "basemap": "imagery"})
        == ""
    )
    assert (
        js(
            "writeState",
            "",
            {"layers": ["district", "wells"], "basemap": "dark"},
        )
        == "?layers=wells"
    )
    assert (
        js("writeState", "", {"layers": ["district"], "basemap": "topo"})
        == "?basemap=topo"
    )
    # The groups in the panel's order, whatever order they were turned on.
    got = js(
        "writeState",
        "?step=52&look=3d",
        {
            "layers": ["aquifer", "places", "district", "vineyards"],
            "basemap": "dark",
        },
    )
    assert got == "?step=52&look=3d&layers=places,vineyards,aquifer"


def test_a_written_address_reads_back_the_same(js):
    for layers, basemap in (
        (["district", "geology", "boundaries"], "topo"),
        (["district", "wells", "aquifer"], "imagery"),
        (["district"], "dark"),
    ):
        search = js("writeState", "", {"layers": layers, "basemap": basemap})
        state = js("readState", search)
        assert state["layers"] == sorted(layers), search
        assert state["basemap"] == basemap, search


def test_the_groups_are_the_panel_s():
    # map-url.js's groups, in the panel's order, are map.html's switches.
    with open(SCRIPT, encoding="utf-8") as fh:
        script = fh.read()
    with open(os.path.join(ROOT, "docs", "map.html"), encoding="utf-8") as fh:
        page = fh.read()
    groups = re.search(r"export const GROUPS = \[(.*?)\];", script, re.S)
    named = re.findall(r'"(\w+)"', groups.group(1))
    assert named == re.findall(r'data-group-switch="(\w+)"', page)
    basemaps = re.search(r"export const BASEMAPS = \[(.*?)\];", script)
    assert re.findall(r'"(\w+)"', basemaps.group(1)) == re.findall(
        r'data-basemap="(\w+)"', page
    )
    assert f'export const WATER = "{WATER}";' in script
