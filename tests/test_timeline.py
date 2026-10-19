"""docs/land.html: the cited geologic timeline (issue #117).

The section #deep-time walks through eight stages, oldest first. Each stage
gives its age (with its uncertainty, in words) and cites at least one source;
every citation is a link to an entry of the section's Sources list, which is
numbered in the order the page first cites its sources, and every entry is
cited and is a full reference (authors, year, title, a link). The page keeps
the site's wording: "the Hickory Sandstone Member", never a bare "Hickory
Sandstone" (a source's own title, in <cite>, keeps its own wording); "Hickory
Sands" only as "Hickory Sands District", outside a quotation (the petition's
"Hickory Sands soils"); never "agreed". timeline.js, an
enhancement only, makes every element and sets every text itself, never from
an HTML string, and timeline.css styles only its own geo- classes; the two
agree on when a phone is held upright (the figure stuck to the top of the
screen, stepped by scrolling).

Every stage rests on the published sources its Sources list cites.
Standard library only, so the lint workflow runs these.
"""

from html.parser import HTMLParser
import os
import re

import pytest

from src.site.stamp_assets import unstamped

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "docs")
PAGE = os.path.join(SITE, "land.html")
SCRIPT = os.path.join(SITE, "assets", "timeline.js")
STYLES = os.path.join(SITE, "assets", "timeline.css")
STAGES = 8
# elements HTML never closes
VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}
AGE = re.compile(
    r"^(?:Today|.*\d[\d,.]* million years(?: ago)?|.*half a billion years ago)$"
)
YEAR = re.compile(r"\b(?:1[89]\d\d|20\d\d)\b|\bn\.d\.")
# A quotation in the page's curly quotes; one opening quote never reaches
# past the next.
QUOTED = re.compile(r"“[^“”]*”")
# The quotations that keep a bare "Hickory Sands" as their source wrote it,
# each with the page's words around it: the petition's (p. 11, and its term
# "Hickory Sands soils") and Notice No. 243's (52584, "Hickory Sands"
# standing alone). Any other quotation, or one of these anywhere else, is the
# site's own wording.
SOURCES_WORDS = (
    (
        "“the Hickory aquifer, Hickory Sands soils, and elevation at 1,500 "
        "feet or higher.”"
    ),
    "the petition calls “Hickory Sands soils.”",
    "“Hickory Sands” standing alone",
)


def own_words(text, phrases=SOURCES_WORDS):
    """Returns the text without the named quotations: the site's own words.

    Args:
        text: The page's text, on one line.
        phrases: The quotations, with their curly quotes and the words around
            them, that keep their source's words.

    Returns:
        The text with each quotation taken out where it stands in one of the
        phrases; any other quotation stays, as the site's wording.
    """

    def keep(m):
        for phrase in phrases:
            quote = QUOTED.search(phrase)[0]
            at = phrase.index(quote)
            before, after = phrase[:at], phrase[at + len(quote) :]
            if (
                m[0] == quote
                and text[m.start() - len(before) : m.start()] == before
                and text[m.end() : m.end() + len(after)] == after
            ):
                return ""
        return m[0]

    return QUOTED.sub(keep, text)


