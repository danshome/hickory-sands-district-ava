"""The website in Google Chrome at phone sizes, as a reader sees it.

Every page in docs/ at three phones held upright and one desktop screen,
anonymously and read-only. Marked live, like test_dashboard.py, but run apart
from it: ./build.sh test and the lint workflow leave it out, and so does
./build.sh check-live (a publish's last step), so the website never fails an
ArcGIS publish. Every website change is tested at phone sizes before it is
merged, against a local server of its branch, and live after it is deployed:
    ./build.sh check-site --local    (this checkout's docs/ on 127.0.0.1)
    ./build.sh check-site            (https://hickorysandsdistrictava.org)

The site is https://hickorysandsdistrictava.org, or HSD_SITE_URL, such as a
local server started by hand:
    python3 -m http.server 8790 --bind 127.0.0.1 -d docs
    export HSD_SITE_URL=http://127.0.0.1:8790
    .venv/bin/python -m pytest -m live tests/live/test_site_mobile.py
The basemap key in docs/assets/map-config.js serves only the live site's
referrer and http://localhost:8765, so on any other local address Esri
refuses the basemap (HTTP 401) and the maps draw the line on a plain
background: on a loopback address those refusals, and the SDK's console
lines about them, are allowed; on the live site they fail the test (the key
expired or lost its referrer).

The viewports: phones 390x844 (iPhone), 360x780 (Android) and 375x667 (iPhone
SE), emulated with their user agent, touch and pixel ratio (isMobile,
hasTouch); and a 1440x900 desktop. On every page at every viewport:
- no console error, uncaught error or failed request from the site's own
  files (a request the browser aborts is not a failure);
- no request to Google Analytics: docs/assets/analytics.js skips an
  automated browser (navigator.webdriver), so the tests never count a visit;
- no sideways scrolling, with the menu shut or open;
- the menu: a hamburger named "Menu" that opens by a tap (a click on the
  desktop) and by the keyboard, turns into a cross while open and closes the
  same ways; inside the screen; its links in order (The boundary, The land,
  The water, The vineyards, Status, Journal, About & contact), the page's
  own marked aria-current, and every one answers 200;
- the header's place line reads "Llano Uplift · Texas Hill Country" and,
  where it shows, sits on one line between the home link and the menu;
- the header's, the footer's and the page's own buttons and action links are
  at least 44 px each way (links inside sentences are not counted).
Every menu link, tapped on a phone and clicked on the desktop, opens its
page, which marks it as the current one (The water: aquifer.html). The place
line also fits at 700 px, the narrowest screen that shows it.
On the phones:
- Explore: tapping three steps, a quarter, a half and three quarters of the
  way along the line (docs/data/steps.geojson), opens each one's popup, docked
  along the map's bottom, and the place tapped stays in view, near the middle of
  the map left above the popup (it was covered before); closing it takes the
  view's padding away; the popup has no undock button, and the map's zoom and
  Home buttons are 44 px;
- Explore: a one-finger swipe beside the map (the page's margin) and on it
  scrolls the page and leaves the map still; two fingers move the map; Home
  goes back to the whole boundary;
- The land: the drawing steps to the stage on the reading line as the page
  scrolls, and still does when the reader scrolls right after tapping Later.
Screenshots: target/browser-tests/site/<page>-<viewport>-<test>.png
(-FAILED.png when it failed), and <page>-<viewport>-loaded.png after each
load.
"""

import contextlib
import functools
import json
import os
from pathlib import Path
from urllib.parse import urldefrag
from urllib.parse import urljoin
from urllib.parse import urlsplit

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="playwright is in requirements-dev.txt: run ./build.sh env",
)
# after the skip: the dashboard tests' browser and page helpers. pytest loads
# tests/live/conftest.py as the module conftest (tests/ is not a package), so
# it is imported by that name: the same View class its screenshot hook knows.
from conftest import SHOTS
from conftest import View
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout

