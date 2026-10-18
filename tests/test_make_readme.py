"""src/documents/make_readme.py: README.txt's headings on the read-me page.

README.txt's ALL-CAPS headings become the read-me page's headings, in sentence
case with the official names kept ("Notice No. 243", "TTB") and the note after
them; and the page has every word of README.txt.
"""

import json
import math
import re

import pytest

from src import revision
from src.documents import make_readme


@pytest.mark.parametrize(
    "line, h2",
    [
        (
            (
                "WHAT WE PROPOSE TO CHANGE IN NOTICE NO. 243 (details in "
                "3_changes-side-by-side; marked in 2_TTB-notice-243-...)"
            ),
            (
                "<h2>What we propose to change in Notice No. 243 "
                "<small>(details in 3_changes-side-by-side; "
                "marked in 2_TTB-notice-243-...)</small></h2>"
            ),
        ),
        ("WHAT IS IN THIS PACKAGE", "<h2>What is in this package</h2>"),
        ("ATTRIBUTES", "<h2>Attributes</h2>"),
        ("WHAT TTB'S TEXT SAYS", "<h2>What TTB&#x27;s text says</h2>"),
        (
            "SOURCES (see https://www.ttb.gov/ava)",
            '<h2>Sources <small>(see <a href="https://www.ttb.gov/ava">https://www.ttb.gov/ava</a>)</small></h2>',
        ),
    ],
)
def test_heading(line, h2):
    assert make_readme.is_heading(line)
    assert make_readme.heading(line) == h2


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   WHAT IS IN THIS PACKAGE",
        "What is in this package",
        "1_description/",
        "README.txt",
        "WHAT IS IN THIS PACKAGE:",
        "NO",
        "- A LIST ITEM",
    ],
)
def test_not_a_heading(line):
    assert not make_readme.is_heading(line)


# A one-degree square at 30-31 degrees north: about 5,316 square miles in
# Web Mercator (the sphere's planar area), against 4,147 true.
SQUARE = {
    "type": "Polygon",
    "coordinates": [[[-100, 30], [-99, 30], [-99, 31], [-100, 31], [-100, 30]]],
}


def test_web_mercator_overstates_a_square_as_expected(tmp_path):
    path = tmp_path / "square.geojson"
    path.write_text(json.dumps({"features": [{"geometry": SQUARE}]}))
    radius = 6378137.0
    north = math.log(math.tan(math.pi / 4 + math.radians(31) / 2))
    south = math.log(math.tan(math.pi / 4 + math.radians(30) / 2))
    want = radius * math.radians(1) * radius * (north - south) / 1609.344**2
    assert make_readme.web_mercator_sqmi(str(path)) == pytest.approx(want)


def test_readme_and_page(tmp_path, monkeypatch):
    """The real templates, with the figures filled in.

    main() itself stops if a word of README.txt is not on the page.
    """
    (tmp_path / "proposed-steps.json").write_text(
        json.dumps(
            {"sqmi": 123.456, "steps": [{"step": n} for n in range(1, 8)]}
        )
    )
    (tmp_path / "gis").mkdir()
    (tmp_path / "gis" / "x-area-EPSG4269.geojson").write_text(
        json.dumps({"features": [{"geometry": SQUARE}]})
    )
    monkeypatch.setattr(make_readme, "HERE", str(tmp_path))
    make_readme.main()
    readme = (tmp_path / "README.txt").read_text(encoding="utf-8")
    page = (
        tmp_path
        / "documents"
        / f"Hickory-Sands-District-read-me-first-{revision.ISO}.html"
    ).read_text(encoding="utf-8")
    assert "123.46" in readme and not re.search(r"\{[A-Z_]+\}", readme)
    assert "all 7 boundary steps" in readme
    headings = [s for s in readme.splitlines()[3:] if make_readme.is_heading(s)]
    assert any(
        h.startswith("WHAT WE PROPOSE TO CHANGE IN NOTICE NO. 243")
        for h in headings
    )
    for h in headings:
        assert make_readme.heading(h) in page
