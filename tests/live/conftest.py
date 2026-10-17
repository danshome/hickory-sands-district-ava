"""Fixtures for the browser tests of the published dashboard (issue #68).

The tests are in tests/live, marked live.
- site: the public group's items and the dashboard's URL, read anonymously
  (src/publish/agol_check.py's REST helper);
- chrome: one Google Chrome for the session, through Playwright: the installed
  Chrome (channel "chrome", or HSD_CHROME), headless, with a fresh temporary
  profile, so the dashboard is seen as TTB sees it, signed in to nothing;
- open_dashboard: a page on the dashboard at one viewport, loaded (the
  indicators hold their numbers), as a View;
- every test's screenshot: after each test,
  target/browser-tests/<viewport>-<test>.png (-FAILED.png when it failed, and
  named in the failure's report); target/browser-tests/<viewport>-loaded.png
  right after each load.
"""

import contextlib
import functools
import os
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

# anonymous GETs with retries; importing it reads nothing online
from src.publish.agol_check import GROUP_ID
from src.publish.agol_check import REST
from src.publish.agol_check import rest

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
except ImportError:
    # requirements-dev.txt has it; an older .venv may not: the tests then skip,
    # they do not error
    sync_playwright = None

ROOT = Path(__file__).resolve().parents[2]  # the repository root
SHOTS = ROOT / "target" / "browser-tests"
# the organization that publishes the group (README.md)
ORG = "https://robertclayvines.maps.arcgis.com"
# seconds a page may take to load: the dashboard loads the ArcGIS JS API, the
# web map and its layers
LOAD_S = 120


class View:
    """One browser page on the dashboard at one viewport.

    The viewport's name is like "phone-iphone-14-390x844" or
    "desktop-1366x650".
    """

    def __init__(self, name, page, phone):
        """Keeps the viewport's name, its page, and whether it is a phone."""
        self.name, self.page, self.phone = name, page, phone

    def shot(self, label):
        """Takes a screenshot of what the viewport shows now.

        Returns:
            Its path, or why there is none.
        """
        SHOTS.mkdir(parents=True, exist_ok=True)
        path = SHOTS / f"{self.name}-{label}.png"
        try:
            self.page.screenshot(path=str(path), timeout=30_000)
        except Exception as e:  # noqa: BLE001, RUF100
            # a closed or hung page: the test's own failure says more
            return f"(no screenshot: {type(e).__name__}: {e})"
        return path

    def wait(self, check, timeout=30, every=0.5):
        """Runs check() until it passes or timeout seconds pass.

        It passes when it raises no AssertionError or Playwright error; after
        the timeout its last error is raised.
        """
        end = time.monotonic() + timeout
        while True:
            try:
                return check()
            except AssertionError, PlaywrightError:
                if time.monotonic() > end:
                    raise
                self.page.wait_for_timeout(every * 1000)

    def close(self):
        """Closes the page's browser context."""
        self.page.context.close()


@pytest.fixture(scope="session")
def site():
    """The group's items by id and the dashboard's URL.

    The URL is HSD_DASHBOARD_URL, or the group's one Dashboard item's.
    """
    try:
        items, start = [], 1
        while start > 0:
            page = rest(
                REST + f"content/groups/{GROUP_ID}", num=100, start=start
            )
            items += page["items"]
            start = page.get("nextStart", -1)
    except Exception as e:  # noqa: BLE001, RUF100
        # whatever stops the read (network, HTTP, JSON) fails the tests
        pytest.fail(
            f"the public group {GROUP_ID} cannot be read without signing in: "
            f"{e}",
            pytrace=False,
        )
    url = os.environ.get("HSD_DASHBOARD_URL")
    if not url:
        dashboards = [it for it in items if it["type"] == "Dashboard"]
        if len(dashboards) != 1:
            pytest.fail(
                f"the group should hold one dashboard, not {len(dashboards)}",
                pytrace=False,
            )
        url = f"{ORG}/apps/dashboards/{dashboards[0]['id']}"
    return SimpleNamespace(
        url=url, group=GROUP_ID, items={it["id"]: it for it in items}
    )


@pytest.fixture(scope="session")
def chrome():
    """(playwright, browser): Google Chrome, headless.

    Each page gets a fresh profile (anonymous).
    """
    if sync_playwright is None:
        pytest.skip(
            "playwright is not installed in .venv (requirements-dev.txt): "
            "run ./build.sh env"
        )
    for old in SHOTS.glob("*.png"):  # this run's screenshots only
        old.unlink()
    with sync_playwright() as p:
        exe = os.environ.get("HSD_CHROME")
        try:
            browser = (
                p.chromium.launch(executable_path=exe)
                if exe
                else p.chromium.launch(channel="chrome")
            )
        except PlaywrightError as e:
            pytest.fail(
                "Google Chrome could not be started (install it, or set "
                f"HSD_CHROME to its path): {e}",
                pytrace=False,
            )
        yield p, browser
        browser.close()


@pytest.fixture(scope="session")
def open_dashboard(chrome, site):
    """A loader of the dashboard: load(name, phone, **context options).

    It returns a View of the dashboard, loaded: every indicator ready and
    holding a number. A load that fails is tried once more; then the fixture
    fails, naming the viewport and its screenshot.
    """
    _, browser = chrome

    def load(name, phone, **context):
        view = None
        for attempt in (1, 2):
            view = View(name, browser.new_context(**context).new_page(), phone)
            view.page.set_default_timeout(60_000)
            try:
                view.page.goto(
                    site.url, wait_until="load", timeout=LOAD_S * 1000
                )
                # the map may keep fetching tiles; the indicators below decide
                # whether the page is up
                with contextlib.suppress(PlaywrightTimeout):
                    view.page.wait_for_load_state("networkidle", timeout=60_000)
                view.wait(
                    functools.partial(indicators_loaded, view.page),
                    timeout=LOAD_S,
                )
                # the indicators fit their text after the numbers arrive
                view.page.wait_for_timeout(2000)
                view.shot("loaded")
                return view
            except (AssertionError, PlaywrightError) as e:
                shot = view.shot(f"load-{attempt}-FAILED")
                view.close()
                if attempt == 2:
                    pytest.fail(
                        f"{name}: the dashboard {site.url} did not load (no "
                        f"indicator numbers after {LOAD_S} s): "
                        f"{type(e).__name__}: {e}; screenshot: {shot}",
                        pytrace=False,
                    )
        return None  # not reached: the second failed load fails the fixture

    return load


def indicators_loaded(page):
    widgets = page.locator("dashboards-indicator-widget")
    n = widgets.count()
    assert n > 0, "no indicator on the page yet"
    assert page.locator("dashboards-indicator-widget[ready]").count() == n, (
        "indicators not ready yet"
    )
    values = page.locator(
        "dashboards-indicator-item[slot=middle] #text"
    ).evaluate_all("els => els.map(e => e.textContent.trim())")
    assert len(values) == n and all(values), (
        f"indicator numbers not shown yet: {values}"
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """After every test that used a View: its screenshot.

    A failure's report names it.
    """
    outcome = yield
    report = outcome.get_result()
    if report.when != "call":
        return
    view = next(
        (
            v
            for v in getattr(item, "funcargs", {}).values()
            if isinstance(v, View)
        ),
        None,
    )
    if view is not None:
        path = view.shot(
            item.originalname + ("-FAILED" if report.failed else "")
        )
        if report.failed:
            report.sections.append(("screenshot", str(path)))
