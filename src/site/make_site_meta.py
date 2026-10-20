"""make_site_meta.py: the website's machine-readable files, from the site.

Writes three things, each from what the site and the repository already say,
so nothing here types a page's title, a description, a figure or a URL:

- docs/llms.txt (the llms.txt proposal, https://llmstxt.org/): the site's
  name as the H1, its home page's meta description as the summary, its
  footer's line on who makes it, then H2 lists: every indexable page in the
  sitemap's order with its title, canonical URL and meta description; the
  public record the pages link (Notice No. 243, the docket, the boundary
  documents); and the GeoJSON downloads The map links.
- A JSON-LD block (schema.org) in the head of every indexable page, and of
  src/site/walk.template.html, between the SITE-META markers: WebSite on the
  home page; WebPage on each page, from its own head; a Place on the page
  that explains the boundary (The boundary), described by that page's own
  sentence; and a Dataset for each GeoJSON download on the page that offers
  them with its paragraph on the data (The map), licensed as LICENSE.txt
  says and credited as ABOUT.md credits the GIS work. The boxes come from
  docs/data/boundary.geojson. A page marked noindex gets no block.
- docs/.well-known/security.txt (RFC 9116): the two reporting routes in
  SECURITY.md, its GitHub URL as the Policy, the file's own URL as the
  Canonical, and an Expires under a year out. The Expires is the one value
  time changes: a write keeps it while it is more than REFRESH_DAYS away and
  otherwise sets it EXPIRES_DAYS from today; the check fails only when it
  has passed or is more than a year away, and warns inside REFRESH_DAYS, so
  ./build.sh site-data (or site-meta) renews it before it lapses.

Run it after make_site_data.py has written walk.html from its template (the
template carries the same block, so the two stay identical). Standard
library only, so the lint workflow can test it.

Usage (the project .venv, -E -s):
  make_site_meta.py [--site DIR] [--template PAGE] [--check]
With --check nothing is written; it exits 3 when a file is stale. Other
errors exit 1.
"""

import argparse
import datetime
import html
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
STALE = 3  # --check's exit status when a file is stale
SITE = os.path.join(ROOT, "docs")
TEMPLATE = os.path.join(ROOT, "src", "site", "walk.template.html")
SECURITY_MD = os.path.join(ROOT, "SECURITY.md")
LICENSE_TXT = os.path.join(ROOT, "LICENSE.txt")
ABOUT_MD = os.path.join(ROOT, "ABOUT.md")
LLMS = "llms.txt"
SECURITY_TXT = os.path.join(".well-known", "security.txt")
EXPIRES_DAYS = 360  # RFC 9116 recommends less than a year
REFRESH_DAYS = 60  # a write renews an Expires this close; the check warns
GEOJSON_TYPE = "application/geo+json"  # RFC 7946's media type
START = "<!-- SITE-META: made by src/site/make_site_meta.py; do not edit -->"
END = "<!-- /SITE-META -->"
BLOCK = re.compile(re.escape(START) + r".*?" + re.escape(END) + r"\n?", re.S)
# What may not stand bare in a <script> data block, as JSON escapes it.
SCRIPT_SAFE = {
    "<": "\\u003c",
    ">": "\\u003e",
    "&": "\\u0026",
    " ": "\\u2028",
    " ": "\\u2029",
}


def read(path):
    """Returns a text file's contents.

    Args:
        path: The file.

    Returns:
        Its text.

    Raises:
        SystemExit: When it cannot be read.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as error:
        sys.exit(f"{os.path.relpath(path, ROOT)}: {error}")


def write(path, text):
    """Writes a text file, with LF line ends, making its folder.

    Args:
        path: The file.
        text: What it holds.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def plain(fragment):
    """Returns an HTML fragment as plain text, on one line.

    A <br> is a space; <small> and aria-hidden spans (an arrow) are dropped
    by the caller where they are not part of the name.

    Args:
        fragment: The HTML.

    Returns:
        Its text, entities decoded and spaces collapsed.
    """
    text = re.sub(r"<br\s*/?>", " ", fragment)
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(html.unescape(text).split())


