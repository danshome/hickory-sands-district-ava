"""The site's vineyard data is always loaded fresh (after a merge, at once).

GitHub Pages serves every file with cache-control: max-age=600. The
scripts' and stylesheets' URLs carry a version (src/site/stamp_assets.py,
#138); the vineyard data's (docs/assets/vineyards/) carry the data's stamp,
from its record.json, which docs/assets/vineyard-data.js fetches revalidated.
These check that every vineyard file the site's scripts load goes through
that helper (vineyardJson or vineyardUrl), so none is named by its plain,
cacheable URL; that the helper reads the record revalidated and falls back to
a revalidated fetch without it; and that the record's stamp is the data's.
Standard library only.
"""

import glob
import json
import os
import re

import pytest

from src.site import make_vineyards as mv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
VINES = os.path.join(DOCS, "assets", "vineyards")
HELPER = os.path.join(DOCS, "assets", "vineyard-data.js")
SCRIPTS = sorted(
    p
    for p in glob.glob(os.path.join(DOCS, "**", "*.js"), recursive=True)
    if os.path.abspath(p) != HELPER
)
PAGES = sorted(glob.glob(os.path.join(DOCS, "**", "*.html"), recursive=True))
# The vineyard data's files, but the record (which is fetched unstamped).
FILES = sorted(
    name
    for name in os.listdir(VINES)
    if name != "record.json" and os.path.isfile(os.path.join(VINES, name))
)
CALL = re.compile(r'vineyard(?:Json|Url)\("(?P<name>[^"]+)"\)')


def code_lines(path):
    """A script's lines but its whole-line comments, with their numbers."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    text = re.sub(
        r"/\*.*?\*/", lambda m: "\n" * m.group().count("\n"), text, flags=re.S
    )
    for number, line in enumerate(text.split("\n"), 1):
        if not line.lstrip().startswith("//"):
            yield number, line


def rel(path):
    return os.path.relpath(path, ROOT)


def test_there_is_vineyard_data_and_scripts_to_check():
    assert {"register.json", "known.json", "vineyards.geojson"} <= set(FILES)
    assert SCRIPTS


@pytest.mark.parametrize("path", SCRIPTS, ids=rel)
def test_only_the_helper_names_the_vineyard_folder(path):
    for number, line in code_lines(path):
        assert "vineyards/" not in line, (
            f"{rel(path)}:{number} names the vineyard data's folder; load "
            "its files through vineyard-data.js (vineyardJson, vineyardUrl)"
        )


@pytest.mark.parametrize("path", PAGES, ids=rel)
def test_no_page_names_the_vineyard_folder(path):
    with open(path, encoding="utf-8") as fh:
        assert "assets/vineyards/" not in fh.read(), rel(path)


@pytest.mark.parametrize("path", SCRIPTS, ids=rel)
def test_every_vineyard_file_goes_through_the_helper(path):
    for number, line in code_lines(path):
        bare = CALL.sub("", line)
        for name in FILES:
            for m in re.finditer(r"[\w.${}/-]*" + re.escape(name), bare):
                # The aquifer's own stats.json, after its DATA folder (which
                # cannot be the vineyards': only the helper names that).
                assert name == "stats.json" and m.group() == (
                    "${DATA}stats.json"
                ), (
                    f"{rel(path)}:{number} loads {name} without "
                    "vineyardJson or vineyardUrl (vineyard-data.js)"
                )
        for m in CALL.finditer(line):
            assert m["name"] in FILES, f"{rel(path)}:{number} {m['name']}"


def test_the_pages_that_read_vineyard_data_use_the_helper():
    used = {}
    for path in SCRIPTS:
        for _, line in code_lines(path):
            for m in CALL.finditer(line):
                used.setdefault(os.path.basename(path), set()).add(m["name"])
    assert used == {
        "map3d.js": {"stats.json", "vineyard-wells.json", "vineyards.geojson"},
        "vineyard-list.js": {"register.json", "vineyards.geojson"},
        "vineyard-wizard.js": {"counties.geojson", "known.json"},
    }
    for name in used:
        with open(os.path.join(DOCS, "assets", name), encoding="utf-8") as fh:
            assert re.search(
                r'from "\./vineyard-data\.js(?:\?v=[0-9a-f]+)?";', fh.read()
            ), name


def test_the_helper_reads_the_record_revalidated_and_falls_back():
    with open(HELPER, encoding="utf-8") as fh:
        text = fh.read()
    assert 'const FOLDER = "assets/vineyards/";' in text
    assert 'fetch(`${FOLDER}record.json`, { cache: "no-cache" })' in text
    # Without a stamp, the file is fetched revalidated, never from cache.
    assert '{ cache: "no-cache" }' in text.split("vineyardJson", 1)[1]
    assert "${FOLDER}${name}?v=${v}" in text
    # The stamp is checked before it is put in a URL.
    assert "STAMP.test(value)" in text
    assert "export async function vineyardUrl(name)" in text
    assert "export async function vineyardJson(name)" in text


def test_the_record_has_the_data_s_stamp():
    with open(os.path.join(VINES, "record.json"), encoding="utf-8") as fh:
        stamp = json.load(fh)["stamp"]
    assert re.fullmatch(r"[0-9a-f]{7}", stamp)
    assert stamp == mv.data_stamp(VINES)


def test_a_changed_file_changes_the_stamp(tmp_path):
    for name in FILES:
        with open(os.path.join(VINES, name), "rb") as src:
            (tmp_path / name).write_bytes(src.read())
    before = mv.data_stamp(str(tmp_path))
    assert before == mv.data_stamp(VINES)
    known = tmp_path / "known.json"
    known.write_bytes(known.read_bytes().replace(b"a", b"b", 1))
    assert mv.data_stamp(str(tmp_path)) != before
