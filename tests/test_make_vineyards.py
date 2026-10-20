"""The website's vineyard data (docs/assets/vineyards/), made apart.

src/site/make_vineyards.py makes it from committed files only: the vineyard
file, the 3D page's well tiles and its county lines. These check that the
committed data is up to date with its record (the build's check); that made
again here, every file is byte for byte the committed one (so the wells near
each block come from the tiles exactly); that the counties are seven closed
polygons and the register one entry per vineyard; that the 3D aquifer page no
longer depends on the vineyards (its record lists none); and, on made-up
files, what the check calls stale. Standard library only.
"""

from html.parser import HTMLParser
import json
import os
import re
import shutil

import pytest

from src.site import make_vineyards as mv
from src.site.aquifer import record
from src.site.aquifer import vineyards

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, mv.OUT)


def load(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as fh:
        return json.load(fh)


def test_the_committed_data_is_up_to_date():
    assert mv.stale_reasons(ROOT) == [], "run ./build.sh site-data"
    assert mv.main(["--check"]) == 0


def test_made_again_it_is_the_same_bytes(tmp_path):
    words = record.private_words()
    figures = vineyards.write(mv.paths(ROOT), str(tmp_path), words)
    record.write_json(
        os.path.join(tmp_path, "stats.json"), mv.stats(figures), indent=1
    )
    for name in sorted(os.listdir(tmp_path)):
        with (
            open(tmp_path / name, "rb") as new,
            open(os.path.join(OUT, name), "rb") as old,
        ):
            assert new.read() == old.read(), name
    assert set(os.listdir(tmp_path)) | {"record.json"} == set(os.listdir(OUT))


def test_the_counties_and_the_register():
    counties = load("counties.geojson")["features"]
    assert [f["properties"]["name"] for f in counties] == list(
        vineyards.COUNTIES
    )
    for f in counties:
        ring = f["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1]
        assert len(ring) >= 4
    register = load("register.json")["vineyards"]
    blocks = load("vineyards.geojson")["features"]
    assert sorted(v for e in register for v in e["vids"]) == sorted(
        f["properties"]["vid"] for f in blocks
    )
    names = {
        (f["properties"]["category"], f["properties"]["name"]) for f in blocks
    }
    assert len(register) == len(names)
    stats = load("stats.json")["figures"]
    for key, _ in vineyards.CATEGORIES:
        name = key.replace("-", "_")
        assert stats[f"vineyards_{name}_names"] == sum(
            1 for e in register if e["category"] == key
        )


def test_each_vineyard_has_one_stable_id_and_its_known_entry():
    register = load("register.json")["vineyards"]
    blocks = load("vineyards.geojson")["features"]
    known = load("known.json")
    ids = [e["id"] for e in register]
    assert len(ids) == len(set(ids))
    assert set(ids) == set(known)
    for e in register:
        assert vineyards.ID.fullmatch(e["id"]), e["id"]
        mine = [f for f in blocks if f["properties"]["vineyard_id"] == e["id"]]
        assert sorted(f["properties"]["vid"] for f in mine) == sorted(e["vids"])
        assert {f["properties"]["name"] for f in mine} == {e["name"]}
        k = known[e["id"]]
        assert (k["name"], k["category"]) == (e["name"], e["category"])
        assert len(k["blocks"]) == len(e["vids"])
        for ring, f in zip(k["blocks"], mine, strict=True):
            assert [*ring, ring[0]] == f["geometry"]["coordinates"][0]


def test_a_block_without_its_id_or_sharing_another_s_stops_the_run():
    with open(
        os.path.join(ROOT, mv.INPUTS["vineyards"]), encoding="utf-8"
    ) as fh:
        source = json.load(fh)["features"]
    assert vineyards.vineyard_ids(source)
    for bad in (None, "", "Blackmon", "a--b", "-a", "x" * 81, "a\n"):
        broken = json.loads(json.dumps(source))
        broken[0]["properties"]["vineyard_id"] = bad
        with pytest.raises(SystemExit, match="vineyard_id"):
            vineyards.vineyard_ids(broken)
    twin = json.loads(json.dumps(source))
    twin[0]["properties"]["vineyard_id"] = twin[-1]["properties"]["vineyard_id"]
    with pytest.raises(SystemExit, match="another name"):
        vineyards.vineyard_ids(twin)
    assert vineyards.slug("Torr Na Lochs Vineyard & Winery") == (
        "torr-na-lochs-vineyard-winery"
    )
    assert vineyards.slug("Château Pérez") == "chateau-perez"
    assert vineyards.slug("!!!") == "vineyard"


def test_the_aquifer_data_no_longer_needs_the_vineyards():
    assert "vineyards" not in record.LOCAL
    params = record.parameters()
    assert not [k for k in params if k.startswith("vineyard")]
    aquifer = record.read_record(record.OUT)
    assert "vineyards.geojson" not in aquifer["outputs"]
    assert "vineyard-wells.json" not in aquifer["outputs"]


def test_a_changed_vineyard_file_or_tile_is_stale(tmp_path):
    for rel in (*mv.INPUTS.values(), mv.OUT, mv.PAGE):
        src = os.path.join(ROOT, rel)
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy(src, dst)
    assert mv.stale_reasons(str(tmp_path)) == []
    with open(tmp_path / mv.INPUTS["vineyards"], "a", encoding="utf-8") as fh:
        fh.write(" ")
    assert mv.stale_reasons(str(tmp_path)) == ["local vineyards"]
    tile = sorted((tmp_path / mv.INPUTS["wells"]).glob("draw-*.json"))[0]
    tile.write_text(tile.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert mv.stale_reasons(str(tmp_path)) == ["local vineyards", "local wells"]
    os.remove(tmp_path / mv.OUT / "counties.geojson")
    assert "counties.geojson is missing" in mv.stale_reasons(str(tmp_path))
    assert mv.main(["--check", "--root", str(tmp_path)]) == mv.STALE


# ---- the page's list, readable without JavaScript (#171) -------------------


class ListText(HTMLParser):
    """The text of #vy-list's names, headings and change links."""

    def __init__(self):
        super().__init__()
        self.depth = 0  # inside #vy-list: the open elements' count
        self.cls = None
        self.names = []
        self.headings = []
        self.links = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.depth:
            self.depth += 1
            self.cls = attrs.get("class")
            if tag == "a":
                self.links.append(attrs.get("href"))
        elif attrs.get("id") == "vy-list":
            self.depth = 1

    def handle_endtag(self, tag):
        if self.depth:
            self.depth -= 1
            self.cls = None

    def handle_data(self, data):
        if not self.depth:
            return
        self.text.append(data)
        if self.cls == "vy-name":
            self.names.append(data)
        elif self.cls == "vy-heading":
            self.headings.append(data)


def page_text():
    with open(os.path.join(ROOT, mv.PAGE), encoding="utf-8") as fh:
        return fh.read()


def test_the_page_lists_every_vineyard_without_javascript():
    entries = load("register.json")["vineyards"]
    parsed = ListText()
    parsed.feed(page_text())
    assert parsed.names == [e["name"] for e in entries]
    shown = {e["category"] for e in entries}
    assert parsed.headings == [h for c, h in mv.GROUPS if c in shown]
    assert parsed.links == [f"#change={e['id']}" for e in entries]
    text = "".join(parsed.text)
    assert "JavaScript" not in text
    for e in entries:
        n = len(e["vids"])
        assert f"{n} block{'' if n == 1 else 's'}" in text
        if e["year"]:
            assert f"first planted {e['year']}" in text
        if e["varieties"]:
            assert ", ".join(e["varieties"]) in text


def test_the_page_s_list_is_what_the_register_makes():
    parts = mv._page_parts(page_text())
    assert parts is not None
    assert parts[1] == mv.render_list(load("register.json")["vineyards"])
    assert mv.page_reasons(ROOT) == []


def test_the_groups_are_the_scripts():
    with open(
        os.path.join(ROOT, "docs", "assets", "vineyard-list.js"),
        encoding="utf-8",
    ) as fh:
        script = fh.read()
    block = re.search(r"const GROUPS = \[(.*?)\n\];", script, re.S).group(1)
    pairs = re.findall(r'\["([^"]+)", "([^"]+)"\]', block)
    assert tuple(pairs) == mv.GROUPS


def test_the_list_s_text_is_escaped():
    out = mv.render_list(
        [
            {
                "id": "a-b",
                "name": 'A <b>"bold"</b> & Co',
                "category": "hsd",
                "vids": ["v-1", "v-2"],
                "year": 2001,
                "varieties": ["<script>x</script>"],
            },
            {
                "id": 'not a slug"><x',
                "name": "Plain",
                "category": "historical",
                "vids": ["v-3"],
                "year": None,
                "varieties": [],
            },
        ]
    )
    assert "<b>" not in out
    assert "<script>" not in out
    assert "A &lt;b&gt;&quot;bold&quot;&lt;/b&gt; &amp; Co" in out
    assert "2 blocks · first planted 2001" in out
    assert "1 block<" in out
    assert out.count('class="vy-change"') == 1  # none for an id not a slug
    assert "Under development" not in out  # an empty group is left out


def test_a_stale_or_unmarked_list_is_caught_and_written_again(tmp_path):
    for rel in (*mv.INPUTS.values(), mv.OUT, mv.PAGE):
        src = os.path.join(ROOT, rel)
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy(src, dst)
    page = tmp_path / mv.PAGE
    good = page.read_text(encoding="utf-8")
    page.write_text(
        good.replace("Blackmon Vineyard</h4>", "Blackmon</h4>", 1),
        encoding="utf-8",
    )
    assert mv.stale_reasons(str(tmp_path)) == [f"{mv.PAGE}'s vineyard list"]
    assert mv.main(["--check", "--root", str(tmp_path)]) == mv.STALE
    assert mv.main(["--root", str(tmp_path)]) == 0
    assert page.read_text(encoding="utf-8") == good
    assert mv.main(["--check", "--root", str(tmp_path)]) == 0
    page.write_text(good.replace(mv.END, ""), encoding="utf-8")
    assert "markers" in mv.stale_reasons(str(tmp_path))[0]
    assert mv.main(["--check", "--root", str(tmp_path)]) == mv.STALE
    with pytest.raises(SystemExit):
        mv.main(["--root", str(tmp_path)])
    os.remove(page)
    assert mv.stale_reasons(str(tmp_path)) == [f"{mv.PAGE} is missing"]
