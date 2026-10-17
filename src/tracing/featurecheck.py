"""Acceptance check: is a traced line on the RIGHT feature, not just near ink?

Why: grade() (centerline.py) asks every metre "is there ink of this class
within 6 m, and how far is its centre?". It never asks whether that ink is the
SAME line the trace was on a few metres before, so a contour trace that hops
onto the neighbouring contour on a steep slope is graded "centred" on the wrong
contour (Oct. 16, 2026: last night's step 65 spent 343 m on the next contour
and grade() gave that stretch 91% measured, 100% within 2 m, median 0.25 m).
The checks here look at IDENTITY and SHAPE, on the raw ink (no gap closing, no
lettering/digit removal), independent of the tracer and of the prior (the
prior is only drawn on the crops):

  hop        lane continuity in a straightened frame: cross-sections every 1 m
             (+-15 m, 0.5 m steps) of the feature's raw ink (contours:
             brown), runs tracked row to row into lanes; the lane under the
             line (|off| <= 1.5 m) is the one it rides. Where it stops riding a
             lane and some long line seen at the leaving point carries on
             BESIDE it (>= 20 m at >= 3 m off, or >= 10 m reaching >= 6 m;
             white paper between; not the line itself elsewhere, e.g. the
             other arm of a V) -- or where it starts riding a lane that already
             ran beside it -- that is a hop. A label/gap bridged correctly
             (line ends, line resumes) gives neither. A hop-out followed within
             600 m by a hop-in is an excursion: every metre between is flagged
             ("metres on the wrong line").
  crossing   (contours) a long line passes from one side of the trace to the
             other: contours never cross.
  wiggle     total |turn| - |net turn| over 40 m > 150 deg while >= 5 m of the
             window is off long-line ink (digits).
  bridge     off long-line ink (pieces >= 40 m) for 8-400 m: max distance from
             the Hermite bridge continuing the ink's direction either side >
             max(3 m, 5% of the chord).
  wrongclass the line rides another class's long ink for >= 10 m (contours:
             blue; creeks: brown/black).
  road_leave (roads) the line crosses a long casing lane.
  selfx / stepx  crosses itself / another step.
Per metre (the 10 m at each pin excluded, as in grade()): VERIFIED = grade()
within 2 m AND riding one continuous, unambiguous lane (roads: a casing each
side) AND no event within 20 m; FLAGGED = inside an event +-20 m, an excursion,
or graded > 2 m off over >= 3 m; UNMEASURED = the rest. Dan's rule: unmeasured
is not verified.

Validated Oct. 16, 2026 on the 5 contours (3 6 59 65 82) of three traced
versions: fires at all 4 owner-reported spots and at 19-20 of the 23 critic
"off" contour spots; quiet at 35 of 44 critic "centred" spots, and 6-7 of the
other 9 were real defects the critics passed (the 885 hop, loops through
1800/1500 labels); on the 3.5 km where last night's contours and today's
disagree by > 3 m, grade() passes 71% of last night's metres and this check
verifies 22.5%. Precision on non-label identity events about 8 in 13. Creek and
road modes RUN but are NOT validated (dotted creeks give short lanes): their
queue items say so. Known blind spots (BLIND_SPOTS below) are always queued for
a person.

CLI (the project .venv, -E -s):
  featurecheck.py --quads "GLOB" --traced traced.geojson --out-dir DIR
                  [--ids 3 6 ...] [--prior lines.geojson] [--no-crops]
Writes DIR/per_step.csv (current-check figures, VERIFIED/FLAGGED/UNMEASURED %,
metres, events by type, metres on the wrong line), DIR/queue.geojson (one point
per review item: events and unmeasured stretches >= 15 m clustered within 60 m
along the line, plus the known blind spots; step, types, lon/lat, size, crop
path, validated, status, priority 0 blind spot / 1 identity / 2 shape / 3
unmeasured) and DIR/crops/*.png (one close-up per item). Read only on its
inputs.
Acceptance (per step): no open queue items (each fixed and re-run, or signed
off by Dan on its crop), VERIFIED plus signed-off metres >= 95%, no
owner/critic "off" spot VERIFIED, no selfx/stepx, pins within 2 m or listed.
"""

import argparse
import csv
import itertools
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from scipy import ndimage
from scipy.spatial import cKDTree

import centerline as cl
import ink as inklib
from quadsheets import open_sheets
from quadsheets import sheet_of

HALF, DO = 15.0, 0.5  # cross-section half-width and step (m)
RIDE = 1.5  # |offset| of the lane under the line
BESIDE = 3.0  # a lane this far off is "beside" the line, not under it
# m before/after a switch where an abandoned / pre-existing lane is looked for
LOOK = 60
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
    """Returns the index of the sheet holding each NAD83 point (-1: none)."""
    idx = np.full(len(lons), -1)
    for k, sh in enumerate(sheets):
        todo = np.flatnonzero(idx < 0)
        if not len(todo):
            break
        _, _, inside, _ = sh.pixels(lons[todo], lats[todo])
        idx[todo[inside]] = k
    return idx


