"""The land page's slice and maps: docs/land.html and docs/assets/land/.

"Sand, height and water" (four small maps) and "A slice through the district"
(part of TWDB's section line A-A', model row 239) are drawn from
docs/assets/land/, made by src/site/make_land.py. These check, on the
committed files: that the data is up to date with its record (the build's
own check, which needs no download); that section.json agrees with
stats.json, and both with the class rule run again on the 3D aquifer page's
committed well files; that only a report number and the driller's cleaned
words leave the build for each well; the files' sizes; that every figure the
two sections show is a data-figure mark the build fills, and no other number
is typed in them; that every drawing they show exists at its size, and that
Comment 9 is never a statement's only source; that land.js sets text only as
text and agrees with land.css on a phone held upright; and the wording. And,
on made-up records, the class rule (the first rock a driller names, with the
fact-check's three fixes), the logs, the figures' formats and what the check
calls stale. Standard library only, so the lint workflow runs these.
"""

from html.parser import HTMLParser
import json
import os
import re

import pytest

from src.site import make_site_data as msd
from src.site.land import draw
from src.site.land import params
from src.site.land import record
from src.site.land import rules
from src.site.land import verify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
DATA = os.path.join(DOCS, "assets", "land")
WELLS = os.path.join(DOCS, "assets", "aquifer", "wells")
SECTIONS = ("the-place", "the-slice")
DRAWINGS = (
    "map-elevation.svg",
    "map-sand.svg",
    "map-water.svg",
    "map-together.svg",
    "locator.svg",
    "section.svg",
)
# Text with a digit that is not a figure: the maps' and the steps' indices
# (skipped as elements), the notice's name and the 3D page's name.
NOT_FIGURES = ("Notice No. 243", "in 3D")
# A quotation in the page's curly quotes; one opening quote never reaches
# past the next.
QUOTED = re.compile(r"“[^“”]*”")
# The quotations whose figures are their source's, typed as it wrote them:
# Notice No. 243 (52579) and the petition (p. 11). Any other quotation is the
# site's own wording, and a number in it must be a figure the build fills.
QUOTED_FIGURES = (
    (
        "“to encompass the portions of the Hickory Sandstone Member geologic "
        "formation that are at 1,500 feet or higher.”"
    ),
    (
        "“the Hickory aquifer, Hickory Sands soils, and elevation at 1,500 "
        "feet or higher.”"
    ),
)


def own_words(text):
    """The text without the quotations whose figures are their source's."""
    return QUOTED.sub(lambda m: "" if m[0] in QUOTED_FIGURES else m[0], text)


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def load(*parts):
    return json.loads(read(*parts))


@pytest.fixture(scope="module")
def section():
    return load(DATA, "section.json")


@pytest.fixture(scope="module")
def stats():
    return load(DATA, "stats.json")


@pytest.fixture(scope="module")
def page():
    return read(DOCS, "land.html")


@pytest.fixture(scope="module")
def heads():
    out = []
    for path in record.wells_files():
        if os.path.basename(path).startswith("heads-"):
            out += load(path)
    return out


@pytest.fixture(scope="module")
def reports(heads):
    """A well's cleaned report by its uid, from the committed detail files."""
    cells = {h[0]: rules.detail_cell(h[1], h[2]) for h in heads}
    files = {}

    def report(uid):
        cell = cells[uid]
        if cell not in files:
            files[cell] = load(WELLS, f"detail-{cell}.json")
        return files[cell][uid]

    return report


# ------------------------------------------------------------------- the data
def test_the_committed_data_is_up_to_date():
    # What ./build.sh checks (make_land.py --check): no download needed.
    new = record.expected(record.read_manifest(), record.local_digests())
    old = record.read_record(DATA)
    assert record.differences(old, new, record.listing(DATA)) == [], (
        "run ./build.sh site-data"
    )


def test_the_manifest_pins_https_downloads():
    rows = record.read_manifest()
    names = [r["name"] for r in rows]
    for tile in {*params.LINE_TILES, *params.DEM_TILES}:
        assert tile in names, tile
    assert "twdb-gam" in names  # the 3D page's model, from its manifest
    for row in rows:
        assert row["url"].startswith("https://"), row["name"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["snapshot"]), row
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["fetched"]), row


