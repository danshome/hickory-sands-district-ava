"""Splices hand-finished stretches into the automatic ink centrelines.

Inputs (both NAD83, EPSG:4269):
  --traced   ink-centerline-steps.geojson (ink_centerline.py output; never
             edited by hand)
  --patches  hand-patches-EPSG4269.geojson: one LineString per edited stretch,
             digitized in QGIS on the scan with the ink-class overlay, FIRST
             and LAST vertex snapped onto the automatic trace (vertex/segment
             snapping to the traced-steps layer only). Fields: step (int), spot
             (problems.json pid), method, who, when, reason.
  --out      the spliced lines (same schema; build_proposed.py reads it in
             place of the automatic file)
Rules: a patch's ends must lie within TOL m of the step's trace (fails loudly
otherwise, e.g. after a re-trace), stay more than PIN_TIE m from both pins
(build_proposed.py drops the vertices that close and ties the line to the
pin) or sit ON a pin (a patch run to the pin; the step gets pin_patched), never
overlap another patch on the step; it may be digitized in either direction.
Every edit is listed, with its provenance, in the step's `hand_edits`.
--patches may be the QGIS GeoPackage (layer hand_patches, EPSG:4269) or a
GeoJSON; --out may never be the --traced file.

Usage: apply_patches.py --patches hand-patches-EPSG4269.gpkg [--traced ...]
       [--out ...]   (exit 1 on any failed check)
"""

import argparse
import itertools
import json
import math
import os
import sys

from osgeo import ogr

ogr.UseExceptions()
FILING = os.environ.get("HSD_WORK") or os.path.join(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ),
    "target",
    "work",
)
TRACED_DEFAULT = os.path.join(FILING, "ink-centerline-steps.geojson")
TOL, PIN_TIE, MAX_SHIFT_WARN = 0.5, 12.0, 15.0


def xy(p, lat0):
    """Returns the point p (lon, lat) in metres, on a flat frame for lat0."""
    return (p[0] * 111320 * math.cos(math.radians(lat0)), p[1] * 110574)


def proj(c, p, lat0):
    """Projects the point p onto the polyline c.

    Args:
        c: the polyline, [(lon, lat)].
        p: the point (lon, lat).
        lat0: the latitude of the flat frame (see xy).

    Returns:
        ((distance m, segment index i, t along that segment, arc position m)
        of c's point nearest p, c's length m).
    """
    pm = xy(p, lat0)
    best = None
    arc = 0.0
    for i in range(len(c) - 1):
        pa, pb = xy(c[i], lat0), xy(c[i + 1], lat0)
        dx, dy = pb[0] - pa[0], pb[1] - pa[1]
        len2 = dx * dx + dy * dy
        t = (
            0.0
            if len2 == 0
            else max(
                0.0,
                min(1.0, ((pm[0] - pa[0]) * dx + (pm[1] - pa[1]) * dy) / len2),
            )
        )
        q = (pa[0] + t * dx, pa[1] + t * dy)
        dd = math.hypot(pm[0] - q[0], pm[1] - q[1])
        if best is None or dd < best[0]:
            best = (dd, i, t, arc + t * math.sqrt(len2))
        arc += math.sqrt(len2)
    return best, arc


