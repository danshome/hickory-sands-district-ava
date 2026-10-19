"""The vineyard file's writer, the review, and the pin's outline.

src/vineyards/submission.py: the review the check posts (ready, or what to
look at: a name or a block already on the map, a block across the
district's line, a pin), and add_blocks(), which keeps the vineyard file's
own layout byte for byte (so a pull request's diff is only the new lines),
sorts by category and name, writes rings clockwise, writes a block's number
as the file does, keeps the year and the varieties, and refuses a field that
names someone. src/vineyards/outline_issue.py: the petitioners' blocks put
into a pin's issue. Standard library only.
"""

import copy
import json
import os
import shutil

import pytest

from src.site.aquifer import vineyards as places
from src.vineyards import outline_issue
from src.vineyards import submission as vs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SENT = "2026-10-19T08:30:00.000Z"
GOOD = {
    "form": "hsd-vineyard",
    "version": 1,
    "id": "3f2b8c1e-5d4a-4e6f-9a7b-1c2d3e4f5a6b",
    "vineyard": {
        "name": "Prairie Gap Vineyard",
        "county": "Mason",
        "planted": "planted",
        "acres": 8,
        "year": 2016,
        "varieties": ["Tempranillo", "Mourvèdre"],
    },
    "blocks": [
        [
            [-99.295, 30.865],
            [-99.2925, 30.865],
            [-99.2925, 30.8632],
            [-99.295, 30.8632],
        ]
    ],
    "pin": None,
    "contact": {"name": "Jane Q. Grower", "phone": "325 555 0100"},
    "agree": {"public": True, "permission": True},
    "website": "",
}


def reviewed(raw, number=12, **kw):
    sub, errors, _ = vs.check(raw, year=2026)
    assert not errors, errors
    return vs.review(vs.parse_issue(vs.issue_body(sub, SENT)), number, **kw)


@pytest.fixture
def root(tmp_path):
    """A copy of the vineyard file and the areas, to write into."""
    for rel in (vs.VINEYARDS, vs.LLANO, vs.DISTRICT):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(os.path.join(ROOT, rel), tmp_path / rel)
    (tmp_path / vs.WELLS).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / vs.WELLS).symlink_to(os.path.join(ROOT, vs.WELLS))
    return tmp_path


def test_a_good_one_is_ready(root):
    md, ok, result = reviewed(GOOD, root=root, today="2026-10-19")
    assert ok
    assert "### The check: ready for review" in md
    assert "**Hickory Sands District vineyard** (`hsd`), 1 block" in md
    assert "Sent through the website's vineyard form (GitHub issue #12)" in md
    assert result["category"] == "hsd"
    assert "Jane" not in md
    assert "555" not in md


def test_planned_and_outside_the_district():
    planned = copy.deepcopy(GOOD)
    planned["vineyard"]["planted"] = "planned"
    assert reviewed(planned)[2]["category"] == "under-development"
    sub = {"vineyard": {"planted": "planted"}}
    assert vs.category(sub, [{"district": "out", "acres": 3}]) == (
        "llano-uplift",
        False,
    )
    both = [
        {"district": "in", "acres": 2},
        {"district": "both", "acres": 9},
        {"district": "out", "acres": 5},
    ]
    # a block across the line counts on neither side; the whole blocks decide
    assert vs.category(sub, both) == ("llano-uplift", True)
    both[0]["acres"] = 6
    assert vs.category(sub, both) == ("hsd", True)


def test_the_writer_keeps_the_file_byte_for_byte(root):
    with open(root / vs.VINEYARDS, encoding="utf-8") as fh:
        old = fh.read()
    nothing = {
        "submission": {"vineyard": GOOD["vineyard"], "blocks": []},
        "category": "hsd",
    }
    new, diff = vs.add_blocks(nothing, 12, "2026-10-19", root)
    assert new == old
    assert diff == ""


