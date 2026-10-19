"""Protect template prose and catch direct edits to the generated README."""

import json
from pathlib import Path

import pytest

from src.documents import make_repo_readme as readme

ROOT = Path(__file__).resolve().parents[1]


def checkout(tmp_path):
    """Make a minimal checkout with the real template and recorded figures."""
    for relative in (readme.TEMPLATE, readme.FIGURES, Path("README.md")):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    return tmp_path


def test_committed_readme_matches():
    assert readme.generate(ROOT, None, check=True) == 0


@pytest.mark.parametrize("edit", ["prose", "figure", "deleted"])
def test_direct_edits_fail_without_overwriting(tmp_path, edit):
    root = checkout(tmp_path)
    path = root / "README.md"
    text = path.read_text("utf-8")
    if edit == "deleted":
        path.unlink()
    else:
        text = (
            text + "\nManual addition\n"
            if edit == "prose"
            else text.replace("193.83", "999.99")
        )
        path.write_text(text, encoding="utf-8")
    assert readme.generate(root, None, check=True) == 1
    assert (
        not path.exists()
        if edit == "deleted"
        else path.read_text("utf-8") == text
    )


def test_template_prose_survives_regeneration(tmp_path):
    root = checkout(tmp_path)
    path = root / readme.TEMPLATE
    path.write_text(
        path.read_text("utf-8") + "\nNew prose.\n", encoding="utf-8"
    )
    assert readme.generate(root, None, check=True) == 1
    assert readme.generate(root, None, check=False) == 0
    first = (root / "README.md").read_bytes()
    assert first.endswith(b"\nNew prose.\n")
    assert readme.generate(root, None, check=False) == 0
    assert (root / "README.md").read_bytes() == first


@pytest.mark.parametrize("token", ["", "{{unknown}}", "{{area", "{{Area}}"])
def test_invalid_template_never_writes(tmp_path, token):
    root = checkout(tmp_path)
    path = root / readme.TEMPLATE
    path.write_text(
        path.read_text("utf-8").replace("{{area}}", token), encoding="utf-8"
    )
    before = (root / "README.md").read_bytes()
    with pytest.raises(ValueError):
        readme.generate(root, None, check=False)
    assert (root / "README.md").read_bytes() == before


def test_build_refresh_and_rounding(tmp_path):
    root = checkout(tmp_path)
    work = root / "work"
    (work / "review").mkdir(parents=True)
    (work / "gis").mkdir()
    data = {
        "proposed-steps.json": {"steps": [1, 2], "sqmi": 12.34},
        "gis/test-points-EPSG4269.geojson": {"features": [1, 2, 3]},
        "review/grit-change-stats.json": {
            "areas": {
                name: {"acres": 1000.5, "granite_acres": 0.5}
                for name in readme.GRIT_KEYS.values()
            },
            "sqmi": {"notice_243": 15.12, "petition": 13.45, "revision": 12.34},
        },
        "review/ttb-diff-stats.json": {
            "big": 2,
            "big_m": 100.0,
            "median_m": 10.5,
            "areas": {
                "drawing": {
                    "pieces": 5,
                    "revision_only_acres": 2.5,
                    "map_explorer_only_acres": 3.5,
                },
                "text": {"pieces": 2},
            },
        },
    }
    for relative, value in data.items():
        (work / relative).write_text(json.dumps(value), encoding="utf-8")
    before = (root / readme.FIGURES).read_bytes()
    assert readme.generate(root, work, check=True) == 1
    assert (root / readme.FIGURES).read_bytes() == before
    assert readme.generate(root, work, check=False) == 0
    figures = json.loads((root / readme.FIGURES).read_text("utf-8"))
    assert figures["steps"] == "2"
    assert figures["points"] == "3"
    assert figures["area"] == "12.34"
    assert figures["pieces"] == "7"
    assert figures["notice_only_acres"] == "1,001"
    assert figures["notice_only_granite_acres"] == "1"
    assert figures["median"] == "11"
    assert figures["revision_only"] == "3"
    assert figures["map_only"] == "4"
    assert readme.generate(root, work, check=True) == 0
    (work / "gis/second-points-EPSG4269.geojson").write_text(
        "{}", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="exactly one"):
        readme.generate(root, work, check=False)
