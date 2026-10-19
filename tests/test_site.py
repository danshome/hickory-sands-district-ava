"""docs/: the website at hickorysandsdistrictava.org (issue #96).

Every page in docs/ is a complete HTML document (a doctype, the language, the
character set, the phone viewport and a title), every local file a page links
to or loads is in docs/ (a script's or stylesheet's version stamp aside), every
link off the site is https, and every local script and stylesheet a page loads,
and every module a script imports, carries the stamp of the file as it is now
(src/site/stamp_assets.py, #138), so a pull request that changes a script
without stamping it again fails. site.yml runs these before it deploys docs/
to GitHub Pages. Standard library only, so the lint workflow runs them too.
"""

from html.parser import HTMLParser
import os
from urllib.parse import unquote
from urllib.parse import urlsplit

import pytest

from src.site import stamp_assets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "docs")
# Pages made from a template elsewhere, stamped like the pages (build.sh).
TEMPLATES = (os.path.join(ROOT, "src", "site", "walk.template.html"),)
PAGES = sorted(
    os.path.relpath(os.path.join(folder, name), SITE)
    for folder, _, names in os.walk(SITE)
    for name in names
    if name.endswith(".html")
)
LINKS = ("href", "src", "poster", "data")


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


def test_a_stamped_url_names_its_file():
    want = os.path.join(SITE, "assets", "site.css")
    assert target("index.html", "assets/site.css?v=3f2a91c") == want
    assert target("404.html", "/assets/site.css?v=3f2a91c") == want


def test_every_script_and_stylesheet_carries_its_stamp():
    stale = stamp_assets.Site(SITE, TEMPLATES).stale
    shown = [
        f"{os.path.relpath(p, ROOT)}: {have} -> {want}"
        for p, have, want in stale
    ]
    assert not stale, (
        "run ./build.sh stamp and commit what it changes:\n" + "\n".join(shown)
    )


@pytest.mark.parametrize("page", PAGES)
def test_links_off_the_site_are_https(page):
    plain = [r for r in read(page).refs if urlsplit(r).scheme == "http"]
    assert not plain, f"http, not https: {plain}"