def test_the_section_agrees_with_the_stats(section, stats):
    assert verify.agree(section, stats["figures"]) == []
    assert section["wells"], "no wells on the slice"
    assert len(section["district"]) >= 1


def test_the_section_is_drawable(section):
    cols, ground = section["cols"], section["ground"]
    assert [c[0] for c in cols[1:]] == [c[1] for c in cols[:-1]]
    assert cols[0][0] == 0 and cols[-1][1] == section["length_ft"]
    assert ground[0][0] == 0 and ground[-1][0] == section["length_ft"]
    assert [g[0] for g in ground] == sorted(g[0] for g in ground)
    tops = [g[1] for g in ground] + [section["rule_ft"]]
    assert section["z_base"] < min(c[3] for c in cols if c[3] is not None)
    assert section["z_top"] > max(tops)
    for name in ("district", "surface_hickory", "core"):
        for a, b in section[name]:
            assert 0 <= a < b <= section["length_ft"], (name, a, b)
    for w in section["wells"]:
        assert 0 <= w["s"] <= section["length_ft"], w["uid"]
        assert all(seg[0] < seg[1] <= w["depth"] for seg in w["log"])


def test_the_static_drawing_is_the_section_s(section):
    # section.svg is drawn from section.json alone (src/site/land/draw.py).
    from src.site.make_land import SECTION_LABEL  # noqa: PLC0415

    drawn = draw.Slice(section).svg(SECTION_LABEL) + "\n"
    assert read(DATA, "section.svg") == drawn, "run ./build.sh site-data"


def test_only_report_numbers_and_cleaned_words_leave_the_build(
    section, reports
):
    assert verify.privacy(section, reports) == []


def test_the_privacy_check_refuses_more_than_the_words():
    made_up = {
        "wells": [
            {
                "uid": "S1",
                "s": 0,
                "depth": 10,
                "ground": 1,
                "log": [[0, 10, 4, "dug by Smith Drilling Co."]],
                "OwnerName": "J. Smith",
            },
            {"uid": "Smith", "s": 0, "depth": 1, "ground": 1, "log": []},
        ]
    }
    problems = " ".join(verify.privacy(made_up, None))
    assert "OwnerName" in problems
    assert "not a report number" in problems
    assert "in LithologyDescription" in problems  # the scan's own finding


# The outlines each committed drawing is made of (draw.map_svg), as filled or
# stroked paths, and the dots of map 03.
OUTLINES = {
    "map-elevation.svg": 2,  # the high ground, the district
    "map-sand.svg": 3,  # the core, the sandstone, the district
    "map-water.svg": 3,  # the core, the sandstone, the district
    "map-together.svg": 4,  # high, sandstone, both, the district
    "locator.svg": 3,  # the sandstone, the core, the district
}
MADE_UP_MAPS = {
    "w": 540,
    "h": 500,
    "district": "M0,0L1,0L1,1Z",
    "hickory": "M0,0L2,0L2,2Z",
    "precambrian": "M3,3L4,3L4,4Z",
    "high": "M0,0L5,0L5,5Z",
    "together": "M0,0L1,0L1,1Z",
    "wells": [[1.0, 1.0, 2]],
    "line": [[0, 0], [5, 5]],
    "scale": 90,
}


def test_the_committed_maps_draw_every_outline():
    for name, count in OUTLINES.items():
        svg = read(DATA, name)
        # an outline's path is "Mx,yL...", a pattern's mark "M3 6h6..."
        assert len(re.findall(r'<path d="M[\d.]+,', svg)) == count, name
    assert read(DATA, "map-water.svg").count("<circle") > 1


@pytest.mark.parametrize("name", verify.MAP_OUTLINES)
def test_an_empty_outline_stops_the_generator(section, name):
    # An input that misses the frame leaves an outline empty: the generator
    # stops before it writes (verify.outlines()), and the drawing refuses it.
    maps = dict(MADE_UP_MAPS, **{name: ""})
    assert verify.outlines(MADE_UP_MAPS, section) == []
    assert name in " ".join(verify.outlines(maps, section))
    with pytest.raises(ValueError, match=name):
        for kind in ("high", "sand", "water", "together", "locator"):
            draw.map_svg(maps, kind, "made up")


