"""docs/vineyards.html: the vineyards on the site, and "Add your vineyard".

The page lists every vineyard of the site's data (assets/vineyard-list.js)
and opens the five-step form (assets/vineyard-wizard.js), which sends to
the Supabase function set in assets/vineyard-config.js and, when it cannot
send, offers the email (assets/vineyard-email.js). These check the page and
its files: the old email form gone; every field labelled, every message tied
to its field, every field the rules name on the page; the counties and
varieties the rules'; the config empty or well formed, and the form ending
at the email while it is empty; no script that parses text as HTML or hides
a failure in an empty catch; one pinned SDK; the targets' sizes; the
wording. And, in node when it is installed, the fallback's email: every line
in order, never a URL past LONG_URL, nothing typed able to add a header, an
emoji never cut in half. The rules themselves are
tests/test_vineyard_rules.py's. Standard library only, so the lint workflow
runs these.
"""

from html.parser import HTMLParser
import json
import os
import re
import shutil
import subprocess
from urllib.parse import parse_qs
from urllib.parse import urlsplit

import pytest

from src.vineyards import submission as vs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
ASSETS = os.path.join(DOCS, "assets")
SCRIPTS = ("vineyard-wizard.js", "vineyard-list.js", "vineyard-email.js")
SDK = "https://js.arcgis.com/5.1/"
NODE = shutil.which("node")
ADDRESS = "district@hickorysandsdistrictava.org"
# Calls one function of vineyard-email.js with JSON arguments from stdin and
# prints its result as JSON: node only evaluates, the tests decide.
BRIDGE = """
import { pathToFileURL } from "node:url";
const [path, name] = process.argv.slice(1);
const module = await import(pathToFileURL(path));
let input = "";
for await (const chunk of process.stdin) input += chunk;
const result = module[name](...JSON.parse(input));
process.stdout.write(JSON.stringify(result ?? null));
"""


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


class Page(HTMLParser):
    """Every element's tag and attributes, and every label's target."""

    def __init__(self):
        """Starts an empty page."""
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.labels = set()
        self.text = []

    def handle_starttag(self, tag, attrs):
        """Keeps the element."""
        a = dict(attrs)
        self.elements.append((tag, a))
        if tag == "label" and a.get("for"):
            self.labels.add(a["for"])

    def handle_data(self, data):
        """Keeps the text."""
        self.text.append(data)


@pytest.fixture(scope="module")
def page():
    parser = Page()
    parser.feed(read(DOCS, "vineyards.html"))
    return parser


@pytest.fixture(scope="module")
def html():
    return read(DOCS, "vineyards.html")


@pytest.fixture(scope="module")
def wizard():
    return read(ASSETS, "vineyard-wizard.js")


def ids(page):
    return {a["id"] for _, a in page.elements if a.get("id")}


def test_the_page_loads_its_own_files_and_not_the_old_form(html):
    for name in (
        "assets/site.css",
        "assets/vineyard-form.css",
        "assets/vineyard-list.js",
        "assets/vineyard-wizard.js",
    ):
        assert name in html
        assert os.path.isfile(os.path.join(DOCS, name)), name
    for gone in ("forms.css", "vineyards.js", 'action="mailto:', "<form class"):
        assert gone not in html, gone
    for name in ("vineyards.js", "forms.css"):
        assert not os.path.exists(os.path.join(ASSETS, name)), name


def test_every_field_is_labelled_and_every_reference_resolves(page):
    known = ids(page)
    for tag, a in page.elements:
        if tag in {"input", "select", "textarea"} and a.get("type") != "radio":
            if a.get("type") == "checkbox":
                continue  # a box inside its label
            assert a.get("id") in page.labels, a
        for ref in ("aria-describedby", "aria-labelledby", "aria-controls"):
            for target in (a.get(ref) or "").split():
                assert target in known, (tag, ref, target)


