"""Google Analytics on the website: docs/assets/analytics.js.

Every page in docs/ (and the walk page's template, src/site/walk.template.html)
loads docs/assets/analytics.js once, in its head, deferred; no page or other
script names Google's tag (www.googletagmanager.com) or its collector, so
Google's tag comes only through analytics.js. The script loads gtag.js only on
the live site, never for an automated browser (navigator.webdriver: the site's
own browser tests never count), with Do Not Track or Global Privacy Control,
or with an empty measurement ID; it turns Google signals and ad
personalization off. Besides the page view it sends only the site's own events,
through window.hsdTrack: only the names in EVENTS below, each with only its
own params, each a word from that param's fixed list or a small whole number;
every call in docs/assets/ names one with literal or listed params and passes
nothing read from a form's field. No form
puts what a visitor types into the page's address (Analytics reads the address
of every page it counts): every form is posted or mailed, and no script
writes the address bar. And, in node when it is installed (it is on GitHub's
Linux runners), the script is run against a made-up browser: on the live site
it loads gtag.js with those settings and sends only the allowed events, and in
every other case it does nothing, events included. Standard library only, so
the lint workflow runs these.
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
    location: { hostname: env.hostname, pathname: env.pathname || "/" },
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
  // The page's own events, as its scripts would send them.
  for (const [name, params] of env.calls || []) {
    context.hsdTrack(name, params);
  }
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
    # js and config once each, and the events track lets through
    calls = re.findall(r'\bgtag\("(\w+)"', text)
    assert sorted(calls) == ["config", "event", "js"], calls


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
    # A history entry with no address (the vineyard form's steps, so that
    # the phone's Back goes back one) leaves the address as it is.
    text = re.sub(
        r'history\.(?:push|replace)State\(\s*[\w.]+\s*,\s*""\s*\)',
        "",
        read(path),
    )
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


# --- the site's own events ---------------------------------------------------

# Every event analytics.js lets through, and each of its params: the words it
# may take, or INT (a whole number from 0 to 999). BUILD.md (Analytics) lists
# the same; each param is a custom dimension in Analytics. Every event also
# carries page, which track adds from the page's address.
INT = "int"
MAP_GROUPS = [
    "district",
    "places",
    "wells",
    "vineyards",
    "boundaries",
    "geology",
    "aquifer",
]
MAP_LAYERS = [
    "all",
    "ava",
    "counties",
    "district",
    "location",
    "member",
    "official-outcrop",
    "outside-official",
    "precambrian",
    "precambrian-buried",
    "sides",
    "steps",
    "top-buried",
    "top-surface",
    "towns",
    "vineyards-developing",
    "vineyards-historical",
    "vineyards-hsd",
    "vineyards-llano",
    "wells",
    "wells-water",
]
EVENTS = {
    "map_layer": {
        "group": MAP_GROUPS,
        "layer": MAP_LAYERS,
        "state": ["on", "off"],
    },
    "map_open_item": {
        "kind": ["step", "point", "well", "vineyard", "aquifer", "other"],
    },
    "map_view": {
        "action": [
            "3d",
            "2d",
            "home",
            "basemap",
            "wells_filter",
            "wells_reset",
            "panel_min",
            "panel_restore",
            "about",
        ],
        "value": [
            "button",
            "imagery",
            "topo",
            "dark",
            "use",
            "yield",
            "depth",
            "unreported",
            "hickory_only",
            "about-district",
            "about-sources",
            "sheet",
        ],
    },
    "map_mode": {"mode": ["map", "aquifer"]},
    "walk_step": {"step": INT, "total": INT},
    "walk_complete": {"total": INT},
    "land_section": {
        "section": [f"slice-{n}" for n in range(1, 7)]
        + [f"timeline-{n}" for n in range(1, 9)],
    },
    "vote_cast": {"dir": ["like", "pass"]},
    "vote_undo": {},
    "vote_upload": {"result": ["ok", "refused", "error"]},
    "vineyard_form": {
        "step": [
            "start",
            "blocks",
            "details",
            "review",
            "sent",
            "email_fallback",
            "error",
        ],
    },
}
PAGE_NAMES = [
    "home",
    "about",
    "boundary",
    "colophon",
    "journal",
    "land",
    "logo-vote",
    "map",
    "status",
    "vineyards",
    "walk",
    "other",
]
# What a param's value must never be read from: a field's value or files, a
# page's text, its address, or a layer's or file's name.
READS = (
    ".value",
    "valueAsNumber",
    ".files",
    "FormData",
    "textContent",
    "innerText",
    "innerHTML",
    "location",
    ".title",
    ".name",
    "getAttribute",
    "prompt(",
)


def events_in_the_script():
    """The event names in analytics.js's EVENTS, in its order."""
    text = read(SCRIPT)
    block = re.search(r"\n  const EVENTS = \{\n(.*?)\n  \};\n", text, re.S)
    assert block, "analytics.js has no EVENTS"
    return re.findall(r"^    (\w+): ", block.group(1), re.M)


