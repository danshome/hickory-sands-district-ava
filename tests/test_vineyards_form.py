"""docs/vineyards.html: a vineyard's owner adds it by email ("Not listed?").

The section's form builds an email to the district and opens it in the
visitor's own email app (a mailto: URL); the page sends and keeps nothing.
These check the section's files; the form (the district's address, a label for
every field, the required fields and their marks, the consent's own words, every
error linked to the fields it marks, the panels' roles, Enter moving on, the
coordinate boxes' length); the county list against the counties of the
district in docs/data/; the scripts (no HTML parsing, no storage, no requests
of their own, one pinned SDK); the stylesheet, scoped to the section; and, in
node when it is installed (it is on GitHub's Linux runners), the email the form
builds: its fixed text short, its URL never past LONG_URL (a longer message
goes by the clipboard), an emoji never cut in half, nothing typed able to add
a header, and every line there in the same order.
Standard library only, so the lint workflow runs these.
"""

from html.parser import HTMLParser
import json
import os
import re
import shutil
import subprocess
from urllib.parse import parse_qs

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
ASSETS = os.path.join(DOCS, "assets")
PAGE = os.path.join(DOCS, "vineyards.html")
SCRIPT = os.path.join(ASSETS, "vineyards.js")
EMAIL = os.path.join(ASSETS, "vineyard-email.js")
STYLES = os.path.join(ASSETS, "forms.css")
SDK = "https://js.arcgis.com/5.1/"
CONSENT = (
    "I own or manage this vineyard, or have the owner's permission, and agree"
    " that its name, outline and the details above (not the contact details)"
    " may be shown on this site and its maps."
)
# The fields the form needs; every other field is optional.
REQUIRED = {"v-name", "v-county", "v-contact", "v-email", "v-consent"}
# The "Where it is" message marks the point and the road (vineyards.js).
WHERE = ("v-lat", "v-lon", "v-road")
VOID = {"br", "img", "input", "link", "meta", "source", "wbr", "hr"}
NODE = shutil.which("node")
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


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class Page(HTMLParser):
    """Every element of a page: its tag, attributes, text and ancestors."""

    def __init__(self):
        """Starts an empty page."""
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        """Keeps the element, and opens it unless it is void."""
        element = {
            "tag": tag,
            "attrs": dict(attrs),
            "text": "",
            "spoken": "",
            "within": list(self.stack),
        }
        self.elements.append(element)
        if tag not in VOID:
            self.stack.append(element)

    def handle_endtag(self, tag):
        """Closes the element, and any left open inside it."""
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        """Adds text to every open element; spoken leaves out aria-hidden."""
        hidden = any(
            e["attrs"].get("aria-hidden") == "true" for e in self.stack
        )
        for element in self.stack:
            element["text"] += data
            if not hidden:
                element["spoken"] += data


@pytest.fixture(scope="module")
def page():
    parsed = Page()
    parsed.feed(read(PAGE))
    parsed.close()
    return parsed.elements


def by_id(elements, ident):
    found = [e for e in elements if e["attrs"].get("id") == ident]
    assert len(found) == 1, f"{len(found)} elements with id {ident}"
    return found[0]


def inside(element, ident):
    return any(e["attrs"].get("id") == ident for e in element["within"])


def controls(elements):
    """The form's fields: every input but hidden ones, select and textarea."""
    return [
        e
        for e in elements
        if inside(e, "vineyard-form")
        and e["tag"] in ("input", "select", "textarea")
        and e["attrs"].get("type") != "hidden"
    ]


def words(text):
    return " ".join(text.split())


def described(element):
    return (element["attrs"].get("aria-describedby") or "").split()


def address():
    """The district's address, as About & contact gives it."""
    found = set(
        re.findall(
            r'href="mailto:([^"?]+)"', read(os.path.join(DOCS, "about.html"))
        )
    )
    assert len(found) == 1, found
    return found.pop()