def test_no_wells_or_an_empty_slice_stops_the_generator(section):
    maps = dict(MADE_UP_MAPS, wells=[])
    assert "no wells on the map" in " ".join(verify.outlines(maps, section))
    for part in ("ground", "cols", "district", "surface_hickory", "core"):
        empty = dict(section, **{part: []})
        problems = " ".join(verify.outlines(MADE_UP_MAPS, empty))
        assert f"the slice has no {part}" in problems


def test_every_file_is_within_its_budget():
    assert verify.sizes(DATA) == []


def test_the_slice_s_logs_are_classed_by_the_rule(section, reports):
    for w in section["wells"]:
        want = [
            [round(a, 1), round(b, 1), cls, words]
            for a, b, cls, words in rules.log_of(reports(w["uid"]), w["depth"])
        ]
        assert w["log"] == want, w["uid"]


def test_the_map_s_wells_are_classed_by_the_rule(heads, reports, stats):
    # Map 03 again, from the 3D page's committed heads and reports.
    west, south, east, north = params.FRAME
    found = dict.fromkeys(params.MAP_DRAW_ORDER, 0)
    for h in heads:
        if not (west <= h[1] <= east and south <= h[2] <= north):
            continue
        if h[6] == rules.UNLOGGED:
            continue
        pick = rules.water_interval(
            rules.log_of(reports(h[0]), h[3]), h[7], h[8], h[9]
        )
        found[params.CLASSES[h[6] if pick is None else pick[2]]] += 1
    assert found == stats["counts"]["map_classes"]
    assert sum(found.values()) == stats["figures"]["wells_on_map"]


def test_every_well_class_drawn_has_a_colour_and_a_key(page):
    assert len(params.CLASS_COLOURS) == len(params.CLASSES)
    keys = {
        "Sandstone",
        "Sand",
        "Granite",
        "Gneiss, schist or other metamorphic rock",
        "Limestone or dolomite",
        "Other",
    }
    for key in keys:
        assert page.count(f"</span>{key}</span>") == 1, key  # map 03
        assert page.count(f"</span>{key}</li>") == 1, key  # step 5


# -------------------------------------------------------------- the class rule
@pytest.mark.parametrize(
    ("text", "cls"),
    [
        ("shale w/ lime stks", "other"),
        ("lime w/ shale stks", "limestone"),
        ("Whitelime", "limestone"),
        ("Dark Sandy Limestone", "limestone"),
        ("gray lime w/ sandstone streaks", "limestone"),
        ("Blue Clay W/ Lime Streaks", "other"),
        ("Elenburger", "other"),
        ("sand", "sand"),
        ("Brown Sandstone", "sandstone"),
        ("Hickory Various Colors", "sandstone"),
        ("Gray Granite", "granite"),
        ("Weathered Red Metamorphic", "metamorphic"),
        ("Topsoil", "other"),
        ("sandy clay", "other"),
        ("", "other"),
        (None, "other"),
        # the fact-check's three fixes (N16, N17)
        ("light brown dolomite", "limestone"),
        ("silty sand w/sandstone; brown", "sand"),
        ("Brown clayey sand.", "sand"),
        ("gravelly sand", "sand"),
        ("clay and sand", "other"),
        ("silt", "other"),
    ],
)
def test_the_first_rock_named_is_the_class(text, cls):
    assert params.CLASSES[rules.classify(text)] == cls


def test_a_log_is_cut_at_the_well_s_depth_and_sorted():
    report = {
        "Lithology": [
            {
                "TopDepth": "20",
                "BottomDepth": "205",
                "LithologyDescription": "gray granite",
            },
            {
                "TopDepth": "0",
                "BottomDepth": "20",
                "LithologyDescription": " brown sandstone ",
            },
            {
                "TopDepth": "205",
                "BottomDepth": "300",
                "LithologyDescription": "granite",
            },
            {
                "TopDepth": "x",
                "BottomDepth": "5",
                "LithologyDescription": "soil",
            },
        ]
    }
    assert rules.log_of(report, 200) == [
        [0.0, 20.0, 2, "brown sandstone"],
        [20.0, 200, 0, "gray granite"],
    ]


