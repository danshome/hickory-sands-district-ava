"""Trace lines onto the centre of the printed ink of scanned USGS topographic quadrangles.

Each input line is an approximate trace (the "prior") of one feature -- a road or highway, a creek, or a contour --
between two fixed endpoints (pins). The output follows the feature's ink centreline between the same pins:
  1. 1 m grid in a corridor around the prior (roads 50 m, creeks 120 m, contours 30 m either side);
  2. each cell takes the ink of the sheet whose neatline holds it (quadsheets.py; NADCON 5.0 for NAD27 sheets);
     cells within 2.5 m of a neatline count as gaps;
  3. the kind's ink (ink.py) -- for creeks plus the dots chained from the end of each solid stretch along its
     direction of travel (chain_dots) -- has dash/dot gaps closed along the prior's direction (roads 20 m, contours 5 m), is grown into one band (for
     double-line roads this merges the two edges), and the band's medial ridge is the cheap route (Dijkstra,
     8-neighbour; gaps cost 20+, a mild pull toward the prior stops hops onto parallel lines);
  4. roads: the path, smoothed, is moved onto the road's centre measured on cross-sections every metre: for a
     double-line road, the midpoint of its two casings, or ONE casing plus half the road's width (measured once per
     step) where the other casing's dash is missing -- this is what stops the line bouncing between the casings of a
     dashed road; for a filled highway or single line, the centre of symmetry (pooled +-8 m along), twice, the offsets smoothed over 12 m -- this centres two-edge roads,
     filled highways and single-line roads alike; creeks and contours: the ridge path, Gaussian-smoothed (2 m);
  5. simplified to 0.3 m; the pins are kept exactly.
Then the CHECK, independent of the tracing (grade(): raw ink, no gap closing, explicit edge/band/line rules,
anything ambiguous left unmeasured): across the final line every metre, the distance from the symbol's centre (median, 95th percentile, stretches over 2 m), gaps bridged, pins' distance off the centreline, and
how far the line moved from the prior.

CLI: centerline.py --quads "GLOB" [--quads ...] --lines lines.geojson --out traced.geojson
                   [--id-field id] [--kind-field kind] [--kind road] [--ids 7 8 ...]
     lines.geojson: LineStrings in NAD83 lon/lat (EPSG:4269); kind per feature: road | creek | contour.
     traced.geojson: the traced LineStrings with the check's figures as properties (merged by id if it exists).
"""

import argparse
import datetime
import json
import math
import os
import sys

import numpy as np
from scipy import ndimage
from scipy import sparse
from scipy.sparse import csgraph

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ink as inklib
from quadsheets import open_sheets

RES = 1.0
PARAM = {
    "road": dict(
        corridor=50.0,
        prior=25.0,
        fill=20,
        grow=4.0,
        sigma=3.0,
        sym=dict(half=10.0, pool=8, search=8.0),
        shift_sigma=25.0,
        shift_iters=2,
    ),  # 25 m > a dash cycle
    "creek": dict(
        corridor=120.0,
        prior=30.0,
        fill=0,
        grow=1.5,
        sigma=2.0,
        sym=dict(half=4.0, pool=1, search=4.0),
    ),
    # contours: prior 6 m, not 20 (Oct. 16, 2026, Dan: "the line is hopping to different contour lines"): on a
    # hachured slope the next contour is 3-4 m away and cutting a 60 m lobe through it cost less than going round
    # when the pull was (d/20)^2; at (d/6)^2 the lobe wins, and the band still beats the pull unless the prior
    # is > ~25 m off the ink
    "contour": dict(
        corridor=30.0,
        prior=6.0,
        fill=5,
        grow=1.5,
        sigma=2.0,
        sym=dict(half=4.0, pool=1, search=4.0),
    ),
}
K_RIDGE, GAP, NEAT_M = 4.0, 20.0, 2.5
MAX_ARC_JUMP = 150.0  # m along the prior: no path edge may connect parts of the line further apart than this
# contours: 40 m. Where a contour makes a narrow V up a creek, the tip is only ~100 m of arc, so 150 m let the path cut
# across the neck and skip the tip (steps 59, 3, 65, 82, 6 lost 186, 122, 73, 189, 25 m; contour review Oct. 16, 2026).
# 25 m over-shoots.
MAX_ARC_JUMP_KIND = {"contour": 40.0}
END_BLANK = 20  # m: road cross-section readings this close to a pin (a junction) are not used
LABEL_TEXT_GROW = 10.0  # m: brown lettering removed from contour ink, grown this far, is part of the label zone
# flat cost over the digits: OFF. Tried Oct. 16, 2026 (1.5 per m over lettering grown 5 m, with and without the prior
# pull): no effect where the label's digits are not detected (step 3's 1800, step 82's 1500), worse at 59/65 without
# the prior. Remaining label loops are hand-fixed (a straight segment across the label).
LABEL_FLAT, LABEL_FLAT_GROW, LABEL_FLAT_PRIOR = None, 5.0, True
END_PULL, END_PULL_M = (
    40.0,
    5.0,
)  # m: within END_PULL of a pin a road path is pulled to the prior at END_PULL_M (not 25)
DEBUG = None  # set to {} to keep the last trace's grids (ink, band, ridge, cost, frame)


# ---------------------------------------------------------------- geometry helpers
def densify(c, step_m):
    out = []
    for (x0, y0), (x1, y1) in zip(c, c[1:]):
        d = math.hypot(
            (x1 - x0) * 111320 * math.cos(math.radians(y0)), (y1 - y0) * 110574
        )
        k = max(1, int(d / step_m))
        out += [
            (x0 + (x1 - x0) * i / k, y0 + (y1 - y0) * i / k) for i in range(k)
        ]
    return out + [tuple(c[-1])]


def disk(rad):
    r = int(math.ceil(rad))
    y, x = np.ogrid[-r : r + 1, -r : r + 1]
    return x * x + y * y <= rad * rad + 1e-9


def line_se(length, theta):
    h = length // 2
    se = np.zeros((2 * h + 1, 2 * h + 1), bool)
    for t in np.linspace(-h, h, 4 * length + 1):
        se[
            int(round(h - t * math.sin(theta))),
            int(round(h + t * math.cos(theta))),
        ] = True
    return se


