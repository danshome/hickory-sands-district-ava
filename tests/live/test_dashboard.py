"""The published dashboard in Google Chrome, as a reader sees it (issue #68): two phones and four laptop and desktop
screens, anonymously, read-only (taps and clicks change nothing on the site). Marked live: ./build.sh test and the lint
workflow leave them out; ./build.sh check-live runs them after agol_check.py, or alone:
    .venv/bin/python -m pytest -m live tests/live
- phones (Playwright's iPhone 14 and Pixel 7: their user agent, touch, mobile and pixel ratio, at 390x844 and 412x915):
  ArcGIS Dashboards shows the phone layout (mobileView, #49), not the desktop one; the header; the three indicators'
  numbers, their captions inside their boxes and not printed over each other; the map drawn; the four tabs each open
  with content; every step in the Steps list, and tapping one moves the map; the Documents tab's links go to items in
  the group; no sideways scrolling; the drawer's step selector, whose "Corrections" choice leaves (49) and (85);
- laptops and desktops (1280x720, 1366x650, 1536x750, 1920x1080): the desktop layout; the five indicators' numbers and
  captions (#45); every left tab reachable, the USGS quadrangles tab's GeoPDF and GeoTIFF links each on one line (#47);
  the right tabs; no sideways scrolling.
The figures come from the build's outputs (HSD_WORK, else target/work) when they are there, else from the publish of
Oct. 17, 2026 (FALLBACK). Screenshots: target/browser-tests/ (conftest.py)."""
import csv, json, math, os, re, warnings
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright is in requirements-dev.txt: run ./build.sh env")
from src.publish.agol_check import ITEM_LINK, holds   # noqa: E402  (after the skip: the same rules as the live checks)

pytestmark = pytest.mark.live
ROOT = Path(__file__).resolve().parents[2]
PHONES = {"iphone-14-390x844": ("iPhone 14", 390, 844), "pixel-7-412x915": ("Pixel 7", 412, 915)}
SCREENS = ["1280x720", "1366x650", "1536x750", "1920x1080"]   # 1366 laptops; 1920x1080 at 150% and 125% Windows scaling
FALLBACK = {"sqmi": "193.83", "steps": 104, "changed": 15, "places": 6, "acres": "1,050", "corrections": [49, 85]}
SLACK = 2   # px: how far a text's em box may reach past its indicator's box or into the text above it


def figures():
    """what the indicators and the step list should show"""
    work = Path(os.environ.get("HSD_WORK") or ROOT / "target" / "work")
    try:
        built = json.loads((work / "agreed-steps.json").read_text())
        stats = json.loads((work / "review" / "ttb-diff-stats.json").read_text())
    except FileNotFoundError:
        return dict(FALLBACK, source="the publish of Oct. 17, 2026 (no build outputs in target/work)")
    steps, same = built["steps"], stats["areas"]["drawing"]   # acres from the same text drawn differently, both sides
    change = lambda s: (s["change"] or "").lower()
    return {"sqmi": f"{built['sqmi']:.2f}", "steps": len(steps), "changed": sum("unchanged" not in change(s) for s in steps),
            "places": stats["big"], "acres": f"{math.floor(same['revision_only_acres'] + same['map_explorer_only_acres'] + 0.5):,}",
            "corrections": [s["step"] for s in steps if "text correction" in change(s)], "source": f"the build ({work})"}


FIG = figures()
QUADS = sum(1 for _ in csv.DictReader(open(ROOT / "resources" / "quads" / "quads-manifest.csv")))
# each indicator by the start of its top caption, and the number it shows (the desktop's has the big differences' distance)
PHONE_INDICATORS = {"AVA area": FIG["sqmi"], "Steps reworded": str(FIG["changed"]), "Big differences": str(FIG["places"])}
DESKTOP_INDICATORS = {"AVA as proposed": FIG["sqmi"], "Steps shown": str(FIG["steps"]), "Steps reworded": str(FIG["changed"]),
                      "Big differences": str(FIG["places"]), "Acres between the boundaries": FIG["acres"]}
PHONE_TABS = ["Steps", "What changes", "Grit", "Documents"]
LEFT_TABS = ["Documents", "The change near Grit", "What changes", "USGS quadrangles"]
RIGHT_TABS = ["Steps", "Big differences", "All differences"]