def test_the_water_interval_is_the_3d_page_s():
    segs = [[0, 20, 2, "sand stone"], [20, 205, 0, "granite"]]
    assert rules.water_interval(segs, 10, 15, 0) == segs[0]
    assert rules.water_interval(segs, 300, 310, 0) == segs[1]  # no overlap
    assert rules.water_interval(segs, None, None, 1) == segs[1]
    assert rules.water_interval([], None, None, 2) is None


# ---------------------------------------------------------------- the record
def test_a_changed_snapshot_or_parameter_is_stale():
    manifest = record.read_manifest()
    local = record.local_digests()
    old = record.expected(manifest, local, {"stats.json": 1})
    moved = [dict(r) for r in manifest]
    moved[0]["sha256"] = "0" * 64
    assert record.differences(old, record.expected(moved, local))
    changed = json.loads(json.dumps(old))
    changed["parameters"]["ve"] = params.VE + 1
    assert record.differences(changed, record.expected(manifest, local))
    assert record.differences(None, record.expected(manifest, local))


def test_the_record_pins_the_3d_page_s_wells():
    local = record.local_digests()
    assert local["aquifer-wells"]["files"] > 2
    assert local["aquifer-wells"]["sha256"].startswith("sha256:")
    assert set(record.LOCAL) <= set(local)


# ------------------------------------------------------------------ the page
class Sections(HTMLParser):
    """The text, figures, citations and images of the two new sections."""

    SKIP = ("lnd-map-index", "lnd-step-index", "geo-cite")
    VOID = ("img", "br", "source", "meta", "link", "input", "hr", "wbr")

    def __init__(self):
        """Starts outside both sections."""
        super().__init__(convert_charrefs=True)
        self.stack = []  # (tag, skipped) of the open elements inside
        self.text = []
        self.figures = []
        self.cites = []
        self.images = []

    def skipped(self):
        """Whether an open element is one whose text is not read."""
        return any(skip for _, skip in self.stack)

    def handle_starttag(self, tag, attrs):
        """Tracks the sections, the skipped elements and the marks."""
        a = dict(attrs)
        inside = bool(self.stack)
        if not inside and not (tag == "section" and a.get("id") in SECTIONS):
            return
        if tag == "img":
            self.images.append(a)
        if tag in self.VOID:
            return
        cls = (a.get("class") or "").split()
        self.stack.append(
            (tag, "data-figure" in a or any(c in self.SKIP for c in cls))
        )
        if "data-figure" in a:
            self.figures.append(a["data-figure"])
        if tag == "sup" and "geo-cite" in cls:
            self.cites.append([])
        href = a.get("href") or ""
        if tag == "a" and href.startswith("#source-"):
            self.cites[-1].append(int(href.removeprefix("#source-")))

    def handle_endtag(self, tag):
        """Closes the innermost open element of that tag."""
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        """Keeps the sections' text outside the skipped elements."""
        if self.stack and not self.skipped():
            self.text.append(data)


@pytest.fixture(scope="module")
def sections(page):
    parser = Sections()
    parser.feed(page)
    parser.close()
    return parser


def test_the_page_loads_its_styles_and_script(page):
    # Version stamps (?v=..., #138) aside.
    css = [
        href.split("?")[0]
        for href in re.findall(r'<link rel="stylesheet" href="([^"]+)"', page)
    ]
    assert css.index("assets/land.css") > css.index("assets/timeline.css")
    assert re.search(
        r'<script src="assets/land\.js(\?v=[0-9a-f]+)?" defer>', page
    )


def test_both_sections_come_before_the_timeline(page):
    at = [page.index(f'id="{s}"') for s in (*SECTIONS, "deep-time")]
    assert at == sorted(at)
    assert "geologic-section" not in page
    assert "CONCEPTUAL SECTION" not in page


