"""src/publish/agol_dryrun_checks.py (issue #58): the checks on everything the publish would send to ArcGIS Online pass on
a dry run of the current build, and each fails on a fault planted in it: a hosted layer left editable (#25), plain CC0 on
TTB's text (#11), a phone element without its desktop twin and no phone view (#49), a link to an item not in the group
or titled otherwise, a caption too long for its indicator (#45), a link cell that wraps (#47), the quadrangles' band
legend and raw pop-up (#46), a stray web map layer, metadata gaps (#31), credits (#30), descriptions (#29, #34), the
quadrangle editions (#44), the wording rules, a private group, a new or retitled item.
The dry run's files are tests/fixtures/publish/dry-run/ (target/publish/ from ./build.sh publish-dry-run: copy them
there again after changing what the publish sends) and the group's item list tests/fixtures/publish/agol-items.json.
Standard library only, so the lint workflow runs these; the last test, marked build, runs the whole dry run on a build.
"""

import copy
import json
import os
import re
import subprocess
import sys

import pytest

from src.publish import agol_dryrun_checks as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "publish")


@pytest.fixture(scope="module")
def bundle():
    b = {
        k: json.load(
            open(os.path.join(FIX, "dry-run", k + ".json"), encoding="utf-8")
        )
        for k in C.FILES
        if k != "item-list"
    }
    b["item-list"] = json.load(
        open(os.path.join(FIX, "agol-items.json"), encoding="utf-8")
    )
    return b


def problems(b, name):
    bad = []
    dict(C.CHECKS)[name](b, bad.append)
    return bad


def test_every_check_passes_on_the_current_build(bundle):
    lines = []
    assert C.run(bundle, lines.append) == [], "\n".join(lines)


# ---------------------------------------------------------------- where to plant
def item(
    b, number
):  # "1a", or the start of a title up to a space or comma ("5a ... - Fly Gap")
    return next(
        it
        for it in b["items"]
        if it["title"].startswith((number + " ", number + ","))
    )


def widget(b, view, kind, name):
    return next(
        w
        for w in b["dashboard"][view]["widgets"]
        if w["type"] == kind and w["name"] == name
    )


def op(b, lid):
    return next(
        lyr
        for lyr in C.layers(b["webmap"]["operationalLayers"])
        if lyr.get("id") == lid
    )


def caption(b, view, name, text):
    widget(b, view, "indicatorWidget", name)["defaultSettings"]["topSection"][
        "textInfo"
    ]["text"] = text


def edit_text(b, name, old, new, count=1):
    w = widget(b, "desktopView", "richTextWidget", name)
    assert old in w["text"], old
    w["text"] = w["text"].replace(old, new, count)


def first_item_link(b, new_id):
    w = widget(b, "desktopView", "richTextWidget", "Documents")
    w["text"] = re.sub(
        r"item\.html\?id=[0-9a-f]{32}",
        "item.html?id=" + new_id,
        w["text"],
        count=1,
    )


def first_link_text(b, text):
    w = widget(b, "desktopView", "richTextWidget", "Documents")
    w["text"] = re.sub(
        r'(<a href="[^"]*item\.html[^"]*"[^>]*>)[^<]*(</a>)',
        r"\g<1>" + text + r"\g<2>",
        w["text"],
        count=1,
    )


def props(b, number, **kw):
    item(b, number)["properties"].update(kw)


def retitle(b, number, old, new):
    it = item(b, number)
    it["title"] = it["title"].replace(old, new)
    it["properties"]["snippet"] = it["properties"]["snippet"].replace(old, new)


