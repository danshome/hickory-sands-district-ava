"""Problem finder: close-ups of every place a traced line may be off the ink.

Walks every traced line and cuts a close-up of each place that may not be on the
ink, plus a few random controls, for review by a person or by reviewer agents
(the "critic" pass). Writes:
  OUT/problems.json   one record per spot: pid, line id, kind, type, lon, lat,
                      sheet, detail, png
  OUT/<pid>.png       left: the scan, prior (current line) red, traced line
                      purple; right: the ink classes the tracer sees
                      (black/gray magenta, red orange, brown green, blue/teal
                      blue) with the traced line
Spot types:
  off_center   the independent check measured the symbol's centre > 2 m from
               the line (traced 'off_center_runs')
  gap          >= 15 m where no centre could be measured (traced 'gaps'):
               lettering, ink missed, a real gap
  moved        the traced line is > 8 m from the prior (local maxima): one of
               them is wrong
  sheet_edge   the line crosses from one sheet to another: is there a jog, is
               it the right size
  control      random places, so a reviewer also sees what right looks like
CLI: problems.py --quads "GLOB" --traced traced.geojson [--prior lines.geojson]
                 --out-dir DIR [--ids ...] [--controls 1] [--half 32]
                 [--scale 6] [--spots regression.json]
     (at most 3 off_center, 2 moved, 2 gap, 1 sheet_edge, 1 control per line)
Review with agents: references/review-rubric.md.
"""

import argparse
from collections import Counter
import json
import math
import os
import random
import sys

import numpy as np
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from centerline import densify
import ink
from quadsheets import open_sheets
from quadsheets import sheet_of

COL = {
    "black": (255, 0, 255),
    "red": (255, 140, 0),
    "brown": (0, 160, 0),
    "creek": (0, 0, 255),
}
OLD, NEW = (230, 0, 0), (120, 0, 230)
QUOTA = dict(
    off_center=3, moved=2, gap=2, sheet_edge=1, control=1
)  # spots per line, worst first


def _font(size):
    for f in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


SMALL = _font(16)


def m_between(a, b):
    """Returns the flat distance in metres between two NAD83 (lon, lat)."""
    return math.hypot(
        (a[0] - b[0]) * 111320 * math.cos(math.radians(a[1])),
        (a[1] - b[1]) * 110574,
    )


def dist_to(line, p):
    """Returns the distance in metres from a point to a polyline.

    Both are NAD83 (lon, lat); the distance is measured in a flat frame around
    the point (111320 m per degree of longitude times cos(lat), 110574 m per
    degree of latitude).
    """
    pts = np.array(line)
    dx = (pts[:, 0] - p[0]) * 111320 * math.cos(math.radians(p[1]))
    dy = (pts[:, 1] - p[1]) * 110574
    rel = np.column_stack([dx, dy])
    seg = rel[1:] - rel[:-1]
    seg_len2 = (seg**2).sum(1)
    seg_len2[seg_len2 == 0] = 1
    t = np.clip(-(rel[:-1] * seg).sum(1) / seg_len2, 0, 1)
    foot = rel[:-1] + t[:, None] * seg
    return float(np.sqrt((foot**2).sum(1)).min())