# ---------------------------------------------------------------- in the page (ArcGIS Dashboards is web components:
# most of it sits in shadow roots, which Playwright's CSS locators pierce and these scripts walk)
DEEP = "const deep = (root, sel, out = []) => { for (const el of root.querySelectorAll('*')) { if (el.matches(sel)) out.push(el); if (el.shadowRoot) deep(el.shadowRoot, sel, out); } return out; };"
INDICATORS = "() => {" + DEEP + """
  const box = (b) => ({x: b.left, y: b.top, r: b.right, b: b.bottom, w: b.width, h: b.height});
  return deep(document, 'dashboards-indicator-widget').map((w) => {
    const items = {};
    for (const it of deep(w.shadowRoot || w, 'dashboards-indicator-item')) {
      const t = it.shadowRoot && it.shadowRoot.querySelector('#text');
      if (!t || !t.textContent.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(t);
      const lines = [...range.getClientRects()].filter((q) => q.width > 0 && q.height > 0);
      const n = new Set(lines.map((q) => Math.round(q.top))).size;
      // the text's em boxes: its line boxes (Dashboards scales the text to fit) less the half-leading above and below
      const cs = getComputedStyle(t), lh = parseFloat(cs.lineHeight), fs = parseFloat(cs.fontSize);
      const lead = lh > fs ? (lh - fs) / 2 / lh : 0;
      let ink = null;
      if (lines.length) {
        const y = Math.min(...lines.map((q) => q.top)), b = Math.max(...lines.map((q) => q.bottom)), cut = (b - y) / n * lead;
        ink = {x: Math.min(...lines.map((q) => q.left)), r: Math.max(...lines.map((q) => q.right)), y: y + cut, b: b - cut};
      }
      items[it.getAttribute('slot')] = {text: t.textContent.trim(), sw: t.scrollWidth, cw: t.clientWidth, lines: n, ink};
    }
    return {ready: w.hasAttribute('ready'), box: box(w.getBoundingClientRect()), items};
  });
}"""
DEEP_TEXT = """(el) => { let s = ''; const walk = (n) => { if (n.nodeType === 3) s += n.textContent; if (n.shadowRoot) walk(n.shadowRoot);
  for (const c of n.childNodes) walk(c); }; walk(el); return s.replace(/\\s+/g, ' ').trim(); }"""
# the Steps list (Tabulator) draws only the rows near its scroll position: scroll it through, noting each row's position
# (data-row-index) and the step number its text starts with
LIST_ROWS = """async (holder) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const text = (row) => { let s = ''; for (const d of row.querySelectorAll('*')) if (d.shadowRoot) s += d.shadowRoot.textContent; return (s || row.textContent).trim(); };
  const rows = new Set(), steps = new Set();
  const note = () => { for (const row of holder.querySelectorAll('.tabulator-row')) {
    rows.add(+row.getAttribute('data-row-index')); const m = text(row).match(/^\\((\\d+)\\)/); if (m) steps.add(+m[1]); } };
  holder.scrollTop = 0; await sleep(500);
  for (let i = 0; i < 1000; i++) {
    note();
    if (holder.scrollTop + holder.clientHeight >= holder.scrollHeight - 1) { await sleep(1000); note(); break; }
    holder.scrollTop += 150; await sleep(150);
  }
  holder.scrollTop = 0; await sleep(300);
  return {rows: [...rows].sort((a, b) => a - b), steps: [...steps].sort((a, b) => a - b)};
}"""
MAP_STATE = "(m) => ({ready: !!m.ready, scale: m.scale || null, extent: m.extent && m.extent.toJSON ? m.extent.toJSON() : null})"