def link_name(inner):
    """Returns a link's name and its note, from the link's inner HTML.

    The site's links read "Name <small>note</small><span aria-hidden>↗</span>".

    Args:
        inner: The inner HTML of the <a>.

    Returns:
        (name, note); note is "" when the link has no <small>.
    """
    inner = re.sub(r'<span aria-hidden="true">.*?</span>', "", inner)
    small = re.search(r"<small>(.*?)</small>", inner, re.S)
    note = plain(small.group(1)) if small else ""
    name = plain(re.sub(r"<small>.*?</small>", "", inner, flags=re.S))
    return name, note


def need(match, where, what):
    """Returns a regex match, or stops when there is none.

    Args:
        match: The match, or None.
        where: The file, for the message.
        what: What was looked for, for the message.

    Returns:
        The match.

    Raises:
        SystemExit: When match is None.
    """
    if match is None:
        sys.exit(f"{os.path.relpath(where, ROOT)}: no {what}")
    return match


def head(path):
    """Returns what a page's head says about it.

    Args:
        path: The page.

    Returns:
        A dict: text (the page), title, description, canonical, noindex,
        site_name (og:site_name or None) and lang.
    """
    text = read(path)
    title = need(re.search(r"<title>(.*?)</title>", text, re.S), path, "title")
    desc = need(
        re.search(r'<meta name="description" content="([^"]*)">', text),
        path,
        "meta description",
    )
    canon = re.search(r'<link rel="canonical" href="([^"]+)">', text)
    site = re.search(r'<meta property="og:site_name" content="([^"]*)">', text)
    lang = need(re.search(r'<html lang="([^"]+)"', text), path, "html lang")
    return {
        "text": text,
        "title": html.unescape(title.group(1)).strip(),
        "description": html.unescape(desc.group(1)),
        "canonical": canon.group(1) if canon else None,
        "noindex": re.search(r'<meta name="robots"', text) is not None,
        "site_name": html.unescape(site.group(1)) if site else None,
        "lang": lang.group(1),
    }


def sitemap_urls(site):
    """Returns the sitemap's URLs, in its order.

    Args:
        site: The site's folder.

    Returns:
        The <loc> values.
    """
    path = os.path.join(site, "sitemap.xml")
    urls = re.findall(r"<loc>([^<]+)</loc>", read(path))
    if not urls:
        sys.exit(f"{os.path.relpath(path, ROOT)}: no <loc>")
    return urls


class Site:
    """The site's pages, read once.

    Attributes:
        folder: docs/.
        url: The home page's canonical URL, ending in /.
        name: The site's name (the home page's og:site_name).
        lang: The home page's language.
        pages: {file name: head()} for every page in the folder.
    """

    def __init__(self, folder):
        """Reads every page's head.

        Args:
            folder: docs/.
        """
        self.folder = folder
        self.pages = {
            name: head(os.path.join(folder, name))
            for name in sorted(os.listdir(folder))
            if name.endswith(".html")
        }
        home = self.pages.get("index.html")
        if home is None or not home["canonical"] or not home["site_name"]:
            sys.exit("docs/index.html: needs a canonical URL and og:site_name")
        self.url = home["canonical"]
        if not self.url.endswith("/"):
            sys.exit(f"docs/index.html: canonical {self.url} must end in /")
        self.name = home["site_name"]
        self.lang = home["lang"]

    def page_for(self, url):
        """Returns the page file a canonical URL names.

        Args:
            url: A URL on the site.

        Returns:
            The page's file name in docs/.

        Raises:
            SystemExit: When the URL is not one of the site's pages.
        """
        if not url.startswith(self.url):
            sys.exit(f"sitemap: {url} is not on {self.url}")
        name = url[len(self.url) :] or "index.html"
        if name not in self.pages:
            sys.exit(f"sitemap: {url} has no page in docs/")
        return name

    def indexed(self):
        """Returns the pages search engines may index, in the sitemap's order.

        Returns:
            [(file name, head())], each page's canonical its sitemap URL.
        """
        out = []
        for url in sitemap_urls(self.folder):
            name = self.page_for(url)
            page = self.pages[name]
            if page["noindex"] or page["canonical"] != url:
                sys.exit(f"sitemap: {url} is noindex or not {name}'s canonical")
            out.append((name, page))
        return out

    def short_title(self, page):
        """Returns a page's title without the site's name after it.

        Args:
            page: A head().

        Returns:
            The title.
        """
        suffix = f" · {self.name}"
        title = page["title"]
        return title[: -len(suffix)] if title.endswith(suffix) else title