def test_the_section_s_files_are_there_and_loaded():
    text = read(PAGE)
    assert '<link rel="stylesheet" href="assets/forms.css">' in text
    assert '<script type="module" src="assets/vineyards.js"></script>' in text
    for path in (SCRIPT, EMAIL, STYLES):
        assert os.path.isfile(path), path
    script = read(SCRIPT)
    assert 'from "./vineyard-email.js"' in script
    assert 'const MAPS = "./maps.js"' in script
    assert os.path.isfile(os.path.join(ASSETS, "maps.js"))


def test_the_form_mails_the_district(page):
    to = address()
    form = by_id(page, "vineyard-form")
    assert form["attrs"]["action"] == (
        f"mailto:{to}?subject=Vineyard%20submission"
    )
    assert form["attrs"]["method"] == "post"
    assert form["attrs"]["enctype"] == "text/plain"
    assert f'export const ADDRESS = "{to}";' in read(EMAIL)
    shown = [
        e
        for e in page
        if inside(e, "add")
        and e["tag"] == "a"
        and e["attrs"].get("href") == f"mailto:{to}"
        and e["text"] == to
    ]
    assert shown, "the address is on the page as a mailto: link"


def test_every_field_has_a_label_and_no_placeholder(page):
    labelled = {e["attrs"].get("for") for e in page if e["tag"] == "label"}
    for control in controls(page):
        ident = control["attrs"].get("id")
        assert ident, control
        in_label = any(e["tag"] == "label" for e in control["within"])
        assert ident in labelled or in_label, ident
        assert "placeholder" not in control["attrs"], ident


def test_the_required_fields_and_only_they_are_marked(page):
    for control in controls(page):
        ident = control["attrs"]["id"]
        needed = ident in REQUIRED or control["attrs"].get("name") == "Status"
        assert ("required" in control["attrs"]) == needed, ident
    labels = {
        e["attrs"]["for"]: e
        for e in page
        if e["tag"] == "label" and "for" in e["attrs"]
    }
    for ident, label in labels.items():
        assert ("*" in label["text"]) == (ident in REQUIRED), ident
    status = [e for e in page if e["tag"] == "legend" and inside(e, "v-status")]
    assert status
    assert "*" in status[0]["text"]
    consent = by_id(page, "v-consent")["within"][-1]  # the box's own label
    assert consent["tag"] == "label"
    assert "*" in consent["text"]


def test_the_consent_is_in_its_own_words(page):
    assert words(by_id(page, "v-consent-text")["text"]) == CONSENT


def test_the_form_key_reads_correctly(page):
    # Its * is hidden from screen readers, so words say what it means (R6).
    spoken = words(by_id(page, "form-key")["spoken"])
    assert "Fields marked are" not in spoken
    assert "with a star" in spoken
    assert ".add-vineyard .visually-hidden{" in read(STYLES)


def test_every_reference_names_an_element(page):
    ids = {e["attrs"]["id"] for e in page if "id" in e["attrs"]}
    for element in page:
        for name in ("aria-describedby", "aria-labelledby", "aria-controls"):
            for ident in (element["attrs"].get(name) or "").split():
                assert ident in ids, (name, ident)


def test_each_message_is_read_with_the_fields_it_marks(page):
    # R7: a field reads its own message; a group's message is read with each
    # control it marks, as a fieldset's own description often is not.
    errors = [
        e for e in page if "field-error" in (e["attrs"].get("class") or "")
    ]
    assert errors
    for error in errors:
        ident = error["attrs"]["id"]
        base = ident.removesuffix("-error")
        if base == "v-where":
            marked = [by_id(page, i) for i in WHERE]
        elif by_id(page, base)["tag"] == "fieldset":
            marked = [
                e for e in page if e["tag"] == "input" and inside(e, base)
            ]
        else:
            marked = [by_id(page, base)]
        assert marked, ident
        for field in marked:
            assert ident in described(field), (field["attrs"]["id"], ident)
    marks = (
        'if (id === "v-where") return [$("v-lat"), $("v-lon"), $("v-road")];'
    )
    assert marks in read(SCRIPT)


