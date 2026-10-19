"""Add your vineyard (docs/vineyards.html), driven in Google Chrome.

Marked live. This checkout's docs/ is served on 127.0.0.1:8765 (HSD_WIZARD_PORT)
and opened as http://localhost:8765, the one local address the basemap key
answers, so the real map is drawn. The form sends to the real function, the
one-file bundle Dan deploys, served by tests/vineyard_standin.mjs with
stand-ins for Supabase's table, Turnstile's check and GitHub; the page's
config is pointed at it, with Cloudflare's always-passing test site key.

- At 390x844 and 360x780 (touch only) and 1440x900 (the mouse): find the
  vineyard by the phone's location, tap four corners, undo one and tap it
  again, drag a corner, finish the block, add a second block of three
  corners, see an error and fix it, fill in the rest, wait for the person
  check, send; the thank-you screen gives the issue's number, the stand-in
  holds one row with the contact and one issue without it, and the draft is
  forgotten. No console error.
- At 360x780: a pin instead of blocks (the acres then needed), and the
  function unreachable: the failure screen, its email link and copying.
- At 390x844: GitHub failing (the function answers 502): the failure screen.
- At 390x844: the config empty (the function not set up yet): no person
  check, and Send offers the email.

    .venv/bin/python -m pytest -v -m live tests/live/test_vineyard_wizard.py

Screenshots: target/browser-tests/vineyard/<viewport>-<step>.png. Port 8765
must be free: stop whatever serves there for the run.
"""

import contextlib
import functools
import http.server
import json
import os
import shutil
import socket
import subprocess
import threading
import urllib.request

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="playwright is in requirements-dev.txt: run ./build.sh env",
)
# pytest loads tests/live/conftest.py as the module conftest (tests/ is not a
# package), so it is imported by that name, as test_site_mobile.py does.
from conftest import ROOT
from conftest import SHOTS

from src.vineyards import bundle_function

pytestmark = pytest.mark.live
PORT = int(os.environ.get("HSD_WIZARD_PORT", "8765"))
SITE = f"http://localhost:{PORT}"
SHOT_DIR = SHOTS / "vineyard"
NODE = shutil.which("node")
TEST_SITE_KEY = (
    "1x00000000000000000000AA"  # Cloudflare's test key: always passes
)
# an open field inside the proposed district, east of Mason
FIELD = (30.8640, -99.2940)
VIEWPORTS = {
    "phone-390x844": (390, 844, True),
    "phone-360x780": (360, 780, True),
    "desktop-1440x900": (1440, 900, False),
}
BLOCK_1 = [(0.15, 0.25), (0.45, 0.25), (0.45, 0.70), (0.15, 0.70)]
BLOCK_2 = [(0.55, 0.32), (0.78, 0.32), (0.66, 0.66)]


class Quiet(http.server.SimpleHTTPRequestHandler):
    """docs/, as GitHub Pages serves it, without the log or a cache."""

    def end_headers(self):
        """Every answer uncached, so each run reads this checkout's files."""
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        """Keeps the test's output quiet."""


