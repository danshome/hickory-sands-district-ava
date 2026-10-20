"""src/site/make_site_meta.py: llms.txt, the pages' JSON-LD, security.txt.

Each committed file is what the generator makes from the site now; llms.txt
keeps the llms.txt proposal's structure (https://llmstxt.org/); every JSON-LD
block parses and names its page's canonical URL; security.txt has RFC 9116's
required fields and an Expires in the future; and the Pages workflow deploys
docs/.well-known/, the only dot-named path in docs/. Standard library only,
so the lint workflow runs these.
"""

import datetime
import html
import json
import os
import re
import shutil
import subprocess
import sys
import warnings

import pytest

from src.site import make_site_meta as msm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "docs")
NOW = datetime.datetime.now(datetime.UTC)
LD = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL
)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def pages():
    return sorted(n for n in os.listdir(SITE) if n.endswith(".html"))


def head_of(text):
    canon = re.search(r'<link rel="canonical" href="([^"]+)">', text)
    return {
        "canonical": canon.group(1) if canon else None,
        "noindex": msm.NOINDEX.search(text) is not None,
        "title": html.unescape(re.search(r"<title>(.*?)</title>", text)[1]),
        "description": html.unescape(
            re.search(r'<meta name="description" content="([^"]*)">', text)[1]
        ),
    }


def sitemap():
    return re.findall(r"<loc>([^<]+)</loc>", read(f"{SITE}/sitemap.xml"))


# --- every file current -------------------------------------------------------


def test_every_file_is_what_the_generator_makes():
    made = msm.outputs(SITE, msm.TEMPLATE, NOW)
    problems = [p for p in (msm.stale(k, v, NOW) for k, v in made.items()) if p]
    assert not problems, "run ./build.sh site-meta: " + "; ".join(problems)


def test_the_walk_page_and_its_template_carry_the_same_block():
    walk = msm.BLOCK.search(read(f"{SITE}/walk.html"))
    tpl = msm.BLOCK.search(read(msm.TEMPLATE))
    assert walk and tpl and walk.group(0) == tpl.group(0)


# --- llms.txt -----------------------------------------------------------------


def llms():
    return read(f"{SITE}/llms.txt")


def test_llms_txt_has_the_proposal_s_structure():
    lines = llms().split("\n")
    assert lines[0].startswith("# ") and lines[0][2:].strip()
    assert [x for x in lines if x.startswith("# ")] == [lines[0]]
    assert lines[2].startswith("> ")
    first_h2 = next(i for i, x in enumerate(lines) if x.startswith("## "))
    assert not any(x.startswith("#") for x in lines[1:first_h2])
    entry = re.compile(r"^- \[[^\]]+\]\(https://[^)\s]+\)(: .+)?$")
    for line in lines[first_h2:]:
        assert line == "" or line.startswith("## ") or entry.match(line), line


def test_llms_txt_says_what_the_home_page_says():
    home = head_of(read(f"{SITE}/index.html"))
    assert f"> {home['description']}\n" in llms()


def test_llms_txt_lists_every_indexed_page_in_the_sitemap_s_order():
    text = llms()
    pages_part = text.split("## Pages\n", 1)[1].split("\n## ", 1)[0]
    listed = re.findall(r"^- \[[^\]]+\]\(([^)]+)\)", pages_part, re.M)
    assert listed == sitemap()
    assert "logo-vote" not in text


def test_llms_txt_links_the_record_and_the_data():
    text = llms()
    assert "](https://www.federalregister.gov/d/2026-16670)" in text
    assert "](https://www.regulations.gov/docket/TTB-2026-0005)" in text
    for url in re.findall(
        r"\]\((https://hickorysandsdistrictava\.org/[^)]+)", text
    ):
        path = url.removeprefix("https://hickorysandsdistrictava.org/")
        assert os.path.isfile(os.path.join(SITE, path or "index.html")), url


def section(name):
    part = llms().split(f"## {name}\n", 1)[1].split("\n## ", 1)[0]
    return [x for x in part.split("\n") if x.startswith("- ")]


def test_llms_txt_s_record_is_the_pages_external_text_links():
    url = msm.Site(SITE).url
    want = []
    for name in ("status.html", "boundary.html"):
        for link in msm.external_links(read(f"{SITE}/{name}"), url):
            if link[0] not in [w[0] for w in want]:
                want.append(link)
    got = [
        re.match(r"^- \[([^\]]+)\]\(([^)]+)\)(?:: (.*))?$", x).groups()
        for x in section("The public record")
    ]
    assert [(u, n, o or "") for n, u, o in got] == want
    # The class may stand anywhere among the attributes.
    moved = (
        '<a href="https://example.org/x" rel="external" class="a text-link">'
        "X <small>PDF</small></a>"
    )
    assert msm.external_links(moved, url) == [
        ("https://example.org/x", "X", "PDF")
    ]