def caption_problems(view, expected):
    """each indicator found by its top caption: its number, and every caption inside the indicator's box, not cut at the
    side, and not printed over its neighbour (#45). (numbers, problems)"""
    numbers, problems = {}, []
    for ind in view.page.evaluate(INDICATORS):
        slots = {s: ind["items"][s] for s in ("top", "middle", "bottom") if s in ind["items"]}
        top = slots.get("top", {}).get("text", "?")
        name = next((k for k in expected if top.startswith(k)), top)
        numbers[name] = slots.get("middle", {}).get("text")
        b, prev = ind["box"], None
        for s, it in slots.items():
            ink, what = it["ink"], f'"{name}" {s} "{it["text"]}"'
            if ink is None:
                problems.append(f"{what} is not drawn")
                continue
            if it["sw"] > it["cw"] + 1:
                problems.append(f"{what} is cut at the side ({it['sw']} px of text in {it['cw']} px)")
            if ink["x"] < b["x"] - 2 or ink["r"] > b["r"] + 2:
                problems.append(f"{what} runs past the side of its box (text x {ink['x']:.0f}-{ink['r']:.0f}, box {b['x']:.0f}-{b['r']:.0f})")
            if ink["y"] < b["y"] - SLACK or ink["b"] > b["b"] + SLACK:
                problems.append(f"{what} ({it['lines']} line{'s' * (it['lines'] > 1)}) is cut off by its box (text y {ink['y']:.0f}-{ink['b']:.0f}, "
                                f"box {b['y']:.0f}-{b['b']:.0f})")
            if prev and prev[1]["b"] - ink["y"] > SLACK:
                problems.append(f"{what} is printed over the {PART[prev[0]]} above it ({prev[1]['b'] - ink['y']:.0f} px overlap)")
            prev = (s, ink)
    return numbers, problems


PART = {"top": "caption", "middle": "number", "bottom": "caption"}


def check_numbers(view, expected):
    numbers, _ = caption_problems(view, expected)
    assert sorted(numbers) == sorted(expected), f"{view.name}: indicators {sorted(numbers)}, expected {sorted(expected)}"
    wrong = {k: (numbers[k], v) for k, v in expected.items() if numbers[k] != v}
    assert not wrong, f"{view.name}: indicator numbers (shown, expected from {FIG['source']}): {wrong}"


def check_captions(view, expected):
    _, problems = caption_problems(view, expected)
    assert not problems, f"{view.name}: indicator text clipped or overprinted:\n  " + "\n  ".join(problems)


def tabs(view, title):
    """the tab strip (dashboards-tabs-element) that has a tab of this title"""
    page = view.page
    strip = page.locator("dashboards-tabs-element").filter(has=page.locator("calcite-tab-title", has_text=exactly(title)))
    assert strip.count() == 1, f"{view.name}: {strip.count()} tab strips with a tab '{title}'"
    return strip


def exactly(text):
    return re.compile(rf"^\s*{re.escape(text)}\s*$")


def titles(strip):
    return [t.strip() for t in strip.locator("calcite-tab-title").all_inner_texts()]


def open_tab(view, strip, title):
    """select a tab (tap on a phone, click elsewhere; Playwright scrolls a title hidden behind the strip's arrows into
    view) and return its content's widget once it is ready, visible and holds something"""
    t = strip.locator("calcite-tab-title", has_text=exactly(title))
    view.wait(lambda: (t.tap() if view.phone else t.click()), timeout=20)
    view.wait(lambda: _assert(t.get_attribute("aria-selected") == "true", f"{view.name}: tab '{title}' not selected"))
    widget = strip.locator("calcite-tab[selected] .widget")

    def shown():
        assert widget.count() == 1, f"{view.name}: tab '{title}' shows {widget.count()} widgets"
        assert widget.get_attribute("ready") is not None, f"{view.name}: tab '{title}' not ready"
        box = widget.bounding_box()
        assert box and box["width"] > 100 and box["height"] > 40, f"{view.name}: tab '{title}' content is not visible ({box})"
        size = view.page.viewport_size
        assert box["y"] < size["height"] and box["x"] < size["width"], f"{view.name}: tab '{title}' content is off the screen ({box})"
        if widget.evaluate("w => w.tagName.toLowerCase()") == "dashboards-list-widget":
            assert widget.locator(".tabulator-row").count() > 0, f"{view.name}: tab '{title}' lists nothing"
        else:
            assert len(widget.evaluate(DEEP_TEXT)) > 40, f"{view.name}: tab '{title}' holds no text"
    view.wait(shown)
    return widget


def _assert(ok, message):
    assert ok, message


def no_sideways_scroll(view):
    s = view.page.evaluate("() => { scrollTo(300, 0); const s = {width: document.scrollingElement.scrollWidth, inner: innerWidth, x: scrollX}; scrollTo(0, 0); return s; }")
    assert s["width"] <= s["inner"] and s["x"] == 0, f"{view.name}: the page scrolls sideways ({s['width']} px wide in a {s['inner']} px window)"