def test_new_blocks_are_new_lines_in_order(root):
    two = copy.deepcopy(GOOD)
    two["blocks"].append(
        [
            [-99.296, 30.8628],
            [-99.2945, 30.8628],
            [-99.2945, 30.8618],
            [-99.296, 30.8618],
        ]
    )
    _, ok, result = reviewed(two, root=root)
    assert ok
    new, diff = vs.add_blocks(result, 12, "2026-10-19", root)
    added = [line for line in diff.splitlines() if line.startswith("+{")]
    removed = [
        line
        for line in diff.splitlines()
        if line.startswith("-") and not line.startswith("---")
    ]
    assert len(added) == 2
    assert all(line.endswith(",") for line in removed)  # a comma moved, at most
    features = json.loads(new)["features"]
    order = [c for c, _ in places.CATEGORIES]
    keys = [
        (
            order.index(f["properties"]["category"]),
            f["properties"]["name"].casefold(),
        )
        for f in features
    ]
    assert keys == sorted(keys)
    mine = [
        f for f in features if f["properties"]["name"] == "Prairie Gap Vineyard"
    ]
    # the file writes blocks as text (#144), so the new ones are text too
    assert [f["properties"]["block"] for f in mine] == ["1", "2"]
    for f in mine:
        p = f["properties"]
        assert p["year"] == 2016
        assert p["varieties"] == ["Tempranillo", "Mourvèdre"]
        assert p["acres"] > 0
        ring = f["geometry"]["coordinates"][0]
        assert ring[0] == ring[-1]
        assert vs._signed(ring) < 0  # clockwise, as the file's rings
        assert not places.named(json.dumps(p, ensure_ascii=False))


def test_a_file_that_writes_blocks_as_text_gets_text(root):
    path = root / vs.VINEYARDS
    data = json.loads(path.read_text(encoding="utf-8"))
    for f in data["features"]:
        if f["properties"]["block"] is not None:
            f["properties"]["block"] = str(f["properties"]["block"])
    path.write_text(
        vs.HEADER
        + ",\n".join(vs.feature_line(f) for f in data["features"])
        + vs.FOOTER,
        encoding="utf-8",
    )
    _, _, result = reviewed(GOOD, root=root)
    new, _ = vs.add_blocks(result, 12, "2026-10-19", root)
    mine = [
        f
        for f in json.loads(new)["features"]
        if f["properties"]["name"] == "Prairie Gap Vineyard"
    ]
    assert [f["properties"]["block"] for f in mine] == ["1"]


def test_a_private_word_stops_the_writer(root):
    _, _, result = reviewed(GOOD, root=root)
    with pytest.raises(SystemExit):
        vs.add_blocks(result, 12, "2026-10-19", root, ["prairie gap"])


def test_what_is_already_on_the_map_is_flagged(root):
    same = copy.deepcopy(GOOD)
    same["vineyard"]["name"] = "certenburg vineyard"
    md, ok, _ = reviewed(same, root=root)
    assert not ok
    assert "A vineyard of this name is already on the map (3 blocks)" in md
    md, ok, _ = reviewed(GOOD, others=[(13, "Prairie Gap Vineyard")], root=root)
    assert ok  # a twin is said, for Dan to close, and does not stop it
    assert "Another open submission has this name: #13." in md


def test_a_pin_is_drawn_by_the_petitioners_then_ready(root, tmp_path):
    pin = copy.deepcopy(GOOD)
    pin["blocks"] = []
    pin["pin"] = [-99.294, 30.864]
    sub, _, _ = vs.check(pin, year=2026)
    body = vs.issue_body(sub, SENT)
    md, ok, _ = vs.review(vs.parse_issue(body), 14, root=root)
    assert not ok
    assert "No outline: only a pin" in md
    drawn = tmp_path / "drawn.geojson"
    drawn.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [*GOOD["blocks"][0], GOOD["blocks"][0][0]]
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    new_body = outline_issue.outlined(body, outline_issue.drawn_rings(drawn))
    data = vs.parse_issue(new_body)
    assert data["outline"] == "petitioner"
    assert data["pin"] == [-99.294, 30.864]
    assert data["sent"] == SENT
    assert "1 block drawn by the petitioners" in new_body
    md, ok, result = vs.review(data, 14, root=root, today="2026-10-19")
    assert ok, md
    assert "drawn by the petitioners on Esri World Imagery" in md
    new, _ = vs.add_blocks(result, 14, "2026-10-19", root)
    assert "from the sender's pin" in new


def test_an_outline_that_breaks_a_rule_is_refused(tmp_path):
    pin = copy.deepcopy(GOOD)
    pin["blocks"] = []
    pin["pin"] = [-99.294, 30.864]
    body = vs.issue_body(vs.check(pin, year=2026)[0], SENT)
    with pytest.raises(SystemExit, match="break a rule"):
        outline_issue.outlined(
            body, [[[-97.75, 30.27], [-97.74, 30.27], [-97.74, 30.26]]]
        )
    with pytest.raises(SystemExit, match="not a vineyard submission"):
        outline_issue.outlined("hello", [GOOD["blocks"][0]])