def test_llms_txt_s_data_lists_the_three_downloads():
    assert len(section("Data")) == 3


def test_llms_txt_words():
    assert "agreed" not in llms().lower()


# --- JSON-LD ------------------------------------------------------------------


@pytest.mark.parametrize("name", pages())
def test_json_ld_parses_and_names_its_page(name):
    text = read(os.path.join(SITE, name))
    head = head_of(text)
    blocks = LD.findall(text.split("</head>", 1)[0])
    if head["noindex"]:
        assert not blocks
        return
    assert len(blocks) == 1
    data = json.loads(blocks[0])
    assert data["@context"] == "https://schema.org"
    graph = data["@graph"]
    webpage = [n for n in graph if n["@type"] == "WebPage"]
    assert len(webpage) == 1
    assert webpage[0]["url"] == head["canonical"]
    assert webpage[0]["name"] == head["title"]
    assert webpage[0]["description"] == head["description"]
    sites = [n for n in graph if n["@type"] == "WebSite"]
    assert len(sites) == (1 if name == "index.html" else 0)
    for node in graph:
        if node["@type"] == "Dataset":
            assert node["url"] == head["canonical"]
            assert "(proposed)" in node["name"]
            assert "proposed" in node["description"]
            assert "creator" not in node  # The map names no one
            assert 50 <= len(node["description"]) <= 5000
            assert node["license"].startswith("https://creativecommons.org/")
            for d in node["distribution"]:
                rel = d["contentUrl"].removeprefix(msm_site_url())
                assert os.path.isfile(os.path.join(SITE, rel))
                assert f'href="{rel}"' in text  # linked from the page
        if node["@type"] == "Place":
            assert node["name"].endswith("(proposed)")
            assert node["description"] in html.unescape(text)


def msm_site_url():
    return msm.Site(SITE).url


def test_the_boundary_page_has_the_place_and_the_map_the_data():
    def types(name):
        block = LD.search(read(os.path.join(SITE, name)))
        return [n["@type"] for n in json.loads(block.group(1))["@graph"]]

    assert "Place" in types("boundary.html")
    assert types("map.html").count("Dataset") == 3


def test_a_block_cannot_close_its_script():
    block = msm.script_block({"x": "</script><b>& "})
    inner = LD.search(block).group(1)
    assert "<" not in inner and ">" not in inner and "&" not in inner
    assert json.loads(inner) == {"x": "</script><b>& "}


@pytest.mark.parametrize(
    "markers",
    [msm.START, msm.END, msm.START + msm.END + msm.START + msm.END],
    ids=["start only", "end only", "doubled"],
)
def test_unpaired_or_doubled_markers_stop(markers):
    page = f"<html><head>{markers}</head><body></body></html>"
    with pytest.raises(SystemExit, match="SITE-META"):
        msm.with_block(page, msm.script_block({"a": 1}), "p")


def test_with_block_replaces_and_removes():
    page = "<html><head><title>x</title></head><body></body></html>"
    once = msm.with_block(page, msm.script_block({"a": 1}), "p")
    assert msm.with_block(once, msm.script_block({"a": 1}), "p") == once
    assert msm.with_block(once, "", "p").replace("\n", "") == page


# --- security.txt -------------------------------------------------------------


def security():
    return read(os.path.join(SITE, ".well-known", "security.txt"))


def fields(text):
    out = {}
    for line in text.splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition(": ")
            out.setdefault(key, []).append(value)
    return out


def test_security_txt_has_rfc_9116_s_fields():
    f = fields(security())
    assert f["Contact"]
    for c in f["Contact"]:
        assert c.startswith(("https://", "mailto:"))
    assert len(f["Expires"]) == 1
    expires = msm.parse_expires(security())
    assert expires and NOW < expires <= NOW + datetime.timedelta(days=365)
    assert f["Canonical"] == [
        "https://hickorysandsdistrictava.org/.well-known/security.txt"
    ]
    assert f["Policy"][0].endswith("/blob/main/SECURITY.md")
    assert f["Preferred-Languages"] == ["en"]
    assert set(f) <= {
        "Contact", "Expires", "Canonical", "Policy", "Preferred-Languages"
    }  # fmt: skip


def test_security_txt_names_security_md_s_routes():
    report, email, _ = msm.security_routes()
    f = fields(security())
    assert f["Contact"] == [report, f"mailto:{email}"]


def test_security_txt_expires_soon_only_warns():
    # Time passing never fails a test or the build; the monthly workflow
    # (security-txt.yml) opens the issue instead.
    when = msm.parse_expires(security())
    warning = msm.expires_warning(when, NOW)
    if warning:
        warnings.warn(f"{warning}: run ./build.sh site-meta", stacklevel=1)