@pytest.fixture(scope="module")
def served():
    try:
        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", PORT),
            functools.partial(Quiet, directory=str(ROOT / "docs")),
        )
    except OSError:
        pytest.skip(f"port {PORT} is in use: stop the server holding it")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield SITE
    server.shutdown()
    server.server_close()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def standin(tmp_path_factory):
    if not NODE:
        pytest.skip("node is not installed")
    bundle = tmp_path_factory.mktemp("function") / "index.mts"
    bundle.write_text(bundle_function.bundle(), encoding="utf-8")
    port = free_port()
    server = subprocess.Popen(
        [
            NODE,
            "--experimental-strip-types",
            str(ROOT / "tests" / "vineyard_standin.mjs"),
            "serve",
            str(port),
            str(bundle),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert "stand-in on" in server.stdout.readline()
    yield f"http://127.0.0.1:{port}"
    server.terminate()
    server.wait(timeout=10)


def control(standin, **state):
    """Sets the stand-ins (a fresh one with reset=True); answers their data."""
    body = json.dumps(
        {"reset": state.pop("reset", False), "state": state}
    ).encode()
    req = urllib.request.Request(f"{standin}/standin", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


class Grower:
    """One grower's phone (or desktop) on the page."""

    def __init__(self, browser, viewport, site, endpoint, key=TEST_SITE_KEY):
        """Opens the page at a viewport, the config pointed at endpoint."""
        width, height, touch = VIEWPORTS[viewport]
        self.name = viewport
        self.touch = touch
        self.context = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=2,
            is_mobile=touch,
            has_touch=touch,
            locale="en-US",
            geolocation={
                "latitude": FIELD[0],
                "longitude": FIELD[1],
                "accuracy": 8,
            },
            permissions=["geolocation", "clipboard-read", "clipboard-write"],
        )
        config = (
            f'export const endpoint = "{endpoint}";\n'
            f'export const turnstileSiteKey = "{key}";\n'
        )
        self.context.route(
            "**/assets/vineyard-config.js",
            lambda route: route.fulfill(
                status=200, content_type="text/javascript", body=config
            ),
        )
        self.page = self.context.new_page()
        self.errors = []
        self.page.on(
            "console",
            lambda m: self.errors.append(m.text) if m.type == "error" else None,
        )
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.set_default_timeout(60_000)
        self.page.goto(f"{site}/vineyards.html", wait_until="load")

    def shot(self, label):
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        self.page.wait_for_timeout(300)
        self.page.screenshot(path=str(SHOT_DIR / f"{self.name}-{label}.png"))

    def press(self, selector):
        loc = self.page.locator(selector)
        loc.scroll_into_view_if_needed()
        if self.touch:
            loc.tap()
        else:
            loc.click()

    def map_at(self, fx, fy):
        box = self.page.locator("#wiz-map").bounding_box()
        return box["x"] + fx * box["width"], box["y"] + fy * box["height"]

    def map_tap(self, fx, fy):
        x, y = self.map_at(fx, fy)
        if self.touch:
            self.page.touchscreen.tap(x, y)
        else:
            self.page.mouse.click(x, y)
        self.page.wait_for_timeout(500)

    def drag(self, x, y, dx, dy):
        if self.touch:
            cdp = self.context.new_cdp_session(self.page)
            cdp.send(
                "Input.dispatchTouchEvent",
                {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]},
            )
            for k in range(1, 9):
                cdp.send(
                    "Input.dispatchTouchEvent",
                    {
                        "type": "touchMove",
                        "touchPoints": [
                            {"x": x + dx * k / 8, "y": y + dy * k / 8}
                        ],
                    },
                )
                self.page.wait_for_timeout(30)
            cdp.send(
                "Input.dispatchTouchEvent",
                {"type": "touchEnd", "touchPoints": []},
            )
        else:
            self.page.mouse.move(x, y)
            self.page.mouse.down()
            for k in range(1, 9):
                self.page.mouse.move(x + dx * k / 8, y + dy * k / 8)
                self.page.wait_for_timeout(30)
            self.page.mouse.up()
        self.page.wait_for_timeout(600)

    def type_in(self, selector, text):
        self.press(selector)
        self.page.keyboard.type(text, delay=5)

    def text(self, selector):
        return self.page.locator(selector).text_content()

    def shown(self, selector):
        return self.page.locator(selector).is_visible()

    def open_and_locate(self):
        self.press("#start")
        self.page.wait_for_function(
            "document.getElementById('map-loading').hidden", timeout=90_000
        )
        self.page.wait_for_timeout(1500)
        self.press("#locate")
        self.page.wait_for_function(
            "document.getElementById('locate-status').textContent"
            ".startsWith('Found you')"
        )
        self.page.wait_for_timeout(3000)  # the map moves to the vines
        self.shot("1-located")
        self.press("#next")
        self.at_step(2)
        self.page.wait_for_timeout(1500)

    def at_step(self, n):
        self.page.wait_for_function(
            "document.getElementById('wiz-count').textContent"
            f" === 'Step {n} of 5'"
        )

    def contact_and_send(self):
        self.at_step(4)
        self.type_in("#w-cname", "Jane Grower")
        self.type_in("#w-phone", "325 555 0100")
        self.shot("4-contact")
        self.press("#next")

    def close(self):
        self.context.close()


@pytest.fixture
def grower(chrome, served, standin, request):
    _, browser = chrome
    opened = []

    def make(viewport, **kw):
        g = Grower(
            browser, viewport, served, f"{standin}/vineyard-submit", **kw
        )
        opened.append(g)
        return g

    yield make
    for g in opened:
        with contextlib.suppress(Exception):
            g.close()


@pytest.mark.parametrize("viewport", list(VIEWPORTS))
def test_draw_two_blocks_send_and_thanks(grower, standin, viewport):
    control(standin, reset=True)
    g = grower(viewport)
    g.open_and_locate()
    corners = []
    for fx, fy in BLOCK_1:
        g.map_tap(fx, fy)
        corners.append(g.map_at(fx, fy))
    assert g.text("#draw-live").startswith("Block 1: 4 corners")
    g.press("#undo")
    assert g.text("#draw-live").startswith("Block 1: 3 corners")
    g.map_tap(*BLOCK_1[3])
    g.shot("2-four-corners")
    g.drag(*corners[2], 12, 8)  # the third corner, to fit the rows
    assert g.text("#draw-live").startswith("Block 1: 4 corners")
    g.press("#done-block")
    assert "Block 1 · about" in g.text("#block-list")
    g.press("#add-block")
    for fx, fy in BLOCK_2:
        g.map_tap(fx, fy)
    g.press("#done-block")
    g.shot("2-two-blocks")
    assert g.page.locator("#block-list li").count() == 2
    g.press("#next")
    # step 3: Next before the name shows the name's error, beside it
    g.at_step(3)
    assert g.page.locator("#w-county").input_value() == "Mason"
    assert g.text("#acres-hint").startswith("Your drawing is about")
    g.press("#next")
    assert g.shown("#err-name")
    assert g.text("#err-name") == "Type the vineyard's name."
    g.shot("3-error")
    g.type_in("#w-name", "Prairie Gap Vineyard")
    g.press('input[name="planted"][value="planted"]')
    g.type_in("#w-acres", "4,5")  # read as 4.5
    g.page.locator("#w-year").select_option("2016")
    g.press('.chip[data-variety="Tempranillo"]')
    g.press('.chip[data-variety="Mourvèdre"]')
    g.press("#next")
    g.contact_and_send()
    g.at_step(5)
    g.page.wait_for_function(
        "document.getElementById('human-note').textContent.startsWith('Checked')"
    )
    g.press("#w-agree-permission")
    g.press("#w-agree-public")
    g.shot("5-check")
    g.press("#next")
    g.page.wait_for_function(
        "!document.querySelector('section[data-step=done]').hidden",
        timeout=60_000,
    )
    g.shot("6-thanks")
    data = control(standin)
    (issue,) = data["issues"]
    (row,) = data["rows"]
    assert g.text("#ref") == str(issue["number"])
    assert "We'll review it within about a week." in g.text(
        "section[data-step=done]"
    )
    assert row["issue_number"] == issue["number"]
    assert row["contact_name"] == "Jane Grower"
    assert row["phone"] == "(325) 555-0100"
    assert "Jane" not in issue["body"]
    assert "555" not in issue["body"].split("```json")[0]
    assert "2 blocks drawn" in issue["body"]
    assert '"acres":4.5' in issue["body"]
    assert issue["title"] == "Vineyard submission, Mason County"
    draft = g.page.evaluate("localStorage.getItem('hsd-vineyard-draft-v1')")
    assert draft is None
    assert g.errors == [], g.errors


def test_a_pin_then_the_email_when_the_function_is_unreachable(grower, standin):
    control(standin, reset=True)
    g = grower("phone-360x780")
    g.open_and_locate()
    g.press("#to-pin")
    g.map_tap(0.5, 0.5)
    g.shot("2-pin")
    g.press("#next")
    g.at_step(3)
    g.type_in("#w-name", "Prairie Gap Vineyard")
    g.press('input[name="planted"][value="planned"]')
    g.press("#next")
    assert g.shown("#err-acres")  # a pin needs the acres
    g.type_in("#w-acres", "6")
    g.press("#next")
    g.contact_and_send()
    g.at_step(5)
    g.page.wait_for_function(
        "document.getElementById('human-note').textContent.startsWith('Checked')"
    )
    g.press("#w-agree-permission")
    g.press("#w-agree-public")
    control(standin, github="unreachable")
    g.press("#next")
    g.page.wait_for_function(
        "!document.querySelector('section[data-step=failed]').hidden",
        timeout=60_000,
    )
    g.shot("6-failed")
    assert g.text("#fail-say") == "It didn't go through just now."
    href = g.page.locator("#mail").get_attribute("href")
    assert href.startswith(
        "mailto:district@hickorysandsdistrictava.org?subject="
    )
    assert "Prairie%20Gap%20Vineyard" in href
    assert "Your email app opens" in g.text("#mail-note")
    g.press("#copy")
    g.page.wait_for_function(
        "document.getElementById('copy-status').textContent !== ''"
    )
    status = g.text("#copy-status")
    assert status.startswith(("Copied.", "Your browser would not copy them."))
    assert control(standin)["rows"] == []
    g.press("#retry")
    g.at_step(5)
    # the failure was logged, and nothing else went wrong
    assert all(
        "could not be sent" in e or "Failed to fetch" in e or "ERR_" in e
        for e in g.errors
    ), g.errors


def test_github_failing_offers_the_email(grower, standin):
    control(standin, reset=True)
    control(standin, github="issue-fails")
    g = grower("phone-390x844")
    g.open_and_locate()
    for fx, fy in BLOCK_1:
        g.map_tap(fx, fy)
    g.press("#done-block")
    g.press("#next")
    g.at_step(3)
    g.type_in("#w-name", "Prairie Gap Vineyard")
    g.press('input[name="planted"][value="planted"]')
    g.press("#next")
    g.contact_and_send()
    g.at_step(5)
    g.page.wait_for_function(
        "document.getElementById('human-note').textContent.startsWith('Checked')"
    )
    g.press("#w-agree-permission")
    g.press("#w-agree-public")
    g.press("#next")
    g.page.wait_for_function(
        "!document.querySelector('section[data-step=failed]').hidden",
        timeout=60_000,
    )
    g.shot("6-github-failed")
    assert g.text("#fail-say") == "It didn't go through just now."
    data = control(standin)
    assert data["rows"] == []  # the row was freed for a retry
    assert data["issues"] == []


def test_not_set_up_yet_the_form_ends_at_the_email(grower, standin):
    g = grower("phone-390x844", key="")
    g.open_and_locate()
    for fx, fy in BLOCK_1:
        g.map_tap(fx, fy)
    g.press("#done-block")
    g.press("#next")
    g.at_step(3)
    g.type_in("#w-name", "Prairie Gap Vineyard")
    g.press('input[name="planted"][value="planted"]')
    g.press("#next")
    g.contact_and_send()
    g.at_step(5)
    assert not g.shown("#human")  # no person check that could never pass
    g.press("#w-agree-permission")
    g.press("#w-agree-public")
    g.press("#next")
    g.page.wait_for_function(
        "!document.querySelector('section[data-step=failed]').hidden"
    )
    g.shot("6-not-set-up")
    assert g.text("#fail-say") == "Sending from this page isn't open yet."
    assert not g.shown("#retry")  # trying again cannot help: only the email
    assert (
        g.page.locator("#mail")
        .get_attribute("href")
        .startswith("mailto:district@hickorysandsdistrictava.org")
    )
    assert g.errors == [], g.errors
