"""compare_ttb.py: find where our boundary differs from TTB's published AVA polygon by more than hand-drawing noise,
and ring each place for a look in QGIS.

TTB's polygon (AVAs_Production) was digitized by hand; ours follows the centre of the printed ink. So the two always
differ a little everywhere. This measures that everyday difference from the data itself (distance from every 2 m of
each boundary to the other boundary), sets the noise threshold from it (median + K x MAD, never below --min-threshold),
and rings every stretch that is farther apart than that, from either side (ours away from TTB, or TTB away from ours).
Each ring says which of our steps it touches, how far apart the lines are, the acres of the pieces of land between the
two lines that it touches (whole pieces, as in the all-differences layer, so the figures add up), and whether the
step's change register (agreed-steps.json "change"; a "text correction" does not move the line, so it counts as unchanged)
says the difference is intended or not; rings at least --big m apart (default 100: TTB's line takes another path, or
slips) are flagged big. It also writes every piece of land inside one polygon and not the other (the sum of all the
differences), each with its side, acres, length, widths, steps and cause.

Usage (the project .venv, -E -s):
  compare_ttb.py --ours-line LINE.geojson --ours-area AREA.geojson (--ttb TTB.geojson | --ttb-url URL --ttb-name NAME)
                 [--steps agreed-steps.json] [--out-dir DIR] [--k 4] [--min-threshold 15] [--threshold M]
Outputs in --out-dir: ttb-diff-rings-EPSG4269.geojson (circles, one per place), ttb-diff-areas-EPSG4269.geojson (every
piece between the two boundaries), ttb-diff-report.md, ttb-diff-stats.json.
All inputs and outputs are NAD83 (EPSG:4269); distances are measured in NAD83 / Conus Albers (EPSG:5070) metres."""
import argparse, json, os, sys, urllib.parse, urllib.request
import numpy as np
from scipy.spatial import cKDTree
from osgeo import ogr, osr
ogr.UseExceptions()
SQM_PER_ACRE = 4046.8564224

def tr(src, dst):
    a = osr.SpatialReference(); a.ImportFromEPSG(src); b = osr.SpatialReference(); b.ImportFromEPSG(dst)
    for s in (a, b): s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(a, b)
TO_M, TO_LL = tr(4269, 5070), tr(5070, 4269)

def to_m(coords): return np.array([TO_M.TransformPoint(x, y)[:2] for x, y in ((c[0], c[1]) for c in coords)])

def densify(P, step=2.0):
    """points every `step` m along polyline P (N x 2), with their arc position"""
    seg = np.hypot(*np.diff(P, axis=0).T); arc = np.r_[0, np.cumsum(seg)]
    s = np.arange(0, arc[-1] + 1e-9, step)
    return np.c_[np.interp(s, arc, P[:, 0]), np.interp(s, arc, P[:, 1])], s

def load_ttb(a):
    if a.ttb:
        fc = json.load(open(a.ttb))
    else:
        q = urllib.parse.urlencode({"where": "Name = '%s'" % a.ttb_name, "outFields": "Name,Status", "outSR": 4269, "f": "geojson"})
        with urllib.request.urlopen(a.ttb_url.rstrip("/") + "/query?" + q, timeout=60) as r: fc = json.load(r)
    feats = fc["features"]
    if len(feats) != 1: sys.exit(f"TTB source has {len(feats)} features, expected 1")
    g = feats[0]["geometry"]
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    return polys, feats[0].get("properties", {})

def ogr_poly_m(polys):
    mp = ogr.Geometry(ogr.wkbMultiPolygon)
    for rings in polys:
        p = ogr.Geometry(ogr.wkbPolygon)
        for ring in rings:
            r = ogr.Geometry(ogr.wkbLinearRing)
            for x, y in to_m(ring): r.AddPoint_2D(float(x), float(y))
            p.AddGeometry(r)
        mp.AddGeometry(p)
    return mp.MakeValid() if not mp.IsValid() else mp

def poly_area(g):
    if g is None or g.IsEmpty(): return 0.0
    t = ogr.GT_Flatten(g.GetGeometryType())
    if t in (ogr.wkbPolygon, ogr.wkbMultiPolygon): return g.GetArea()
    return sum(poly_area(g.GetGeometryRef(i)) for i in range(g.GetGeometryCount())) if t == ogr.wkbGeometryCollection else 0.0

