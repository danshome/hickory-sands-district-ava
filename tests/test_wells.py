"""The land page's three wells: docs/land.html#three-wells, docs/assets/wells/.

"Three wells, three rocks" is drawn and counted by src/site/make_wells.py.
These check, on the committed files: that the data and the drawings are up
to date with their record (the build's own check, which needs no download);
that every figure the section shows is a data-figure mark the build fills,
and no other number is typed in it but its sources' own; that water enters
each drawn well only through a screen or open hole; that every label of the
wide drawings a phone shows is at least 11 px on a 360 px phone; that no
position of the granite example, nor a person's name or address field,
leaves the build; that every source the section names is in the list, and
Setlur et al. is not; and that wells.js sets text only as text. And, on the
cited constants, that the cost and energy arithmetic gives the prototype's
checked values. Standard library only, so the lint workflow runs these.
"""

from html.parser import HTMLParser
import json
import os
import re

import pytest

from src.site import make_site_data as msd
from src.site.wells import costs
from src.site.wells import params
from src.site.wells import record

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
DATA = os.path.join(DOCS, "assets", "wells")
# The figures typed as their sources wrote them (a model's storativity and
# recharge, a district plan's saturated thickness, Hunt's medians, the
# petitioners' response's yields), and the names, dates and references that
# hold digits but are not figures.
SOURCE_FIGURES = (
    "a few feet to about 100 feet",
    "storativity 0.001, against 0.09–0.3",
    "0.18 inches a year, against 1.09",
    "medians of 120 feet deep, 11 gpm and 23 feet to water",
    "yields of 30 gpm (all uses) and 200 gpm (irrigation)",
    "Carbon-14",
    "July 2026",
    "January 2023",
    "September 2023",
    "2026 Region F",
    "2026 Region K",
    "2023 Census",
    "Table 14, p. 30",
    "Table 16, p. 32",
    "Table 14, public supply, p. 30",
    "Table 16, irrigation, p. 32",
    "Comment 8",
    "1:500,000",
    "100% efficiency",
    "0-gpm",
    "step 04",
    "Step 05",
    "/ 06",
)


def read(*parts):
    """A file's text."""
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def page():
    return read(DOCS, "land.html")


@pytest.fixture(scope="module")
def stats():
    return json.loads(read(DATA, "stats.json"))


@pytest.fixture(scope="module")
def section(page):
    start = page.index('<section class="lnd-sec w-sec')
    return page[start : page.index("</section>", start)]


class Text(HTMLParser):
    """The section's text outside marks, citations, indexes and drawings."""

    SKIP = ("geo-cite", "lnd-step-index", "w-count", "w-defs")

    def __init__(self):
        """Starts with nothing read."""
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.text = []
        self.figures = []
        self.cites = []

    def handle_starttag(self, tag, attrs):
        """Tracks the skipped elements, the marks and the citations."""
        a = dict(attrs)
        if tag in ("br", "img", "path", "rect", "circle"):
            return
        cls = (a.get("class") or "").split()
        skip = (
            tag == "svg"
            or "data-figure" in a
            or bool(set(cls) & set(self.SKIP))
        )
        self.stack.append((tag, skip))
        if "data-figure" in a:
            self.figures.append(a["data-figure"])
        if tag == "sup" and "geo-cite" in cls:
            self.cites.append([])
        href = a.get("href") or ""
        if tag == "a" and href.startswith("#source-") and self.cites:
            self.cites[-1].append(int(href.removeprefix("#source-")))

    def handle_endtag(self, tag):
        """Closes the innermost open element of that tag."""
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        """Keeps the text outside the skipped elements."""
        if not any(skip for _, skip in self.stack):
            self.text.append(data)


@pytest.fixture(scope="module")
def parsed(section):
    parser = Text()
    parser.feed(section)
    parser.close()
    return parser


# ------------------------------------------------------------------- the data
def test_the_committed_data_and_drawings_are_up_to_date(page):
    # What ./build.sh checks (make_wells.py --check): no download needed.
    new = record.expected(record.read_manifest(), record.local_digests())
    old = record.read_record(DATA)
    stale = record.differences(old, new, record.listing(DATA), page)
    assert stale == [], "run ./build.sh site-data"


def test_the_manifest_pins_https_downloads():
    rows = record.read_manifest()
    names = {r["name"] for r in rows}
    assert {"usgs-sgmc-texas", "twdb-sdr", "census-counties"} <= names
    for row in rows:
        assert row["url"].startswith("https://"), row["name"]
        assert re.fullmatch(r"[0-9a-f]{64}", row["sha256"]), row["name"]


def test_every_constant_has_its_source():
    data = json.loads(read(ROOT, "resources", "wells", "constants.json"))
    for name, item in data.items():
        if name == "about":
            continue
        assert set(item) == {"value", "source"}, name
        assert len(item["source"]) > 20, name


def test_the_page_has_every_drawing_slot(page):
    assert set(record.blocks(page)) == set(params.SLOTS)


# ------------------------------------------------------------------ the text
def test_every_figure_shown_is_the_build_s(parsed, page, stats):
    built = {f"wells_{name}" for name in stats["figures"]}
    shown = {f for f in parsed.figures if f.startswith("wells_")}
    in_sources = set(re.findall(r'data-figure="(wells_[a-z_]+)"', page))
    assert shown | in_sources <= built, (shown | in_sources) - built
    figs = msd.land_figures(DOCS)
    for name in in_sources:
        assert name in figs


