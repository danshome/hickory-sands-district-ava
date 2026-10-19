"""The version stamps on the site's scripts and stylesheets (#138).

src/site/stamp_assets.py gives each local script and stylesheet a page loads,
and each of the site's own modules a script imports, a short hash of the file
(assets/timeline.js?v=3f2a91c), so a changed file gets a new URL. These check,
on a made-up site: what is stamped and what is left alone; that a stamp is the
hash of the file as served, a module's taken after its own imports are
stamped, so a change reaches every importer and page; that running it again
changes nothing; that --check writes nothing and exits 3; and its refusals.
tests/test_site.py checks the real site's stamps. Standard library only, so
the lint workflow runs these.
"""

import hashlib
import os

import pytest

from src.site import stamp_assets as sa

INDEX = (
    "<!doctype html><head>"
    '<link rel="icon" href="assets/mark.svg">'
    '<link href="https://fonts.example/css2?family=X" rel="stylesheet">'
    '<link rel="stylesheet" href="assets/site.css">'
    '<script type="module" src="https://cdn.example/sdk/"></script>'
    '<script type="module" src="assets/app.js"></script>'
    "</head><body><p>assets/site.css in a sentence</p></body>"
)
FILES = {
    "docs/index.html": INDEX,
    "docs/404.html": '<link rel="stylesheet" href="/assets/site.css">',
    "docs/assets/site.css": "body{color:#111}\n",
    "docs/assets/mark.svg": "<svg/>\n",
    "docs/assets/app.js": (
        'import { key } from "./config.js";\n'
        'const LATER = "./lazy.js"; // import(LATER) when asked\n'
    ),
    "docs/assets/other.js": "import { key } from './config.js';\n",
    "docs/assets/config.js": 'export const key = "";\n',
    "docs/assets/lazy.js": "export const later = 1;\n",
    "src/walk.template.html": '<script src="assets/app.js" defer></script>',
}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()[: sa.DIGITS]


@pytest.fixture
def site(tmp_path):
    """A made-up site, docs/, and a template elsewhere; returns their paths."""
    for name, text in FILES.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path / "docs", tmp_path / "src" / "walk.template.html"


def stamp(site, *more):
    docs, template = site
    return sa.main(["--site", str(docs), "--template", str(template), *more])


def text(site, name):
    return (site[0] / name).read_text(encoding="utf-8")


def test_stamps_each_local_script_and_stylesheet_only(site):
    assert stamp(site) == 0
    config = sha(FILES["docs/assets/config.js"])
    lazy = sha(FILES["docs/assets/lazy.js"])
    app = (
        f'import {{ key }} from "./config.js?v={config}";\n'
        f'const LATER = "./lazy.js?v={lazy}"; // import(LATER) when asked\n'
    )
    assert text(site, "assets/app.js") == app
    css = sha(FILES["docs/assets/site.css"])
    page = text(site, "index.html")
    assert f'href="assets/site.css?v={css}"' in page
    assert f'src="assets/app.js?v={sha(app)}"' in page
    for kept in (
        'href="assets/mark.svg"',
        "https://fonts.example/css2?family=X",
        "https://cdn.example/sdk/",
        "assets/site.css in a sentence",
    ):
        assert kept in page
    assert text(site, "404.html") == (
        f'<link rel="stylesheet" href="/assets/site.css?v={css}">'
    )
    assert site[1].read_text(encoding="utf-8") == (
        f'<script src="assets/app.js?v={sha(app)}" defer></script>'
    )


def test_every_importer_names_a_module_alike(site):
    stamp(site)
    config = sha(FILES["docs/assets/config.js"])
    assert f"'./config.js?v={config}'" in text(site, "assets/other.js")
    assert f'"./config.js?v={config}"' in text(site, "assets/app.js")


def test_running_it_again_changes_nothing(site, capsys):
    stamp(site)
    before = {p: p.read_bytes() for p in site[0].rglob("*") if p.is_file()}
    assert stamp(site) == 0
    after = {p: p.read_bytes() for p in site[0].rglob("*") if p.is_file()}
    assert after == before
    assert stamp(site, "--check") == 0
    assert "every script and stylesheet is stamped" in capsys.readouterr().out