def directional_fill(ink, theta, length, nbins=16):
    """close dash and dot gaps along the feature's own direction (theta per cell, from the prior)"""
    out = ink.copy()
    k = np.floor((theta % math.pi) / math.pi * nbins + 0.5).astype(int) % nbins
    for i in range(nbins):
        sel = k == i
        if sel.any():
            out[sel] |= ndimage.binary_closing(
                ink, structure=line_se(length, i * math.pi / nbins)
            )[sel]
    return out


def smooth(XY, sigma):
    """Gaussian smoothing of a path by arc length (not by vertex); ends held"""
    s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(XY, axis=0).T))])
    out = XY.copy()
    h = 3 * sigma
    for i in range(1, len(XY) - 1):
        lo, hi = (
            max(np.searchsorted(s, s[i] - h), 0),
            min(np.searchsorted(s, s[i] + h, side="right"), len(XY)),
        )
        k = min(i - lo, hi - 1 - i)
        j = np.arange(i - k, i + k + 1)
        w = np.exp(-0.5 * ((s[j] - s[i]) / sigma) ** 2)
        out[i] = (XY[j] * w[:, None]).sum(0) / w.sum()
    return out


def resample(XY, step=1.0):
    s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(XY, axis=0).T))])
    t = np.linspace(0, s[-1], max(2, int(round(s[-1] / step)) + 1))
    return np.column_stack(
        [np.interp(t, s, XY[:, 0]), np.interp(t, s, XY[:, 1])]
    )


def normals(B, k=5):
    n = len(B)
    i = np.arange(n)
    T = B[np.minimum(i + k, n - 1)] - B[np.maximum(i - k, 0)]
    T /= np.maximum(np.hypot(T[:, 0], T[:, 1]), 1e-9)[:, None]
    return np.column_stack([-T[:, 1], T[:, 0]])


