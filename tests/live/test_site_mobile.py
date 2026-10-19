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
  on the pages those ACTIONS lists (.text-link, the map's Layers button,
  The land's Earlier and Later, Home's ways in and arrival links, the map's
  panel links and About contents); other links and buttons (links
  inside sentences, the vineyards form) are not measured. One hidden by
  design is not measured: inside a [hidden] element, or not rendered
  (checkVisibility(): display:none, visibility:hidden, the content of a shut
  <details> or <dialog>). Every other one is, so a box collapsed to 1.5 px
  or less fails as too small.
Every menu link, tapped on a phone and clicked on the desktop, opens its
page, which marks it as the current one (The water: the map as the water,
map.html?layers=aquifer,vineyards,places). The place line also fits at
700 px, the narrowest screen that shows it. A page that has moved
(explore.html, aquifer.html) is not a page of its own: it sends the reader on
to the map.
The map (map.html), at every viewport: its panel's links (on a phone, with
the Layers sheet opened) and, opened from "About this map", the About
panel's contents links and Close button are 44 px each way.
The map, on the phones:
- tapping three steps, a quarter, a half and three quarters of the way along
  the line (docs/data/steps.geojson), opens each one's popup, docked along the
  map's bottom, and the place tapped stays in view, near the middle of the map
  left above the popup; closing it takes the view's padding away; the popup
  has no undock button;
- the Layers sheet opens and closes, and a popup and the sheet never show
  together; 3D tilts the map and 2D brings it back north up and straight
  down; Home goes back to where the page opened; the page does not scroll
  under the map; the map's buttons (zoom, Home, compass, 3D) and the sheet's
  are 44 px.
The map, on two phones and the desktop: it opens on the district alone and
loads none of the aquifer's data but its figures; the wells, turned on, load
and start at the script's DEFAULT_FILTER (irrigation wells that tested at
25 gpm or more), and Reset comes back to it; ?layers=all turns on every group
without an error; The water draws the aquifer and is headed and marked as the
water; ?step= opens that step's popup; and the old addresses, explore.html and
aquifer.html, go to the map with their query and #fragment (and, without
JavaScript, by their meta refresh).
The map's wells on a phone (390x844) and the desktop (#148), through the
page's window.aquiferWells, once turned on: at first the default filters'
wells (irrigation, the default yield and up, counted here from the data),
every one's head drawn zoomed out; "All" uses thins them to the overview;
filters widened in quick steps leave one heads layer on the map, in step with
the filters and the Wells switch; Reset comes back to the first count.
The land, on the phones: the drawing steps to the stage on the reading line
as the page scrolls, and still does when the reader scrolls right after
tapping Later (the tap holds the drawing for 1,200 ms); and, with the page's
clock stopped so that only the reader can end the hold, a touch outside the
drawing's buttons or a turn of the wheel ends it at once, while a touch on
the buttons does not (timeline.js, reader()).
A map must settle (ready, not updating) within 30 s of each move, or the
test fails there.
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
import re
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
WATER = "map.html?layers=aquifer,vineyards,places"
# The pages that have moved (a meta refresh): where each sends the reader.
MOVED = {"explore.html": "map.html", "aquifer.html": WATER}
PAGES = sorted(
    p.name for p in (ROOT / "docs").glob("*.html") if p.name not in MOVED
)
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
    "map.html": ".aq-stage arcgis-scene",
    "walk.html": ".walk-map arcgis-map",
}
SCENE = MAPS["map.html"]


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


# The map's steps to tap; the tapped place's height in the map left above
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
    ("The water", WATER),
    ("The vineyards", "vineyards.html"),
    ("Status", "status.html"),
    ("Journal", "journal.html"),
    ("About & contact", "about.html"),
)
PLACE_LINE = "Llano Uplift · Texas Hill Country"
FOOTER = (".site-footer a",)
ACTIONS = (
    "main .text-link",
    "main .lp-sheet-toggle",
    "main .geo-step",
    "main .way-list>a",
    "main .arrival-foot a",
    "main .lp-link",  # the map's panel: About this map, Walk the line, Sources
    "main .about-toc a",  # its About panel's contents (rendered when open)
)
# The map: the panel's links, and the About panel's contents and Close
MAP_LINKS = ("main .lp-link",)
MAP_ABOUT = ("main .aq-about .about-toc a", "main .aq-about .about-close")
# the panel's links but those in a group closed (hidden), which BOXES skips
SHOWN_LINKS = """() => [...document.querySelectorAll('main .lp-link')]
  .filter(e => !e.closest('[hidden]')).length"""