def test_check_writes_nothing_and_names_each_stale_stamp(site, capsys):
    assert stamp(site, "--check") == sa.STALE
    out = capsys.readouterr().out
    assert "index.html: assets/site.css should be assets/site.css?v=" in out
    assert "./config.js should be ./config.js?v=" in out
    assert "./build.sh stamp" in out
    assert text(site, "index.html") == INDEX


def test_a_changed_module_reaches_its_importers_and_the_pages(site):
    stamp(site)
    page = text(site, "index.html")
    (site[0] / "assets" / "config.js").write_text('export const key = "k";\n')
    assert stamp(site, "--check") == sa.STALE
    stamp(site)
    assert "./config.js?v=" + sha('export const key = "k";\n') in text(
        site, "assets/app.js"
    )
    changed = text(site, "index.html")
    css = sha(FILES["docs/assets/site.css"])
    assert f"assets/site.css?v={css}" in changed  # untouched: same stamp
    assert changed != page  # app.js's stamp moved with config.js
    app = sha(text(site, "assets/app.js"))
    assert f'src="assets/app.js?v={app}"' in changed


def test_a_stale_or_conflicting_stamp_is_replaced(site):
    page = INDEX.replace('="assets/site.css"', '="assets/site.css?v=0000000"')
    (site[0] / "index.html").write_text(page, encoding="utf-8")
    stamp(site)
    css = sha(FILES["docs/assets/site.css"])
    assert f'href="assets/site.css?v={css}"' in text(site, "index.html")
    assert "0000000" not in text(site, "index.html")


def test_single_quotes_are_kept(site):
    (site[0] / "index.html").write_text(
        "<link rel='stylesheet' href='assets/site.css'>", encoding="utf-8"
    )
    stamp(site)
    css = sha(FILES["docs/assets/site.css"])
    assert text(site, "index.html") == (
        f"<link rel='stylesheet' href='assets/site.css?v={css}'>"
    )


@pytest.mark.parametrize(
    "tag",
    [
        # rel without quotes (#153's review): read as HTML reads it
        '<link rel=stylesheet href="assets/site.css">',
        # a ">" inside a quoted value before the href
        '<link data-x="a>b" rel="stylesheet" href="assets/site.css">',
        '<link rel="Preload StyleSheet" as="style" href="assets/site.css">',
    ],
)
def test_a_link_is_read_as_html_reads_it(site, tag):
    (site[0] / "index.html").write_text(tag, encoding="utf-8")
    assert stamp(site, "--check") == sa.STALE  # not skipped
    stamp(site)
    css = sha(FILES["docs/assets/site.css"])
    assert text(site, "index.html") == tag.replace(
        "assets/site.css", f"assets/site.css?v={css}"
    )
    assert stamp(site, "--check") == 0


def test_a_modulepreload_names_the_module_as_the_imports_do(site):
    page = '<link rel="modulepreload" href="assets/config.js">'
    (site[0] / "index.html").write_text(page, encoding="utf-8")
    assert stamp(site, "--check") == sa.STALE
    stamp(site)
    config = sha(FILES["docs/assets/config.js"])
    assert f'href="assets/config.js?v={config}"' in text(site, "index.html")
    assert f'"./config.js?v={config}"' in text(site, "assets/app.js")


# Inline scripts that name a module: not stamped, so refused.
INLINE_IMPORT = (
    '<script type="module">import { key } from "./assets/config.js";</script>'
)
INLINE_DYNAMIC = "<script type=\"module\">import('./assets/lazy.js');</script>"
INLINE_MAP = (
    '<script type="importmap">{"imports": {"c": "./assets/config.js"}}</script>'
)


@pytest.mark.parametrize(
    ("tag", "error"),
    [
        ('<script src="assets/gone.js"></script>', "not a file"),
        ('<link rel="stylesheet" href="assets/site.css?x=1">', "only its"),
        ('<link rel="stylesheet" href="assets/site.css?v=G1">', "only its"),
        ('<link rel="stylesheet" href="assets/site.css#x">', "only its"),
        ('<link rel="stylesheet" href="../outside.css">', "not a file"),
        ("<script src=assets/app.js></script>", "quote the src"),
        ("<link rel=stylesheet href=assets/site.css>", "quote the href"),
        (
            '<link rel="stylesheet" href="assets/site.css" href="x.css">',
            "one href",
        ),
        (INLINE_IMPORT, "inline <script> names a module"),
        (INLINE_DYNAMIC, "inline <script> names a module"),
        (INLINE_MAP, "inline <script> names a module"),
    ],
)
def test_refuses_what_it_cannot_stamp(site, tag, error):
    (site[0] / "index.html").write_text(tag, encoding="utf-8")
    with pytest.raises(SystemExit, match=error):
        stamp(site, "--check")