def footer_line(page_text, where):
    """Returns the footer's line on who makes the site.

    Args:
        page_text: The home page.
        where: Its path, for a message.

    Returns:
        The text of the footer's paragraph.
    """
    footer = need(
        re.search(r"<footer[^>]*>(.*?)</footer>", page_text, re.S),
        where,
        "footer",
    )
    para = need(re.search(r"<p>(.*?)</p>", footer.group(1), re.S), where, "p")
    return plain(para.group(1))


def external_links(page_text, base):
    """Returns a page's external "text-link" links, in order.

    Args:
        page_text: The page.
        base: The site's URL; links on it are not external.

    Returns:
        [(url, name, note)].
    """
    out = []
    pattern = r'<a class="text-link[^"]*" href="(https://[^"]+)">(.*?)</a>'
    for m in re.finditer(pattern, page_text, re.S):
        url = html.unescape(m.group(1))
        if url.startswith(base):
            continue
        name, note = link_name(m.group(2))
        out.append((url, name, note))
    return out


def data_section(page_text):
    """Returns a page's paragraph on its data and its GeoJSON downloads.

    The map's panel has <section id="about-data"> with one paragraph and a
    download link for each GeoJSON file.

    Args:
        page_text: The page.

    Returns:
        (paragraph, [(relative href, name)]), or None when the page has no
        such section.
    """
    sec = re.search(
        r'<section id="about-data"[^>]*>(.*?)</section>', page_text, re.S
    )
    if sec is None:
        return None
    para = re.search(r"<p>(.*?)</p>", sec.group(1), re.S)
    links = [
        (html.unescape(m.group(1)), link_name(m.group(2))[0])
        for m in re.finditer(
            r'<a [^>]*href="(data/[^"]+\.geojson)"[^>]*\bdownload\b[^>]*>'
            r"(.*?)</a>",
            sec.group(1),
            re.S,
        )
    ]
    if para is None or not links:
        return None
    return plain(para.group(1)), links


def download_label(page_text):
    """Returns the short label the map puts by its downloads.

    Args:
        page_text: The page.

    Returns:
        Its text ("GeoJSON, CC0"), or "" when there is none.
    """
    m = re.search(r'<p class="lp-dl"><span>(.*?)</span>', page_text, re.S)
    return plain(m.group(1)) if m else ""


def place_sentence(page_text):
    """Returns The boundary page's sentence on where the line runs, or None.

    Args:
        page_text: The page.

    Returns:
        The first paragraph of its boundary-explanation section, or None.
    """
    m = re.search(
        r'<section class="boundary-explanation[^"]*"[^>]*>\s*<p>(.*?)</p>',
        page_text,
        re.S,
    )
    return plain(m.group(1)) if m else None


def boundary_box(site):
    """Returns the boundary's bounding box as schema.org writes a box.

    Args:
        site: docs/.

    Returns:
        "south west north east" (latitude then longitude, 4 decimals,
        rounded outward), from data/boundary.geojson.
    """
    path = os.path.join(site, "data", "boundary.geojson")
    try:
        data = json.loads(read(path))
    except ValueError as error:
        sys.exit(f"{os.path.relpath(path, ROOT)}: {error}")
    xs, ys = [], []

    def walk(coords):
        if coords and isinstance(coords[0], (int, float)):
            xs.append(coords[0])
            ys.append(coords[1])
            return
        for c in coords:
            walk(c)

    for feature in data.get("features", []):
        walk(feature["geometry"]["coordinates"])
    if not xs:
        sys.exit(f"{os.path.relpath(path, ROOT)}: no coordinates")

    def down(v):
        return f"{math.floor(v * 1e4) / 1e4:.4f}"

    def up(v):
        return f"{math.ceil(v * 1e4) / 1e4:.4f}"

    return f"{down(min(ys))} {down(min(xs))} {up(max(ys))} {up(max(xs))}"


