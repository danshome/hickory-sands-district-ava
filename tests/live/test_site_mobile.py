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
Errors: a console error counts only when Chrome gives its source as one of
the site's own files; what Esri's SDK logs (from js.arcgis.com) is never
counted, here or live. The basemap key in docs/assets/map-config.js serves
only the live site's referrer and http://localhost:8765, so on any other
local address Esri refuses the basemap (HTTP 401) and the maps draw the line
on a plain background: on a loopback address those refusals (HTTP 401 or 403
from arcgis.com) are allowed; on the live site they fail the test (the key
expired or lost its referrer).

The viewports: phones 390x844 (iPhone), 360x780 (Android) and 375x667 (iPhone
SE), emulated with their user agent, touch and pixel ratio (isMobile,
hasTouch); and a 1440x900 desktop. On every page at every viewport:
- no console error from the site's own files, uncaught error from them (or
  from no file) or failed request for one (a request the browser aborts is
  not a failure);
- no sideways scrolling, with the menu shut or open;
- the menu: a hamburger named "Menu" that opens by a tap (a click on the
  desktop) and by the keyboard, turns into a cross while open and closes the
  same ways; inside the screen; its links in order (The boundary, The land,
  The water, The vineyards, Status, Journal, About & contact), the page's
  own marked aria-current, and every one answers 200;
- the header's place line reads "Llano Uplift · Texas Hill Country" and,
  where it shows, sits on one line between the home link and the menu;
- these buttons and action links are at least 44 px each way: the header's
  home link and menu button, the open menu's links, the footer's links, and
  on the pages those ACTIONS lists (.text-link, Explore's basemap buttons,
  The land's Earlier and Later, Home's ways in and arrival links, The
  water's panel links and About contents); other links and buttons (links
  inside sentences, the vineyards form) are not measured. One hidden by
  design is not measured: inside a [hidden] element, or not rendered
  (checkVisibility(): display:none, visibility:hidden, the content of a shut
  <details> or <dialog>). Every other one is, so a box collapsed to 1.5 px
  or less fails as too small.
Every menu link, tapped on a phone and clicked on the desktop, opens its
page, which marks it as the current one (The water: aquifer.html). The place
line also fits at 700 px, the narrowest screen that shows it.
The water (aquifer.html), at every viewport: its panel's links (on a phone,
with the Layers sheet opened) and, opened from "About this map", the About
panel's contents links and Close button are 44 px each way.
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
  scrolls, and still does when the reader scrolls right after tapping Later
  (the tap holds the drawing for 1,200 ms); and, with the page's clock
  stopped so that only the reader can end the hold, a touch outside the
  drawing's buttons or a turn of the wheel ends it at once, while a touch on
  the buttons does not (timeline.js, reader()); so does the slice through
  the district, at every viewport, with no sideways scrolling, after tapping
  Next too (screenshots of the maps, each step and the questions); and when
  its data is not JSON, malformed, or fails while it is drawn, the slice
  keeps the build's static drawing and the steps, with nothing of land.js
  left on the page.