# ---------------------------------------------------------------- in the page
READY = """(sel) => { const m = document.querySelector(sel);
  return !!(m && m.view && m.view.ready && !m.view.updating); }"""

# the map (map3d.js): opened as its address says, and drawn
SCENE_READY = """() => document.documentElement.dataset.map === 'ready' &&
  !!(window.mapView && window.mapView.ready && !window.mapView.updating)"""

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

# the map's buttons (zoom in and out, Home, the compass) in their shadow
# roots, and the map's own 3D button
CONTROLS = """() => { const out = [];
  const box = (host, b) => { const r = b.getBoundingClientRect();
    if (r.width) out.push({host, w: r.width, h: r.height,
      x: r.left + r.width / 2, y: r.top + r.height / 2}); };
  for (const host of document.querySelectorAll(
      'arcgis-zoom, arcgis-home, arcgis-compass')) {
    for (const b of host.shadowRoot.querySelectorAll('calcite-button')) {
      box(host.localName, b); } }
  const look = document.getElementById('map-look');
  if (look) box('map-look', look);
  return out; }"""

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

AWAY = """async (sel) => { const v = document.querySelector(sel).view;
  await v.goTo({center: [-98.9, 30.9], scale: 300000}, {animate: false}); }"""

# the map's state: its camera, groups, layers, the sheet and the popup
MAP3D = """() => { const v = window.mapView; const c = v.camera;
  const on = [...document.querySelectorAll('[data-group-switch]')]
    .filter(b => b.checked).map(b => b.dataset.groupSwitch);
  const look = document.getElementById('map-look');
  const panel = document.getElementById('aq-panel');
  return {tilt: c.tilt, heading: c.heading, scale: v.scale,
    center: [v.center.longitude, v.center.latitude], groups: on,
    ground: v.map.ground.opacity,
    meshes: v.graphics.filter(g => !!g.geometry).length,
    layers: v.map.layers.filter(l => l.visible).map(l => l.title).toArray(),
    look: look.textContent.trim(), pressed: look.getAttribute('aria-pressed'),
    sheet: panel.classList.contains('is-open'),
    popup: document.querySelector('arcgis-popup').open,
    title: document.getElementById('aq-title').textContent,
    docTitle: document.title,
    current: [...document.querySelectorAll(
      '.site-header nav a[aria-current="page"]')].map(a => a.textContent),
    url: location.pathname.split('/').pop() + location.search + location.hash};
  }"""

# opens a step's popup as a tap does, through the scene's own popup
OPEN_STEP = """async (step) => {
  const s = document.querySelector('.aq-stage arcgis-scene');
  const layer = s.map.layers.find(l => l.title === 'Steps');
  const q = await layer.queryFeatures(
    {where: `step = ${step}`, outFields: ['*'], returnGeometry: true});
  await s.openPopup({features: q.features,
                     location: q.features[0].geometry.extent.center}); }"""

# the wells' filters as the panel shows them
WELLS = """() => { const w = window.aquiferWells;
  return {shown: w.counts().shown, total: w.index.filter_keys.length,
    uses: [...document.querySelectorAll('#aq-uses input')].filter(i =>
      i.checked).map(i => i.parentElement.querySelector('span').textContent),
    yield: document.getElementById('aq-yield-out').textContent,
    noYield: document.getElementById('aq-yield-none').checked,
    depth: document.getElementById('aq-depth-out').textContent,
    filters: document.getElementById('aq-filters-state').textContent,
    shownText: document.getElementById('aq-wells-shown').textContent}; }"""

# scrolls the panel (not the page) so an element is at its top
PANEL_TO = """(sel) => { const b = document.getElementById('aq-panel-body');
  const el = document.querySelector(sel);
  b.scrollTop += el.getBoundingClientRect().top
    - b.getBoundingClientRect().top - 4; }"""

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