def polygons(g):   # the polygons of a (multi)polygon or collection
    t = ogr.GT_Flatten(g.GetGeometryType())
    if t == ogr.wkbPolygon: return [g]
    return [q for i in range(g.GetGeometryCount()) for q in polygons(g.GetGeometryRef(i))] if t in (ogr.wkbMultiPolygon, ogr.wkbGeometryCollection) else []

def geojson_ll(g):   # metres (EPSG:5070) -> NAD83 lon/lat GeoJSON geometry, 8 decimals
    g = g.Clone(); g.Transform(TO_LL)
    r = lambda c: [round(c[0], 8), round(c[1], 8)] if isinstance(c[0], float) else [r(x) for x in c]
    j = json.loads(g.ExportToJson()); j["coordinates"] = r(j["coordinates"]); return j

def runs(mask, s, gap):
    """contiguous index runs where mask is true, bridging gaps shorter than `gap` m along s"""
    idx = np.flatnonzero(mask); out = []
    if not len(idx): return out
    start = prev = idx[0]
    for i in idx[1:]:
        if s[i] - s[prev] > gap: out.append((start, prev)); start = i
        prev = i
    out.append((start, prev)); return out

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ours-line", required=True); ap.add_argument("--ours-area", required=True)
    ap.add_argument("--ttb"); ap.add_argument("--ttb-url"); ap.add_argument("--ttb-name", default="Hickory Sands District")
    ap.add_argument("--steps", help="agreed-steps.json (step -> change register) to mark intended differences")
    ap.add_argument("--out-dir", default="."); ap.add_argument("--k", type=float, default=4.0)
    ap.add_argument("--min-threshold", type=float, default=15.0); ap.add_argument("--threshold", type=float)
    ap.add_argument("--merge", type=float, default=60.0, help="rings closer than this (m) become one place")
    ap.add_argument("--big", type=float, default=100.0, help="rings at least this far apart (m) are the big differences")
    a = ap.parse_args()
    if not (a.ttb or a.ttb_url): sys.exit("give --ttb FILE or --ttb-url URL")
    os.makedirs(a.out_dir, exist_ok=True)
    # ---- ours: the step lines in boundary order, every 2 m, each sample knowing its step
    L = sorted(json.load(open(a.ours_line))["features"], key=lambda f: f["properties"]["step"])
    OP, OS, OST = [], [], []; base = 0.0
    for f in L:
        P = to_m(f["geometry"]["coordinates"])
        if len(P) < 2: continue
        Q, s = densify(P); OP.append(Q); OS.append(s + base); OST.append(np.full(len(Q), f["properties"]["step"])); base += s[-1] + 2.0
    OP, OS, OST = np.vstack(OP), np.concatenate(OS), np.concatenate(OST)
    area_f = json.load(open(a.ours_area))["features"][0]["geometry"]
    ours_poly = ogr_poly_m([area_f["coordinates"]] if area_f["type"] == "Polygon" else area_f["coordinates"])
    # ---- TTB: every ring of the polygon, every 2 m
    tpolys, tprops = load_ttb(a); ttb_poly = ogr_poly_m(tpolys)
    TP, TS = [], []; base = 0.0
    for rings in tpolys:
        for ring in rings:
            Q, s = densify(to_m(ring)); TP.append(Q); TS.append(s + base); base += s[-1] + 1000.0   # ring breaks never bridge
    TP, TS = np.vstack(TP), np.concatenate(TS)
    d_o = cKDTree(TP).query(OP)[0]; d_t, near_o = cKDTree(OP).query(TP)
    # ---- the everyday (hand-drawn vs ink) difference, from the data
    allv = np.r_[d_o, d_t]; med = float(np.median(allv)); mad = float(np.median(np.abs(allv - med)) * 1.4826)
    thr = a.threshold or max(a.min_threshold, med + a.k * mad)
    pct = {p: round(float(np.percentile(d_o, p)), 1) for p in (50, 75, 90, 95, 99)}
    print(f"ours->TTB distance percentiles {pct}; median {med:.1f} m, MAD {mad:.1f} m -> threshold {thr:.1f} m")
    # ---- stretches farther apart than that, from both sides
    cand = []
    for P, S, D, side in ((OP, OS, d_o, "ours"), (TP, TS, d_t, "ttb")):
        for i0, i1 in runs(D > thr, S, 30.0):
            seg = slice(i0, i1 + 1)
            cand.append({"pts": P[seg], "dmax": float(D[seg].max()), "len": float(S[i1] - S[i0] + 2.0) if side == "ours" else 0.0,
                         "from": side, "i0": i0, "i1": i1,
                         "steps": sorted(set(OST[seg].tolist())) if side == "ours" else sorted(set(OST[near_o[seg]].tolist()))})
    # pair the two sides of one difference exactly: a TTB run goes with the ours runs its nearest-ours samples land in
    parent = list(range(len(cand)))
    def find(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    def join(i, j): parent[find(i)] = find(j)
    ours_ix = [k for k, c in enumerate(cand) if c["from"] == "ours"]
    paired = set()
    for k, c in enumerate(cand):
        if c["from"] != "ttb": continue
        hit = set(near_o[c["i0"]:c["i1"] + 1].tolist())
        for j in ours_ix:
            o = cand[j]
            if any(o["i0"] - 25 <= h <= o["i1"] + 25 for h in hit): join(k, j); paired |= {k, j}
    # runs with no partner: join a neighbour only within a capped distance (never across a whole lobe)
    for k, c in enumerate(cand):
        if k in paired: continue
        for j, o in enumerate(cand):
            if j == k: continue
            if cKDTree(o["pts"][::2]).query(c["pts"][::2])[0].min() <= min(max(c["dmax"], o["dmax"]), 100.0) + a.merge: join(k, j)
    groups = {}
    for k in range(len(cand)): groups.setdefault(find(k), []).append(cand[k])
    places = []
    for g in groups.values():
        froms = {c["from"] for c in g}
        places.append({"pts": np.vstack([c["pts"] for c in g]), "dmax": max(c["dmax"] for c in g),
                       "len": sum(c["len"] for c in g) or max(len(c["pts"]) for c in g) * 2.0,
                       "from": "both" if len(froms) > 1 else froms.pop(), "steps": sorted(set().union(*[set(c["steps"]) for c in g]))})
    # change register: which steps were meant to differ from TTB's text
    reg, kind = {}, {}
    if a.steps:
        for st_ in json.load(open(a.steps))["steps"]:
            reg[st_["step"]] = st_.get("change", ""); kind[st_["step"]] = "straight line" if "straight line" in st_.get("text", "") else "follows a feature"
    # a "text correction" (steps (49) and (85): one word of TTB's step corrected) leaves the line TTB's, so it counts as unchanged
    changed = lambda st_: bool(reg.get(st_, "")) and not reg.get(st_, "").startswith(("unchanged", "text correction"))
    def status(steps):
        why = sorted({reg[st_][:70] for st_ in steps if changed(st_)})
        if not why: return "CHECK"
        if all(changed(st_) for st_ in steps): return "intended: " + "; ".join(why)
        return "CHECK (steps %s unchanged; partly intended: %s)" % (",".join(str(st_) for st_ in steps if not changed(st_)), "; ".join(why))
    # our pins (step ends) and TTB's vertices, for "this chord moved because its pin differs"
    PINS = {f["properties"]["step"]: to_m([f["geometry"]["coordinates"][-1]])[0] for f in L}
    TV = np.vstack([to_m(r) for rings in tpolys for r in rings]); TVt = cKDTree(TV)
    sym = ours_poly.SymDifference(ttb_poly)
    REV_ONLY = "in the proposed revision only"
    pieces = [(g, REV_ONLY if ours_poly.Contains(g.PointOnSurface()) else "in the Map Explorer polygon only")
              for g in polygons(sym) if g.GetArea() > 0]
    out, rows = [], []
    order = sorted(places, key=lambda p: (min(p["steps"]) if p["steps"] else 999, -p["dmax"]))
    for n, p in enumerate(order, 1):
        c = p["pts"].mean(0); rad = float(np.max(np.hypot(*(p["pts"] - c).T)))
        if rad <= 200:        # a short place: one circle round it
            circ = ogr.CreateGeometryFromWkt("POINT (%f %f)" % (c[0], c[1])).Buffer(max(40.0, rad + 30.0), 24)
        else:                 # a long stretch: an outline 40 m round both lines, so the ring follows the stretch
            mp = ogr.Geometry(ogr.wkbMultiPoint)
            for x, y in p["pts"][::5]:
                q = ogr.Geometry(ogr.wkbPoint); q.AddPoint_2D(float(x), float(y)); mp.AddGeometry(q)
            circ = mp.Buffer(40.0, 8).ConvexHull() if rad <= 600 else mp.Buffer(40.0, 8).Buffer(20.0, 8).Buffer(-20.0, 8)
            if circ.GetGeometryType() == ogr.wkbMultiPolygon: circ = circ.ConvexHull()
        filled = ogr.Geometry(ogr.wkbPolygon); filled.AddGeometry(circ.GetGeometryRef(0))   # the ring as published: its outline
        touched = [(g, side) for g, side in pieces if g.Intersects(filled) and poly_area(g.Intersection(filled)) > 1.0]
        add = sum(g.GetArea() for g, side in touched if side == REV_ONLY)        # whole pieces (issue #26: a long stretch's
        rem = sum(g.GetArea() for g, side in touched if side != REV_ONLY)        # outline can have a hole; only its outline shows)
        stt = status(p["steps"]); ok = stt.startswith("intended")
        kinds = sorted({kind.get(st_, "?") for st_ in p["steps"]})
        pins = [st_ for st_ in sorted(set(p["steps"]) | {st_ - 1 for st_ in p["steps"]}) if st_ in PINS]
        pin_txt = "; ".join("point %d is %.0f m from the Map Explorer polygon's nearest vertex" % (st_, TVt.query(PINS[st_])[0]) for st_ in pins)
        props = {"n": n, "steps": ",".join(map(str, p["steps"])), "kind": ", ".join(kinds), "max_apart_m": round(p["dmax"], 1), "length_m": round(p["len"]),
                 "ours_adds_acres": round(add / SQM_PER_ACRE, 2), "ours_drops_acres": round(rem / SQM_PER_ACRE, 2),
                 "found_from": p["from"], "status": stt, "pins": pin_txt, "big": int(p["dmax"] >= a.big),
                 "label": "#%d s%s %.0fm %s" % (n, ",".join(map(str, p["steps"][:3])) + ("+" if len(p["steps"]) > 3 else ""), p["dmax"], "intended" if ok else "CHECK")}
        ring = circ.GetGeometryRef(0); ll = [list(TO_LL.TransformPoint(*ring.GetPoint_2D(i))[:2]) for i in range(ring.GetPointCount())]
        out.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[round(x, 8), round(y, 8)] for x, y in ll]]}, "properties": props})
        lon, lat = TO_LL.TransformPoint(float(c[0]), float(c[1]))[:2]; rows.append((props, lon, lat))
    fc = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4269"}}, "features": out}
    json.dump(fc, open(os.path.join(a.out_dir, "ttb-diff-rings-EPSG4269.geojson"), "w"), indent=1)
    # ---- every piece of land inside one polygon and not the other: the sum of all the differences
    our_tree, ttb_tree = cKDTree(OP), cKDTree(TP)
    areas, totals = [], {}
    for g in sorted(polygons(sym), key=lambda g: -g.GetArea()):
        if g.GetArea() <= 0: continue
        ext = g.GetGeometryRef(0); B = np.array([ext.GetPoint_2D(i) for i in range(ext.GetPointCount())])
        oi = sorted({i for l in our_tree.query_ball_point(B, 3.0) for i in l}); ti = sorted({i for l in ttb_tree.query_ball_point(B, 3.0) for i in l})
        cause = "proposed text change" if oi and np.mean([changed(int(s_)) for s_ in OST[oi]]) >= 0.5 else "drawing"
        side = REV_ONLY if ours_poly.Contains(g.PointOnSurface()) else "in the Map Explorer polygon only"
        acres, length = g.GetArea() / SQM_PER_ACRE, ext.Length() / 2.0
        widest = max(float(d_o[oi].max()) if oi else 0.0, float(d_t[ti].max()) if ti else 0.0)   # farthest apart along it
        tot = totals.setdefault(cause, {"pieces": 0, "revision_only_acres": 0.0, "map_explorer_only_acres": 0.0})
        tot["pieces"] += 1; tot["revision_only_acres" if side == "in the proposed revision only" else "map_explorer_only_acres"] += acres
        areas.append({"type": "Feature", "geometry": geojson_ll(g), "properties": {
            "side": side, "cause": cause, "acres": round(acres, 3), "length_m": round(length), "mean_width_m": round(g.GetArea() / max(length, 1.0), 1),
            "widest_m": round(widest, 1), "steps": ",".join(map(str, sorted({int(s_) for s_ in OST[oi]}))) if oi else ""}})
    for tot in totals.values():
        for k in ("revision_only_acres", "map_explorer_only_acres"): tot[k] = round(tot[k], 1)
    json.dump({"type": "FeatureCollection", "crs": fc["crs"], "features": areas}, open(os.path.join(a.out_dir, "ttb-diff-areas-EPSG4269.geojson"), "w"))
    oa = ours_poly.GetArea() / 2589988.110336; ta = ttb_poly.GetArea() / 2589988.110336
    sweep = {}
    for kk in (3, 4, 5, 6):
        t2 = max(a.min_threshold, med + kk * mad)
        sweep["k=%d (%.0f m)" % (kk, t2)] = sum(1 for _ in runs(d_o > t2, OS, 30.0))
    stats = {"threshold_m": round(thr, 1), "stretches_of_ours_beyond_threshold_by_k": sweep, "median_m": round(med, 1), "mad_m": round(mad, 1), "ours_to_ttb_percentiles_m": pct,
             "places": len(out), "check": sum(1 for r in rows if r[0]["status"].startswith("CHECK")), "ttb": tprops,
             "big_m": a.big, "big": sum(1 for r in rows if r[0]["big"]), "areas": totals,
             "albers_area_sqmi": {"ours": round(oa, 2), "ttb": round(ta, 2)}}
    json.dump(stats, open(os.path.join(a.out_dir, "ttb-diff-stats.json"), "w"), indent=1)
    with open(os.path.join(a.out_dir, "ttb-diff-report.md"), "w") as f:
        f.write("# Our boundary vs TTB's published polygon\n\nEveryday difference (hand-drawn vs ink centre): median %.1f m, MAD %.1f m; "
                "rings mark stretches more than **%.1f m** apart (median + %g x MAD, at least %g m).\n\n" % (med, mad, thr, a.k, a.min_threshold))
        f.write("| # | steps | kind | max apart (m) | length (m) | ours adds (ac) | ours drops (ac) | status | pins vs TTB | lon, lat |\n|---|---|---|---|---|---|---|---|---|---|\n")
        for p, lon, lat in rows:
            f.write("| %d | %s | %s | %.0f | %d | %.2f | %.2f | %s | %s | %.6f, %.6f |\n" % (p["n"], p["steps"], p["kind"], p["max_apart_m"], p["length_m"], p["ours_adds_acres"], p["ours_drops_acres"], p["status"], p["pins"], lon, lat))
        f.write("\nBig differences (at least %g m apart): %s.\n\nAll the land between the two boundaries (ttb-diff-areas-EPSG4269.geojson):\n\n"
                "| cause | pieces | in the proposed revision only (ac) | in the Map Explorer polygon only (ac) |\n|---|---|---|---|\n"
                % (a.big, ", ".join("#%d" % p["n"] for p, _, _ in rows if p["big"]) or "none"))
        for cause, tot in sorted(totals.items()):
            f.write("| %s | %d | %.1f | %.1f |\n" % (cause, tot["pieces"], tot["revision_only_acres"], tot["map_explorer_only_acres"]))
    print("stretches of ours beyond the threshold, by K:", sweep)
    print(f"{len(out)} places ringed ({stats['check']} CHECK, {len(out) - stats['check']} intended), {stats['big']} at least {a.big:g} m apart -> {a.out_dir}")
    print("all the land between the two boundaries:", totals)
    for p, lon, lat in rows: print("  #%-3d steps %-10s %-18s %6.0f m apart %6d m long  +%.2f/-%.2f ac  %s | %s" % (p["n"], p["steps"], p["kind"][:18], p["max_apart_m"], p["length_m"], p["ours_adds_acres"], p["ours_drops_acres"], p["status"][:60], p["pins"][:90]))

if __name__ == "__main__":
    main()
