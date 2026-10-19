"""The growers' logo vote (docs/logo-vote.html), driven in Google Chrome.

Marked live. This checkout's docs/ is served on a free local port; the page
votes against the real function, the one-file bundle Dan deploys, served by
tests/vote_standin.mjs with stand-ins for Supabase and Turnstile; the page's
config is replaced (live, and pointed at the stand-in). At 390x844, a phone:

- the config as it is in the repository (live: false): "The vote moves here
  soon", the Shopify link, and no call to the function;
- the person check off (no site key, no secret): Like twice and Undo; the
  stand-in holds one vote by a signed id, and Your votes lists it;
- the person check on (Cloudflare's always-passing test site key; the widget
  loads from Cloudflare): the check shows, passes and hides; a vote counts;
- the carry-over: arriving from the Shopify page with #voter=<its id>, the
  fragment leaves the address at once, the id's three votes are handed to a
  new signed id and shown, and those designs are not offered again; the same
  link without the Shopify referrer carries nothing;
- the network limit: a vote answered "limit" says so and is not kept;
- sending a design: a photo chosen, sent, and waiting with no name.

No console error in any. Screenshots: target/browser-tests/logo-vote/.

    .venv/bin/python -m pytest -v -m live tests/live/test_logo_vote.py
"""

import functools
import http.server
import json
import shutil
import socket
import struct
import subprocess
import threading
import urllib.request
import zlib

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="playwright is in requirements-dev.txt: run ./build.sh env",
)
from conftest import ROOT
from conftest import SHOTS

from src.vote import bundle_function

pytestmark = pytest.mark.live
SHOT_DIR = SHOTS / "logo-vote"
NODE = shutil.which("node")
TEST_SITE_KEY = "1x00000000000000000000AA"  # Cloudflare's: always passes
SHOPIFY = "https://robertclayvineyards.com/pages/hsd-logo-vote"
SIGNED = "/^v2-[0-9a-f]{24}-[0-9a-f]{32}$/"


def png():
    """A one-pixel PNG, made here."""

    def chunk(kind, data):
        body = kind + data
        crc = struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + body + crc

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00\xb0\x30\x30")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", pixels)
        + chunk(b"IEND", b"")
    )


class Quiet(http.server.SimpleHTTPRequestHandler):
    """docs/, as GitHub Pages serves it, without the log or a cache."""

    def end_headers(self):
        """Every answer uncached, so each run reads this checkout's files."""
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        """Keeps the test's output quiet."""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def site():
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", free_port()),
        functools.partial(Quiet, directory=str(ROOT / "docs")),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://localhost:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


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
            str(ROOT / "tests" / "vote_standin.mjs"),
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


def control(standin, **body):
    """Sets the stand-ins; answers the votes and designs they hold."""
    req = urllib.request.Request(
        f"{standin}/standin", data=json.dumps(body).encode(), method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


class Phone:
    """One grower's phone on the page, its config replaced."""

    def __init__(self, browser, standin, live=True, key=""):
        """Opens a fresh phone (a new profile); the page is not loaded yet."""
        self.context = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
            locale="en-US",
        )
        if live:
            config = (
                "export const live = true;\n"
                f'export const endpoint = "{standin}/functions/v1/vote-api";\n'
                f'export const turnstileSiteKey = "{key}";\n'
                "export const carryFrom = "
                '["https://robertclayvineyards.com"];\n'
                "export const closed = false;\n"
                'export const chosen = "";\n'
            )
            self.context.route(
                "**/assets/vote-config.js*",
                lambda route: route.fulfill(
                    status=200, content_type="text/javascript", body=config
                ),
            )
        self.calls = []
        self.context.on(
            "request",
            lambda r: self.calls.append(r.url) if "vote-api" in r.url else None,
        )
        self.page = self.context.new_page()
        self.errors = []
        self.page.on(
            "console",
            lambda m: self.errors.append(m.text) if m.type == "error" else None,
        )
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.set_default_timeout(30_000)

    def open(self, site, fragment="", referer=None):
        self.page.goto(
            f"{site}/logo-vote.html{fragment}",
            wait_until="load",
            referer=referer,
        )

    def shot(self, label):
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        self.page.wait_for_timeout(300)
        self.page.screenshot(path=str(SHOT_DIR / f"390x844-{label}.png"))

    def tap(self, selector):
        loc = self.page.locator(selector)
        loc.scroll_into_view_if_needed()
        loc.tap()

    def text(self, selector):
        return self.page.locator(selector).text_content() or ""

    def wait_for_voter(self):
        self.page.wait_for_function(
            f"{SIGNED}.test(localStorage.getItem('hsd_voter') || '')"
        )

    def wait_sent(self):
        self.page.wait_for_function(
            "(localStorage.getItem('hsd_outbox') || '[]') === '[]'"
        )

    def close(self):
        errors = list(self.errors)
        self.context.close()
        assert not errors, errors


@pytest.fixture
def browser(chrome):
    return chrome[1]


def test_before_the_switch_over(browser, site, standin):
    phone = Phone(browser, standin, live=False)
    phone.open(site)
    phone.page.wait_for_timeout(800)
    assert phone.page.locator("#soon").is_visible()
    assert "The vote moves here soon." in phone.text("#soon")
    link = phone.page.locator("#soon a")
    assert link.get_attribute("href") == SHOPIFY
    for ident in ("vote", "send", "how"):
        assert not phone.page.locator(f"#{ident}").is_visible(), ident
    assert phone.calls == []
    phone.shot("1-soon")
    phone.close()