def test_every_field_the_rules_name_has_its_place_and_message(page, wizard):
    known = ids(page)
    block = re.search(r"const FIELD_ELEMENT = \{(.*?)\};", wizard, re.DOTALL)
    pairs = re.findall(r'"?([\w-]+)"?: "([\w-]+)"', block.group(1))
    assert len(pairs) == 11
    for field, element in pairs:
        assert element in known, element
        assert f"err-{field}" in known, field
    # every field the Python twin can name, the page shows
    raw = {
        "form": vs.FORM,
        "version": 1,
        "id": "0" * 8 + "-0000-4000-8000-" + "0" * 12,
    }
    _, errors, _ = vs.check(dict(raw, blocks=[], pin=None), year=2026)
    named = {f for f, _ in errors}
    for field in named:
        assert field in dict(pairs) or field in {"where"}, field
    assert "err-where" in known


def test_the_counties_and_varieties_are_the_rules(html):
    options = re.findall(
        r"<option>([^<]+)</option>",
        html.split('id="w-county"')[1].split("</select>")[0],
    )
    assert tuple(options) == vs.COUNTIES
    rules = read(ASSETS, "vineyard-blocks.js")
    chips = re.search(r"export const VARIETIES = \[(.*?)\];", rules, re.DOTALL)
    assert tuple(re.findall(r'"([^"]+)"', chips.group(1))) == vs.VARIETIES


def test_the_config_is_empty_or_well_formed(wizard):
    text = read(ASSETS, "vineyard-config.js")
    endpoint = re.search(r'export const endpoint = "([^"]*)";', text).group(1)
    key = re.search(r'export const turnstileSiteKey = "([^"]*)";', text).group(
        1
    )
    assert endpoint == "" or re.fullmatch(
        r"https://[a-z0-9-]+\.supabase\.co/functions/v1/vineyard-submit",
        endpoint,
    )
    assert key == "" or re.fullmatch(r"0x[A-Za-z0-9_-]{10,}", key)
    # while either is empty, Send ends at the email, never a Turnstile that
    # cannot resolve
    assert 'from "./vineyard-config.js"' in wizard
    assert "const CONFIGURED = READY && Boolean(turnstileSiteKey);" in wizard
    assert "if (CONFIGURED) loadTurnstile();" in wizard
    assert "if (!CONFIGURED || turnstileFailed) {" in wizard


@pytest.mark.parametrize("name", SCRIPTS)
def test_no_script_parses_text_as_html_or_hides_a_failure(name):
    text = read(ASSETS, name)
    for sink in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
    ):
        assert sink not in text, f"{name} uses {sink}"
    assert not re.search(
        r"catch\s*\(\s*(\(\s*\))?\s*(=>)?\s*\{\s*\}\s*\)", text
    ), f"{name} has an empty catch"
    assert "localStorage" not in text or name == "vineyard-wizard.js"


def test_the_maps_load_one_pinned_sdk_only_when_needed(html):
    assert "js.arcgis.com" not in html  # loaded when asked, not with the page
    for name in ("vineyard-wizard.js", "vineyard-list.js"):
        text = read(ASSETS, name)
        assert f'const SDK = "{SDK}";' in text
        assert not re.findall(r"js\.arcgis\.com/(?!5\.1/)", text)


def test_the_data_the_scripts_read_is_there(wizard):
    for path in re.findall(
        r'"((?:assets|data)/[\w/.-]+\.(?:geo)?json)"', wizard
    ):
        assert os.path.isfile(os.path.join(DOCS, path)), path
    listing = read(ASSETS, "vineyard-list.js")
    assert 'const DATA = "assets/vineyards/";' in listing
    for name in ("register.json", "vineyards.geojson"):
        assert f"${{DATA}}{name}" in listing
        assert os.path.isfile(os.path.join(ASSETS, "vineyards", name))


def test_targets_are_big_enough_to_tap():
    css = read(ASSETS, "vineyard-form.css")
    sizes = {
        ".w-button{": 56,
        ".map-button{": 56,
        ".w-link{": 48,
        ".chip{": 48,
        ".vy-show{": 48,
        ".wiz-close{": 48,
    }
    for rule, least in sizes.items():
        body = css.split(rule, 1)[1].split("}", 1)[0]
        found = re.search(r"min-height:(\d+)px|height:(\d+)px", body)
        assert found, rule
        assert int(found.group(1) or found.group(2)) >= least, rule