# ---------------------------------------------------------------- phones
@pytest.fixture(scope="module", params=list(PHONES))
def phone(request, chrome, open_dashboard):
    device, w, h = PHONES[request.param]
    p, _ = chrome
    context = {k: v for k, v in p.devices[device].items() if k != "default_browser_type"}   # user agent, touch, mobile, ratio
    context.update(viewport={"width": w, "height": h}, screen={"width": w, "height": h})    # the whole screen, as #68 asks
    view = open_dashboard(f"phone-{request.param}", True, **context)
    yield view
    view.close()


def phone_layout(view):
    if view.page.locator("dashboards-mobile-layout").count() != 1:
        pytest.fail(f"{view.name}: the phone layout is not shown (see test_phone_layout_is_shown)", pytrace=False)


def test_phone_layout_is_shown(phone):
    """ArcGIS Dashboards picks the phone layout (mobileView) for a phone's user agent and touch screen, not by width"""
    page = phone.page
    count = {sel: page.locator(sel).count() for sel in ("dashboards-mobile-layout", "dashboards-mobile-header-panel", "calcite-fab",
                                                         "dashboards-desktop-layout", "dashboards-header-panel", "dashboards-details-widget")}
    assert count["dashboards-desktop-layout"] == 0 and count["dashboards-mobile-layout"] == 1, \
        f"{phone.name}: the desktop layout is shown on a phone, not the phone layout: {count}"
    assert page.locator("dashboards-mobile-layout").is_visible(), f"{phone.name}: the phone layout is not visible"
    assert count["dashboards-mobile-header-panel"] == 1 and count["calcite-fab"] == 1, \
        f"{phone.name}: the phone layout lacks its header or its Filter button: {count}"
    assert count["dashboards-details-widget"] == 0 and count["dashboards-header-panel"] == 0, \
        f"{phone.name}: desktop panels (the selected step's details, the desktop header) on the phone: {count}"
    assert page.locator("dashboards-indicator-widget").count() == len(PHONE_INDICATORS), \
        f"{phone.name}: {page.locator('dashboards-indicator-widget').count()} indicators, the phone layout has {len(PHONE_INDICATORS)}"


def test_phone_header(phone):
    phone_layout(phone)
    title = phone.page.locator("dashboards-mobile-header-panel .title")
    subtitle = phone.page.locator("dashboards-mobile-header-panel .subtitle")
    assert title.is_visible() and subtitle.is_visible(), f"{phone.name}: the header's title or subtitle is not visible"
    assert "Hickory Sands District AVA" in title.inner_text(), f"{phone.name}: header title {title.inner_text()!r}"
    assert "Notice No. 243" in subtitle.inner_text(), f"{phone.name}: header subtitle {subtitle.inner_text()!r}"
    cut = [f"{el.inner_text()!r} ({w} px of text in {c} px)" for el in (title, subtitle)
           for w, c in [el.evaluate("e => [e.scrollWidth, e.clientWidth]")] if w > c + 1]
    if cut:   # Esri's phone header is one line and ends a long title with an ellipsis: a note, not a failure
        warnings.warn(f"{phone.name}: the phone header cuts its text short with an ellipsis: {'; '.join(cut)}", stacklevel=1)


def test_phone_indicator_numbers(phone):
    phone_layout(phone)
    check_numbers(phone, PHONE_INDICATORS)


def test_phone_indicator_captions_fit(phone):
    phone_layout(phone)
    check_captions(phone, PHONE_INDICATORS)


def test_phone_map_is_drawn(phone):
    phone_layout(phone)
    m = phone.page.locator("dashboards-map-widget arcgis-map")
    state = phone.wait(lambda: _ready(phone, m), timeout=60)
    canvas = phone.page.locator("dashboards-map-widget arcgis-map canvas").first
    box = canvas.bounding_box()
    assert box and box["width"] > 200 and box["height"] > 150, f"{phone.name}: the map's canvas is {box}"
    assert box["y"] < phone.page.viewport_size["height"], f"{phone.name}: the map is below the screen ({box})"
    assert state["extent"], f"{phone.name}: the map has no extent"


def _ready(view, m):
    assert m.count() == 1, f"{view.name}: {m.count()} maps"
    state = m.evaluate(MAP_STATE)
    assert state["ready"] and state["scale"], f"{view.name}: the map is not ready: {state}"
    return state


