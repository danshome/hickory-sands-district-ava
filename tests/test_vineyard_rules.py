"""The vineyard form's rules: the page's and the function's against Python's.

docs/assets/vineyard-blocks.js (which the page and the Supabase function
run) and src/vineyards/submission.py (which the repository's Actions run)
must give the same errors, facts, cleaned submission, title and public issue
for every fixture, hostile ones among them; the hostile ones are refused,
and the issue never holds the contact, the submission's id or anything that
could close a code fence or carry HTML. The JavaScript runs in node, when it
is installed (it is on GitHub's Linux runners); without it those tests are
skipped. Standard library only, so the lint workflow runs these.
"""

import copy
import json
import os
import shutil
import subprocess

import pytest

from src.vineyards import submission as vs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
MODULE = os.path.join(ROOT, "docs", "assets", "vineyard-blocks.js")
LLANO = os.path.join(ROOT, vs.LLANO)
DISTRICT = os.path.join(ROOT, vs.DISTRICT)
SENT = "2026-10-18T23:59:01.123Z"
# Runs every case through the module: parse, check, title, issue.
BRIDGE = """
import { pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";
const [path, llanoPath, districtPath] = process.argv.slice(1);
const m = await import(pathToFileURL(path));
const llano = m.makeArea(JSON.parse(readFileSync(llanoPath, "utf8")));
const district = m.makeArea(JSON.parse(readFileSync(districtPath, "utf8")));
let input = "";
for await (const chunk of process.stdin) input += chunk;
const out = [];
for (const [text, sent] of JSON.parse(input)) {
  try {
    const raw = m.parse(text);
    const r = m.check(raw, { llano, district, year: 2026 });
    out.push({ errors: r.errors, facts: r.facts, submission: r.submission,
      title: m.issueTitle(r.submission),
      body: m.issueBody(r.submission, sent) });
  } catch (error) {
    out.push({ invalid: error instanceof m.Invalid,
      message: String(error.message) });
  }
}
process.stdout.write(JSON.stringify(out));
"""

GOOD = {
    "form": "hsd-vineyard",
    "version": 1,
    "id": "3f2b8c1e-5d4a-4e6f-9a7b-1c2d3e4f5a6b",
    "vineyard": {
        "name": "Prairie Gap Vineyard",
        "county": "Mason",
        "planted": "planted",
        "acres": 4.5,
        "year": 2019,
        "varieties": ["Tempranillo", "Mourvèdre", "Lenoir"],
    },
    "blocks": [
        [
            [-99.295, 30.865],
            [-99.2925, 30.865],
            [-99.2925, 30.8632],
            [-99.295, 30.8632],
        ],
        [
            [-99.296, 30.8628],
            [-99.2945, 30.8628],
            [-99.2945, 30.8618],
            [-99.296, 30.8618],
        ],
    ],
    "pin": None,
    "contact": {
        "name": "Jane Q. Grower",
        "email": "jane@example.com",
        "phone": "325-555-0100",
    },
    "agree": {"public": True, "permission": True},
    "website": "",
}


def variant(**changes):
    """GOOD with changes; a__b names GOOD["a"]["b"]."""
    raw = copy.deepcopy(GOOD)
    for path, value in changes.items():
        keys = path.split("__")
        target = raw
        for k in keys[:-1]:
            target = target[k]
        target[keys[-1]] = value
    return raw


def district_corner():
    """A block around a vertex of the proposed district's line."""
    lon, lat = vs.area("district").rings[0][4000]
    d = 0.0015
    return [
        [lon - d, lat + d],
        [lon + d, lat + d],
        [lon + d, lat - d],
        [lon - d, lat - d],
    ]