def test_the_wording(html, wizard):
    text = re.sub(r"<[^>]+>", " ", html) + wizard
    low = text.lower()
    assert "agreed" not in low
    assert "We'll review it within about a week." in html
    assert "[about a week]" not in html
    assert "At the time of the petition:" in html
    assert "as each owner approves it" not in html
    # the petitioners, never "the district" for them
    assert not re.search(r"\b(to|by|from) the district\b", low)
    assert "petitioners" in low
    # the thank-you screen gives the email address, no telephone number
    done = html.split('data-step="done"')[1].split("</section>")[0]
    assert ADDRESS in done
    assert not re.search(r"\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}", done)
    # GitHub is named once, in the public box; "issue" never to a grower
    words = re.sub(r"<[^>]+>", " ", html.split('id="wiz"')[1])
    assert "issue" not in words.lower()
    assert "polygon" not in words.lower()


# ---- the email the failure screen offers (node) -----------------------------


@pytest.fixture(scope="module")
def js(tmp_path_factory):
    """Returns call(name, *args): a function of vineyard-email.js, run."""
    if not NODE:
        pytest.skip("node is not installed")
    module = tmp_path_factory.mktemp("js") / "vineyard-email.mjs"
    shutil.copy(os.path.join(ASSETS, "vineyard-email.js"), module)

    def call(name, *args):
        done = subprocess.run(
            [NODE, "--input-type=module", "-e", BRIDGE, str(module), name],
            input=json.dumps(args),
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(done.stdout)

    return call


SENT = {
    "vineyard": {
        "name": "Prairie Gap Vineyard",
        "county": "Mason",
        "planted": "planted",
        "acres": 4.5,
        "year": 2019,
        "varieties": ["Tempranillo", "Mourvèdre"],
    },
    "blocks": [
        [[-99.295, 30.865], [-99.2925, 30.865], [-99.2925, 30.8632]],
    ],
    "pin": None,
    "contact": {"name": "Jane", "email": "jane@example.com", "phone": ""},
}


def test_every_line_is_there_in_order(js):
    built = js("message", SENT)
    assert built["subject"] == "Vineyard submission: Prairie Gap Vineyard"
    assert built["body"].split("\r\n") == [
        "Vineyard: Prairie Gap Vineyard",
        "County: Mason",
        "Planted or planned: planted",
        "Acres planted: 4.5",
        "Year first planted: 2019",
        "Varieties: Tempranillo, Mourvèdre",
        "",
        "Pin: ",
        "Block 1:",
        "30.86500, -99.29500",
        "30.86500, -99.29250",
        "30.86320, -99.29250",
        "",
        "Contact (for the petitioners only, never published)",
        "Name: Jane",
        "Phone: ",
        "Email: jane@example.com",
    ]


def test_an_empty_form_says_nothing_wrong(js):
    built = js("message", {})
    assert "undefined" not in built["body"]
    assert "null" not in built["body"]
    assert built["subject"] == "Vineyard submission: (no name given)"


def test_a_message_that_fits_goes_whole(js):
    built = js("message", SENT)
    planned = js("plan", built)
    assert planned["long"] is False
    query = parse_qs(urlsplit(planned["url"]).query)
    assert query["body"][0] == built["body"]
    assert urlsplit(planned["url"]).path == ADDRESS


def test_a_long_message_never_makes_a_long_url(js):
    big = json.loads(json.dumps(SENT))
    big["blocks"] = [
        [[-99.3 + i * 1e-4, 30.8 + j * 1e-4] for j in range(100)]
        for i in range(20)
    ]
    planned = js("plan", js("message", big))
    assert planned["long"] is True
    assert len(planned["url"]) <= 1900
    body = parse_qs(urlsplit(planned["url"]).query)["body"][0]
    assert (
        body
        == "The vineyard details were copied from the form: paste them here."
    )


def test_nothing_typed_adds_a_header(js):
    sneaky = json.loads(json.dumps(SENT))
    sneaky["vineyard"]["name"] = "X\r\nBcc: someone@example.com&cc=x?y#z"
    url = js("plan", js("message", sneaky))["url"]
    assert "\r" not in url
    assert "\n" not in url
    query = parse_qs(urlsplit(url).query)
    assert set(query) == {"subject", "body"}


def test_an_emoji_is_never_cut_in_half(js):
    name = "V" * 118 + "\U0001f347\U0001f347"
    built = js(
        "message", dict(SENT, vineyard=dict(SENT["vineyard"], name=name))
    )
    assert len(built["subject"]) <= 140
    assert "\ufffd" not in built["subject"]
