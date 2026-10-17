"""featurecheck.py -- THE ACCEPTANCE CHECK for traced lines: is each line on the RIGHT feature, not just near ink?

Why: grade() (centerline.py) asks every metre "is there ink of this class within 6 m, and how far is its centre?". It
never asks whether that ink is the SAME line the trace was on a few metres before, so a contour trace that hops onto
the neighbouring contour on a steep slope is graded "centred" on the wrong contour (Oct. 16, 2026: last night's step 65
spent 343 m on the next contour and grade() gave that stretch 91% measured, 100% within 2 m, median 0.25 m). The checks
here look at IDENTITY and SHAPE, on the raw ink (no gap closing, no lettering/digit removal), independent of the tracer
and of the prior (the prior is only drawn on the crops):

  hop        lane continuity in a straightened frame: cross-sections every 1 m (+-15 m, 0.5 m steps) of the feature's raw
             ink (contours: brown), runs tracked row to row into lanes; the lane under the line (|off| <= 1.5 m) is the
             one it rides. Where it stops riding a lane and some long line seen at the leaving point carries on BESIDE
             it (>= 20 m at >= 3 m off, or >= 10 m reaching >= 6 m; white paper between; not the line itself elsewhere,
             e.g. the other arm of a V) -- or where it starts riding a lane that already ran beside it -- that is a hop.
             A label/gap bridged correctly (line ends, line resumes) gives neither. A hop-out followed within 600 m by a
             hop-in is an excursion: every metre between is flagged ("metres on the wrong line").
  crossing   (contours) a long line passes from one side of the trace to the other: contours never cross.
  wiggle     total |turn| - |net turn| over 40 m > 150 deg while >= 5 m of the window is off long-line ink (digits).
  bridge     off long-line ink (pieces >= 40 m) for 8-400 m: max distance from the Hermite bridge continuing the ink's
             direction either side > max(3 m, 5% of the chord).
  wrongclass the line rides another class's long ink for >= 10 m (contours: blue; creeks: brown/black).
  road_leave (roads) the line crosses a long casing lane.          selfx / stepx  crosses itself / another step.
Per metre (the 10 m at each pin excluded, as in grade()): VERIFIED = grade() within 2 m AND riding one continuous,
unambiguous lane (roads: a casing each side) AND no event within 20 m; FLAGGED = inside an event +-20 m, an excursion,
or graded > 2 m off over >= 3 m; UNMEASURED = the rest. Dan's rule: unmeasured is not verified.

Validated Oct. 16, 2026 on the 5 contours (3 6 59 65 82) of three traced versions: fires at all 4 owner-reported spots
and at 19-20 of the 23 critic "off" contour spots; quiet at 35 of 44 critic "centred" spots, and 6-7 of the other 9 were
real defects the critics passed (the 885 hop, loops through 1800/1500 labels); on the 3.5 km where last night's contours
and today's disagree by > 3 m, grade() passes 71% of last night's metres and this check verifies 22.5%. Precision on
non-label identity events about 8 in 13. Creek and road modes RUN but are NOT validated (dotted creeks give short lanes):
their queue items say so. Known blind spots (BLIND_SPOTS below) are always queued for a person.

CLI (the project .venv, -E -s):
  featurecheck.py --quads "GLOB" --traced traced.geojson --out-dir DIR [--ids 3 6 ...] [--prior lines.geojson] [--no-crops]
Writes DIR/per_step.csv (current-check figures, VERIFIED/FLAGGED/UNMEASURED %, metres, events by type, metres on the
wrong line), DIR/queue.geojson (one point per review item: events and unmeasured stretches >= 15 m clustered within
60 m along the line, plus the known blind spots; step, types, lon/lat, size, crop path, validated, status, priority
0 blind spot / 1 identity / 2 shape / 3 unmeasured) and DIR/crops/*.png (one close-up per item). Read only on its inputs.
Acceptance (per step): no open queue items (each fixed and re-run, or signed off by Dan on its crop), VERIFIED plus
signed-off metres >= 95%, no owner/critic "off" spot VERIFIED, no selfx/stepx, pins within 2 m or listed."""

import argparse, csv, json, math, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
import centerline as cl
import ink as inklib
from quadsheets import open_sheets

HALF, DO = 15.0, 0.5  # cross-section half-width and step (m)
RIDE = 1.5  # |offset| of the lane under the line
BESIDE = 3.0  # a lane this far off is "beside" the line, not under it
LOOK = 60  # m before/after a switch where an abandoned / pre-existing lane is looked for
BESIDE_MIN = 10  # m of the lane seen beside the line in that window
LANE_MIN = (
    15  # lanes shorter than this (digit strokes, ticks, noise) are not lines
)
GATE, COAST = (
    1.5,
    8,
)  # tracking: max offset change per row (m), rows a lane may go unseen
EVENT_PAD = 20  # m either side of an event that is FLAGGED
WIGGLE_DEG, WIGGLE_WIN = 150.0, 40
END_SKIP = 10  # m at each end (the pins, reported separately as in grade())


# ---------------------------------------------------------------- sampling
def sheet_index(sheets, lons, lats):
    idx = np.full(len(lons), -1)
    for k, sh in enumerate(sheets):
        todo = np.flatnonzero(idx < 0)
        if not len(todo):
            break
        _, _, inside, _ = sh.pixels(lons[todo], lats[todo])
        idx[todo[inside]] = k
    return idx


