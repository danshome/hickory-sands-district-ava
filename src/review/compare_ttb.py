"""compare_ttb.py: where the proposed revision differs from the Map Explorer.

It rings each place where the two differ by more than hand-drawing noise, for
a look in QGIS.

The AVA Map Explorer polygon (TTB's AVAs_Production layer) was digitized by
hand; the proposed revision follows the centre of the printed ink. So the two
always differ a little everywhere. This measures that everyday difference from
the data itself (distance from every 2 m of each boundary to the other
boundary), sets the noise threshold from it (median + K x MAD, never below
--min-threshold), and rings every stretch that is farther apart than that, from
either side (the proposed revision away from the Map Explorer polygon, or the
other way). Each ring says which of the proposed revision's steps it touches,
how far apart the lines are, the acres of the pieces of land between the two
lines that it touches (whole pieces, as in the all-differences layer, so the
figures add up), and whether the step's change register (proposed-steps.json
"change"; a "text correction" does not move the line, so it counts as
unchanged) says the difference is intended or not; rings at least --big m apart
(default 100: TTB's line takes another path, or slips) are flagged big. It also
writes every piece of land inside one polygon and not the other (the sum of all
the differences), each with its side, acres, length, widths, steps and cause.

Usage (the project .venv, -E -s):
  compare_ttb.py --ours-line LINE.geojson --ours-area AREA.geojson
                 (--ttb TTB.geojson | --ttb-url URL --ttb-name NAME)
                 [--steps proposed-steps.json] [--out-dir DIR] [--k 4]
                 [--min-threshold 15] [--threshold M]
Outputs in --out-dir: ttb-diff-rings-EPSG4269.geojson (circles, one per
place), ttb-diff-areas-EPSG4269.geojson (every piece between the two
boundaries), ttb-diff-report.md, ttb-diff-stats.json.
All inputs and outputs are NAD83 (EPSG:4269); distances are measured in NAD83 /
Conus Albers (EPSG:5070) metres.
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

import numpy as np
from osgeo import ogr
from osgeo import osr
from scipy.spatial import cKDTree

ogr.UseExceptions()
SQM_PER_ACRE = 4046.8564224


def tr(src, dst):
    """Returns the transformation between two EPSG codes, in lon/lat order."""
    a = osr.SpatialReference()
    a.ImportFromEPSG(src)
    b = osr.SpatialReference()
    b.ImportFromEPSG(dst)
    for s in (a, b):
        s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(a, b)


TO_M, TO_LL = tr(4269, 5070), tr(5070, 4269)


def to_m(coords):
    """Returns NAD83 lon/lat points as an N x 2 array of EPSG:5070 metres."""
    return np.array(
        [
            TO_M.TransformPoint(x, y)[:2]
            for x, y in ((c[0], c[1]) for c in coords)
        ]
    )


def densify(polyline, step=2.0):
    """Returns points every step m along a polyline, with their arc positions.

    Args:
        polyline: an N x 2 array of points, in metres.
        step: the spacing, in metres.

    Returns:
        (the points, an M x 2 array; their distances along the polyline)
    """
    seg = np.hypot(*np.diff(polyline, axis=0).T)
    arc = np.r_[0, np.cumsum(seg)]
    s = np.arange(0, arc[-1] + 1e-9, step)
    return (
        np.c_[
            np.interp(s, arc, polyline[:, 0]), np.interp(s, arc, polyline[:, 1])
        ],
        s,
    )


def load_ttb(a):
    """Returns TTB's polygons (lists of rings) and properties.

    Read from the file --ttb, or from the feature service --ttb-url (the
    feature named --ttb-name).
    """
    if a.ttb:
        with open(a.ttb) as fh:
            fc = json.load(fh)
    else:
        q = urllib.parse.urlencode(
            {
                "where": f"Name = '{a.ttb_name}'",
                "outFields": "Name,Status",
                "outSR": 4269,
                "f": "geojson",
            }
        )
        with urllib.request.urlopen(
            a.ttb_url.rstrip("/") + "/query?" + q, timeout=60
        ) as r:
            fc = json.load(r)
    feats = fc["features"]
    if len(feats) != 1:
        sys.exit(f"TTB source has {len(feats)} features, expected 1")
    g = feats[0]["geometry"]
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    return polys, feats[0].get("properties", {})


def ogr_poly_m(polys):
    """Returns lon/lat polygons as one valid multipolygon, in EPSG:5070 m."""
    mp = ogr.Geometry(ogr.wkbMultiPolygon)
    for rings in polys:
        p = ogr.Geometry(ogr.wkbPolygon)
        for ring in rings:
            r = ogr.Geometry(ogr.wkbLinearRing)
            for x, y in to_m(ring):
                r.AddPoint_2D(float(x), float(y))
            p.AddGeometry(r)
        mp.AddGeometry(p)
    return mp.MakeValid() if not mp.IsValid() else mp


def poly_area(g):
    """Returns the area of the polygons in g (0 if none, empty or None)."""
    if g is None or g.IsEmpty():
        return 0.0
    t = ogr.GT_Flatten(g.GetGeometryType())
    if t in (ogr.wkbPolygon, ogr.wkbMultiPolygon):
        return g.GetArea()
    return (
        sum(poly_area(g.GetGeometryRef(i)) for i in range(g.GetGeometryCount()))
        if t == ogr.wkbGeometryCollection
        else 0.0
    )


def polygons(g):
    """Returns the polygons of a (multi)polygon or geometry collection."""
    t = ogr.GT_Flatten(g.GetGeometryType())
    if t == ogr.wkbPolygon:
        return [g]
    return (
        [
            q
            for i in range(g.GetGeometryCount())
            for q in polygons(g.GetGeometryRef(i))
        ]
        if t in (ogr.wkbMultiPolygon, ogr.wkbGeometryCollection)
        else []
    )


def geojson_ll(g):
    """Returns an EPSG:5070 geometry as NAD83 lon/lat GeoJSON, 8 decimals."""
    g = g.Clone()
    g.Transform(TO_LL)

    def round_coords(c):
        if isinstance(c[0], float):
            return [round(c[0], 8), round(c[1], 8)]
        return [round_coords(x) for x in c]

    j = json.loads(g.ExportToJson())
    j["coordinates"] = round_coords(j["coordinates"])
    return j


def touched_areas(circ, pieces, rev_only):
    """Returns the area (m2) of the whole pieces of land a ring touches.

    Args:
        circ: the ring (EPSG:5070). Only its outline counts, as published: a
            long stretch's outline can have a hole (issue #26).
        pieces: (polygon, side) pairs, the pieces of land between the lines.
        rev_only: the side of the pieces in the proposed revision only.

    Returns:
        (the area in the proposed revision only, the area in the Map Explorer
        polygon only), each of whole pieces.
    """
    filled = ogr.Geometry(ogr.wkbPolygon)
    filled.AddGeometry(circ.GetGeometryRef(0))  # the ring as published
    touched = [
        (g, side)
        for g, side in pieces
        if g.Intersects(filled) and poly_area(g.Intersection(filled)) > 1.0
    ]
    add = sum(g.GetArea() for g, side in touched if side == rev_only)
    rem = sum(g.GetArea() for g, side in touched if side != rev_only)
    return add, rem


def runs(mask, s, gap):
    """Returns the runs of indexes where mask is true.

    Args:
        mask: a boolean array, one value per sample.
        s: each sample's position along the line, in metres.
        gap: false stretches shorter than this (m along s) are bridged.

    Returns:
        A list of (first index, last index) pairs, in order.
    """
    idx = np.flatnonzero(mask)
    out = []
    if not len(idx):
        return out
    start = prev = idx[0]
    for i in idx[1:]:
        if s[i] - s[prev] > gap:
            out.append((start, prev))
            start = i
        prev = i
    out.append((start, prev))
    return out


def main():
    """Measures, rings and writes the differences (see the module's text)."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ours-line", required=True)
    ap.add_argument("--ours-area", required=True)
    ap.add_argument("--ttb")
    ap.add_argument("--ttb-url")
    ap.add_argument("--ttb-name", default="Hickory Sands District")
    ap.add_argument(
        "--steps",
        help="proposed-steps.json (step -> change register) to mark intended "
        "differences",
    )
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--k", type=float, default=4.0)
    ap.add_argument("--min-threshold", type=float, default=15.0)
    ap.add_argument("--threshold", type=float)
    ap.add_argument(
        "--merge",
        type=float,
        default=60.0,
        help="rings closer than this (m) become one place",
    )
    ap.add_argument(
        "--big",
        type=float,
        default=100.0,
        help="rings at least this far apart (m) are the big differences",
    )
    a = ap.parse_args()
    if not (a.ttb or a.ttb_url):
        sys.exit("give --ttb FILE or --ttb-url URL")
    os.makedirs(a.out_dir, exist_ok=True)
    # ---- ours: the step lines in boundary order, every 2 m, each sample
    # knowing its step
    with open(a.ours_line) as fh:
        line_feats = sorted(
            json.load(fh)["features"], key=lambda f: f["properties"]["step"]
        )
    our_xy, our_s, our_step = [], [], []
    base = 0.0
    for f in line_feats:
        xy = to_m(f["geometry"]["coordinates"])
        if len(xy) < 2:
            continue
        dense, s = densify(xy)
        our_xy.append(dense)
        our_s.append(s + base)
        our_step.append(np.full(len(dense), f["properties"]["step"]))
        base += s[-1] + 2.0
    our_xy, our_s, our_step = (
        np.vstack(our_xy),
        np.concatenate(our_s),
        np.concatenate(our_step),
    )
    with open(a.ours_area) as fh:
        area_f = json.load(fh)["features"][0]["geometry"]
    ours_poly = ogr_poly_m(
        [area_f["coordinates"]]
        if area_f["type"] == "Polygon"
        else area_f["coordinates"]
    )
    # ---- TTB: every ring of the polygon, every 2 m
    tpolys, tprops = load_ttb(a)
    ttb_poly = ogr_poly_m(tpolys)
    ttb_xy, ttb_s = [], []
    base = 0.0
    for rings in tpolys:
        for ring in rings:
            dense, s = densify(to_m(ring))
            ttb_xy.append(dense)
            ttb_s.append(s + base)
            base += s[-1] + 1000.0  # ring breaks never bridge
    ttb_xy, ttb_s = np.vstack(ttb_xy), np.concatenate(ttb_s)
    d_o = cKDTree(ttb_xy).query(our_xy)[0]
    d_t, near_o = cKDTree(our_xy).query(ttb_xy)
    # ---- the everyday (hand-drawn vs ink) difference, from the data
    allv = np.r_[d_o, d_t]
    med = float(np.median(allv))
    mad = float(np.median(np.abs(allv - med)) * 1.4826)
    thr = a.threshold or max(a.min_threshold, med + a.k * mad)
    pct = {
        p: round(float(np.percentile(d_o, p)), 1) for p in (50, 75, 90, 95, 99)
    }
    print(
        "distance from the proposed revision to the Map Explorer polygon, "
        f"percentiles {pct}; median {med:.1f} m, "
        f"MAD {mad:.1f} m -> threshold {thr:.1f} m"
    )
    # ---- stretches farther apart than that, from both sides
    cand = []
    for xy, arc, dist, side in (
        (our_xy, our_s, d_o, "ours"),
        (ttb_xy, ttb_s, d_t, "ttb"),
    ):
        for i0, i1 in runs(dist > thr, arc, 30.0):
            seg = slice(i0, i1 + 1)
            cand.append(
                {
                    "pts": xy[seg],
                    "dmax": float(dist[seg].max()),
                    "len": float(arc[i1] - arc[i0] + 2.0)
                    if side == "ours"
                    else 0.0,
                    "from": side,
                    "i0": i0,
                    "i1": i1,
                    "steps": sorted(set(our_step[seg].tolist()))
                    if side == "ours"
                    else sorted(set(our_step[near_o[seg]].tolist())),
                }
            )
    # pair the two sides of one difference exactly: a TTB run goes with the
    # ours runs its nearest-ours samples land in
    parent = list(range(len(cand)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(i, j):
        parent[find(i)] = find(j)

    ours_ix = [k for k, c in enumerate(cand) if c["from"] == "ours"]
    paired = set()
    for k, c in enumerate(cand):
        if c["from"] != "ttb":
            continue
        hit = set(near_o[c["i0"] : c["i1"] + 1].tolist())
        for j in ours_ix:
            o = cand[j]
            if any(o["i0"] - 25 <= h <= o["i1"] + 25 for h in hit):
                join(k, j)
                paired |= {k, j}
    # runs with no partner: join a neighbour only within a capped distance
    # (never across a whole lobe)
    for k, c in enumerate(cand):
        if k in paired:
            continue
        for j, o in enumerate(cand):
            if j == k:
                continue
            if (
                cKDTree(o["pts"][::2]).query(c["pts"][::2])[0].min()
                <= min(max(c["dmax"], o["dmax"]), 100.0) + a.merge
            ):
                join(k, j)
    groups = {}
    for k in range(len(cand)):
        groups.setdefault(find(k), []).append(cand[k])
    places = []
    for g in groups.values():
        froms = {c["from"] for c in g}
        places.append(
            {
                "pts": np.vstack([c["pts"] for c in g]),
                "dmax": max(c["dmax"] for c in g),
                "len": sum(c["len"] for c in g)
                or max(len(c["pts"]) for c in g) * 2.0,
                "from": "both" if len(froms) > 1 else froms.pop(),
                "steps": sorted(set().union(*[set(c["steps"]) for c in g])),
            }
        )
    # change register: which steps were meant to differ from TTB's text
    reg, kind = {}, {}
    if a.steps:
        with open(a.steps) as fh:
            register = json.load(fh)["steps"]
        for st_ in register:
            reg[st_["step"]] = st_.get("change", "")
            kind[st_["step"]] = (
                "straight line"
                if "straight line" in st_.get("text", "")
                else "follows a feature"
            )

    def changed(st_):
        # a "text correction" (steps (49) and (85): one word of TTB's step
        # corrected) leaves the line TTB's, so it counts as unchanged
        return bool(reg.get(st_, "")) and not reg.get(st_, "").startswith(
            ("unchanged", "text correction")
        )

    def status(steps):
        why = sorted({reg[st_][:70] for st_ in steps if changed(st_)})
        if not why:
            return "CHECK"
        if all(changed(st_) for st_ in steps):
            return "intended: " + "; ".join(why)
        unchanged = ",".join(str(st_) for st_ in steps if not changed(st_))
        return (
            f"CHECK (steps {unchanged} unchanged; partly intended: "
            f"{'; '.join(why)})"
        )

    # our pins (step ends) and TTB's vertices, for "this chord moved because
    # its pin differs"
    pin_xy = {
        f["properties"]["step"]: to_m([f["geometry"]["coordinates"][-1]])[0]
        for f in line_feats
    }
    ttb_vertices = np.vstack([to_m(r) for rings in tpolys for r in rings])
    ttb_vertex_tree = cKDTree(ttb_vertices)
    sym = ours_poly.SymDifference(ttb_poly)
    rev_only = "in the proposed revision only"
    pieces = [
        (
            g,
            rev_only
            if ours_poly.Contains(g.PointOnSurface())
            else "in the Map Explorer polygon only",
        )
        for g in polygons(sym)
        if g.GetArea() > 0
    ]
    out, rows = [], []
    order = sorted(
        places,
        key=lambda p: (min(p["steps"]) if p["steps"] else 999, -p["dmax"]),
    )
    for n, p in enumerate(order, 1):
        c = p["pts"].mean(0)
        rad = float(np.max(np.hypot(*(p["pts"] - c).T)))
        if rad <= 200:  # a short place: one circle round it
            circ = ogr.CreateGeometryFromWkt(
                f"POINT ({c[0]:f} {c[1]:f})"
            ).Buffer(max(40.0, rad + 30.0), 24)
        else:
            # a long stretch: an outline 40 m round both lines, so the ring
            # follows the stretch
            mp = ogr.Geometry(ogr.wkbMultiPoint)
            for x, y in p["pts"][::5]:
                q = ogr.Geometry(ogr.wkbPoint)
                q.AddPoint_2D(float(x), float(y))
                mp.AddGeometry(q)
            circ = (
                mp.Buffer(40.0, 8).ConvexHull()
                if rad <= 600
                else mp.Buffer(40.0, 8).Buffer(20.0, 8).Buffer(-20.0, 8)
            )
            if circ.GetGeometryType() == ogr.wkbMultiPolygon:
                circ = circ.ConvexHull()
        add, rem = touched_areas(circ, pieces, rev_only)
        stt = status(p["steps"])
        ok = stt.startswith("intended")
        kinds = sorted({kind.get(st_, "?") for st_ in p["steps"]})
        pins = [
            st_
            for st_ in sorted(set(p["steps"]) | {st_ - 1 for st_ in p["steps"]})
            if st_ in pin_xy
        ]
        pin_txt = "; ".join(
            f"point {st_:d} is {ttb_vertex_tree.query(pin_xy[st_])[0]:.0f} m "
            "from the Map Explorer polygon's nearest vertex"
            for st_ in pins
        )
        shown = ",".join(map(str, p["steps"][:3])) + (
            "+" if len(p["steps"]) > 3 else ""
        )
        props = {
            "n": n,
            "steps": ",".join(map(str, p["steps"])),
            "kind": ", ".join(kinds),
            "max_apart_m": round(p["dmax"], 1),
            "length_m": round(p["len"]),
            "ours_adds_acres": round(add / SQM_PER_ACRE, 2),
            "ours_drops_acres": round(rem / SQM_PER_ACRE, 2),
            "found_from": p["from"],
            "status": stt,
            "pins": pin_txt,
            "big": int(p["dmax"] >= a.big),
            "label": f"#{n:d} s{shown} {p['dmax']:.0f}m "
            f"{'intended' if ok else 'CHECK'}",
        }
        ring = circ.GetGeometryRef(0)
        ll = [
            list(TO_LL.TransformPoint(*ring.GetPoint_2D(i))[:2])
            for i in range(ring.GetPointCount())
        ]
        out.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[round(x, 8), round(y, 8)] for x, y in ll]
                    ],
                },
                "properties": props,
            }
        )
        lon, lat = TO_LL.TransformPoint(float(c[0]), float(c[1]))[:2]
        rows.append((props, lon, lat))
    fc = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::4269"},
        },
        "features": out,
    }
    with open(
        os.path.join(a.out_dir, "ttb-diff-rings-EPSG4269.geojson"), "w"
    ) as fh:
        json.dump(fc, fh, indent=1)
    # ---- every piece of land inside one polygon and not the other: the sum
    # of all the differences
    our_tree, ttb_tree = cKDTree(our_xy), cKDTree(ttb_xy)
    areas, totals = [], {}
    for g in sorted(polygons(sym), key=lambda g: -g.GetArea()):
        if g.GetArea() <= 0:
            continue
        ext = g.GetGeometryRef(0)
        outline_xy = np.array(
            [ext.GetPoint_2D(i) for i in range(ext.GetPointCount())]
        )
        oi = sorted(
            {
                i
                for near in our_tree.query_ball_point(outline_xy, 3.0)
                for i in near
            }
        )
        ti = sorted(
            {
                i
                for near in ttb_tree.query_ball_point(outline_xy, 3.0)
                for i in near
            }
        )
        cause = (
            "proposed text change"
            if oi and np.mean([changed(int(s_)) for s_ in our_step[oi]]) >= 0.5
            else "drawing"
        )
        side = (
            rev_only
            if ours_poly.Contains(g.PointOnSurface())
            else "in the Map Explorer polygon only"
        )
        acres, length = g.GetArea() / SQM_PER_ACRE, ext.Length() / 2.0
        widest = max(
            float(d_o[oi].max()) if oi else 0.0,
            float(d_t[ti].max()) if ti else 0.0,
        )  # farthest apart along it
        tot = totals.setdefault(
            cause,
            {
                "pieces": 0,
                "revision_only_acres": 0.0,
                "map_explorer_only_acres": 0.0,
            },
        )
        tot["pieces"] += 1
        tot[
            "revision_only_acres"
            if side == "in the proposed revision only"
            else "map_explorer_only_acres"
        ] += acres
        areas.append(
            {
                "type": "Feature",
                "geometry": geojson_ll(g),
                "properties": {
                    "side": side,
                    "cause": cause,
                    "acres": round(acres, 3),
                    "length_m": round(length),
                    "mean_width_m": round(g.GetArea() / max(length, 1.0), 1),
                    "widest_m": round(widest, 1),
                    "steps": ",".join(
                        map(str, sorted({int(s_) for s_ in our_step[oi]}))
                    )
                    if oi
                    else "",
                },
            }
        )
    for tot in totals.values():
        for k in ("revision_only_acres", "map_explorer_only_acres"):
            tot[k] = round(tot[k], 1)
    with open(
        os.path.join(a.out_dir, "ttb-diff-areas-EPSG4269.geojson"), "w"
    ) as fh:
        json.dump(
            {"type": "FeatureCollection", "crs": fc["crs"], "features": areas},
            fh,
        )
    oa = ours_poly.GetArea() / 2589988.110336
    ta = ttb_poly.GetArea() / 2589988.110336
    sweep = {}
    for kk in (3, 4, 5, 6):
        t2 = max(a.min_threshold, med + kk * mad)
        sweep[f"k={kk:d} ({t2:.0f} m)"] = sum(
            1 for _ in runs(d_o > t2, our_s, 30.0)
        )
    stats = {
        "threshold_m": round(thr, 1),
        "stretches_of_ours_beyond_threshold_by_k": sweep,
        "median_m": round(med, 1),
        "mad_m": round(mad, 1),
        "ours_to_ttb_percentiles_m": pct,
        "places": len(out),
        "check": sum(1 for r in rows if r[0]["status"].startswith("CHECK")),
        "ttb": tprops,
        "big_m": a.big,
        "big": sum(1 for r in rows if r[0]["big"]),
        "areas": totals,
        "albers_area_sqmi": {"ours": round(oa, 2), "ttb": round(ta, 2)},
    }
    with open(os.path.join(a.out_dir, "ttb-diff-stats.json"), "w") as fh:
        json.dump(stats, fh, indent=1)
    with open(os.path.join(a.out_dir, "ttb-diff-report.md"), "w") as f:
        f.write(
            "# The proposed revision vs the AVA Map Explorer polygon\n\n"
            "Everyday difference (hand-drawn vs ink centre): "
            f"median {med:.1f} m, MAD {mad:.1f} m; "
            f"rings mark stretches more than **{thr:.1f} m** apart "
            f"(median + {a.k:g} x MAD, at least {a.min_threshold:g} m).\n\n"
        )
        f.write(
            "| # | steps | kind | max apart (m) | length (m) "
            "| in the proposed revision only (ac) "
            "| in the Map Explorer polygon only (ac) | status | pins vs TTB "
            "| lon, lat |\n"
            "|---|---|---|---|---|---|---|---|---|---|\n"
        )
        for p, lon, lat in rows:
            f.write(
                f"| {p['n']:d} | {p['steps']} | {p['kind']} "
                f"| {p['max_apart_m']:.0f} | {p['length_m']:d} "
                f"| {p['ours_adds_acres']:.2f} | {p['ours_drops_acres']:.2f} "
                f"| {p['status']} | {p['pins']} | {lon:.6f}, {lat:.6f} |\n"
            )
        big = ", ".join(f"#{p['n']:d}" for p, _, _ in rows if p["big"])
        f.write(
            f"\nBig differences (at least {a.big:g} m apart): "
            f"{big or 'none'}.\n\n"
            "All the land between the two boundaries "
            "(ttb-diff-areas-EPSG4269.geojson):\n\n"
            "| cause | pieces | in the proposed revision only (ac) "
            "| in the Map Explorer polygon only (ac) |\n|---|---|---|---|\n"
        )
        for cause, tot in sorted(totals.items()):
            f.write(
                f"| {cause} | {tot['pieces']:d} "
                f"| {tot['revision_only_acres']:.1f} "
                f"| {tot['map_explorer_only_acres']:.1f} |\n"
            )
    print(
        "stretches of the proposed revision beyond the threshold, by K:", sweep
    )
    print(
        f"{len(out)} places ringed ({stats['check']} CHECK, "
        f"{len(out) - stats['check']} intended), {stats['big']} at least "
        f"{a.big:g} m apart -> {a.out_dir}"
    )
    print("all the land between the two boundaries:", totals)
    for p, _, _ in rows:
        print(
            f"  #{p['n']:<3d} steps {p['steps']:<10} {p['kind'][:18]:<18} "
            f"{p['max_apart_m']:6.0f} m apart {p['length_m']:6d} m long  "
            f"+{p['ours_adds_acres']:.2f}/-{p['ours_drops_acres']:.2f} ac  "
            f"{p['status'][:60]} | {p['pins'][:90]}"
        )


if __name__ == "__main__":
    main()
