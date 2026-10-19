"""stamp_assets.py: a version on every script and stylesheet the site loads.

GitHub Pages serves every file with cache-control: max-age=600, so a browser
that loaded assets/timeline.js shortly before a deploy can keep the old file
for ten minutes after it (#138). So each local <script src> and
<link rel="stylesheet" href> in the site's pages, and each import of one of
the site's own modules by another (from "./maps.js", or a module path such
as const MAPS = "./maps.js" in docs/assets/*.js), carries a short hash of the
file it names, as in assets/timeline.js?v=3f2a91c: a changed file gets a new
URL, which a browser fetches at once.

A module's hash is taken after its own imports are stamped, so a change to
map-config.js changes the stamp maps.js gives it, and so maps.js's own hash
and the stamps of explore.js and walk.js that import it, up to the pages.
Every importer of a module names it with the same URL, so a page never loads
two copies of one module.

Running it again changes nothing. After changing a script or stylesheet, or
merging a branch that did, run it (./build.sh stamp, or ./build.sh site-data)
and commit what it changes. A merge conflict on a stamped line is resolved as
any other, keeping the code of both sides with either stamp, then it is run
again. Standard library only, so the lint workflow tests it.

Usage (the project .venv, -E -s -B):
  stamp_assets.py --site docs [--template FILE ...] [--check]
--template names a page made elsewhere from a template whose URLs are read as
if it were in --site's top folder (src/site/walk.template.html, which becomes
docs/walk.html), stamped like the pages. With --check nothing is written: it
exits 3 when a stamp is missing or stale, naming each. Other errors exit 1: a
page or module names a script, stylesheet or module that is not in the site,
a local URL carries another query, or the modules import each other in a
circle.
"""

import argparse
import hashlib
import os
import re
import sys
from urllib.parse import unquote
from urllib.parse import urlsplit

STALE = 3  # --check's exit status when a stamp is missing or stale
DIGITS = 7  # hex digits of the SHA-256 in a stamp, as in a short git hash
PAGES = (".html",)
MODULES = (".js", ".mjs")
# A version stamp at the end of a URL; unstamped() takes it off.
STAMPED = re.compile(r"\?v=[0-9a-f]*$")
# A tag that may load a script or a stylesheet, with its attributes.
TAG = re.compile(r"<(?P<tag>script|link)\b(?P<attrs>[^>]*)>", re.IGNORECASE)
# One attribute of such a tag, quoted either way.
ATTR = re.compile(
    r"(?P<lead>\s(?P<key>[a-z-]+)\s*=\s*)(?P<q>[\"'])(?P<value>.*?)(?P=q)",
    re.IGNORECASE | re.DOTALL,
)
# The same attribute written without quotes: refused, since the stamp could
# not be added or checked reliably.
BARE = re.compile(r"\s(?:src|href)\s*=\s*[^\s\"'>]", re.IGNORECASE)
# A module path in a script: a string literal "./name.js" or "../x/name.js",
# stamped or not. Such a literal names one of the site's own modules (static
# and dynamic imports, or a constant a dynamic import() is given).
IMPORT = re.compile(
    r"(?P<q>[\"'])(?P<path>\.\.?/[\w./-]+\.m?js)"
    r"(?P<stamp>\?v=[0-9a-f]*)?(?P=q)"
)


def unstamped(url):
    """Returns a URL without its version stamp.

    Args:
        url: A URL, such as "assets/timeline.js?v=3f2a91c".

    Returns:
        The URL without a trailing ?v=..., such as "assets/timeline.js".
    """
    return STAMPED.sub("", url)


def without_stamps(text):
    """Returns a page's or a script's text with every version stamp taken off.

    Args:
        text: The text, whose quoted URLs may end in a stamp.

    Returns:
        The text with each ?v=... that ends a quoted URL taken off.
    """
    return re.sub(r"\?v=[0-9a-f]*(?=[\"'])", "", text)