def test_no_number_is_typed_but_the_sources(parsed):
    text = re.sub(r"\s+", " ", " ".join(parsed.text))
    text = re.sub(r"“[^“”]*”", "", text)  # quotations keep their figures
    for allowed in SOURCE_FIGURES:
        text = text.replace(allowed, "")
    assert not re.findall(r".{0,30}\d.{0,30}", text)


def test_every_source_cited_is_listed(parsed, page):
    listed = {int(n) for n in re.findall(r'<li id="source-(\d+)">', page)}
    cited = {n for group in parsed.cites for n in group}
    assert cited <= listed, cited - listed
    for n in range(27, max(listed) + 1):
        assert n in cited, f"source {n} is never cited by the wells"
    assert "Setlur" not in page


def test_the_drawings_name_listed_sources(section, page):
    for n in set(re.findall(r'data-src="(\d+)"', section)):
        assert f'<li id="source-{n}">' in page, n


# -------------------------------------------------------------- the drawings
def svgs(section):
    """Every drawing: (class, viewBox width, markup)."""
    return [
        (m[1], float(m[2]), m[0])
        for m in re.finditer(
            r'<svg class="(w-f-[a-z]+)" viewBox="0 0 ([\d.]+) [\d.]+".*?</svg>',
            section,
            re.DOTALL,
        )
    ]


def test_every_well_is_drawn_tall_and_wide(section):
    found = svgs(section)
    assert [c for c, _, _ in found].count("w-f-wide") == 4
    assert [c for c, _, _ in found].count("w-f-tall") == 4


def test_labels_on_a_phone_are_large_enough(section):
    inner = params.PHONE_PX * (1 - 2 * params.GUTTER)
    for cls, width, svg in svgs(section):
        if cls != "w-f-wide":
            continue
        for size in re.findall(r'<text[^>]*font-size="([\d.]+)"', svg):
            assert float(size) * inner / width >= params.MIN_LABEL_PX, size
    scale = section[section.index('<figure class="w-scale"') :]
    width = float(re.search(r'viewBox="0 0 ([\d.]+)', scale)[1])
    shown = min(inner, 360)  # .w-scale's max-width
    for size in re.findall(r'<text[^>]*font-size="([\d.]+)"', scale[:4000]):
        assert float(size) * shown / width >= params.MIN_LABEL_PX, size


def numbers(d):
    """The numbers of a path's d."""
    return [float(x) for x in re.findall(r"-?[\d.]+", d)]


def test_water_enters_only_through_a_screen_or_open_hole(section):
    for _, _, svg in svgs(section):
        wells = {}
        for m in re.finditer(
            r'class="w-(screen|openhole|casing)" d="([^"]+)" data-seg="(\w+)"'
            r' data-well="([\w-]+)"',
            svg,
        ):
            v = numbers(m[2])  # M x y V y M x y V y
            xs, ys = (v[0], v[3]), (v[1], v[2])
            wells.setdefault(m[4], []).append((m[3], xs, ys))
        ends = re.findall(
            r'data-(?:flow|inflow)="([\w-]+)" d="([^"]+)"', svg
        ) + [
            (w, d)
            for d, w in re.findall(
                r'class="w-(?:move|inflow)" d="([^"]+)" data-(?:flow|inflow)="'
                r'([\w-]+)"',
                svg,
            )
        ]
        assert ends, "no water drawn"
        for well, d in ends:
            v = numbers(d)
            x, y = v[-2], v[-1]
            on = [
                kind
                for kind, xs, ys in wells[well]
                if min(xs) - 4 <= x <= max(xs) + 4 and min(ys) <= y <= max(ys)
            ]
            assert on and "casing" not in on, (well, x, y, on)


def test_no_position_or_personal_field_leaves_the_build(section, stats):
    text = section + json.dumps(stats)
    for word in ("Owner", "DrillerName", "CoordDD", "GridNumber", "Property"):
        assert word not in text, word
    report = json.loads(
        read(DOCS, "assets", "aquifer", "wells", "detail--1970_613.json")
    )["S" + stats["figures"]["example_report"]]
    for key in ("CoordDDLat", "CoordDDLong", "GridNumber"):
        assert report[key] not in text, key


def test_the_script_sets_text_only_as_text():
    js = read(DOCS, "assets", "wells.js")
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js
    assert "fetch(" not in js


# ------------------------------------------------------------ the arithmetic
def test_the_costs_and_energy_are_the_checked_ones():
    data = json.loads(read(ROOT, "resources", "wells", "constants.json"))
    c = {k: v["value"] for k, v in data.items() if k != "about"}
    pws = ("ucm_public_supply_usd_2023_01", "ucm_depths_public_supply_ft")
    assert round(costs.cost(c, *pws, 205, 150)) == pytest.approx(
        319_800, abs=100
    )
    assert round(costs.cost(c, *pws, 2500, 400)) == pytest.approx(
        2_082_462, abs=100
    )
    irr = ("ucm_irrigation_usd_2023_01", "ucm_depths_irrigation_ft")
    assert round(costs.cost(c, *irr, 2000, 150)) == pytest.approx(
        597_375, abs=100
    )
    figs = {
        "outcrop_level": 61,
        "deep_level_gwdb": 306,
        "deep_level_sdr": 416,
        "deep_depth": 2528,
        "outcrop_depth": 170,
    }
    e = costs.energy_figures(c, figs, 50)
    assert e["outcrop_energy"] == "130–190"
    assert e["deep_energy"] == "550–720"
    assert e["energy_ratio_mid"] == "3.5 to 4.6"
