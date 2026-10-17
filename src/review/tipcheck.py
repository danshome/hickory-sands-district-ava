"""tipcheck.py: does the line reach the end of every tip it turns at?

For each contour/creek step of the FINAL boundary, find every sharp turn (a
hairpin or V: the line turns more than --min-turn degrees within --window m),
take the apex, and walk outward from the apex along the turn's bisector on the
step's own ink class (1 m ink grid from the usgs-quad-trace ink classes). If
the printed ink runs on past our apex by more than --tol m, the line stops
short of the tip: flagged with how far. (Dan, Oct. 16 2026: "On 82 the point
was at the end of that lip, and our line didn't even touch it".) Read-only.

Usage (the project .venv, -E -s):
  tipcheck.py --line FINAL-line.geojson --kinds 6=contour,9=creek,...
              [--out tips.geojson]
  (kinds default: the steps' "kind" from the traced file --traced)
"""

import argparse
import json
import math
import os
import sys

import numpy as np
from scipy import ndimage

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixing"
    ),
)
import patchlib


def interp_xy(q, s, xy):
    """Returns the points at arc positions q along a line.

    Args:
        q: the positions (m along the line).
        s: the line's vertices' positions (m along it).
        xy: the line's vertices, an N x 2 array (m).
    """
    return np.c_[np.interp(q, s, xy[:, 0]), np.interp(q, s, xy[:, 1])]