class Land(HTMLParser):
    """What the tests need from land.html: its timeline and its words."""

    def __init__(self):
        """Starts an empty page."""
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.robots = None
        self.head = []
        self.stages = []
        self.cites = []
        self.sources = []
        self.words = []
        self.titles = []

    def inside(self, tag, cls=None, ident=None):
        """Returns whether an open element is a tag with that class or id."""
        for open_tag, attrs in reversed(self.stack):
            if open_tag != tag:
                continue
            if cls and cls not in (attrs.get("class") or "").split():
                continue
            if ident and attrs.get("id") != ident:
                continue
            return True
        return False

    def handle_starttag(self, tag, attrs):
        """Keeps the head's links and the timeline's stages and sources."""
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        href = unstamped(a.get("href") or "")  # without its version (#138)
        if tag == "meta" and a.get("name") == "robots":
            self.robots = a.get("content")
        elif tag == "link" and a.get("rel") == "stylesheet":
            self.head.append(("css", href, False))
        elif tag == "script":
            src = a.get("src")
            self.head.append(("js", src and unstamped(src), "defer" in a))
        elif tag == "li" and "geo-stage" in cls:
            self.stages.append(
                {**a, "age": "", "certainty": "", "title": "", "cites": []}
            )
        elif tag == "li" and self.inside("ol", cls="geo-source-list"):
            self.sources.append({**a, "title": "", "links": []})
        elif tag == "a" and href.startswith("#source-"):
            cite = {
                "href": href,
                "text": "",
                "label": a.get("aria-label"),
                "in_text": self.inside("div", cls="geo-text"),
            }
            self.cites.append(cite)
            if self.stages and self.inside("li", cls="geo-stage"):
                self.stages[-1]["cites"].append(cite)
        elif tag == "a" and self.inside("ol", cls="geo-source-list"):
            self.sources[-1]["links"].append(href)
        if tag not in VOID:
            self.stack.append((tag, a))

    def handle_endtag(self, tag):
        """Closes the innermost open element of that tag."""
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        """Collects the text where the tests read it."""
        if self.inside("script") or self.inside("style"):
            return
        in_cite = self.inside("cite")
        (self.titles if in_cite else self.words).append(data)
        if self.inside("a") and self.cites and self.inside("sup"):
            self.cites[-1]["text"] += data
        stage = self.stages[-1] if self.stages else None
        if stage and self.inside("li", cls="geo-stage"):
            if self.inside("p", cls="geo-age"):
                stage["age"] += data
            elif self.inside("p", cls="geo-certainty"):
                stage["certainty"] += data
            elif self.inside("h3"):
                stage["title"] += data
        if in_cite and self.sources and self.inside("li"):
            self.sources[-1]["title"] += data
        if self.sources and self.inside("ol", cls="geo-source-list"):
            self.sources[-1].setdefault("text", "")
            self.sources[-1]["text"] += data


def plain(chunks):
    """Returns the chunks as one line of text, one space between words."""
    return re.sub(r"\s+", " ", " ".join(chunks)).strip()


@pytest.fixture(scope="module")
def land():
    """The parsed land.html."""
    p = Land()
    with open(PAGE, encoding="utf-8") as fh:
        p.feed(fh.read())
    p.close()
    return p


def number(href):
    """Returns N from "#source-N"."""
    return int(href.removeprefix("#source-"))


def test_search_engines_may_index_the_page(land):
    # Dan, 2026-10-19 (#167): the site's pages are indexed.
    assert land.robots is None


def test_timeline_styles_follow_the_site_and_the_script_waits(land):
    css = [href for kind, href, _ in land.head if kind == "css"]
    assert "assets/site.css" in css and "assets/timeline.css" in css
    assert css.index("assets/timeline.css") > css.index("assets/site.css")
    assert ("js", "assets/timeline.js", True) in land.head, "not deferred"


def test_eight_stages_oldest_first(land):
    assert [s.get("id") for s in land.stages] == [
        f"stage-{n}" for n in range(1, STAGES + 1)
    ]
    starts = [float(s["data-from"]) for s in land.stages]
    ends = [float(s["data-to"]) for s in land.stages]
    assert starts == sorted(starts, reverse=True), "not oldest first"
    assert len(set(starts)) == STAGES, "two stages start together"
    assert all(a >= b >= 0 for a, b in zip(starts, ends, strict=True))


@pytest.mark.parametrize("n", range(1, STAGES + 1))
def test_every_stage_has_a_title_an_age_and_its_uncertainty(land, n):
    stage = land.stages[n - 1]
    assert plain([stage["title"]]), "no title"
    assert AGE.match(plain([stage["age"]])), f"age: {stage['age']!r}"
    assert plain([stage["certainty"]]), "no word on how certain the age is"


@pytest.mark.parametrize("n", range(1, STAGES + 1))
def test_every_stage_cites_a_source(land, n):
    cites = land.stages[n - 1]["cites"]
    assert any(c["in_text"] for c in cites), "no citation in the stage's text"


@pytest.mark.parametrize("n", range(1, STAGES + 1))
def test_every_stage_s_dates_are_the_ones_its_age_gives(land, n):
    stage = land.stages[n - 1]
    numbers = {
        int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", stage["age"])
    }
    if "half a billion" in stage["age"]:
        numbers.update(range(490, 511))  # "roughly half a billion": 500 +-2%
    for end in ("data-from", "data-to"):
        value = int(float(stage[end]))
        assert value == 0 or value in numbers, (
            f"{end}={value}: {stage['age']!r}"
        )


def test_no_claim_the_research_says_to_avoid(land):
    text = plain(land.words).lower()
    for phrase in (
        "deep ocean",
        "ocean floor",
        "upper cambrian",
        "late cambrian",
        "dresbachian",
    ):
        assert phrase not in text, phrase