def test_the_script_allows_only_the_listed_events():
    assert events_in_the_script() == list(EVENTS)


def test_the_event_names_and_params_suit_analytics():
    # GA4: names of letters, digits and _, up to 40; at most 25 params.
    for name, params in EVENTS.items():
        assert re.fullmatch(r"[a-z][a-z0-9_]{0,39}", name), name
        assert len(params) < 25, name
        for param, vocabulary in params.items():
            assert re.fullmatch(r"[a-z][a-z0-9_]{0,39}", param), param
            assert param != "page", "track adds page itself"
            if vocabulary != INT:
                for word in vocabulary:
                    assert re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,29}", word)


def test_the_map_s_switches_are_all_listed():
    # A new switch on the map is counted only once it is listed here and in
    # analytics.js.
    text = read(os.path.join(DOCS, "map.html"))
    groups = set(re.findall(r'data-group-switch="([^"]+)"', text))
    switches = set(re.findall(r'data-switch="([^"]+)"', text))
    assert groups <= set(MAP_GROUPS), groups - set(MAP_GROUPS)
    # wells-hickory-only is a filter (map_view wells_filter hickory_only)
    layers = switches - {"wells-hickory-only"}
    assert layers <= set(MAP_LAYERS), layers - set(MAP_LAYERS)
    url = read(os.path.join(ASSETS, "map-url.js"))
    listed = re.search(r"export const GROUPS = \[(.*?)\];", url, re.S)
    assert re.findall(r'"([^"]+)"', listed.group(1)) == MAP_GROUPS
    basemaps = set(re.findall(r'data-basemap="([^"]+)"', text))
    abouts = set(re.findall(r'data-about="([^"]+)"', text))
    assert basemaps | abouts <= set(EVENTS["map_view"]["value"])


def split_top(text, sep=","):
    """Splits text at sep outside brackets and strings."""
    parts, depth, quote, start = [], 0, None, 0
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def closing(text, at):
    """The index just past the bracket that closes the one at text[at]."""
    pairs = {"(": ")", "{": "}", "[": "]"}
    stack, quote, i = [], None, at
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c in pairs:
            stack.append(pairs[c])
        elif c in ")}]":
            assert stack and stack.pop() == c, text[at : i + 1]
            if not stack:
                return i + 1
        i += 1
    raise AssertionError("unclosed: " + text[at : at + 80])


CALL = re.compile(r"window\.hsdTrack(\?\.)?\(")
GUARD = "if (window.hsdTrack) {"


