"""Review sheets for traced lines: one PNG per line, the proof a person checks before the linework is used.
Top: the whole line on the USGS scan, the prior (current line) in red, the trace in purple, the check's figures in the
header. Below: six close-ups about 120 m across -- the worst stretches off the measured centre, the largest moves from
the prior, and the longest gaps bridged -- each labelled with what it shows and the sheet it is on.

CLI: review.py --quads "GLOB" --traced traced.geojson [--prior lines.geojson] [--title-field narrative]
               --out-dir DIR [--ids ...]
"""

import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from centerline import densify
from quadsheets import open_sheets
from quadsheets import sheet_of


def _font(size):
    for f in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


FONT, SMALL = _font(22), _font(17)
OLD, NEW = (230, 0, 0), (120, 0, 230)


def crop(sh, c0, r0, c1, r1, out_w, lines):
    a, cc0, rr0 = sh.read(c0, r0, c1, r1)
    im = Image.fromarray(np.transpose(a, (1, 2, 0)).astype("uint8"))
    scale = out_w / a.shape[2]
    im = im.resize(
        (out_w, max(1, int(a.shape[1] * scale))),
        Image.LANCZOS if scale < 1 else Image.NEAREST,
    )
    d = ImageDraw.Draw(im)
    for pts, col, w in lines:
        if not pts:
            continue
        c, r, _, _ = sh.pixels([p[0] for p in pts], [p[1] for p in pts])
        d.line(
            [
                ((u - cc0) * scale, (v - rr0) * scale)
                for u, v in zip(c, r, strict=True)
            ],
            fill=col,
            width=w,
        )
    return im


def osr_ct(sh):
    """sheet projection -> NAD83 lon/lat (inverse of the sheet's own transform)"""
    if not hasattr(sh, "_inv"):
        sh._inv = sh.ct.GetInverse()
    return sh._inv


def dist_to(line, p):
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