def rdp(P, eps):
    keep = np.zeros(len(P), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(P) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        A, B = P[a], P[b]
        s = B - A
        L = math.hypot(*s)
        V = P[a + 1 : b] - A
        d = (
            np.abs(s[0] * V[:, 1] - s[1] * V[:, 0]) / L
            if L
            else np.hypot(V[:, 0], V[:, 1])
        )
        i = int(np.argmax(d))
        if d[i] > eps:
            keep[a + 1 + i] = True
            stack += [(a, a + 1 + i), (a + 1 + i, b)]
    return np.flatnonzero(keep)


def runs(flags):
    """(start, end) index pairs of True runs"""
    d = np.diff(np.concatenate([[0], flags.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


# ---------------------------------------------------------------- ink on the grid
def sample_ink(sheets, kind, lons, lats, extra=()):
    """the kind's ink flag per NAD83 point (and any `extra` ink.classes masks), each read from the sheet whose
    neatline holds the point; points within NEAT_M of a neatline count as no ink
    """
    n = len(lons)
    ink = np.zeros(n, bool)
    edge = np.zeros(n, bool)
    done = np.zeros(n, bool)
    ext = {k: np.zeros(n, bool) for k in extra}
    for sh in sheets:
        todo = np.flatnonzero(~done)
        if not len(todo):
            break
        c, r, inside, near = sh.pixels(lons[todo], lats[todo], NEAT_M)
        if not inside.any():
            continue
        sel = np.flatnonzero(inside)
        ci = np.floor(c[sel]).astype(int)
        ri = np.floor(r[sel]).astype(int)
        a, c0, r0 = sh.read(ci.min(), ri.min(), ci.max() + 1, ri.max() + 1)
        M = inklib.classes(a)
        m = M[kind]
        ok = (
            (ri - r0 >= 0)
            & (ri - r0 < m.shape[0])
            & (ci - c0 >= 0)
            & (ci - c0 < m.shape[1])
        )
        ink[todo[sel[ok]]] = m[ri[ok] - r0, ci[ok] - c0]
        for k in extra:
            ext[k][todo[sel[ok]]] = M[k][ri[ok] - r0, ci[ok] - c0]
        edge[todo[near]] = True
        done[todo[sel]] = True
    ink[edge] = False
    for k in extra:
        ext[k][edge] = False
    return (ink, done, ext) if extra else (ink, done)


# ---------------------------------------------------------------- centre of symmetry across the feature
def sym_offsets(B, ink, xmin, ymin, half, pool, search):
    """per point of B (1 m spacing): (offset of the ink's centre of symmetry along the normal, strength 0-1, normals).
    Cross-sections are pooled over +-pool m along the feature, so dash gaps don't matter. Two edges, a filled band and
    a single line are all symmetric about their centre.
    """
    o = np.arange(-(half + search), half + search + 1e-9, 0.5)
    N = normals(B)
    PX = B[:, 0, None] + o[None, :] * N[:, 0, None]
    PY = B[:, 1, None] + o[None, :] * N[:, 1, None]
    r = np.floor((PY - ymin) / RES).astype(int)
    c = np.floor((PX - xmin) / RES).astype(int)
    ok = (r >= 0) & (r < ink.shape[0]) & (c >= 0) & (c < ink.shape[1])
    prof = np.zeros(PX.shape, np.float32)
    prof[ok] = ink[r[ok], c[ok]]
    # pool along the feature by MEAN (tried median: it also outvotes the dashes of unimproved roads, which cover
    # less than half the window -- step 7 lost a third of its readings)
    if pool:
        prof = ndimage.uniform_filter1d(
            prof, size=2 * pool + 1, axis=0, mode="nearest"
        )
    k0 = len(o) // 2
    hw = int(half / 0.5)
    cands = np.arange(
        -int(search / 0.5), int(search / 0.5) + 1
    )  # half-metre steps
    score = np.full((len(B), len(cands)), -1.0, np.float32)
    qual = np.zeros_like(score)
    for j, ci in enumerate(k0 + cands):
        L = prof[:, ci - hw : ci][:, ::-1]
        R = prof[:, ci + 1 : ci + 1 + hw]
        Cc = prof[:, ci : ci + 1]
        # symmetric about cell ci: compare left and right halves (the centre cell counts for both)
        num = (L * R).sum(1) + (Cc * Cc).sum(1)
        den = (
            np.sqrt(
                ((L * L).sum(1) + (Cc * Cc).sum(1))
                * ((R * R).sum(1) + (Cc * Cc).sum(1))
            )
            + 1e-6
        )
        # choose by ink paired with its mirror, weighted by how symmetric: between two road edges both edges pair
        # up; centred on ONE edge only that edge pairs with itself (a lone line is symmetric too, so symmetry alone
        # cannot tell the road's centre from an edge's)
        qual[:, j] = num / den
        score[:, j] = num * qual[:, j] ** 2
    jb = np.argmax(score, 1)
    strength = qual[np.arange(len(B)), jb]
    # sub-sample refinement (parabola through the best score and its neighbours)
    jl, jr = (
        np.clip(jb - 1, 0, len(cands) - 1),
        np.clip(jb + 1, 0, len(cands) - 1),
    )
    sl, sc, sr = (
        score[np.arange(len(B)), jl],
        score[np.arange(len(B)), jb],
        score[np.arange(len(B)), jr],
    )
    den = sl - 2 * sc + sr
    frac = np.where(
        np.abs(den) > 1e-6,
        0.5 * (sl - sr) / np.where(np.abs(den) > 1e-6, den, 1),
        0,
    )
    best = (cands[jb] + np.clip(frac, -0.5, 0.5)) * 0.5
    present = prof[:, k0 - hw : k0 + hw + 1].sum(1)
    best[(strength < 0.6) | (present < 1.0)] = (
        np.nan
    )  # nothing symmetric to measure here (gap, junction)
    return best, strength, N


def chain_dots(
    solid,
    dotlike,
    res,
    theta=None,
    max_hop=50.0,
    cone_deg=35.0,
    max_hops=80,
    max_area=50.0,
    max_extent=10.5,
    dash_width=5.0,
    dash_area=150.0,
):
    """Dotted and dash-dot creeks: from the end of each solid stretch of creek ink, look ahead in its direction of
    travel (within cone_deg, up to max_hop m) for the nearest piece of the symbol -- a small compact DOT, or a thin
    DASH lying along the direction of travel -- hop to it (a dash: in at its near end, out at its far end, along its
    own direction), update the direction, and repeat. The direction of travel at a solid end comes from the solid
    stretch itself when it is long enough (>= 12 m) and otherwise from the prior's bearing there (theta grid), the two
    blended in between: a 3-cell stub says nothing about where the creek goes. Over the woodland tint both often print dark and near-neutral,
    so they are taken from any non-brown ink ("dotlike"), by shape and position rather than colour.
    Measured on these scans: dots 4-49 m2 (1-12 px), 2-10 m across, 12-41 m apart; dashes up to ~25 m long, <= 4 m
    wide. Dots overlap house symbols in size, so a chain counts only if it has >= 2 pieces or ends in the cone of
    another solid stretch of creek. Returns the accepted pieces as a mask (creek ink).
    """
    lab, n = ndimage.label(dotlike & ~solid, structure=np.ones((3, 3)))
    if n == 0:
        return np.zeros_like(solid)
    cosmin = math.cos(math.radians(cone_deg))
    pieces = []  # (id, centroid, unit axis, half-length, is_dash)
    for k, o in enumerate(ndimage.find_objects(lab), 1):
        ys, xs = np.nonzero(lab[o] == k)
        area = len(ys) * res * res
        if area < 2 * res * res or area > dash_area:
            continue
        P = np.column_stack([ys + o[0].start, xs + o[1].start]).astype(float)
        c = P.mean(0)
        if len(P) >= 3:
            _, sv, vt = np.linalg.svd(P - c, full_matrices=False)
            u = vt[0]
            t = (P - c) @ u
            w_ = (P - c) @ vt[1]
            length = (t.max() - t.min() + 1) * res
            width = (w_.max() - w_.min() + 1) * res
        else:
            u = np.array([1.0, 0.0])
            t = np.zeros(1)
            length = width = res * len(P)
        if area <= max_area and length <= max_extent:
            pieces.append((k, c, u, 0.0, False))
        elif width <= dash_width and length <= 30:
            pieces.append((k, c, u, (t.max() - t.min()) / 2, True))
    if not pieces:
        return np.zeros_like(solid)
    pid = np.array([q[0] for q in pieces])
    cen = np.array([q[1] for q in pieces])
    ax = np.array([q[2] for q in pieces])
    half = np.array([q[3] for q in pieces])
    dash = np.array([q[4] for q in pieces])
    slab, sn = ndimage.label(solid, structure=np.ones((3, 3)))
    sy, sx = np.nonzero(solid)
    slabv = slab[sy, sx]

    def reaches_solid(p, dv, own):
        v = np.column_stack([sy - p[0], sx - p[1]]).astype(float)
        dist = np.hypot(v[:, 0], v[:, 1])
        ok = (
            (slabv != own)
            & (dist * res <= max_hop)
            & ((v @ dv) / (dist + 1e-9) >= cosmin)
        )
        return bool(ok.any())

    accepted = set()
    for k, o in enumerate(ndimage.find_objects(slab), 1):
        if o is None:
            continue
        ys, xs = np.nonzero(slab[o] == k)
        if len(ys) < 3:
            continue
        P = np.column_stack([ys + o[0].start, xs + o[1].start]).astype(float)
        c = P.mean(0)
        d = np.linalg.svd(P - c, full_matrices=False)[2][0]
        t = (P - c) @ d
        blob_len = (t.max() - t.min()) * res
        w_own = min(1.0, blob_len / 12.0)
        for sign in (1, -1):
            tt = t.max() if sign > 0 else t.min()
            e = P[np.abs(t - tt) <= 2 / res].mean(0)
            back = P[
                (sign * (t - tt) <= -3 / res) & (sign * (t - tt) >= -10 / res)
            ]
            dv = e - back.mean(0) if len(back) else sign * d
            dv = dv / (np.linalg.norm(dv) + 1e-9)
            if (
                theta is not None
            ):  # the prior's bearing here, as a (row, col) unit vector
                th = theta[int(e[0]), int(e[1])]
                pv = np.array([math.sin(th), math.cos(th)])
                if pv @ dv < 0:
                    pv = -pv
                dv = w_own * dv + (1 - w_own) * pv
                dv /= np.linalg.norm(dv) + 1e-9
            p = e
            seen = set()
            chain = []
            for _ in range(max_hops):
                side = np.sign(((cen - p) * ax).sum(1))
                side[side == 0] = 1
                entry = cen - (side * half)[:, None] * ax
                exitp = cen + (side * half)[:, None] * ax
                v = entry - p
                dist = np.hypot(v[:, 0], v[:, 1])
                cosang = (v @ dv) / (dist + 1e-9)
                dm = dist * res
                aligned = ~dash | (np.abs(ax @ dv) >= cosmin)
                ok = (
                    (dm <= max_hop)
                    & ((cosang >= cosmin) | (dm <= 2.0))
                    & aligned
                )
                ok &= np.array([q not in seen for q in pid])
                if not ok.any():
                    break
                j = np.flatnonzero(ok)[np.argmin((dm + 8 * (1 - cosang))[ok])]
                seen.add(pid[j])
                chain.append(int(pid[j]))
                if dash[j]:
                    new_dv = side[j] * ax[j]
                else:
                    new_dv = (cen[j] - p) / (dist[j] + 1e-9)
                dv = 0.5 * dv + 0.5 * new_dv
                dv /= np.linalg.norm(dv) + 1e-9
                p = exitp[j]
            if len(chain) >= 2 or (chain and reaches_solid(p, dv, k)):
                accepted.update(chain)
    return np.isin(lab, sorted(accepted)) if accepted else np.zeros_like(solid)


def drop_crossing(ink, theta, max_extent_m=400.0, min_elong=3.0, min_deg=30.0):
    """roads: a fence line or a side road is the same black ink as the road's casings, and where one meets the road
    the band's ridge runs into it (point 94, Oct. 16, 2026: every trace rode a fence line for 30 m below the junction).
    Connected pieces of road ink that are elongated (principal axes >= min_elong) and CROSS the prior's local bearing
    by more than min_deg are not road ink. Pieces longer than max_extent_m are kept whatever their axis (a fence
    crossing the 100 m corridor at 35 deg is 175 m of ink, so 150 m was too short): a solid
    casing spans bends, and its principal axis means nothing against one local bearing.
    """
    lab, n = ndimage.label(ink, structure=np.ones((3, 3)))
    if n == 0:
        return ink
    out = ink.copy()
    dropped = []
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        if sl is None:
            continue
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if max(h, w) * RES > max_extent_m or max(h, w) < 4:
            continue
        rr, cc = np.nonzero(lab[sl] == i)
        if len(rr) < 6:
            continue
        y = rr + sl[0].start
        x = cc + sl[1].start
        cov = np.cov(np.vstack([x - x.mean(), y - y.mean()]))
        ev, vec = np.linalg.eigh(cov)
        if ev[0] <= 0 or math.sqrt(ev[1] / max(ev[0], 1e-9)) < min_elong:
            continue
        axis = math.atan2(vec[1, 1], vec[0, 1])
        th = float(theta[int(round(y.mean())), int(round(x.mean()))])
        diff = abs((axis - th + math.pi / 2) % math.pi - math.pi / 2)
        if diff > math.radians(min_deg):
            out[y, x] = False
            dropped.append(
                (len(rr), round(max(h, w) * RES), round(math.degrees(diff)))
            )
    if os.environ.get("TRACE_DEBUG"):
        print(
            f"drop_crossing: {len(dropped)} of {n} pieces dropped (px, extent m, deg):",
            dropped[:12],
        )
    return out


def ink_runs(row, o):
    """(centre, width, start, end) of each run of ink along a cross-section"""
    d = np.diff(np.concatenate([[0], row.astype(np.int8), [0]]))
    st, en = np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1
    step = o[1] - o[0]
    return [
        (
            (o[i] + o[j]) / 2,
            o[j] - o[i] + step,
            o[i] - step / 2,
            o[j] + step / 2,
        )
        for i, j in zip(st, en)
    ]


def grade(C, ink_raw, xmin, ymin, kind, half=10.0, pool=2, dash_pool=None):
    """THE CHECK, independent of the tracing: on the raw ink (no gap closing), across the line every metre (ink
    within +-pool m along it counts), where is the symbol's centre?
      - an ink run each side of the line, 3-20 m apart, both thin (<= 6 m)  -> their midpoint (two-edge road);
      - one wide run (>= 4.5 m) straddling the line                          -> its middle (filled highway);
      - creeks, contours (and single-line roads): the nearest run within 6 m  -> its middle; where a second run is
        also within 6 m (a steep slope, a parallel line) the nearest counts only if it is within 2.5 m of the line
        and the other at least 3.5 m further out -- a person reads that; the rest is ambiguous;
      - a dashed or dotted symbol: a section in a dash gap is re-read with ink pooled +-dash_pool m along the line
        (roads 12, creeks 15: a dash cycle), as the eye lines the dashes up.
    Anything else (a junction, lettering, a third line, a missing edge) is UNMEASURED. Dan's rule (Oct. 16, 2026):
    an unmeasured metre is a FAILED metre in the headline figure -- report within-2 m of the WHOLE line.
    Returns the offset of the centre from the line (m; NaN = unmeasured) and the road symbol found.
    """
    if dash_pool is None:
        dash_pool = {"road": 12, "creek": 15, "contour": 4}[kind]
    o = np.arange(-half, half + 1e-9, 0.5)
    N = normals(C)
    PX = C[:, 0, None] + o[None, :] * N[:, 0, None]
    PY = C[:, 1, None] + o[None, :] * N[:, 1, None]
    r = np.floor((PY - ymin) / RES).astype(int)
    c = np.floor((PX - xmin) / RES).astype(int)
    ok = (r >= 0) & (r < ink_raw.shape[0]) & (c >= 0) & (c < ink_raw.shape[1])
    prof0 = np.zeros(PX.shape, bool)
    prof0[ok] = ink_raw[r[ok], c[ok]]
    prof = (
        ndimage.maximum_filter1d(
            prof0.astype(np.uint8), size=2 * pool + 1, axis=0
        ).astype(bool)
        if pool
        else prof0
    )
    profd = (
        ndimage.maximum_filter1d(
            prof0.astype(np.uint8), size=2 * dash_pool + 1, axis=0
        ).astype(bool)
        if dash_pool > pool
        else prof
    )
    pair = np.full(len(C), np.nan)
    wide = np.full(len(C), np.nan)
    single = np.full(len(C), np.nan)

    def read(R, i):
        left = [q for q in R if q[0] < 0]
        right = [q for q in R if q[0] >= 0]
        if left and right:
            L, Rr = left[-1], right[0]
            if (
                L[3] < 0 < Rr[2]
                and 3 <= Rr[0] - L[0] <= 20
                and L[1] <= 6
                and Rr[1] <= 6
            ):  # the line in the white between them
                pair[i] = (L[0] + Rr[0]) / 2
        st = [q for q in R if q[2] <= 0 <= q[3] and q[1] >= 4.5]
        if st:
            wide[i] = st[0][0]
        near = sorted(
            [q for q in R if abs(q[0]) <= 6 and q[1] <= 8],
            key=lambda q: abs(q[0]),
        )
        if len(near) == 1 or (
            len(near) > 1
            and abs(near[0][0]) <= 2.5
            and abs(near[1][0]) - abs(near[0][0]) >= 3.5
        ):
            single[i] = near[0][0]

    for i in range(len(C)):
        R = ink_runs(prof[i], o)
        if R:
            read(R, i)
        got = (
            not np.isnan(pair[i]) if kind == "road" else not np.isnan(single[i])
        )
        if (
            not got and profd is not prof
        ):  # a dash gap: line the dashes up along the line
            R = ink_runs(profd[i], o)
            if R:
                read(R, i)
    if kind != "road":
        return single, "single line"
    n_pair, n_wide = int((~np.isnan(pair)).sum()), int((~np.isnan(wide)).sum())
    if max(n_pair, n_wide) < 0.1 * len(C):
        return single, "single line"
    m = np.where(~np.isnan(pair), pair, wide)
    return m, ("two edges" if n_pair >= n_wide else "filled band")


def edge_offsets(B, ink, xmin, ymin, half=14.0, pool=6, width=None, faint=None):
    """roads: per point of B, the offset of the road's centre from the line, read from the ink across it:
      - two thin runs (casings) either side, 3.5-20 m apart          -> their midpoint;
      - where no casing pairs are seen along the step, one run 3-9 m wide straddling the line (a filled highway,
        or a narrow double line whose casings merge at this scan)    -> its centre;
      - one casing only, at about half the road's width              -> that casing +- half the width,
        the width measured once per step (median casing separation) unless given -- so the line does not jump to
        whichever casing happens to be printed on a dashed road.
    Returns (offsets, NaN where nothing usable; width or None when no casing pairs were seen).
    """
    o = np.arange(-half, half + 1e-9, 0.5)
    N = normals(B)
    PX = B[:, 0, None] + o[None, :] * N[:, 0, None]
    PY = B[:, 1, None] + o[None, :] * N[:, 1, None]
    r = np.floor((PY - ymin) / RES).astype(int)
    c = np.floor((PX - xmin) / RES).astype(int)
    ok = (r >= 0) & (r < ink.shape[0]) & (c >= 0) & (c < ink.shape[1])
    prof = np.zeros(PX.shape, bool)
    prof[ok] = ink[r[ok], c[ok]]
    if pool:
        prof = ndimage.maximum_filter1d(
            prof.astype(np.uint8), size=2 * pool + 1, axis=0
        ).astype(bool)
    R = [ink_runs(prof[i], o) for i in range(len(B))]
    F = None
    if (
        faint is not None
    ):  # faint marks, read the same way, used only at an expected casing
        pf = np.zeros(PX.shape, bool)
        pf[ok] = faint[r[ok], c[ok]]
        if pool:
            pf = ndimage.maximum_filter1d(
                pf.astype(np.uint8), size=2 * pool + 1, axis=0
            ).astype(bool)
        F = [ink_runs(pf[i], o) for i in range(len(B))]
    pairs, strad = [None] * len(B), [None] * len(B)
    seps = []
    for i, runs_i in enumerate(R):
        thin = [q for q in runs_i if q[1] <= 6.0]
        L = [q for q in thin if q[0] < 0]
        Rr = [q for q in thin if q[0] >= 0]
        if (
            L
            and Rr
            and 3.5 <= Rr[0][0] - L[-1][0] <= 20
            and (Rr[0][2] - L[-1][3]) >= 0.5
        ):
            pairs[i] = ((L[-1][0] + Rr[0][0]) / 2, Rr[0][0] - L[-1][0])
            seps.append(Rr[0][0] - L[-1][0])
        st = [
            q
            for q in runs_i
            if 3.0 <= q[1] <= 9.0 and q[2] - 4.0 <= 0 <= q[3] + 4.0
        ]
        if st:
            strad[i] = min(st, key=lambda q: abs(q[0]))[0]
    if width is None and len(seps) >= 0.15 * len(B):
        width = float(np.median(seps))
    m = np.full(len(B), np.nan)
    for i, runs_i in enumerate(R):
        if (
            width is not None
            and pairs[i] is not None
            and abs(pairs[i][1] - width) <= 4.0
        ):
            m[i] = pairs[i][0]
        elif width is None and strad[i] is not None:
            m[i] = strad[i]  # no casing pairs along the step: a filled band
        elif width is not None:
            hw = width / 2
            thin = [q for q in runs_i if q[1] <= 6.0]
            L = [q for q in thin if q[0] < 0 and abs(-q[0] - hw) <= 3.5]
            Rr = [q for q in thin if q[0] >= 0 and abs(q[0] - hw) <= 3.5]
            if L or Rr:
                near = L[-1][0] if L else Rr[0][0]
                other = None
                if (
                    F is not None
                ):  # the other casing, faint, where the width says it should be
                    want = near + (width if L else -width)
                    cand = [
                        q
                        for q in F[i]
                        if q[1] <= 6.0 and abs(q[0] - want) <= 2.5
                    ]
                    if cand:
                        other = min(cand, key=lambda q: abs(q[0] - want))[0]
                m[i] = (
                    (near + other) / 2
                    if other is not None
                    else near + (hw if L else -hw)
                )
    return m, width


def robust_offsets(m, sigma, med_size=41, tol=2.5):
    """clean and smooth the per-metre centre offsets: readings are compared with a LOCAL TREND (a Gaussian-smoothed
    interpolation over sigma), not a flat median -- on a bend the true correction changes smoothly by several
    metres along the road, and a flat median rejected exactly those readings, leaving the line on the inside casing
    of every curve. Readings more than tol m from the trend (junctions, lettering) are dropped, the rest smoothed.
    """
    m = m.copy()
    idx = np.arange(len(m))
    good = ~np.isnan(m)
    if not good.any():
        return np.zeros(len(m))
    f = np.interp(idx, idx[good], m[good])
    trend = ndimage.gaussian_filter1d(
        ndimage.median_filter(f, size=med_size, mode="nearest"),
        sigma,
        mode="nearest",
    )
    with np.errstate(invalid="ignore"):
        m[np.abs(m - trend) > tol] = np.nan
    good = ~np.isnan(m)
    f = np.interp(idx, idx[good], m[good]) if good.any() else np.zeros(len(m))
    return ndimage.gaussian_filter1d(f, sigma, mode="nearest")


# ---------------------------------------------------------------- one line
def trace(sheets, prior, kind, label=""):
    """prior: [(lon, lat), ...] NAD83, first and last points are the pins. Returns (coords, stats)."""
    P = PARAM[kind]
    old = [tuple(p[:2]) for p in prior]
    lon0 = float(np.mean([p[0] for p in old]))
    lat0 = float(np.mean([p[1] for p in old]))
    mx, my = 111320.0 * math.cos(math.radians(lat0)), 110574.0
    X = np.array([(p[0] - lon0) * mx for p in old])
    Y = np.array([(p[1] - lat0) * my for p in old])
    pad = P["corridor"] + 12
    xmin, ymin = X.min() - pad, Y.min() - pad
    nx, ny = (
        int((X.max() + pad - xmin) / RES) + 1,
        int((Y.max() + pad - ymin) / RES) + 1,
    )
    to_cell = lambda lon, lat: (
        int(((lat - lat0) * my - ymin) / RES),
        int(((lon - lon0) * mx - xmin) / RES),
    )
    near = np.zeros((ny, nx), bool)
    bearing = np.zeros((ny, nx), np.float32)
    arc = np.zeros((ny, nx), np.float32)
    D = densify(old, RES / 2)
    s_along = 0.0
    for (lon, lat), (lon2, lat2) in zip(D, D[1:] + [D[-1]]):
        rc = to_cell(lon, lat)
        near[rc] = True
        arc[rc] = s_along
        if (lon2, lat2) != (lon, lat):
            bearing[rc] = math.atan2((lat2 - lat) * my, (lon2 - lon) * mx)
            s_along += math.hypot((lon2 - lon) * mx, (lat2 - lat) * my)
    d_prior, (ni, nj) = ndimage.distance_transform_edt(
        ~near, return_indices=True
    )
    d_prior = d_prior.astype(np.float32) * RES
    theta = bearing[ni, nj]
    arc_cell = arc[ni, nj]
    del near, ni, nj
    corr = d_prior <= P["corridor"]
    iy, ix = np.nonzero(corr)
    lons = lon0 + (xmin + (ix + 0.5) * RES) / mx
    lats = lat0 + (ymin + (iy + 0.5) * RES) / my
    faint = None
    if kind == "creek":
        ink_c, have, ext = sample_ink(
            sheets, kind, lons, lats, extra=("dotlike",)
        )
    elif kind == "road":
        ink_c, have, ext = sample_ink(
            sheets, kind, lons, lats, extra=("road_faint",)
        )
        faint = np.zeros((ny, nx), bool)
        faint[iy, ix] = ext["road_faint"]
    elif kind == "contour":
        ink_c, have, ext = sample_ink(
            sheets, kind, lons, lats, extra=("label", "text", "brown")
        )
        # LABEL ZONE: the label strip of ink.digit_holes plus the brown lettering removed from the contour ink, grown
        # LABEL_TEXT_GROW m. Inside it a gap costs a flat GAP (see the cost below)
        labelz = np.zeros((ny, nx), bool)
        labelz[iy, ix] = ext["label"]
        textb = np.zeros((ny, nx), bool)
        textb[iy, ix] = ext["text"] & ext["brown"] & ~ink_c
        labelz |= ndimage.binary_dilation(
            textb, structure=disk(LABEL_TEXT_GROW / RES)
        )
        # the DIGITS themselves (lettering grown LABEL_FLAT_GROW m, holes filled): one flat-cost area the path crosses
        # straight, through the middle of the numbers (Dan: "passing through the middles of the numbers")
        digitz = ndimage.binary_fill_holes(
            ndimage.binary_dilation(
                textb, structure=disk(LABEL_FLAT_GROW / RES)
            )
        )
    else:
        ink_c, have = sample_ink(sheets, kind, lons, lats)
    ink = np.zeros((ny, nx), bool)
    ink[iy, ix] = ink_c
    if (
        kind == "creek"
    ):  # dotted creeks: hop dot to dot along the direction of travel
        dl = np.zeros((ny, nx), bool)
        dl[iy, ix] = ext["dotlike"]
        ink |= chain_dots(ink, dl, RES, theta)
    if kind == "road":
        ink = drop_crossing(ink, theta)
    ink_raw = ink.copy()
    if P["fill"]:
        ink = directional_fill(ink, theta, int(P["fill"] / RES))
    band = ndimage.binary_dilation(ink, structure=disk(P["grow"] / RES))
    edt = ndimage.distance_transform_edt(band).astype(np.float32) * RES
    ridge = ndimage.maximum_filter(edt, size=int(2 * (P["grow"] + 6) / RES) + 1)
    d_out = ndimage.distance_transform_edt(~band).astype(np.float32) * RES
    off = GAP + np.minimum(d_out, 20.0) ** 2
    if kind == "contour":
        # a label printed ON the contour breaks it for 40-60 m. Off the band the gap cost rises with the distance from
        # ink (up to 420 per m mid-gap), so the cheapest crossing hugged leftover digit strokes or the NEIGHBOURING
        # contour -- the loops and hops Dan saw at "1700" (65), "1800" and "1885" (59) and "1800" (3), Oct. 16, 2026.
        # Inside the label zone the gap costs a flat GAP: the path crosses straight, all ink and band costs are kept
        # (this is not the dead-end strip of method.md, which removed the ink and followed the prior)
        off = np.where(labelz, GAP, off)
    cost = np.where(
        band, 1.0 + np.minimum(K_RIDGE * (ridge - edt) ** 2, 0.8 * GAP), off
    )
    cost = cost + (d_prior / P["prior"]) ** 2
    if kind == "contour" and LABEL_FLAT:
        # inside the digits every cell costs the same, band or not: leftover digit strokes (a 1, the outline of a 0
        # whose ring is broken) no longer pull the line along the bottoms of the numbers (triage, Oct. 16, 2026:
        # 15 label loops and 4 spikes after the flat-GAP change alone)
        cost = np.where(
            digitz,
            LABEL_FLAT
            + ((d_prior / P["prior"]) ** 2 if LABEL_FLAT_PRIOR else 0.0),
            cost,
        )
    if kind == "road":
        # junctions: the pins sit where roads meet, and the merged band of two roads (or a road and a fence line) has
        # its ridge in the junction, so the path hooked 10-15 m into the side road (point 94, Oct. 16, 2026); within
        # END_PULL m of either pin the prior is trusted more (the crossing road's ink is left to the cross-sections)
        near_end = (arc_cell < END_PULL) | (arc_cell > s_along - END_PULL)
        cost = cost + np.where(near_end, (d_prior / END_PULL_M) ** 2, 0.0)
    if DEBUG is not None:
        DEBUG.update(
            ink=ink,
            band=band,
            edt=edt,
            ridge=ridge,
            cost=cost,
            corr=corr,
            frame=(lon0, lat0, mx, my, xmin, ymin, RES),
        )
    # least-cost path on the corridor cells
    Nn = len(iy)
    node = -np.ones((ny, nx), np.int64)
    node[iy, ix] = np.arange(Nn)
    cc = cost[iy, ix].astype(np.float64)
    arc_s = arc_cell[iy, ix]
    A, Bv, W = [], [], []
    for dr, dc, ln in (
        (0, 1, 1.0),
        (1, 0, 1.0),
        (1, 1, math.sqrt(2)),
        (1, -1, math.sqrt(2)),
    ):
        r2, c2 = iy + dr, ix + dc
        ok = (r2 < ny) & (c2 >= 0) & (c2 < nx)
        j = np.full(Nn, -1, np.int64)
        j[ok] = node[r2[ok], c2[ok]]
        ok = j >= 0
        a = np.flatnonzero(ok)
        b = j[ok]
        # no shortcuts: where a contour or creek doubles back, both sides of the loop are in the corridor at its neck;
        # an edge between cells whose nearest prior points are > MAX_ARC_JUMP apart ALONG the prior is not allowed
        keep = np.abs(arc_s[a] - arc_s[b]) <= MAX_ARC_JUMP_KIND.get(
            kind, MAX_ARC_JUMP
        )
        a, b = a[keep], b[keep]
        A.append(a)
        Bv.append(b)
        W.append(ln * RES * 0.5 * (cc[a] + cc[b]))
    G = sparse.csr_matrix(
        (np.concatenate(W), (np.concatenate(A), np.concatenate(Bv))),
        shape=(Nn, Nn),
    )
    s = node[to_cell(*old[0])]
    t = node[to_cell(*old[-1])]
    assert s >= 0 and t >= 0, (label, "pin outside the corridor")
    dist, pred = csgraph.dijkstra(
        G, directed=False, indices=s, return_predecessors=True
    )
    assert np.isfinite(dist[t]), (label, "no path")
    path = [t]
    while path[-1] != s:
        path.append(pred[path[-1]])
    path = np.array(path[::-1])
    pr, pc = iy[path], ix[path]
    XY = np.column_stack(
        [xmin + (pc + 0.5) * RES, ymin + (pr + 0.5) * RES]
    ).astype(np.float64)
    pin0 = np.array([X[0], Y[0]])
    pin1 = np.array([X[-1], Y[-1]])
    XY[0], XY[-1] = pin0, pin1
    S = P["sym"]
    road_width = None
    if kind == "road":
        C = resample(smooth(XY, 8.0), 1.0)
        m, road_width = edge_offsets(C, ink_raw, xmin, ymin, faint=faint)
        if (
            (~np.isnan(m)).mean() >= 0.3
        ):  # casings or a band readable along the step: centre on them
            # END HOOKS (Oct. 16, 2026): with the end readings blanked, the interior offset carries straight to the pin
            # and the line runs parallel to the road centre until build_agreed's tie to the pin. At a pin checked ON
            # the ink centre where the line 12-40 m in is not (start of step 68: pin 67 on the highway centre, the line
            # 3.2 m low) the offset is held to 0 at the pin and tapered in over END_BLANK m. Listed per step id as
            # (start, end): an automatic on-centre test at the pin is NOT reliable at junctions (tried: it took 7
            # held-pin ends and missed pin 67), and a lateral offset on a curve into a junction (end of step 67) is the
            # road, not a hook. Pins off the centre are pin decisions and keep the old behaviour.
            hold = {"68": (True, False)}.get(
                str(label), (False, False)
            )  # pin 67, start of step 68 (highway)
            for it in range(3):
                # the pins sit at junctions: within END_BLANK m of each end the cross-sections also see the crossing
                # road's casings and the centre reading drifts (Dan saw a 4 m bulge below point 94); those readings are
                # dropped and the road's interior trend carries straight to the pin
                m[:END_BLANK] = np.nan
                m[-END_BLANK:] = np.nan
                shift = robust_offsets(m, P["shift_sigma"], med_size=41)
                k = np.arange(len(shift), dtype=float)
                w = np.ones(len(shift))
                if hold[0]:
                    w = np.minimum(w, k / END_BLANK)
                if hold[1]:
                    w = np.minimum(w, (len(shift) - 1 - k) / END_BLANK)
                C = resample(
                    smooth(C + (shift * w)[:, None] * normals(C), 6.0), 1.0
                )
                m, _ = edge_offsets(
                    C, ink_raw, xmin, ymin, width=road_width, faint=faint
                )
        else:  # a single line: centre of symmetry
            for _ in range(P["shift_iters"]):
                m, _, N = sym_offsets(C, ink, xmin, ymin, **S)
                C = resample(
                    smooth(
                        C + robust_offsets(m, P["shift_sigma"])[:, None] * N,
                        2.0,
                    ),
                    1.0,
                )
    else:
        C = resample(smooth(XY, P["sigma"]), 1.0)
    # ---- the check
    meas, symbol = grade(C, ink_raw, xmin, ymin, kind)
    pin_off = [
        round(float(np.nanmedian(np.abs(meas[sl]))), 1)
        if (~np.isnan(meas[sl])).any()
        else None
        for sl in (slice(1, 16), slice(-16, -1))
    ]
    core = np.zeros(len(C), bool)
    core[10:-10] = True  # pins and their junctions reported separately
    resid = np.abs(meas)
    r_ok = resid[core & ~np.isnan(resid)]
    off_runs = []
    for a, b in runs(core & (np.nan_to_num(resid, nan=0) > 2)):
        if b - a >= 3:
            k = a + int(np.nanargmax(resid[a:b]))
            x, y = C[k]
            off_runs.append(
                [
                    round(lon0 + x / mx, 6),
                    round(lat0 + y / my, 6),
                    int(b - a),
                    round(float(np.nanmax(resid[a:b])), 1),
                ]
            )
    gaps = []
    for a, b in runs(np.isnan(meas)):
        if b - a >= 8:
            x, y = C[(a + b) // 2]
            gaps.append(
                [round(lon0 + x / mx, 6), round(lat0 + y / my, 6), int(b - a)]
            )
    C[0], C[-1] = pin0, pin1
    keep = rdp(C, 0.3)
    coords = [
        [round(lon0 + x / mx, 9), round(lat0 + y / my, 9)] for x, y in C[keep]
    ]
    coords[0], coords[-1] = list(old[0]), list(old[-1])
    cr = np.clip(((C[:, 1] - ymin) / RES).astype(int), 0, ny - 1)
    ccol = np.clip(((C[:, 0] - xmin) / RES).astype(int), 0, nx - 1)
    dev = d_prior[cr, ccol]
    stats = dict(
        kind=kind,
        symbol=symbol,
        road_width_m=round(road_width, 1) if road_width else None,
        length_prior_m=round(
            float(np.sum(np.hypot(np.diff(X), np.diff(Y)))), 1
        ),
        length_m=round(float(np.sum(np.hypot(*np.diff(C[keep], axis=0).T))), 1),
        vertices=len(coords),
        measured_pct=round(100 * float((~np.isnan(meas[core])).mean()), 1)
        if core.any()
        else None,
        off_center_median_m=round(float(np.median(r_ok)), 2)
        if len(r_ok)
        else None,
        off_center_p95_m=round(float(np.percentile(r_ok, 95)), 2)
        if len(r_ok)
        else None,
        within_2m_pct=round(100 * float((r_ok <= 2).mean()), 1)
        if len(r_ok)
        else None,
        off_center_runs=sorted(off_runs, key=lambda q: -q[2] * q[3]),
        moved_median_m=round(float(np.median(dev)), 1),
        moved_max_m=round(float(dev.max()), 1),
        gaps=gaps,
        pin_start_off_center_m=pin_off[0],
        pin_end_off_center_m=pin_off[1],
        cells_without_sheet=int((~have).sum()),
    )
    return coords, stats


def summary(label, st):
    return (
        f"{label:>6} {st['kind']:7s} {st['length_prior_m']:7.0f} -> {st['length_m']:7.0f} m | measured {st['measured_pct']}% | "
        f"off centre med {st['off_center_median_m']} p95 {st['off_center_p95_m']} m, within 2 m {st['within_2m_pct']}% | "
        f"moved med {st['moved_median_m']} max {st['moved_max_m']} m | pins off {st['pin_start_off_center_m']}, "
        f"{st['pin_end_off_center_m']} m | gaps>=8 m {len(st['gaps'])}"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--quads",
        action="append",
        required=True,
        help="GeoTIFF/zip path or glob (repeatable)",
    )
    ap.add_argument("--lines", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--id-field", default="id")
    ap.add_argument("--kind-field", default="kind")
    ap.add_argument(
        "--kind", choices=inklib.KINDS, help="kind for features without one"
    )
    ap.add_argument("--ids", nargs="*", help="only these ids")
    a = ap.parse_args()
    sheets = open_sheets(a.quads)
    feats = json.load(open(a.lines))["features"]
    out = (
        json.load(open(a.out))
        if os.path.exists(a.out)
        else {"type": "FeatureCollection", "features": []}
    )
    have = {
        str(f["properties"]["id"]): i for i, f in enumerate(out["features"])
    }
    for f in feats:
        fid = str(f["properties"].get(a.id_field))
        kind = f["properties"].get(a.kind_field) or a.kind
        if a.ids and fid not in a.ids:
            continue
        if kind not in PARAM:
            continue
        coords, st = trace(sheets, f["geometry"]["coordinates"], kind, fid)
        feat = {
            "type": "Feature",
            "properties": {
                "id": fid,
                "traced": datetime.datetime.now().isoformat(timespec="seconds"),
                **st,
            },
            "geometry": {"type": "LineString", "coordinates": coords},
        }
        if fid in have:
            out["features"][have[fid]] = feat
        else:
            have[fid] = len(out["features"])
            out["features"].append(feat)
        json.dump(out, open(a.out, "w"))
        print(summary(fid, st), flush=True)


if __name__ == "__main__":
    main()