class StepGrid:
    """one 1 m grid per step, covering every version's line +-(HALF+3) m; ink classes sampled once"""

    def __init__(self, sheets, lines, kind):
        allc = np.vstack([np.asarray(c)[:, :2] for c in lines])
        self.lon0, self.lat0 = (
            float(allc[:, 0].mean()),
            float(allc[:, 1].mean()),
        )
        self.mx, self.my = (
            111320.0 * math.cos(math.radians(self.lat0)),
            110574.0,
        )
        XY = [self.xy(c) for c in lines]
        A = np.vstack(XY)
        pad = HALF + 6
        self.xmin, self.ymin = A[:, 0].min() - pad, A[:, 1].min() - pad
        nx, ny = (
            int((A[:, 0].max() + pad - self.xmin) / cl.RES) + 1,
            int((A[:, 1].max() + pad - self.ymin) / cl.RES) + 1,
        )
        near = np.zeros((ny, nx), bool)
        for P in XY:
            C = cl.resample(P, 0.5)
            rr = np.clip(
                ((C[:, 1] - self.ymin) / cl.RES).astype(int), 0, ny - 1
            )
            cc = np.clip(
                ((C[:, 0] - self.xmin) / cl.RES).astype(int), 0, nx - 1
            )
            near[rr, cc] = True
        near = ndimage.binary_dilation(
            near, structure=cl.disk((HALF + 3) / cl.RES)
        )
        iy, ix = np.nonzero(near)
        lons = self.lon0 + (self.xmin + (ix + 0.5) * cl.RES) / self.mx
        lats = self.lat0 + (self.ymin + (iy + 0.5) * cl.RES) / self.my
        extra = (
            "brown",
            "black",
            "blue",
            "red",
            "road",
            "creek",
            "contour",
            "dotlike",
            "text",
        )
        kink, have, ext = cl.sample_ink(sheets, kind, lons, lats, extra=extra)
        self.g = {}
        for k in ("kind",) + extra:
            m = np.zeros((ny, nx), bool)
            m[iy, ix] = kink if k == "kind" else ext[k]
            self.g[k] = m
        if (
            kind == "creek"
        ):  # as trace()/regrade(): the dots of a dotted creek are creek ink
            self.g["kind"] = self.g["kind"] | cl.chain_dots(
                self.g["kind"], self.g["dotlike"], cl.RES
            )
        self.kind = kind
        self.shape = (ny, nx)
        self.sheets = sheets
        # the feature's raw line ink for identity: contours = brown that is not road ink; creeks = creek ink;
        # roads = road ink (casings)
        # (not "brown minus road": over the halftone tint a contour breaks into dash-shaped pieces that ink.dashes()
        # gives to the road class; only the highway casings next to the red fill are taken out)
        # Brown only. Over the halftone woodland tint some contour ink classes black (olive-grey); brown|black was tried
        # Oct. 16 and lost two owner-reported hops (roads and fences become lanes) -- that is blind spot 59/(-99.0094, 30.9285)
        if kind == "contour":
            self.line = self.g["brown"] & ~ndimage.binary_dilation(
                self.g["red"], iterations=3
            )
        elif kind == "creek":
            self.line = self.g["creek"] | self.g["blue"]
        else:
            self.line = self.g["road"]
        # LONG-line ink: connected pieces whose principal-axis length is >= 40 m (digits, ticks, dots drop out)
        self.long = long_pieces(self.line, 40.0)
        self.d_long = ndimage.distance_transform_edt(~self.long) * cl.RES
        # other classes' long ink, for the wrong-class test
        # (contours: blue only -- roads and lettering print over contours everywhere and hide them; lettering never)
        txt = ndimage.binary_dilation(self.g["text"], iterations=2)
        if kind == "contour":
            other = self.g["blue"]
        elif kind == "creek":
            other = (self.g["brown"] & ~self.g["road"]) | self.g["black"]
        else:
            other = self.g["brown"] & ~self.g["road"]
        self.other_long = long_pieces(other & ~txt, 40.0)

    def xy(self, coords):
        c = np.asarray(coords)[:, :2]
        return np.column_stack(
            [(c[:, 0] - self.lon0) * self.mx, (c[:, 1] - self.lat0) * self.my]
        )

    def lonlat(self, P):
        return self.lon0 + P[..., 0] / self.mx, self.lat0 + P[..., 1] / self.my

    def sample(self, mask, PX, PY):
        r = np.floor((PY - self.ymin) / cl.RES).astype(int)
        c = np.floor((PX - self.xmin) / cl.RES).astype(int)
        ok = (r >= 0) & (r < self.shape[0]) & (c >= 0) & (c < self.shape[1])
        out = np.zeros(PX.shape, bool)
        out[ok] = mask[r[ok], c[ok]]
        return out


def long_pieces(mask, min_len):
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return np.zeros_like(mask)
    keep = np.zeros(n + 1, bool)
    for k, o in enumerate(ndimage.find_objects(lab), 1):
        if o is None:
            continue
        h, w = (
            (o[0].stop - o[0].start) * cl.RES,
            (o[1].stop - o[1].start) * cl.RES,
        )
        if max(h, w) >= min_len:
            keep[k] = True
            continue
        if math.hypot(h, w) < min_len:
            continue
        ys, xs = np.nonzero(lab[o] == k)
        P = np.column_stack([xs, ys]).astype(float)
        P -= P.mean(0)
        sv = np.linalg.svd(P, compute_uv=False)
        if 2 * math.sqrt(3) * sv[0] / math.sqrt(len(P)) * cl.RES >= min_len:
            keep[k] = True
    return keep[lab]


# ---------------------------------------------------------------- lanes in the straightened frame
def typical_width(S, o):
    W = [
        q[1]
        for i in range(S.shape[0])
        for q in (cl.ink_runs(S[i], o) if S[i].any() else [])
        if abs(q[0]) <= RIDE
    ]
    return float(np.median(W)) if W else 3.0


def track_lanes(S, o, wide=None):
    """S: rows (1 m along the line) x cols (offsets o). Returns lanes [{rows, offs, wid, merged, life}].
    A run of ink continues a lane when it lies within GATE of the lane's last offset (or of its extrapolation), or
    contains the last offset; ties go to the OLDER lane. A lane whose last offset lies inside the (ordinary-width) run
    taken by an older lane is the same line seen twice and is absorbed into it. A run wider than `wide` (1.6 x the
    line's typical width) holds lines welded together: lanes inside it coast, marked merged (identity ambiguous)."""
    if wide is None:
        wide = max(8.0, 1.6 * typical_width(S, o))
    lanes, active = [], []
    for i in range(S.shape[0]):
        R = cl.ink_runs(S[i], o) if S[i].any() else []
        used = [False] * len(R)
        upd = {}
        cand = []
        for li in active:
            L = lanes[li]
            dt = i - L["rows"][-1]
            last = L["offs"][-1]
            v = 0.0
            if len(L["rows"]) >= 4:
                v = float(
                    np.clip(
                        (L["offs"][-1] - L["offs"][-4])
                        / max(L["rows"][-1] - L["rows"][-4], 1),
                        -1.0,
                        1.0,
                    )
                )
            pred = last + v * dt
            gate = GATE + 0.25 * (dt - 1)
            for j, q in enumerate(R):
                d = min(
                    abs(q[0] - pred), abs(q[0] - last)
                )  # the run grid is 0.5 m: jitter is not velocity
                if q[1] <= wide and q[2] <= last <= q[3]:
                    d = min(d, 0.25)
                if d <= gate:
                    cand.append((round(d * 2) / 2, L["rows"][0], li, j, pred))
                elif q[1] > wide and q[2] - 0.5 <= pred <= q[3] + 0.5:
                    cand.append((gate + 0.5, L["rows"][0], li, j, pred))
        for d, _, li, j, pred in sorted(cand):
            if li in upd:
                continue
            q = R[j]
            L = lanes[li]
            if used[j]:
                if (
                    q[1] > wide and q[2] - 0.5 <= pred <= q[3] + 0.5
                ):  # a second lane inside a welded run: coasts
                    L["rows"].append(i)
                    L["offs"].append(pred)
                    L["wid"].append(q[1])
                    L["merged"].append(True)
                    upd[li] = j
                continue
            used[j] = True
            L["rows"].append(i)
            L["offs"].append(q[0])
            L["wid"].append(q[1])
            L["merged"].append(q[1] > wide)
            upd[li] = j
        for j, q in enumerate(R):
            if not used[j]:
                lanes.append(
                    dict(
                        rows=[i], offs=[q[0]], wid=[q[1]], merged=[q[1] > wide]
                    )
                )
                active.append(len(lanes) - 1)
                upd[len(lanes) - 1] = j
        # twins: a younger lane whose last offset lies inside the ordinary run an older lane took this row
        dead = set()
        for la, j in upd.items():
            q = R[j]
            if q[1] > wide:
                continue
            for lb in active:
                if (
                    lb == la
                    or lb in dead
                    or la in dead
                    or lanes[lb]["rows"][0] < lanes[la]["rows"][0]
                ):
                    continue
                if q[2] - 0.25 <= lanes[lb]["offs"][-1] <= q[
                    3
                ] + 0.25 and upd.get(lb, -1) in (-1, j):
                    A, B = lanes[la], lanes[lb]
                    for k in ("rows", "offs", "wid", "merged"):
                        A[k] = A[k] + B[k]
                    order = np.argsort(A["rows"], kind="stable")
                    for k in ("rows", "offs", "wid", "merged"):
                        A[k] = [A[k][x] for x in order]
                    B["rows"] = []
                    dead.add(lb)
        active = [
            li
            for li in active
            if li not in dead and i - lanes[li]["rows"][-1] <= COAST
        ]
    lanes = [L for L in lanes if L["rows"]]
    for L in lanes:
        r = np.array(L["rows"])
        _, first = np.unique(r, return_index=True)
        L["rows"] = r[first]
        L["offs"] = np.array(L["offs"])[first]
        L["wid"] = np.array(L["wid"])[first]
        L["merged"] = np.array(L["merged"])[first]
        L["life"] = int(L["rows"][-1] - L["rows"][0] + 1)
    return lanes


