"""The growers' logo vote page, docs/logo-vote.html (issue #100).

The page is kept from search engines (noindex, and not in the sitemap); it
says "The vote moves here soon" and links to the Shopify page until
docs/assets/vote-config.js says live, so merging the page breaks nothing;
the vote's sections are hidden until then. The config names the function's
address, no Turnstile site key (the person check is off), and the Shopify
page's origins for the carry-over. The carried voter id is read and cleared
by an inline script before analytics.js. The 13 built-in designs keep the
Shopify page's ids and each is a JPEG in docs/assets/logo-vote/designs/. The
script never writes HTML (no innerHTML and the like), never runs text as
code, and asks no name. Standard library only.
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
PAGE = os.path.join(DOCS, "logo-vote.html")
ASSETS = os.path.join(DOCS, "assets")
DESIGNS = os.path.join(ASSETS, "logo-vote", "designs.json")
SHOPIFY = "https://robertclayvineyards.com/pages/hsd-logo-vote"
# the Shopify page's ENTRIES, in its order (sections/hsd-logo-vote.liquid)
SHOPIFY_IDS = [
    "current",
    "c1",
    "c3",
    "c4",
    "c5",
    "c6",
    "c7",
    "c8",
    "c10",
    "c12",
    "c14",
    "c15",
    "c16",
]


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def config():
    return read(os.path.join(ASSETS, "vote-config.js"))


def test_the_page_is_kept_from_search_engines():
    page = read(PAGE)
    assert '<meta name="robots" content="noindex, nofollow">' in page
    assert "logo-vote" not in read(os.path.join(DOCS, "sitemap.xml"))


def test_before_the_switch_over_it_says_the_vote_moves_here_soon():
    page = read(PAGE)
    assert re.search(r"\bexport const live = false;", config())
    soon = re.search(
        r'<section [^>]*id="soon"[^>]*>(.*?)</section>', page, re.S
    )
    assert soon, "no #soon section"
    assert "hidden" not in soon.group(0).split(">")[0]
    assert "The vote moves here soon." in soon.group(1)
    assert f'href="{SHOPIFY}"' in soon.group(1)
    for ident in ("vote", "send", "how", "foot"):
        tag = re.search(rf'<[a-z]+ [^>]*id="{ident}"[^>]*>', page)
        assert tag and " hidden" in tag.group(0), ident


def test_the_config_names_the_function_and_no_site_key():
    text = config()
    assert (
        '"https://yayebhncbagmebwgmezd.supabase.co/functions/v1/vote-api"'
        in text
    )
    assert 'export const turnstileSiteKey = "";' in text
    assert '"https://robertclayvineyards.com"' in text
    assert "export const closed = false;" in text
    assert 'export const chosen = "";' in text


def test_the_carried_id_is_cleared_before_analytics():
    page = read(PAGE)
    head = page.split("</head>")[0]
    carry = head.find("#voter=")
    analytics = head.find("assets/analytics.js")
    assert 0 < carry < analytics
    assert 'history.replaceState(null, "", location.pathname' in head


def test_the_designs_keep_the_shopify_ids_and_their_pictures():
    with open(DESIGNS, encoding="utf-8") as fh:
        designs = json.load(fh)
    assert [d["id"] for d in designs] == SHOPIFY_IDS
    for d in designs:
        assert d["name"] and d["sub"], d["id"]
        assert re.fullmatch(
            r"assets/logo-vote/designs/[a-z0-9-]+\.jpg", d["img"]
        ), d["img"]
        with open(os.path.join(DOCS, d["img"]), "rb") as fh:
            assert fh.read(3) == b"\xff\xd8\xff", d["img"]


def test_the_script_writes_no_html_and_asks_no_name():
    text = read(os.path.join(ASSETS, "logo-vote.js"))
    for sink in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "new Function",
        "callback=",
    ):
        assert sink not in text, sink
    assert 'name: ""' in text  # the upload's name is always empty
    assert "Your name" not in read(PAGE)
    assert "demo" not in text