def closeup(sh, lon, lat, old, new, half, scale, label):
    """Draws the close-up of one spot: the scan beside the ink classes.

    Left, the scan with the prior (red) and the traced line (purple); right,
    the ink classes the tracer sees (COL, classified with a 30-pixel margin)
    with the traced line; both enlarged, the spot circled, the label above.

    Args:
        sh: The sheet holding the spot (quadsheets.Sheet).
        lon: The spot's NAD83 longitude.
        lat: The spot's NAD83 latitude.
        old: The prior's NAD83 points, or None.
        new: The traced line's NAD83 points.
        half: Half the close-up's width and height, in scan pixels.
        scale: The enlargement (nearest neighbour).
        label: The text above the panels.

    Returns:
        The PIL image.
    """
    c, r, _ = sh.pixel(lon, lat)
    a, c0, r0 = sh.read(c - half, r - half, c + half, r + half)
    big, bc0, br0 = sh.read(
        c - half - 30, r - half - 30, c + half + 30, r + half + 30
    )
    m = ink.classes(big)
    oy, ox = int(r0 - br0), int(c0 - bc0)
    rgb = np.transpose(a, (1, 2, 0)).astype("uint8")
    ov = np.full_like(rgb, 255)
    for k, col in COL.items():
        ov[m[k][oy : oy + rgb.shape[0], ox : ox + rgb.shape[1]]] = col
    width = rgb.shape[1] * scale
    height = rgb.shape[0] * scale
    left = Image.fromarray(rgb).resize((width, height), Image.NEAREST)
    right = Image.fromarray(ov).resize((width, height), Image.NEAREST)
    for im, lines in ((left, ((old, OLD), (new, NEW))), (right, ((new, NEW),))):
        d = ImageDraw.Draw(im)
        for pts, col in lines:
            if not pts:
                continue
            cc, rr, _, _ = sh.pixels([p[0] for p in pts], [p[1] for p in pts])
            d.line(
                [
                    ((u - c0) * scale, (v - r0) * scale)
                    for u, v in zip(cc, rr, strict=True)
                ],
                fill=col,
                width=2,
            )
        d.ellipse(
            [width / 2 - 5, height / 2 - 5, width / 2 + 5, height / 2 + 5],
            outline=(0, 0, 0),
            width=1,
        )
    out = Image.new("RGB", (2 * width + 10, height + 28), "white")
    out.paste(left, (0, 28))
    out.paste(right, (width + 10, 28))
    ImageDraw.Draw(out).text((6, 5), label, fill=(0, 0, 0), font=SMALL)
    return out


def spots_for(feat, prior, sheets, controls, rng):
    """Finds the spots of one traced line worth a close-up, worst first.

    Candidates: the check's off-centre runs (worst: length times offset) and
    its gaps of 15 m or more, from the line's properties; the local maxima over
    8 m of the line's distance from the prior (points every 2 m); the places
    where the line passes from one sheet to another (looked at every 10 m); and
    `controls` random points. Of each type, worst first, at most QUOTA[type]
    are kept, none within 40 m of a spot already kept.

    Args:
        feat: The traced line, a GeoJSON feature with trace()'s figures.
        prior: The prior's NAD83 points, or None (then no "moved" spots).
        sheets: The open sheets (quadsheets.open_sheets).
        controls: How many random control spots.
        rng: The random.Random the controls are drawn with.

    Returns:
        A list of (type, lon, lat, detail).
    """
    st = feat["properties"]
    new = [tuple(p[:2]) for p in feat["geometry"]["coordinates"]]
    out = []
    for q in st.get("off_center_runs", []):
        out.append(
            (
                "off_center",
                q[0],
                q[1],
                f"centre measured up to {q[3]} m off the line over {q[2]} m",
                q[2] * q[3],
            )
        )
    for g in st.get("gaps", []):
        if g[2] >= 15:
            out.append(
                ("gap", g[0], g[1], f"no centre measurable over {g[2]} m", g[2])
            )
    dense = densify(new, 2.0)
    if prior:
        dd = np.array([dist_to(prior, p) for p in dense])
        for i in range(1, len(dd) - 1):
            if dd[i] > 8 and dd[i] >= dd[max(0, i - 15) : i + 16].max():
                out.append(
                    (
                        "moved",
                        dense[i][0],
                        dense[i][1],
                        f"traced line {dd[i]:.0f} m from the prior",
                        dd[i],
                    )
                )
    owner = [sheet_of(sheets, *p) for p in dense[::5]]
    for i in range(1, len(owner)):
        if (
            owner[i] is not None
            and owner[i - 1] is not None
            and owner[i] is not owner[i - 1]
        ):
            p = dense[i * 5]
            out.append(
                (
                    "sheet_edge",
                    p[0],
                    p[1],
                    f"from {owner[i - 1].name} to {owner[i].name}",
                    1.0,
                )
            )
    for _ in range(controls):
        p = dense[rng.randrange(len(dense))]
        out.append(("control", p[0], p[1], "random place on the line", 0.0))
    # worst first within each type, at most QUOTA[type], one spot per 40 m
    kept = []
    for typ in ("off_center", "moved", "gap", "sheet_edge", "control"):
        n = 0
        for s in sorted((s for s in out if s[0] == typ), key=lambda s: -s[4]):
            if n >= QUOTA[typ]:
                break
            if all(m_between((s[1], s[2]), (k[1], k[2])) > 40 for k in kept):
                kept.append(s)
                n += 1
    return [s[:4] for s in kept]


