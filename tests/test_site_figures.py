"""The website's figures (#124): every boundary figure a page shows is built.

A figure in a page is an element marked data-figure (the area, the step and
point counts, the line's length, the revision date); the build writes its text
from docs/data/ (src/site/make_site_data.py --pages). These check that every
page's marked figures are what the committed data gives, and that no page types
one of those figures without the mark. Dated history (a journal note, a step in
the status timeline) is an event, not a figure, and is left as written.
Standard library only, so the lint workflow runs these.
"""

import glob
import os
import re

import pytest

from src.site import make_site_data as msd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
PAGES = sorted(glob.glob(os.path.join(DOCS, "*.html")))
# Dated history: kept as written, not a figure.
HISTORY = re.compile(
    r'<p class="timeline-date">.*?</p>'
    r'|<article class="journal-note"><time[^>]*>[^<]*</time>',
    re.S,
)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def figs():
    names = ("boundary.geojson", "steps.geojson", "points.geojson")
    return msd.figures({n: read(os.path.join(DOCS, "data", n)) for n in names})


@pytest.mark.parametrize("page", PAGES, ids=os.path.basename)
def test_marked_figures_are_the_build_s(page, figs):
    text = read(page)
    assert msd.fill_figures(text, figs, page) == text, (
        "run ./build.sh site-data"
    )


@pytest.mark.parametrize("page", PAGES, ids=os.path.basename)
def test_no_figure_is_typed_without_its_mark(page, figs):
    text = HISTORY.sub("", msd.FIGURE.sub("", read(page)))
    area, whole = figs["area_sqmi"][0], figs["area_whole"][0]
    steps, points = figs["step_count"][0], figs["point_count"][0]
    typed = [
        area,
        f"{whole} square miles",
        f"{steps} steps",
        f"{steps} boundary steps",
        f">{steps}<",
        f"{points} points",
        figs["revision_date"][0],
    ]
    found = [t for t in typed if t in text]
    assert not found, f"typed, not marked data-figure: {found}"