def track_calls():
    """Every hsdTrack call in docs/assets/ but analytics.js.

    Returns:
        The calls, as (where, [the name's text, the params' text]), and
        where hsdTrack is named but neither called nor guarded.
    """
    calls, stray = [], []
    for name in sorted(os.listdir(ASSETS)):
        path = os.path.join(ASSETS, name)
        if not name.endswith((".js", ".mjs")) or path == SCRIPT:
            continue
        text = read(path)
        for found in re.finditer(r"hsdTrack", text):
            line_start = text.rfind("\n", 0, found.start()) + 1
            line = text[line_start : text.find("\n", found.start())]
            where = f"{name}:{text.count(chr(10), 0, found.start()) + 1}"
            if line.lstrip().startswith(("//", "*", "/*")):
                continue  # a comment
            if line.strip() == GUARD:
                continue
            call = CALL.match(text, found.start() - len("window."))
            if not call:
                stray.append(where)
                continue
            if not call.group(1):
                # a plain call, only right under its guard
                before = text[:line_start].rstrip().rsplit("\n", 1)[-1]
                if before.strip() != GUARD:
                    stray.append(where)
                    continue
            open_at = call.end() - 1
            args = split_top(text[open_at + 1 : closing(text, open_at) - 1])
            calls.append((where, args))
    return calls, stray


def test_every_mention_of_track_is_a_call_or_its_guard():
    calls, stray = track_calls()
    assert not stray, f"hsdTrack named but not called as allowed: {stray}"
    assert len(calls) >= len(EVENTS), "fewer calls than events"


def test_every_event_is_sent_somewhere():
    calls, _ = track_calls()
    sent = {json.loads(args[0]) for _, args in calls if args}
    assert sent == set(EVENTS), set(EVENTS) ^ sent


@pytest.mark.parametrize(
    ("where", "args"), track_calls()[0], ids=lambda v: str(v)[:40]
)
def test_every_call_sends_an_allowed_event_with_allowed_params(where, args):
    assert len(args) == 2, f"{where}: track(name, {{params}})"
    name, params = args
    assert re.fullmatch(r'"\w+"', name), f"{where}: a literal name"
    name = json.loads(name)
    assert name in EVENTS, f"{where}: {name} is not an allowed event"
    allowed = EVENTS[name]
    assert params.startswith("{") and params.endswith("}"), where
    for entry in split_top(params[1:-1]):
        key, _, value = entry.partition(":")
        key = key.strip()
        value = value.strip() or key  # { step } is { step: step }
        assert key in allowed, f"{where}: {name} has no param {key}"
        vocabulary = allowed[key]
        for read_ in READS:
            assert read_ not in value, f"{where}: {key} reads {read_}"
        if re.fullmatch(r"\d+", value):
            assert vocabulary == INT, f"{where}: {key} is not a number"
        for literal in re.findall(r'"([^"]*)"', value):
            assert vocabulary != INT, f"{where}: {key} takes a number"
            assert any(word.startswith(literal) for word in vocabulary), (
                f"{where}: {key} {literal!r} is not an allowed word"
            )
        assert "'" not in value and "`" not in value, f"{where}: {value}"


def test_no_call_passes_what_a_field_holds():
    # The params' text never reads a field: .value, files, a form's data.
    calls, _ = track_calls()
    for where, args in calls:
        joined = " ".join(args)
        for read_ in (".value", "valueAsNumber", ".files", "FormData"):
            assert read_ not in joined, f"{where} reads {read_}"


# --- the events, run in node --------------------------------------------------


def every_allowed_call():
    """One call for each word and number each param may take."""
    calls = []
    for name, params in EVENTS.items():
        if not params:
            calls.append([name, {}])
        for param, vocabulary in params.items():
            words = [0, 7, 999] if vocabulary == INT else vocabulary
            calls.extend([name, {param: word}] for word in words)
    return calls


def test_the_allowed_events_are_sent_with_the_page(run):
    if not measurement_id():
        pytest.skip("no measurement ID: nothing loads")
    calls = every_allowed_call()
    got = run({**visitor(), "pathname": "/map.html", "calls": calls})
    events = got["dataLayer"][2:]
    assert events == [
        ["event", name, {**params, "page": "map"}] for name, params in calls
    ]