def test_voting_with_the_check_off(browser, site, standin):
    control(standin, reset=True, turnstile=False)
    phone = Phone(browser, standin)
    phone.open(site)
    phone.page.wait_for_selector("#card:not([hidden])")
    assert not phone.page.locator("#soon").is_visible()
    assert not phone.page.locator("#check").is_visible()
    phone.shot("2-first-screen")
    assert phone.page.evaluate("localStorage.getItem('hsd_voter')") is None
    phone.tap("#like")
    phone.wait_for_voter()
    phone.wait_sent()
    phone.page.wait_for_timeout(400)
    phone.tap("#pass")
    phone.page.wait_for_timeout(400)
    phone.wait_sent()
    phone.tap("#undo")
    phone.page.wait_for_timeout(400)
    phone.wait_sent()
    votes = control(standin)["votes"]
    voter = phone.page.evaluate("localStorage.getItem('hsd_voter')")
    assert [v["voter_token"] for v in votes] == [voter]
    assert votes[0]["dir"] == 1
    assert "(1)" in phone.text("#mine-count")
    assert not phone.page.locator("#check").is_visible()
    phone.shot("3-after-votes")
    phone.close()


def test_voting_with_the_check_on(browser, site, standin):
    control(standin, reset=True, turnstile=True)
    phone = Phone(browser, standin, key=TEST_SITE_KEY)
    phone.open(site)
    phone.page.wait_for_selector("#check:not([hidden])")
    phone.shot("4-person-check")
    phone.wait_for_voter()
    phone.page.wait_for_selector("#check", state="hidden")
    phone.tap("#like")
    phone.page.wait_for_timeout(400)
    phone.wait_sent()
    assert len(control(standin)["votes"]) == 1
    phone.close()


def test_the_carry_over_from_the_shopify_page(browser, site, standin):
    old = "vshopify0001"
    control(
        standin,
        reset=True,
        turnstile=False,
        votes=[
            {"design_id": "c1", "voter_token": old, "dir": 1},
            {"design_id": "c3", "voter_token": old, "dir": -1},
            {"design_id": "c4", "voter_token": old, "dir": 1},
        ],
    )
    # a planted link, not from the Shopify page: nothing carried
    phone = Phone(browser, standin)
    phone.open(site, f"#voter={old}")
    phone.page.wait_for_selector("#card:not([hidden])")
    assert "#voter" not in phone.page.url
    phone.page.wait_for_timeout(800)
    assert phone.page.evaluate("localStorage.getItem('hsd_voter')") is None
    assert phone.page.locator("#mine-wrap").is_hidden()
    phone.close()
    # from the Shopify page: carried once, shown, not offered again
    phone = Phone(browser, standin)
    phone.open(site, f"#voter={old}", referer=SHOPIFY)
    assert "#voter" not in phone.page.url
    phone.wait_for_voter()
    phone.page.wait_for_function(
        "document.getElementById('status').textContent"
        ".startsWith('Welcome back')"
    )
    assert "Your 3 votes" in phone.text("#status")
    assert "(3)" in phone.text("#mine-count")
    assert phone.text("#progress").startswith("10 to go")
    tokens = {v["voter_token"] for v in control(standin)["votes"]}
    assert tokens == {phone.page.evaluate("localStorage.getItem('hsd_voter')")}
    phone.shot("5-carried-over")
    phone.close()


def test_the_network_limit_is_said_plainly(browser, site, standin):
    control(standin, reset=True, turnstile=False)
    phone = Phone(browser, standin)

    def limit(route):
        if route.request.method == "POST" and "action=vote" in (
            route.request.post_data or ""
        ):
            route.fulfill(
                status=200,
                body="limit",
                headers={"Access-Control-Allow-Origin": site},
            )
        else:
            route.continue_()

    phone.page.route("**/functions/v1/vote-api", limit)
    phone.open(site)
    phone.page.wait_for_selector("#card:not([hidden])")
    phone.tap("#like")
    phone.page.wait_for_function(
        "document.getElementById('status').textContent"
        ".includes('on this same internet connection')"
    )
    assert phone.text("#status").startswith("10 people")
    assert phone.page.evaluate("localStorage.getItem('hsd_my_votes')") == "{}"
    phone.shot("6-limit")
    phone.close()


def test_sending_a_design(browser, site, standin):
    control(standin, reset=True, turnstile=False)
    phone = Phone(browser, standin)
    phone.open(site)
    phone.page.wait_for_selector("#card:not([hidden])")
    phone.page.set_input_files(
        "#file",
        files=[
            {"name": "sketch.png", "mimeType": "image/png", "buffer": png()}
        ],
    )
    phone.page.wait_for_selector("#preview:not([hidden])")
    phone.page.fill("#title", "Grandpa's Mesa")
    phone.tap("#send-button")
    phone.page.wait_for_function(
        "document.getElementById('send-status').textContent"
        ".startsWith('Thank you')"
    )
    subs = control(standin)["subs"]
    assert subs == [
        {"title": "Grandpa's Mesa", "name": "", "status": "pending"}
    ]
    phone.shot("7-sent")
    phone.close()