def smooth_join(c, j, lat0, reach=8.0, max_dev=2.5):
    """Rounds off the corner at a patch join c[j].

    Replaces the line between the points `reach` m before and after the join
    (A and B) with a cubic Bezier that leaves A and arrives at B along the
    line's own directions there (G1-continuous).

    Args:
        c: the line, [[lon, lat]].
        j: the index of the join's vertex.
        lat0: the latitude of the flat frame (see xy).
        reach: metres along the line from the join to A and to B.
        max_dev: the most the blend may move the line, metres.

    Returns:
        (new c, j_lo, j_hi, the sharpest turn between A and B in degrees, the
        blend's greatest distance from the old line in metres);
        ("left", that turn, that distance) when the blend would move the line
        more than max_dev m (the corner is left for a hand fix); or None when
        the line is too short around the join.
    """
    pts = [xy(q, lat0) for q in c]

    # index of the first vertex at least `dist` m from c[j] along the line
    def walk(k, sign, dist):
        acc = 0.0
        while 0 < k < len(pts) - 1 and acc < dist:
            acc += math.hypot(
                pts[k + sign][0] - pts[k][0], pts[k + sign][1] - pts[k][1]
            )
            k += sign
        return k, acc

    a, da = walk(j, -1, reach)
    b, db = walk(j, +1, reach)
    if da < reach * 0.75 or db < reach * 0.75 or a < 1 or b > len(pts) - 2:
        return None

    def turn(k):
        u = (pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1])
        v = (pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1])
        nu, nv = math.hypot(*u), math.hypot(*v)
        return (
            0.0
            if nu < 1e-6 or nv < 1e-6
            else math.degrees(
                math.acos(
                    max(-1, min(1, (u[0] * v[0] + u[1] * v[1]) / (nu * nv)))
                )
            )
        )

    ang = max(turn(k) for k in range(max(1, a), min(len(pts) - 1, b + 1)))
    pa, pb = pts[a], pts[b]
    ta = (pa[0] - pts[a - 1][0], pa[1] - pts[a - 1][1])
    tb = (pts[b + 1][0] - pb[0], pts[b + 1][1] - pb[1])
    na, nb = math.hypot(*ta) or 1, math.hypot(*tb) or 1
    h = math.hypot(pb[0] - pa[0], pb[1] - pa[1]) / 3
    ctrl1 = (pa[0] + ta[0] / na * h, pa[1] + ta[1] / na * h)
    ctrl2 = (pb[0] - tb[0] / nb * h, pb[1] - tb[1] / nb * h)
    n = max(4, int(math.hypot(pb[0] - pa[0], pb[1] - pa[1])))
    curve = []
    for i in range(1, n):
        t = i / n
        m = 1 - t
        curve.append(
            (
                m**3 * pa[0]
                + 3 * m * m * t * ctrl1[0]
                + 3 * m * t * t * ctrl2[0]
                + t**3 * pb[0],
                m**3 * pa[1]
                + 3 * m * m * t * ctrl1[1]
                + 3 * m * t * t * ctrl2[1]
                + t**3 * pb[1],
            )
        )

    def dseg(q, poly):
        best = 1e9
        for (x1, y1), (x2, y2) in itertools.pairwise(poly):
            dx, dy = x2 - x1, y2 - y1
            len2 = dx * dx + dy * dy
            t = (
                0
                if len2 == 0
                else max(
                    0, min(1, ((q[0] - x1) * dx + (q[1] - y1) * dy) / len2)
                )
            )
            best = min(best, math.hypot(q[0] - x1 - t * dx, q[1] - y1 - t * dy))
        return best

    dev = max(dseg(q, pts[a : b + 1]) for q in curve)
    if dev > max_dev:
        return ("left", ang, dev)
    k0 = 111320 * math.cos(math.radians(lat0))
    newv = [[q[0] / k0, q[1] / 110574] for q in curve]
    return c[: a + 1] + newv + c[b:], a, a + len(newv) + 1, ang, dev


def read_patches(path):
    """Reads the patches from a GeoJSON or any OGR source (a GeoPackage).

    From an OGR source it reads the layer hand_patches, else the first layer
    with geometry. Either must be in EPSG:4269.

    Args:
        path: the patches file.

    Returns:
        ([{"coords": [[lon, lat]], "properties": {...}}], [error messages]).
    """
    errors, out = [], []
    if path.lower().endswith((".geojson", ".json")):
        with open(path) as fh:
            fc = json.load(fh)
        crs = ((fc.get("crs") or {}).get("properties") or {}).get(
            "name", "EPSG:4269"
        )
        if not crs.replace("::", ":").endswith("EPSG:4269"):
            errors.append(f"{path}: CRS {crs} is not EPSG:4269")
        for f in fc["features"]:
            g = f.get("geometry")
            c = []
            if g and g["type"] == "LineString":
                c = [list(q[:2]) for q in g["coordinates"]]
            elif (
                g
                and g["type"] == "MultiLineString"
                and len(g["coordinates"]) == 1
            ):
                c = [list(q[:2]) for q in g["coordinates"][0]]
            elif g:
                errors.append(
                    f"{path}: a {g['type']} patch "
                    f"({f['properties'].get('spot')}): "
                    "draw one single line per patch"
                )
            out.append({"coords": c, "properties": dict(f["properties"])})
        return out, errors
    ds = ogr.Open(path)
    lyrs = [ds.GetLayer(i) for i in range(ds.GetLayerCount())]
    lyrs = [x for x in lyrs if x.GetName() == "hand_patches"] or [
        x for x in lyrs if x.GetGeomType() != ogr.wkbNone
    ]
    if not lyrs:
        return [], [f"{path}: no line layer"]
    lyr = lyrs[0]
    srs = lyr.GetSpatialRef()
    if srs is None or srs.GetAuthorityCode(None) != "4269":
        errors.append(f"{path}: layer {lyr.GetName()} is not EPSG:4269")
    names = [
        lyr.GetLayerDefn().GetFieldDefn(j).GetName()
        for j in range(lyr.GetLayerDefn().GetFieldCount())
    ]
    for f in lyr:
        pr = {
            nm: (
                None
                if not f.IsFieldSetAndNotNull(nm)
                else f.GetFieldAsISO8601DateTime(nm)
                if f.GetFieldDefnRef(nm).GetType() == ogr.OFTDateTime
                else f.GetField(nm)
            )
            for nm in names
        }
        pr["fid"] = f.GetFID()
        g = f.GetGeometryRef()
        c = []
        if g is None or g.IsEmpty():
            errors.append(
                f"patch fid {f.GetFID()} ({pr.get('spot')}): no geometry"
            )
        else:
            g = g.Clone()
            g.FlattenTo2D()
            if (
                g.GetGeometryType() == ogr.wkbMultiLineString
                and g.GetGeometryCount() == 1
            ):
                g = g.GetGeometryRef(0)
            if g.GetGeometryType() != ogr.wkbLineString:
                errors.append(
                    f"patch fid {f.GetFID()} ({pr.get('spot')}): "
                    f"{g.GetGeometryName()}, need one single line"
                )
            else:
                c = [list(p) for p in g.GetPoints()]
        out.append({"coords": c, "properties": pr})
    return out, errors