# the same, at once (no smooth scrolling)
JUMP_TO_STAGE = """(n) => { document.querySelectorAll('.geo-stage')[n - 1]
  .scrollIntoView({block: 'start', behavior: 'instant'}); }"""

# The map's wells as drawn and counted, through the page's own hooks; the
# default's counts are counted here from the data the page loaded
HEADS = """async () => {
  const w = window.aquiferWells; const v = window.aquiferView;
  if (!w || !v || document.documentElement.dataset.map !== 'ready')
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
        self.requested = []  # the site's own files asked for, by path
        page.on("console", self._console)
        page.on("request", self._request)
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

    def _request(self, request):
        if own(request.url):
            self.requested.append(urlsplit(request.url).path.lstrip("/"))

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
    name = f"{slug(page_name)}-{viewport}"
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
            if page_name.startswith("map.html"):
                view.page.wait_for_function(SCENE_READY, timeout=LOAD_S * 1000)
            elif page_name in MAPS:
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


def slug(page):
    """Returns a page's address as a name for a test or a screenshot."""
    path, _, query = page.partition("?")
    name = path.removesuffix(".html")
    if not query:
        return name
    return f"{name}-{query.replace('=', '-').replace(',', '-')}"


def cells(pages, viewports):
    """Returns the (page, viewport) pairs to load, for indirect parameters."""
    return [
        pytest.param((p, v), id=f"{slug(p)}-{v}")
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
        url = urlsplit(page.url)
        landed = url.path.rsplit("/", 1)[-1]
        if url.query:
            landed += f"?{url.query}"
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
    "site_page", cells(["map.html"], PHONES), indirect=True
)
def test_map_popup_leaves_the_tapped_step_in_view(site_page):
    view, page = site_page, site_page.page
    sel = SCENE
    problems = []
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


def tap_at(view, selector):
    """Taps the middle of an element as a finger does, never scrolling to it.

    Playwright's own tap scrolls the page to reach an element something
    covers for a moment (a popup docking over the Layers bar), which no
    finger does.
    """
    box = view.page.locator(selector).bounding_box()
    assert box, f"{selector} is not on the screen"
    view.page.touchscreen.tap(
        box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    )


def north(heading):
    """Degrees between a heading and north."""
    h = heading % 360
    return min(h, 360 - h)


def turn_on(view, group, on=True):
    """Turns a group on (or off) by its switch, in the sheet on a phone."""
    page = view.page
    if view.phone and not page.evaluate(MAP3D)["sheet"]:
        tap(view, page.locator("#aq-sheet-toggle"))
        page.wait_for_timeout(700)
    page.evaluate(PANEL_TO, f'[data-group="{group}"]')
    page.wait_for_timeout(300)
    box = page.locator(f'[data-group-switch="{group}"]')
    if box.is_checked() != on:
        tap(
            view,
            page.locator(f'label.lp-swhit:has([data-group-switch="{group}"])'),
        )
    if view.phone:
        page.wait_for_timeout(300)
        tap(view, page.locator("#aq-sheet-toggle"))
        page.wait_for_timeout(700)


def default_filter():
    """The wells' first filter, (use group, lowest yield), from the script."""
    text = (ROOT / "docs" / "assets" / "aquifer-wells.js").read_text(
        encoding="utf-8"
    )
    found = re.search(
        r'export const DEFAULT_FILTER = \{ use: "(\w+)", yieldLo: (\d+), '
        r"noYield: false \};",
        text,
    )
    assert found, "aquifer-wells.js has no DEFAULT_FILTER"
    return found.group(1), int(found.group(2))


def default_wells():
    """How many wells pass the first filter, counted from the data."""
    use, low = default_filter()
    with open(
        ROOT / "docs" / "assets" / "aquifer" / "wells" / "index.json",
        encoding="utf-8",
    ) as fh:
        index = json.load(fh)
    group = index["use_groups"].index(use)
    return sum(
        1
        for u, _, gpm, _ in index["filter_keys"]
        if u == group and gpm is not None and gpm >= low
    )


THREE = ["phone-390x844", "phone-360x780", "desktop-1440x900"]