def license_url():
    """Returns the license's versioned URL, from LICENSE.txt.

    Returns:
        The Creative Commons legal code URL it names.
    """
    m = need(
        re.search(r"https://creativecommons\.org/\S+", read(LICENSE_TXT)),
        LICENSE_TXT,
        "Creative Commons URL",
    )
    return m.group(0)


def gis_credit():
    """Returns the name ABOUT.md credits with the GIS work.

    ABOUT.md: "**Name** wrote the boundary narrative, drew the boundary, and
    did all the spatial work for the GIS layers."

    Returns:
        The name.
    """
    text = " ".join(read(ABOUT_MD).split())
    m = need(
        re.search(
            r"\*\*([^*]+)\*\*[^*]*?drew the boundary, and did all the spatial"
            r" work for the GIS layers",
            text,
        ),
        ABOUT_MD,
        "credit for the GIS layers",
    )
    return m.group(1)


def llms_txt(site):
    """Returns docs/llms.txt.

    Args:
        site: A Site.

    Returns:
        The file's text.
    """
    home = site.pages["index.html"]
    where = os.path.join(site.folder, "index.html")
    lines = [
        f"# {site.name}",
        "",
        f"> {home['description']}",
        "",
        footer_line(home["text"], where),
        "",
        "## Pages",
        "",
    ]
    lines += [
        f"- [{site.short_title(p)}]({p['canonical']}): {p['description']}"
        for _, p in site.indexed()
    ]
    # The public record: Notice No. 243 and the docket (Status), then the
    # boundary documents and the dashboard (The boundary), each URL once.
    seen = set()
    record = []
    for name in ("status.html", "boundary.html"):
        for url, title, note in external_links(
            site.pages[name]["text"], site.url
        ):
            if url not in seen:
                seen.add(url)
                record.append(
                    f"- [{title}]({url})" + (f": {note}" if note else "")
                )
    if record:
        lines += ["", "## The public record", "", *record]
    data = []
    for _, page in site.indexed():
        found = data_section(page["text"])
        if found is None:
            continue
        label = download_label(page["text"])
        for href, title in found[1]:
            entry = f"- [{title}]({site.url}{href})"
            data.append(entry + (f": {label}" if label else ""))
        break  # one page offers them
    if data:
        lines += ["", "## Data", "", *data]
    return "\n".join(lines) + "\n"


def jsonld(site, name, page, box):
    """Returns the JSON-LD graph for one indexable page.

    Args:
        site: A Site.
        name: The page's file name.
        page: Its head().
        box: The boundary's box (boundary_box()).

    Returns:
        A dict, ready for json.dumps.
    """
    url = page["canonical"]
    website = f"{site.url}#website"
    graph = []
    if name == "index.html":
        graph.append(
            {
                "@type": "WebSite",
                "@id": website,
                "url": site.url,
                "name": site.name,
                "description": page["description"],
                "inLanguage": site.lang,
            }
        )
    webpage = {
        "@type": "WebPage",
        "@id": f"{url}#webpage",
        "url": url,
        "name": page["title"],
        "description": page["description"],
        "inLanguage": page["lang"],
        "isPartOf": {"@id": website},
    }
    graph.append(webpage)
    sentence = place_sentence(page["text"])
    if sentence:
        place = f"{url}#place"
        webpage["about"] = {"@id": place}
        graph.append(
            {
                "@type": "Place",
                "@id": place,
                "name": f"{site.name} (proposed)",
                "description": sentence,
                "geo": {"@type": "GeoShape", "box": box},
            }
        )
    found = data_section(page["text"])
    if found:
        paragraph, links = found
        if len(paragraph) < 50:
            sys.exit(f"docs/{name}: the data paragraph is under 50 characters")
        creator = {"@type": "Person", "name": gis_credit()}
        licence = license_url()
        for href, title in links:
            stem = os.path.splitext(os.path.basename(href))[0]
            graph.append(
                {
                    "@type": "Dataset",
                    "@id": f"{url}#{stem}",
                    "name": f"{site.name}: {title} (GeoJSON)",
                    "description": paragraph,
                    "url": url,
                    "license": licence,
                    "creator": creator,
                    "isAccessibleForFree": True,
                    "spatialCoverage": {
                        "@type": "Place",
                        "geo": {"@type": "GeoShape", "box": box},
                    },
                    "distribution": [
                        {
                            "@type": "DataDownload",
                            "contentUrl": f"{site.url}{href}",
                            "encodingFormat": GEOJSON_TYPE,
                        }
                    ],
                }
            )
    return {"@context": "https://schema.org", "@graph": graph}


