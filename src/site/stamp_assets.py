"""stamp_assets.py: a version on every script and stylesheet the site loads.

GitHub Pages serves every file with cache-control: max-age=600, so a browser
that loaded assets/timeline.js shortly before a deploy can keep the old file
for ten minutes after it (#138). So every URL by which the site loads one of
its own scripts or stylesheets carries a short hash of the file it names, as
in assets/timeline.js?v=3f2a91c: a changed file gets a new URL, which a
browser fetches at once. Stamped:

- in the pages (docs/**/*.html, and the templates named): each local
  <script src>, and each local href of a <link> whose rel is stylesheet,
  modulepreload or preload;
- in the site's scripts (docs/**/*.js): each string in plain quotes holding a
  relative module path, "./name.js" or "../x/name.js", stamped or not. That
  is every way the site's own modules name each other: the static imports
  (import ... from "./maps.js") and dynamic ones (import("./maps.js"), or
  import(MAPS) where const MAPS = "./maps.js" in the same script).

A module's hash is taken after its own imports are stamped, so a change to
map-config.js changes the stamp maps.js gives it, and so maps.js's own hash
and the stamps of explore.js and walk.js that import it, up to the pages.
Every importer of a module names it with the same URL, so a page never loads
two copies of one module.

Whatever it cannot stamp stops it (exit 1), naming where, rather than being
skipped: a src or href without quotes; a local URL with another query or a
fragment, or naming no file in the site; in a script, an import of anything
but a relative path in plain quotes or Esri's SDK (a URL on https, or one of
its @arcgis/core/ modules), a template literal, a module path with another
query, import() of anything but such a path or a constant holding one, an
import circle; a stylesheet with @import; an inline <script> that names a
module (move it into a file); a site folder that is missing or has no pages.

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
exits 3 when a stamp is missing or stale, naming each.
"""

import argparse
import hashlib
import html
from html.parser import HTMLParser
import os
import re
import sys
from urllib.parse import unquote
from urllib.parse import urlsplit