def test_the_where_message_sits_at_the_group_s_top(page):
    order = [e["attrs"].get("id") for e in page]
    hint = order.index("v-where-hint")
    assert order[hint + 1] == "v-where-error"
    assert order.index("v-where-error") < order.index("pin-open")


def test_the_panels_and_messages_have_their_roles(page):
    # R8: a named panel is a region or a group, never a bare div.
    roles = {
        "ready": ("region", "aria-labelledby", "ready-title"),
        "ready-body": ("region", "aria-label", "The message"),
        "error-summary": ("group", "aria-labelledby", "error-summary-title"),
    }
    for ident, (role, name, value) in roles.items():
        attrs = by_id(page, ident)["attrs"]
        assert attrs.get("role") == role, ident
        assert attrs.get(name) == value, ident
    assert by_id(page, "status")["attrs"].get("role") == "status"
    assert by_id(page, "pin-failed")["attrs"].get("role") == "alert"
    for ident in ("ready", "error-summary"):  # focus moves to them
        assert by_id(page, ident)["attrs"].get("tabindex") == "-1"
    for element in page:
        named = {"aria-label", "aria-labelledby"} & set(element["attrs"])
        if (
            named
            and inside(element, "add")
            and element["tag"] in ("div", "pre", "p", "span")
        ):
            assert element["attrs"].get("role"), element["attrs"].get("id")


def test_enter_moves_to_the_next_field(page):
    # R2: Enter (a phone keyboard's Go) in a one-line field never sends.
    for control in controls(page):
        if control["tag"] == "input" and control["attrs"].get("type") in (
            "text",
            "email",
        ):
            ident = control["attrs"]["id"]
            assert control["attrs"].get("enterkeyhint") == "next", ident
    script = read(SCRIPT)
    assert 'event.key !== "Enter"' in script
    assert "event.preventDefault();\n  nextField(field)?.focus();" in script


def test_a_pasted_pair_fits_a_coordinate_box(page):
    # R9: "30.764680° N, 99.410730° W" and longer pairs fit.
    for ident in ("v-lat", "v-lon"):
        assert by_id(page, ident)["attrs"].get("maxlength") == "40"


def test_the_counties_are_the_district_s(page):
    # R10: the choices are the counties the district lies in, as the build's
    # data gives them, then "Not sure".
    data = json.loads(read(os.path.join(DOCS, "data", "boundary.geojson")))
    (boundary,) = data["features"]
    counties = boundary["properties"]["counties"].split(", ")
    assert counties
    options = [
        e["attrs"].get("value", words(e["text"]))
        for e in page
        if e["tag"] == "option" and inside(e, "v-county")
    ]
    assert options == ["", *counties, "Not sure"]


def test_the_error_links_are_phone_sized():
    # R11: each link in the error summary is at least 44px tall.
    rule = re.search(
        r"\.add-vineyard \.error-summary a\{([^}]*)\}", read(STYLES)
    )
    assert rule
    assert "display:block" in rule.group(1)
    assert "min-height:44px" in rule.group(1)


def test_the_section_s_wording():
    text = read(PAGE)
    assert "the proposed Hickory Sands District" in text
    assert not re.search(r"\bagreed\b", text, re.IGNORECASE)
    assert "<noscript>" not in text