@pytest.mark.parametrize(
    ("pathname", "page"),
    [
        ("/", "home"),
        ("/index.html", "home"),
        ("/walk.html", "walk"),
        ("/logo-vote.html", "logo-vote"),
        ("/a/b/land.html", "land"),
        ("/someone@example.com.html", "other"),
        ("/map.html/../x", "other"),
    ],
)
def test_the_page_is_one_of_the_site_s_pages(run, pathname, page):
    if not measurement_id():
        pytest.skip("no measurement ID: nothing loads")
    assert page in PAGE_NAMES
    got = run({**visitor(), "pathname": pathname, "calls": [["vote_undo", {}]]})
    assert got["dataLayer"][2:] == [["event", "vote_undo", {"page": page}]]


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(["page_view", {}], id="not-an-event"),
        pytest.param(["map_layers", {}], id="near-miss"),
        pytest.param(["toString", {}], id="inherited"),
        pytest.param([7, {}], id="a-number-for-a-name"),
        pytest.param(["vote_undo", {"dir": "like"}], id="another-s-param"),
        pytest.param(["vote_cast", {"dir": "Like"}], id="not-the-word"),
        pytest.param(
            ["vote_cast", {"dir": "like", "page": "map"}], id="page-given"
        ),
        pytest.param(
            ["map_view", {"action": "about", "value": "a typed name"}],
            id="free-text",
        ),
        pytest.param(
            ["map_view", {"action": "basemap", "value": ["dark"]}],
            id="a-list",
        ),
        pytest.param(["walk_step", {"step": -1}], id="negative"),
        pytest.param(["walk_step", {"step": 1000}], id="too-big"),
        pytest.param(["walk_step", {"step": 1.5}], id="a-fraction"),
        pytest.param(["walk_step", {"step": "3"}], id="a-number-as-text"),
        pytest.param(["walk_step", {"step": 30.2967}], id="a-coordinate"),
        pytest.param(["land_section", {"section": "slice-7"}], id="no-slice"),
        pytest.param(["vote_cast", "like"], id="text-for-params"),
    ],
)
def test_a_call_that_breaks_a_rule_sends_nothing(run, call):
    if not measurement_id():
        pytest.skip("no measurement ID: nothing loads")
    got = run({**visitor(), "calls": [call, ["vote_undo", None]]})
    # the bad call is dropped; the good one after it still goes
    assert got["dataLayer"][2:] == [["event", "vote_undo", {"page": "home"}]]


def test_a_page_view_sends_at_most_300_events(run):
    if not measurement_id():
        pytest.skip("no measurement ID: nothing loads")
    got = run({**visitor(), "calls": [["vote_undo", {}]] * 400})
    assert len(got["dataLayer"]) == 2 + 300


@pytest.mark.parametrize(
    "env",
    [
        pytest.param(visitor(webdriver=True), id="automated-browser"),
        pytest.param(visitor(hostname="localhost"), id="localhost"),
        pytest.param(visitor(doNotTrack="1"), id="do-not-track"),
        pytest.param(
            visitor(globalPrivacyControl=True), id="global-privacy-control"
        ),
    ],
)
def test_track_does_nothing_when_analytics_is_off(run, env):
    got = run({**env, "calls": every_allowed_call()})
    assert got == {"added": [], "dataLayer": None}


def test_track_does_nothing_without_a_measurement_id(run, tmp_path):
    text = read(SCRIPT)
    empty = re.sub(
        r'const MEASUREMENT_ID = "[^"]*";', 'const MEASUREMENT_ID = "";', text
    )
    script = tmp_path / "analytics.js"
    script.write_text(empty, encoding="utf-8")
    got = run({**visitor(), "calls": every_allowed_call()}, str(script))
    assert got == {"added": [], "dataLayer": None}