def test_every_figure_shown_is_the_build_s(sections, stats, page):
    shown = {f for f in sections.figures if f.startswith("land_")}
    built = {f"land_{name}" for name in stats["figures"]}
    assert shown <= built, shown - built
    # every other figure is in the sources: the wells' date (source 7) and
    # the 3DEP tiles and their years (source 3)
    cited = {"land_wells_snapshot", "land_dem_years", "land_dem_tiles"}
    assert built - shown == cited
    for name in cited:
        assert page.count(f'data-figure="{name}"') == 1, name


def test_no_number_is_typed_in_the_sections(sections):
    text = own_words(re.sub(r"\s+", " ", " ".join(sections.text)))
    for allowed in NOT_FIGURES:
        text = text.replace(allowed, "")
    assert not re.findall(r".{0,30}\d.{0,30}", text)


@pytest.mark.parametrize(
    "text",
    [
        "the “about 1,500 feet” of ground",  # a number typed in quotes
        "“a quote never closed, 2,240 feet “then another.”",  # unbalanced
        "drawn “to encompass the portions at 1,500 feet or higher.”",  # cut
    ],
)
def test_a_number_in_the_site_s_own_quotes_is_typed(text):
    assert re.search(r"\d", own_words(text))


def test_the_source_s_quotations_keep_their_figures():
    for quotation in QUOTED_FIGURES:
        assert not re.search(r"\d", own_words(f"so: {quotation}"))


def test_comment_9_is_never_the_only_source(page, sections):
    (c9,) = re.findall(
        r'<li id="source-(\d+)">[^<]*<cite>Petitioners’ Response', page
    )
    groups = [g for g in sections.cites if int(c9) in g]
    assert groups, "Comment 9 is not cited"
    assert all(len(g) >= 2 for g in groups), groups


def test_every_drawing_exists_at_its_size(sections):
    srcs = [img["src"] for img in sections.images]
    assert sorted(srcs) == sorted(f"assets/land/{n}" for n in DRAWINGS)
    for img in sections.images:
        head = read(DOCS, img["src"])[:400]
        w = float(re.search(r'width="([\d.]+)"', head)[1])
        h = float(re.search(r'height="([\d.]+)"', head)[1])
        assert (int(img["width"]), int(img["height"])) == (round(w), round(h))
        assert "alt" in img, img["src"]
        assert not re.search(r"\d", img["alt"]), img["alt"]


@pytest.mark.parametrize("name", DRAWINGS)
def test_every_drawing_stands_alone(name):
    svg = read(DATA, name)
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    for ref in re.findall(r"url\(#([\w-]+)\)", svg):
        assert f'id="{ref}"' in svg, (name, ref)
    assert "'Source Sans 3'" in svg  # a family name with a digit, quoted


def test_land_figures_are_formatted_and_dated(tmp_path):
    folder = tmp_path / "assets" / "land"
    folder.mkdir(parents=True)
    figures = {"wells_on_map": 2594, "line_mi": 35.25, "snap": "2026-10-16"}
    (folder / "stats.json").write_text(json.dumps({"figures": figures}))
    assert msd.land_figures(str(tmp_path)) == {
        "land_wells_on_map": ("2,594", None),
        "land_line_mi": ("35.25", None),
        "land_snap": ("October 16, 2026", "2026-10-16"),
    }
    (folder / "stats.json").write_text(json.dumps({"figures": {"x": True}}))
    with pytest.raises(SystemExit):
        msd.land_figures(str(tmp_path))
    assert msd.land_figures(str(tmp_path / "none")) == {}


# --------------------------------------------------------- the script, styles
def test_the_page_draws_by_the_generator_s_colours_and_layers(section):
    # land.js reads the class colours and the model's layers from
    # section.json (checked against the parameters by verify.agree());
    # land.css keys the classes in the same colours.
    js = read(DOCS, "assets", "land.js")
    for colour in params.CLASS_COLOURS:
        assert colour.lower() not in js.lower(), colour
    for name in ("colours", "hickory_layer", "precambrian_layer"):
        assert f"S.{name}" in js, name
    assert not re.search(r"c\[5\] *(?:<|===) *\d", js)
    css = read(DOCS, "assets", "land.css")
    keyed = dict(re.findall(r"--lnd-c(\d):(#[0-9a-fA-F]{6})", css))
    drawn = {
        str(i) for i, name in enumerate(params.CLASSES) if name != "unlogged"
    }
    assert set(keyed) == drawn, keyed
    for i, colour in keyed.items():
        assert colour.lower() == params.CLASS_COLOURS[int(i)].lower(), i
    assert section["colours"] == list(params.CLASS_COLOURS)