On a phone (390x844) and the desktop, The water's wells (aquifer.html,
through the page's window.aquiferWells): at first the default filters'
wells (irrigation, the default yield and up, counted here from the data),
every one's head drawn zoomed out; "All" uses thins them to the overview;
filters widened in quick steps leave one heads layer on the map, in step with
the filters and the Wells switch; Reset comes back to the first count.
Explore's map must settle (ready, not updating) within 30 s of each move,
or the test fails there.
Screenshots: target/browser-tests/site/<page>-<viewport>-<test>.png
(-FAILED.png when it failed), and <page>-<viewport>-loaded.png after each
load.
"""

import contextlib
import datetime
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
    "main .lp-link",  # The water's panel: About this map, Sources and limits
    "main .about-toc a",  # its About panel's contents (rendered when open)
)
# The water: the panel's links, and the About panel's contents and Close
AQUIFER_LINKS = ("main .lp-link",)
AQUIFER_ABOUT = ("main .aq-about .about-toc a", "main .aq-about .about-close")

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

# every element a selector finds, with its box, but those hidden by design:
# inside a [hidden] element, or not rendered (checkVisibility(): display:none,
# visibility:hidden, the content of a shut <details> or <dialog>). Any other
# box is returned whatever its size, so one collapsed to nothing is measured
# (and fails), not skipped.
BOXES = """(sels) => {
  const out = [];
  for (const sel of sels) {
    for (const el of document.querySelectorAll(sel)) {
      if (el.closest('[hidden]') || (el.checkVisibility &&
          !el.checkVisibility({visibilityProperty: true}))) continue;
      const r = el.getBoundingClientRect();
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
  const fig = document.querySelector('#deep-time .geo-figure');
  const panel = fig.getBoundingClientRect().height;
  const line = panel + (innerHeight - panel) / 3;
  const items = [...document.querySelectorAll('.geo-stage')];
  const on = items.findIndex(li => { const r = li.getBoundingClientRect();
    return r.top <= line && r.bottom > line; });
  return {shown: parseInt(
            document.querySelector('#deep-time .geo-count').textContent, 10),
          online: on + 1, stuck: getComputedStyle(fig).position}; }"""

# scrolls stage n's top to just under the stuck panel (its scroll margin)
TO_STAGE = """(n) => { document.querySelectorAll('.geo-stage')[n - 1]
  .scrollIntoView({block: 'start'}); }"""

# the same, at once (no smooth scrolling)
JUMP_TO_STAGE = """(n) => { document.querySelectorAll('.geo-stage')[n - 1]
  .scrollIntoView({block: 'start', behavior: 'instant'}); }"""

# The water: whether the page's script has wired its panel and About links
# (it does so once the 3D view is up, and marks the page ready at the end)
AQUIFER_READY = """() => document.documentElement.dataset.aquifer === 'ready'"""

# The water: the wells as drawn and counted, through the page's own hooks;
# the default's counts are counted here from the data the page loaded
WELLS = """async () => {
  const w = window.aquiferWells; const v = window.aquiferView;
  if (!w || !v || document.documentElement.dataset.aquifer !== 'ready')
    return null;
  const d = w.defaults; const keys = w.index.filter_keys;
  const tested = (gpm) => gpm !== null && gpm >= d.yieldLo;
  const onMap = v.map.allLayers.toArray()
    .filter(l => l.title === 'Well heads (TWDB reports)');
  const tracked = w.headLayers();
  const layer = w.heads();
  let held = null; let drawn = null;
  if (layer && layer.visible) {
    held = await layer.queryFeatureCount();
    drawn = await (await v.whenLayerView(layer)).queryFeatureCount(); }
  return {note: w.note(), held, drawn, updating: v.updating,
    irrigation: d.uses.size === 1 &&
      d.uses.has(w.index.use_groups.indexOf('Irrigation')),
    first: keys.filter(([u, , g]) => d.uses.has(u) && tested(g)).length,
    allUses: keys.filter(([, , g]) => tested(g)).length,
    anyYield: keys.filter(([u]) => d.uses.has(u)).length,
    farMax: Number(document.getElementById('aq-wells-far-max')
      .textContent.replace(/,/g, '')),
    shown: document.getElementById('aq-wells-shown').textContent,
    filters: document.getElementById('aq-filters-state').textContent,
    orphans: onMap.filter(l => !tracked.includes(l)).length,
    visibleHeads: onMap.filter(l => l.visible).length}; }"""

# widens the yield filter to everything in quick steps, each a new heads
# layer, some replaced before they are drawn
WIDEN = """async () => {
  const lo = document.getElementById('aq-yield-lo');
  for (const at of ['2', '1', '0']) {
    lo.value = at; lo.dispatchEvent(new Event('input'));
    await new Promise(r => setTimeout(r, 40)); }
  const none = document.getElementById('aq-yield-none');
  none.checked = true; none.dispatchEvent(new Event('change')); }"""


# The land's slice (land.js): the step the drawing shows, and the step on its
# reading line (the middle of a wide screen; on a phone, a third of the way
# down the screen left under the stuck panel)
SLICE = """() => {
  const fig = document.querySelector('.lnd-fig');
  const wide = matchMedia('(min-width: 1000px)').matches;
  const panel = wide ? 0 : fig.getBoundingClientRect().height;
  const line = wide ? innerHeight * 0.455 : panel + (innerHeight - panel) / 3;
  const items = [...document.querySelectorAll('.lnd-step')];
  const on = items.findIndex(li => { const r = li.getBoundingClientRect();
    return r.top <= line && r.bottom > line; });
  return {shown: parseInt(
            document.querySelector('.lnd-sec .geo-count').textContent, 10),
          online: on + 1, stuck: getComputedStyle(fig).position,
          over: document.documentElement.scrollWidth - innerWidth}; }"""

# scrolls step n onto the reading line: its top just under the stuck panel
# on a phone (its scroll margin), its middle at the middle of a wide screen
TO_STEP = """(n) => { const wide = matchMedia('(min-width: 1000px)').matches;
  document.querySelectorAll('.lnd-step')[n - 1]
  .scrollIntoView({block: wide ? 'center' : 'start'}); }"""


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
        page.on("console", self._console)
        page.on("pageerror", self._pageerror)
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


def touch(view, x, y):
    """Touches the screen at (x, y) with one finger, and lifts it."""
    swipe(view, [(x, y)], [(x, y)], steps=0)


def settle(view, sel):
    """Waits until the map has drawn what it is moving to.

    Fails the test, naming a screenshot, when the map is not ready or still
    updating after 30 s: what the test measured next would be a map still
    moving.
    """
    view.page.wait_for_timeout(500)
    try:
        view.page.wait_for_function(READY, arg=sel, timeout=30_000)
    except PlaywrightTimeout:
        shot = view.shot("settle-FAILED")
        pytest.fail(
            f"{view.name}: the map ({sel}) was not ready, or still updating, "
            f"30 s after it was moved; screenshot: {shot}",
            pytrace=False,
        )


def small(boxes):
    """The boxes smaller than TARGET either way, described.

    A box of 1.5 px or less either way, a button or link collapsed to
    nothing that BOXES did not find hidden by design, is called collapsed.
    """
    return [
        f"{b['sel']} {b['text']!r} {b['w']:.0f}x{b['h']:.0f}"
        + (" (collapsed)" if min(b["w"], b["h"]) <= 1.5 else "")
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
        land_shows(page, n, n)

    for n in range(1, 9):
        page.evaluate(TO_STAGE, n)
        try:
            view.wait(functools.partial(follows, n), timeout=5)
        except AssertionError as e:
            problems.append(f"scrolling: {e}")
    view.shot("scrolled")

    # a scroll right after a tap: the drawing follows it once the tap's hold
    # ends (here, by its 1,200 ms timer)
    page.evaluate(TO_STAGE, 2)
    page.wait_for_timeout(1500)
    page.locator("#deep-time .geo-step").nth(1).tap()  # Later
    page.wait_for_timeout(300)
    page.evaluate(TO_STAGE, 6)
    try:
        view.wait(functools.partial(follows, 6), timeout=5)
    except AssertionError as e:
        problems.append(f"scrolling right after Later: {e}")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize(
    "site_page",
    cells(["land.html"], [*PHONES, "desktop-1440x900"]),
    indirect=True,
)
def test_land_slice_steps_on_scroll(site_page):
    # The maps, then the slice step by step, as the reader scrolls (the
    # screenshots show each), then the questions; then a scroll right after
    # a tap on Next. No console error and no sideways scrolling throughout.
    # Every progress mark shows, the steps not yet reached among them.
    view, page = site_page, site_page.page
    page.wait_for_selector(".lnd-has-figure", timeout=30_000)
    problems = []
    marks = page.evaluate(
        "() => [...document.querySelectorAll('.lnd-progress li')]"
        ".map(li => getComputedStyle(li).backgroundColor)"
    )
    clear = [m for m in marks if m in ("transparent", "rgba(0, 0, 0, 0)")]
    if len(marks) != 6 or clear:
        problems.append(f"progress marks {marks}: {len(clear)} clear")
    page.evaluate(
        "document.querySelector('.lnd-maps').scrollIntoView({block:'start'})"
    )
    page.wait_for_timeout(800)
    view.shot("maps")

    def follows(n):
        got = page.evaluate(SLICE)
        assert got["stuck"] == "sticky", f"the drawing is not stuck: {got}"
        assert got["online"] == n, f"step {n} is not on the line: {got}"
        assert got["shown"] == n, f"step {n} on the line, drawn: {got}"
        assert got["over"] <= 0, f"sideways scrolling: {got}"

    for n in range(1, 7):
        page.evaluate(TO_STEP, n)
        try:
            view.wait(functools.partial(follows, n), timeout=5)
        except AssertionError as e:
            problems.append(f"scrolling: {e}")
        view.shot(f"step-{n}")
    page.evaluate(
        "document.querySelector('.lnd-qa').scrollIntoView({block:'start'})"
    )
    page.wait_for_timeout(300)
    view.shot("questions")

    # a scroll right after a tap: the drawing follows it once the tap's hold
    # ends
    page.evaluate(TO_STEP, 2)
    page.wait_for_timeout(1500)
    tap(view, page.locator(".lnd-sec .geo-step").nth(1))  # Next
    page.wait_for_timeout(300)
    page.evaluate(TO_STEP, 5)
    try:
        view.wait(functools.partial(follows, 5), timeout=5)
    except AssertionError as e:
        problems.append(f"scrolling right after Next: {e}")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


# The slice as land.js leaves it when its data is bad: the static drawing and
# the steps, with nothing it adds
STATIC = """() => ({
  figure: document.querySelector('.lnd-sec-body')
    .classList.contains('lnd-has-figure'),
  img: document.querySelectorAll('.lnd-art > img[src$="section.svg"]').length,
  svg: document.querySelectorAll('.lnd-art svg').length,
  buttons: document.querySelectorAll('.lnd-sec .geo-step').length,
  hint: document.querySelectorAll('.lnd-sec .geo-hint').length,
  marks: document.querySelectorAll('.lnd-progress li').length,
  live: document.querySelectorAll('.lnd-sec .geo-live').length,
  current: document.querySelectorAll('.lnd-current').length,
  title: document.querySelector('.lnd-now').textContent})"""
UNTOUCHED = {
    "figure": False,
    "img": 1,
    "svg": 0,
    "buttons": 0,
    "hint": 0,
    "marks": 0,
    "live": 0,
    "current": 0,
    "title": "",
}
# Each bad case: what section.json answers (None: the real file), and a
# script run in the page first (None: none). "late" makes the scroll
# watcher refuse the slice's steps (only theirs: the timeline's stages are
# watched as ever), so land.js fails after it has drawn and added its panel,
# and must take it all away again.
BAD_DATA = {
    "not-json": ("{not json", None),
    "malformed": (json.dumps({"length_ft": 1, "ground": []}), None),
    "late": (
        None,
        (
            "const watch = IntersectionObserver.prototype.observe;"
            " IntersectionObserver.prototype.observe = function (target) {"
            " if (target.classList.contains('lnd-step')) {"
            " throw new Error('a made-up failure'); }"
            " return watch.call(this, target); };"
        ),
    ),
}


@pytest.mark.parametrize("bad", list(BAD_DATA))
@pytest.mark.parametrize(
    "site_page",
    cells(["land.html"], ["phone-390x844", "desktop-1440x900"]),
    indirect=True,
)
def test_land_slice_keeps_its_static_drawing_on_bad_data(site_page, bad):
    view, page = site_page, site_page.page
    body, script = BAD_DATA[bad]
    if body is not None:
        page.route(
            "**/assets/land/section.json",
            lambda route: route.fulfill(
                status=200, content_type="application/json", body=body
            ),
        )
    if script is not None:
        page.add_init_script(script)
    warned = []
    page.on(
        "console",
        lambda m: warned.append(m.text) if m.type == "warning" else None,
    )
    page.reload(wait_until="load")
    with contextlib.suppress(PlaywrightTimeout):
        page.wait_for_load_state("networkidle", timeout=15_000)
    page.wait_for_timeout(500)
    page.evaluate(
        "document.querySelector('.lnd-fig').scrollIntoView({block:'start'})"
    )
    page.wait_for_timeout(300)
    view.shot(f"bad-{bad}")
    problems = []
    got = page.evaluate(STATIC)
    if got != UNTOUCHED:
        problems.append(f"{bad}: the slice is not as the page has it: {got}")
    if not any("keeps its static drawing" in w for w in warned):
        problems.append(f"{bad}: no warning in the console: {warned}")
    if bad == "late" and page.locator("#deep-time .geo-step").count() != 2:
        problems.append("late: the timeline lost its buttons")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


def land_shows(page, online, shown):
    """Asserts The land's drawing is stuck, with these stages.

    Args:
        page: The land's page.
        online: The stage that should be on the reading line.
        shown: The stage the drawing should show.
    """
    got = page.evaluate(LAND)
    assert got["stuck"] == "sticky", f"the drawing is not stuck: {got}"
    assert got["online"] == online, f"stage {online} is not on the line: {got}"
    assert got["shown"] == shown, (
        f"stage {online} on the line: stage {shown} should be drawn: {got}"
    )


@pytest.mark.parametrize(
    "site_page", cells(["land.html"], PHONES), indirect=True
)
def test_land_a_touch_or_the_wheel_ends_the_hold_at_once(site_page):
    view, page = site_page, site_page.page
    # Later holds the drawing for 1,200 ms by the page's clock; with that
    # clock stopped, neither the hold's timer nor Date.now() ever ends it, so
    # only the reader's own touch or wheel can (timeline.js, reader()). With
    # reduced motion the page jumps to a stage instead of gliding to it, so
    # each scroll is over before the next step.
    page.emulate_media(reduced_motion="reduce")
    page.clock.install()
    page.reload(wait_until="load")
    page.wait_for_selector(".geo-has-figure", timeout=30_000)
    page.clock.pause_at(datetime.datetime.now() + datetime.timedelta(minutes=1))
    # the page's left margin, low on the screen: under the stuck drawing and
    # away from its buttons
    margin = (6, page.viewport_size["height"] - 40)
    problems = []
    for gesture in ("touch", "wheel"):
        page.clock.run_for(2000)  # any hold left over ends by its timer
        page.evaluate(JUMP_TO_STAGE, 2)
        try:
            view.wait(functools.partial(land_shows, page, 2, 2), timeout=5)
            page.locator("#deep-time .geo-step").nth(1).tap()  # Later: 3, held
            page.evaluate(JUMP_TO_STAGE, 6)
            page.wait_for_timeout(300)
            land_shows(page, 6, 3)
        except AssertionError as e:
            problems.append(f"{gesture}: Later did not hold the drawing: {e}")
            continue
        if gesture == "touch":
            # a touch on the drawing's buttons is the reader's own hold
            box = page.locator("#deep-time .geo-count").bounding_box()
            touch(
                view, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            )
            page.wait_for_timeout(300)
            try:
                land_shows(page, 6, 3)
            except AssertionError as e:
                problems.append(f"a touch on the buttons ended the hold: {e}")
            touch(view, *margin)
        else:
            page.mouse.move(*margin)
            page.mouse.wheel(0, 1)
        try:
            view.wait(functools.partial(land_shows, page, 6, 6), timeout=3)
        except AssertionError as e:
            problems.append(
                f"a {gesture} outside the buttons did not end the hold: {e}"
            )
    view.shot("released")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize(
    "site_page", cells(["aquifer.html"], VIEWPORTS), indirect=True
)
def test_aquifer_panel_and_about_links_are_44px(site_page):
    view, page = site_page, site_page.page
    try:
        page.wait_for_function(AQUIFER_READY, timeout=LOAD_S * 1000)
    except PlaywrightTimeout:
        shot = view.shot("ready-FAILED")
        pytest.fail(
            f"{view.name}: the 3D view was not ready (html[data-aquifer]) "
            f"after {LOAD_S} s; screenshot: {shot}",
            pytrace=False,
        )
    problems = []
    toggle = page.locator("#aq-sheet-toggle")
    if toggle.is_visible():  # a phone: the panel is a sheet, shut
        tap(view, toggle)
        page.wait_for_timeout(500)  # it slides up in 0.28 s
    links = page.evaluate(BOXES, list(AQUIFER_LINKS))
    expected = page.locator(AQUIFER_LINKS[0]).count()
    if not expected or len(links) != expected:
        problems.append(f"the panel shows {len(links)} of {expected} links")
    problems += [f"under {TARGET} px: {s}" for s in small(links)]

    tap(view, page.locator(AQUIFER_LINKS[0]).first)  # About this map
    try:
        page.wait_for_selector("#aq-about[open]", timeout=10_000)
    except PlaywrightTimeout:
        problems.append("About this map did not open the About panel")
    else:
        page.wait_for_timeout(300)
        about = page.evaluate(BOXES, list(AQUIFER_ABOUT))
        expected = sum(page.locator(sel).count() for sel in AQUIFER_ABOUT)
        if len(about) != expected:
            problems.append(f"the About panel shows {len(about)} of {expected}")
        problems += [f"under {TARGET} px: {s}" for s in small(about)]
        wide = page.evaluate(SIDEWAYS)
        if max(wide["page"], wide["body"]) > wide["screen"] + 1:
            problems.append(f"scrolls sideways (About open): {wide}")
        view.shot("about-open")
        tap(view, page.locator("#aq-about-close"))
        page.wait_for_timeout(300)
        if page.locator("#aq-about[open]").count():
            problems.append("Close did not close the About panel")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


WELLS_VIEWS = {v: VIEWPORTS[v] for v in ("phone-390x844", "desktop-1440x900")}


def open_wells_filters(view):
    """Opens the panel (a bottom sheet on a phone), Wells and its Filters."""
    page = view.page
    sheet = page.locator("#aq-sheet-toggle")
    if sheet.is_visible() and sheet.get_attribute("aria-expanded") != "true":
        tap(view, sheet)
    for target in ("g-wells", "aq-filters"):
        button = page.locator(f'button[aria-controls="{target}"]')
        if button.get_attribute("aria-expanded") != "true":
            tap(view, button)


def wells_drawn(page, label, key, filters):
    """Checks that the wells settled as the filters say.

    Args:
        page: The 3D page.
        label: What was done, for the message.
        key: Which count of WELLS's must pass ("first", "allUses", ...).
        filters: What the Filters heading must say ("2 on", ...).

    Returns:
        WELLS's answer.
    """
    got = page.evaluate(WELLS)
    assert got and not got["updating"], f"{label}: still drawing"
    assert got["irrigation"], f"the default is not irrigation: {got}"
    count = got[key]
    mode = "overview" if count > got["farMax"] else "heads"
    assert got["shown"] == f"{count:,}", f"{label}: {got}"
    assert got["filters"] == filters, f"{label}: {got}"
    note = got["note"]
    assert note["mode"] == mode, f"{label}: {got}"
    assert not note.get("loading") and not note.get("failed"), f"{label}: {got}"
    assert got["orphans"] == 0, f"{label}: a heads layer left behind: {got}"
    if mode == "heads":
        assert got["visibleHeads"] == 1, f"{label}: {got}"
        # its layer holds every one; the view draws those on the screen,
        # all but a few at its edges (not one per cell)
        assert got["held"] == count, f"{label}: heads held: {got}"
        assert 0.9 * count <= got["drawn"] <= count, f"{label}: {got}"
    else:
        assert got["visibleHeads"] == 0, f"{label}: {got}"
    return got


def wells_hidden(page):
    """Checks that no wells' heads layer shows with the Wells switch off."""
    got = page.evaluate(WELLS)
    assert got["visibleHeads"] == 0 and got["orphans"] == 0, got


@pytest.mark.parametrize(
    "site_page", cells(["aquifer.html"], WELLS_VIEWS), indirect=True
)
def test_aquifer_wells_start_filtered_and_follow_the_filters(site_page):
    view, page = site_page, site_page.page
    page.wait_for_function(
        "document.documentElement.dataset.aquifer === 'ready'",
        timeout=LOAD_S * 1000,
    )
    problems = []
    steps = (
        ("at first", "first", "2 on", None),
        ("all uses", "allUses", "1 on", "#aq-uses-all"),
        ("reset", "first", "2 on", "#aq-wells-reset"),
        ("widened in quick steps", "anyYield", "1 on", WIDEN),
    )
    try:
        for label, key, filters, action in steps:
            if action == WIDEN:
                page.evaluate(WIDEN)
            elif action:
                open_wells_filters(view)
                tap(view, page.locator(action))
            view.wait(
                functools.partial(wells_drawn, page, label, key, filters),
                timeout=60,
            )
            if label == "at first":
                view.shot("wells-first")
        show = page.locator("#aq-wells-show")
        show.evaluate("(box) => box.click()")
        view.wait(functools.partial(wells_hidden, page), timeout=15)
        show.evaluate("(box) => box.click()")
        tap(view, page.locator("#aq-wells-reset"))
        view.wait(
            functools.partial(
                wells_drawn, page, "reset again", "first", "2 on"
            ),
            timeout=60,
        )
    except AssertionError as e:
        problems.append(f"{e}; screenshot: {view.shot('wells-FAILED')}")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)
