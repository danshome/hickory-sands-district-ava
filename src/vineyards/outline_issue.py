"""Puts the petitioners' outline into a pin-only submission's issue.

When a grower drops a pin instead of drawing the blocks, the petitioners
draw the blocks from imagery before approving (src/vineyards/SETUP.md, "A
pin with no outline"). This writes the issue's new body: the same
submission with the drawn blocks, marked as drawn by the petitioners, in the
form's fixed layout. It prints the body; nothing is sent. Paste it over the
issue's body (Edit), or send it with the GitHub CLI:

    .venv/bin/python -E -s -B src/vineyards/outline_issue.py 12 drawn.geojson >b
    gh issue edit 12 --body-file b

drawn.geojson holds the blocks as Polygons, longitude and latitude in WGS 84
(EPSG:4326), as QGIS exports them ("Export > Save Features As", GeoJSON,
CRS EPSG:4326). The issue's body is read with the GitHub CLI (gh issue view)
unless --body names a file. The check runs again when the issue is edited;
add the label `approved` once it says "ready for review".
"""

import argparse
import json
import os
import re
import subprocess
import sys

# The repository's root: -I leaves the script's own folder off sys.path.
sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ),
)

from src.vineyards import submission as vs

ROOT = vs.ROOT


def drawn_rings(path):
    """The blocks of a GeoJSON file, as open rings of [lon, lat].

    Args:
        path: The file: a FeatureCollection, a Feature or a geometry, of
            Polygons or MultiPolygons (their outer rings only).

    Returns:
        A list of rings.

    Raises:
        SystemExit: No polygon in the file.
    """
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    feats = data.get("features") or [data]
    rings = []
    for f in feats:
        geom = f.get("geometry", f)
        if geom["type"] == "Polygon":
            polys = [geom["coordinates"]]
        elif geom["type"] == "MultiPolygon":
            polys = geom["coordinates"]
        else:
            continue
        for poly in polys:
            ring = [[round(p[0], 6), round(p[1], 6)] for p in poly[0]]
            if len(ring) > 1 and ring[0] == ring[-1]:
                ring.pop()
            rings.append(ring)
    if not rings:
        raise SystemExit(f"{path}: no polygon")
    return rings


def outlined(body, rings):
    """The issue's new body, with the petitioners' blocks.

    Args:
        body: The issue's body now (the form's layout).
        rings: drawn_rings()'s blocks.

    Returns:
        The new body.

    Raises:
        SystemExit: The body is not the form's, or the blocks break a rule.
    """
    try:
        data = vs.parse_issue(body)
    except vs.SubmissionError as error:
        raise SystemExit(
            f"not a vineyard submission's issue: {error}"
        ) from None
    raw = {
        **{k: data.get(k) for k in ("form", "version", "vineyard", "pin")},
        "blocks": rings,
        "id": "00000000-0000-4000-8000-000000000000",
        "contact": {"name": "Checked", "email": "check@example.com"},
        "agree": {"public": True, "permission": True},
    }
    try:
        sub, errors, _ = vs.check(raw)
    except vs.SubmissionError as error:
        raise SystemExit(f"cannot be read: {error}") from None
    errors = [m for f, m in errors if not f.startswith(("contact", "agree"))]
    if errors:
        raise SystemExit("the blocks break a rule: " + " ".join(errors))
    sub["outline"] = "petitioner"
    out = vs.issue_body(sub, data.get("sent") or "")
    # the function's marker, by which it ties the issue to its sender, stays
    found = re.search(r"<!-- hsd-vineyard-ref: [0-9a-f]{24} -->", body)
    return out + found.group(0) + "\n" if found else out


def main(argv=None):
    """Prints the issue's new body.

    Args:
        argv: The command line's arguments (sys.argv[1:] when None).

    Returns:
        0.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("issue", type=int, help="the issue's number")
    parser.add_argument("drawn", help="the blocks, GeoJSON in EPSG:4326")
    parser.add_argument("--body", help="the issue's body, from a file")
    args = parser.parse_args(argv)
    if args.body:
        with open(args.body, encoding="utf-8") as fh:
            body = fh.read()
    else:
        body = subprocess.run(
            [
                "gh",
                "issue",
                "view",
                str(args.issue),
                "--json",
                "body",
                "-q",
                ".body",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    sys.stdout.write(outlined(body, drawn_rings(args.drawn)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