def sheet_png(sheets, feat, prior, title, out_path, width=1500):
    st = feat["properties"]
    new = [tuple(p[:2]) for p in feat["geometry"]["coordinates"]]
    old = [tuple(p[:2]) for p in prior] if prior else []
    sample = new[:: max(1, len(new) // 40)]
    owners = [sheet_of(sheets, *p) for p in sample]
    sh = max(
        (s for s in owners if s), key=lambda s: sum(1 for o in owners if o is s)
    )
    c, r, _, _ = sh.pixels([p[0] for p in new], [p[1] for p in new])
    c0, r0, c1, r1 = c.min() - 60, r.min() - 60, c.max() + 60, r.max() + 60
    side = max(c1 - c0, r1 - r0)
    cx, cy = (c0 + c1) / 2, (r0 + r1) / 2
    over = crop(
        sh,
        cx - side / 2,
        cy - side / 2,
        cx + side / 2,
        cy + side / 2,
        width,
        [(old, OLD, 3), (new, NEW, 3)],
    )
    # where the line runs onto another sheet, show that sheet's own map face there (not this sheet's collar)
    others = list({id(o): o for o in owners if o and o is not sh}.values())
    if others:
        scale = width / side
        height = over.height
        gx, gy = np.meshgrid(np.arange(0, width, 4), np.arange(0, height, 4))
        pc = (cx - side / 2) + gx / scale
        pr = (cy - side / 2) + gy / scale
        g = sh.gt
        proj_x = g[0] + pc * g[1]
        proj_y = g[3] + pr * g[5]
        ll = np.array(
            osr_ct(sh).TransformPoints(
                np.column_stack([proj_x.ravel(), proj_y.ravel()]).tolist()
            )
        )[:, :2]
        for s2 in others:
            c2, r2, ins2, _ = s2.pixels(ll[:, 0], ll[:, 1])
            if not ins2.any():
                continue
            a2, c0b, r0b = s2.read(
                c2[ins2].min() - 2,
                r2[ins2].min() - 2,
                c2[ins2].max() + 3,
                r2[ins2].max() + 3,
            )
            img = np.array(over)
            ci = np.clip((c2 - c0b).astype(int), 0, a2.shape[2] - 1)
            ri = np.clip((r2 - r0b).astype(int), 0, a2.shape[1] - 1)
            vals = np.transpose(a2, (1, 2, 0))[ri, ci]
            for k in np.flatnonzero(ins2):
                yy, xx = divmod(k, gx.shape[1])
                img[yy * 4 : yy * 4 + 4, xx * 4 : xx * 4 + 4] = vals[k][:3]
            over = Image.fromarray(img)
        d = ImageDraw.Draw(over)
        for pts, col in ((old, OLD), (new, NEW)):
            if not pts:
                continue
            c, r, _, _ = sh.pixels([p[0] for p in pts], [p[1] for p in pts])
            d.line(
                [
                    (
                        (u - (cx - side / 2)) * scale,
                        (v - (cy - side / 2)) * scale,
                    )
                    for u, v in zip(c, r, strict=True)
                ],
                fill=col,
                width=3,
            )
    spots = [
        (q[0], q[1], f"off centre up to {q[3]} m over {q[2]} m")
        for q in st.get("off_center_runs", [])[:3]
    ]
    spots += [
        (g[0], g[1], f"gap bridged, {g[2]} m")
        for g in sorted(st.get("gaps", []), key=lambda g: -g[2])[:1]
    ]
    if old:
        dense = densify(new, 2.0)
        dd = np.array([dist_to(old, p) for p in dense])
        taken = []
        for i in np.argsort(-dd):
            if len(taken) == 2 or dd[i] <= 3:
                break
            if all(abs(i - j) > 60 for j in taken):
                taken.append(i)
                spots.append(
                    (
                        dense[i][0],
                        dense[i][1],
                        f"moved {dd[i]:.0f} m from the prior",
                    )
                )
    dense = densify(new, 2.0)
    k = 1
    while len(spots) < 6:
        i = int(len(dense) * k / 7)
        spots.append((dense[i][0], dense[i][1], "sample"))
        k += 1
    tiles = []
    for lon, lat, label in spots[:6]:
        s2 = sheet_of(sheets, lon, lat)
        if not s2:
            continue
        u, v, _ = s2.pixel(lon, lat)
        h = 30
        im = crop(
            s2, u - h, v - h, u + h, v + h, 480, [(old, OLD, 2), (new, NEW, 2)]
        )
        ImageDraw.Draw(im).text(
            (8, 6),
            f"{label}  ({s2.name})",
            fill=(0, 0, 0),
            font=SMALL,
            stroke_width=3,
            stroke_fill=(255, 255, 255),
        )
        tiles.append(im)
    head = 120
    rows = (len(tiles) + 2) // 3
    out = Image.new(
        "RGB", (width, head + over.height + rows * 490 + 10), "white"
    )
    d = ImageDraw.Draw(out)
    d.text(
        (10, 8),
        (title or f"line {st.get('id')}")[:150],
        fill=(0, 0, 0),
        font=FONT,
    )
    d.text(
        (10, 42),
        f"{st['kind']}: {st['length_prior_m']:.0f} m -> {st['length_m']:.0f} m; centre measured along {st['measured_pct']}%; "
        f"off centre median {st['off_center_median_m']} m, 95% {st['off_center_p95_m']} m, within 2 m {st['within_2m_pct']}%; "
        f"largest move {st['moved_max_m']} m",
        fill=(0, 0, 0),
        font=SMALL,
    )
    d.text(
        (10, 68),
        f"pins off the centreline: start {st['pin_start_off_center_m']} m, end {st['pin_end_off_center_m']} m; gaps bridged "
        f">= 8 m: {len(st.get('gaps', []))}.  Red: prior (current line).  Purple: traced centreline.  Sheet: {sh.name}",
        fill=(0, 0, 0),
        font=SMALL,
    )
    out.paste(over, (0, head))
    for i, im in enumerate(tiles):
        out.paste(
            im, (10 + (i % 3) * 495, head + over.height + 10 + (i // 3) * 490)
        )
    out.save(out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quads", action="append", required=True)
    ap.add_argument("--traced", required=True)
    ap.add_argument("--prior")
    ap.add_argument("--id-field", default="id")
    ap.add_argument("--title-field")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ids", nargs="*")
    a = ap.parse_args()
    sheets = open_sheets(a.quads)
    os.makedirs(a.out_dir, exist_ok=True)
    pri = {}
    if a.prior:
        with open(a.prior) as fh:
            prior_fc = json.load(fh)
        for f in prior_fc["features"]:
            pri[str(f["properties"].get(a.id_field))] = f
    with open(a.traced) as fh:
        traced_fc = json.load(fh)
    for f in traced_fc["features"]:
        fid = str(f["properties"]["id"])
        if a.ids and fid not in a.ids:
            continue
        pf = pri.get(fid)
        title = (
            pf["properties"].get(a.title_field)
            if pf and a.title_field
            else None
        ) or f"line {fid}"
        name = (
            f"review-{int(fid):03d}.png"
            if fid.isdigit()
            else f"review-{fid}.png"
        )
        print(
            sheet_png(
                sheets,
                f,
                pf["geometry"]["coordinates"] if pf else None,
                title,
                os.path.join(a.out_dir, name),
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