pytestmark = pytest.mark.live
ROOT = Path(__file__).resolve().parents[2]
BASE = os.environ.get(
    "HSD_SITE_URL", "https://hickorysandsdistrictava.org"
).rstrip("/")
ORIGIN = "{0.scheme}://{0.netloc}".format(urlsplit(BASE))
LOCAL = urlsplit(BASE).hostname in {"localhost", "127.0.0.1", "::1"}
PAGES = sorted(p.name for p in (ROOT / "docs").glob("*.html"))
# name: (width, height, Playwright's device for the user agent, pixel ratio);
# no device: a desktop window
PHONES = {
    "phone-390x844": (390, 844, "iPhone 13", 3),
    "phone-360x780": (360, 780, "Pixel 7", 3),
    "phone-375x667": (375, 667, "iPhone SE", 2),
}
VIEWPORTS = {**PHONES, "desktop-1440x900": (1440, 900, None, 1)}
# the narrowest screen that shows the header's place line
NARROW = {"desktop-700x900": (700, 900, None, 1)}
TARGET = 44  # px: the smallest button or action link, each way
SUBPIXEL = 0.5  # px a box may fall short of TARGET by rounding
LOAD_S = 120  # s a page may take to load (the maps load Esri's SDK)
SHOTS_DIR = SHOTS / "site"
MAPS = {
    "explore.html": ".explore-map arcgis-map",
    "walk.html": ".walk-map arcgis-map",
}