class StepGrid:
    """One 1 m grid per step, covering every version's line +-(HALF+3) m.

    The ink classes are sampled once, on the cells near the lines.

    Attributes:
        lon0: The grid frame's origin longitude (NAD83; the lines' mean).
        lat0: The grid frame's origin latitude.
        mx: Metres per degree of longitude at lat0.
        my: Metres per degree of latitude.
        xmin: The grid's x origin (m east of lon0).
        ymin: The grid's y origin (m north of lat0).
        g: Boolean grids by name: "kind" (the step's own ink class, with a
            creek's dots chained) and the ink.classes masks brown, black,
            blue, red, road, creek, contour, dotlike and text.
        kind: The step's kind.
        shape: The grid's (rows, cols).
        sheets: The open sheets.
        line: The feature's raw line ink (contours: brown not next to red
            fill; creeks: creek or blue; roads: road).
        long: The line ink's long pieces (>= 40 m).
        d_long: The distance to the nearest long piece (m).
        other_long: Other classes' long ink, for the wrong-class test.
    """

    def __init__(self, sheets, lines, kind):
        """Builds the grid around the lines and samples the ink on it.

        Args:
            sheets: The open sheets (quadsheets.open_sheets).
            lines: The NAD83 coordinates of each version of the step's line.
            kind: "contour", "creek" or "road".
        """
        allc = np.vstack([np.asarray(c)[:, :2] for c in lines])
        self.lon0, self.lat0 = (
            float(allc[:, 0].mean()),
            float(allc[:, 1].mean()),
        )
        self.mx, self.my = (
            111320.0 * math.cos(math.radians(self.lat0)),
            110574.0,
        )
        lines_xy = [self.xy(c) for c in lines]
        all_xy = np.vstack(lines_xy)
        pad = HALF + 6
        self.xmin, self.ymin = (
            all_xy[:, 0].min() - pad,
            all_xy[:, 1].min() - pad,
        )
        nx, ny = (
            int((all_xy[:, 0].max() + pad - self.xmin) / cl.RES) + 1,
            int((all_xy[:, 1].max() + pad - self.ymin) / cl.RES) + 1,
        )
        near = np.zeros((ny, nx), bool)
        for pts in lines_xy:
            dense = cl.resample(pts, 0.5)
            rr = np.clip(
                ((dense[:, 1] - self.ymin) / cl.RES).astype(int), 0, ny - 1
            )
            cc = np.clip(
                ((dense[:, 0] - self.xmin) / cl.RES).astype(int), 0, nx - 1
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
        kink, _have, ext = cl.sample_ink(sheets, kind, lons, lats, extra=extra)
        self.g = {}
        for k in ("kind", *extra):
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
        # the feature's raw line ink for identity: contours = brown that is not
        # road ink; creeks = creek ink; roads = road ink (casings)
        # (not "brown minus road": over the halftone tint a contour breaks into
        # dash-shaped pieces that ink.dashes() gives to the road class; only the
        # highway casings next to the red fill are taken out)
        # Brown only. Over the halftone woodland tint some contour ink classes
        # black (olive-grey); brown|black was tried Oct. 16 and lost two
        # owner-reported hops (roads and fences become lanes) -- that is blind
        # spot 59/(-99.0094, 30.9285)
        if kind == "contour":
            self.line = self.g["brown"] & ~ndimage.binary_dilation(
                self.g["red"], iterations=3
            )
        elif kind == "creek":
            self.line = self.g["creek"] | self.g["blue"]
        else:
            self.line = self.g["road"]
        # LONG-line ink: connected pieces whose principal-axis length is >= 40 m
        # (digits, ticks, dots drop out)
        self.long = long_pieces(self.line, 40.0)
        self.d_long = ndimage.distance_transform_edt(~self.long) * cl.RES
        # other classes' long ink, for the wrong-class test
        # (contours: blue only -- roads and lettering print over contours
        # everywhere and hide them; lettering never)
        txt = ndimage.binary_dilation(self.g["text"], iterations=2)
        if kind == "contour":
            other = self.g["blue"]
        elif kind == "creek":
            other = (self.g["brown"] & ~self.g["road"]) | self.g["black"]
        else:
            other = self.g["brown"] & ~self.g["road"]
        self.other_long = long_pieces(other & ~txt, 40.0)

    def xy(self, coords):
        """Returns NAD83 coordinates as (n, 2) metres in the grid's frame."""
        c = np.asarray(coords)[:, :2]
        return np.column_stack(
            [(c[:, 0] - self.lon0) * self.mx, (c[:, 1] - self.lat0) * self.my]
        )

    def lonlat(self, pts):
        """Returns (lon, lat) of points given in the grid's frame (m)."""
        return self.lon0 + pts[..., 0] / self.mx, self.lat0 + pts[
            ..., 1
        ] / self.my

    def sample(self, mask, px, py):
        """Samples a grid at points px, py (m); False outside the grid."""
        r = np.floor((py - self.ymin) / cl.RES).astype(int)
        c = np.floor((px - self.xmin) / cl.RES).astype(int)
        ok = (r >= 0) & (r < self.shape[0]) & (c >= 0) & (c < self.shape[1])
        out = np.zeros(px.shape, bool)
        out[ok] = mask[r[ok], c[ok]]
        return out


def long_pieces(mask, min_len):
    """Returns the connected pieces of a mask at least min_len metres long.

    A piece's length is its box's longer side or, when that is shorter, the
    length of a uniform bar with its spread along its principal axis (a
    diagonal piece).
    """
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
        pix = np.column_stack([xs, ys]).astype(float)
        pix -= pix.mean(0)
        sv = np.linalg.svd(pix, compute_uv=False)
        if 2 * math.sqrt(3) * sv[0] / math.sqrt(len(pix)) * cl.RES >= min_len:
            keep[k] = True
    return keep[lab]


# ---------------------------------------------- lanes in the straightened frame
def typical_width(strip, o):
    """Returns the median width (m) of the ink runs under the line, else 3.0.

    The runs whose centre lies within RIDE of the line, over every row.
    """
    widths = [
        q[1]
        for i in range(strip.shape[0])
        for q in (cl.ink_runs(strip[i], o) if strip[i].any() else [])
        if abs(q[0]) <= RIDE
    ]
    return float(np.median(widths)) if widths else 3.0


def track_lanes(strip, o, wide=None):
    """Tracks the runs of ink across the line, row to row, into lanes.

    A run of ink continues a lane when it lies within GATE of the lane's last
    offset (or of its extrapolation), or contains the last offset; ties go to
    the OLDER lane. A lane whose last offset lies inside the (ordinary-width)
    run taken by an older lane is the same line seen twice and is absorbed
    into it. A run wider than `wide` (by default 1.6 x the line's typical
    width, at least 8 m) holds lines welded together: lanes inside it coast,
    marked merged (identity ambiguous). A lane unseen for more than COAST
    rows ends.

    Args:
        strip: The ink across the line: rows (1 m along the line) x columns
            (offsets o).
        o: The columns' offsets (m).
        wide: The width (m) above which a run is lines welded together.

    Returns:
        The lanes: dicts of arrays rows, offs, wid and merged (one entry per
        row the lane is seen in) and life (rows from its first to its last).
    """
    if wide is None:
        wide = max(8.0, 1.6 * typical_width(strip, o))
    lanes, active = [], []
    for i in range(strip.shape[0]):
        found = cl.ink_runs(strip[i], o) if strip[i].any() else []
        used = [False] * len(found)
        upd = {}
        cand = []
        for li in active:
            lane = lanes[li]
            dt = i - lane["rows"][-1]
            last = lane["offs"][-1]
            v = 0.0
            if len(lane["rows"]) >= 4:
                v = float(
                    np.clip(
                        (lane["offs"][-1] - lane["offs"][-4])
                        / max(lane["rows"][-1] - lane["rows"][-4], 1),
                        -1.0,
                        1.0,
                    )
                )
            pred = last + v * dt
            gate = GATE + 0.25 * (dt - 1)
            for j, q in enumerate(found):
                d = min(
                    abs(q[0] - pred), abs(q[0] - last)
                )  # the run grid is 0.5 m: jitter is not velocity
                if q[1] <= wide and q[2] <= last <= q[3]:
                    d = min(d, 0.25)
                if d <= gate:
                    cand.append(
                        (round(d * 2) / 2, lane["rows"][0], li, j, pred)
                    )
                elif q[1] > wide and q[2] - 0.5 <= pred <= q[3] + 0.5:
                    cand.append((gate + 0.5, lane["rows"][0], li, j, pred))
        for _d, _, li, j, pred in sorted(cand):
            if li in upd:
                continue
            q = found[j]
            lane = lanes[li]
            if used[j]:
                if (
                    q[1] > wide and q[2] - 0.5 <= pred <= q[3] + 0.5
                ):  # a second lane inside a welded run: coasts
                    lane["rows"].append(i)
                    lane["offs"].append(pred)
                    lane["wid"].append(q[1])
                    lane["merged"].append(True)
                    upd[li] = j
                continue
            used[j] = True
            lane["rows"].append(i)
            lane["offs"].append(q[0])
            lane["wid"].append(q[1])
            lane["merged"].append(q[1] > wide)
            upd[li] = j
        for j, q in enumerate(found):
            if not used[j]:
                lanes.append(
                    dict(
                        rows=[i], offs=[q[0]], wid=[q[1]], merged=[q[1] > wide]
                    )
                )
                active.append(len(lanes) - 1)
                upd[len(lanes) - 1] = j
        # twins: a younger lane whose last offset lies inside the ordinary run
        # an older lane took this row
        dead = set()
        for la, j in upd.items():
            q = found[j]
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
                    keeper, absorbed = lanes[la], lanes[lb]
                    for k in ("rows", "offs", "wid", "merged"):
                        keeper[k] = keeper[k] + absorbed[k]
                    order = np.argsort(keeper["rows"], kind="stable")
                    for k in ("rows", "offs", "wid", "merged"):
                        keeper[k] = [keeper[k][x] for x in order]
                    absorbed["rows"] = []
                    dead.add(lb)
        active = [
            li
            for li in active
            if li not in dead and i - lanes[li]["rows"][-1] <= COAST
        ]
    lanes = [lane for lane in lanes if lane["rows"]]
    for lane in lanes:
        r = np.array(lane["rows"])
        _, first = np.unique(r, return_index=True)
        lane["rows"] = r[first]
        lane["offs"] = np.array(lane["offs"])[first]
        lane["wid"] = np.array(lane["wid"])[first]
        lane["merged"] = np.array(lane["merged"])[first]
        lane["life"] = int(lane["rows"][-1] - lane["rows"][0] + 1)
    return lanes


def ridden_sequence(lanes, n):
    """Finds which long lane the line rides, row by row.

    Returns:
        (rid, amb): per row, the index of the long lane (life >= LANE_MIN)
        nearest under the line, within RIDE (-1: none), and an 'ambiguous'
        flag (a merged run under the line, or two long lanes within +-RIDE).
    """
    rid = np.full(n, -1)
    best = np.full(n, np.inf)
    amb = np.zeros(n, bool)
    cnt = np.zeros(n, int)
    for li, lane in enumerate(lanes):
        if lane["life"] < LANE_MIN:
            continue
        sel = np.abs(lane["offs"]) <= RIDE
        for i, off, mg in zip(
            lane["rows"][sel],
            lane["offs"][sel],
            lane["merged"][sel],
            strict=True,
        ):
            cnt[i] += 1
            if mg:
                amb[i] = True
            if abs(off) < best[i]:
                best[i] = abs(off)
                rid[i] = li
    amb |= cnt >= 2
    return rid, amb


def lane_beside(lane, lo, hi, strip=None, o=None, elsewhere=None):
    """Measures how much of a lane runs BESIDE the line in rows [lo, hi).

    Beside means: BESIDE <= |off| <= HALF - 1, white paper (>= 1 m with no
    ink) between it and the line -- so a heavy line's halo or a split run is
    not a second line -- and not on the line itself somewhere else (the other
    arm of a V or a hairpin is the same contour: `elsewhere` gives a
    per-observation flag computed from the whole line). The white paper is
    looked for only when strip and o are given, the line elsewhere only when
    elsewhere is.

    Returns:
        (metres, largest |off|) of the lane seen beside the line there.
    """
    sel = (
        (lane["rows"] >= lo)
        & (lane["rows"] < hi)
        & (np.abs(lane["offs"]) >= BESIDE)
        & (np.abs(lane["offs"]) <= HALF - 1)
    )
    if strip is not None and sel.any():
        k0 = len(o) // 2
        for x in np.flatnonzero(sel):
            r, f = lane["rows"][x], lane["offs"][x]
            j = round((f + HALF) / DO)
            between = (
                strip[r, k0:j] if j > k0 else strip[r, j + 1 : k0 + 1][::-1]
            )
            # the lane's own run is at the far end; require a white stretch of
            # >= 2 cells somewhere between
            w = ~between
            best = 0
            cur = 0
            for v in w:
                cur = cur + 1 if v else 0
                best = max(best, cur)
            if best < 2:
                sel[x] = False
    if elsewhere is not None and sel.any():
        sel &= ~elsewhere(lane, sel)
    return int(sel.sum()), float(
        np.abs(lane["offs"][sel]).max()
    ) if sel.any() else 0.0


def hop_events(lanes, rid, n, strip=None, o=None, line=None, nrm=None):
    """Finds the hops: the line leaves a line that carries on beside it.

    Each END of riding a lane is a hop when a long lane seen at the line near
    the leaving point runs beside it (lane_beside) for >= 2 x BESIDE_MIN m,
    or >= BESIDE_MIN m reaching >= 6 m off, within LOOK m after; each START
    when a lane at the line there ran beside it as much within LOOK m before.
    See the module doc.

    Args:
        lanes: track_lanes()'s lanes.
        rid: ridden_sequence()'s lane per row.
        n: The number of rows.
        strip: The ink strip (for lane_beside's white-paper test), or None.
        o: The strip's offsets (m).
        line: The line's points (m), for the "elsewhere" test, or None.
        nrm: The line's normals.

    Returns:
        A list of event dicts (type "hop", r0, r1, size_m, why).
    """
    tree = cKDTree(line) if line is not None else None

    def elsewhere(lane, sel):
        """Flags a lane's observations that lie within 2 m of the line anywhere.

        Returns a boolean array over the lane's rows, set only where sel is.
        """
        r = lane["rows"][sel]
        f = lane["offs"][sel]
        pts = line[r] + f[:, None] * nrm[r]
        # an observation >= 3 m off its own row that is within 2 m of the line
        # ANYWHERE is ink the line rides elsewhere (the other arm of a V, a
        # hairpin, the far side of a tight bend), not a second line
        out = np.zeros(len(lane["rows"]), bool)
        out[np.flatnonzero(sel)] = tree.query(pts)[0] <= 2.0
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
    # each END of riding a lane (the next lane ridden is another one) is tested
    # for "the old line carries on beside"; each START of riding a lane (the
    # previous one was another) for "the new line was already running beside".
    # Lane identity at a fork is arbitrary (the tracker may hand the old id to
    # either branch), so the line that "carries on" is ANY long lane seen within
    # 3.5 m of the line's position at the leaving point, not just the old id.
    at = {}
    k0 = len(o) // 2
    for li, lane in enumerate(lanes):
        if lane["life"] < LANE_MIN:
            continue
        for r, f in zip(lane["rows"], lane["offs"], strict=True):
            if abs(f) <= 3.5:
                at.setdefault(int(r), set()).add(li)
            elif (
                abs(f) <= 8.0 and strip is not None
            ):  # or its ink joins the ink under the line (a fork)
                j = round((f + HALF) / DO)
                seg = strip[r, min(j, k0) : max(j, k0) + 1]
                if (~seg).sum() <= 1:
                    at.setdefault(int(r), set()).add(li)

    def near(lo, hi):
        out = set()
        for r in range(lo, hi + 1):
            out |= at.get(r, set())
        return out

    for x, (lane_out, _a0, a1) in enumerate(segs):
        if x + 1 < len(segs) and segs[x + 1][0] == lane_out:
            continue
        nxt = segs[x + 1][0] if x + 1 < len(segs) else None
        best = (0, 0.0)
        for lj in near(a1 - 3, a1 + 6) - {nxt}:
            best = max(
                best,
                lane_beside(lanes[lj], a1 + 1, a1 + 1 + LOOK, strip, o, ew),
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
                    why=(
                        "left a line that carries on beside it "
                        f"({outm} m, up to {outx:.1f} m off)"
                    ),
                )
            )
    for x, (lane_in, b0, _b1) in enumerate(segs):
        if x > 0 and segs[x - 1][0] == lane_in:
            continue
        prv = segs[x - 1][0] if x > 0 else None
        best = (0, 0.0)
        for lj in near(b0 - 6, b0 + 3) - {prv}:
            best = max(
                best,
                lane_beside(lanes[lj], max(0, b0 - LOOK), b0, strip, o, ew),
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
                    why=(
                        "joined a line that ran beside it before "
                        f"({inm} m, up to {inx:.1f} m off)"
                    ),
                )
            )
    return ev


