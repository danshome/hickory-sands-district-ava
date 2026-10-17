"""Move the step endpoints (the pins = the AVA boundary points) onto the centre of the printed feature.

The tracer (ink_centerline.py) holds every pin fixed and bends the line in its last metres to reach it, so a pin that
was placed off a road's or contour's centre leaves a hook. Dan, Oct. 16, 2026: the pins have to be perfect.

Method, per pin, for each traced step that starts or ends there:
  - the feature's DIRECTION at the pin is the principal axis of the traced vertices 10-30 m from the pin;
  - the feature's CENTRE at the pin is measured on the raw ink of the sheet (the skill's ink classes), on a cross-
    section through the pin perpendicular to that direction, pooled +-2 m along, with the grader's rules
    (centerline.grade): a double-line road -> midpoint of the two casings; a filled band -> its middle; a contour or
    creek -> middle of the nearest run within 6 m. Where the ink is ambiguous (the crossing feature's ink merges
    with the followed one) the pin is UNMEASURED and left where it is, and listed.
  A straight fit extended to the pin was tried first and is WRONG on bends (a contour that curves 9 m in its last
  30 m gave a 9 m "move" for a pin that sits on the ink): measure at the pin, do not extrapolate.
  - one measurable step at the pin -> the pin moves along that cross-section onto the measured centre (lateral
    move only; the along-track position stays where the hand placed it, e.g. at a junction with a road that is not
    traced);
  - two measurable steps -> the intersection of the two centre lines (each through its measured centre with its
    direction), or the mean of the two lateral moves when they are within 20 deg of parallel.
Writes <work>/pin-moves.json (a proposal; copy it to resources/boundary/tracing/ once reviewed): {step n (the END of step n == start of step n+1): {old, new, moved_m, method, ...}} for every
pin whose move is >= MIN_MOVE m; build_agreed.py applies them to END[n] and the ring vertex, and ink_centerline.py
(write_input) to the priors' endpoints before re-tracing.
Usage (GDAL venv): fix_pins.py [--min-move 0.5] [--apply]   (without --apply: report only)
"""

import json, math, os, sys
import numpy as np

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)  # the repository root
sys.path.insert(0, os.path.join(ROOT, "src", "tracing"))
import centerline as cl
from quadsheets import open_sheets

HERE = os.environ.get("HSD_WORK") or os.path.join(
    ROOT, "target", "work"
)  # build work dir (build.sh stages resources/ here)
TRACED = os.path.join(HERE, "ink-centerline-steps.geojson")
PRIORS = os.path.join(
    ROOT, "resources", "boundary", "tracing", "trace-priors-EPSG4269.geojson"
)
OUT = os.path.join(HERE, "pin-moves.json")
NEAR, FAR = 10.0, 30.0
LANE_STEPS = {
    10,
    11,
    91,
    92,
}  # highway passes drawn 30 m off the road centre (build_agreed.py); not traced
HALF, POOL = 12.0, 2
MIN_MOVE = (
    float(sys.argv[sys.argv.index("--min-move") + 1])
    if "--min-move" in sys.argv
    else 0.5
)
# pins NOT moved by this script, with the reason (Dan decides): --exclude 58,64,82
AUTO = "--auto" in sys.argv
EXCLUDE = (
    {int(x) for x in sys.argv[sys.argv.index("--exclude") + 1].split(",")}
    if "--exclude" in sys.argv
    else set()
)


def frame(lat0):
    return 111320.0 * math.cos(math.radians(lat0)), 110574.0