def test_phone_tabs(phone):
    phone_layout(phone)
    strip = tabs(phone, "Steps")
    assert titles(strip) == PHONE_TABS, f"{phone.name}: phone tabs {titles(strip)}, expected {PHONE_TABS}"
    for title in PHONE_TABS[1:] + PHONE_TABS[:1]:   # end on Steps
        open_tab(phone, strip, title)


def test_phone_steps_list_has_every_step(phone):
    phone_layout(phone)
    widget = open_tab(phone, tabs(phone, "Steps"), "Steps")
    got = widget.locator(".tabulator-tableholder").evaluate(LIST_ROWS)
    n = FIG["steps"]
    assert got["rows"] == list(range(1, n + 1)), f"{phone.name}: the Steps list holds rows {got['rows'][:3]}...{got['rows'][-3:]} ({len(got['rows'])}), expected 1-{n}"
    assert set(got["steps"]) <= set(range(1, n + 1)) and n in got["steps"], f"{phone.name}: step numbers read in the list: {got['steps']}"


def test_phone_tapping_a_step_moves_the_map(phone):
    phone_layout(phone)
    widget = open_tab(phone, tabs(phone, "Steps"), "Steps")
    m = phone.page.locator("dashboards-map-widget arcgis-map")
    before = phone.wait(lambda: _ready(phone, m), timeout=60)
    row = widget.locator('.tabulator-row[data-row-index="2"]')
    phone.wait(lambda: row.tap(), timeout=20)

    def moved():
        now = m.evaluate(MAP_STATE)
        assert now["scale"] and now["scale"] < before["scale"] / 2, \
            f"{phone.name}: tapping step (2) in the Steps list did not zoom the map (scale 1:{before['scale']:,.0f}, now 1:{(now['scale'] or 0):,.0f})"
    phone.wait(moved, timeout=20)


def test_phone_documents_link_to_the_group(phone, site):
    phone_layout(phone)
    widget = open_tab(phone, tabs(phone, "Documents"), "Documents")
    links = widget.locator("a").evaluate_all("els => els.map(a => [a.href, a.innerText.replace(/\\s+/g, ' ').trim()])")
    bad, items = [], 0
    for href, text in links:
        m = ITEM_LINK.search(href)
        if m and m[1] in site.items:
            items += 1
            if not holds(site.items[m[1]]["title"], text):
                bad.append(f"'{text}' opens '{site.items[m[1]]['title']}'")
        elif m:
            bad.append(f"'{text}' opens item {m[1]}, which is not in the group")
        elif f"group.html?id={site.group}" not in href:
            bad.append(f"'{text}' goes to {href}, not an item in the group")
    assert items >= 4 and not bad, f"{phone.name}: Documents tab: {items} links to items in the group; {bad}"


def test_phone_no_sideways_scroll(phone):
    phone_layout(phone)
    no_sideways_scroll(phone)


def test_phone_drawer_corrections(phone):
    """last of the phone's tests: it leaves the steps filtered"""
    phone_layout(phone)
    page = phone.page
    sheet = page.locator("calcite-sheet[aria-label=Filter]")
    phone.wait(lambda: page.locator("calcite-fab").tap(), timeout=20)
    phone.wait(lambda: _assert(sheet.evaluate("s => s.open"), f"{phone.name}: the Filter button does not open the drawer"))
    trigger = page.locator("dashboards-drawer-panel dashboards-selector-trigger")
    assert trigger.count() == 1, f"{phone.name}: {trigger.count()} step selectors in the drawer"
    all_steps = f"All {FIG['steps']} steps"
    assert all_steps in trigger.evaluate(DEEP_TEXT), f"{phone.name}: the drawer's selector reads {trigger.evaluate(DEEP_TEXT)!r}"
    phone.wait(lambda: trigger.tap(), timeout=20)
    choice = page.locator("dashboards-drawer-panel calcite-list-item").filter(has_text="Corrections to Notice No. 243's wording")
    phone.wait(lambda: _assert(choice.count() == 1 and choice.is_visible(), f"{phone.name}: no 'Corrections' choice in the drawer"), timeout=20)
    choice.tap()
    # Done on the choices goes back to the drawer's first page (which now names the choice); Done there closes the drawer
    done = page.locator("dashboards-drawer-panel calcite-button", has_text="Done").filter(visible=True)

    def close():
        if sheet.evaluate("s => s.open"):
            done.tap()
            page.wait_for_timeout(1000)
        assert not sheet.evaluate("s => s.open"), f"{phone.name}: the drawer stays open after Done"
    phone.wait(close, timeout=20)
    holder = open_tab(phone, tabs(phone, "Steps"), "Steps").locator(".tabulator-tableholder")
    want = FIG["corrections"]

    def filtered():
        got = holder.evaluate(LIST_ROWS)
        assert got["steps"] == want and len(got["rows"]) == len(want), \
            f"{phone.name}: with 'Corrections to Notice No. 243's wording' the Steps list shows steps {got['steps']} ({len(got['rows'])} rows), expected {want}"
    phone.wait(filtered, timeout=30)
    numbers, _ = caption_problems(phone, PHONE_INDICATORS)
    assert numbers.get("Steps reworded") == str(len(want)), f"{phone.name}: 'Steps reworded' shows {numbers.get('Steps reworded')} with the corrections only"