def crossing_events(lanes, n, rid=None):
    """Finds long lines crossing from one side of the line to the other.

    For contours (contours never cross): a long lane (life >= LANE_MIN) seen
    >= 2 m on one side and then, within 20 m, >= 2 m on the other, with at
    least 8 sightings on each side within 40 m -- unless the line rides that
    lane over 60% of the rows from 30 m before to 30 m after (its own
    contour drifting from side to side).

    Returns:
        A list of event dicts (type "crossing", r0, r1, size_m, why).
    """
    ev = []
    for li, lane in enumerate(lanes):
        if lane["life"] < LANE_MIN:
            continue
        r, f = lane["rows"], lane["offs"]
        pos = np.flatnonzero(f >= 2.0)
        neg = np.flatnonzero(f <= -2.0)
        if not len(pos) or not len(neg):
            continue
        # a transition: last row on one side, first row on the other within 20 m
        side = np.where(f >= 2.0, 1, np.where(f <= -2.0, -1, 0))
        k = np.flatnonzero(side != 0)
        for a, b in itertools.pairwise(k):
            if side[a] != side[b] and r[b] - r[a] <= 20:
                before = int(
                    ((r <= r[a]) & (r >= r[a] - 40) & (side == side[a])).sum()
                )
                after = int(
                    ((r >= r[b]) & (r <= r[b] + 40) & (side == side[b])).sum()
                )
                # the line's OWN contour drifting from one side to the other is
                # wobble (graded off-centre), not a crossing
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
                            why=(
                                f"a {lane['life']} m line passes "
                                f"from {f[a]:+.1f} m to {f[b]:+.1f} m "
                                "across the line"
                            ),
                        )
                    )
    return ev


