"""The moved pages' redirect (docs/assets/moved.js), run in node.

explore.html and aquifer.html are now the map: each loads assets/moved.js
with the address it moved to (data-to), and the script goes there at once,
keeping the old address's query (its words win over the new address's) and
its #fragment, with location.replace, so Back does not return to the old
page. Here the script runs in node with a stand-in for the page's document
and location; the tests check where it goes. Without node these are skipped
(it is on GitHub's Linux runners).
"""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
SCRIPT = os.path.join(DOCS, "assets", "moved.js")
NODE = shutil.which("node")
SITE = "https://hickorysandsdistrictava.org/"
WATER = "map.html?layers=aquifer,vineyards,places"
# Runs moved.js in a fresh context with the page's data-to and address from
# stdin, and prints where location.replace was sent (null if it was not).
BRIDGE = """
import { readFileSync } from "node:fs";
import vm from "node:vm";
let input = "";
for await (const chunk of process.stdin) input += chunk;
const [to, address] = JSON.parse(input);
const here = new URL(address);
let went = null;
const location = {
  href: here.href, search: here.search, hash: here.hash,
  replace(url) { went = String(url); },
};
const document = { currentScript: { dataset: { to } } };
vm.runInNewContext(readFileSync(process.argv[1], "utf8"),
  { document, location, URL, URLSearchParams });
process.stdout.write(JSON.stringify(went));
"""


@pytest.fixture(scope="module")
def goes():
    """Returns a function of (to, address): where moved.js sends a reader."""
    if NODE is None:
        pytest.skip("node is not installed")

    def run(to, address):
        done = subprocess.run(
            [NODE, "--input-type=module", "-e", BRIDGE, SCRIPT],
            input=json.dumps([to, SITE + address]),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=60,
        )
        assert done.returncode == 0, done.stderr
        went = json.loads(done.stdout)
        assert went is not None, "moved.js did not go anywhere"
        assert went.startswith(SITE), f"left the site: {went}"
        return went.removeprefix(SITE)

    return run


def data_to(page):
    """The address a moved page's script sends the reader to."""
    with open(os.path.join(DOCS, page), encoding="utf-8") as fh:
        found = re.search(
            r'src="assets/moved\.js" data-to="([^"]+)"', fh.read()
        )
    assert found, page
    return found.group(1)


@pytest.mark.parametrize(
    ("page", "address", "went"),
    [
        ("explore.html", "explore.html", "map.html"),
        ("explore.html", "explore.html?step=52#map", "map.html?step=52#map"),
        ("explore.html", "explore.html#map", "map.html#map"),
        ("aquifer.html", "aquifer.html", WATER),
        (
            "aquifer.html",
            "aquifer.html?view=district",
            f"{WATER}&view=district",
        ),
        # the old address's words win: the wells, without the aquifer
        ("aquifer.html", "aquifer.html?layers=wells", "map.html?layers=wells"),
        (
            "aquifer.html",
            "aquifer.html?layers=wells&step=7#top",
            "map.html?layers=wells&step=7#top",
        ),
    ],
)
def test_a_moved_page_goes_to_the_map_with_its_query(goes, page, address, went):
    assert goes(data_to(page), address) == went


def test_the_old_address_cannot_send_the_reader_off_the_site(goes):
    # Only the query and the #fragment are carried over; the page's own
    # data-to fixes where it goes.
    went = goes("map.html", "explore.html?to=https://example.com/#//evil")
    assert went.startswith("map.html?to=https"), went