def test_the_script_sets_text_as_text():
    js = read(DOCS, "assets", "land.js")
    for sink in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "createContextualFragment",
        "DOMParser",
        "eval(",
        "Function(",
        "srcdoc",
    ):
        assert sink not in js, sink
    assert "textContent" in js
    assert 'fetch("assets/land/section.json")' in js


def test_the_script_and_styles_agree_on_a_phone_held_upright():
    js = read(DOCS, "assets", "land.js")
    css = re.sub(r"/\*.*?\*/", "", read(DOCS, "assets", "land.css"), flags=re.S)
    found = re.search(r"var tall = window\.matchMedia\(([^;]*)\);", js)
    assert found
    query = re.sub(r"\s+", "", "".join(re.findall(r'"([^"]*)"', found[1])))
    assert "orientation:portrait" in query
    sticky = {
        re.sub(r"\s+", "", q)
        for q in re.findall(r"@media([^{]*max-width:999px[^{]*)\{", css)
    }
    assert sticky == {query}, (sticky, query)


# The timeline's classes the slice reuses (land.js makes them).
REUSED = ("geo-progress", "geo-step", "geo-count", "geo-hint", "geo-live")


def test_the_slice_sets_the_timeline_s_variables_it_uses():
    # timeline.css sets its variables on its own section (.geo), which the
    # slice's (.lnd-sec) is not inside: whatever its rules for the reused
    # classes read, land.css sets for the slice, with the timeline's value
    # (an unset one would leave the progress marks not yet reached clear).
    def variables(css, selector):
        block = re.search(re.escape(selector) + r"\{([^}]*)\}", css)
        assert block, selector
        return dict(re.findall(r"(--[\w-]+):([^;}]+)", block[1]))

    timeline = re.sub(
        r"/\*.*?\*/", "", read(DOCS, "assets", "timeline.css"), flags=re.S
    )
    land = re.sub(
        r"/\*.*?\*/", "", read(DOCS, "assets", "land.css"), flags=re.S
    )
    used = set()
    for selector, decls in re.findall(r"([^{}]+)\{([^{}]*)\}", timeline):
        if any(re.search(rf"\.{c}\b", selector) for c in REUSED):
            used |= set(re.findall(r"var\((--geo-[\w-]+)\)", decls))
    assert "--geo-scale" in used  # the marks not yet reached
    theirs = variables(timeline, ".geo")
    ours = variables(land, ".lnd-place,.lnd-sec")
    for name in used:
        assert ours.get(name) == theirs[name], name


def test_the_styles_use_their_own_classes_and_the_timeline_s_controls():
    # Beside its own lnd- classes: the timeline's buttons and count, which
    # the slice reuses, and the site's eyebrow and reading body, only as the
    # sections' context.
    css = re.sub(r"/\*.*?\*/", "", read(DOCS, "assets", "land.css"), flags=re.S)
    names = set(re.findall(r"\.(-?[A-Za-z_][\w-]*)", css))
    reused = {"geo-step", "geo-count", "eyebrow", "reading-body"}
    assert names
    assert all(n.startswith("lnd-") or n in reused for n in names), names


@pytest.mark.parametrize(
    "path",
    [
        os.path.join(DOCS, "assets", "land.js"),
        os.path.join(DOCS, "assets", "land.css"),
        *(os.path.join(DATA, n) for n in DRAWINGS),
    ],
    ids=os.path.basename,
)
def test_the_wording(path):
    text = read(path)
    assert not re.search(r"Hickory Sandstone(?! Member)", text), path
    assert not re.search(r"Hickory Sands\b(?! District)", text), path
    assert not re.search(r"\bagreed\b", text, re.IGNORECASE), path
