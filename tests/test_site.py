"""docs/: the website at hickorysandsdistrictava.org (issue #96).

Every page in docs/ is a complete HTML document (a doctype, the language, the
character set, the phone viewport and a title), every local file a page links
to or loads is in docs/, and every link off the site is https. A page that has
moved (explore.html and aquifer.html, now the map) is a small page that sends
the reader on, with and without JavaScript, and no page links it. Walk the
line is the site's only story map: no page names or links the 2023 ArcGIS
StoryMap (Dan, 2026-10-19). site.yml runs these before it deploys docs/ to
GitHub Pages. Standard library only, so the lint workflow runs them too.
"""

from html.parser import HTMLParser
import os
import re
from urllib.parse import unquote
from urllib.parse import urlsplit

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "docs")
PAGES = sorted(
    os.path.relpath(os.path.join(folder, name), SITE)
    for folder, _, names in os.walk(SITE)
    for name in names
    if name.endswith(".html")
)
LINKS = ("href", "src", "poster", "data")
SITE_URL = "https://hickorysandsdistrictava.org/"
# The pages that have moved, and where each sends the reader.
MOVED = {
    "explore.html": "map.html",
    "aquifer.html": "map.html?layers=aquifer,vineyards,places",
}


class Page(HTMLParser):
    """What the tests need from one page: its head and its references."""

    def __init__(self):
        """Starts an empty page."""
        super().__init__(convert_charrefs=True)
        self.doctype = None
        self.lang = None
        self.charset = False
        self.viewport = False
        self.title = ""
        self.refs = []
        self.refresh = None  # a meta refresh's content
        self.canonical = None
        self.robots = None
        self.moved_to = None  # assets/moved.js's data-to
        self._in_title = False

    def handle_decl(self, decl):
        """Keeps the doctype."""
        self.doctype = decl

    def handle_starttag(self, tag, attrs):
        """Keeps the head's tags and every reference to another file."""
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "meta":
            self.charset = self.charset or "charset" in a
            self.viewport = self.viewport or a.get("name") == "viewport"
            if (a.get("http-equiv") or "").lower() == "refresh":
                self.refresh = a.get("content")
            if a.get("name") == "robots":
                self.robots = a.get("content")
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        elif tag == "script" and a.get("src") == "assets/moved.js":
            self.moved_to = a.get("data-to")
        elif tag == "title":
            self._in_title = True
        for name in LINKS:
            if a.get(name):
                self.refs.append(a[name])
        for item in (a.get("srcset") or "").split(","):
            if item.strip():
                self.refs.append(item.split()[0])

    def handle_endtag(self, tag):
        """Ends the title."""
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        """Collects the title's text."""
        if self._in_title:
            self.title += data


def read(page):
    """Returns the parsed page at page, a path under docs/."""
    p = Page()
    with open(os.path.join(SITE, page), encoding="utf-8") as fh:
        p.feed(fh.read())
    p.close()
    return p


def target(page, ref):
    """Returns the file under docs/ that ref on page names, or None.

    None for a link off the site, a mail or phone link, an anchor on the
    same page or inline data.
    """
    url = urlsplit(ref)
    if url.scheme or url.netloc or not url.path:
        return None
    path = unquote(url.path)
    if path.startswith("/"):
        full = os.path.join(SITE, path.lstrip("/"))
    else:
        full = os.path.join(SITE, os.path.dirname(page), path)
    full = os.path.normpath(full)
    if path.endswith("/") or os.path.isdir(full):
        full = os.path.join(full, "index.html")
    return full


def test_site_has_a_home_page():
    assert "index.html" in PAGES


@pytest.mark.parametrize("page", PAGES)
def test_page_is_complete(page):
    p = read(page)
    assert (p.doctype or "").lower() == "doctype html", "no <!doctype html>"
    assert p.lang, "no <html lang>"
    assert p.charset, "no <meta charset>"
    assert p.viewport, "no <meta name=viewport> (phones)"
    assert p.title.strip(), "no <title>"


@pytest.mark.parametrize("page", PAGES)
def test_local_files_exist(page):
    missing = []
    for ref in read(page).refs:
        full = target(page, ref)
        if full is None:
            continue
        inside = full.startswith(SITE + os.sep)
        if not inside or not os.path.isfile(full):
            missing.append(ref)
    assert not missing, f"not in docs/: {missing}"


@pytest.mark.parametrize("page", PAGES)
def test_links_off_the_site_are_https(page):
    plain = [r for r in read(page).refs if urlsplit(r).scheme == "http"]
    assert not plain, f"http, not https: {plain}"


def test_the_moved_pages_are_the_only_ones_that_refresh():
    refreshing = sorted(p for p in PAGES if read(p).refresh is not None)
    assert refreshing == sorted(MOVED)


@pytest.mark.parametrize("page", sorted(MOVED))
def test_a_moved_page_sends_the_reader_on(page):
    # assets/moved.js goes there at once, keeping the old address's query and
    # #fragment; without JavaScript the meta refresh goes to the address
    # alone; the page's link is there for anything that stops both.
    p = read(page)
    to = MOVED[page]
    assert p.moved_to == to
    assert p.refresh == f"0; url={to}"
    assert to in p.refs
    assert p.canonical == SITE_URL + "map.html"
    assert p.robots == "noindex"
    assert os.path.isfile(target(page, to))


@pytest.mark.parametrize("page", [p for p in PAGES if p not in MOVED])
def test_no_page_relies_on_a_redirect(page):
    moved = {os.path.join(SITE, name) for name in MOVED}
    links = [r for r in read(page).refs if target(page, r) in moved]
    assert not links, f"links a moved page: {links}"


# The 2023 ArcGIS StoryMap: its host, ArcGIS Online's story app, or its name.
STORYMAP = re.compile(r"storymaps\.arcgis\.com|/apps/stories/|storymap", re.I)


def test_no_page_names_or_links_the_2023_storymap():
    # Walk the line is the site's only story map (Dan, 2026-10-19).
    texts = [os.path.join(ROOT, "src", "site", "walk.template.html")]
    for folder, _, names in os.walk(SITE):
        texts += [
            os.path.join(folder, name)
            for name in names
            if name.endswith((".html", ".js", ".css"))
        ]
    found = []
    for path in texts:
        with open(path, encoding="utf-8") as fh:
            for m in STORYMAP.finditer(fh.read()):
                found.append(f"{os.path.relpath(path, ROOT)}: {m[0]!r}")
    assert not found