@pytest.mark.parametrize(
    "site_page", cells(["map.html"], PHONES), indirect=True
)
def test_map_on_a_phone(site_page):
    view, page = site_page, site_page.page
    problems = []
    opened = page.evaluate(MAP3D)
    if opened["tilt"] > 1 or north(opened["heading"]) > 1:
        problems.append(f"the map does not open straight down: {opened}")
    controls = page.evaluate(CONTROLS)
    # zoom in, zoom out, Home and the compass, each a calcite-button in its
    # shadow root, and the 3D button: none found means the SDK has changed,
    # not that they are big enough
    hosts = sorted({c["host"] for c in controls})
    if len(controls) < 5 or hosts != [
        "arcgis-compass",
        "arcgis-home",
        "arcgis-zoom",
        "map-look",
    ]:
        problems.append(
            "the map's zoom, Home, compass and 3D buttons are not found "
            f"({len(controls)} found in {hosts}): has the SDK changed?"
        )
    problems += [
        f"map button under {TARGET} px: {c['host']} {c['w']:.0f}x{c['h']:.0f}"
        for c in controls
        if c["w"] < TARGET - SUBPIXEL or c["h"] < TARGET - SUBPIXEL
    ]

    # the Layers sheet, and a popup: never both
    toggle = "#aq-sheet-toggle"
    tap_at(view, toggle)
    page.wait_for_timeout(800)
    if not page.evaluate(MAP3D)["sheet"]:
        problems.append("the Layers button did not open the sheet")
    sheet = (".lp-sheet-toggle", ".seg button", ".lp-gt", ".lp-swhit")
    problems += [
        f"under {TARGET} px in the sheet: {s}"
        for s in small(page.evaluate(BOXES, list(sheet)))
    ]
    view.shot("sheet")
    page.evaluate(OPEN_STEP, STEPS[1])

    def popup_alone():
        got = page.evaluate(MAP3D)
        assert got["popup"] and not got["sheet"], f"popup and sheet: {got}"

    def sheet_alone():
        got = page.evaluate(MAP3D)
        assert got["sheet"] and not got["popup"], f"sheet and popup: {got}"

    try:
        view.wait(popup_alone, timeout=10)
    except AssertionError as e:
        problems.append(f"a popup opened: {e}")
    page.wait_for_timeout(1000)  # the popup docks
    tap_at(view, toggle)
    try:
        view.wait(sheet_alone, timeout=10)
    except AssertionError as e:
        problems.append(f"the sheet opened: {e}")
    page.wait_for_timeout(800)  # the sheet slides up
    tap_at(view, toggle)
    page.wait_for_timeout(800)
    if page.evaluate(MAP3D)["sheet"]:
        problems.append("the Layers button did not close the sheet")

    # 3D tilts the map; 2D brings it back north up and straight down
    look = "#map-look"
    tap_at(view, look)

    def tilted():
        got = page.evaluate(MAP3D)
        assert got["tilt"] > 30, f"3D did not tilt the map: {got}"
        assert (got["look"], got["pressed"]) == ("2D", "true"), got
        return got

    def flat():
        got = page.evaluate(MAP3D)
        assert got["tilt"] < 1, f"2D did not bring the map down: {got}"
        assert north(got["heading"]) < 1, f"2D is not north up: {got}"
        assert (got["look"], got["pressed"]) == ("3D", "false"), got
        return got

    try:
        view.wait(tilted, timeout=15)
        view.shot("3d")
        tap_at(view, look)
        view.wait(flat, timeout=15)
    except AssertionError as e:
        problems.append(str(e))

    # Home goes back to where the page opened
    page.evaluate(AWAY, SCENE)
    settle(view, SCENE)
    home = [c for c in page.evaluate(CONTROLS) if c["host"] == "arcgis-home"]
    if not home:
        problems.append("no Home button on the map")
    else:
        page.touchscreen.tap(home[0]["x"], home[0]["y"])

        def back():
            got = page.evaluate(MAP3D)
            off = abs(got["scale"] - opened["scale"]) / opened["scale"]
            assert off < 0.05, f"Home: scale {got['scale']:.0f}, {opened}"
            assert (
                max(
                    abs(a - b)
                    for a, b in zip(
                        got["center"], opened["center"], strict=True
                    )
                )
                < 0.01
            ), f"Home: centre {got['center']}, {opened['center']}"

        try:
            view.wait(back, timeout=15)
        except AssertionError as e:
            problems.append(str(e))
    if scrolled := page.evaluate("scrollY"):
        problems.append(f"the page scrolled {scrolled:.0f} px under the map")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("site_page", cells(["map.html"], THREE), indirect=True)