ABOUT = lambda b: b["facts"]["about"][0]
FAULTS = {  # fault: (the check that must fail, the plant, what its problem says)
    "a hosted layer with Create (#25)": (
        "security",
        lambda b: b["services"][item(b, "4k")["title"]]["definition"].update(
            capabilities="Create,Delete,Query,Update,Editing"
        ),
        r"not read-only",
    ),
    "a hosted layer with Sync": (
        "security",
        lambda b: b["services"][item(b, "4b")["title"]]["definition"].update(
            capabilities="Query,Extract,Sync"
        ),
        r"not read-only",
    ),
    "a hosted layer the publish never locks": (
        "security",
        lambda b: b["services"].pop(item(b, "4o")["title"]),
        r"does not set read-only",
    ),
    "plain CC0 on 1a, TTB's text (#11)": (
        "licences",
        lambda b: props(
            b,
            "1a",
            licenseInfo=C.CC0
            + " (public domain dedication): no rights reserved.",
        ),
        r"does not name 'U\.S\. Government work",
    ),
    "plain CC0 on the web map (#30)": (
        "licences",
        lambda b: props(
            b, "4a", licenseInfo=C.CC0 + " (public domain dedication)."
        ),
        r"does not name",
    ),
    "CC0 on TTB's own notice": (
        "licences",
        lambda b: props(
            b,
            "2b",
            licenseInfo="U.S. Government work (public domain). " + C.CC0,
        ),
        r"TTB's own work licensed CC0",
    ),
    "credits without Esri on the web map (#30)": (
        "licences",
        lambda b: props(b, "4a", accessInformation="Dan McLaughlin; TTB; USGS"),
        r"credits do not name Esri",
    ),
    "a phone element without its desktop twin (#49)": (
        "dashboard",
        lambda b: b["dashboard"]["elementMappings"].popitem(),
        r"check_views",
    ),
    "no phone view (#49)": (
        "dashboard",
        lambda b: b["dashboard"].pop("mobileView"),
        r"no mobileView",
    ),
    "a phone action aimed at a desktop element": (
        "dashboard",
        lambda b: b["dashboard"]["mobileView"]["widgets"].__setitem__(
            0,
            {
                **b["dashboard"]["mobileView"]["widgets"][0],
                "id": b["dashboard"]["desktopView"]["widgets"][0]["id"],
            },
        ),
        r"check_views",
    ),
    "a link to an item not in the group": (
        "dashboard",
        lambda b: first_item_link(b, "f" * 32),
        r"not in the group's item list",
    ),
    "a link titled as another item": (
        "dashboard",
        lambda b: first_link_text(b, "Boundary description as agreed"),
        r"is not in the title",
    ),
    "an item the dashboard no longer links": (
        "dashboard",
        lambda b: [
            edit_text(
                b, "USGS quadrangles", "GeoTIFF</a>", "GeoTIFF</span>", 99
            )
        ],
        r"does not link",
    ),
    "a caption too long for its indicator (#45)": (
        "dashboard",
        lambda b: caption(
            b,
            "desktopView",
            "Big differences",
            "Big differences from the Map Explorer polygon",
        ),
        r"its width holds 3\d\b",
    ),
    "a phone caption too long (#45)": (
        "dashboard",
        lambda b: caption(
            b,
            "mobileView",
            "Steps worded differently from Notice No. 243",
            "Steps worded differently",
        ),
        r"its width holds 20",
    ),
    "a quadrangle link cell that wraps (#47)": (
        "dashboard",
        lambda b: edit_text(
            b, "USGS quadrangles", "white-space:nowrap", "white-space:normal"
        ),
        r"may wrap",
    ),
    "the dashboard's map is another map": (
        "dashboard",
        lambda b: widget(b, "mobileView", "mapWidget", "Map").update(
            itemId="0" * 32
        ),
        r"not the web map",
    ),
    "the quadrangles' band legend (#46)": (
        "web map",
        lambda b: op(b, "usgs-quads").update(showLegend=True),
        r"showLegend",
    ),
    "the quadrangles' raw pop-up (#46)": (
        "web map",
        lambda b: op(b, "usgs-quads").pop("popupInfo"),
        r"no pop-up",
    ),
    "years with a thousands separator (#46)": (
        "web map",
        lambda b: op(b, "usgs-quads")["popupInfo"]["fieldInfos"][2][
            "format"
        ].update(digitSeparator=True),
        r"thousands separator",
    ),
    "the quadrangles' time filter": (
        "web map",
        lambda b: op(b, "usgs-quads").update(timeAnimation=True),
        r"time filter",
    ),
    "a layer from an unknown service": (
        "web map",
        lambda b: b["webmap"]["operationalLayers"].append(
            {
                "id": "x",
                "title": "x",
                "url": "https://example.com/arcgis/rest/services/x/FeatureServer/0",
                "layerType": "ArcGISFeatureLayer",
            }
        ),
        r"known service",
    ),
    "a layer of an item not in the group": (
        "web map",
        lambda b: op(b, "hsd-rings").update(itemId="e" * 32),
        r"not in the group's item list",
    ),
    "no culture (#31)": (
        "metadata",
        lambda b: props(b, "2a", culture=""),
        r"culture",
    ),
    "no docket tag (#31)": (
        "metadata",
        lambda b: props(
            b, "4d", tags="Hickory Sands District,AVA,TTB,Notice No. 243"
        ),
        r"no tag 'TTB-2026-0005'",
    ),
    "no extent on a quadrangle (#31)": (
        "metadata",
        lambda b: next(
            it for it in b["items"] if it["title"].startswith("5b ")
        )["properties"].pop("extent"),
        r"extent",
    ),
    "an extent far from the AVA": (
        "metadata",
        lambda b: props(b, "4c", extent=[[-80.0, 40.0], [-79.0, 41.0]]),
        r"extent",
    ),
    "no credits": (
        "metadata",
        lambda b: props(b, "3a", accessInformation=""),
        r"no accessInformation",
    ),
    "the wrong group category": (
        "metadata",
        lambda b: item(b, "2c").update(
            group_category="/Categories/1 Boundary description (proposed text)"
        ),
        r"group category",
    ),
    "a stub summary (#34)": (
        "descriptions",
        lambda b: props(b, "1b", snippet="The proposed text as a Word file."),
        r"stub summary",
    ),
    "a boilerplate description (#34)": (
        "descriptions",
        lambda b: props(b, "4e", description=ABOUT(b)),
        r"beyond the shared opening",
    ),
    "the CSV described as the PDF (#29)": (
        "descriptions",
        lambda b: props(
            b, "1d", description=item(b, "1a")["properties"]["description"]
        ),
        r"CSV file",
    ),
    "TTB's notice prepared by the petitioner (#29)": (
        "descriptions",
        lambda b: props(
            b,
            "2b",
            description=ABOUT(b) + item(b, "2b")["properties"]["description"],
        ),
        r"prepared by the petitioner",
    ),
    "exports without Web Mercator (#29)": (
        "descriptions",
        lambda b: props(
            b,
            "4b",
            description=item(b, "4b")["properties"]["description"].replace(
                "Web Mercator", "its own projection"
            ),
        ),
        r"Web Mercator",
    ),
    "a quadrangle titled without its revision (#44)": (
        "quad titles",
        lambda b: retitle(
            b,
            "5a USGS quadrangle with the boundary (GeoPDF) - Fly Gap",
            "(1962, photorevised 1982)",
            "(1962)",
        ),
        r"as paragraph \(b\) cites it",
    ),
    "a quadrangle missing": (
        "quad titles",
        lambda b: b["items"].remove(
            item(b, "5b USGS quadrangle with the boundary (GeoTIFF) - Voca")
        ),
        r"0 5b items for Voca",
    ),
    "agreed": (
        "wording",
        lambda b: props(
            b,
            "4a",
            description=item(b, "4a")["properties"]["description"]
            + "<p>The agreed boundary.</p>",
        ),
        r"agreed",
    ),
    "TTB's published polygon": (
        "wording",
        lambda b: op(b, "hsd-ttb").update(title="TTB's published polygon"),
        r"published polygon",
    ),
    "bare Hickory Sandstone": (
        "wording",
        lambda b: edit_text(
            b,
            "The change near Grit",
            "Hickory Sandstone Member formation",
            "Hickory Sandstone",
        ),
        r"Hickory Sandstone",
    ),
    "a private group": (
        "group",
        lambda b: b["group"].update(access="private"),
        r"not public",
    ),
    "a group description without the dashboard": (
        "group",
        lambda b: b["group"].update(
            description=b["group"]["description"].replace(
                "item.html", "group.html", 1
            )
        ),
        r"does not link 0 Dashboard",
    ),
    "a retitled item": (
        "items",
        lambda b: item(b, "3b").update(title="3b Changes side by side (DOCX)"),
        r"not in the group's item list",
    ),
    "an item the publish no longer makes": (
        "items",
        lambda b: b["items"].remove(item(b, "2c")),
        r"no longer makes it",
    ),
}