@pytest.mark.parametrize(
    ("script", "error"),
    [
        ("const lazy = import(`./lazy.js`);\n", "cannot stamp import"),
        ('import { key } from "/assets/config.js";\n', "cannot stamp import"),
        ('import { key } from "assets/config.js";\n', "cannot stamp import"),
        ('import { key } from "config.js";\n', "cannot stamp import"),
        ('import "./config.js?v=G1";\n', "cannot stamp import"),
        ('const c = "./config.js?x=1";\n', "cannot stamp"),
        ("const c = `./${name}.js`;\n", "cannot stamp"),
        ('const lazy = import("/assets/lazy.js");\n', "cannot stamp import"),
        ("const lazy = import(WHERE);\n", r"cannot stamp import\(WHERE\)"),
        ("const lazy = import(base + name);\n", "cannot stamp import"),
    ],
)
def test_refuses_an_import_it_cannot_stamp(site, script, error):
    (site[0] / "assets" / "other.js").write_text(script, encoding="utf-8")
    with pytest.raises(SystemExit, match=error):
        stamp(site, "--check")


def test_esri_s_sdk_is_imported_as_it_is(site):
    script = (
        'import "https://js.arcgis.com/5.1/";\n'
        'import Map from "@arcgis/core/Map.js";\n'
        "const load = (n) => $arcgis.import(`@arcgis/core/${n}.js`);\n"
        'const [Graphic] = await $arcgis.import(["@arcgis/core/Graphic.js"]);\n'
        'const later = import("@arcgis/core/Camera.js");\n'
    )
    (site[0] / "assets" / "other.js").write_text(script, encoding="utf-8")
    stamp(site)
    assert text(site, "assets/other.js") == script


def test_refuses_a_stylesheet_that_imports_another(site):
    (site[0] / "assets" / "site.css").write_text('@import "more.css";\n')
    with pytest.raises(SystemExit, match="@import is not stamped"):
        stamp(site, "--check")


def test_refuses_a_missing_module(site):
    (site[0] / "assets" / "lazy.js").unlink()
    with pytest.raises(SystemExit, match=r"lazy\.js is not a module"):
        stamp(site, "--check")


def test_refuses_modules_that_import_in_a_circle(site):
    (site[0] / "assets" / "config.js").write_text('import "./app.js";\n')
    with pytest.raises(SystemExit, match=r"in a circle: .*app\.js"):
        stamp(site, "--check")


def test_refuses_a_site_that_is_not_there(tmp_path):
    with pytest.raises(SystemExit, match="not a folder"):
        sa.main(["--site", str(tmp_path / "gone"), "--check"])
    (tmp_path / "empty" / "assets").mkdir(parents=True)
    (tmp_path / "empty" / "assets" / "a.js").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="no pages"):
        sa.main(["--site", str(tmp_path / "empty"), "--check"])


def test_refuses_a_missing_template(site, tmp_path):
    gone = str(tmp_path / "gone.template.html")
    with pytest.raises(SystemExit, match="no such template"):
        sa.main(["--site", str(site[0]), "--template", gone, "--check"])


def test_unstamped_and_without_stamps():
    assert sa.unstamped("assets/a.js?v=3f2a91c") == "assets/a.js"
    assert sa.unstamped("assets/a.js") == "assets/a.js"
    assert sa.without_stamps("src=\"a.js?v=3f2a91c\" from './b.js?v=1'") == (
        "src=\"a.js\" from './b.js'"
    )


def test_the_template_is_read_as_if_in_the_site(site):
    stamp(site)
    rel = os.path.relpath(site[1], site[0].parent)
    assert rel == os.path.join("src", "walk.template.html")
    assert "assets/app.js?v=" in site[1].read_text(encoding="utf-8")