def test_the_map_loads_only_the_district_and_the_wells_start_at_the_default(
    site_page,
):
    view, page = site_page, site_page.page
    problems = []
    data = sorted(u for u in view.requested if u.startswith("data/"))
    if data != [
        "data/boundary.geojson",
        "data/points.geojson",
        "data/steps.geojson",
    ]:
        problems.append(f"the map loaded {data} from data/")
    others = [
        u
        for u in view.requested
        if u.startswith("assets/aquifer/") and u != "assets/aquifer/stats.json"
    ]
    if others:
        problems.append(f"the map loaded the aquifer's {others} at once")
    opened = page.evaluate(MAP3D)
    if opened["groups"] != ["district"] or opened["layers"] != [
        "Proposed revision",
        "Steps",
        "Points",
    ]:
        problems.append(f"the map opens with more than the district: {opened}")

    turn_on(view, "wells")
    try:
        page.wait_for_function("!!window.aquiferWells", timeout=LOAD_S * 1000)
    except PlaywrightTimeout:
        problems.append("the wells did not load when turned on")
        problems += view.problems()
        pytest.fail(f"{view.name}:\n  " + "\n  ".join(problems), pytrace=False)
    if "assets/aquifer/wells/index.json" not in view.requested:
        problems.append("turning on the wells did not load wells/index.json")
    settle(view, SCENE)
    got = page.evaluate(MAP3D)
    if got["tilt"] < 30 or got["ground"] != 0.4:
        problems.append(
            f"the wells did not tilt the view or clear the ground: {got}"
        )
    # the basemap is kept too: with the wells on, a bare address opens dark
    if got["url"] != "map.html?layers=wells&basemap=imagery":
        problems.append(f"the address did not keep the wells: {got['url']}")
    view.shot("wells")

    use, low = default_filter()
    first = page.evaluate(WELLS)
    want = default_wells()
    if first["uses"] != [use] or first["shown"] != want:
        problems.append(
            f"the wells start with {first}, not {use} ({want} wells)"
        )
    if not first["yield"].startswith(f"{low:,}–") or first["noYield"]:
        problems.append(f"the wells' yield starts at {first}, not {low} gpm")
    if (first["filters"], first["depth"]) != ("2 on", "all"):
        problems.append(f"the wells' filters start as {first}")
    if first["shownText"] != f"{want:,}":
        problems.append(f"the panel says {first['shownText']} wells match")
    page.locator("#aq-uses-all").dispatch_event("click")
    page.wait_for_timeout(500)
    wider = page.evaluate(WELLS)
    if wider["shown"] <= first["shown"]:
        problems.append(f"All uses did not widen the wells: {wider}")
    page.locator("#aq-wells-reset").dispatch_event("click")
    page.wait_for_timeout(500)
    if (reset := page.evaluate(WELLS)) != first:
        problems.append(f"Reset gave {reset}, not the first filter {first}")
    wide = page.evaluate(SIDEWAYS)
    if max(wide["page"], wide["body"]) > wide["screen"] + 1:
        problems.append(f"scrolls sideways: {wide}")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize(
    "site_page", cells(["map.html?layers=all"], THREE), indirect=True
)
def test_every_group_turns_on(site_page):
    view, page = site_page, site_page.page
    problems = []
    groups = ["district", "places", "wells", "vineyards", "boundaries"]
    groups += ["geology", "aquifer"]

    def drawn():
        got = page.evaluate(MAP3D)
        assert got["groups"] == groups, got
        assert got["meshes"] == 4, f"the aquifer is not drawn: {got}"
        assert page.evaluate("!!window.aquiferWells"), "no wells"
        for title in (
            "Towns (Census 2023)",
            "Hickory Sands District vineyards",
            "Llano Uplift AVA (proposed, TTB)",
            "County lines (Census 2023)",
            "Hickory Sandstone Member formation (USGS geologic map, shifted)",
            "Precambrian rock at the surface (TWDB model layer 8)",
        ):
            assert title in got["layers"], f"{title} is not drawn: {got}"
        return got

    try:
        view.wait(drawn, timeout=LOAD_S)
    except AssertionError as e:
        problems.append(str(e))
    settle(view, SCENE)
    view.shot("all")
    turn_on(view, "aquifer", on=False)
    got = page.evaluate(MAP3D)
    want = "map.html?layers=places,wells,vineyards,boundaries,geology"
    if got["url"] != want:
        problems.append(f"the address reads {got['url']}, not {want}")
    if page.evaluate(
        "() => window.mapView.graphics.some(g => g.visible && g.geometry)"
    ):
        problems.append("the aquifer still shows when turned off")
    wide = page.evaluate(SIDEWAYS)
    if max(wide["page"], wide["body"]) > wide["screen"] + 1:
        problems.append(f"scrolls sideways: {wide}")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("site_page", cells([WATER], THREE), indirect=True)