B0 = GOOD["blocks"][0]
B1 = GOOD["blocks"][1]
FIXTURES = {
    "good": GOOD,
    "bow-tie": variant(
        blocks=[
            [
                [-99.295, 30.865],
                [-99.2925, 30.8632],
                [-99.2925, 30.865],
                [-99.295, 30.8632],
            ]
        ]
    ),
    "outside-llano": variant(
        blocks=[
            [[-97.75, 30.27], [-97.74, 30.27], [-97.74, 30.26], [-97.75, 30.26]]
        ]
    ),
    "straddles-district": variant(blocks=[district_corner()]),
    "overlap": variant(
        blocks=[B0, [[-99.294, 30.864], [-99.290, 30.864], [-99.290, 30.860]]]
    ),
    "two-corners": variant(blocks=[[[-99.295, 30.865], [-99.2925, 30.865]]]),
    "closed-ring-repeats": variant(blocks=[[*B0, B0[0]], [*B1, B1[3]]]),
    "tiny": variant(
        blocks=[[[-99.295, 30.865], [-99.29499, 30.865], [-99.29499, 30.86499]]]
    ),
    "huge": variant(
        blocks=[
            [[-99.32, 30.89], [-99.30, 30.89], [-99.30, 30.87], [-99.32, 30.87]]
        ]
    ),
    "too-many-corners": variant(
        blocks=[
            [[-99.3 + 0.001 * (i % 2), 30.86 + 0.0001 * i] for i in range(120)]
        ]
    ),
    "too-many-blocks": variant(blocks=[B0] * 21),
    "unreadable-block": variant(blocks=[[[-99.3, "x"], [-99.2, 30.8]]]),
    "pin-only-no-acres": variant(
        blocks=[], pin=[-99.294, 30.864], vineyard__acres=None
    ),
    "pin-only": variant(blocks=[], pin=[-99.294, 30.864]),
    "pin-outside": variant(blocks=[], pin=[-97.74, 30.27]),
    "pin-not-texas": variant(blocks=[], pin=[2.35, 48.85]),
    "nothing": variant(blocks=[]),
    "name-email": variant(vineyard__name="Call jane@example.com"),
    "name-web": variant(vineyard__name="Best vines at cheap-pills.ru"),
    "name-title": variant(vineyard__name="Dr. Smith Vineyard"),
    "name-html": variant(vineyard__name="<img src=x onerror=alert(1)>"),
    "name-backticks": variant(vineyard__name="```json Bad | name"),
    "name-mention": variant(vineyard__name="@danshome #12"),
    "name-bidi": variant(vineyard__name="Good\u202eVineyard\u200b  Name"),
    "name-long": variant(vineyard__name="V" * 81),
    "name-digits": variant(vineyard__name="Call 3255550100 now"),
    "name-paren-phone": variant(vineyard__name="Vines (325)5550100"),
    "name-slash-phone": variant(vineyard__name="Vines 325/555/0100"),
    "name-dan": variant(vineyard__name="Dan's Creek Vineyard"),
    "name-owner": variant(vineyard__name="The Owners Vineyard"),
    "name-drive": variant(vineyard__name="Mill Dr. Vineyard"),
    "name-year-ok": variant(vineyard__name="1900 Vineyard"),
    "name-ok-punctuation": variant(
        vineyard__name="Torr Na Lochs Vineyard & Winery (St. Joseph's)"
    ),
    "name-accents": variant(vineyard__name="Château Pérez Viñedo"),
    "name-empty": variant(vineyard__name="   "),
    "county": variant(vineyard__county="Travis"),
    "county-not-sure": variant(vineyard__county="Not sure"),
    "planted": variant(vineyard__planted="maybe"),
    "planted-list": variant(vineyard__planted=["planted"]),
    "acres-text": variant(vineyard__acres="12 acres"),
    "acres-zero": variant(vineyard__acres=0),
    "acres-list": variant(vineyard__acres=[1]),
    "acres-whole": variant(vineyard__acres=8.0),
    "year-old": variant(vineyard__year=1850),
    "year-ahead": variant(vineyard__year=2032),
    "year-float": variant(vineyard__year=2019.0),
    "year-bool": variant(vineyard__year=True),
    "variety-spam": variant(
        vineyard__varieties=["Tempranillo", "buy now at x.com", "`|@x"]
    ),
    "variety-dupes": variant(
        vineyard__varieties=["Syrah", " Syrah ", "Lenoir", "Lenoir"]
    ),
    "variety-too-many": variant(
        vineyard__varieties=list(vs.VARIETIES[:21]),
    ),
    "contact-bad": variant(
        contact={"name": "J4ne", "email": "jane@", "phone": "555-0100"}
    ),
    "contact-none": variant(contact={"name": "", "email": "", "phone": ""}),
    "phone-only": variant(
        contact={"name": "Jane", "email": "", "phone": "+1 (325) 555-0100"}
    ),
    "no-agree": variant(agree={"public": False, "permission": "yes"}),
    "planned": variant(vineyard__planted="planned"),
    # Hostile text in each public field: refused, so never posted.
    "name-backslash": variant(vineyard__name="Back\\slash Vineyard"),
    "name-backtick-run": variant(vineyard__name="Vines ```` and `` more"),
    "name-close-details": variant(vineyard__name="</details> Vineyard"),
    "name-at-mention": variant(vineyard__name="Vineyard of @danshome"),
    "name-issue-ref": variant(vineyard__name="Vineyard #123"),
    "name-html-bold": variant(vineyard__name="<b>Bold</b> Vineyard"),
    "name-md-link": variant(vineyard__name="[Vines](https://evil.example)"),
    "name-md-link-bare": variant(vineyard__name="[Vines](evil)"),
    "name-md-image": variant(vineyard__name="![x](x.png)"),
    "name-autolink": variant(vineyard__name="Vines <https://evil.example>"),
    "varieties-hostile": variant(
        vineyard__varieties=[
            "Syrah",
            "@danshome",
            "#123",
            "</details>",
            "a\\b",
            "``x``",
            "[x](y)",
            "<i>x</i>",
        ]
    ),
    "county-hostile": variant(vineyard__county="</details> @danshome"),
    # The limits, each side (#140's review): Texas's box for a point, a
    # point given the wrong way round or half given, the email, the acres
    # and the years.
    "pin-lat-24.9": variant(blocks=[], pin=[-99.294, 24.9]),
    "pin-lat-37.1": variant(blocks=[], pin=[-99.294, 37.1]),
    "pin-lon-92.9": variant(blocks=[], pin=[-92.9, 30.864]),
    "pin-lon-107.1": variant(blocks=[], pin=[-107.1, 30.864]),
    "pin-swapped": variant(blocks=[], pin=[30.864, -99.294]),
    "pin-one-number": variant(blocks=[], pin=[-99.294]),
    "pin-three-numbers": variant(blocks=[], pin=[-99.294, 30.864, 0]),
    "block-corner-lat-24.9": variant(
        blocks=[[[-99.295, 24.9], [-99.2925, 30.865], [-99.2925, 30.8632]]]
    ),
    "block-corner-swapped": variant(
        blocks=[[[30.865, -99.295], [-99.2925, 30.865], [-99.2925, 30.8632]]]
    ),
    "email-no-domain": variant(contact__email="jane@example"),
    "email-no-at": variant(contact__email="jane.example.com"),
    "email-two-at": variant(contact__email="jane@@example.com"),
    "acres-2000": variant(vineyard__acres=2000),
    "acres-2000.01": variant(vineyard__acres=2000.01),
    "acres-10001": variant(vineyard__acres=10001),
    "acres-negative": variant(vineyard__acres=-4),
    "year-1799": variant(vineyard__year=1799),
    "year-1899": variant(vineyard__year=1899),
    "year-1900": variant(vineyard__year=1900),
    "year-now+5": variant(vineyard__year=2031),
    "year-now+6": variant(vineyard__year=2032),
}
INVALID = {
    "trap": json.dumps(variant(website="http://spam")),
    "trap-list": json.dumps(variant(website=["x"])),
    "nan": json.dumps(GOOD).replace("-99.295", "NaN", 1),
    "not-json": "{",
    "array": "[]",
    "wrong-form": json.dumps(variant(form="other")),
    "wrong-version": json.dumps(variant(version=2)),
    "no-id": json.dumps({k: v for k, v in GOOD.items() if k != "id"}),
    "bad-id": json.dumps(variant(id="1; drop table")),
    "blocks-object": json.dumps(variant(blocks={"a": 1})),
    "varieties-object": json.dumps(variant(vineyard__varieties={"a": 1})),
    "oversize": json.dumps(variant(vineyard__name="x" * 70000)),
}