def ridden_sequence(lanes, n):
    """per row: the id of the long lane under the line (-1 none), and an 'ambiguous' flag (merged run under the line,
    or two long lanes within +-RIDE)"""
    rid = np.full(n, -1)
    best = np.full(n, np.inf)
    amb = np.zeros(n, bool)
    cnt = np.zeros(n, int)
    for li, L in enumerate(lanes):
        if L["life"] < LANE_MIN:
            continue
        sel = np.abs(L["offs"]) <= RIDE
        for i, off, mg in zip(L["rows"][sel], L["offs"][sel], L["merged"][sel]):
            cnt[i] += 1
            if mg:
                amb[i] = True
            if abs(off) < best[i]:
                best[i] = abs(off)
                rid[i] = li
    amb |= cnt >= 2
    return rid, amb


def lane_beside(L, lo, hi, S=None, o=None, elsewhere=None):
    """metres of lane L seen BESIDE the line in rows [lo, hi), and the largest |off| there. Beside means: |off| >= BESIDE,
    white paper (>= 1 m with no ink) between it and the line -- so a heavy line's halo or a split run is not a second
    line -- and not on the line itself somewhere else (the other arm of a V or a hairpin is the same contour: elsewhere
    is a per-observation flag computed from the whole line)"""
    sel = (
        (L["rows"] >= lo)
        & (L["rows"] < hi)
        & (np.abs(L["offs"]) >= BESIDE)
        & (np.abs(L["offs"]) <= HALF - 1)
    )
    if S is not None and sel.any():
        k0 = len(o) // 2
        for x in np.flatnonzero(sel):
            r, f = L["rows"][x], L["offs"][x]
            j = int(round((f + HALF) / DO))
            between = S[r, k0:j] if j > k0 else S[r, j + 1 : k0 + 1][::-1]
            # the lane's own run is at the far end; require a white stretch of >= 2 cells somewhere between
            w = ~between
            best = 0
            cur = 0
            for v in w:
                cur = cur + 1 if v else 0
                best = max(best, cur)
            if best < 2:
                sel[x] = False
    if elsewhere is not None and sel.any():
        sel &= ~elsewhere(L, sel)
    return int(sel.sum()), float(
        np.abs(L["offs"][sel]).max()
    ) if sel.any() else 0.0


def hop_events(lanes, rid, n, S=None, o=None, C=None, N=None):
    tree = cKDTree(C) if C is not None else None

    def elsewhere(L, sel):
        """observations of L that lie within 2 m of the line at an arc position > 20 m from the row they were seen at"""
        r = L["rows"][sel]
        f = L["offs"][sel]
        Pts = C[r] + f[:, None] * N[r]
        # an observation >= 3 m off its own row that is within 2 m of the line ANYWHERE is ink the line rides
        # elsewhere (the other arm of a V, a hairpin, the far side of a tight bend), not a second line
        out = np.zeros(len(L["rows"]), bool)
        out[np.flatnonzero(sel)] = tree.query(Pts)[0] <= 2.0
        return out

    segs = []  # (lane, first row, last row) of the ridden sequence
    for i in range(n):
        if rid[i] < 0:
            continue
        if segs and segs[-1][0] == rid[i] and i - segs[-1][2] <= COAST:
            segs[-1][2] = i
        else:
            segs.append([rid[i], i, i])
    segs = [
        s for s in segs if s[2] - s[1] + 1 >= 3
    ]  # one- or two-metre touches are crossings, handled there
    ev = []
    ew = elsewhere if tree is not None else None
    # each END of riding a lane (the next lane ridden is another one) is tested for "the old line carries on beside";
    # each START of riding a lane (the previous one was another) for "the new line was already running beside".
    # Lane identity at a fork is arbitrary (the tracker may hand the old id to either branch), so the line that
    # "carries on" is ANY long lane seen within 3.5 m of the line's position at the leaving point, not just the old id.
    at = {}
    k0 = len(o) // 2
    for li, L in enumerate(lanes):
        if L["life"] < LANE_MIN:
            continue
        for r, f in zip(L["rows"], L["offs"]):
            if abs(f) <= 3.5:
                at.setdefault(int(r), set()).add(li)
            elif (
                abs(f) <= 8.0 and S is not None
            ):  # or its ink joins the ink under the line (a fork)
                j = int(round((f + HALF) / DO))
                seg = S[r, min(j, k0) : max(j, k0) + 1]
                if (~seg).sum() <= 1:
                    at.setdefault(int(r), set()).add(li)

    def near(lo, hi):
        out = set()
        for r in range(lo, hi + 1):
            out |= at.get(r, set())
        return out

    for x, (A, a0, a1) in enumerate(segs):
        if x + 1 < len(segs) and segs[x + 1][0] == A:
            continue
        nxt = segs[x + 1][0] if x + 1 < len(segs) else None
        best = (0, 0.0)
        for L in near(a1 - 3, a1 + 6) - {nxt}:
            best = max(
                best, lane_beside(lanes[L], a1 + 1, a1 + 1 + LOOK, S, o, ew)
            )
        outm, outx = best
        if outm >= 2 * BESIDE_MIN or (outm >= BESIDE_MIN and outx >= 6.0):
            r1 = segs[x + 1][1] if x + 1 < len(segs) else min(n - 1, a1 + 10)
            ev.append(
                dict(
                    type="hop",
                    r0=int(a1),
                    r1=int(r1),
                    size_m=round(outx, 1),
                    why=f"left a line that carries on beside it ({outm} m, up to {outx:.1f} m off)",
                )
            )
    for x, (B, b0, b1) in enumerate(segs):
        if x > 0 and segs[x - 1][0] == B:
            continue
        prv = segs[x - 1][0] if x > 0 else None
        best = (0, 0.0)
        for L in near(b0 - 6, b0 + 3) - {prv}:
            best = max(
                best, lane_beside(lanes[L], max(0, b0 - LOOK), b0, S, o, ew)
            )
        inm, inx = best
        if inm >= 2 * BESIDE_MIN or (inm >= BESIDE_MIN and inx >= 6.0):
            r0 = segs[x - 1][2] if x > 0 else max(0, b0 - 10)
            ev.append(
                dict(
                    type="hop",
                    r0=int(r0),
                    r1=int(b0),
                    size_m=round(inx, 1),
                    why=f"joined a line that ran beside it before ({inm} m, up to {inx:.1f} m off)",
                )
            )
    return ev


