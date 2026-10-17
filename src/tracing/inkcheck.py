"""Show how ink.py classifies the scan at given points: for each point, the scan beside its class overlay (lettering gray, road
magenta, highway red orange, contour green, creek blue). Use it to check or recalibrate the classes on a new sheet set -- look at
creeks over paper and over the woodland tint, light and heavy contours, dashed and solid roads, and highways.

CLI: inkcheck.py --quads "GLOB" --at LON,LAT [--at LON,LAT ...] --out check.png [--half 60] [--scale 4]
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ink
from quadsheets import open_sheets
from quadsheets import sheet_of

# drawn in this order: lettering (gray) first, then the FINAL per-kind masks the tracer uses
COL = {
    "text": (120, 120, 120),
    "contour": (0, 160, 0),
    "creek": (0, 0, 255),
    "road": (255, 0, 255),
    "red": (255, 140, 0),
}


def panel(sheets, lon, lat, half=60):
    sh = sheet_of(sheets, lon, lat)
    if sh is None:
        return None
    c, r, _ = sh.pixel(lon, lat)
    a, c0, r0 = sh.read(c - half, r - half, c + half, r + half)
    big, bc0, br0 = sh.read(
        c - half - 30, r - half - 30, c + half + 30, r + half + 30
    )  # classify with a margin
    m = ink.classes(big)
    oy, ox = int(r0 - br0), int(c0 - bc0)
    rgb = np.transpose(a, (1, 2, 0)).astype("uint8")
    ov = np.full_like(rgb, 255)
    for k, col in COL.items():
        ov[m[k][oy : oy + rgb.shape[0], ox : ox + rgb.shape[1]]] = col
    return np.hstack([rgb, ov])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quads", action="append", required=True)
    ap.add_argument("--at", action="append", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--half", type=int, default=60)
    ap.add_argument("--scale", type=int, default=4)
    a = ap.parse_args()
    sheets = open_sheets(a.quads)
    rows = [
        p
        for p in (
            panel(sheets, *map(float, s.split(",")), a.half) for s in a.at
        )
        if p is not None
    ]
    w = max(r.shape[1] for r in rows)
    rows = [
        np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0)), constant_values=255)
        for r in rows
    ]
    im = Image.fromarray(np.vstack(rows))
    im.resize((im.width * a.scale, im.height * a.scale), Image.NEAREST).save(
        a.out
    )
    print(a.out)


if __name__ == "__main__":
    main()