def test_stale_ignores_expires_but_not_a_contact(tmp_path):
    sec = tmp_path / ".well-known" / "security.txt"
    sec.parent.mkdir()
    want = security()
    later = re.sub(
        r"^Expires: .*$", "Expires: 2027-01-02T00:00:00Z", want, flags=re.M
    )
    sec.write_text(later, encoding="utf-8")
    now = datetime.datetime(2026, 12, 30, tzinfo=datetime.UTC)
    assert msm.stale(str(sec), want, now) is None
    past = datetime.datetime(2027, 3, 1, tzinfo=datetime.UTC)
    assert msm.stale(str(sec), want, past) is None  # passed: a warning only
    sec.write_text(later.replace("mailto:", "mailto:x"), encoding="utf-8")
    assert msm.stale(str(sec), want, now)


def test_expires_kept_while_far_and_renewed_when_near():
    now = datetime.datetime(2026, 10, 19, 15, 30, tzinfo=datetime.UTC)
    far = now + datetime.timedelta(days=200)
    assert msm.new_expires(far, now) == far
    near = now + datetime.timedelta(days=30)
    fresh = msm.new_expires(near, now)
    assert fresh == datetime.datetime(2027, 10, 14, tzinfo=datetime.UTC)
    assert msm.new_expires(None, now) == fresh
    too_far = now + datetime.timedelta(days=400)
    assert msm.new_expires(too_far, now) == fresh


def test_expires_errors_and_warnings():
    now = datetime.datetime(2026, 10, 19, tzinfo=datetime.UTC)
    day = datetime.timedelta(days=1)
    assert msm.expires_error(now + 10 * day, now) is None
    assert msm.expires_error(now - day, now) is None  # time is no error
    assert msm.expires_error(now + 400 * day, now)
    assert msm.expires_error(None, now)
    assert msm.expires_warning(now + 100 * day, now) is None
    assert msm.expires_warning(now + 10 * day, now)
    assert "passed" in msm.expires_warning(now - day, now)
    assert msm.parse_expires("Expires: 2027-01-01T00:00:00") is None  # no zone


def test_expires_check_fails_when_near_or_past(tmp_path, capsys):
    sec = tmp_path / ".well-known" / "security.txt"
    sec.parent.mkdir()
    sec.write_text("Expires: 2027-01-01T00:00:00Z\n", encoding="utf-8")
    at = datetime.datetime
    utc = datetime.UTC
    assert msm.expires_check(str(tmp_path), at(2026, 9, 1, tzinfo=utc), 0) == 0
    assert msm.expires_check(str(tmp_path), at(2026, 12, 1, tzinfo=utc), 0) == 1
    assert msm.expires_check(str(tmp_path), at(2027, 2, 1, tzinfo=utc), 0) == 1
    sec.write_text("Contact: mailto:a@b.c\n", encoding="utf-8")
    assert msm.expires_check(str(tmp_path), at(2026, 9, 1, tzinfo=utc), 0) == 1
    assert "site-meta" in capsys.readouterr().out


# --- what stops it ------------------------------------------------------------


def tiny_site(tmp_path, pages, locs):
    """A made-up site: {name: (canonical or None, robots or None)}."""
    for name, (canon, robots) in pages.items():
        tags = '<html lang="en"><head><title>T · S</title>'
        tags += '<meta name="description" content="D">'
        tags += '<meta property="og:site_name" content="S">'
        if canon:
            tags += f'<link rel="canonical" href="{canon}">'
        if robots:
            tags += f'<meta name="robots" content="{robots}">'
        (tmp_path / name).write_text(tags + "</head></html>", encoding="utf-8")
    urls = "".join(f"<url><loc>{u}</loc></url>" for u in locs)
    (tmp_path / "sitemap.xml").write_text(f"<urlset>{urls}</urlset>")
    return msm.Site(str(tmp_path))


HOME = "https://e.org/"


def test_a_page_neither_in_the_sitemap_nor_noindex_stops(tmp_path):
    site = tiny_site(
        tmp_path,
        {"index.html": (HOME, None), "a.html": (HOME + "a.html", None)},
        [HOME],
    )
    with pytest.raises(SystemExit, match=r"a\.html: neither in sitemap"):
        site.indexed()


def test_noindex_is_read_from_the_robots_content(tmp_path):
    site = tiny_site(
        tmp_path,
        {
            "index.html": (HOME, None),
            "a.html": (HOME + "a.html", "noindex, nofollow"),
            "b.html": (HOME + "b.html", "nofollow"),
        },
        [HOME, HOME + "b.html"],
    )
    assert site.pages["a.html"]["noindex"]
    assert not site.pages["b.html"]["noindex"]
    assert [n for n, _ in site.indexed()] == ["index.html", "b.html"]