def script_block(graph):
    """Returns the marked <script> block for a page's head.

    Args:
        graph: jsonld()'s dict.

    Returns:
        The block, the markers around it, ending in a newline.
    """
    text = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
    for char, escaped in SCRIPT_SAFE.items():
        text = text.replace(char, escaped)
    return (
        f'{START}\n<script type="application/ld+json">{text}</script>\n{END}\n'
    )


def with_block(text, block, where):
    """Returns a page with its JSON-LD block set, or removed.

    Args:
        text: The page.
        block: script_block()'s text, or "" for none.
        where: The page's path, for a message.

    Returns:
        The page: the block just before </head>, in place of any old one.
    """
    text = BLOCK.sub("", text)
    at = text.find("</head>")
    if at < 0:
        sys.exit(f"{os.path.relpath(where, ROOT)}: no </head>")
    if block and not text[:at].endswith("\n"):
        block = "\n" + block
    return text[:at] + block + text[at:]


def security_routes():
    """Returns SECURITY.md's reporting routes and its repository's URL.

    Returns:
        (advisory URL, email address, repository URL).
    """
    text = read(SECURITY_MD)
    report = need(
        re.search(r"^\[report\]:\s*(https://\S+)$", text, re.M),
        SECURITY_MD,
        "[report] link",
    ).group(1)
    email = need(
        re.search(r"\*\*By email:\*\*\s*([\w.+-]+@[\w.-]+\w)", text),
        SECURITY_MD,
        "email",
    ).group(1)
    tail = "/security/advisories/new"
    if not report.startswith("https://github.com/") or not report.endswith(
        tail
    ):
        sys.exit(f"SECURITY.md: {report} is not a GitHub advisory link")
    return report, email, report[: -len(tail)]


def security_txt(site, expires):
    """Returns docs/.well-known/security.txt.

    Args:
        site: A Site.
        expires: The Expires value (RFC 3339).

    Returns:
        The file's text.
    """
    report, email, repo = security_routes()
    return "\n".join(
        [
            f"# Security contacts for {site.url} (RFC 9116), from SECURITY.md.",
            "# Made by src/site/make_site_meta.py; do not edit.",
            f"Contact: {report}",
            f"Contact: mailto:{email}",
            f"Expires: {expires}",
            f"Preferred-Languages: {site.lang}",
            f"Canonical: {site.url}{SECURITY_TXT.replace(os.sep, '/')}",
            f"Policy: {repo}/blob/main/SECURITY.md",
            "",
        ]
    )


def parse_expires(text):
    """Returns a security.txt's Expires as a datetime, or None.

    Args:
        text: The file, or None.

    Returns:
        The aware UTC datetime, or None when there is none or it does not
        parse.
    """
    if not text:
        return None
    m = re.search(r"^Expires: (\S+)$", text, re.M)
    if not m:
        return None
    try:
        when = datetime.datetime.fromisoformat(m.group(1))
    except ValueError:
        return None
    if when.tzinfo is None:
        return None
    return when.astimezone(datetime.UTC)


