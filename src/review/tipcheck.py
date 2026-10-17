"""tipcheck.py: does the line reach the end of every tip it turns at?

For each contour/creek step of the FINAL boundary, find every sharp turn (a hairpin or V: the line turns more than
--min-turn degrees within --window m), take the apex, and walk outward from the apex along the turn's bisector on the
step's own ink class (1 m ink grid from the usgs-quad-trace ink classes). If the printed ink runs on past our apex by
more than --tol m, the line stops short of the tip: flagged with how far. (Dan, Oct. 16 2026: "On 82 the point was at
the end of that lip, and our line didn't even touch it".) Read-only.

Usage (the project .venv, -E -s): tipcheck.py --line FINAL-line.geojson --kinds 6=contour,9=creek,... [--out tips.geojson]
       (kinds default: the steps' "kind" from the traced file --traced)"""

import argparse, json, math, sys, os
import numpy as np

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixing"
    ),
)
import patchlib as P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--line", required=True)
    ap.add_argument("--traced", default=P.TRACED)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-turn", type=float, default=100.0)
    ap.add_argument("--window", type=float, default=30.0)
    ap.add_argument("--tol", type=float, default=3.0)
    a = ap.parse_args()
    T = P.Trace(traced=a.traced)
    kinds = {int(k): f["properties"]["kind"] for k, f in T.F.items()}
    L = {
        f["properties"]["step"]: f["geometry"]["coordinates"]
        for f in json.load(open(a.line))["features"]
    }
    out = []
    for st, coords in sorted(L.items()):
        if kinds.get(st) not in ("contour", "creek") or st not in T.F:
            continue
        lat0 = coords[0][1]
        mx = 111320 * math.cos(math.radians(lat0))
        my = 110850.0
        X = np.array(
            [((c[0] - coords[0][0]) * mx, (c[1] - lat0) * my) for c in coords]
        )
        seg = np.hypot(*np.diff(X, axis=0).T)
        s = np.r_[0, np.cumsum(seg)]
        if s[-1] < 3 * a.window:
            continue
        ss = np.arange(a.window, s[-1] - a.window, 2.0)

        def at(q):
            return np.c_[np.interp(q, s, X[:, 0]), np.interp(q, s, X[:, 1])]

        A, B, C = at(ss - a.window / 2), at(ss), at(ss + a.window / 2)
        u = A - B
        v = C - B
        nu = np.linalg.norm(u, axis=1)
        nv = np.linalg.norm(v, axis=1)
        cosang = np.einsum("ij,ij->i", u, v) / np.maximum(nu * nv, 1e-9)
        turn = 180 - np.degrees(
            np.arccos(np.clip(cosang, -1, 1))
        )  # 0 = straight, 180 = full hairpin
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
            apex = B[i]
            bis = -((u[i] / nu[i]) + (v[i] / nv[i]))
            nb = np.linalg.norm(bis)
            if nb < 1e-6:
                continue
            bis /= nb  # points out of the turn, toward the tip
            lon, lat = coords[0][0] + apex[0] / mx, lat0 + apex[1] / my
            s_tr = T.nearest_s(st, lon, lat)
            try:
                g = P.Grid(
                    T,
                    st,
                    max(0, s_tr - 40),
                    min(T.length(st), s_tr + 40),
                    pad=40,
                )
            except Exception:
                continue
            gx, gy = g.xy(lon, lat)
            if (
                kinds[st] == "contour"
            ):  # brown contour ink only: creek dots/dashes (blue, dotlike) are not the contour (Dan, 17:32)
                ink = (g.ink | g.m["brown"]) & ~g.m["blue"]
                if "dotlike" in g.m:
                    ink &= ~g.m["dotlike"]
                from scipy import ndimage as _nd

                lab, nl = _nd.label(
                    ink
                )  # and only the brown blob our line itself runs on (not a separate dot)
                if (
                    0 <= int(round(gy)) < ink.shape[0]
                    and 0 <= int(round(gx)) < ink.shape[1]
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
            for r in np.arange(
                1.0, 40.0, 1.0
            ):  # walk outward; allow a 3 m gap (dashes, dots)
                px, py = int(round(gx + ux * r)), int(round(gy + uy * r))
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
            # half the printed line's width at the tip (measured across the bisector), so "short by" is to the
            # CENTRE of the tip, not its outer edge
            px_, py_ = -uy, ux
            wcnt = 0
            for r in np.arange(-8.0, 8.5, 1.0):
                qx, qy = (
                    int(round(gx + ux * max(reach - 2.0, 0) + px_ * r)),
                    int(round(gy + uy * max(reach - 2.0, 0) + py_ * r)),
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
                            "label": "s%d: tip centre %.0f m past our turn"
                            % (st, reach),
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
    json.dump(fc, open(a.out, "w"), indent=1)
    print(f"{len(out)} tips our line stops short of (> {a.tol} m) -> {a.out}")
    for f in sorted(out, key=lambda f: -f["properties"]["short_by_m"]):
        p = f["properties"]
        print(
            "  step %3d %-7s turn %3.0f deg  tip centre %4.1f m past our apex  at %.6f, %.6f"
            % (
                p["step"],
                p["kind"],
                p["turn_deg"],
                p["short_by_m"],
                p["apex_lon"],
                p["apex_lat"],
            )
        )


if __name__ == "__main__":
    main()
