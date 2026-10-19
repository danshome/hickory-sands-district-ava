"""Add your vineyard (docs/vineyards.html), driven in Google Chrome.

Marked live. This checkout's docs/ is served on 127.0.0.1:8765 (HSD_WIZARD_PORT)
and opened as http://localhost:8765, the one local address the basemap key
answers, so the real map is drawn. The form sends to the real function, the
one-file bundle Dan deploys, served by tests/vineyard_standin.mjs with
stand-ins for Supabase's table, Turnstile's check and GitHub; the page's
config is pointed at it, with Cloudflare's always-passing test site key.

- At 390x844 and 360x780 (touch only), and at 1440x900 by the mouse and by
  touch (a touch screen on a desktop): find the
  vineyard by the phone's location, tap four corners, undo one and tap it
  again, drag a corner, finish the block, add a second block of three
  corners, see an error and fix it, fill in the rest, wait for the person
  check, send; the thank-you screen gives the issue's number, the stand-in
  holds one row with the contact and one issue without it, and the draft is
  forgotten. No console error.
- At 360x780: a pin instead of blocks (the acres then needed), and the
  function unreachable: the failure screen, its email link and copying.
- At 390x844: GitHub failing (the function answers 502): the failure screen.
- At 390x844: the endpoint empty (the function not set up yet): no person
  check, and Send offers the email.
- At 390x844: the endpoint set and no site key, the function without
  TURNSTILE_SECRET (no Cloudflare for now, Dan 2026-10-19): no person check
  shown or loaded, and Send sends: the thank-you screen, one row, one issue.

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
VIEWPORTS = {  # name: (width, height, touch, a phone)
    "phone-390x844": (390, 844, True, True),
    "phone-360x780": (360, 780, True, True),
    "desktop-1440x900": (1440, 900, False, False),
    "desktop-1440x900-touch": (1440, 900, True, False),
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
    """Sets the stand-ins (a fresh one with reset=True); answers their data.

    env={...} sets the function's secrets after any reset (a fresh stand-in
    has every one set).
    """
    body = json.dumps(
        {
            "reset": state.pop("reset", False),
            "env": state.pop("env", {}),
            "state": state,
        }
    ).encode()
    req = urllib.request.Request(f"{standin}/standin", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


class Grower:
    """One grower's phone (or desktop) on the page."""

    def __init__(self, browser, viewport, site, endpoint, key=TEST_SITE_KEY):
        """Opens the page at a viewport, the config pointed at endpoint."""
        width, height, touch, phone = VIEWPORTS[viewport]
        self.name = viewport
        self.touch = touch
        self.context = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=2,
            is_mobile=phone,
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

    def small_targets(self):
        """The visible tap targets in the form under 44 px either way."""
        return self.page.evaluate(SMALL)

    def ready_to_send(self):
        """Ticks both boxes and waits for the person check."""
        self.at_step(5)
        self.page.wait_for_function(
            "document.getElementById('human-note').textContent"
            ".startsWith('Checked')"
        )
        if not self.page.locator("#w-agree-permission").is_checked():
            self.press("#w-agree-permission")
        if not self.page.locator("#w-agree-public").is_checked():
            self.press("#w-agree-public")

    def to_step_five(self, name="Prairie Gap Vineyard"):
        """One block, a name, planted, the contact: at step 5."""
        self.open_and_locate()
        for fx, fy in BLOCK_1:
            self.map_tap(fx, fy)
        self.press("#done-block")
        self.press("#next")
        self.at_step(3)
        self.type_in("#w-name", name)
        self.press('input[name="planted"][value="planted"]')
        self.press("#next")
        self.contact_and_send()
        self.at_step(5)

    def failed(self):
        self.page.wait_for_function(
            "!document.querySelector('section[data-step=failed]').hidden",
            timeout=90_000,
        )

    def close(self):
        self.context.close()