def digest(text):
    """Returns the stamp for a file's text: a short hash of its bytes.

    Args:
        text: The file's text, as it will be served.

    Returns:
        The first DIGITS hex digits of its SHA-256 (UTF-8).
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:DIGITS]


def read(path):
    """Returns a file's text, with its line endings kept.

    Args:
        path: The file.

    Returns:
        Its text, read as UTF-8.
    """
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def inside(site, path):
    """Returns whether path is a file inside the site's folder.

    Args:
        site: The site's folder.
        path: A normalized absolute path.

    Returns:
        True when path is a file under site.
    """
    root = os.path.abspath(site)
    return path.startswith(root + os.sep) and os.path.isfile(path)


class Site:
    """The site's pages and modules, and the stamp each file should carry.

    Attributes:
        site: The site's folder (docs).
        texts: The stamped text of every page, template and module whose
            text the stamps change, by absolute path.
        found: The same files as they are on disk, by absolute path.
        stale: (file, URL as written, URL as it should be) for every stamp
            that is missing or wrong.
    """

    def __init__(self, site, templates=()):
        """Reads the site and works out every stamp, writing nothing.

        Args:
            site: The site's folder (docs).
            templates: Pages made elsewhere from a template whose URLs are
                read as if it were in the site's top folder.

        Raises:
            SystemExit: When a URL names a file that is not in the site,
                carries another query, or the modules import in a circle.
        """
        self.site = os.path.abspath(site)
        self.texts, self.found, self.stale = {}, {}, []
        self._stamps = {}
        self._visiting = []
        modules, pages = [], []
        for folder, dirs, names in os.walk(self.site):
            dirs.sort()
            for name in sorted(names):
                path = os.path.join(folder, name)
                if name.endswith(MODULES):
                    modules.append(path)
                elif name.endswith(PAGES):
                    pages.append((path, folder))
        pages += [(os.path.abspath(t), self.site) for t in templates]
        for path in modules:
            self.stamp_of(path)
        for path, base in pages:
            self._page(path, base)

    def stamp_of(self, path):
        """Returns the stamp of a file the site loads.

        A module's own imports are stamped first, and its stamp is the hash
        of its text with them.

        Args:
            path: An absolute path to a script or stylesheet in the site.

        Returns:
            The file's stamp.

        Raises:
            SystemExit: When modules import each other in a circle, or a
                module names a module that is not in the site.
        """
        if path in self._stamps:
            return self._stamps[path]
        if not path.endswith(MODULES):
            self._stamps[path] = digest(read(path))
            return self._stamps[path]
        if path in self._visiting:
            cycle = [*self._visiting[self._visiting.index(path) :], path]
            names = " -> ".join(os.path.relpath(p, self.site) for p in cycle)
            sys.exit(f"the site's modules import in a circle: {names}")
        self._visiting.append(path)
        text = read(path)
        folder = os.path.dirname(path)
        where = os.path.relpath(path, self.site)

        def stamp_import(m):
            named = os.path.normpath(os.path.join(folder, m["path"]))
            if not inside(self.site, named):
                sys.exit(f"{where}: {m['path']} is not a module in the site")
            want = f"{m['path']}?v={self.stamp_of(named)}"
            have = m["path"] + (m["stamp"] or "")
            if have != want:
                self.stale.append((path, have, want))
            return f"{m['q']}{want}{m['q']}"

        stamped = IMPORT.sub(stamp_import, text)
        self._visiting.pop()
        self.found[path], self.texts[path] = text, stamped
        self._stamps[path] = digest(stamped)
        return self._stamps[path]

    def _local(self, url, base, where):
        """Returns the file a page's URL names in the site, or None.

        Args:
            url: The URL as the page writes it.
            base: The folder the page's relative URLs start from.
            where: The page's name, for errors.

        Returns:
            The file's absolute path, or None for a URL off the site or
            inline data.

        Raises:
            SystemExit: When the URL carries a query other than a stamp or a
                fragment, or names no file in the site.
        """
        parts = urlsplit(url)
        if parts.scheme or parts.netloc or not parts.path:
            return None
        if parts.fragment or (parts.query and STAMPED.search(url) is None):
            sys.exit(
                f"{where}: {url}: a local script or stylesheet's URL may"
                " carry only its stamp (?v=...)"
            )
        path = unquote(parts.path)
        start = self.site if path.startswith("/") else base
        full = os.path.normpath(os.path.join(start, path.lstrip("/")))
        if not inside(self.site, full):
            sys.exit(f"{where}: {url} is not a file in {self.site}")
        return full

    def _page(self, path, base):
        """Works out the stamps of one page's scripts and stylesheets.

        Args:
            path: The page or template.
            base: The folder its relative URLs start from.

        Raises:
            SystemExit: As _local(), or for an unquoted src or href.
        """
        text = read(path)
        where = os.path.relpath(path)

        def stamp_tag(tag):
            attrs = tag["attrs"]
            found = {m["key"].lower(): m for m in ATTR.finditer(attrs)}
            kind = tag["tag"].lower()
            key = "src" if kind == "script" else "href"
            rels = found.get("rel")
            if kind == "link" and (
                rels is None
                or "stylesheet" not in rels["value"].lower().split()
            ):
                return tag[0]
            if key not in found:
                if BARE.search(attrs):
                    sys.exit(f"{where}: quote the {key} of {tag[0]}")
                return tag[0]
            m = found[key]
            named = self._local(m["value"], base, where)
            if named is None:
                return tag[0]
            want = f"{unstamped(m['value'])}?v={self.stamp_of(named)}"
            if m["value"] != want:
                self.stale.append((path, m["value"], want))
            new = f"{m['lead']}{m['q']}{want}{m['q']}"
            attrs = attrs[: m.start()] + new + attrs[m.end() :]
            return f"<{tag['tag']}{attrs}>"

        self.found[path], self.texts[path] = text, TAG.sub(stamp_tag, text)

    def changed(self):
        """Returns the files whose text the stamps change, by absolute path.

        Returns:
            A dict from path to the stamped text, for the files that differ
            from it on disk.
        """
        return {
            path: text
            for path, text in self.texts.items()
            if text != self.found[path]
        }


def write_one(path, text):
    """Writes text to path in one step (a temporary file, then a rename).

    Args:
        path: The file to write.
        text: Its text.
    """
    with open(path + ".tmp", "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(path + ".tmp", path)


def main(argv=None):
    """Writes or checks the stamps.

    Args:
        argv: The command line's arguments, or None for sys.argv's.

    Returns:
        0 when every stamp is right (or has been written), STALE when --check
        finds one missing or stale.
    """
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", required=True, help="the site's folder (docs)")
    ap.add_argument(
        "--template",
        action="append",
        default=[],
        help="a page made from this template, read as if in --site",
    )
    ap.add_argument("--check", action="store_true", help="compare only")
    args = ap.parse_args(argv)
    site = Site(args.site, args.template)
    changed = site.changed()
    if args.check:
        for path, have, want in site.stale:
            print(f"{os.path.relpath(path)}: {have} should be {want}")
        if changed:
            print(
                "run ./build.sh stamp (or ./build.sh site-data) and commit the"
                " pages and scripts it changes"
            )
            return STALE
        print(f"{args.site}: every script and stylesheet is stamped")
        return 0
    for path, text in changed.items():
        write_one(path, text)
        print(f"stamped {os.path.relpath(path)}")
    if not changed:
        print(f"{args.site}: every script and stylesheet is stamped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