def python_side(text, sent):
    """What src/vineyards/submission.py makes of one case."""
    try:
        raw = vs.loads(text)
        sub, errors, facts = vs.check(raw, year=2026)
    except vs.SubmissionError as error:
        return {"invalid": True, "message": str(error)}
    return {
        "errors": errors,
        "facts": facts,
        "submission": json.loads(json.dumps(vs.js_numbers(sub))),
        "title": vs.issue_title(sub),
        "body": vs.issue_body(sub, sent),
    }


CASES = list(FIXTURES.items()) + list(INVALID.items())


@pytest.fixture(scope="module")
def results():
    if not NODE:
        pytest.skip("node is not installed")
    texts = [
        (v if isinstance(v, str) else json.dumps(v), SENT) for _, v in CASES
    ]
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", BRIDGE, MODULE, LLANO, DISTRICT],
        input=json.dumps(texts),
        capture_output=True,
        text=True,
        check=True,
    )
    js = json.loads(done.stdout)
    return {
        name: (python_side(text, sent), j)
        for (name, _), (text, sent), j in zip(CASES, texts, js, strict=True)
    }


@pytest.mark.parametrize("name", [n for n, _ in CASES])
def test_the_page_the_function_and_the_actions_agree(results, name):
    py, js = results[name]
    if "invalid" in py or "invalid" in js:
        assert py.get("invalid"), py
        assert js.get("invalid"), js
        return
    assert py["errors"] == js["errors"]
    assert py["facts"] == js["facts"]
    assert py["submission"] == js["submission"]
    assert py["title"] == js["title"]
    assert py["body"] == js["body"]