@pytest.mark.parametrize("path", [SCRIPT, EMAIL], ids=os.path.basename)
def test_the_scripts_keep_and_send_nothing(path):
    text = read(path)
    for sink in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "document.cookie",
        "fetch(",
        "XMLHttpRequest",
        "sendBeacon",
        "WebSocket",
        "formspree",
        "script.google",
    ):
        assert sink not in text, f"{os.path.basename(path)} uses {sink}"
    urls = {
        url
        for url in re.findall(r"https?://[^\s\"'`]+", text)
        if "${" not in url  # the website a visitor types, made a URL
    }
    assert urls <= {SDK}, urls
    assert not re.findall(r"js\.arcgis\.com/(?!5\.1/)", text)


def test_the_map_loads_the_pinned_sdk_only_when_asked():
    text = read(SCRIPT)
    assert f'const SDK = "{SDK}";' in text
    assert 'addEventListener("click", openMap)' in text
    assert "js.arcgis.com" not in read(PAGE)  # nothing from Esri until asked


def test_the_stylesheet_styles_only_its_section():
    text = re.sub(r"/\*.*?\*/", "", read(STYLES), flags=re.S)
    rules = re.findall(r"([^{}]+)\{[^{}]*\}", text)
    assert rules
    for selectors in rules:
        for selector in selectors.split(","):
            assert selector.strip().startswith(".add-vineyard"), selector


# --- the email, built in node ---------------------------------------------