# ---------------------------------------------------------------- shape checks
def headings(pts, h=2):
    """Returns each point's unwrapped heading (radians), over +-h points."""
    n = len(pts)
    i = np.arange(n)
    delta = pts[np.minimum(i + h, n - 1)] - pts[np.maximum(i - h, 0)]
    return np.unwrap(np.arctan2(delta[:, 1], delta[:, 0]))


def wiggle_events(pts, d_long=None):
    """Finds loops through label digits.

    Total |turn| - |net turn| over WIGGLE_WIN m > WIGGLE_DEG, AND inside that
    window the line spends >= 5 m off long-line ink (it is riding digit
    strokes or nothing; with d_long None the ink is not looked at). A real
    hairpin or S-bend of the contour turns as much, but the line stays on the
    contour's own long ink the whole way.

    Returns:
        (events, score): the event dicts (type "wiggle") and the wiggle score
        (degrees) at each point.
    """
    th = headings(pts)
    d = np.diff(th)
    n = len(pts)
    win = WIGGLE_WIN
    a = np.concatenate([[0], np.cumsum(np.abs(d))])
    s = np.concatenate([[0], np.cumsum(d)])
    i = np.arange(0, max(n - win, 0))
    if not len(i):
        return [], np.zeros(n)
    tot = a[i + win - 1] - a[i]
    net = np.abs(s[i + win - 1] - s[i])
    wig = np.degrees(tot - net)
    if d_long is not None:
        offl = np.concatenate([[0], np.cumsum(d_long > RIDE + 0.5)])
        offm = offl[i + win] - offl[i]
        wig = np.where(offm >= 5, wig, 0.0)
    score = np.zeros(n)
    score[i + win // 2] = wig
    ev = []
    for r0, r1 in cl.runs(score > WIGGLE_DEG):
        k = r0 + int(np.argmax(score[r0:r1]))
        ev.append(
            dict(
                type="wiggle",
                r0=int(r0),
                r1=int(r1),
                size_m=round(float(score[k]), 0),
                why=(
                    f"turns {score[k]:.0f} deg back and forth within {win} m "
                    "while off the line's ink (loop through digits?)"
                ),
            )
        )
    return ev, score


def bridge_events(pts, grid):
    """Finds gaps in the long-line ink that the line does not bridge smoothly.

    Where the line is off long-line ink for 8-400 m it must bridge the gap
    smoothly: it is compared with the cubic Hermite curve between the ink
    either side, with the line's own direction over the 10 m of ink before
    and after the gap (straight across a label on a straight contour, along
    the bend for a gap on a bend). Max distance > max(3 m, 5% of the chord)
    is flagged.

    Returns:
        (events, d): the event dicts (type "bridge") and each point's
        distance from long-line ink (m).
    """
    d = d_long_at(grid, pts)
    off = d > RIDE + 0.5
    ev = []
    n = len(pts)
    for a, b in cl.runs(off):
        gap_len = b - a
        if gap_len < 8 or gap_len > 400 or a < 11 or b + 10 >= n:
            continue
        p0, p1 = pts[a - 1], pts[b]
        ch = float(np.hypot(*(p1 - p0)))
        if ch < 1:
            continue
        t0 = pts[a - 1] - pts[a - 11]
        t1 = pts[b + 10] - pts[b]
        t0 = t0 / (np.hypot(*t0) + 1e-9) * ch
        t1 = t1 / (np.hypot(*t1) + 1e-9) * ch
        u = np.linspace(0, 1, 4 * gap_len + 2)[:, None]
        herm = (
            (2 * u**3 - 3 * u**2 + 1) * p0
            + (u**3 - 2 * u**2 + u) * t0
            + (-2 * u**3 + 3 * u**2) * p1
            + (u**3 - u**2) * t1
        )
        dev = cKDTree(herm).query(pts[a:b])[0]
        k = int(np.argmax(dev))
        tol = max(3.0, 0.05 * ch)
        if dev[k] > tol:
            ev.append(
                dict(
                    type="bridge",
                    r0=int(a),
                    r1=int(b),
                    size_m=round(float(dev[k]), 1),
                    why=(
                        f"off the line ink for {gap_len} m and "
                        f"{dev[k]:.1f} m from a smooth bridge "
                        f"across the gap (chord {ch:.0f} m)"
                    ),
                )
            )
    return ev, d


def d_long_at(grid, pts):
    """Returns each point's distance (m) from long-line ink (on the grid)."""
    r = np.clip(
        ((pts[:, 1] - grid.ymin) / cl.RES).astype(int), 0, grid.shape[0] - 1
    )
    c = np.clip(
        ((pts[:, 0] - grid.xmin) / cl.RES).astype(int), 0, grid.shape[1] - 1
    )
    return grid.d_long[r, c]


def wrongclass_events(pts, grid):
    """Finds where the line rides another class's long ink for >= 10 m.

    Within +-RIDE of the line there is the other classes' long ink and none
    of its own (contours: blue; creeks: brown/black). Roads are not checked.

    Returns:
        A list of event dicts (type "wrongclass", r0, r1, size_m, why).
    """
    if grid.kind == "road":
        return []
    nrm = cl.normals(pts)
    o = np.arange(-RIDE, RIDE + 1e-9, 0.5)
    px = pts[:, 0, None] + o * nrm[:, 0, None]
    py = pts[:, 1, None] + o * nrm[:, 1, None]
    oth = grid.sample(grid.other_long, px, py).any(1)
    own = grid.sample(grid.line, px, py).any(1)
    ev = []
    for a, b in cl.runs(oth & ~own):
        if b - a >= 10:
            ev.append(
                dict(
                    type="wrongclass",
                    r0=int(a),
                    r1=int(b),
                    size_m=float(b - a),
                    why=(
                        "rides other ink ("
                        f"{'blue' if grid.kind == 'contour' else 'brown/black'}"
                        f") for {b - a} m"
                    ),
                )
            )
    return ev


def seg_intersections(pts, other=None, cell=5.0, min_sep=4):
    """Finds where polyline pts crosses itself, or another polyline.

    Segments are put in buckets of cell x cell (m) to find the candidates.

    Returns:
        A sorted list of (i, j) segment index pairs: with other None, the
        segments of pts that cross each other, at least min_sep apart
        (i < j); else segment i of pts crossing segment j of other.
    """

    def buckets(poly):
        cells = {}
        for i in range(len(poly) - 1):
            x0, x1 = sorted((poly[i, 0], poly[i + 1, 0]))
            y0, y1 = sorted((poly[i, 1], poly[i + 1, 1]))
            for gx in range(math.floor(x0 / cell), math.floor(x1 / cell) + 1):
                for gy in range(
                    math.floor(y0 / cell), math.floor(y1 / cell) + 1
                ):
                    cells.setdefault((gx, gy), []).append(i)
        return cells

    def cross(a, b, c, d):
        def o(p, q, r):
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

        return (o(a, b, c) * o(a, b, d) < 0) and (o(c, d, a) * o(c, d, b) < 0)

    cells_p = buckets(pts)
    out = set()
    if other is None:
        for segs in cells_p.values():
            for x in range(len(segs)):
                for y in range(x + 1, len(segs)):
                    i, j = segs[x], segs[y]
                    if abs(i - j) >= min_sep and cross(
                        pts[i], pts[i + 1], pts[j], pts[j + 1]
                    ):
                        out.add((min(i, j), max(i, j)))
    else:
        cells_q = buckets(other)
        for k, segs in cells_p.items():
            for j in cells_q.get(k, []):
                for i in segs:
                    if cross(pts[i], pts[i + 1], other[j], other[j + 1]):
                        out.add((i, j))
    return sorted(out)


# ---------------------------------------------------------------- one line
def check_line(grid, coords, others=(), sheet_rows=None):
    """Runs every check on one traced line.

    Args:
        grid: The step's StepGrid.
        coords: The line's NAD83 coordinates.
        others: (name, coordinates) of the other steps, for crossings.
        sheet_rows: The sheet index of each metre of the line, to tag the
            events near a neatline crossing; or None.

    Returns:
        A dict: C (the line resampled at 1 m, in m), meas (grade()'s
        offsets), rid, amb, lanes, events, the per-metre masks verified,
        flagged and unmeasured, stats (the figures of per_step.csv), queue
        (the unmeasured stretches of 15 m or more) and unmeasured_runs.
    """
    pts = grid.xy(coords)
    line = cl.resample(pts, 1.0)
    line[0], line[-1] = pts[0], pts[-1]
    n = len(line)
    meas, _symbol = cl.grade(
        line, grid.g["kind"], grid.xmin, grid.ymin, grid.kind
    )
    o = np.arange(-HALF, HALF + 1e-9, DO)
    nrm = cl.normals(line)
    px = line[:, 0, None] + o * nrm[:, 0, None]
    py = line[:, 1, None] + o * nrm[:, 1, None]
    strip = grid.sample(grid.line, px, py)
    lanes = track_lanes(strip, o)
    rid, amb = ridden_sequence(lanes, n)
    ev = []
    if grid.kind in ("contour", "creek"):
        ev += hop_events(lanes, rid, n, strip, o, line, nrm)
        if grid.kind == "contour":
            ev += crossing_events(lanes, n, rid)
    else:
        ev += road_events(lanes, n)
    d_long = None
    if grid.kind != "road":
        be, d_long = bridge_events(line, grid)
        ev += be
    we, _wscore = wiggle_events(line, d_long)
    ev += we
    ev += wrongclass_events(line, grid)
    for i, j in seg_intersections(line):
        ev.append(
            dict(
                type="selfx",
                r0=i,
                r1=i + 1,
                size_m=0,
                why=f"crosses itself (metre {j})",
            )
        )
    for name, other_coords in others:
        for i, _j in seg_intersections(
            line, grid.xy(other_coords) if len(other_coords) else None
        ):
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
    # sheet edges: events within 30 m of a neatline crossing are tagged (a jog
    # there is expected and reported)
    if sheet_rows is not None:
        edges = np.flatnonzero(np.diff(sheet_rows) != 0)
        for e in ev:
            if (
                len(edges)
                and np.min(np.abs(edges - (e["r0"] + e["r1"]) / 2)) <= 30
            ):
                e["sheet_edge"] = True
    ev = [e for e in ev if e["r1"] >= END_SKIP and e["r0"] <= n - 1 - END_SKIP]
    # context, for the reader only (pass/fail does not depend on it): a sharp
    # bend at the event, lettering near it
    th = headings(line)
    tx = ndimage.binary_dilation(grid.g["text"], structure=cl.disk(12 / cl.RES))
    for e in ev:
        a0, a1 = max(0, e["r0"] - 10), min(n - 1, e["r1"] + 10)
        e["turn_deg"] = round(abs(math.degrees(th[a1] - th[a0])))
        seg = line[e["r0"] : e["r1"] + 1]
        rr = np.clip(
            ((seg[:, 1] - grid.ymin) / cl.RES).astype(int), 0, grid.shape[0] - 1
        )
        cc = np.clip(
            ((seg[:, 0] - grid.xmin) / cl.RES).astype(int), 0, grid.shape[1] - 1
        )
        e["at_label"] = bool(tx[rr, cc].any())
        e["context"] = (
            "label"
            if e["at_label"]
            else ("sharp bend" if e["turn_deg"] >= 100 else "")
        )
    for e in ev:
        k = (e["r0"] + e["r1"]) // 2
        lo, la = grid.lonlat(line[k])
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
    for x, y in itertools.pairwise(hops):
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
    lane_ok = road_ok(lanes, n) if grid.kind == "road" else (rid >= 0) & ~amb
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
        # metres grade() calls within 2 m that are NOT on one continuous lane,
        # or inside an event
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
            lo, la = grid.lonlat(line[k])
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
        C=line,
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


# ------------------------------------------------------- roads: the casing pair
def road_ok(lanes, n):
    """Roads: marks the metres with a long lane on each side (a casing pair).

    A lane (life >= LANE_MIN) counts on a side from 1.25 m to 11 m off the
    line, and a casing seen within +-8 m along counts (dashes).
    """
    left = np.zeros(n, bool)
    right = np.zeros(n, bool)
    for lane in lanes:
        if lane["life"] < LANE_MIN:
            continue
        f = lane["offs"]
        r = lane["rows"]
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
    """Roads: finds where the line crosses a long casing lane.

    That is, it went over the road's edge onto something else: a lane of life
    >= 25 seen >= 1 m on one side and then, within 15 m, on the other, with
    at least 12 sightings on each side within 40 m.

    Returns:
        A list of event dicts (type "road_leave", r0, r1, size_m, why).
    """
    ev = []
    for lane in lanes:
        if lane["life"] < 25:
            continue
        r, f = lane["rows"], lane["offs"]
        side = np.where(f >= 1.0, 1, np.where(f <= -1.0, -1, 0))
        k = np.flatnonzero(side != 0)
        for a, b in itertools.pairwise(k):
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
                            why=(
                                f"a {lane['life']} m casing/line passes "
                                f"from {f[a]:+.1f} m to {f[b]:+.1f} m "
                                "across the line"
                            ),
                        )
                    )
    return ev


