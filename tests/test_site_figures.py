"""The website's figures (#124): every boundary figure a page shows is built.

A figure in a page is an element marked data-figure (the area, the step and
point counts, the line's length, the revision date, and the land page's
land_ figures); the build writes its text from docs/data/ and
docs/assets/land/stats.json (src/site/make_site_data.py --pages). These check
that every page's marked figures, and its drawn paths marked data-figure-path
(the boundary drawing and its scale bar, #126), are what the committed data
gives, and that no page types one of those figures without the mark. A journal
note is history and is left as written; a dated step in the status timeline
keeps its date, but its figures describe the current proposed revision, so they
are marked.
Standard library only, so the lint workflow runs these.
"""

import glob
import os
import re

import pytest

from src.site import make_site_data as msd
from src.site import make_site_meta as msm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
PAGES = sorted(glob.glob(os.path.join(DOCS, "*.html")))
# Dated history: kept as written, not a figure.
HISTORY = re.compile(r'<article class="journal-note">.*?</article>', re.S)
# A dated step in the status timeline: its date is history, but its figures
# describe the current proposed revision, so they are marked and built.
EVENT_DATE = re.compile(r'<p class="timeline-date">.*?</p>', re.S)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def figs():
    names = ("boundary.geojson", "steps.geojson", "points.geojson")
    found = msd.figures({n: read(os.path.join(DOCS, "data", n)) for n in names})
    # The land page's slice and maps (src/site/make_land.py).
    found.update(msd.land_figures(DOCS))
    return found


@pytest.mark.parametrize("page", PAGES, ids=os.path.basename)
def test_marked_figures_are_the_build_s(page, figs):
    text = read(page)
    assert msd.fill_figures(text, figs, page) == text, (
        "run ./build.sh site-data"
    )


@pytest.mark.parametrize("page", PAGES, ids=os.path.basename)
def test_drawn_paths_are_the_build_s(page):
    # The boundary drawing and its scale bar (#126), from the committed data.
    text = read(page)
    data = read(os.path.join(DOCS, "data", "boundary.geojson"))
    assert msd.fill_paths(text, data, page) == text, "run ./build.sh site-data"


def test_dated_history_keeps_its_figures_as_written():
    # A journal note records what was true then; the next revision must not
    # rewrite it.
    for page in PAGES:
        for event in HISTORY.findall(read(page)):
            assert "data-figure" not in event, (page, event[:80])


@pytest.mark.parametrize("page", PAGES, ids=os.path.basename)
def test_no_figure_is_typed_without_its_mark(page, figs):
    text = msd.FIGURE_PATH.sub("", read(page))  # a coordinate is no figure
    text = EVENT_DATE.sub("", HISTORY.sub("", msd.FIGURE.sub("", text)))
    # The JSON-LD block copies the page's own text, marked figures included,
    # and tests/test_site_meta.py keeps it what the generator makes of it.
    text = msm.BLOCK.sub("", text)
    area, whole = figs["area_sqmi"][0], figs["area_whole"][0]
    steps, points = figs["step_count"][0], figs["point_count"][0]
    typed = [
        area,
        f"{whole} square miles",
        f"{steps} steps",
        f"{steps} boundary steps",
        f">{steps}<",
        f"{points} points",
        f"{figs['miles'][0]} miles",
        figs["revision_date"][0],
        figs["revision_date"][1],
    ]
    for compared in ("petition_area_whole", "notice_243_area_whole"):
        if compared in figs:
            typed.append(f"about {figs[compared][0]} square miles")
    found = [t for t in typed if t in text]
    assert not found, f"typed, not marked data-figure: {found}"
