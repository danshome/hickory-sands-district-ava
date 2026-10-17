"""Traces the steps that follow a mapped feature onto the centre of its ink.

Hickory Sands District: the steps are traced on the 13 USGS 1:24,000 sheets
(resources/quads/geotiff/*.tif.zip, read in place) with the usgs-quad-trace
skill (the project skill .claude/skills/usgs-quad-trace; method and checks in
its SKILL.md). Goal: GOAL-ink-centerlines.md.

Input: the step lines as they stood at Oct. 15, 2026, 22:11
(resources/boundary/tracing/trace-priors-EPSG4269.geojson), whose end points
are the pins, kept exactly. The doubled road near Grit (steps 10, 11, 91, 92)
keeps its 30 m lanes and is not traced.
Output: ink-centerline-steps.geojson (one traced line per step, with the
check's figures), which build_agreed.py splices into the ring.

Usage (the project .venv, via ./build.sh):
  ink_centerline.py [STEP ...]   default: every step in KIND
Review sheets: ink_centerline.py --review [STEP ...]
  -> review-ink/review-NNN.png
Problem close-ups for the critic pass: ink_centerline.py --problems [STEP ...]
  -> review-ink/problems/
"""

import json
import os
import subprocess
import sys

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)  # the repository root
HERE = os.environ.get("HSD_WORK") or os.path.join(
    ROOT, "target", "work"
)  # build work dir (build.sh stages resources/ here)
SKILL = os.path.join(ROOT, "src", "tracing")
QUADS = ROOT + "/resources/quads/geotiff/*.tif.zip"
PRIORS = os.path.join(
    ROOT, "resources", "boundary", "tracing", "trace-priors-EPSG4269.geojson"
)
INPUT = os.path.join(HERE, "ink-trace-input.geojson")
OUT = os.path.join(HERE, "ink-centerline-steps.geojson")
KIND = {
    **dict.fromkeys((3, 6, 59, 65, 82), "contour"),
    **dict.fromkeys((9, 30, 90), "creek"),
    **dict.fromkeys(
        (
            7,
            8,
            13,
            21,
            27,
            28,
            31,
            43,
            53,
            60,
            67,
            68,
            71,
            72,
            73,
            79,
            80,
            95,
            98,
        ),
        "road",
    ),
}
# Not traced, current line kept, listed for Dan: the feature the text follows is
# not printed on the sheet.
NOT_ON_SHEET = {
    81: (
        "Copperhead Road is not shown on the Mason sheet (1960s): no road "
        "symbol south of the junction at the 1,526"
    )
}

OVERRIDES = os.path.join(
    ROOT, "resources", "boundary", "tracing", "route-overrides-EPSG4269.geojson"
)
# fix_pins.py: pins moved onto the ink centre (end of step n == start of n+1)
MOVES = os.path.join(ROOT, "resources", "boundary", "tracing", "pin-moves.json")


def write_input():
    """Writes INPUT, the tracer's input: one line for each step in KIND.

    Each line is the step's prior, or its route override, with its ends on the
    moved pins where pin-moves.json moves them.
    """
    feats = []
    pin_moves = {}
    if os.path.exists(MOVES):
        with open(MOVES) as fh:
            pin_moves = json.load(fh)
    # route hints that replace a step's prior (OVERRIDES; e.g. steps 72-73 on
    # the light-duty road)
    overrides = {}
    if os.path.exists(OVERRIDES):
        with open(OVERRIDES) as fh:
            overrides = {
                f["properties"]["step"]: f["geometry"]["coordinates"]
                for f in json.load(fh)["features"]
            }
    with open(PRIORS) as fh:
        priors = json.load(fh)["features"]
    for f in priors:
        s = f["properties"]["step"]
        if s in KIND:
            c = [
                list(p)
                for p in (overrides.get(s) or f["geometry"]["coordinates"])
            ]
            if str(s) in pin_moves:
                c[-1] = list(pin_moves[str(s)]["new"])
            if str(s - 1) in pin_moves:
                c[0] = list(pin_moves[str(s - 1)]["new"])
            feats.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": c},
                    "properties": {
                        "id": str(s),
                        "kind": KIND[s],
                        "narrative": f["properties"]["narrative"],
                    },
                }
            )
    with open(INPUT, "w") as fh:
        json.dump({"type": "FeatureCollection", "features": feats}, fh)


if __name__ == "__main__":
    args = sys.argv[1:]
    review = "--review" in args
    problems = "--problems" in args
    ids = [a for a in args if a not in ("--review", "--problems")]
    write_input()
    if problems:
        cmd = [
            sys.executable,
            "-E",
            "-s",
            "-B",
            os.path.join(SKILL, "problems.py"),
            "--quads",
            QUADS,
            "--traced",
            OUT,
            "--prior",
            INPUT,
            "--out-dir",
            os.path.join(HERE, "review-ink", "problems"),
        ]
    elif review:
        cmd = [
            sys.executable,
            "-E",
            "-s",
            "-B",
            os.path.join(SKILL, "review.py"),
            "--quads",
            QUADS,
            "--traced",
            OUT,
            "--prior",
            INPUT,
            "--title-field",
            "narrative",
            "--out-dir",
            os.path.join(HERE, "review-ink"),
        ]
    else:
        cmd = [
            sys.executable,
            "-E",
            "-s",
            "-B",
            os.path.join(SKILL, "centerline.py"),
            "--quads",
            QUADS,
            "--lines",
            INPUT,
            "--out",
            OUT,
        ]
    if ids:
        cmd += ["--ids", *ids]
    sys.exit(subprocess.call(cmd))
