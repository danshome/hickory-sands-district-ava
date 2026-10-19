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

import json
import os
import shutil

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


def test_the_aquifer_data_no_longer_needs_the_vineyards():
    assert "vineyards" not in record.LOCAL
    params = record.parameters()
    assert not [k for k in params if k.startswith("vineyard")]
    aquifer = record.read_record(record.OUT)
    assert "vineyards.geojson" not in aquifer["outputs"]
    assert "vineyard-wells.json" not in aquifer["outputs"]


def test_a_changed_vineyard_file_or_tile_is_stale(tmp_path):
    for rel in (*mv.INPUTS.values(), mv.OUT):
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