def fields(name):
    return [
        e[0] for e in python_side(json.dumps(FIXTURES[name]), SENT)["errors"]
    ]


def test_each_rule_names_its_field():
    assert fields("good") == []
    assert fields("bow-tie") == ["block-1"]
    assert fields("outside-llano") == ["block-1"]
    assert fields("straddles-district") == []
    assert fields("overlap") == ["block-2"]
    assert fields("two-corners") == ["block-1"]
    assert fields("closed-ring-repeats") == []
    assert fields("tiny") == ["block-1"]
    assert fields("huge") == ["block-1"]
    assert fields("too-many-corners") == ["block-1"]
    assert fields("too-many-blocks")[0] == "blocks"
    assert fields("unreadable-block") == ["block-1"]
    assert fields("pin-only-no-acres") == ["acres"]
    assert fields("pin-only") == []
    assert fields("pin-outside") == ["pin"]
    assert fields("pin-not-texas") == ["pin"]
    assert fields("nothing") == ["where"]
    for name in (
        "name-email",
        "name-web",
        "name-title",
        "name-html",
        "name-backticks",
        "name-mention",
        "name-long",
        "name-digits",
        "name-paren-phone",
        "name-slash-phone",
        "name-dan",
        "name-owner",
        "name-drive",
        "name-empty",
    ):
        assert fields(name) == ["name"], name
    for name in ("name-year-ok", "name-ok-punctuation", "name-accents"):
        assert fields(name) == [], name
    assert fields("county") == ["county"]
    assert fields("county-not-sure") == []
    assert fields("planted") == ["planted"]
    assert fields("planted-list") == ["planted"]
    assert fields("acres-text") == ["acres"]
    assert fields("acres-zero") == ["acres"]
    assert fields("acres-list") == ["acres"]
    assert fields("year-old") == ["year"]
    assert fields("year-ahead") == ["year"]
    assert fields("year-float") == []
    assert fields("year-bool") == ["year"]
    assert fields("variety-spam") == ["varieties", "varieties"]
    assert fields("variety-too-many") == ["varieties"]
    assert fields("contact-bad") == [
        "contact-name",
        "contact-email",
        "contact-phone",
    ]
    assert fields("contact-none") == ["contact-name", "contact-email"]
    assert fields("phone-only") == []
    assert fields("no-agree") == ["agree-permission", "agree-public"]


def test_a_whole_valid_submission_has_no_problem():
    py = python_side(json.dumps(GOOD), SENT)
    assert py["errors"] == []
    assert [f["district"] for f in py["facts"]] == ["in", "in"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("pin-lat-24.9", ["pin"]),
        ("pin-lat-37.1", ["pin"]),
        ("pin-lon-92.9", ["pin"]),
        ("pin-lon-107.1", ["pin"]),
        ("pin-swapped", ["pin"]),
        ("pin-one-number", ["pin"]),
        ("pin-three-numbers", ["pin"]),
        ("block-corner-lat-24.9", ["block-1"]),
        ("block-corner-swapped", ["block-1"]),
        ("email-no-domain", ["contact-email"]),
        ("email-no-at", ["contact-email"]),
        ("email-two-at", ["contact-email"]),
        ("acres-2000", []),
        ("acres-2000.01", ["acres"]),
        ("acres-10001", ["acres"]),
        ("acres-negative", ["acres"]),
        ("acres-text", ["acres"]),
        ("year-1799", ["year"]),
        ("year-1899", ["year"]),
        ("year-1900", []),
        ("year-now+5", []),
        ("year-now+6", ["year"]),
    ],
)
def test_each_limit_on_each_side(name, expected):
    assert fields(name) == expected


def test_messages_say_how_to_fix_it():
    def first(name):
        return python_side(json.dumps(FIXTURES[name]), SENT)["errors"][0][1]

    assert "phone numbers" in first("name-digits")
    assert "Drive" in first("name-drive")
    assert "wording" in first("name-dan")
    assert "Llano Uplift" in first("outside-llano")
    assert "cross" in first("bow-tie")