@pytest.fixture(scope="module")
def js(tmp_path_factory):
    """Returns call(name, *args): a function of vineyard-email.js, run."""
    if NODE is None:
        pytest.skip("node is not installed")
    module = tmp_path_factory.mktemp("js") / "vineyard-email.mjs"
    shutil.copyfile(EMAIL, module)  # .mjs: a module, whatever node's version

    def call(name, *args):
        done = subprocess.run(
            [NODE, "--input-type=module", "-e", BRIDGE, str(module), name],
            input=json.dumps(list(args)),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=60,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return call


def built(js, raw):
    """Returns the message and the plan for the form's raw values."""
    mail = js("message", js("normalize", raw), CONSENT)
    return mail, js("plan", mail)


def query(url):
    head, _, rest = url.partition("?")
    assert head == f"mailto:{address()}"
    return rest, parse_qs(rest, keep_blank_values=True)


def maxlengths(page):
    return {
        e["attrs"]["id"]: int(e["attrs"]["maxlength"])
        for e in controls(page)
        if "maxlength" in e["attrs"]
    }


def test_the_fixed_text_is_short(js):
    # R1: with every field empty but the consent, the URL is under 900.
    mail, sent = built(js, {"consent": True})
    assert not sent["long"]
    assert len(sent["url"]) < 900, len(sent["url"])
    assert f"Consent: Yes. {CONSENT}" in mail["body"]


def test_a_message_that_fits_goes_whole(js):
    raw = {
        "name": "Sample Ridge Vineyard & Cellars",
        "status": "Producing",
        "lat": "30.76468",
        "lon": "99.41073",
        "county": "Mason",
        "varieties": "Tempranillo 6, Mourvèdre 4, Viognier 2.5",
        "contact": "Jane Grower",
        "email": "jane@example.com",
        "consent": True,
        "note": "Second block planted in 2019.\nHappy to send photographs.",
    }
    mail, sent = built(js, raw)
    assert not sent["long"]
    _, fields = query(sent["url"])
    assert sorted(fields) == ["body", "subject"]
    assert fields["subject"] == [mail["subject"]]
    assert fields["body"] == [mail["body"]]
    assert "Point: 30.76468, -99.41073 (WGS 84, typed)" in mail["body"]
    assert (
        "Note: Second block planted in 2019.\r\nHappy to send" in mail["body"]
    )


def test_a_long_message_never_makes_a_long_url(js, page):
    # R1: every field at its maxlength, in letters that encode long (curly
    # apostrophes and è, 9 and 6 characters each); the URL stays within
    # LONG_URL and asks for the copied details instead.
    assert "export const LONG_URL = 1900;" in read(EMAIL)
    fill = "’è" * 400
    keys = {
        "v-name": "name",
        "v-business": "business",
        "v-website": "website",
        "v-road": "road",
        "v-directions": "directions",
        "v-acres": "acres",
        "v-year": "year",
        "v-varieties": "varieties",
        "v-contact": "contact",
        "v-email": "email",
        "v-note": "note",
    }
    raw = {keys[i]: fill[:n] for i, n in maxlengths(page).items() if i in keys}
    raw.update(status="Producing", county="Mason", consent=True)
    mail, sent = built(js, raw)
    assert sent["long"]
    assert len(sent["url"]) <= 1900, len(sent["url"])
    _, fields = query(sent["url"])
    assert fields["body"] == [
        "The vineyard details were copied from the form: paste them here."
    ]
    assert fields["subject"] == [sent["subject"]] == [mail["subject"]]
    assert fill[:600] in mail["body"]  # the copied text is whole


def test_an_emoji_is_never_cut_in_half(js):
    # R3: a name of 118 letters and a grape (two UTF-16 units) once split
    # the grape and stopped encodeURIComponent; and a longer one, set past
    # the box's maxlength.
    for name in ("a" * 118 + "\U0001f347", "\U0001f347" * 300):
        mail, sent = built(js, {"name": name, "consent": True})
        assert len(mail["subject"]) <= 140
        mail["subject"].encode("utf-8")  # no half of a pair left
        _, fields = query(sent["url"])
        assert fields["subject"] == [sent["subject"]]
    assert js("wellFormed", "a\ud800b\udc00") == "a�b�"
    mail, _ = built(js, {"note": "x\ud83c", "consent": True})
    assert "Note: x�" in mail["body"]


def test_nothing_typed_adds_a_header(js):
    name = "A & B?bcc=x@example.com\r\nBcc: y@example.com#cc=z@example.com"
    _, sent = built(js, {"name": name, "consent": True})
    rest, fields = query(sent["url"])
    assert sorted(fields) == ["body", "subject"]
    assert not re.search(r"[?#\r\n]", rest)
    assert rest.count("&") == 1
    subject = (
        "Vineyard submission: A & B?bcc=x@example.com Bcc: y@example.com"
        "#cc=z@example.com"
    )
    assert fields["subject"] == [subject]


def test_every_line_is_there_in_order(js):
    mail, _ = built(js, {})
    labels = [line.split(":")[0] for line in mail["body"].split("\r\n") if line]
    assert labels == [
        "Vineyard name",
        "Business name",
        "Status",
        "Website",
        "Point",
        "Nearest road",
        "How to find it",
        "County",
        "Acres planted",
        "Year first planted",
        "Varieties",
        "Sells grapes",
        "Makes wine",
        "Contact (for replies only, not to be published)",
        "Name",
        "Email",
        "Consent",
        "Note",
    ]
    assert "\n" not in mail["body"].replace("\r\n", "")
    assert "Consent: No" in mail["body"]


def test_points_as_people_type_them(js):
    d = js("normalize", {"lat": "30.764680° N", "lon": "99.410730° W"})
    assert (d["lat"], d["lon"]) == (30.76468, -99.41073)
    d = js("normalize", {"lat": "30.7647", "lon": "99.4107"})
    assert d["lon"] == -99.4107  # a positive longitude is west, here
    assert js("coordinate", "−99.4107") == -99.4107  # the hint's minus
    assert js("pair", "30.764680° N, 99.410730° W") == [
        "30.764680° N",
        "99.410730° W",
    ]
    assert js("pair", "30.76468, -99.41073") == ["30.76468", "-99.41073"]
    assert js("pair", "30.76468") is None


def test_an_empty_form_names_what_to_fix(js):
    found = js("problems", js("normalize", {}), 2026)
    assert [f[0] for f in found] == [
        "v-name",
        "v-status",
        "v-where",
        "v-county",
        "v-contact",
        "v-email",
        "v-consent",
    ]
    assert found[-1][1] == "Tick the box to give permission."