def test_the_water(site_page):
    view, page = site_page, site_page.page
    problems = []

    def water():
        got = page.evaluate(MAP3D)
        assert got["groups"] == ["district", "places", "vineyards", "aquifer"]
        assert got["meshes"] == 4, f"the aquifer is not drawn: {got}"
        return got

    try:
        got = view.wait(water, timeout=LOAD_S)
    except AssertionError as e:
        problems.append(str(e))
        got = page.evaluate(MAP3D)
    if got["title"] != "The Hickory Aquifer" or not got["docTitle"].startswith(
        "The Hickory Aquifer in 3D"
    ):
        problems.append(f"The water is not headed as the aquifer: {got}")
    if got["current"] != ["The water"]:
        problems.append(f"the menu marks {got['current']}, not The water")
    if got["tilt"] < 30 or got["ground"] != 0.4:
        problems.append(f"The water does not open tilted, see-through: {got}")
    dark = page.get_attribute('button[data-basemap="dark"]', "aria-pressed")
    if dark != "true":
        problems.append("The water does not open on the dark basemap")
    settle(view, SCENE)
    view.shot("water")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize(
    "site_page",
    cells(
        [f"map.html?step={STEPS[1]}", "map.html?point=beginning"],
        ["phone-390x844", "desktop-1440x900"],
    ),
    indirect=True,
)
def test_a_step_or_point_in_the_address_opens_its_popup(site_page):
    view, page = site_page, site_page.page
    want = ("step", STEPS[1]) if "step=" in page.url else ("point", "Beginning")

    def opened():
        got = page.evaluate(
            "() => { const p = document.querySelector('arcgis-popup');"
            " const f = p.selectedFeature;"
            " return {open: p.open, a: f && f.attributes}; }"
        )
        assert got["open"] and got["a"], f"no popup: {got}"
        assert got["a"].get(want[0]) == want[1], got
        return got

    problems = []
    try:
        view.wait(opened, timeout=30)
    except AssertionError as e:
        problems.append(str(e))
    view.shot("popup")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


