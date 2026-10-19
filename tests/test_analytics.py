"""Google Analytics on the website: docs/assets/analytics.js.

Every page in docs/ (and the walk page's template, src/site/walk.template.html)
loads docs/assets/analytics.js once, in its head, deferred; no page or other
script names Google's tag (www.googletagmanager.com) or its collector, so
Google's tag comes only through analytics.js. The script loads gtag.js only on
the live site, never for an automated browser (navigator.webdriver: the site's
own browser tests never count), with Do Not Track or Global Privacy Control,
or with an empty measurement ID; it turns Google signals and ad
personalization off and sends nothing of its own but the page view. No form
puts what a visitor types into the page's address (Analytics reads the address
of every page it counts): every form is posted or mailed, and no script
writes the address bar. And, in node when it is installed (it is on GitHub's
Linux runners), the script is run against a made-up browser: on the live site
it loads gtag.js with those settings, and in every other case it does nothing.
Standard library only, so the lint workflow runs these.
"""

from html.parser import HTMLParser
import json
import os
import re
import shutil
import subprocess
from urllib.parse import urlsplit

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
ASSETS = os.path.join(DOCS, "assets")
SCRIPT = os.path.join(ASSETS, "analytics.js")
TEMPLATE = os.path.join(ROOT, "src", "site", "walk.template.html")
# every page as GitHub Pages serves it, and the template the walk page is
# made from: (the file, the page's path under docs/)
PAGES = sorted(
    [
        (
            os.path.join(folder, name),
            os.path.relpath(os.path.join(folder, name), DOCS),
        )
        for folder, _, names in os.walk(DOCS)
        for name in names
        if name.endswith(".html")
    ]
    + [(TEMPLATE, "walk.html")]
)
PAGE_IDS = [os.path.relpath(path, ROOT) for path, _ in PAGES]
SDK = "https://js.arcgis.com/5.1/"
HOST = "hickorysandsdistrictava.org"
GTAG = "https://www.googletagmanager.com/gtag/js?id="
# what only analytics.js may name: Google's tag, its collectors, a gtag call
GOOGLE_TAG = (
    "googletagmanager",
    "google-analytics",
    "analytics.google",
    "gtag(",
    "dataLayer",
)
NODE = shutil.which("node")
# Runs analytics.js (argv[1]) in a fresh context whose navigator, location,
# document and window are made up from the JSON on stdin; prints the scripts it
# added to the head and its dataLayer as JSON. node only runs it; the tests
# decide.
BRIDGE = """
const fs = require("node:fs");
const vm = require("node:vm");
const path = process.argv[1];
let input = "";
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  const env = JSON.parse(input);
  const added = [];
  const context = {
    navigator: env.navigator,
    location: { hostname: env.hostname },
    document: {
      createElement: (tag) => ({ tag }),
      head: { appendChild: (el) => (added.push(el), el) },
    },
  };
  context.window = context;
  if (env.windowDoNotTrack !== undefined) {
    context.doNotTrack = env.windowDoNotTrack;
  }
  vm.runInNewContext(fs.readFileSync(path, "utf8"), context, {
    filename: path,
  });
  const layer = context.dataLayer;
  process.stdout.write(JSON.stringify({
    added: added.map((e) => ({ tag: e.tag, src: e.src, async: e.async })),
    dataLayer: layer === undefined ? null : Array.from(layer, (call) =>
      Array.from(call, (x) =>
        Object.prototype.toString.call(x) === "[object Date]" ? "DATE" : x)),
  }));
});
"""
# a visitor's browser on the live site, counted
VISITOR = {
    "hostname": HOST,
    "navigator": {
        "webdriver": False,
        "doNotTrack": None,
        "globalPrivacyControl": False,
    },
}


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def measurement_id():
    """The measurement ID analytics.js holds."""
    found = re.findall(r'const MEASUREMENT_ID = "([^"]*)";', read(SCRIPT))
    assert len(found) == 1, "analytics.js holds one MEASUREMENT_ID"
    return found[0]


class Page(HTMLParser):
    """A page's scripts and forms, and whether each script is in the head."""

    def __init__(self):
        """Starts an empty page."""
        super().__init__(convert_charrefs=True)
        self.scripts = []  # (attributes, in the head)
        self.forms = []  # attributes
        self._head = False

    def handle_starttag(self, tag, attrs):
        """Keeps every script and form, and follows the head."""
        a = dict(attrs)
        if tag == "head":
            self._head = True
        elif tag == "body":
            self._head = False
        elif tag == "script":
            self.scripts.append((a, self._head))
        elif tag == "form":
            self.forms.append(a)

    def handle_endtag(self, tag):
        """Ends the head."""
        if tag == "head":
            self._head = False