# ---------------------------------------------------------------- laptops and desktops
@pytest.fixture(scope="module", params=SCREENS)
def desktop(request, open_dashboard):
    w, h = map(int, request.param.split("x"))
    view = open_dashboard(f"desktop-{request.param}", False, viewport={"width": w, "height": h})
    yield view
    view.close()


def desktop_layout(view):
    if view.page.locator("dashboards-desktop-layout").count() != 1:
        pytest.fail(f"{view.name}: the desktop layout is not shown (see test_desktop_layout_is_shown)", pytrace=False)


def test_desktop_layout_is_shown(desktop):
    page = desktop.page
    count = {sel: page.locator(sel).count() for sel in ("dashboards-desktop-layout", "dashboards-mobile-layout", "dashboards-details-widget",
                                                         "dashboards-header-panel dashboards-selector", "dashboards-indicator-widget")}
    assert count["dashboards-desktop-layout"] == 1 and count["dashboards-mobile-layout"] == 0, \
        f"{desktop.name}: the desktop layout is not shown: {count}"
    assert count["dashboards-details-widget"] == 1 and count["dashboards-header-panel dashboards-selector"] == 1, \
        f"{desktop.name}: the desktop layout lacks the selected step's details or the header's step selector: {count}"
    assert count["dashboards-indicator-widget"] == len(DESKTOP_INDICATORS), f"{desktop.name}: indicators: {count}"


def test_desktop_indicator_numbers(desktop):
    desktop_layout(desktop)
    check_numbers(desktop, DESKTOP_INDICATORS)


def test_desktop_indicator_captions_fit(desktop):
    desktop_layout(desktop)
    check_captions(desktop, DESKTOP_INDICATORS)


def test_desktop_left_tabs(desktop):
    desktop_layout(desktop)
    strip = tabs(desktop, "Documents")
    assert titles(strip) == LEFT_TABS, f"{desktop.name}: left tabs {titles(strip)}, expected {LEFT_TABS}"
    for title in LEFT_TABS[1:] + LEFT_TABS[:1]:   # end on Documents
        open_tab(desktop, strip, title)


def test_desktop_quad_links_on_one_line(desktop):
    """#47: never "GeoPD / F" """
    desktop_layout(desktop)
    widget = open_tab(desktop, tabs(desktop, "USGS quadrangles"), "USGS quadrangles")
    links = widget.locator("a").evaluate_all("els => els.map(a => [a.textContent.trim(), a.getClientRects().length])")
    files = [(t, n) for t, n in links if t in ("GeoPDF", "GeoTIFF")]
    assert len(files) == 2 * QUADS, f"{desktop.name}: {len(files)} GeoPDF/GeoTIFF links in the USGS quadrangles tab, expected {2 * QUADS}"
    broken = [f"{t} ({n} pieces)" for t, n in files if n != 1]
    assert not broken, f"{desktop.name}: GeoPDF/GeoTIFF links broken across lines: {broken}"


def test_desktop_right_tabs(desktop):
    desktop_layout(desktop)
    strip = tabs(desktop, "Big differences")
    assert titles(strip) == RIGHT_TABS, f"{desktop.name}: right tabs {titles(strip)}, expected {RIGHT_TABS}"
    for title in RIGHT_TABS[1:] + RIGHT_TABS[:1]:   # end on Steps
        open_tab(desktop, strip, title)


def test_desktop_no_sideways_scroll(desktop):
    desktop_layout(desktop)
    no_sideways_scroll(desktop)