def crossing_events(lanes, n, rid=None):
    ev = []
    for li, L in enumerate(lanes):
        if L["life"] < LANE_MIN:
            continue
        r, f = L["rows"], L["offs"]
        pos = np.flatnonzero(f >= 2.0)
        neg = np.flatnonzero(f <= -2.0)
        if not len(pos) or not len(neg):
            continue
        # a transition: last row on one side, first row on the other within 20 m
        side = np.where(f >= 2.0, 1, np.where(f <= -2.0, -1, 0))
        k = np.flatnonzero(side != 0)
        for a, b in zip(k, k[1:]):
            if side[a] != side[b] and r[b] - r[a] <= 20:
                before = int(
                    ((r <= r[a]) & (r >= r[a] - 40) & (side == side[a])).sum()
                )
                after = int(
                    ((r >= r[b]) & (r <= r[b] + 40) & (side == side[b])).sum()
                )
                # the line's OWN contour drifting from one side to the other is wobble (graded off-centre), not a crossing
                if (
                    rid is not None
                    and (
                        rid[max(0, int(r[a]) - 30) : int(r[b]) + 31] == li
                    ).mean()
                    >= 0.6
                ):
                    continue  # ridden 60% of the 60 m around: own line
                if before >= 8 and after >= 8:
                    ev.append(
                        dict(
                            type="crossing",
                            r0=int(r[a]),
                            r1=int(r[b]),
                            size_m=round(float(max(abs(f[a]), abs(f[b]))), 1),
                            why=f"a {L['life']} m line passes from {f[a]:+.1f} m to {f[b]:+.1f} m across the line",
                        )
                    )
    return ev


# ---------------------------------------------------------------- shape checks
def headings(C, h=2):
    n = len(C)
    i = np.arange(n)
    D = C[np.minimum(i + h, n - 1)] - C[np.maximum(i - h, 0)]
    return np.unwrap(np.arctan2(D[:, 1], D[:, 0]))


