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
        "noindex": '<meta name="robots"' in text,
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


def test_expires_check_fails_only_when_passed_or_too_far():
    now = datetime.datetime(2026, 10, 19, tzinfo=datetime.UTC)
    assert msm.expires_problem(now + datetime.timedelta(days=10), now) is None
    assert msm.expires_problem(now - datetime.timedelta(days=1), now)
    assert msm.expires_problem(now + datetime.timedelta(days=400), now)
    assert msm.expires_problem(None, now)
    assert msm.parse_expires("Expires: 2027-01-01T00:00:00") is None  # no zone


# --- deployed -----------------------------------------------------------------


def test_well_known_is_the_only_dot_named_path_in_docs():
    found = []
    for folder, dirs, files in os.walk(SITE):
        for name in dirs + files:
            if name.startswith("."):
                found.append(os.path.relpath(os.path.join(folder, name), SITE))
    assert found == [".well-known"]


def test_the_pages_workflow_deploys_dot_named_paths():
    text = read(os.path.join(ROOT, ".github", "workflows", "site.yml"))
    assert re.search(r"^\s+include-hidden-files: true$", text, re.M)