def parse(path):
    p = Page()
    p.feed(read(path))
    p.close()
    return p


def resolves_to_the_script(page, src):
    """True when src, on the page at page (under docs/), is analytics.js."""
    url = urlsplit(src)
    if url.scheme or url.netloc:
        return False
    if url.path.startswith("/"):
        full = os.path.join(DOCS, url.path.lstrip("/"))
    else:
        full = os.path.join(DOCS, os.path.dirname(page), url.path)
    return os.path.normpath(full) == SCRIPT


def site_files():
    """Every page, script and stylesheet under docs/ but analytics.js."""
    found = sorted(
        os.path.join(folder, name)
        for folder, _, names in os.walk(DOCS)
        for name in names
        if name.endswith((".html", ".js", ".mjs", ".css"))
        and os.path.join(folder, name) != SCRIPT
    )
    return [*found, TEMPLATE]


# --- the pages ---------------------------------------------------------------


@pytest.mark.parametrize(("path", "page"), PAGES, ids=PAGE_IDS)
def test_every_page_loads_analytics_once_in_its_head(path, page):
    ours = [
        (a, head)
        for a, head in parse(path).scripts
        if resolves_to_the_script(page, a.get("src") or "")
    ]
    assert len(ours) == 1, f"loads analytics.js {len(ours)} times"
    attrs, head = ours[0]
    assert head, "analytics.js is loaded outside the head"
    assert "defer" in attrs or "async" in attrs, "neither defer nor async"
    assert "type" not in attrs, "a classic script: no type"


@pytest.mark.parametrize(("path", "page"), PAGES, ids=PAGE_IDS)
def test_the_pages_load_no_other_outside_script_than_the_sdk(path, page):
    outside = {
        a["src"]
        for a, _ in parse(path).scripts
        if a.get("src") and urlsplit(a["src"]).netloc
    }
    assert outside <= {SDK}, outside


@pytest.mark.parametrize("path", site_files(), ids=os.path.basename)
def test_only_analytics_js_names_google_s_tag(path):
    text = read(path)
    found = [name for name in GOOGLE_TAG if name in text]
    assert not found, f"{os.path.relpath(path, ROOT)} names {found}"


# --- the script --------------------------------------------------------------


def test_the_measurement_id_is_a_ga4_id_or_empty():
    assert re.fullmatch(r"(G-[A-Z0-9]+)?", measurement_id())


def test_the_script_skips_tests_previews_and_visitors_who_opt_out():
    text = read(SCRIPT)
    for check in (
        "if (!MEASUREMENT_ID)",
        "navigator.webdriver",
        f'const HOST = "{HOST}";',
        "location.hostname !== HOST",
        'navigator.doNotTrack === "1"',
        "navigator.globalPrivacyControl",
        "if (skip()) return;",
    ):
        assert check in text, f"analytics.js lacks {check}"


def test_the_script_turns_google_signals_and_ad_personalization_off():
    text = read(SCRIPT)
    assert re.search(r"\ballow_google_signals: false,", text)
    assert re.search(r"\ballow_ad_personalization_signals: false,", text)
    assert "send_page_view: true" in text
    assert len(re.findall(r'\bgtag\("', text)) == 2, "only js and config"


def test_the_script_loads_only_gtag_and_parses_and_keeps_nothing():
    text = read(SCRIPT)
    urls = set(re.findall(r"https?://[^\s\"'`]+", text))
    assert urls == {GTAG}, urls
    assert 'document.createElement("script")' in text
    for sink in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "document.cookie",
        "fetch(",
        "XMLHttpRequest",
        "sendBeacon",
    ):
        assert sink not in text, f"analytics.js uses {sink}"


# --- nothing typed in the address ---------------------------------------------


@pytest.mark.parametrize(("path", "page"), PAGES, ids=PAGE_IDS)
def test_no_form_puts_what_is_typed_in_the_address(path, page):
    # A form sent by GET to a web page puts its fields in that page's
    # address, which Analytics reads; mailed or posted, they never are.
    for form in parse(path).forms:
        action = form.get("action") or ""
        mailed = urlsplit(action).scheme == "mailto"
        posted = (form.get("method") or "get").lower() == "post"
        assert mailed or posted, f"form {form.get('id')} sent by GET"