def _interp(c, i, t):
    """Returns the point t of the way along segment i of the line c."""
    return [
        c[i][0] + t * (c[i + 1][0] - c[i][0]),
        c[i][1] + t * (c[i + 1][1] - c[i][1]),
    ]


def main():
    """Splices the patches into the traces; exits 1 if any check fails."""
    ap = argparse.ArgumentParser(
        description="splice hand patches into the ink centrelines"
    )
    ap.add_argument(
        "--traced",
        default=TRACED_DEFAULT,
        help="automatic traces (default: %(default)s)",
    )
    ap.add_argument(
        "--patches",
        required=True,
        help="hand-patches GeoPackage (layer hand_patches) or GeoJSON, "
        "EPSG:4269",
    )
    ap.add_argument(
        "--out",
        help="spliced lines (default: ink-centerline-steps-patched.geojson "
        "beside --traced)",
    )
    ap.add_argument(
        "--smooth-joins",
        type=float,
        default=0.0,
        metavar="DEG",
        help="round off every patch join that turns more than DEG degrees "
        "(cubic blend 8 m each side, skipped if it would move the line "
        "> 2.5 m)",
    )
    a = ap.parse_args()
    out = a.out or os.path.join(
        os.path.dirname(os.path.abspath(a.traced)),
        "ink-centerline-steps-patched.geojson",
    )
    if os.path.abspath(out) == os.path.abspath(a.traced):
        sys.exit(
            "refusing to overwrite the automatic traces: "
            "--out must differ from --traced"
        )
    with open(a.traced) as fh:
        fc = json.load(fh)
    steps = {int(f["properties"]["id"]): f for f in fc["features"]}
    patches, errors = read_patches(a.patches)
    by_step = {}
    for k, pf in enumerate(patches):
        pr = pf["properties"]
        pc = pf["coords"]
        if pr.get("step") in (None, ""):
            errors.append(f"patch {k} ({pr.get('spot')}): no step number")
            continue
        n = int(pr["step"])
        if len(pc) < 2:
            errors.append(
                f"patch {k} (step {n}, {pr.get('spot')}): fewer than 2 vertices"
            )
            continue
        if n not in steps:
            errors.append(f"patch {k}: step {n} is not a traced step")
            continue
        c = steps[n]["geometry"]["coordinates"]
        lat0 = c[0][1]
        (d0, i0, t0, s0), total = proj(c, pc[0], lat0)
        (d1, i1, t1, s1), _ = proj(c, pc[-1], lat0)
        if max(d0, d1) > TOL:
            errors.append(
                f"patch {k} (step {n}, {pr.get('spot')}): ends {d0:.2f} / "
                f"{d1:.2f} m off the trace (> {TOL} m): snap them onto the "
                "trace"
            )
            continue
        if s0 > s1:
            pc.reverse()
            (s0, i0, t0), (s1, i1, t1) = (s1, i1, t1), (s0, i0, t0)
        # an end either stays more than PIN_TIE m from the pins, or sits ON the
        # pin (a patch run to the pin, Oct. 16, 2026: build_proposed.py then
        # keeps the patch's vertices at that end instead of tying the last 12 m
        # straight)
        at0, at1 = s0 <= TOL, total - s1 <= TOL
        if (s0 < PIN_TIE and not at0) or (total - s1 < PIN_TIE and not at1):
            errors.append(
                f"patch {k} (step {n}): within {PIN_TIE} m of a pin but not "
                "on it -- pins are changed only through pin-moves.json"
            )
            continue
        if at0:
            pr["to_pin"] = "start"
        if at1:
            pr["to_pin"] = "end" if not at0 else "both"
        by_step.setdefault(n, []).append((s0, s1, i0, t0, i1, t1, pc, pr))
    for n, step_patches in by_step.items():
        step_patches.sort(key=lambda q: q[0])
        for u, v in itertools.pairwise(step_patches):
            if v[0] < u[1]:
                errors.append(
                    f"step {n}: patches {u[7].get('spot')} and "
                    f"{v[7].get('spot')} overlap"
                )
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    for n, step_patches in by_step.items():
        f = steps[n]
        c = [list(p) for p in f["geometry"]["coordinates"]]
        lat0 = c[0][1]
        edits = []
        # back to front: indices stay valid
        for s0, s1, i0, t0, i1, t1, pc, pr in sorted(
            step_patches, key=lambda q: -q[0]
        ):
            # the exact join points ON the trace
            a0, a1 = _interp(c, i0, t0), _interp(c, i1, t1)
            old = c[i0 + 1 : i1 + 1]
            new = [a0, *pc[1:-1], a1]
            shift = max([proj(new, p, lat0)[0][0] for p in old] or [0.0])
            c = c[: i0 + 1] + new + c[i1 + 1 :]
            e = {
                "spot": pr.get("spot"),
                "method": pr.get("method"),
                "who": pr.get("who"),
                "when": pr.get("when"),
                "reason": pr.get("reason"),
                "from_m": round(s0, 1),
                "to_m": round(s1, 1),
                "replaced_vertices": len(old),
                "new_vertices": len(pc),
                "max_shift_m": round(shift, 2),
            }
            edits.append(e)
            if shift > MAX_SHIFT_WARN:
                print(
                    f"WARNING step {n} {e['spot']}: patch moves the line "
                    f"{shift:.1f} m -- check it is the same feature"
                )
        if a.smooth_joins > 0:  # Dan, Oct. 16 2026: no angled joins
            for e, (*_, pc, pr) in zip(
                edits, sorted(step_patches, key=lambda q: -q[0]), strict=True
            ):
                for side, q in (("start", pc[0]), ("end", pc[-1])):
                    if pr.get("to_pin") in (side, "both"):
                        continue
                    j = min(
                        range(len(c)),
                        key=lambda k: (
                            (c[k][0] - q[0]) ** 2 + (c[k][1] - q[1]) ** 2
                        ),
                    )
                    if j == 0 or j == len(c) - 1:
                        continue
                    r = smooth_join(c, j, lat0)
                    if r is None:
                        continue
                    if r[0] == "left":
                        if r[1] > a.smooth_joins:
                            e.setdefault("join_left", {})[side] = {
                                "turn_deg": round(r[1], 1),
                                "would_move_m": round(r[2], 2),
                            }
                        continue
                    c2, _lo, _hi, ang, dev = r
                    if ang <= a.smooth_joins:
                        continue
                    c = c2
                    e.setdefault("join_smoothed", {})[side] = {
                        "turn_deg": round(ang, 1),
                        "max_move_m": round(dev, 2),
                    }
        f["geometry"]["coordinates"] = c
        f["properties"]["hand_edits"] = sorted(edits, key=lambda e: e["from_m"])
        pp = sorted(
            {
                w
                for q in step_patches
                for w in {
                    "start": ["start"],
                    "end": ["end"],
                    "both": ["start", "end"],
                }.get(q[7].get("to_pin"), [])
            }
        )
        if pp:
            f["properties"]["pin_patched"] = pp
        f["properties"]["vertices"] = len(c)
        print(
            f"step {n}: {len(edits)} patch(es) spliced:",
            [
                (e["spot"], e["from_m"], e["to_m"], e["max_shift_m"])
                for e in f["properties"]["hand_edits"]
            ],
        )
    with open(out, "w") as fh:
        json.dump(fc, fh)
    print(f"{len(patches)} patch(es) on {len(by_step)} step(s) -> {out}")


if __name__ == "__main__":
    main()