def main():
    """Finds and draws the spots of the traced lines, or re-renders --spots."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quads", action="append", required=True)
    ap.add_argument("--traced", required=True)
    ap.add_argument("--prior")
    ap.add_argument("--id-field", default="id")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--controls", type=int, default=1)
    ap.add_argument("--half", type=int, default=32)
    ap.add_argument("--scale", type=int, default=6)
    ap.add_argument(
        "--spots",
        help=(
            "re-render these spots (a problems.json, e.g. the labelled "
            "regression cases) instead of finding new ones"
        ),
    )
    a = ap.parse_args()
    sheets = open_sheets(a.quads)
    os.makedirs(a.out_dir, exist_ok=True)
    rng = random.Random(1)
    pri = {}
    if a.prior:
        with open(a.prior) as fh:
            prior_fc = json.load(fh)
        for f in prior_fc["features"]:
            pri[str(f["properties"].get(a.id_field))] = [
                tuple(p[:2]) for p in f["geometry"]["coordinates"]
            ]
    records = []
    if a.spots:
        with open(a.traced) as fh:
            traced_fc = json.load(fh)
        traced = {str(f["properties"]["id"]): f for f in traced_fc["features"]}
        with open(a.spots) as fh:
            spots = json.load(fh)
        spots = spots["spots"] if isinstance(spots, dict) else spots
        for r in spots:
            f = traced.get(str(r["id"]))
            if f is None or (a.ids and str(r["id"]) not in a.ids):
                continue
            sh = sheet_of(sheets, r["lon"], r["lat"])
            new = [tuple(p[:2]) for p in f["geometry"]["coordinates"]]
            label = (
                f"{r['pid']}  {f['properties']['kind']}  ({sh.name})  "
                f"re-check: {r.get('detail', '')}"
            )
            closeup(
                sh,
                r["lon"],
                r["lat"],
                pri.get(str(r["id"])),
                new,
                a.half,
                a.scale,
                label,
            ).save(os.path.join(a.out_dir, r["pid"] + ".png"))
            records.append(dict(r, png=r["pid"] + ".png"))
        with open(os.path.join(a.out_dir, "problems.json"), "w") as fh:
            json.dump(records, fh, indent=1)
        print(len(records), "spots re-rendered")
        return
    with open(a.traced) as fh:
        traced_fc = json.load(fh)
    for f in traced_fc["features"]:
        fid = str(f["properties"]["id"])
        if a.ids and fid not in a.ids:
            continue
        new = [tuple(p[:2]) for p in f["geometry"]["coordinates"]]
        old = pri.get(fid)
        for k, (typ, lon, lat, detail) in enumerate(
            spots_for(f, old, sheets, a.controls, rng)
        ):
            sh = sheet_of(sheets, lon, lat)
            if sh is None:
                continue
            pid = f"{fid}-{k:02d}-{typ}"
            label = f"{pid}  {f['properties']['kind']}  ({sh.name})  {detail}"
            closeup(sh, lon, lat, old, new, a.half, a.scale, label).save(
                os.path.join(a.out_dir, pid + ".png")
            )
            records.append(
                dict(
                    pid=pid,
                    id=fid,
                    kind=f["properties"]["kind"],
                    type=typ,
                    lon=round(lon, 6),
                    lat=round(lat, 6),
                    sheet=sh.name,
                    detail=detail,
                    png=pid + ".png",
                )
            )
        print(
            f"{fid}: {sum(1 for r in records if r['id'] == fid)} spots",
            flush=True,
        )
    with open(os.path.join(a.out_dir, "problems.json"), "w") as fh:
        json.dump(records, fh, indent=1)
    print(len(records), "spots:", dict(Counter(r["type"] for r in records)))


if __name__ == "__main__":
    main()