def test_old_addresses_go_to_the_map(chrome):
    p, browser = chrome
    step = STEPS[1]
    rows = [
        ("explore.html", "map.html", True),
        (f"explore.html?step={step}#map", f"map.html?step={step}#map", True),
        ("aquifer.html", WATER, True),
        ("aquifer.html?view=district", f"{WATER}&view=district", True),
        ("aquifer.html?view=district", WATER, False),
        ("aquifer.html?layers=wells", "map.html?layers=wells", True),
    ]
    problems = []
    for old, new, js in rows:
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            java_script_enabled=js,
            user_agent=p.devices["iPhone 13"]["user_agent"],
        )
        view = SiteView(
            f"moved-{slug(old)}-{'js' if js else 'nojs'}",
            context.new_page(),
            True,
        )
        page = view.page
        try:
            page.goto(f"{BASE}/{old}", wait_until="commit")
            page.wait_for_url("**/map.html*", timeout=30_000)
            landed = page.url.removeprefix(f"{BASE}/")
            if landed != new:
                problems.append(f"{old} (JavaScript {js}): {landed}, not {new}")
            if js and "step=" in old:
                page.wait_for_function(SCENE_READY, timeout=LOAD_S * 1000)
                page.wait_for_function(
                    "(s) => { const p = document.querySelector('arcgis-popup');"
                    " return p.open && p.selectedFeature &&"
                    " p.selectedFeature.attributes.step === s; }",
                    arg=step,
                    timeout=30_000,
                )
            if js:
                page.go_back(wait_until="commit")
                if "explore.html" in page.url or "aquifer.html" in page.url:
                    problems.append(f"{old}: Back returns to the moved page")
        except PlaywrightError as e:
            problems.append(f"{old} (JavaScript {js}): {type(e).__name__}: {e}")
            view.shot("FAILED")
        finally:
            view.close()
    assert not problems, "\n  ".join(problems)


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
    page.locator(".geo-step").nth(1).tap()  # Later
    page.wait_for_timeout(300)
    page.evaluate(TO_STAGE, 6)
    try:
        view.wait(functools.partial(follows, 6), timeout=5)
    except AssertionError as e:
        problems.append(f"scrolling right after Later: {e}")
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
            page.locator(".geo-step").nth(1).tap()  # Later: stage 3, held
            page.evaluate(JUMP_TO_STAGE, 6)
            page.wait_for_timeout(300)
            land_shows(page, 6, 3)
        except AssertionError as e:
            problems.append(f"{gesture}: Later did not hold the drawing: {e}")
            continue
        if gesture == "touch":
            # a touch on the drawing's buttons is the reader's own hold
            box = page.locator(".geo-count").bounding_box()
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
    "site_page", cells(["map.html", WATER], VIEWPORTS), indirect=True
)
def test_map_panel_and_about_links_are_44px(site_page):
    # site_page waits until the map is drawn and its panel wired
    # (html[data-map="ready"])
    view, page = site_page, site_page.page
    problems = []
    toggle = page.locator("#aq-sheet-toggle")
    if toggle.is_visible():  # a phone: the panel is a sheet, shut
        tap(view, toggle)
        page.wait_for_timeout(500)  # it slides up in 0.28 s
    links = page.evaluate(BOXES, list(MAP_LINKS))
    expected = page.evaluate(SHOWN_LINKS)
    if not expected or len(links) != expected:
        problems.append(f"the panel shows {len(links)} of {expected} links")
    problems += [f"under {TARGET} px: {s}" for s in small(links)]

    tap(view, page.locator(MAP_LINKS[0]).first)  # About this map
    try:
        page.wait_for_selector("#aq-about[open]", timeout=10_000)
    except PlaywrightTimeout:
        problems.append("About this map did not open the About panel")
    else:
        page.wait_for_timeout(300)
        about = page.evaluate(BOXES, list(MAP_ABOUT))
        expected = sum(page.locator(sel).count() for sel in MAP_ABOUT)
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
        page: The map, its wells turned on.
        label: What was done, for the message.
        key: Which count of HEADS's must pass ("first", "allUses", ...).
        filters: What the Filters heading must say ("2 on", ...).

    Returns:
        HEADS's answer.
    """
    got = page.evaluate(HEADS)
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
    got = page.evaluate(HEADS)
    assert got["visibleHeads"] == 0 and got["orphans"] == 0, got


@pytest.mark.parametrize(
    "site_page", cells(["map.html"], WELLS_VIEWS), indirect=True
)
def test_the_wells_start_filtered_and_follow_the_filters(site_page):
    view, page = site_page, site_page.page
    turn_on(view, "wells")
    page.wait_for_function("!!window.aquiferWells", timeout=LOAD_S * 1000)
    # as The water opened before the map: the whole aquifer, from above
    page.locator('button[data-place="whole"]').dispatch_event("click")
    page.wait_for_timeout(2500)
    settle(view, SCENE)
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


@pytest.mark.parametrize(
    "site_page",
    cells(
        ["map.html?step=999", "map.html?point=998"],
        ["phone-390x844", "desktop-1440x900"],
    ),
    indirect=True,
)
def test_a_step_or_point_that_does_not_exist_is_said(site_page):
    view, page = site_page, site_page.page
    asked = "step 999" if "step=" in page.url else "point 998"
    got = page.evaluate(MAP3D)
    status = page.evaluate("document.getElementById('aq-status').textContent")
    problems = []
    if f"There is no {asked}." not in status:
        problems.append(f"the status line reads {status!r}")
    if "Loading" in status:
        problems.append(f"the status line still says it is loading: {status!r}")
    if got["popup"] or got["groups"] != ["district"] or got["tilt"] > 1:
        problems.append(f"the map did not stay on the whole district: {got}")
    view.shot("not-found")
    problems += view.problems()
    assert not problems, f"{view.name}:\n  " + "\n  ".join(problems)


STATUS_LINE = "() => document.getElementById('aq-status').textContent"
SETTLED_OR_FAILED = """() => ['ready', 'failed'].includes(
  document.documentElement.dataset.map)"""


def failing(chrome, address, aborted, refuse_basemap=False):
    """Opens the map with some of its files refused, as a SiteView.

    Args:
        chrome: The chrome fixture.
        address: The map's address, such as "map.html?layers=geology".
        aborted: The site's files whose requests fail (paths in docs/).
        refuse_basemap: Esri refuses the basemap too (HTTP 401), as for a
            key that has expired.

    Returns:
        The SiteView, once the map is ready or has failed.
    """
    p, browser = chrome
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        is_mobile=True,
        has_touch=True,
        user_agent=p.devices["iPhone 13"]["user_agent"],
    )
    view = SiteView(f"failing-{slug(address)}", context.new_page(), True)
    for path in aborted:
        view.page.route(f"{BASE}/{path}", lambda route: route.abort("failed"))
    if refuse_basemap:
        view.page.route(
            "**/basemapstyles-api.arcgis.com/**",
            lambda route: route.fulfill(
                status=401,
                content_type="application/json",
                body='{"error": {"code": 401, "message": "refused"}}',
            ),
        )
    view.page.goto(f"{BASE}/{address}", wait_until="load")
    view.page.wait_for_function(SETTLED_OR_FAILED, timeout=LOAD_S * 1000)
    return view


def unexpected(view, aborted):
    """The page's errors but those the refused files explain."""
    return [
        e
        for e in view.errors
        if not any(path in e for path in aborted) and "could not be" not in e
    ]