# ---------------------------- known blind spots (always queued, never verified)
# Places where the checks above are known to be blind (Oct. 16, 2026); a person
# signs each off on its crop.
BLIND_SPOTS = [
    (
        "59",
        -99.0094,
        30.9285,
        (
            "grey contour over the tint: the abandoned contour prints grey "
            "(classes black) over the halftone tint, so a hop here is "
            "invisible to the lane test; every version and the prior step "
            "onto the next contour here"
        ),
    ),
    (
        "59",
        -99.0222,
        30.9380,
        (
            "label digits not detected by ink.py: check the line bridges the "
            "label straight on its own contour"
        ),
    ),
    (
        "59",
        -99.0231,
        30.9378,
        (
            "label digits not detected by ink.py: check the line bridges the "
            "label straight on its own contour"
        ),
    ),
    (
        "82",
        -99.2068,
        30.7202,
        (
            "label digits not detected by ink.py: check the line bridges the "
            "label straight on its own contour"
        ),
    ),
    (
        "3",
        -99.3951,
        30.7775,
        (
            "the '1' of a contour label has no hole and is not detected: check "
            "for a spike toward it"
        ),
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

# ------------------------------------------------------- crops for the reviewer
COL = {
    "black": (255, 0, 255),
    "red": (255, 140, 0),
    "brown": (0, 160, 0),
    "creek": (0, 0, 255),
}


def _font(size):
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
    """Draws the reviewer's crop of one queue item and saves it as a PNG.

    Left: the scan with the traced line (purple), the prior (thin red) and the
    item's stretches (yellow, ends circled); right: the ink classes
    (black/grey magenta, red fill orange, brown green, blue/teal blue) with
    the traced line; above them, the text lines (wrapped, at most 8).

    Returns:
        False when no sheet holds the point, else True.
    """
    sh = sheet_of(sheets, lon, lat)
    if sh is None:
        return False
    c, r, _ = sh.pixel(lon, lat)
    m = 30
    big, bc0, br0 = sh.read(
        c - half_px - m, r - half_px - m, c + half_px + m, r + half_px + m
    )
    masks = inklib.classes(big)
    a, c0, r0 = sh.read(c - half_px, r - half_px, c + half_px, r + half_px)
    oy, ox = int(r0 - br0), int(c0 - bc0)
    rgb = np.transpose(a, (1, 2, 0)).astype("uint8")
    ov = np.full_like(rgb, 255)
    for k, col in COL.items():
        ov[masks[k][oy : oy + rgb.shape[0], ox : ox + rgb.shape[1]]] = col
    width_px, height_px = rgb.shape[1] * scale, rgb.shape[0] * scale
    left_im = Image.fromarray(rgb).resize((width_px, height_px), Image.NEAREST)
    right_im = Image.fromarray(ov).resize((width_px, height_px), Image.NEAREST)

    def pts(co):
        cc, rr, _, _ = sh.pixels([p[0] for p in co], [p[1] for p in co])
        return [
            ((u - c0) * scale, (v - r0) * scale)
            for u, v in zip(cc, rr, strict=True)
        ]

    for im, items in (
        (left_im, ((prior, (230, 0, 0), 1), (traced, (120, 0, 230), 2))),
        (right_im, ((traced, (120, 0, 230), 2),)),
    ):
        d = ImageDraw.Draw(im)
        for co, col, wd in items:
            if co is not None and len(co) > 1:
                d.line(pts(co), fill=col, width=wd)
    d = ImageDraw.Draw(left_im)
    for st in stretches:
        if len(st) > 1:
            p = pts(st)
            d.line(p, fill=(255, 210, 0), width=4)
            for u, v in (p[0], p[-1]):
                d.ellipse([u - 4, v - 4, u + 4, v + 4], outline=(0, 0, 0))
    for im in (left_im, right_im):
        ImageDraw.Draw(im).ellipse(
            [
                width_px / 2 - 6,
                height_px / 2 - 6,
                width_px / 2 + 6,
                height_px / 2 + 6,
            ],
            outline=(0, 0, 0),
            width=1,
        )
    f = _font(14)
    lh = 18
    lines = [
        x
        for t in lines
        for x in wrap(t, max(40, int((2 * width_px + 10) / 7.4)))
    ][:8]
    o = Image.new(
        "RGB", (2 * width_px + 10, height_px + lh * len(lines) + 6), "white"
    )
    dd = ImageDraw.Draw(o)
    for k, t in enumerate(lines):
        dd.text((4, 3 + k * lh), t, fill=(0, 0, 0), font=f)
    o.paste(left_im, (0, lh * len(lines) + 6))
    o.paste(right_im, (width_px + 10, lh * len(lines) + 6))
    o.save(out)
    return True


def wrap(t, n=150):
    """Splits text at spaces into lines of at most n characters."""
    out = []
    while len(t) > n:
        k = t.rfind(" ", 0, n)
        k = k if k > 0 else n
        out.append(t[:k])
        t = t[k:].lstrip()
    return [*out, t]


# ---------------------------------------------------------------- driver
def main():
    """Checks the traced lines; writes per_step.csv, queue.geojson and crops."""
    ap = argparse.ArgumentParser(
        description=(
            "acceptance check: is each traced line on the RIGHT feature "
            "(identity), not just near ink"
        )
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
    with open(a.traced) as fh:
        traced_fc = json.load(fh)
    for f in traced_fc["features"]:
        feats[str(f["properties"].get(a.id_field))] = (
            f["properties"].get(a.kind_field),
            f["geometry"]["coordinates"],
        )
    prior = {}
    if a.prior:
        with open(a.prior) as fh:
            prior_fc = json.load(fh)
        for f in prior_fc["features"]:
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
        grid = StepGrid(sheets, [coords], kind)
        others = [(o_, feats[o_][1]) for o_ in feats if o_ != sid]
        pts = grid.xy(coords)
        line = cl.resample(pts, 1.0)
        lo, la = grid.lonlat(line)
        chk = check_line(grid, coords, others, sheet_index(sheets, lo, la))
        st = chk["stats"]
        ok = kind in VALIDATED
        # ---- queue entries: every event, and every unmeasured stretch >= 15 m;
        # clustered along the line
        ent = [
            dict(
                r0=e["r0"],
                r1=e["r1"],
                type=("sheet_edge_jog" if e.get("sheet_edge") else e["type"]),
                size=e["size_m"],
                why=e["why"],
                context=e.get("context", ""),
            )
            for e in chk["events"]
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
            for x0, x1 in chk["unmeasured_runs"]
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
                                strict=True,
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
                                strict=True,
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
                verified_m=int(chk["verified"].sum()),
                flagged_m=int(chk["flagged"].sum()),
                unmeasured_m=int(chk["unmeasured"].sum()),
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
            f"{sid:>4} {kind:7s} {'' if ok else '(unvalidated) '}"
            "current check: within 2 m of measured "
            f"{r_['current_within2_of_measured_pct']}%, "
            f"strict {r_['current_strict_pct']}% | "
            f"VERIFIED {r_['verified_pct']}% FLAGGED {r_['flagged_pct']}% "
            f"UNMEASURED {r_['unmeasured_pct']}% | "
            f"wrong line {r_['wrong_line_m']} m | "
            f"events {sum(c_.values())} -> {r_['queue_items']} queue items | "
            f"{r_['seconds']} s",
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
                dx = (np.array([p[0] for p in stx]) - it["lon"]) * 95600
                dy = (np.array([p[1] for p in stx]) - it["lat"]) * 110574
                ext = max(ext, float(np.hypot(dx, dy).max()))
        half = int(min(110, max(50, ext / 2.03 + 25)))
        where = (
            f"size {it['size']}  "
            f"metres {it['s_from_m']}-{it['s_to_m']} along the line"
            if it["s_from_m"] is not None
            else "fixed item: a place the checks are known to be blind to"
        )
        head = [
            (
                f"item {it['item']}  step {it['step']} ({it['kind']}"
                f"{', UNVALIDATED detector' if not it['validated'] else ''})  "
                f"{it['types']}  at {it['lon']}, {it['lat']}  {where}"
            )
        ]
        head += [it["why"]]
        head += [
            (
                "left: scan, traced line purple, prior thin red, the item's "
                "stretch yellow; right: ink classes (grey/black magenta, "
                "red orange, brown green, blue blue). Is the purple line on "
                "the CENTRE of the RIGHT feature here?"
            )
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
    with open(os.path.join(a.out_dir, "queue.geojson"), "w") as fh:
        json.dump(fc, fh, indent=1)
    nv = [r for r in rows if r["validated"]]
    print(
        f"\n{len(rows)} steps, {len(items)} queue items "
        f"({sum(1 for i in items if i['validated'])} validated, "
        f"{sum(1 for i in items if not i['validated'])} unvalidated), "
        f"{round(time.time() - t0)} s. Outputs in {a.out_dir}"
    )
    if nv:
        tot = sum(r["core_m"] for r in nv)
        n_passing = sum(
            1 for r in nv if r["verified_pct"] >= 95 and r["queue_items"] == 0
        )
        print(
            "validated kinds: VERIFIED "
            f"{100 * sum(r['verified_m'] for r in nv) / tot:.1f}% of {tot} m; "
            "steps passing (VERIFIED >= 95% and no open items): "
            f"{n_passing} of {len(nv)}"
        )


if __name__ == "__main__":
    main()
