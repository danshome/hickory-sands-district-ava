"""The website's menu: the same links, in the same order, on every page.

Every page in docs/, and src/site/walk.template.html (the build makes
walk.html from it), has the header's menu (the nav in details.navigation)
with the same links as Home's, in the same order; each link opens a page
that is in docs/; and the page's own link, and only it, is marked
aria-current="page" (a page that is not in the menu, such as Home or the
map, marks none). A link's page is its address with its query: The aquifer
is map.html?layers=aquifer,vineyards,places and The map is map.html (both in
"The maps", #179); The vineyards and The logo vote are in "The growers"
(#100); map.html marks The map in its HTML, and its script marks
The aquifer instead when opened with the aquifer on. A page that has
moved (explore.html, aquifer.html: a meta refresh to the map) has no menu.
404.html links from the site's root (/boundary.html), so it works at any
depth; its links are read from there.

Standard library only, so the lint workflow runs it; in Chrome,
tests/live/test_site_mobile.py checks the menu opens and its links answer.
"""

from html.parser import HTMLParser
from pathlib import Path
import posixpath
from urllib.parse import unquote
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs"
TEMPLATE = ROOT / "src" / "site" / "walk.template.html"
# each page and the page it is in the site (the walk's template is walk.html),
# but those that have moved (a meta refresh to the map)
PAGES = {
    **{
        path: path.name
        for path in sorted(SITE.glob("*.html"))
        if 'http-equiv="refresh"' not in path.read_text(encoding="utf-8")
    },
    TEMPLATE: "walk.html",
}
HOME = SITE / "index.html"


class Menu(HTMLParser):
    """The links of the header's menu: (text, href, aria-current) each."""

    def __init__(self):
        """Starts outside the menu."""
        super().__init__(convert_charrefs=True)
        self.links = []
        self.menus = 0  # how many details.navigation the page has
        self._depth = 0  # >0 inside details.navigation
        self._nav = False  # inside its nav
        self._link = None  # the link being read

    def handle_starttag(self, tag, attrs):
        """Enters the menu, its nav and each of its links."""
        a = dict(attrs)
        if tag == "details":
            if self._depth:
                self._depth += 1
            elif "navigation" in (a.get("class") or "").split():
                self._depth = 1
                self.menus += 1
        elif tag == "nav" and self._depth:
            self._nav = True
        elif tag == "a" and self._nav:
            self._link = [
                "",
                a.get("href") or "",
                a.get("aria-current"),
            ]

    def handle_endtag(self, tag):
        """Leaves a link, the nav or the menu."""
        if tag == "a" and self._link is not None:
            text, href, current = self._link
            self.links.append((" ".join(text.split()), href, current))
            self._link = None
        elif tag == "nav":
            self._nav = False
        elif tag == "details" and self._depth:
            self._depth -= 1

    def handle_data(self, data):
        """Keeps a link's text."""
        if self._link is not None:
            self._link[0] += data


def menu(path):
    """Returns the parsed menu of the page at path."""
    parsed = Menu()
    parsed.feed(path.read_text(encoding="utf-8"))
    parsed.close()
    return parsed


def target(href):
    """Returns the page in docs/ that a menu link opens, such as "land.html".

    Every page is in docs/ itself, so a relative link and one from the
    site's root ("/land.html", as 404.html has) name the same page. None
    for a link off the site.
    """
    url = urlsplit(href)
    if url.scheme or url.netloc or not url.path:
        return None
    path = posixpath.normpath(unquote(url.path).lstrip("/"))
    return "index.html" if path in {".", ""} else path


def address(href):
    """Returns the address in the site a menu link opens, with its query.

    "map.html?layers=aquifer,vineyards,places" (The aquifer) is not
    "map.html" (The map): the map marks The aquifer only when opened so.
    """
    page = target(href)
    query = urlsplit(href).query
    return f"{page}?{query}" if page and query else page


def links(path):
    """Returns the menu's links as (text, page) pairs."""
    return [(text, target(href)) for text, href, _ in menu(path).links]


def test_home_has_a_menu_of_pages_in_the_site():
    home = links(HOME)
    assert len(home) >= 2, f"Home's menu has {home}"
    addresses = [address(href) for _, href, _ in menu(HOME).links]
    assert len(set(addresses)) == len(addresses), (
        f"a page twice in the menu: {home}"
    )
    missing = [
        (text, page)
        for text, page in home
        if page is None or not (SITE / page).is_file()
    ]
    assert not missing, f"menu links to no page in docs/: {missing}"


@pytest.mark.parametrize(
    "path", list(PAGES), ids=lambda p: str(p.relative_to(ROOT))
)
def test_menu_is_home_s_with_this_page_marked(path):
    page = PAGES[path]
    parsed = menu(path)
    assert parsed.menus == 1, f"{parsed.menus} menus (details.navigation)"
    got = [(text, target(href)) for text, href, _ in parsed.links]
    home = links(HOME)
    assert got == home, f"the menu's links are {got}, not Home's {home}"
    marked = [
        (text, current)
        for text, _, current in parsed.links
        if current is not None
    ]
    mine = [
        (text, "page")
        for text, href, _ in menu(HOME).links
        if address(href) == page
    ]
    assert marked == mine, (
        f"aria-current marks {marked}, not {mine or 'no link'} ({page})"
    )