def main():
    """Finds the tips the line stops short of and writes them as points."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--line", required=True)
    ap.add_argument("--traced", default=patchlib.TRACED)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-turn", type=float, default=100.0)
    ap.add_argument("--window", type=float, default=30.0)
    ap.add_argument("--tol", type=float, default=3.0)
    a = ap.parse_args()
    trace = patchlib.Trace(traced=a.traced)
    kinds = {int(k): f["properties"]["kind"] for k, f in trace.F.items()}
    with open(a.line) as fh:
        lines = {
            f["properties"]["step"]: f["geometry"]["coordinates"]
            for f in json.load(fh)["features"]
        }
    out = []
    for st, coords in sorted(lines.items()):
        if kinds.get(st) not in ("contour", "creek") or st not in trace.F:
            continue
        lat0 = coords[0][1]
        mx = 111320 * math.cos(math.radians(lat0))
        my = 110850.0
        xy = np.array(
            [((c[0] - coords[0][0]) * mx, (c[1] - lat0) * my) for c in coords]
        )
        seg = np.hypot(*np.diff(xy, axis=0).T)
        s = np.r_[0, np.cumsum(seg)]
        if s[-1] < 3 * a.window:
            continue
        ss = np.arange(a.window, s[-1] - a.window, 2.0)
        back, mid, ahead = (
            interp_xy(ss - a.window / 2, s, xy),
            interp_xy(ss, s, xy),
            interp_xy(ss + a.window / 2, s, xy),
        )
        u = back - mid
        v = ahead - mid
        nu = np.linalg.norm(u, axis=1)
        nv = np.linalg.norm(v, axis=1)
        cosang = np.einsum("ij,ij->i", u, v) / np.maximum(nu * nv, 1e-9)
        # 0 = straight, 180 = full hairpin
        turn = 180 - np.degrees(np.arccos(np.clip(cosang, -1, 1)))
        cand = np.flatnonzero(turn > a.min_turn)
        # one apex per cluster: the sharpest point
        groups, cur = [], []
        for i in cand:
            if cur and ss[i] - ss[cur[-1]] > a.window:
                groups.append(cur)
                cur = []
            cur.append(i)
        if cur:
            groups.append(cur)
        for gi in groups:
            i = max(gi, key=lambda k: turn[k])
            apex = mid[i]
            bis = -((u[i] / nu[i]) + (v[i] / nv[i]))
            nb = np.linalg.norm(bis)
            if nb < 1e-6:
                continue
            bis /= nb  # points out of the turn, toward the tip
            lon, lat = coords[0][0] + apex[0] / mx, lat0 + apex[1] / my
            s_tr = trace.nearest_s(st, lon, lat)
            # a tip whose ink grid cannot be read is left out of the report
            try:
                g = patchlib.Grid(
                    trace,
                    st,
                    max(0, s_tr - 40),
                    min(trace.length(st), s_tr + 40),
                    pad=40,
                )
            except Exception:  # noqa: BLE001, S112, RUF100
                continue
            gx, gy = g.xy(lon, lat)
            if kinds[st] == "contour":
                # brown contour ink only: creek dots/dashes (blue, dotlike) are
                # not the contour (Dan, 17:32)
                ink = (g.ink | g.m["brown"]) & ~g.m["blue"]
                if "dotlike" in g.m:
                    ink &= ~g.m["dotlike"]
                # and only the brown blob our line itself runs on (not a
                # separate dot)
                lab, _ = ndimage.label(ink)
                if (
                    0 <= round(gy) < ink.shape[0]
                    and 0 <= round(gx) < ink.shape[1]
                ):
                    near = lab[
                        max(0, int(gy) - 2) : int(gy) + 3,
                        max(0, int(gx) - 2) : int(gx) + 3,
                    ]
                    ids = set(near[near > 0].tolist())
                    if ids:
                        ink = np.isin(lab, list(ids))
            else:
                ink = g.ink | g.m["blue"]
            ux, uy = bis[0], bis[1]
            reach, miss = 0.0, 0
            # walk outward; allow a 3 m gap (dashes, dots)
            for r in np.arange(1.0, 40.0, 1.0):
                px, py = round(gx + ux * r), round(gy + uy * r)
                hit = False
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if (
                            0 <= py + dy < ink.shape[0]
                            and 0 <= px + dx < ink.shape[1]
                            and ink[py + dy, px + dx]
                        ):
                            hit = True
                if hit:
                    reach, miss = r, 0
                else:
                    miss += 1
                    if miss > 3:
                        break
            # half the printed line's width at the tip (measured across the
            # bisector), so "short by" is to the CENTRE of the tip, not its
            # outer edge
            px_, py_ = -uy, ux
            wcnt = 0
            for r in np.arange(-8.0, 8.5, 1.0):
                qx, qy = (
                    round(gx + ux * max(reach - 2.0, 0) + px_ * r),
                    round(gy + uy * max(reach - 2.0, 0) + py_ * r),
                )
                if (
                    0 <= qy < ink.shape[0]
                    and 0 <= qx < ink.shape[1]
                    and ink[qy, qx]
                ):
                    wcnt += 1
            halfw = max(1.0, min(4.0, wcnt / 2.0))
            reach = max(0.0, reach - halfw)
            if reach > a.tol:
                tip = (lon + ux * reach / mx, lat + uy * reach / my)
                out.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [round(tip[0], 8), round(tip[1], 8)],
                        },
                        "properties": {
                            "step": st,
                            "kind": kinds[st],
                            "turn_deg": round(float(turn[i]), 0),
                            "short_by_m": round(reach, 1),
                            "apex_lon": round(lon, 8),
                            "apex_lat": round(lat, 8),
                            "label": f"s{st:d}: tip centre {reach:.0f} m past "
                            "our turn",
                        },
                    }
                )
    fc = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::4269"},
        },
        "features": out,
    }
    with open(a.out, "w") as fh:
        json.dump(fc, fh, indent=1)
    print(f"{len(out)} tips our line stops short of (> {a.tol} m) -> {a.out}")
    for f in sorted(out, key=lambda f: -f["properties"]["short_by_m"]):
        p = f["properties"]
        print(
            f"  step {p['step']:3d} {p['kind']:<7} turn {p['turn_deg']:3.0f} "
            f"deg  tip centre {p['short_by_m']:4.1f} m past our apex  "
            f"at {p['apex_lon']:.6f}, {p['apex_lat']:.6f}"
        )


if __name__ == "__main__":
    main()