def quarter_steps():
    """Returns the steps a quarter, a half and three quarters along the line.

    From the site's own data (docs/data/steps.geojson), so they follow the
    boundary when its step count changes.
    """
    with open(ROOT / "docs" / "data" / "steps.geojson", encoding="utf-8") as fh:
        steps = sorted(
            int(f["properties"]["step"]) for f in json.load(fh)["features"]
        )
    return tuple(steps[len(steps) * k // 4] for k in (1, 2, 3))


# Explore's steps to tap; the tapped place's height in the map left above
# the docked popup (0 its top, 1 the popup's top) must fall in this range:
# the fix centres it (0.5); covered it was over 1
STEPS = quarter_steps()
MIDDLE = (0.25, 0.75)
# the buttons and action links of the header, the menu, the footer and the
# pages (links inside sentences are not counted)
HEADER = (".site-header .identity", ".site-header details.navigation>summary")
MENU = (".site-header details.navigation nav a",)
# the menu's links in order: (text, page)
MENU_LINKS = (
    ("The boundary", "boundary.html"),
    ("The land", "land.html"),
    ("The water", "aquifer.html"),
    ("The vineyards", "vineyards.html"),
    ("Status", "status.html"),
    ("Journal", "journal.html"),
    ("About & contact", "about.html"),
)
PLACE_LINE = "Llano Uplift · Texas Hill Country"
FOOTER = (".site-footer a",)
ACTIONS = (
    "main .text-link",
    "main .map-basemaps button",
    "main .geo-step",
    "main .way-list>a",
    "main .arrival-foot a",
)

# ---------------------------------------------------------------- in the page
READY = """(sel) => { const m = document.querySelector(sel);
  return !!(m && m.view && m.view.ready && !m.view.updating); }"""

# scrolls to the bottom a screen at a time (lazy images, the walk's map) and
# back to the top
SCROLL_THROUGH = """async () => {
  const step = innerHeight;
  for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
    scrollTo(0, y); await new Promise(r => setTimeout(r, 60)); }
  scrollTo(0, document.documentElement.scrollHeight);
  await new Promise(r => setTimeout(r, 300));
  scrollTo(0, 0); await new Promise(r => setTimeout(r, 300)); }"""

SIDEWAYS = """() => {
  const de = document.documentElement;
  return {page: de.scrollWidth, body: document.body.scrollWidth,
          screen: de.clientWidth}; }"""

# every visible element a selector finds, with its box
BOXES = """(sels) => {
  const out = [];
  for (const sel of sels) {
    for (const el of document.querySelectorAll(sel)) {
      if (el.closest('[hidden]') || (el.checkVisibility &&
          !el.checkVisibility({visibilityProperty: true}))) continue;
      const r = el.getBoundingClientRect();
      if (r.width <= 1.5 || r.height <= 1.5) continue;
      const text = (el.getAttribute('aria-label') || el.textContent)
        .trim().replace(/\\s+/g, ' ').slice(0, 40);
      out.push({sel, text, w: r.width, h: r.height, left: r.left,
                right: r.right, href: el.getAttribute('href')});
    }
  }
  return out; }"""

MENU_STATE = """() => {
  const d = document.querySelector('.site-header details.navigation');
  return d ? d.open : null; }"""

# the hamburger and the menu's links: a cross when open (the top line
# turned, the middle one gone)
MENU_SHAPE = """() => {
  const d = document.querySelector('.site-header details.navigation');
  const s = d.querySelector('summary');
  const icon = s.querySelector('.menu-icon');
  const turned = icon ? getComputedStyle(icon, '::before').transform : null;
  return {open: d.open, label: s.getAttribute('aria-label'),
          text: s.textContent.trim(), icon: !!icon,
          cross: !!turned && turned !== 'none' &&
            getComputedStyle(icon).borderTopColor === 'rgba(0, 0, 0, 0)',
          links: [...d.querySelectorAll('nav a')].map(a => ({
            text: a.textContent.trim(), href: a.getAttribute('href'),
            current: a.getAttribute('aria-current')}))}; }"""

# the header's place line, and the home link and the menu beside it
PLACE = """() => {
  const h = document.querySelector('.site-header');
  const box = (sel) => { const e = h.querySelector(sel);
    const r = e.getBoundingClientRect();
    return {left: r.left, right: r.right, height: r.height,
            shown: r.width > 0 && getComputedStyle(e).display !== 'none'}; };
  const place = h.querySelector('.header-place');
  return {text: place.textContent.trim(),
          line: parseFloat(getComputedStyle(place).lineHeight),
          place: box('.header-place'), identity: box('.identity'),
          menu: box('details.navigation > summary')}; }"""

# the map's buttons (zoom in and out, Home) in their shadow roots
CONTROLS = """() => { const out = [];
  for (const host of document.querySelectorAll('arcgis-zoom, arcgis-home')) {
    for (const b of host.shadowRoot.querySelectorAll('calcite-button')) {
      const r = b.getBoundingClientRect();
      if (r.width) out.push({host: host.localName, w: r.width, h: r.height,
                             x: r.left + r.width / 2, y: r.top + r.height / 2});
    } }
  return out; }"""

MAP_STATE = """(sel) => {
  const m = document.querySelector(sel); const v = m.view;
  const r = m.getBoundingClientRect();
  return {y: scrollY, top: r.top, bottom: r.bottom, left: r.left,
          right: r.right, scale: v.scale,
          center: [v.center.longitude, v.center.latitude]}; }"""

# zooms to a step and returns where the middle of its middle segment is on
# the screen (never a vertex: a straight step's are its ends, where the next
# step and a point begin)
STEP_AT = """async ([sel, step]) => {
  const m = document.querySelector(sel); const v = m.view;
  const layer = m.map.layers.find(l => l.title === 'Steps');
  const q = await layer.queryFeatures(
    {where: `step = ${step}`, returnGeometry: true});
  const g = q.features[0].geometry;
  await v.goTo(g.extent.clone().expand(3), {animate: false});
  const path = g.paths[0]; const k = Math.floor((path.length - 1) / 2);
  const pt = g.getPoint(0, k);
  pt.x = (path[k][0] + path[k + 1][0]) / 2;
  pt.y = (path[k][1] + path[k + 1][1]) / 2;
  window.__hsdTapped = pt;
  const s = v.toScreen(pt); const r = m.getBoundingClientRect();
  return {x: r.left + s.x, y: r.top + s.y}; }"""

# the popup and where the tapped place is now
POPUP = """(sel) => {
  const m = document.querySelector(sel); const v = m.view;
  const pe = m.querySelector('arcgis-popup');
  const box = pe.shadowRoot && pe.shadowRoot.querySelector('.main-container');
  const b = box ? box.getBoundingClientRect() : null;
  const r = m.getBoundingClientRect();
  const s = v.toScreen(window.__hsdTapped);
  const f = pe.selectedFeature;
  return {open: pe.open, dock: pe.currentDockPosition || null,
          step: f && f.attributes ? f.attributes.step : null,
          dockButton: pe.dockOptions.buttonEnabled,
          popupTop: b && b.height ? b.top : null,
          mapTop: r.top, left: r.left, right: r.right,
          x: r.left + s.x, y: r.top + s.y, padding: v.padding.bottom || 0}; }"""

CLOSE_POPUP = """(sel) => {
  document.querySelector(sel).querySelector('arcgis-popup').open = false; }"""

HOME_STATE = """(sel) => {
  const m = document.querySelector(sel); const v = m.view;
  const b = m.map.layers.find(l => l.title === 'Proposed revision');
  return {whole: v.extent.contains(b.fullExtent), scale: v.scale}; }"""

AWAY = """async (sel) => { const v = document.querySelector(sel).view;
  await v.goTo({center: [-98.9, 30.9], scale: 300000}, {animate: false}); }"""

# The land: the stage the drawing shows, and the stage on its reading line
# (a third of the way down the screen left under the stuck panel, as
# timeline.js draws it on a phone held upright)
LAND = """() => {
  const fig = document.querySelector('.geo-figure');
  const panel = fig.getBoundingClientRect().height;
  const line = panel + (innerHeight - panel) / 3;
  const items = [...document.querySelectorAll('.geo-stage')];
  const on = items.findIndex(li => { const r = li.getBoundingClientRect();
    return r.top <= line && r.bottom > line; });
  return {shown: parseInt(document.querySelector('.geo-count').textContent,
                          10),
          online: on + 1, stuck: getComputedStyle(fig).position}; }"""

# scrolls stage n's top to just under the stuck panel (its scroll margin)
TO_STAGE = """(n) => { document.querySelectorAll('.geo-stage')[n - 1]
  .scrollIntoView({block: 'start'}); }"""


# --------------------------------------------------------------- the browser
class SiteView(View):
    """One page of the site at one viewport, with what it logged.

    Its screenshots go to target/browser-tests/site/.
    """

    def __init__(self, name, page, phone):
        """Starts recording the page's errors and failed requests."""
        super().__init__(name, page, phone)
        self.page_name = None  # the file in docs/
        self.response = None  # the page's own HTTP response
        self.errors = []
        self.refused = []  # Esri's refusals of the basemap key (401, 403)
        self.counted = []  # requests to Google Analytics: none, ever
        page.on("console", self._console)
        page.on("pageerror", self._pageerror)
        page.on("request", self._request)
        page.on("requestfailed", self._requestfailed)
        page.on("response", self._response)

    def shot(self, label):
        """Takes a screenshot into target/browser-tests/site/.

        Returns:
            Its path, or why there is none.
        """
        SHOTS_DIR.mkdir(parents=True, exist_ok=True)
        path = SHOTS_DIR / f"{self.name}-{label}.png"
        try:
            self.page.screenshot(path=str(path), timeout=30_000)
        except PlaywrightError as e:
            return f"(no screenshot: {type(e).__name__}: {e})"
        return path

    def _console(self, msg):
        url = (msg.location or {}).get("url", "")
        if msg.type == "error" and own(url):
            self.errors.append(f"console error from {url}: {msg.text[:300]}")

    def _pageerror(self, error):
        if ORIGIN in (error.stack or "") or "://" not in (error.stack or ""):
            self.errors.append(f"uncaught error: {error}"[:400])

    def _request(self, request):
        if analytics(request.url):
            self.counted.append(request.url)

    def _requestfailed(self, request):
        failure = request.failure or ""
        if own(request.url) and "ERR_ABORTED" not in failure:
            self.errors.append(f"request failed: {request.url} ({failure})")

    def _response(self, response):
        if response.status < 400:
            return
        if own(response.url):
            self.errors.append(f"HTTP {response.status}: {response.url}")
        elif esri(response.url) and response.status in {401, 403}:
            self.refused.append(f"HTTP {response.status}: {response.url}")

    def problems(self):
        """Returns what the page logged that fails the tests."""
        found = list(self.errors)
        if self.counted:
            found.append(
                f"the test reached Google Analytics ({len(self.counted)} "
                f"requests, such as {self.counted[0]}): analytics.js must "
                "skip an automated browser (navigator.webdriver)"
            )
        if self.refused and not LOCAL:
            found.append(
                f"Esri refused the basemap key ({len(self.refused)} "
                f"requests, such as {self.refused[0]}): renew it or check "
                "its referrers (docs/assets/map-config.js)"
            )
        return found


def own(url):
    """True when url is one of the site's own files."""
    return url.startswith(ORIGIN + "/") or url == ORIGIN


def esri(url):
    """True when url is on Esri's ArcGIS services (arcgis.com)."""
    host = urlsplit(url).hostname or ""
    return host == "arcgis.com" or host.endswith(".arcgis.com")


def analytics(url):
    """True when url is Google's tag or one of Google Analytics' collectors."""
    host = urlsplit(url).hostname or ""
    return any(
        host == name or host.endswith("." + name)
        for name in (
            "googletagmanager.com",
            "google-analytics.com",
            "analytics.google.com",
        )
    )


@pytest.fixture(scope="module", autouse=True)
def fresh_shots():
    """Clears target/browser-tests/site/ of an earlier run's screenshots."""
    for old in SHOTS_DIR.glob("*.png"):
        old.unlink()


@pytest.fixture
def site_page(request, chrome):
    """A SiteView of one page at one viewport, loaded.

    request.param is (page, viewport). A map page is loaded when its map is
    drawn. A load that fails is tried once more; then the test fails, naming
    the screenshot.
    """
    page_name, viewport = request.param
    p, browser = chrome
    width, height, device, ratio = {**VIEWPORTS, **NARROW}[viewport]
    options = dict(
        viewport={"width": width, "height": height},
        device_scale_factor=ratio,
        is_mobile=device is not None,
        has_touch=device is not None,
        locale="en-US",
    )
    if device:
        options["user_agent"] = p.devices[device]["user_agent"]
    name = f"{page_name.removesuffix('.html')}-{viewport}"
    view = None
    for attempt in (1, 2):
        context = browser.new_context(**options)
        view = SiteView(name, context.new_page(), device is not None)
        view.page.set_default_timeout(60_000)
        view.page_name = page_name
        try:
            view.response = view.page.goto(
                f"{BASE}/{page_name}", wait_until="load", timeout=LOAD_S * 1000
            )
            with contextlib.suppress(PlaywrightTimeout):
                view.page.wait_for_load_state("networkidle", timeout=15_000)
            if page_name in MAPS:
                view.page.wait_for_function(
                    READY, arg=MAPS[page_name], timeout=LOAD_S * 1000
                )
            view.shot("loaded")
            break
        except PlaywrightError as e:
            shot = view.shot(f"load-{attempt}-FAILED")
            view.close()
            if attempt == 2:
                pytest.fail(
                    f"{name}: {BASE}/{page_name} did not load: "
                    f"{type(e).__name__}: {e}; screenshot: {shot}",
                    pytrace=False,
                )
    yield view
    view.close()


def cells(pages, viewports):
    """Returns the (page, viewport) pairs to load, for indirect parameters."""
    return [
        pytest.param((p, v), id=f"{p.removesuffix('.html')}-{v}")
        for p in pages
        for v in viewports
    ]


def tap(view, locator):
    """Taps the element on a phone; clicks it on the desktop."""
    if view.phone:
        locator.tap()
    else:
        locator.click()


def swipe(view, start, end, steps=12):
    """Drags fingers across the screen, through Chrome's touch input.

    Args:
        view: The phone's page.
        start: Each finger's (x, y) where it touches.
        end: Each finger's (x, y) where it lifts.
        steps: How many moves the drag takes.
    """
    cdp = view.page.context.new_cdp_session(view.page)

    def points(t):
        return [
            {"x": x0 + (x1 - x0) * t, "y": y0 + (y1 - y0) * t, "id": i}
            for i, ((x0, y0), (x1, y1)) in enumerate(
                zip(start, end, strict=True)
            )
        ]

    cdp.send(
        "Input.dispatchTouchEvent",
        {"type": "touchStart", "touchPoints": points(0)},
    )
    for s in range(1, steps + 1):
        cdp.send(
            "Input.dispatchTouchEvent",
            {"type": "touchMove", "touchPoints": points(s / steps)},
        )
    cdp.send(
        "Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}
    )
    cdp.detach()


def settle(view, sel):
    """Waits until the map has drawn what it is moving to."""
    view.page.wait_for_timeout(500)
    with contextlib.suppress(PlaywrightTimeout):
        view.page.wait_for_function(READY, arg=sel, timeout=30_000)


def small(boxes):
    """The boxes smaller than TARGET either way, described."""
    return [
        f"{b['sel']} {b['text']!r} {b['w']:.0f}x{b['h']:.0f}"
        for b in boxes
        if b["w"] < TARGET - SUBPIXEL or b["h"] < TARGET - SUBPIXEL
    ]


STATUS = {}  # each link's HTTP status, asked once per run


def answers(request, url):
    """Returns the HTTP status url answers with, through request."""
    if url not in STATUS:
        STATUS[url] = request.get(url, timeout=60_000).status
    return STATUS[url]


# --------------------------------------------------------------------- tests
@pytest.mark.parametrize("site_page", cells(PAGES, VIEWPORTS), indirect=True)
def test_page_reads_and_its_menu_works(site_page):
    view, page = site_page, site_page.page
    problems = []
    status = view.response.status if view.response else None
    if view.page_name != "404.html" and status != 200:
        problems.append(f"the page answered HTTP {status}")

    page.evaluate(SCROLL_THROUGH)
    wide = page.evaluate(SIDEWAYS)
    if max(wide["page"], wide["body"]) > wide["screen"] + 1:
        problems.append(f"scrolls sideways (menu shut): {wide}")

    problems += [
        f"under {TARGET} px: {s}"
        for s in small(page.evaluate(BOXES, [*HEADER, *FOOTER, *ACTIONS]))
    ]

    problems += place_problems(page)
    problems += menu_problems(view)
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


def place_problems(page):
    """The header's place line: its words, and one line where it shows."""
    got = page.evaluate(PLACE)
    problems = []
    if got["text"] != PLACE_LINE:
        problems.append(f"the place line reads {got['text']!r}")
    place = got["place"]
    if place["shown"]:
        if place["height"] > 1.5 * got["line"]:
            problems.append(
                f"the place line takes {place['height']:.0f} px, more than "
                f"one line ({got['line']:.0f} px)"
            )
        if (
            place["left"] < got["identity"]["right"]
            or place["right"] > got["menu"]["left"]
        ):
            problems.append(
                f"the place line overlaps the home link or menu: {got}"
            )
    return problems


def menu_problems(view):
    """The hamburger by tap (click) and keyboard, and the menu's links."""
    page = view.page
    problems = []
    summary = page.locator(".site-header details.navigation > summary")
    if summary.count() != 1:
        return ["no menu in the header"]
    shape = page.evaluate(MENU_SHAPE)
    if shape["label"] != "Menu" or shape["text"] or not shape["icon"]:
        problems.append(
            "the menu's button is not a hamburger named Menu: "
            f"label {shape['label']!r}, text {shape['text']!r}, "
            f"icon {shape['icon']}"
        )
    links = [
        (link["text"], link["href"].rsplit("/", 1)[-1])
        for link in shape["links"]
    ]
    if links != list(MENU_LINKS):
        problems.append(f"the menu's links are {links}, not {MENU_LINKS}")
    current = [
        link["text"] for link in shape["links"] if link["current"] == "page"
    ]
    mine = [text for text, href in MENU_LINKS if href == view.page_name]
    if current != mine:
        problems.append(f"the menu marks {current} as this page, not {mine}")

    tap(view, summary)
    page.wait_for_timeout(400)
    shape = page.evaluate(MENU_SHAPE)
    if not shape["open"]:
        problems.append("the menu did not open by a tap or click")
    elif not shape["cross"]:
        problems.append("the open menu's button is not a cross")
    boxes = page.evaluate(BOXES, list(MENU))
    if len(boxes) != len(MENU_LINKS):
        problems.append(f"the open menu shows {len(boxes)} links")
    screen = page.evaluate(SIDEWAYS)["screen"]
    problems += [
        f"menu link {b['text']!r} outside the screen ({b['left']:.0f} "
        f"to {b['right']:.0f} of {screen})"
        for b in boxes
        if b["left"] < -1 or b["right"] > screen + 1
    ]
    problems += [f"under {TARGET} px: {s}" for s in small(boxes)]
    wide = page.evaluate(SIDEWAYS)
    if max(wide["page"], wide["body"]) > wide["screen"] + 1:
        problems.append(f"scrolls sideways (menu open): {wide}")
    view.shot("menu-open")
    for b in boxes:
        url = urldefrag(urljoin(page.url, b["href"] or "")).url
        if own(url) and (code := answers(page.request, url)) != 200:
            problems.append(f"menu link {b['href']} answers HTTP {code}")
    tap(view, summary)
    page.wait_for_timeout(400)
    shape = page.evaluate(MENU_SHAPE)
    if shape["open"]:
        problems.append("the menu did not close by a tap or click")
    elif shape["cross"]:
        problems.append("the shut menu's button is still a cross")

    # the keyboard: Enter opens it, Space closes it
    summary.focus()
    for key, opens in (("Enter", True), ("Space", False)):
        page.keyboard.press(key)
        page.wait_for_timeout(300)
        if page.evaluate(MENU_STATE) is not opens:
            what = "open" if opens else "close"
            problems.append(f"the menu did not {what} by the {key} key")
    return problems


@pytest.mark.parametrize(
    "site_page",
    cells(["index.html"], ["phone-390x844", "desktop-1440x900"]),
    indirect=True,
)
def test_every_menu_link_opens_its_page(site_page):
    view, page = site_page, site_page.page
    problems = []
    start = page.url
    for text, href in MENU_LINKS:
        page.goto(start, wait_until="domcontentloaded")
        tap(view, page.locator(".site-header details.navigation > summary"))
        page.wait_for_timeout(300)
        link = page.locator(".site-header details.navigation nav a").filter(
            has_text=text
        )
        if link.count() != 1:
            problems.append(f"{text}: {link.count()} such links in the menu")
            continue
        try:
            with page.expect_navigation(wait_until="domcontentloaded"):
                tap(view, link.first)
        except PlaywrightError as e:
            problems.append(f"{text}: no page opened ({type(e).__name__})")
            continue
        landed = urlsplit(page.url).path.rsplit("/", 1)[-1]
        marked = page.evaluate(MENU_SHAPE)["links"]
        current = [link["text"] for link in marked if link["current"] == "page"]
        if landed != href or current != [text]:
            problems.append(
                f"{text}: opened {page.url}, which marks {current} as the "
                f"current page (expected {href}, marking {text!r})"
            )
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("site_page", cells(PAGES, NARROW), indirect=True)
def test_place_line_fits_at_700px(site_page):
    view = site_page
    problems = place_problems(view.page)
    if not view.page.evaluate(PLACE)["place"]["shown"]:
        problems.append("the place line is hidden at 700 px")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize(
    "site_page", cells(["explore.html"], PHONES), indirect=True
)
def test_explore_popup_leaves_the_tapped_step_in_view(site_page):
    view, page = site_page, site_page.page
    sel = MAPS["explore.html"]
    page.evaluate(
        "() => { const m = document.querySelector('.explore-map');"
        " scrollTo(0, m.getBoundingClientRect().top + scrollY - 40); }"
    )
    settle(view, sel)
    controls = page.evaluate(CONTROLS)
    # zoom in, zoom out and Home, each a calcite-button in its shadow root:
    # none found means the SDK has changed, not that they are big enough
    hosts = sorted({c["host"] for c in controls})
    problems = []
    if len(controls) < 3 or hosts != ["arcgis-home", "arcgis-zoom"]:
        problems.append(
            f"the map's zoom and Home buttons are not found as calcite-buttons "
            f"in their shadow roots ({len(controls)} found in {hosts}): has "
            "the SDK changed?"
        )
    problems += [
        f"map button under {TARGET} px: {c['host']} {c['w']:.0f}x{c['h']:.0f}"
        for c in controls
        if c["w"] < TARGET - SUBPIXEL or c["h"] < TARGET - SUBPIXEL
    ]
    for step in STEPS:
        at = page.evaluate(STEP_AT, [sel, step])
        settle(view, sel)
        page.touchscreen.tap(at["x"], at["y"])

        def shown(step=step):
            got = page.evaluate(POPUP, sel)
            assert got["open"], f"step {step}: no popup after the tap"
            assert got["step"] == step, (
                f"step {step}: the popup shows step {got['step']}"
            )
            assert str(got["dock"]).startswith("bottom"), (
                f"step {step}: the popup is not docked at the bottom on a "
                f"phone ({got['dock']})"
            )
            assert got["popupTop"] is not None, (
                f"step {step}: the popup's box (.main-container) is not "
                "found: has the SDK changed?"
            )
            share = (got["y"] - got["mapTop"]) / (
                got["popupTop"] - got["mapTop"]
            )
            assert MIDDLE[0] <= share <= MIDDLE[1], (
                f"step {step}: the tapped place is at {share:.2f} of the map "
                f"left above the popup (0 top, 1 the popup), not in {MIDDLE}"
                f": {got}"
            )
            assert got["left"] < got["x"] < got["right"], got
            return got

        try:
            got = view.wait(shown, timeout=15)
            if got["dockButton"] is not False:
                problems.append("the popup offers an undock button on a phone")
        except AssertionError as e:
            problems.append(str(e))
        view.shot(f"step{step}")
        page.evaluate(CLOSE_POPUP, sel)
        page.wait_for_timeout(1000)
        padding = page.evaluate(POPUP, sel)["padding"]
        if padding:
            problems.append(f"step {step}: padding {padding} after closing")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize(
    "site_page", cells(["explore.html"], PHONES), indirect=True
)
def test_explore_scrolls_by_one_finger_and_goes_home(site_page):
    view, page = site_page, site_page.page
    sel = MAPS["explore.html"]
    width, height = page.viewport_size["width"], page.viewport_size["height"]
    problems = []

    def to_map():
        page.evaluate(
            "() => { const m = document.querySelector('.explore-map');"
            " scrollTo(0, m.getBoundingClientRect().top + scrollY"
            " - innerHeight * 0.15); }"
        )
        settle(view, sel)
        return page.evaluate(MAP_STATE, sel)

    before = to_map()
    if before["left"] < 12 or before["right"] > width - 12:
        problems.append(
            f"no page margin beside the map: {before['left']:.0f} to "
            f"{before['right']:.0f} of {width}"
        )
    y = min(
        before["top"] + 0.7 * (before["bottom"] - before["top"]), height - 60
    )
    for where, x in (
        ("beside the map", before["left"] / 2),
        ("on the map", width / 2),
    ):
        before = to_map()
        swipe(view, [(x, y)], [(x, y - 300)])
        page.wait_for_timeout(1200)
        after = page.evaluate(MAP_STATE, sel)
        if after["y"] - before["y"] < 100:
            problems.append(
                f"a one-finger swipe {where} did not scroll the page "
                f"({after['y'] - before['y']:.0f} px)"
            )
        if after["center"] != before["center"]:
            problems.append(f"a one-finger swipe {where} moved the map")

    before = to_map()
    middle = (before["top"] + before["bottom"]) / 2
    x = width / 2
    swipe(
        view,
        [(x - 40, middle), (x + 40, middle)],
        [(x - 40, middle - 120), (x + 40, middle - 120)],
    )
    page.wait_for_timeout(1200)
    settle(view, sel)
    after = page.evaluate(MAP_STATE, sel)
    if after["center"] == before["center"]:
        problems.append("a two-finger drag did not move the map")

    page.evaluate(AWAY, sel)
    settle(view, sel)
    home = [c for c in page.evaluate(CONTROLS) if c["host"] == "arcgis-home"]
    if not home:
        problems.append("no Home button on the map")
    else:
        page.touchscreen.tap(home[0]["x"], home[0]["y"])

        def whole():
            got = page.evaluate(HOME_STATE, sel)
            assert got["whole"], f"Home did not show the whole line: {got}"
            return got

        try:
            view.wait(whole, timeout=15)
        except AssertionError as e:
            problems.append(str(e))
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize(
    "site_page", cells(["land.html"], PHONES), indirect=True
)
def test_land_timeline_steps_on_scroll(site_page):
    view, page = site_page, site_page.page
    page.wait_for_selector(".geo-has-figure", timeout=30_000)
    problems = []

    def follows(n):
        got = page.evaluate(LAND)
        assert got["stuck"] == "sticky", f"the drawing is not stuck: {got}"
        assert got["online"] == n, f"stage {n} is not on the line: {got}"
        assert got["shown"] == n, f"stage {n} on the line, drawn: {got}"

    for n in range(1, 9):
        page.evaluate(TO_STAGE, n)
        try:
            view.wait(functools.partial(follows, n), timeout=5)
        except AssertionError as e:
            problems.append(f"scrolling: {e}")
    view.shot("scrolled")

    # a scroll right after a tap: the drawing follows it once the tap's hold
    # ends
    page.evaluate(TO_STAGE, 2)
    page.wait_for_timeout(1500)
    page.locator(".geo-step").nth(1).tap()  # Later
    page.wait_for_timeout(300)
    page.evaluate(TO_STAGE, 6)
    try:
        view.wait(functools.partial(follows, 6), timeout=5)
    except AssertionError as e:
        problems.append(f"scrolling right after Later: {e}")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)