def test_a_file_that_does_not_load_is_said(chrome):
    # Geology's Hickory Sandstone Member formation and the page's figures do
    # not load, and Esri refuses the basemap: the map still opens, says each
    # in its status line, unticks the layer that failed and leaves no "…".
    aborted = [
        "assets/aquifer/hickory-member.geojson",
        "assets/aquifer/stats.json",
    ]
    view = failing(chrome, "map.html?layers=geology", aborted, True)
    page = view.page
    problems = []
    try:

        def said():
            status = page.evaluate(STATUS_LINE)
            for words in (
                "Esri’s basemap could not be loaded",
                "“Hickory Sandstone Member formation (USGS geologic map,",
                "figures could not be loaded",
            ):
                assert words in status, f"{words!r} not in {status!r}"
            assert "Loading" not in status, status
            return status

        view.wait(said, timeout=30)
        state = page.evaluate(
            "() => ({map: document.documentElement.dataset.map,"
            " member: document.querySelector('[data-switch=member]').checked,"
            " precambrian: document.querySelector("
            "'[data-switch=precambrian]').checked,"
            " dots: [...document.querySelectorAll('[data-stat]')]"
            ".filter(e => e.textContent === '…').length})"
        )
        if state != {
            "map": "ready",
            "member": False,
            "precambrian": True,
            "dots": 0,
        }:
            problems.append(f"after the failures: {state}")
        view.shot("failed-files")
    except AssertionError as e:
        problems.append(f"{e}; screenshot: {view.shot('failed-files-FAILED')}")
    finally:
        problems += unexpected(view, aborted)
        view.close()
    assert not problems, "\n  ".join(problems)


def test_the_map_says_so_when_the_boundary_does_not_load(chrome):
    aborted = ["data/steps.geojson"]
    view = failing(chrome, "map.html", aborted)
    page = view.page
    problems = []
    try:
        status = page.evaluate(STATUS_LINE)
        state = page.evaluate("document.documentElement.dataset.map")
        if state != "failed":
            problems.append(f"html[data-map] is {state!r}, not 'failed'")
        if (
            "the boundary could not be loaded" not in status
            or "Loading" in status
        ):
            problems.append(f"the status line reads {status!r}")
        view.shot("failed-boundary")
    finally:
        problems += unexpected(view, aborted)
        view.close()
    assert not problems, "\n  ".join(problems)