@pytest.mark.parametrize("fault", FAULTS)
def test_a_planted_fault_fails_its_check(bundle, fault):
    check, plant, says = FAULTS[fault]
    b = copy.deepcopy(bundle)
    assert problems(b, check) == []
    plant(b)
    bad = problems(b, check)
    assert any(re.search(says, x) for x in bad), bad


@pytest.mark.parametrize(
    "title, number",
    [
        (
            "0 Dashboard - the proposed boundary and everything in this group",
            "0 Dashboard",
        ),
        ("1a Boundary description as proposed (PDF)", "1a"),
        (
            "5a USGS quadrangle with the boundary (GeoPDF) - Fly Gap, TX (1962, photorevised 1982)",
            "5a Fly Gap",
        ),
    ],
)
def test_item_numbers(title, number):
    assert C.code(title) == number


def test_link_text_runs():
    """a phone button's title and note are two pieces of text, each in the item's title; not run together (#49)"""
    assert C.runs(
        '<strong>Read me first</strong><br><span style="x">what is in this group, and the license</span>'
    ) == ["Read me first", "what is in this group, and the license"]
    assert C.runs("TTB&#x27;s text") == ["TTB's text"]


def test_width_shares():
    stack = lambda o, els: {
        "type": "stackLayoutElement",
        "orientation": o,
        "id": "s",
        "width": 1,
        "height": 1,
        "elements": els,
    }
    leaf = lambda i, w=1, h=1: {
        "type": "itemLayoutElement",
        "id": i,
        "width": w,
        "height": h,
    }
    v = {
        "layout": {
            "rootElement": stack(
                "col",
                [
                    {
                        **stack(
                            "row",
                            [
                                stack(
                                    "col", [leaf("a", 1 / 3), leaf("b", 2 / 3)]
                                ),
                                leaf("c"),
                            ],
                        ),
                        "width": 0.3,
                    },
                    leaf("map", 0.7),
                ],
            )
        }
    }
    assert C.width_shares(v) == pytest.approx(
        {"a": 0.1, "b": 0.2, "c": 0.3, "map": 0.7}
    )


@pytest.mark.build
def test_the_dry_run_of_the_build(tmp_path):
    """the whole dry run on the build's outputs (HSD_WORK or target/work), as ./build.sh publish-dry-run runs it"""
    work = os.environ.get("HSD_WORK") or os.path.join(ROOT, "target", "work")
    if not os.path.exists(os.path.join(work, "agreed-steps.json")):
        pytest.skip(f"no build outputs in {work}: run ./build.sh first")
    pytest.importorskip(
        "arcgis",
        reason="the publish scripts import Esri's arcgis package (requirements.txt)",
    )
    r = subprocess.run(
        [
            sys.executable,
            "-E",
            "-s",
            "-B",
            os.path.join(ROOT, "src", "publish", "agol_dryrun.py"),
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "HSD_WORK": work},
    )
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    assert "dry-run checks: 10 of 10 passed" in r.stdout
