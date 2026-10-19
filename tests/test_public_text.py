"""Words that contradicted the petition or Comment 9 stay off the website.

Each phrase in PHRASES was on the website, in its data or in the code that
writes them, and was taken out because it disagreed with the petition (as
amended June 6, 2023) or with Comment 9, the petitioners' response to
Comment 8 (found by the review of PRs #140-#149, Oct. 19, 2026). The test
fails if one comes back in docs/ (every .html, .json, .geojson and .js) or
in src/site/ (every .py and .html), whatever its case, whether a line break,
a non-breaking space or an HTML entity separates its words, and whether a
Python string is split across lines.

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
PHRASES = (
    "not visible on NAIP",
    "1:250,000",
    "about 47%",
    "about 9%",
    "deep, sandy",
    "194 square miles",
    "about a tenth of the ground",
)
# where they must not come back: (folder, file name patterns), searched
# through every folder below it
SCANNED = (
    ("docs", ("*.html", "*.json", "*.geojson", "*.js")),
    ("src/site", ("*.py", "*.html")),
)
# what may separate two words: white space (a line break, a non-breaking
# space) or a non-breaking space as an escape or an entity
GAP = r"(?:\s|\\u00a0|\\xa0|&nbsp;|&#160;|&#xa0;)+"
STATUS = ROOT / "docs" / "status.html"
BOUNDARY_CODE = ROOT / "src" / "boundary" / "build_proposed.py"


def pattern(phrase):
    """Returns the regular expression that finds phrase.

    Case is ignored, any GAP separates its words, and it is not part of a
    longer word or number ("194 square miles" is not found in "2194 square
    miles").
    """
    words = GAP.join(re.escape(word) for word in phrase.split())
    before = r"(?<!\w)" if re.match(r"\w", phrase) else ""
    after = r"(?!\w)" if re.search(r"\w$", phrase) else ""
    return re.compile(before + words + after, re.IGNORECASE)


PATTERNS = {phrase: pattern(phrase) for phrase in PHRASES}


def scanned_files():
    """Returns every file the phrases must stay out of, sorted."""
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
    with its entities read, a JSON file's strings, a Python file's strings
    (the parser joins a string split across lines).
    """
    out = [(None, text)]
    if path.suffix == ".html":
        out.append(("as read", html.unescape(text)))
    elif path.suffix in {".json", ".geojson"}:
        out.append(("in its strings", "\n".join(strings(json.loads(text)))))
    elif path.suffix == ".py":
        held = [
            node.value
            for node in ast.walk(ast.parse(text))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        out.append(("in its strings", "\n".join(held)))
    return out


def found_in(path, raw):
    """Returns where each phrase is in a file.

    Args:
        path: The file, for its type and the report.
        raw: Its bytes.

    Returns:
        One line per phrase found: the file, the line where its text has
        it (or how it was read), and the phrase.
    """
    low = raw.lower()
    # only a file that holds every word of a phrase is read further (the
    # aquifer page's well tiles are 90 MB)
    maybe = [
        phrase
        for phrase in PHRASES
        if all(word.lower().encode() in low for word in phrase.split())
    ]
    if not maybe:
        return []
    text = raw.decode("utf-8")
    name = path.relative_to(ROOT)
    found = []
    for phrase in maybe:
        for label, reading in readings(path, text):
            hit = PATTERNS[phrase].search(reading)
            if hit:
                where = (
                    f"line {text.count(chr(10), 0, hit.start()) + 1}"
                    if label is None
                    else label
                )
                found.append(f"{name} ({where}): {phrase!r}")
                break
    return found


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


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("page.html", "<p>Deep,\n  sandy soils</p>"),
        ("page.html", "<p>about&nbsp;47% of it</p>"),
        ("data.json", '{"note": "about\\u00a09% of the wells"}'),
        ("data.geojson", '{"n": "Historical (NOT VISIBLE ON NAIP 2022)"}'),
        ("code.py", 'NOTE = (\n    "a map at 1:250,000 "\n    "scale"\n)\n'),
        ("code.py", 'NOTE = ("about 194 "\n        "square miles")\n'),
        ("page.js", "const a = 'about a tenth of the ground';"),
    ],
)
def test_a_phrase_is_found_however_it_is_written(name, text):
    assert found_in(ROOT / name, text.encode("utf-8")), text


@pytest.mark.parametrize(
    "text",
    [
        "2194 square miles",
        "about 19% of the wells",
        "deep, sandyish",
        "about 470% more",
    ],
)
def test_a_longer_number_or_word_is_not_the_phrase(text):
    assert not found_in(ROOT / "page.html", text.encode("utf-8")), text


def test_no_phrase_that_contradicted_the_petition_comes_back():
    found = [
        line
        for path in scanned_files()
        for line in found_in(path, path.read_bytes())
    ]
    assert not found, (
        "these contradicted the petition or Comment 9 and were taken out:\n  "
        + "\n  ".join(found)
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
