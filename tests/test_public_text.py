"""Claims that contradicted the petition or Comment 9 stay off the website.

Each claim in CLAIMS was on the website, in its data or in the code that
writes them, and was taken out because it disagreed with the petition (as
amended June 6, 2023) or with Comment 9, the petitioners' response to
Comment 8 (commit a71271c; held by this test since the review of PRs
#140-#149, Oct. 19, 2026). The test fails if one comes back in docs/ (every
.html, .json, .geojson and .js) or in src/site/ (every .py and .html).

A claim is its phrase, and, where the phrase alone is also said correctly,
words that make it the wrong claim when they are in the same sentence:
"1:250,000" is wrong for the USGS State Geologic Map Compilation (SGMC,
1:500,000, as Comment 9 says), not for the Geologic Atlas of Texas; "about
9%" and "about 47%" were the soils' shares of the ground. The phrase is
found whatever its case, and whatever separates its words: white space, a
line break, a non-breaking space (as a character, an entity or an escape)
or an HTML tag; and a Python string split across lines.

The petition's area was shown as "about 194 square miles", which is not the
petition's 193; the proposed revision's own area also rounds to 194, so the
words are not the test: no page may mark the figures the site-data stage
keeps for the petition's and Notice No. 243's areas (petition_area_whole,
notice_243_area_whole).

It also holds the amended petition's date on the Status page to the one the
boundary's code gives (src/boundary/build_proposed.py), so the two cannot
drift apart.

Standard library only, so the lint workflow runs it.
"""