@pytest.mark.parametrize(
    ("loc", "message"),
    [
        ("https://other.org/a.html", "is not on"),
        (HOME + "missing.html", "has no page"),
        (HOME + "b.html", "not a.html|not b.html"),
    ],
    ids=["off the site", "no page", "canonical mismatch"],
)
def test_a_bad_sitemap_url_stops(tmp_path, loc, message):
    site = tiny_site(
        tmp_path,
        {"index.html": (HOME, None), "b.html": (HOME + "a.html", None)},
        [HOME, loc],
    )
    with pytest.raises(SystemExit, match=message):
        site.indexed()


def test_need_and_a_missing_description_stop(tmp_path):
    with pytest.raises(SystemExit, match="no thing"):
        msm.need(None, str(tmp_path / "x"), "thing")
    page = tmp_path / "x.html"
    page.write_text('<html lang="en"><head><title>T</title></head>')
    with pytest.raises(SystemExit, match="no meta description"):
        msm.head(str(page))


def copy_site(tmp_path):
    """The parts of docs/ the generator reads, and the walk template."""
    docs = tmp_path / "docs"
    (docs / "data").mkdir(parents=True)
    for name in os.listdir(SITE):
        if name.endswith((".html", ".xml", ".txt")):
            shutil.copy(os.path.join(SITE, name), docs / name)
    shutil.copytree(os.path.join(SITE, ".well-known"), docs / ".well-known")
    shutil.copy(os.path.join(SITE, "data", "boundary.geojson"), docs / "data")
    tpl = tmp_path / "walk.template.html"
    shutil.copy(msm.TEMPLATE, tpl)
    return docs, tpl


def run_check(docs, tpl):
    return subprocess.run(
        [
            sys.executable, "-I", "-B",
            os.path.join(ROOT, "src", "site", "make_site_meta.py"),
            "--site", str(docs), "--template", str(tpl), "--check",
        ],
        capture_output=True,
        text=True,
        check=False,
    )  # fmt: skip


def test_the_check_passes_on_a_copy(tmp_path):
    result = run_check(*copy_site(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("which", ["llms", "page", "template"])
def test_the_check_exits_3_when_a_file_is_stale(tmp_path, which):
    docs, tpl = copy_site(tmp_path)
    path = {
        "llms": docs / "llms.txt",
        "page": docs / "boundary.html",
        "template": tpl,
    }[which]
    text = path.read_text(encoding="utf-8")
    edited = text.replace('"@type":"WebPage"', '"@type":"WebPage","x":1', 1)
    if which == "llms":
        edited = text + "- [Extra](https://e.org/)\n"
    assert edited != text
    path.write_text(edited, encoding="utf-8")
    result = run_check(docs, tpl)
    assert result.returncode == msm.STALE, result.stdout + result.stderr


def test_the_check_exits_1_on_a_broken_page(tmp_path):
    docs, tpl = copy_site(tmp_path)
    page = docs / "map.html"
    text = page.read_text(encoding="utf-8")
    page.write_text(text.replace('id="about-data"', 'id="x"'), encoding="utf-8")
    result = run_check(docs, tpl)
    assert result.returncode == 1
    assert "GeoJSON downloads" in result.stderr


def test_the_template_s_canonical_must_be_walk_s(tmp_path):
    docs, tpl = copy_site(tmp_path)
    text = tpl.read_text(encoding="utf-8")
    tpl.write_text(text.replace('/walk.html"', '/other.html"', 1))
    result = run_check(docs, tpl)
    assert result.returncode == 1
    assert "walk template" in result.stderr


# --- deployed -----------------------------------------------------------------


def test_well_known_is_the_only_dot_named_path_in_docs():
    found = []
    for folder, dirs, files in os.walk(SITE):
        for name in dirs + files:
            if name.startswith(".") and name != ".DS_Store":  # gitignored
                found.append(os.path.relpath(os.path.join(folder, name), SITE))
    assert found == [".well-known"]


def test_the_pages_workflow_deploys_dot_named_paths():
    text = read(os.path.join(ROOT, ".github", "workflows", "site.yml"))
    assert re.search(r"^\s+include-hidden-files: true$", text, re.M)


def test_a_monthly_workflow_reports_a_near_expires():
    text = read(os.path.join(ROOT, ".github", "workflows", "security-txt.yml"))
    assert "--expires-check --report" in text
    assert "issues: write" in text


@pytest.mark.parametrize(
    ("name", "mark", "message"),
    [
        ("boundary.html", "boundary-explanation", "boundary-explanation"),
        ("map.html", 'id="about-data"', "about-data"),
    ],
)
def test_json_ld_stops_without_the_place_or_the_data(name, mark, message):
    site = msm.Site(SITE)
    page = dict(site.pages[name])
    page["text"] = page["text"].replace(mark, "gone")
    with pytest.raises(SystemExit, match=message):
        msm.jsonld(site, name, page, "0 0 1 1")