def fmt(when):
    """Returns a datetime as security.txt writes it.

    Args:
        when: An aware datetime.

    Returns:
        RFC 3339, UTC, to the second ("2027-10-14T00:00:00Z").
    """
    return when.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_expires(old, now):
    """Returns the Expires a write gives: the old one or a fresh one.

    Args:
        old: The current Expires, or None.
        now: The time now (aware).

    Returns:
        old while it is more than REFRESH_DAYS away and under a year;
        otherwise midnight UTC EXPIRES_DAYS from today.
    """
    if old and (
        now + datetime.timedelta(days=REFRESH_DAYS)
        < old
        <= now + datetime.timedelta(days=365)
    ):
        return old
    today = now.astimezone(datetime.UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return today + datetime.timedelta(days=EXPIRES_DAYS)


def expires_problem(when, now):
    """Returns why an Expires fails the check, or None.

    Args:
        when: The Expires, or None.
        now: The time now (aware).

    Returns:
        A message, or None when it is in the future and within a year.
    """
    if when is None:
        return "no Expires in RFC 3339 with a time zone"
    if when <= now:
        return f"Expires {fmt(when)} has passed"
    if when > now + datetime.timedelta(days=365):
        return f"Expires {fmt(when)} is more than a year away"
    return None


def outputs(site_dir, template, now):
    """Returns every file this makes, as it should be.

    Args:
        site_dir: docs/.
        template: The walk page's template.
        now: The time now (aware), for security.txt's Expires.

    Returns:
        {path: text}.
    """
    site = Site(site_dir)
    box = boundary_box(site_dir)
    out = {os.path.join(site_dir, LLMS): llms_txt(site)}
    indexed = dict(site.indexed())
    for name, page in site.pages.items():
        block = (
            script_block(jsonld(site, name, page, box))
            if name in indexed
            else ""
        )
        path = os.path.join(site_dir, name)
        out[path] = with_block(page["text"], block, path)
        if name == "walk.html":
            tpl = head(template)
            if tpl["canonical"] != page["canonical"]:
                sys.exit("the walk template's canonical is not walk.html's")
            out[template] = with_block(
                tpl["text"],
                script_block(jsonld(site, name, tpl, box)) if block else "",
                template,
            )
    sec = os.path.join(site_dir, SECURITY_TXT)
    old = read(sec) if os.path.exists(sec) else None
    out[sec] = security_txt(site, fmt(new_expires(parse_expires(old), now)))
    return out


def stale(path, text, now):
    """Returns why a file differs from what it should be, or None.

    security.txt's Expires is checked by expires_problem(), not compared.

    Args:
        path: The file.
        text: What it should hold.
        now: The time now (aware).

    Returns:
        A message, or None when it is current.
    """
    where = os.path.relpath(path, ROOT)
    if not os.path.exists(path):
        return f"{where} is missing"
    have = read(path)
    if path.endswith(SECURITY_TXT):
        problem = expires_problem(parse_expires(have), now)
        if problem:
            return f"{where}: {problem}"
        expires = re.compile(r"^Expires: .*$", re.M)
        if expires.sub("", have) != expires.sub("", text):
            return f"{where} differs from SECURITY.md and the site"
        return None
    return None if have == text else f"{where} is stale"


def main():
    """Writes, or checks, llms.txt, the JSON-LD blocks and security.txt."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--site", default=SITE, help="the site's folder (docs/)")
    ap.add_argument("--template", default=TEMPLATE, help="the walk template")
    ap.add_argument(
        "--check", action="store_true", help="write nothing; exit 3 if stale"
    )
    args = ap.parse_args()
    site_dir = os.path.abspath(args.site)
    template = os.path.abspath(args.template)
    now = datetime.datetime.now(datetime.UTC)
    made = outputs(site_dir, template, now)
    if args.check:
        problems = [p for p in (stale(k, v, now) for k, v in made.items()) if p]
        if problems:
            print("\n".join(problems))
            print("the site's meta files are stale: run ./build.sh site-meta")
            sys.exit(STALE)
        when = parse_expires(read(os.path.join(site_dir, SECURITY_TXT)))
        if when - now < datetime.timedelta(days=REFRESH_DAYS):
            print(
                f"security.txt expires {fmt(when)}: run ./build.sh site-meta"
                " to renew it",
                file=sys.stderr,
            )
        print(f"site meta: {len(made)} files current")
        return
    changed = 0
    for path, text in made.items():
        if not os.path.exists(path) or read(path) != text:
            write(path, text)
            changed += 1
            print(f"wrote {os.path.relpath(path, ROOT)}")
    print(f"site meta: {changed} of {len(made)} files written")


if __name__ == "__main__":
    main()