import ast
import datetime
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
# (phrase, words that make it the wrong claim in its sentence, or None when
# the phrase is always the wrong claim)
CLAIMS = (
    ("not visible on NAIP", None),
    (
        "1:250,000",
        (r"\bSGMC\b", r"State\s+Geologic\s+Map\s+Compilation", r"statewide"),
    ),
    ("about 47%", (r"\bsoil", r"\bsandstone", r"\bgranite")),
    ("about 9%", (r"\bsoil", r"\bsandstone", r"\bgranite")),
    ("deep, sandy", None),
    ("about a tenth of the ground", None),
)
# the figures no page may mark (their words are not the test: see above)
UNMARKED = ("petition_area_whole", "notice_243_area_whole")
# where they must not come back: (folder, file name patterns), searched
# through every folder below it
SCANNED = (
    ("docs", ("*.html", "*.json", "*.geojson", "*.js")),
    ("src/site", ("*.py", "*.html")),
)
# what may separate two words: white space (a line break, a non-breaking
# space) or a non-breaking space as an escape or an entity
GAP = r"(?:\s|\\u00a0|\\xa0|&nbsp;|&#160;|&#xa0;)+"
# a tag that starts or ends a block of text (a paragraph, a heading, an
# item, ...), so two blocks are never read as one sentence
BLOCK = (
    r"</?(?:p|h[1-6]|li|ul|ol|dl|dt|dd|div|section|article|aside|header|"
    r"footer|nav|main|figure|figcaption|table|tr|td|th|blockquote)\b[^<>]*>"
)
# where a sentence ends: a full stop, ! or ? before a space or the end, a
# blank line (between two strings of a data or code file) or a block's tag
END = re.compile(r"[.!?](?=\s|$)|\n\s*\n|" + BLOCK, re.IGNORECASE)
TAG = re.compile(r"<[^<>]*>")
# a script's string literal: "...", '...' or `...`
JS_STRING = re.compile(
    r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`'
)
MARK = re.compile(r"""data-figure\s*=\s*["']?(""" + "|".join(UNMARKED) + r")\b")
STATUS = ROOT / "docs" / "status.html"
BOUNDARY_CODE = ROOT / "src" / "boundary" / "build_proposed.py"


def pattern(phrase):
    """Returns the regular expression that finds a claim's phrase.

    Case is ignored, any GAP separates its words, and it is not part of a
    longer word or number ("about 9%" is not found in "about 19%").
    """
    words = GAP.join(re.escape(word) for word in phrase.split())
    before = r"(?<!\w)" if re.match(r"\w", phrase) else ""
    after = r"(?!\w)" if re.search(r"\w$", phrase) else ""
    return re.compile(before + words + after, re.IGNORECASE)


# each claim's phrase, and what must be in its sentence (None: nothing)
PATTERNS = {
    phrase: (
        pattern(phrase),
        re.compile("|".join(context), re.IGNORECASE) if context else None,
    )
    for phrase, context in CLAIMS
}


def sentences(text):
    """Yields (offset, sentence) for each sentence of text, in order."""
    start = 0
    for end in END.finditer(text):
        yield start, text[start : end.end()]
        start = end.end()
    yield start, text[start:]


def search(phrase, text):
    """Returns where in text a claim is (an offset), or None.

    A claim with context words is found only in a sentence that has them.
    """
    found, context = PATTERNS[phrase]
    if context is None:
        hit = found.search(text)
        return hit.start() if hit else None
    for offset, sentence in sentences(text):
        hit = found.search(sentence)
        if hit and context.search(sentence):
            return offset + hit.start()
    return None


def scanned_files():
    """Returns every file the claims must stay out of, sorted."""
    return sorted(
        {
            path
            for folder, globs in SCANNED
            for glob in globs
            for path in (ROOT / folder).rglob(glob)
            if path.is_file()
        }
    )


def strings(value):
    """Returns every string in a parsed JSON value, keys included."""
    found, todo = [], [value]
    while todo:
        item = todo.pop()
        if isinstance(item, str):
            found.append(item)
        elif isinstance(item, dict):
            todo.extend(item.keys())
            todo.extend(item.values())
        elif isinstance(item, list):
            todo.extend(item)
    return found


def readings(path, text):
    """Returns the ways a file's text is read: (label, text) pairs.

    The text as written; and, decoded, what a reader sees: an HTML page
    with its entities read, and so again with its tags taken out (a block's
    tag as a blank line, and any other as nothing, for a tag inside a word
    or a figure, or as a space, for one between two words, such as <br>); a
    JSON file's strings; a Python file's strings (the parser joins a string
    split across lines); a script's string literals. Strings are kept a
    blank line apart, so two are never read as one sentence.
    """
    out = [(None, text)]
    if path.suffix == ".html":
        blocks = re.sub(BLOCK, "\n\n", text, flags=re.IGNORECASE)
        out += [
            ("as read", html.unescape(text)),
            ("as read, without its tags", html.unescape(TAG.sub("", blocks))),
            (
                "as read, its tags as spaces",
                html.unescape(TAG.sub(" ", blocks)),
            ),
        ]
    elif path.suffix in {".json", ".geojson"}:
        held = strings(json.loads(text))
        out.append(("in its strings", "\n\n".join(held)))
    elif path.suffix == ".py":
        held = [
            node.value
            for node in ast.walk(ast.parse(text))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        out.append(("in its strings", "\n\n".join(held)))
    elif path.suffix == ".js":
        held = [m.group()[1:-1] for m in JS_STRING.finditer(text)]
        out.append(("in its strings", "\n\n".join(held)))
    return out


def found_in(path, raw):
    """Returns where each claim is in a file.

    Args:
        path: The file, for its type and the report.
        raw: Its bytes.

    Returns:
        One line per claim found: the file, the line where its text has it
        (or how it was read), and the claim's phrase.
    """
    low, page = raw.lower(), path.suffix == ".html"
    # a page is always read; any other file only when it holds every word
    # of a phrase (a tag cannot split them there; the aquifer page's well
    # tiles are 90 MB)
    maybe = [
        phrase
        for phrase, _ in CLAIMS
        if page or all(word.lower().encode() in low for word in phrase.split())
    ]
    if not maybe:
        return []
    text = raw.decode("utf-8")
    name = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    found = []
    for phrase in maybe:
        for label, reading in readings(path, text):
            # a data or code file's claim in context is read in its
            # strings only: as written, two strings run into one sentence
            if label is None and PATTERNS[phrase][1] and not page:
                continue
            at = search(phrase, reading)
            if at is not None:
                where = (
                    f"line {text.count(chr(10), 0, at) + 1}"
                    if label is None
                    else label
                )
                found.append(f"{name} ({where}): {phrase!r}")
                break
    return found


def marked(text):
    """Returns the figures in UNMARKED that a page marks with data-figure."""
    return sorted(set(MARK.findall(text)))


def test_the_scan_covers_the_site_and_its_code():
    names = {path.relative_to(ROOT).as_posix() for path in scanned_files()}
    for expected in (
        "docs/index.html",
        "docs/status.html",
        "docs/assets/maps.js",
        "docs/data/steps.geojson",
        "docs/assets/aquifer/stats.json",
        "src/site/make_site_data.py",
        "src/site/walk.template.html",
    ):
        assert expected in names, f"{expected} is not scanned"


# the sentences as they were (commit a71271c's), each written in other ways
WRONG = [
    (
        "page.html",
        (
            '<p class="lp-note">Historical vineyards, not visible on NAIP '
            "2022.</p>"
        ),
    ),
    (
        "page.html",
        (
            "<p>At the surface, from the USGS 1:250,000 geologic map (SGMC), "
            "shifted about <span>…</span> m onto the outcrops.</p>"
        ),
    ),
    (
        "page.html",
        (
            "<p>It is the statewide map at about 1:250,000, and the shifted "
            "copy covers the Llano Uplift area only.</p>"
        ),
    ),
    (
        "page.html",
        (
            "<p>Inside the proposed boundary, soils formed in Cambrian "
            "sandstone, mostly the Hickory Sandstone Member, cover nearly "
            "half of the ground (about 47%); soils formed in granite or "
            "granite grus, under a tenth (about 9%).</p>"
        ),
    ),
    ("page.html", "<p>Deep, sandy, well-drained ground.<br>Drawn</p>"),
    (
        "page.html",
        (
            "<p>The line leaves most of the granite core of the Llano Uplift "
            "outside; about a tenth of the ground within it is granite soil "
            "or bare granite.</p>"
        ),
    ),
    # the space, line break, entity, escape or tag between the words
    ("page.html", "<p>Deep,\n  sandy soils</p>"),
    ("page.html", "<p>deep, <em>sandy</em> soils</p>"),
    ("page.html", "<p>Deep,<br>sandy soils</p>"),
    ("page.html", "<p>Granite soils: about&nbsp;9% of it.</p>"),
    ("page.html", "<p>Sandstone soils, about <b>47</b>% of it.</p>"),
    ("page.html", "<p>about a <em>tenth</em> of the ground</p>"),
    ("page.html", "<p>the <abbr>SGMC</abbr>, at 1:<b>250,000</b></p>"),
    ("data.json", '{"note": "granite soils, about\\u00a09% of them"}'),
    ("data.geojson", '{"n": "Historical (NOT VISIBLE ON NAIP 2022)"}'),
    ("code.py", 'NOTE = (\n    "SGMC, a map at 1:250,000 "\n    "scale."\n)\n'),
    ("page.js", "const a = 'about a tenth of the ground';"),
    ("page.js", 'const n = "Granite soils: about 9% of them.";'),
]
# correct uses of the same words
RIGHT = [
    ("page.html", "<p>Geologic Atlas of Texas, Llano Sheet, 1:250,000.</p>"),
    (
        "page.html",
        "<p>The SGMC is 1:500,000. The Atlas of Texas is 1:250,000.</p>",
    ),
    ("page.html", "<p>about 9% of the wells reach the aquifer</p>"),
    ("page.html", "<p>about 47% of the reports have a log</p>"),
    ("page.html", "<p>each block outlined by eye on NAIP 2022</p>"),
    ("page.html", "<p>Soils of shallow-to-medium depth, sandy, drained.</p>"),
    # another block's or string's words are not in the sentence
    ("page.html", "<h3>Granite</h3><p>about 9% of the wells</p>"),
    ("data.json", '{"a": "Granite", "b": "about 9% of the wells"}'),
    ("page.js", 'const a = "SGMC";\nconst b = "Atlas, 1:250,000";'),
    # a longer number or word is not the phrase
    ("page.html", "<p>granite soils, about 19% of them</p>"),
    ("page.html", "<p>sandstone soils, about 470% more</p>"),
    ("page.html", "<p>deep, sandyish</p>"),
]


@pytest.mark.parametrize(("name", "text"), WRONG)
def test_a_wrong_claim_is_found_however_it_is_written(name, text):
    assert found_in(ROOT / name, text.encode("utf-8")), text


@pytest.mark.parametrize(("name", "text"), RIGHT)
def test_a_correct_use_of_its_words_is_not_the_claim(name, text):
    assert not found_in(ROOT / name, text.encode("utf-8")), text


def test_no_claim_that_contradicted_the_petition_comes_back():
    found = [
        line
        for path in scanned_files()
        for line in found_in(path, path.read_bytes())
    ]
    assert not found, (
        "these contradicted the petition or Comment 9 and were taken out:\n  "
        + "\n  ".join(found)
    )


def test_the_old_area_line_marks_the_petition_s_area():
    old = (
        '<p>Within about <span data-figure="petition_area_whole">194</span> '
        "square miles.</p>"
    )
    assert marked(old) == ["petition_area_whole"]
    assert marked("<span data-figure='notice_243_area_whole'>198</span>")
    assert not marked('<span data-figure="area_whole">194</span>')


def test_no_page_marks_the_petition_s_or_the_notice_s_area():
    found = {
        path.relative_to(ROOT).as_posix(): figures
        for path in scanned_files()
        if path.suffix == ".html"
        and (figures := marked(path.read_text(encoding="utf-8")))
    }
    assert not found, (
        "the petition's area was shown as about 194 square miles; the "
        "petition says 193. No page marks the petition's or Notice No. "
        f"243's area: {found}"
    )


class Timeline(HTMLParser):
    """The Status page's chronology: each entry's dates and heading."""

    def __init__(self):
        """Starts with no entry."""
        super().__init__(convert_charrefs=True)
        self.entries = []  # {"times": [(datetime, text)], "heading": str}
        self._in = None  # "time" or "h2" while inside one

    def handle_starttag(self, tag, attrs):
        """Starts an entry at each <li>; keeps a <time>'s datetime."""
        if tag == "li":
            self.entries.append({"times": [], "heading": ""})
        elif tag == "time" and self.entries:
            self.entries[-1]["times"].append([dict(attrs).get("datetime"), ""])
            self._in = "time"
        elif tag == "h2" and self.entries:
            self._in = "h2"

    def handle_endtag(self, tag):
        """Ends a <time> or an <h2>."""
        if tag in {"time", "h2"}:
            self._in = None

    def handle_data(self, data):
        """Keeps a <time>'s text and the entry's heading."""
        if self._in == "time":
            self.entries[-1]["times"][-1][1] += data
        elif self._in == "h2":
            self.entries[-1]["heading"] += data


def test_status_gives_the_amended_petition_s_date_as_the_code_does():
    code = BOUNDARY_CODE.read_text(encoding="utf-8")
    said = {
        " ".join(date.split())
        for date in re.findall(
            r"as\s+amended\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", code
        )
    }
    assert len(said) == 1, (
        f"{BOUNDARY_CODE.name} gives the amended petition's date as {said}"
    )
    (amended,) = said
    iso = datetime.datetime.strptime(amended, "%B %d, %Y").date().isoformat()

    page = Timeline()
    page.feed(STATUS.read_text(encoding="utf-8"))
    page.close()
    entries = [e for e in page.entries if "as amended" in e["heading"].lower()]
    assert len(entries) == 1, (
        "the Status page should have one entry for the petition as amended, "
        f"not {len(entries)}"
    )
    times = [
        (when, " ".join(text.split())) for when, text in entries[0]["times"]
    ]
    assert times == [(iso, amended)], (
        f"the Status page dates the amended petition {times}; "
        f"{BOUNDARY_CODE.name} says {amended} ({iso})"
    )