def wiggle_events(C, d_long=None):
    """loops through label digits: total |turn| - |net turn| over WIGGLE_WIN m > WIGGLE_DEG, AND inside that window the
    line spends >= 5 m off long-line ink (it is riding digit strokes or nothing). A real hairpin or S-bend of the
    contour turns as much, but the line stays on the contour's own long ink the whole way."""
    th = headings(C)
    d = np.diff(th)
    n = len(C)
    W = WIGGLE_WIN
    a = np.concatenate([[0], np.cumsum(np.abs(d))])
    s = np.concatenate([[0], np.cumsum(d)])
    i = np.arange(0, max(n - W, 0))
    if not len(i):
        return [], np.zeros(n)
    tot = a[i + W - 1] - a[i]
    net = np.abs(s[i + W - 1] - s[i])
    wig = np.degrees(tot - net)
    if d_long is not None:
        offl = np.concatenate([[0], np.cumsum(d_long > RIDE + 0.5)])
        offm = offl[i + W] - offl[i]
        wig = np.where(offm >= 5, wig, 0.0)
    score = np.zeros(n)
    score[i + W // 2] = wig
    ev = []
    for r0, r1 in cl.runs(score > WIGGLE_DEG):
        k = r0 + int(np.argmax(score[r0:r1]))
        ev.append(
            dict(
                type="wiggle",
                r0=int(r0),
                r1=int(r1),
                size_m=round(float(score[k]), 0),
                why=f"turns {score[k]:.0f} deg back and forth within {W} m while off the line's ink (loop through digits?)",
            )
        )
    return ev, score


def bridge_events(C, G):
    """where the line is off long-line ink for 8-400 m it must bridge the gap smoothly: compared with the cubic Hermite
    curve between the ink either side, with the line's own direction over the 10 m of ink before and after the gap
    (straight across a label on a straight contour, along the bend for a gap on a bend). Max distance > max(3 m, 5% of
    the chord) is flagged."""
    d = G_d_at(G, C)
    off = d > RIDE + 0.5
    ev = []
    n = len(C)
    for a, b in cl.runs(off):
        L = b - a
        if L < 8 or L > 400 or a < 11 or b + 10 >= n:
            continue
        P0, P1 = C[a - 1], C[b]
        ch = float(np.hypot(*(P1 - P0)))
        if ch < 1:
            continue
        t0 = C[a - 1] - C[a - 11]
        t1 = C[b + 10] - C[b]
        t0 = t0 / (np.hypot(*t0) + 1e-9) * ch
        t1 = t1 / (np.hypot(*t1) + 1e-9) * ch
        u = np.linspace(0, 1, 4 * L + 2)[:, None]
        H = (
            (2 * u**3 - 3 * u**2 + 1) * P0
            + (u**3 - 2 * u**2 + u) * t0
            + (-2 * u**3 + 3 * u**2) * P1
            + (u**3 - u**2) * t1
        )
        dev = cKDTree(H).query(C[a:b])[0]
        k = int(np.argmax(dev))
        tol = max(3.0, 0.05 * ch)
        if dev[k] > tol:
            ev.append(
                dict(
                    type="bridge",
                    r0=int(a),
                    r1=int(b),
                    size_m=round(float(dev[k]), 1),
                    why=f"off the line ink for {L} m and {dev[k]:.1f} m from a smooth bridge across the gap (chord {ch:.0f} m)",
                )
            )
    return ev, d


def G_d_at(G, C):
    r = np.clip(((C[:, 1] - G.ymin) / cl.RES).astype(int), 0, G.shape[0] - 1)
    c = np.clip(((C[:, 0] - G.xmin) / cl.RES).astype(int), 0, G.shape[1] - 1)
    return G.d_long[r, c]


def wrongclass_events(C, G):
    if G.kind == "road":
        return []
    N = cl.normals(C)
    o = np.arange(-RIDE, RIDE + 1e-9, 0.5)
    PX = C[:, 0, None] + o * N[:, 0, None]
    PY = C[:, 1, None] + o * N[:, 1, None]
    oth = G.sample(G.other_long, PX, PY).any(1)
    own = G.sample(G.line, PX, PY).any(1)
    ev = []
    for a, b in cl.runs(oth & ~own):
        if b - a >= 10:
            ev.append(
                dict(
                    type="wrongclass",
                    r0=int(a),
                    r1=int(b),
                    size_m=float(b - a),
                    why=f"rides other ink ({'blue' if G.kind == 'contour' else 'brown/black'}) for {b - a} m",
                )
            )
    return ev


def seg_intersections(P, Q=None, cell=5.0, min_sep=4):
    """crossings of polyline P with itself (Q None; segments >= min_sep apart) or with polyline Q: list of (i, j)"""

    def buckets(A):
        B = {}
        for i in range(len(A) - 1):
            x0, x1 = sorted((A[i, 0], A[i + 1, 0]))
            y0, y1 = sorted((A[i, 1], A[i + 1, 1]))
            for gx in range(
                int(math.floor(x0 / cell)), int(math.floor(x1 / cell)) + 1
            ):
                for gy in range(
                    int(math.floor(y0 / cell)), int(math.floor(y1 / cell)) + 1
                ):
                    B.setdefault((gx, gy), []).append(i)
        return B

    def cross(a, b, c, d):
        def o(p, q, r):
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

        return (o(a, b, c) * o(a, b, d) < 0) and (o(c, d, a) * o(c, d, b) < 0)

    BP = buckets(P)
    out = set()
    if Q is None:
        for k, L in BP.items():
            for x in range(len(L)):
                for y in range(x + 1, len(L)):
                    i, j = L[x], L[y]
                    if abs(i - j) >= min_sep and cross(
                        P[i], P[i + 1], P[j], P[j + 1]
                    ):
                        out.add((min(i, j), max(i, j)))
    else:
        BQ = buckets(Q)
        for k, L in BP.items():
            for j in BQ.get(k, []):
                for i in L:
                    if cross(P[i], P[i + 1], Q[j], Q[j + 1]):
                        out.add((i, j))
    return sorted(out)


# ---------------------------------------------------------------- one line
def check_line(G, coords, others=(), sheet_rows=None):
    P = G.xy(coords)
    C = cl.resample(P, 1.0)
    C[0], C[-1] = P[0], P[-1]
    n = len(C)
    meas, symbol = cl.grade(C, G.g["kind"], G.xmin, G.ymin, G.kind)
    o = np.arange(-HALF, HALF + 1e-9, DO)
    N = cl.normals(C)
    PX = C[:, 0, None] + o * N[:, 0, None]
    PY = C[:, 1, None] + o * N[:, 1, None]
    S = G.sample(G.line, PX, PY)
    lanes = track_lanes(S, o)
    rid, amb = ridden_sequence(lanes, n)
    ev = []
    if G.kind in ("contour", "creek"):
        ev += hop_events(lanes, rid, n, S, o, C, N)
        if G.kind == "contour":
            ev += crossing_events(lanes, n, rid)
    else:
        ev += road_events(lanes, n)
    d_long = None
    if G.kind != "road":
        be, d_long = bridge_events(C, G)
        ev += be
    we, wscore = wiggle_events(C, d_long)
    ev += we
    ev += wrongclass_events(C, G)
    for i, j in seg_intersections(C):
        ev.append(
            dict(
                type="selfx",
                r0=i,
                r1=i + 1,
                size_m=0,
                why=f"crosses itself (metre {j})",
            )
        )
    for name, Q in others:
        for i, j in seg_intersections(C, G.xy(Q) if len(Q) else None):
            if i < END_SKIP or i > n - END_SKIP:
                continue  # steps meet at their shared pins
            ev.append(
                dict(
                    type="stepx",
                    r0=i,
                    r1=i + 1,
                    size_m=0,
                    why=f"crosses step {name}",
                )
            )
    # sheet edges: events within 30 m of a neatline crossing are tagged (a jog there is expected and reported)
    if sheet_rows is not None:
        edges = np.flatnonzero(np.diff(sheet_rows) != 0)
        for e in ev:
            if (
                len(edges)
                and np.min(np.abs(edges - (e["r0"] + e["r1"]) / 2)) <= 30
            ):
                e["sheet_edge"] = True
    ev = [e for e in ev if e["r1"] >= END_SKIP and e["r0"] <= n - 1 - END_SKIP]
    # context, for the reader only (pass/fail does not depend on it): a sharp bend at the event, lettering near it
    th = headings(C)
    tx = ndimage.binary_dilation(G.g["text"], structure=cl.disk(12 / cl.RES))
    for e in ev:
        a0, a1 = max(0, e["r0"] - 10), min(n - 1, e["r1"] + 10)
        e["turn_deg"] = int(round(abs(math.degrees(th[a1] - th[a0]))))
        seg = C[e["r0"] : e["r1"] + 1]
        rr = np.clip(
            ((seg[:, 1] - G.ymin) / cl.RES).astype(int), 0, G.shape[0] - 1
        )
        cc = np.clip(
            ((seg[:, 0] - G.xmin) / cl.RES).astype(int), 0, G.shape[1] - 1
        )
        e["at_label"] = bool(tx[rr, cc].any())
        e["context"] = (
            "label"
            if e["at_label"]
            else ("sharp bend" if e["turn_deg"] >= 100 else "")
        )
    for e in ev:
        k = (e["r0"] + e["r1"]) // 2
        lo, la = G.lonlat(C[k])
        e["lon"], e["lat"] = round(float(lo), 6), round(float(la), 6)
        e["s_m"] = int(k)
    # ---- per-metre states
    core = np.zeros(n, bool)
    core[END_SKIP : n - END_SKIP] = True
    flagged = np.zeros(n, bool)
    for e in ev:
        flagged[
            max(0, e["r0"] - EVENT_PAD) : min(n, e["r1"] + EVENT_PAD + 1)
        ] = True
    hops = sorted([e for e in ev if e["type"] == "hop"], key=lambda e: e["r0"])
    exc = []
    for x, y in zip(hops, hops[1:]):
        if (
            "left a line" in x["why"]
            and "joined a line" in y["why"]
            and 0 < y["r0"] - x["r1"] <= 600
        ):
            flagged[x["r1"] : y["r0"] + 1] = True
            exc.append((x["r1"], y["r0"]))
    resid = np.abs(meas)
    offc = np.nan_to_num(resid, nan=0) > 2
    for a, b in cl.runs(offc):
        if b - a >= 3:
            flagged[a:b] = True
    graded_ok = ~np.isnan(meas) & (np.nan_to_num(resid, nan=99) <= 2)
    if G.kind == "road":
        lane_ok = road_ok(lanes, n)
    else:
        lane_ok = (rid >= 0) & ~amb
    verified = graded_ok & lane_ok & ~flagged & core
    flagged &= core
    unmeasured = core & ~verified & ~flagged
    nc = max(int(core.sum()), 1)
    stats = dict(
        n_m=n,
        core_m=int(core.sum()),
        grade_measured_pct=round(
            100 * float((~np.isnan(meas[core])).mean()), 1
        ),
        grade_within2_of_measured_pct=round(
            100 * float((resid[core & ~np.isnan(meas)] <= 2).mean()), 1
        )
        if (core & ~np.isnan(meas)).any()
        else None,
        grade_strict_pct=round(100 * float((graded_ok & core).sum()) / nc, 1),
        lane_ok_pct=round(100 * float((lane_ok & core).sum()) / nc, 1),
        verified_pct=round(100 * float(verified.sum()) / nc, 1),
        flagged_pct=round(100 * float(flagged.sum()) / nc, 1),
        unmeasured_pct=round(100 * float(unmeasured.sum()) / nc, 1),
        # metres grade() calls within 2 m that are NOT on one continuous lane, or inside an event
        graded_ok_but_suspect_m=int(
            (graded_ok & core & (flagged | ~lane_ok)).sum()
        ),
        event_counts={
            t: sum(1 for e in ev if e["type"] == t)
            for t in (
                "hop",
                "crossing",
                "wiggle",
                "bridge",
                "wrongclass",
                "selfx",
                "stepx",
                "road_leave",
            )
        },
    )
    queue = []
    for a, b in cl.runs(unmeasured):
        if b - a >= 15:
            k = (a + b) // 2
            lo, la = G.lonlat(C[k])
            queue.append([round(float(lo), 6), round(float(la), 6), int(b - a)])
    stats["excursions_m"] = int(
        sum(b - a for a, b in exc)
    )  # metres between a hop-out and the next hop-in
    stats["sheet_edge_events"] = sum(1 for e in ev if e.get("sheet_edge"))
    stats["identity_events"] = sum(
        1
        for e in ev
        if e["type"] in ("hop", "crossing", "road_leave", "wrongclass")
        and not e.get("sheet_edge")
    )
    stats["shape_events"] = sum(
        1
        for e in ev
        if e["type"] in ("wiggle", "bridge", "selfx", "stepx")
        and not e.get("sheet_edge")
    )
    return dict(
        C=C,
        meas=meas,
        rid=rid,
        amb=amb,
        lanes=lanes,
        events=ev,
        verified=verified,
        flagged=flagged,
        unmeasured=unmeasured,
        stats=stats,
        queue=queue,
        unmeasured_runs=cl.runs(unmeasured),
    )


# ---------------------------------------------------------------- roads: the casing pair
def road_ok(lanes, n):
    """a metre is lane-verified when a long lane is on each side of the line (a casing pair) within 2.5-11 m"""
    left = np.zeros(n, bool)
    right = np.zeros(n, bool)
    for L in lanes:
        if L["life"] < LANE_MIN:
            continue
        f = L["offs"]
        r = L["rows"]
        sl = (f <= -1.25) & (f >= -11)
        sr = (f >= 1.25) & (f <= 11)
        left[r[sl]] = True
        right[r[sr]] = True
    # dashes: a casing seen within +-8 m along counts
    k = np.ones(17, bool)
    left = ndimage.binary_dilation(left, structure=k)
    right = ndimage.binary_dilation(right, structure=k)
    return left & right


def road_events(lanes, n):
    """roads: the line crosses a long casing lane (it went over the road's edge onto something else)"""
    ev = []
    for L in lanes:
        if L["life"] < 25:
            continue
        r, f = L["rows"], L["offs"]
        side = np.where(f >= 1.0, 1, np.where(f <= -1.0, -1, 0))
        k = np.flatnonzero(side != 0)
        for a, b in zip(k, k[1:]):
            if side[a] != side[b] and r[b] - r[a] <= 15:
                before = int(
                    ((r <= r[a]) & (r >= r[a] - 40) & (side == side[a])).sum()
                )
                after = int(
                    ((r >= r[b]) & (r <= r[b] + 40) & (side == side[b])).sum()
                )
                if before >= 12 and after >= 12:
                    ev.append(
                        dict(
                            type="road_leave",
                            r0=int(r[a]),
                            r1=int(r[b]),
                            size_m=round(float(max(abs(f[a]), abs(f[b]))), 1),
                            why=f"a {L['life']} m casing/line passes from {f[a]:+.1f} m to {f[b]:+.1f} m across the line",
                        )
                    )
    return ev


# ---------------------------------------------------------------- known blind spots (always queued, never verified)
# Places where the checks above are known to be blind (Oct. 16, 2026); a person signs each off on its crop.
BLIND_SPOTS = [
    (
        "59",
        -99.0094,
        30.9285,
        "grey contour over the tint: the abandoned contour prints grey (classes black) over the halftone "
        "tint, so a hop here is invisible to the lane test; every version and the prior step onto the next contour here",
    ),
    (
        "59",
        -99.0222,
        30.9380,
        "label digits not detected by ink.py: check the line bridges the label straight on its own contour",
    ),
    (
        "59",
        -99.0231,
        30.9378,
        "label digits not detected by ink.py: check the line bridges the label straight on its own contour",
    ),
    (
        "82",
        -99.2068,
        30.7202,
        "label digits not detected by ink.py: check the line bridges the label straight on its own contour",
    ),
    (
        "3",
        -99.3951,
        30.7775,
        "the '1' of a contour label has no hole and is not detected: check for a spike toward it",
    ),
]
VALIDATED = {
    "contour"
}  # creek and road modes run, but their events are marked unvalidated
SEVERITY = {
    "hop": 1,
    "crossing": 1,
    "wrongclass": 1,
    "road_leave": 1,
    "selfx": 1,
    "stepx": 1,
    "bridge": 2,
    "wiggle": 2,
    "unmeasured": 3,
}
CLUSTER_M = 60

# ---------------------------------------------------------------- crops for the reviewer
COL = {
    "black": (255, 0, 255),
    "red": (255, 140, 0),
    "brown": (0, 160, 0),
    "creek": (0, 0, 255),
}


def _font(size):
    from PIL import ImageFont

    for f in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def render_crop(
    sheets, lon, lat, traced, prior, stretches, lines, out, half_px=60, scale=3
):
    """left: the scan with the traced line (purple), the prior (thin red) and the item's stretches (yellow, ends circled);
    right: the ink classes (black/grey magenta, red fill orange, brown green, blue/teal blue) with the traced line"""
    from PIL import Image, ImageDraw
    from quadsheets import sheet_of

    sh = sheet_of(sheets, lon, lat)
    if sh is None:
        return False
    c, r, _ = sh.pixel(lon, lat)
    m = 30
    big, bc0, br0 = sh.read(
        c - half_px - m, r - half_px - m, c + half_px + m, r + half_px + m
    )
    M = inklib.classes(big)
    a, c0, r0 = sh.read(c - half_px, r - half_px, c + half_px, r + half_px)
    oy, ox = int(r0 - br0), int(c0 - bc0)
    rgb = np.transpose(a, (1, 2, 0)).astype("uint8")
    ov = np.full_like(rgb, 255)
    for k, col in COL.items():
        ov[M[k][oy : oy + rgb.shape[0], ox : ox + rgb.shape[1]]] = col
    W, H = rgb.shape[1] * scale, rgb.shape[0] * scale
    L = Image.fromarray(rgb).resize((W, H), Image.NEAREST)
    R = Image.fromarray(ov).resize((W, H), Image.NEAREST)

    def pts(co):
        cc, rr, _, _ = sh.pixels([p[0] for p in co], [p[1] for p in co])
        return [((u - c0) * scale, (v - r0) * scale) for u, v in zip(cc, rr)]

    for im, items in (
        (L, ((prior, (230, 0, 0), 1), (traced, (120, 0, 230), 2))),
        (R, ((traced, (120, 0, 230), 2),)),
    ):
        d = ImageDraw.Draw(im)
        for co, col, wd in items:
            if co is not None and len(co) > 1:
                d.line(pts(co), fill=col, width=wd)
    d = ImageDraw.Draw(L)
    for st in stretches:
        if len(st) > 1:
            p = pts(st)
            d.line(p, fill=(255, 210, 0), width=4)
            for u, v in (p[0], p[-1]):
                d.ellipse([u - 4, v - 4, u + 4, v + 4], outline=(0, 0, 0))
    for im in (L, R):
        ImageDraw.Draw(im).ellipse(
            [W / 2 - 6, H / 2 - 6, W / 2 + 6, H / 2 + 6],
            outline=(0, 0, 0),
            width=1,
        )
    f = _font(14)
    lh = 18
    lines = [
        x for t in lines for x in wrap(t, max(40, int((2 * W + 10) / 7.4)))
    ][:8]
    o = Image.new("RGB", (2 * W + 10, H + lh * len(lines) + 6), "white")
    dd = ImageDraw.Draw(o)
    for k, t in enumerate(lines):
        dd.text((4, 3 + k * lh), t, fill=(0, 0, 0), font=f)
    o.paste(L, (0, lh * len(lines) + 6))
    o.paste(R, (W + 10, lh * len(lines) + 6))
    o.save(out)
    return True


def wrap(t, n=150):
    out = []
    while len(t) > n:
        k = t.rfind(" ", 0, n)
        k = k if k > 0 else n
        out.append(t[:k])
        t = t[k:].lstrip()
    return out + [t]


# ---------------------------------------------------------------- driver
def main():
    ap = argparse.ArgumentParser(
        description="acceptance check: is each traced line on the RIGHT feature (identity), not just near ink"
    )
    ap.add_argument(
        "--quads",
        action="append",
        required=True,
        help="GeoTIFF/zip path or glob (repeatable)",
    )
    ap.add_argument(
        "--traced",
        required=True,
        help="traced lines (centerline.py output); read only",
    )
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ids", nargs="*")
    ap.add_argument(
        "--prior", help="prior lines, drawn thin red on the crops only"
    )
    ap.add_argument("--id-field", default="id")
    ap.add_argument("--kind-field", default="kind")
    ap.add_argument("--no-crops", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    os.makedirs(os.path.join(a.out_dir, "crops"), exist_ok=True)
    feats = {}
    for f in json.load(open(a.traced))["features"]:
        feats[str(f["properties"].get(a.id_field))] = (
            f["properties"].get(a.kind_field),
            f["geometry"]["coordinates"],
        )
    prior = {}
    if a.prior:
        for f in json.load(open(a.prior))["features"]:
            prior[str(f["properties"].get(a.id_field))] = f["geometry"][
                "coordinates"
            ]
    ids = [
        i
        for i in (a.ids or list(feats))
        if i in feats and feats[i][0] in ("contour", "creek", "road")
    ]
    sheets = open_sheets(a.quads)
    rows, items = [], []
    for sid in ids:
        kind, coords = feats[sid]
        ts = time.time()
        G = StepGrid(sheets, [coords], kind)
        others = [(o_, feats[o_][1]) for o_ in feats if o_ != sid]
        P = G.xy(coords)
        C = cl.resample(P, 1.0)
        lo, la = G.lonlat(C)
        R = check_line(G, coords, others, sheet_index(sheets, lo, la))
        st = R["stats"]
        ok = kind in VALIDATED
        # ---- queue entries: every event, and every unmeasured stretch >= 15 m; clustered along the line
        ent = [
            dict(
                r0=e["r0"],
                r1=e["r1"],
                type=("sheet_edge_jog" if e.get("sheet_edge") else e["type"]),
                size=e["size_m"],
                why=e["why"],
                context=e.get("context", ""),
            )
            for e in R["events"]
        ]
        ent += [
            dict(
                r0=int(x0),
                r1=int(x1),
                type="unmeasured",
                size=int(x1 - x0),
                why=f"{int(x1 - x0)} m neither verified nor flagged",
                context="",
            )
            for x0, x1 in R["unmeasured_runs"]
            if x1 - x0 >= 15
        ]
        ent.sort(key=lambda e: e["r0"])
        clusters = []
        for e in ent:
            if clusters and e["r0"] - clusters[-1]["r1"] <= CLUSTER_M:
                cc = clusters[-1]
                cc["ent"].append(e)
                cc["r1"] = max(cc["r1"], e["r1"])
            else:
                clusters.append(dict(r0=e["r0"], r1=e["r1"], ent=[e]))
        for k, cc in enumerate(clusters):
            worst = min(
                cc["ent"],
                key=lambda e: (
                    SEVERITY.get(e["type"], 2),
                    -float(e["size"] or 0),
                ),
            )
            km = (worst["r0"] + worst["r1"]) // 2
            types = sorted(
                {e["type"] for e in cc["ent"]}, key=lambda t: SEVERITY.get(t, 2)
            )
            items.append(
                dict(
                    item=f"{sid}-{k:03d}",
                    step=sid,
                    kind=kind,
                    validated=ok,
                    status="open" if ok else "open (unvalidated detector)",
                    priority=min(SEVERITY.get(t, 2) for t in types),
                    types=",".join(types),
                    n_entries=len(cc["ent"]),
                    lon=round(float(lo[km]), 6),
                    lat=round(float(la[km]), 6),
                    s_from_m=int(cc["r0"]),
                    s_to_m=int(cc["r1"]),
                    size=worst["size"],
                    context=worst["context"],
                    why=" | ".join(sorted({e["why"] for e in cc["ent"]}))[:600],
                    _stretches=[
                        list(
                            zip(
                                lo[e["r0"] : e["r1"] + 1],
                                la[e["r0"] : e["r1"] + 1],
                            )
                        )
                        for e in cc["ent"]
                        if e["type"] != "unmeasured"
                    ]
                    or [
                        list(
                            zip(
                                lo[cc["r0"] : cc["r1"] + 1],
                                la[cc["r0"] : cc["r1"] + 1],
                            )
                        )
                    ],
                )
            )
        for bs, blon, blat, why in BLIND_SPOTS:
            if bs == sid:
                items.append(
                    dict(
                        item=f"{sid}-blind-{blon:.4f},{blat:.4f}",
                        step=sid,
                        kind=kind,
                        validated=ok,
                        status="open (known blind spot)",
                        priority=0,
                        types="known_blind_spot",
                        n_entries=1,
                        lon=blon,
                        lat=blat,
                        s_from_m=None,
                        s_to_m=None,
                        size=None,
                        context="",
                        why=why,
                        _stretches=[],
                    )
                )
        c_ = st["event_counts"]
        nc = st["core_m"]
        rows.append(
            dict(
                step=sid,
                kind=kind,
                validated=ok,
                length_m=st["n_m"],
                core_m=nc,
                current_within2_of_measured_pct=st[
                    "grade_within2_of_measured_pct"
                ],
                current_measured_pct=st["grade_measured_pct"],
                current_strict_pct=st["grade_strict_pct"],
                lane_ok_pct=st["lane_ok_pct"],
                verified_pct=st["verified_pct"],
                flagged_pct=st["flagged_pct"],
                unmeasured_pct=st["unmeasured_pct"],
                verified_m=int(R["verified"].sum()),
                flagged_m=int(R["flagged"].sum()),
                unmeasured_m=int(R["unmeasured"].sum()),
                wrong_line_m=st["excursions_m"],
                graded_ok_but_suspect_m=st["graded_ok_but_suspect_m"],
                **{
                    f"ev_{t}": c_[t]
                    for t in (
                        "hop",
                        "crossing",
                        "bridge",
                        "wiggle",
                        "wrongclass",
                        "road_leave",
                        "selfx",
                        "stepx",
                    )
                },
                ev_sheet_edge=st["sheet_edge_events"],
                queue_items=sum(1 for i in items if i["step"] == sid),
                seconds=round(time.time() - ts, 1),
            )
        )
        r_ = rows[-1]
        print(
            f"{sid:>4} {kind:7s} {'' if ok else '(unvalidated) '}current check: within 2 m of measured {r_['current_within2_of_measured_pct']}%, "
            f"strict {r_['current_strict_pct']}% | VERIFIED {r_['verified_pct']}% FLAGGED {r_['flagged_pct']}% UNMEASURED {r_['unmeasured_pct']}% | "
            f"wrong line {r_['wrong_line_m']} m | events {sum(c_.values())} -> {r_['queue_items']} queue items | {r_['seconds']} s",
            flush=True,
        )
    # ---- crops, then the outputs
    for it in items:
        it["crop"] = os.path.join(
            "crops", f"{it['item'].replace(',', '_')}.png"
        )
        if a.no_crops:
            continue
        ext = 0
        for stx in it["_stretches"]:
            if len(stx) > 1:
                X = (np.array([p[0] for p in stx]) - it["lon"]) * 95600
                Y = (np.array([p[1] for p in stx]) - it["lat"]) * 110574
                ext = max(ext, float(np.hypot(X, Y).max()))
        half = int(min(110, max(50, ext / 2.03 + 25)))
        where = (
            f"size {it['size']}  metres {it['s_from_m']}-{it['s_to_m']} along the line"
            if it["s_from_m"] is not None
            else "fixed item: a place the checks are known to be blind to"
        )
        head = [
            f"item {it['item']}  step {it['step']} ({it['kind']}{', UNVALIDATED detector' if not it['validated'] else ''})  {it['types']}  "
            f"at {it['lon']}, {it['lat']}  {where}"
        ]
        head += [it["why"]]
        head += [
            "left: scan, traced line purple, prior thin red, the item's stretch yellow; right: ink classes (grey/black magenta, red orange, "
            "brown green, blue blue). Is the purple line on the CENTRE of the RIGHT feature here?"
        ]
        render_crop(
            sheets,
            it["lon"],
            it["lat"],
            feats[it["step"]][1],
            prior.get(it["step"]),
            it["_stretches"],
            head,
            os.path.join(a.out_dir, it["crop"]),
            half_px=half,
            scale=4 if half <= 70 else 3,
        )
    with open(os.path.join(a.out_dir, "per_step.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    fc = {
        "type": "FeatureCollection",
        "name": "featurecheck queue",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::4269"},
        },
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [it["lon"], it["lat"]],
                },
                "properties": {
                    k: v for k, v in it.items() if not k.startswith("_")
                },
            }
            for it in sorted(
                items,
                key=lambda i: (i["priority"], i["step"], i["s_from_m"] or 0),
            )
        ],
    }
    json.dump(fc, open(os.path.join(a.out_dir, "queue.geojson"), "w"), indent=1)
    nv = [r for r in rows if r["validated"]]
    print(
        f"\n{len(rows)} steps, {len(items)} queue items ({sum(1 for i in items if i['validated'])} validated, "
        f"{sum(1 for i in items if not i['validated'])} unvalidated), {round(time.time() - t0)} s. Outputs in {a.out_dir}"
    )
    if nv:
        tot = sum(r["core_m"] for r in nv)
        print(
            f"validated kinds: VERIFIED {100 * sum(r['verified_m'] for r in nv) / tot:.1f}% of {tot} m; "
            f"steps passing (VERIFIED >= 95% and no open items): {sum(1 for r in nv if r['verified_pct'] >= 95 and r['queue_items'] == 0)} of {len(nv)}"
        )


if __name__ == "__main__":
    main()