def resample(P, step=1.0):
    seg = np.hypot(*np.diff(P, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.arange(0, s[-1], step)
    return np.column_stack(
        [np.interp(t, s, P[:, 0]), np.interp(t, s, P[:, 1])]
    ), s[-1]


def direction(coords, at_start, lon0, lat0):
    """unit direction of the feature at the pin from the traced vertices 10-30 m away (pointing away from the pin)"""
    mx, my = frame(lat0)
    P = np.array([[(c[0] - lon0) * mx, (c[1] - lat0) * my] for c in coords])
    if not at_start:
        P = P[::-1]
    R, L = resample(P)
    if L < FAR:
        return None
    W = R[int(NEAR) : int(FAR)]
    c = W.mean(axis=0)
    u, s, vt = np.linalg.svd(W - c, full_matrices=False)
    d = vt[0]
    if float(d @ c) < 0:
        d = -d
    return d


CLIP, EXT = 300.0, 40.0


def free_line(sheets, kind, prior, at_start, lon0, lat0):
    """the feature's centreline THROUGH the pin, free of it: the step's prior clipped to its last CLIP m at the pin end and
    extended EXT m straight beyond the pin (so the pin is an interior point, not a held endpoint), traced with the
    skill's tracer; returns the traced line in metres about the pin"""
    mx, my = frame(lat0)
    P = np.array([[(c[0] - lon0) * mx, (c[1] - lat0) * my] for c in prior])
    if not at_start:
        P = P[::-1]  # P[0] is the pin
    R, L = resample(P)
    R = R[: int(min(L, CLIP))]
    d = R[0] - R[min(len(R) - 1, 25)]
    d = d / np.hypot(*d)  # direction out of the step at the pin
    ext = R[0] + d * EXT
    line = np.vstack([ext[None, :], R])
    ll = [(lon0 + x / mx, lat0 + y / my) for x, y in line]
    coords, st = cl.trace(sheets, ll, kind, label="pin-free")
    return np.array(
        [[(c[0] - lon0) * mx, (c[1] - lat0) * my] for c in coords]
    ), st


def nearest_on(F, p=np.zeros(2)):
    best = None
    for a, b in zip(F, F[1:]):
        ab = b - a
        L2 = float(ab @ ab)
        t = 0 if L2 == 0 else max(0, min(1, float((p - a) @ ab) / L2))
        q = a + ab * t
        dd = float(np.hypot(*(q - p)))
        if best is None or dd < best[0]:
            best = (dd, q, ab / math.sqrt(L2) if L2 else ab)
    return best


def intersect_lines(F1, F2, within=30.0):
    """nearest intersection of two polylines within `within` m of the pin, or None"""
    best = None
    for a, b in zip(F1, F1[1:]):
        if min(np.hypot(*a), np.hypot(*b)) > within:
            continue
        for c, d in zip(F2, F2[1:]):
            if min(np.hypot(*c), np.hypot(*d)) > within:
                continue
            r = b - a
            s_ = d - c
            den = r[0] * s_[1] - r[1] * s_[0]
            if abs(den) < 1e-9:
                continue
            qp = c - a
            t = (qp[0] * s_[1] - qp[1] * s_[0]) / den
            u = (qp[0] * r[1] - qp[1] * r[0]) / den
            if 0 <= t <= 1 and 0 <= u <= 1:
                x = a + r * t
                dd = float(np.hypot(*x))
                if best is None or dd < best[0]:
                    best = (dd, x)
    return best


sheets = open_sheets([ROOT + "/resources/quads/geotiff/*.tif.zip"])
traced = {
    int(f["properties"]["id"]): f for f in json.load(open(TRACED))["features"]
}
priors = {
    f["properties"]["step"]: f for f in json.load(open(PRIORS))["features"]
}
nsteps = max(priors)
pins = {}  # n -> pin = end of step n (== start of step n+1)
for n, f in priors.items():
    c = f["geometry"]["coordinates"]
    pins[n] = tuple(c[-1][:2])
moves = {}
rows = []
unmeasured = []
FREE = []
NEWPINS = []
for n in sorted(pins):
    p_ll = pins[n]
    touching = []
    if n in traced:
        touching.append((n, False))
    nxt = n + 1 if n + 1 <= nsteps else 1
    if nxt in traced:
        touching.append((nxt, True))
    if not touching:
        continue
    lon0, lat0 = p_ll
    mx, my = frame(lat0)
    meas = []
    notes = {}
    for st_, at_start in touching:
        kind = traced[st_]["properties"]["kind"]
        try:
            F, stats = free_line(
                sheets,
                kind,
                priors[st_]["geometry"]["coordinates"],
                at_start,
                lon0,
                lat0,
            )
        except AssertionError as e:
            notes[st_] = f"free trace failed: {e}"
            continue
        dd, q1, dvec = nearest_on(F)
        FREE.append(
            {
                "type": "Feature",
                "properties": {
                    "pin": n,
                    "step": st_,
                    "kind": kind,
                    "w2m": stats["within_2m_pct"],
                    "dist_m": round(dd, 2),
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [round(lon0 + x / mx, 9), round(lat0 + y / my, 9)]
                        for x, y in F
                    ],
                },
            }
        )
        notes[st_] = (
            f"free line {dd:.2f} m from the pin (within 2 m {stats['within_2m_pct']}%)"
        )
        meas.append((st_, F, q1, dvec, dd))
    if not meas:
        unmeasured.append((n, notes))
        rows.append((n, None, "UNMEASURED", notes))
        continue
    if len(meas) == 1:
        st_, F, q, dvec, dd = meas[0]
        method = f"onto step {st_}'s free centreline (nearest point)"
        # the pin is where the feature REACHES a highway lane line (steps 9 -> 10, 90 -> 91: the lane drawn 30 m off
        # the road centre, not traced): the free centreline's crossing of that lane line, not its nearest point
        other = n if st_ != n else nxt
        if other in LANE_STEPS:
            Lc = priors[other]["geometry"]["coordinates"]
            Lm = np.array(
                [[(c[0] - lon0) * mx, (c[1] - lat0) * my] for c in Lc]
            )
            if (
                other == nxt
            ):  # the lane starts at this pin: extend it 60 m back through the pin (the feature may reach the lane's line short of the pin)
                u = Lm[1] - Lm[0]
                u = u / np.hypot(*u)
                Lm = np.vstack([(Lm[0] - u * 60.0)[None, :], Lm])
            else:
                u = Lm[-1] - Lm[-2]
                u = u / np.hypot(*u)
                Lm = np.vstack([Lm, (Lm[-1] + u * 60.0)[None, :]])
            Lm, _ = resample(
                Lm, 2.0
            )  # long segments: resample so the near ones are found
            X = intersect_lines(F, Lm, within=80.0)
            if X is not None:
                q = X[1]
                method = f"where step {st_}'s free centreline crosses the lane line of step {other}"
            else:
                notes[other] = "lane line not crossed within 80 m"
    else:
        (s1, F1, q1, d1, dd1), (s2, F2, q2, d2, dd2) = meas[:2]
        ang = math.degrees(math.acos(min(1, abs(float(d1 @ d2)))))
        X = intersect_lines(F1, F2) if ang >= 20 else None
        if X is not None:
            q = X[1]
            method = f"intersection of the free centrelines of steps {s1} and {s2} ({ang:.0f} deg)"
        else:
            q = (q1 + q2) / 2
            method = f"mean of nearest points on steps {s1}, {s2} ({ang:.0f} deg apart, no crossing within 30 m)"
    moved = float(np.hypot(*q))
    new = (round(lon0 + q[0] / mx, 9), round(lat0 + q[1] / my, 9))
    NEWPINS.append(
        {
            "type": "Feature",
            "properties": {
                "pin": n,
                "moved_m": round(moved, 2),
                "method": method,
            },
            "geometry": {"type": "Point", "coordinates": list(new)},
        }
    )
    rows.append((n, moved, method, notes))
    if n in EXCLUDE:
        rows[-1] = (n, moved, "EXCLUDED (--exclude): " + method, notes)
        continue
    if AUTO:  # only moves the evidence supports without a person looking (the rest are listed for review)
        w2m = min(
            float(v.split("within 2 m ")[1].rstrip("%)"))
            for v in notes.values()
            if "within 2 m" in v
        )
        ok = (
            (
                ("intersection" in method or "crosses the lane" in method)
                and w2m >= 70
            )
            or ("nearest point" in method and moved <= 3.0 and w2m >= 85)
            or ("mean of nearest" in method and moved <= 3.0 and w2m >= 70)
        )
        if not ok and moved >= MIN_MOVE:
            rows[-1] = (n, moved, "REVIEW (not applied): " + method, notes)
            continue
    if moved >= MIN_MOVE:
        moves[str(n)] = {
            "old": list(p_ll),
            "new": list(new),
            "moved_m": round(moved, 2),
            "method": method,
            "free_lines": {str(k): v for k, v in notes.items()},
        }
print(f"{'pin':>4} {'move m':>7}  method | measurement per step")
for n, moved, method, notes in sorted(rows, key=lambda r: -(r[1] or -1)):
    flag = "MOVE" if moved is not None and moved >= MIN_MOVE else "    "
    print(
        f"{n:>4} {moved if moved is not None else float('nan'):7.2f}  {flag} {method} | {notes}"
    )
print(
    f"\n{len(moves)} pins to move (>= {MIN_MOVE} m); {len(unmeasured)} unmeasured (left where they are); {len(rows)} pins on traced steps"
)
json.dump(
    {"type": "FeatureCollection", "features": FREE},
    open(os.path.join(HERE, "review-ink", "pin-free-lines.geojson"), "w"),
)
json.dump(
    {"type": "FeatureCollection", "features": NEWPINS},
    open(os.path.join(HERE, "review-ink", "pin-proposed.geojson"), "w"),
)
print(
    "review layers: review-ink/pin-free-lines.geojson, review-ink/pin-proposed.geojson"
)
if "--apply" in sys.argv:
    json.dump(moves, open(OUT, "w"), indent=1)
    print("wrote", OUT)