# Every visible button, card, box and link-button in the form (#wiz), not
# links inside a sentence, nor the map's own controls: under 44 px either way.
SMALL = """() => {
  const out = [];
  const sel = "button, a.w-button, .chip, label.card, label.w-check, .w-link";
  for (const el of document.querySelectorAll(`#wiz ${sel}`)) {
    if (el.closest("arcgis-map, [hidden], .kbd-only")) continue;
    if (el.closest("p") && !el.matches(".w-link, button")) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    if (r.width < 43.5 || r.height < 43.5) {
      const name = el.id || el.className || el.tagName;
      out.push(`${name}: ${Math.round(r.width)}x${Math.round(r.height)}`);
    }
  }
  return out;
}"""


@pytest.fixture
def grower(chrome, served, standin, request):
    _, browser = chrome
    opened = []

    def make(viewport, endpoint=None, **kw):
        if endpoint is None:
            endpoint = f"{standin}/vineyard-submit"
        g = Grower(browser, viewport, served, endpoint, **kw)
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
    small = {}
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
    small["2"] = g.small_targets()
    g.press("#next")
    # step 3: Next before the name shows the name's error, beside it
    g.at_step(3)
    small["3"] = g.small_targets()
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
    small["5"] = g.small_targets()
    g.press("#next")
    g.page.wait_for_function(
        "!document.querySelector('section[data-step=done]').hidden",
        timeout=60_000,
    )
    g.shot("6-thanks")
    small["done"] = g.small_targets()
    assert all(not v for v in small.values()), small
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
    g = grower("phone-390x844", endpoint="", key="")
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


def test_no_person_check_the_form_still_sends(grower, standin):
    # No Cloudflare for now (Dan, 2026-10-19): no site key on the page and no
    # TURNSTILE_SECRET in the function. Nothing from Cloudflare is loaded,
    # the person check is not shown, and Send sends.
    control(standin, reset=True, env={"TURNSTILE_SECRET": ""})
    g = grower("phone-390x844", key="")
    cloudflare = []
    g.context.route(
        "https://challenges.cloudflare.com/**",
        lambda route: (cloudflare.append(route.request.url), route.abort()),
    )
    g.to_step_five()
    assert not g.shown("#human")
    g.press("#w-agree-permission")
    g.press("#w-agree-public")
    g.press("#next")
    g.page.wait_for_function(
        "!document.querySelector('section[data-step=done]').hidden",
        timeout=60_000,
    )
    g.shot("6-sent-no-check")
    data = control(standin)
    (issue,) = data["issues"]
    (row,) = data["rows"]
    assert g.text("#ref") == str(issue["number"])
    assert row["issue_number"] == issue["number"]
    assert cloudflare == []
    assert g.errors == [], g.errors


def test_refusals_the_page_can_get_past_then_the_email(grower, standin):
    # the function refuses the name (a private word: 422): step 3, the name's
    # box, the message; Turnstile refuses three times (403): said, then the
    # email; a send under way (409) three times: the same
    control(standin, reset=True)
    g = grower("phone-390x844")
    g.to_step_five(name="Quillfeather Vineyard")
    g.ready_to_send()
    g.press("#next")
    g.at_step(3)
    assert g.shown("#err-name")
    assert "can't show this name" in g.text("#err-name")
    g.page.locator("#w-name").fill("Prairie Gap Vineyard")
    g.press("#next")
    g.press("#next")
    for state, said in (
        ({"turnstile": "fail"}, "didn't go through"),
        ({"turnstile": "pass", "verdict": "again"}, "still being sent"),
    ):
        control(standin, **state)
        for _ in range(2):
            g.ready_to_send()
            g.press("#next")
            g.page.wait_for_function(
                "!document.getElementById('err-send').hidden"
            )
            assert said in g.text("#err-send")
        g.ready_to_send()
        g.press("#next")
        g.failed()
        assert g.text("#fail-say") == "It didn't go through just now."
        g.press("#retry")
    control(standin, verdict="limit-ip")
    g.ready_to_send()
    g.press("#next")
    g.failed()
    g.shot("6-limit")
    assert g.text("#fail-say") == (
        "Several vineyards have already been sent from this internet "
        "connection today."
    )
    assert control(standin)["issues"] == []