def test_every_citation_resolves_to_its_source(land):
    ids = [s.get("id") for s in land.sources]
    assert ids == [f"source-{n}" for n in range(1, len(ids) + 1)]
    for cite in land.cites:
        n = number(cite["href"])
        assert 1 <= n <= len(ids), f"{cite['href']}: no such source"
        assert cite["text"].strip() == str(n), cite
        assert cite["label"] == f"Source {n}", cite


def test_every_source_is_cited(land):
    cited = {number(c["href"]) for c in land.cites}
    assert cited == set(range(1, len(land.sources) + 1))


def test_sources_numbered_in_order_of_first_citation(land):
    first = []
    for cite in land.cites:
        n = number(cite["href"])
        if n not in first:
            first.append(n)
    assert first == sorted(first)


def test_every_source_is_a_full_reference(land):
    assert land.sources
    for n, source in enumerate(land.sources, 1):
        text = plain([source.get("text", "")])
        assert plain([source["title"]]), f"{n}: no title in <cite>"
        assert YEAR.search(text), f"{n}: no year"
        assert re.match(r"[A-Z][^,]+,", text), f"{n}: no author"
        assert any(h.startswith("https://") for h in source["links"]), n


def test_hickory_sandstone_is_always_the_member(land):
    text = plain(land.words)
    bare = re.findall(r"Hickory Sandstone(?! Member).{0,30}", text)
    assert not bare, bare


def test_hickory_sands_is_only_the_district(land):
    # Only the named quotations keep their source's words (SOURCES_WORDS).
    text = own_words(plain(land.words + land.titles))
    assert not re.findall(r"Hickory Sands\b(?! District).{0,30}", text)


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        # a quotation the sources wrote is taken out
        ("the petition calls “Hickory Sands soils.” 1, 2", "Hickory Sands"),
        ("so: “Hickory Sands” standing alone", "Hickory Sands"),
        # scare quotes are the site's own words: kept, and so caught
        ("the “Hickory Sands” of the uplift", "“Hickory Sands”"),
        ("so-called “Hickory Sands soils.”", "“Hickory Sands soils.”"),
        # an unbalanced quote hides nothing after it
        ("“a quote never closed. Hickory Sands soils “the end.”", "Hickory"),
    ],
)
def test_only_the_named_quotations_keep_their_words(text, kept):
    stripped = own_words(text)
    if kept == "Hickory Sands":
        assert kept not in stripped
    else:
        assert kept in stripped


def test_never_agreed(land):
    text = plain(land.words + land.titles)
    assert not re.search(r"\bagreed\b", text, re.IGNORECASE)


def test_script_sets_text_as_text():
    with open(SCRIPT, encoding="utf-8") as fh:
        js = fh.read()
    # the ways a script turns a string into HTML or code: none may appear
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


def test_script_and_styles_keep_the_wording():
    for path in (SCRIPT, STYLES):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert not re.search(r"Hickory Sandstone(?! Member)", text), path
        assert not re.search(r"\bagreed\b", text, re.IGNORECASE), path


def test_styles_use_only_their_own_classes():
    with open(STYLES, encoding="utf-8") as fh:
        css = re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.DOTALL)
    names = set(re.findall(r"\.(-?[A-Za-z_][\w-]*)", css))
    assert names
    assert all(n == "geo" or n.startswith("geo-") for n in names), names


def test_script_and_styles_agree_on_a_phone_held_upright():
    # timeline.js steps the drawing as the list scrolls where timeline.css
    # sticks the figure to the top of the screen: one query, in both
    with open(SCRIPT, encoding="utf-8") as fh:
        js = fh.read()
    with open(STYLES, encoding="utf-8") as fh:
        css = re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.DOTALL)
    found = re.search(r"var tall = window\.matchMedia\(([^;]*)\);", js)
    assert found, "no query for a phone held upright in timeline.js"
    # the query may be split into string literals joined with +
    parts = re.findall(r'"([^"]*)"', found.group(1))
    assert parts, found.group(0)
    query = re.sub(r"\s+", "", "".join(parts))
    assert "orientation:portrait" in query, "a phone on its side counts"
    sticky = {
        re.sub(r"\s+", "", q)
        for q in re.findall(r"@media([^{]*max-width:999px[^{]*)\{", css)
    }
    assert sticky == {query}, (sticky, query)