STALE = 3  # --check's exit status when a stamp is missing or stale
DIGITS = 7  # hex digits of the SHA-256 in a stamp, as in a short git hash
PAGES = (".html",)
MODULES = (".js", ".mjs")
# A <link> with one of these rels loads the file its href names.
LOADING_RELS = {"stylesheet", "modulepreload", "preload"}
# A version stamp at the end of a URL; unstamped() takes it off.
STAMPED = re.compile(r"\?v=[0-9a-f]*$")
# One attribute of a start tag, with its value quoted either way or bare.
ATTR = re.compile(
    r"(?P<lead>\s+(?P<key>[^\s\"'>/=]+)\s*=\s*)"
    r"(?:\"(?P<dq>[^\"]*)\"|'(?P<sq>[^']*)'|(?P<bare>[^\s\"'=<>`]+))"
)
# What a script may import besides the site's own modules: Esri's SDK, by its
# URL or by the names of its modules (loaded from js.arcgis.com).
EXTERNAL = re.compile(r"(?:https://|@arcgis/core/)\S*")
# A relative module path, as the site's modules name each other.
RELATIVE = re.compile(r"\.\.?/[^\"'`\s?]*\.m?js(?:\?v=[0-9a-f]*)?")
# A string holding a relative module path, in any quotes, with any query.
MODULE_PATH = re.compile(
    r"(?P<q>[\"'`])(?P<path>\.\.?/[^\"'`\s?]*\.m?js)"
    r"(?P<query>\?[^\"'`\s]*)?(?P=q)"
)
# The specifier of a static import or export ... from, at a line's start.
STATIC = re.compile(
    r"^[ \t]*(?:import|export)\b[\w\s{},*$]*?\bfrom\s*"
    r"(?P<q>[\"'`])(?P<spec>[^\"'`]*)(?P=q)"
    r"|^[ \t]*import\s*(?P<q2>[\"'`])(?P<spec2>[^\"'`]*)(?P=q2)",
    re.MULTILINE,
)
# A dynamic import() and what it is given: a string, a name, or neither.
DYNAMIC = re.compile(
    r"(?<![\w$.])import\s*\(\s*"
    r"(?:(?P<q>[\"'`])(?P<spec>[^\"'`]*)(?P=q)|(?P<name>[A-Za-z_$][\w$]*))?"
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


def digest(data):
    """Returns the stamp for a file's bytes: a short hash of them.

    Args:
        data: The file's bytes, as they will be served.

    Returns:
        The first DIGITS hex digits of their SHA-256.
    """
    return hashlib.sha256(data).hexdigest()[:DIGITS]


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


def unstampable_imports(text):
    """Returns what a script imports that the stamper cannot stamp.

    Args:
        text: A script's text (a module, or an inline script).

    Returns:
        A list of the imports, as written, that are neither Esri's SDK nor
        a relative module path in plain quotes (or, for import(), a constant
        in the same script holding one), and of the module paths written as
        a template literal or with a query other than a stamp.
    """
    bad = []
    for m in STATIC.finditer(text):
        q, spec = (m["q"], m["spec"]) if m["q"] else (m["q2"], m["spec2"])
        if EXTERNAL.fullmatch(spec):
            continue
        if q == "`" or not RELATIVE.fullmatch(spec):
            bad.append(f"import {q}{spec}{q}")
    for m in DYNAMIC.finditer(text):
        if m["name"]:
            held = re.search(
                rf"\bconst\s+{re.escape(m['name'])}\s*=\s*([\"'])(?P<spec>"
                rf"{RELATIVE.pattern}|{EXTERNAL.pattern})\1",
                text,
            )
            if not held:
                bad.append(f"import({m['name']})")
        elif m["q"] is None or m["q"] == "`":
            bad.append(m[0].strip() + "...")
        elif not (
            EXTERNAL.fullmatch(m["spec"]) or RELATIVE.fullmatch(m["spec"])
        ):
            bad.append(f"import({m['q']}{m['spec']}{m['q']})")
    for m in MODULE_PATH.finditer(text):
        query = m["query"] or ""
        if m["q"] == "`" or (query and not STAMPED.fullmatch(query)):
            bad.append(m[0])
    return bad


class Tags(HTMLParser):
    """A page's <script> and <link> tags, where they are, and inline scripts.

    Attributes:
        tags: (line, column, tag, attributes, the tag as written), for every
            <script> and <link> start tag.
        inline: The text of every <script> without a src.
    """

    def __init__(self):
        """Starts an empty page."""
        super().__init__(convert_charrefs=False)
        self.tags, self.inline = [], []
        self._script = None

    def handle_starttag(self, tag, attrs):
        """Keeps a <script> or <link> tag; starts an inline script's text."""
        if tag in ("script", "link"):
            line, column = self.getpos()
            raw = self.get_starttag_text()
            self.tags.append((line, column, tag, attrs, raw))
        if tag == "script" and not dict(attrs).get("src"):
            self._script = []

    def handle_data(self, data):
        """Collects an inline script's text."""
        if self._script is not None:
            self._script.append(data)

    def handle_endtag(self, tag):
        """Ends an inline script."""
        if tag == "script" and self._script is not None:
            self.inline.append("".join(self._script))
            self._script = None


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
            SystemExit: When the site is not a folder with pages, a template
                is missing, or the site loads something it cannot stamp (see
                the module's docstring).
        """
        self.site = os.path.abspath(site)
        self.texts, self.found, self.stale = {}, {}, []
        self._stamps = {}
        self._visiting = []
        if not os.path.isdir(self.site):
            sys.exit(f"{site}: not a folder: no site to stamp")
        modules, pages = [], []
        for folder, dirs, names in os.walk(self.site):
            dirs.sort()
            for name in sorted(names):
                path = os.path.join(folder, name)
                if name.endswith(MODULES):
                    modules.append(path)
                elif name.endswith(PAGES):
                    pages.append((path, folder))
        if not pages:
            sys.exit(f"{site}: no pages (*.html): no site to stamp")
        for template in templates:
            if not os.path.isfile(template):
                sys.exit(f"{template}: no such template")
            pages.append((os.path.abspath(template), self.site))
        for path in modules:
            self.stamp_of(path)
        for path, base in pages:
            self._page(path, base)

    def stamp_of(self, path):
        """Returns the stamp of a file the site loads.

        A module's own imports are stamped first, and its stamp is the hash
        of its text with them.

        Args:
            path: An absolute path to a file in the site.

        Returns:
            The file's stamp.

        Raises:
            SystemExit: When a module imports what cannot be stamped, names
                a module that is not in the site, or modules import each
                other in a circle; or a stylesheet uses @import.
        """
        if path in self._stamps:
            return self._stamps[path]
        where = os.path.relpath(path, self.site)
        if not path.endswith(MODULES):
            with open(path, "rb") as fh:
                data = fh.read()
            if path.endswith(".css") and re.search(rb"@import\b", data, re.I):
                sys.exit(
                    f"{where}: @import is not stamped: load the stylesheet"
                    " from the pages with its own <link>"
                )
            self._stamps[path] = digest(data)
            return self._stamps[path]
        if path in self._visiting:
            cycle = [*self._visiting[self._visiting.index(path) :], path]
            names = " -> ".join(os.path.relpath(p, self.site) for p in cycle)
            sys.exit(f"the site's modules import in a circle: {names}")
        self._visiting.append(path)
        text = read(path)
        bad = unstampable_imports(text)
        if bad:
            sys.exit(
                f"{where}: cannot stamp {', '.join(bad)}: name the site's own"
                ' modules by a relative path in plain quotes ("./name.js"),'
                " or import() a constant holding one"
            )
        folder = os.path.dirname(path)

        def stamp_import(m):
            named = os.path.normpath(os.path.join(folder, m["path"]))
            if not inside(self.site, named):
                sys.exit(f"{where}: {m['path']} is not a module in the site")
            want = f"{m['path']}?v={self.stamp_of(named)}"
            have = m["path"] + (m["query"] or "")
            if have != want:
                self.stale.append((path, have, want))
            return f"{m['q']}{want}{m['q']}"

        stamped = MODULE_PATH.sub(stamp_import, text)
        self._visiting.pop()
        self.found[path], self.texts[path] = text, stamped
        self._stamps[path] = digest(stamped.encode("utf-8"))
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
                f"{where}: {url}: a local script's or stylesheet's URL may"
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
            SystemExit: As _local(), for a src or href it cannot read or
                that is not quoted, or for an inline script that names a
                module.
        """
        text = read(path)
        where = os.path.relpath(path)
        parser = Tags()
        parser.feed(text)
        parser.close()
        for script in parser.inline:
            names = MODULE_PATH.findall(script) or unstampable_imports(script)
            if names:
                sys.exit(
                    f"{where}: an inline <script> names a module, which is"
                    " not stamped: move the script into a file"
                )
        starts = [0] + [i + 1 for i, c in enumerate(text) if c == "\n"]
        edits = []
        for line, column, tag, attrs, raw in parser.tags:
            at = starts[line - 1] + column
            if not text.startswith(raw, at):
                sys.exit(f"{where}:{line}: cannot place {raw}")
            values = dict(attrs)
            key = "src" if tag == "script" else "href"
            if tag == "link":
                rels = set((values.get("rel") or "").lower().split())
                if not rels & LOADING_RELS:
                    continue
            if not values.get(key):
                continue
            named = [m for m in ATTR.finditer(raw) if m["key"].lower() == key]
            if len(named) != 1:
                sys.exit(f"{where}:{line}: one {key}, please: {raw}")
            (m,) = named
            if m["bare"] is not None:
                sys.exit(f"{where}:{line}: quote the {key} of {raw}")
            q = '"' if m["dq"] is not None else "'"
            value = m["dq"] if m["dq"] is not None else m["sq"]
            if html.unescape(value) != values[key]:
                sys.exit(f"{where}:{line}: cannot read the {key} of {raw}")
            local = self._local(value, base, where)
            if local is None:
                continue
            want = f"{unstamped(value)}?v={self.stamp_of(local)}"
            if value != want:
                self.stale.append((path, value, want))
            new = raw[: m.start()] + f"{m['lead']}{q}{want}{q}" + raw[m.end() :]
            edits.append((at, at + len(raw), new))
        stamped = text
        for start, end, new in reversed(edits):
            stamped = stamped[:start] + new + stamped[end:]
        self.found[path], self.texts[path] = text, stamped

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