def test_turnstile_failing_then_the_email_and_try_again_loads_it(
    grower, standin
):
    # Cloudflare's script blocked: said, Send offers the email; Try again
    # loads it again once it can, and the vineyard goes
    control(standin, reset=True)
    g = grower("phone-360x780")
    blocked = []

    def block(route):
        blocked.append(route.request.url)
        route.abort()

    g.context.route("https://challenges.cloudflare.com/**", block)
    g.to_step_five()
    g.page.wait_for_function(
        "document.getElementById('human-note').textContent"
        ".includes('could not load')"
    )
    g.press("#w-agree-permission")
    g.press("#w-agree-public")
    g.press("#next")
    g.failed()
    assert (
        g.text("#fail-say") == "The check that you're a person isn't working."
    )
    assert g.page.locator("#mail").get_attribute("href").startswith("mailto:")
    assert blocked
    g.context.unroute("https://challenges.cloudflare.com/**")
    g.press("#retry")
    g.ready_to_send()
    g.press("#next")
    g.page.wait_for_function(
        "!document.querySelector('section[data-step=done]').hidden",
        timeout=60_000,
    )
    assert len(control(standin)["issues"]) == 1


def test_a_check_that_never_passes_ends_at_the_email(grower, standin):
    # Cloudflare's test key that always fails: logged, and after its errors
    # (or 30 seconds) Send offers the email
    control(standin, reset=True)
    g = grower("phone-390x844", key="2x00000000000000000000AB")
    g.to_step_five()
    g.press("#w-agree-permission")
    g.press("#w-agree-public")
    g.page.wait_for_timeout(31_000)
    g.press("#next")
    g.failed()
    g.shot("6-turnstile-failed")
    assert (
        g.text("#fail-say") == "The check that you're a person isn't working."
    )
    assert any("person check" in e for e in g.errors), g.errors


def test_the_draft_is_kept_and_back_goes_one_step(grower, standin):
    g = grower("phone-390x844")
    g.open_and_locate()
    for fx, fy in BLOCK_1:
        g.map_tap(fx, fy)
    g.press("#done-block")
    g.press("#next")
    g.at_step(3)
    g.type_in("#w-name", "Prairie Gap Vineyard")
    g.press("#wiz-close")
    assert g.text("#start") == "Continue adding your vineyard"
    assert g.text("#draft-text").startswith("Your answers so far are kept")
    g.page.reload(wait_until="load")
    g.press("#start")
    g.at_step(3)
    assert g.page.locator("#w-name").input_value() == "Prairie Gap Vineyard"
    g.press("#back")
    g.at_step(2)
    assert g.page.locator("#block-list li").count() == 1
    g.press("#back")
    g.at_step(1)
    assert g.errors == [], g.errors


def test_a_browser_that_keeps_nothing_is_told_so(grower, standin):
    g = grower("phone-360x780")
    g.page.add_init_script(
        "Storage.prototype.setItem = function () {"
        " throw new DOMException('blocked', 'SecurityError'); };"
    )
    g.page.reload(wait_until="load")
    g.open_and_locate()
    g.press("#wiz-close")
    assert g.text("#draft-text") == (
        "This browser won't keep your answers, so they stay only while this "
        "page is open."
    )
    assert g.errors == [], g.errors


def test_search_finds_a_road_and_says_when_it_cannot(grower, standin):
    g = grower("desktop-1440x900")
    g.press("#start")
    g.page.wait_for_function(
        "document.getElementById('map-loading').hidden", timeout=90_000
    )
    g.type_in("#search", "Ranch Road 152, Llano")
    g.press("#search-go")
    first = g.page.locator("#search-results button").first
    first.wait_for(timeout=30_000)
    assert "Ranch Road 152" in first.text_content()
    first.click()
    g.page.wait_for_function(
        "document.getElementById('search-results').children.length === 0"
    )
    # Esri refusing (an error answered with 200): never "Nothing found"
    g.context.route(
        "https://geocode-api.arcgis.com/**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"error":{"code":498,"message":"Invalid token."}}',
        ),
    )
    g.page.locator("#search").fill("County Road 103, Mason")
    g.press("#search-go")
    g.page.wait_for_function(
        "document.getElementById('search-results').textContent"
        ".includes('isn\\'t working')"
    )
    assert "Nothing found" not in g.text("#search-results")
    assert any("search did not answer" in e for e in g.errors), g.errors