def test_text_is_cleaned_and_kept():
    sub = python_side(json.dumps(FIXTURES["name-bidi"]), SENT)["submission"]
    assert sub["vineyard"]["name"] == "GoodVineyard Name"
    sub = python_side(json.dumps(FIXTURES["variety-dupes"]), SENT)["submission"]
    assert sub["vineyard"]["varieties"] == ["Syrah", "Lenoir"]
    sub = python_side(json.dumps(FIXTURES["phone-only"]), SENT)["submission"]
    assert sub["contact"]["phone"] == "(325) 555-0100"
    facts = python_side(json.dumps(FIXTURES["straddles-district"]), SENT)
    assert facts["facts"][0]["district"] == "both"


@pytest.mark.parametrize("name", list(FIXTURES))
def test_the_issue_holds_no_contact_and_no_live_markup(name):
    py = python_side(json.dumps(FIXTURES[name]), SENT)
    if py["errors"]:
        return  # the function posts only a submission without errors
    body = py["body"]
    assert "jane@example.com" not in body
    assert "Jane" not in body
    assert "555" not in body.split("```json")[0]
    assert GOOD["id"] not in body  # the submission's id stays in the table
    assert py["title"].startswith("Vineyard submission")
    # one fence opens and closes each block: nothing typed can end one
    assert body.count("```") == 4
    data = body.split("```json\n")[1].split("\n```")[0]
    assert "<" not in data
    assert "`" not in data
    back = vs.parse_issue(body)
    assert back["vineyard"] == py["submission"]["vineyard"]
    assert "contact" not in back
    assert "id" not in back


def test_a_body_not_in_the_layout_is_refused():
    for body in ("", "hello", vs.MARK, f"{vs.MARK}\n```json\n[]\n```"):
        with pytest.raises(vs.SubmissionError):
            vs.parse_issue(body)
    good = vs.issue_body(vs.check(GOOD, year=2026)[0], SENT)
    twice = good + good.split("<details>")[1]
    with pytest.raises(vs.SubmissionError):
        vs.parse_issue(twice)


HOSTILE_FIXTURES = (
    "name-backslash",
    "name-backtick-run",
    "name-close-details",
    "name-at-mention",
    "name-issue-ref",
    "name-html-bold",
    "name-md-link",
    "name-md-link-bare",
    "name-md-image",
    "name-autolink",
    "varieties-hostile",
    "county-hostile",
)
# What a cell of the issue's table is given, were the rules ever to let
# it through: each must stay one inert code span.
HOSTILE = (
    "a\\b|c`d",
    "```` fence `` run",
    "</details><script>alert(1)</script>",
    "@danshome and #123 and GH-1",
    "[link](https://evil.example) ![img](x.png)",
    "\\` \\| \\\\",
)
CODE_BRIDGE = (
    'import { pathToFileURL } from "node:url";'
    "const m = await import(pathToFileURL(process.argv[1]));"
    'let input = "";'
    "for await (const chunk of process.stdin) input += chunk;"
    "process.stdout.write(JSON.stringify(JSON.parse(input).map(m.code)));"
)


@pytest.mark.parametrize("name", HOSTILE_FIXTURES)
def test_hostile_text_is_refused_where_it_is_typed(name):
    field = name.split("-")[0]
    errors = fields(name)
    assert errors, name
    assert set(errors) == {field}, (name, errors)


def test_a_cell_is_one_inert_code_span_in_both():
    # No @mention, #reference, link, image, HTML or fence can act inside
    # a code span; nothing can end the span or the table's cell early.
    if not NODE:
        pytest.skip("node is not installed")
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", CODE_BRIDGE, MODULE],
        input=json.dumps(HOSTILE),
        capture_output=True,
        text=True,
        check=True,
    )
    js = json.loads(done.stdout)
    for text, cell in zip(HOSTILE, js, strict=True):
        assert vs.code(text) == cell, text
        inner = cell[1:-1]
        assert cell.startswith("`") and cell.endswith("`"), cell
        assert "`" not in inner, cell
        assert "\\" not in inner, cell
        assert "|" not in inner, cell


def test_a_table_cell_holds_no_escape_or_fence():
    # Public text refuses these characters already; the cell is safe anyway.
    assert vs.code("a\\b|c`d") == "`a\u2216b\uff5cc\u02cbd`"
    assert vs.code("  ") == "_not given_"