# The scripts that write the page's address, and how: nothing typed reaches
# it. map3d.js writes back the map's groups and basemap (map-url.js's
# writeState keeps only the names it knows), and moved.js sends an old
# address (explore.html, aquifer.html) on to the map with its own query.
ADDRESS_WRITERS = {
    "map3d.js": ("replaceState",),
    "moved.js": ("location.replace(",),
}


@pytest.mark.parametrize(
    "path",
    [
        os.path.join(ASSETS, name)
        for name in sorted(os.listdir(ASSETS))
        if name.endswith((".js", ".mjs"))
    ],
    ids=os.path.basename,
)
def test_no_script_writes_the_address_bar(path):
    # Only the vineyard form's email (a mailto: URL, vineyard-email.js) is
    # ever opened: the page's own address keeps nothing a visitor typed.
    name = os.path.basename(path)
    allowed = ADDRESS_WRITERS.get(name, ())
    text = read(path)
    for sink in (
        "pushState",
        "replaceState",
        "location.assign",
        "location.replace(",
    ):
        if sink not in allowed:
            assert sink not in text, f"{name} uses {sink}"
    # A script's own variable named location (map3d-district.js's popup
    # point) is not the page's.
    own = re.search(r"\b(?:let|const|var)\s+location\b", text)
    prop = r"(?:\.href|\.search|\.hash|\.pathname)"
    targets = re.findall(
        r"(?:\b(?:window|document)\.location" + prop + "?"
        r"|(?<![\w.])location" + prop + ("" if own else "?") + r")"
        r"\s*=(?!=)\s*([^;\n]+)",
        text,
    )
    assert set(targets) <= {"mail.url"}, targets


# --- the script run, in node -------------------------------------------------


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """What analytics.js does in a made-up browser, env, as JSON."""
    if NODE is None:
        pytest.skip("node is not installed")

    def call(env, script=SCRIPT):
        done = subprocess.run(
            [NODE, "--input-type=commonjs", "-e", BRIDGE, script],
            input=json.dumps(env),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=60,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return call


def visitor(**changes):
    """VISITOR with some of its navigator or location changed."""
    env = json.loads(json.dumps(VISITOR))
    for key, value in changes.items():
        if key in env["navigator"]:
            env["navigator"][key] = value
        else:
            env[key] = value
    return env


def test_a_visitor_on_the_live_site_is_counted_without_ads_or_signals(run):
    the_id = measurement_id()
    if not the_id:
        pytest.skip("no measurement ID: nothing loads")
    got = run(visitor())
    assert got["added"] == [
        {"tag": "script", "src": GTAG + the_id, "async": True}
    ]
    assert got["dataLayer"] == [
        ["js", "DATE"],
        [
            "config",
            the_id,
            {
                "allow_google_signals": False,
                "allow_ad_personalization_signals": False,
                "send_page_view": True,
            },
        ],
    ]


@pytest.mark.parametrize(
    "env",
    [
        pytest.param(visitor(doNotTrack="0"), id="do-not-track-unset"),
        pytest.param(visitor(doNotTrack="unspecified"), id="do-not-track-old"),
    ],
)
def test_a_browser_that_does_not_opt_out_is_counted(run, env):
    if not measurement_id():
        pytest.skip("no measurement ID: nothing loads")
    assert len(run(env)["added"]) == 1


@pytest.mark.parametrize(
    "env",
    [
        pytest.param(visitor(webdriver=True), id="automated-browser"),
        pytest.param(visitor(hostname="localhost"), id="localhost"),
        pytest.param(visitor(hostname="127.0.0.1"), id="loopback"),
        pytest.param(visitor(hostname="danshome.github.io"), id="pages"),
        pytest.param(
            visitor(hostname=f"{HOST}.example.com"), id="another-site"
        ),
        pytest.param(visitor(doNotTrack="1"), id="do-not-track"),
        pytest.param(
            visitor(windowDoNotTrack="1"), id="do-not-track-on-window"
        ),
        pytest.param(
            visitor(globalPrivacyControl=True), id="global-privacy-control"
        ),
    ],
)
def test_nothing_loads_for_tests_previews_or_opt_outs(run, env):
    assert run(env) == {"added": [], "dataLayer": None}


def test_nothing_loads_without_a_measurement_id(run, tmp_path):
    text = read(SCRIPT)
    empty = re.sub(
        r'const MEASUREMENT_ID = "[^"]*";', 'const MEASUREMENT_ID = "";', text
    )
    assert empty != text or not measurement_id()
    script = tmp_path / "analytics.js"
    script.write_text(empty, encoding="utf-8")
    assert run(visitor(), str(script)) == {"added": [], "dataLayer": None}
