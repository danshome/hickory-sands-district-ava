"""patchlib: tools for an agent to hand-fix one flagged stretch of a traced line on a scanned USGS quad.

A PATCH replaces one stretch [s0, s1] (metres along the step's frozen trace) with a new line whose ends lie ON the
trace (so apply_patches.py can splice it) and whose interior follows the centre of the printed ink. Never within
PIN_TIE (12 m) of a step end. Geometry comes only from the sheet's ink (or a straight bridge across a label / gap),
never from another boundary layer.

    import sys; sys.path.insert(0, "<skill>/scripts"); import patchlib as P
    T = P.Trace()                                   # frozen traced lines (TRACED), by step
    s = T.nearest_s(59, lon, lat)                   # where a flagged spot is along the step
    g = P.Grid(T, 59, s - 80, s + 80)               # 1 m ink grid around that stretch (classes of ink.py)
    line = P.follow(g, s - 40, s + 40)              # least-cost path on the RAW ink centre between two trace points
    line = P.follow(g, s - 40, s + 40, ink=g.m["brown"] | g.ink, via=[g.ll(76, 140)])  # ... through a point you read off the render
    line = P.straight(T, 59, s - 25, s + 25)        # or: a straight bridge (label crossings, dot gaps)
    line = P.road_centre(g, s - 40, s + 40)         # or: road centre between the casings, on the trace's own course
    P.render(g, line, "/tmp/x.png", s - 60, s + 60) # scan + ink classes + old trace (purple) + patch (orange): LOOK AT IT
    P.save(OUT, 59, "59-002", line, "follow raw ink", "label loop through 1800")   # append to the agent's GeoJSON
    P.validate(OUT)                                 # apply_patches.py dry run: ends on the trace, not near pins, no overlap

Coordinates: lon/lat NAD83 (EPSG:4269) everywhere; metres in a local frame inside Grid.
"""

import json, math, os, subprocess, sys, datetime
import numpy as np
from scipy import ndimage, sparse
from scipy.sparse import csgraph

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)  # the repository root
SKILL_TRACE = os.path.join(ROOT, "src", "tracing")
sys.path.insert(0, SKILL_TRACE)
import centerline as cl  # noqa: E402
import ink as inklib  # noqa: E402,F401  (P.inklib, for agents writing patches)
from quadsheets import open_sheets  # noqa: E402

FILING = os.environ.get("HSD_WORK") or os.path.join(
    ROOT, "target", "work"
)  # build work dir
TRACED = os.path.join(FILING, "ink-centerline-steps.geojson")
PRIOR = os.path.join(FILING, "ink-trace-input.geojson")
QUADS = ROOT + "/resources/quads/geotiff/*.tif.zip"
APPLY = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "apply_patches.py"
)
PIN_TIE = 12.0
_SHEETS = None


def sheets():
    global _SHEETS
    if _SHEETS is None:
        _SHEETS = open_sheets([QUADS])
    return _SHEETS


def _frame(lat0):
    return 111320.0 * math.cos(math.radians(lat0)), 110574.0


class Trace:
    """the frozen traced lines (and their priors), by step number"""

    def __init__(self, traced=TRACED, prior=PRIOR):
        self.F = {
            int(f["properties"]["id"]): f
            for f in json.load(open(traced))["features"]
        }
        self.P = (
            {
                int(f["properties"]["id"]): f
                for f in json.load(open(prior))["features"]
            }
            if prior and os.path.exists(prior)
            else {}
        )

    def kind(self, step):
        return self.F[step]["properties"]["kind"]

    def coords(self, step):
        return [tuple(c[:2]) for c in self.F[step]["geometry"]["coordinates"]]

    def length(self, step):
        c = np.array(self.coords(step))
        mx, my = _frame(c[:, 1].mean())
        return float(
            np.sum(np.hypot(np.diff(c[:, 0]) * mx, np.diff(c[:, 1]) * my))
        )

    def _arc(self, step):
        c = np.array(self.coords(step))
        mx, my = _frame(c[:, 1].mean())
        d = np.hypot(np.diff(c[:, 0]) * mx, np.diff(c[:, 1]) * my)
        return c, np.concatenate([[0], np.cumsum(d)]), mx, my

    def point_at(self, step, s):
        """(lon, lat) on the trace at s metres along it (clamped)"""
        c, a, mx, my = self._arc(step)
        s = min(max(s, 0.0), a[-1])
        i = min(int(np.searchsorted(a, s, side="right")) - 1, len(a) - 2)
        t = (s - a[i]) / max(a[i + 1] - a[i], 1e-9)
        return (
            float(c[i, 0] + t * (c[i + 1, 0] - c[i, 0])),
            float(c[i, 1] + t * (c[i + 1, 1] - c[i, 1])),
        )

    def nearest_s(self, step, lon, lat):
        """metres along the trace of the point nearest (lon, lat)"""
        c, a, mx, my = self._arc(step)
        P = np.column_stack([(c[:, 0] - lon) * mx, (c[:, 1] - lat) * my])
        best = (1e18, 0.0)
        for i in range(len(P) - 1):
            ab = P[i + 1] - P[i]
            L2 = float(ab @ ab)
            t = 0 if L2 == 0 else max(0, min(1, -float(P[i] @ ab) / L2))
            q = P[i] + t * ab
            d = float(q @ q)
            if d < best[0]:
                best = (d, a[i] + t * (a[i + 1] - a[i]))
        return float(best[1])

    def stretch(self, step, s0, s1, step_m=1.0):
        """the trace between s0 and s1 as [(lon, lat)], every step_m"""
        return [
            self.point_at(step, s) for s in np.arange(s0, s1 + 1e-9, step_m)
        ]


class Grid:
    """1 m ink-class grid (ink.classes, read from the sheet holding each cell) around a stretch of a step"""

    def __init__(
        self,
        T,
        step,
        s0,
        s1,
        pad=45.0,
        extra=(
            "contour",
            "brown",
            "road",
            "creek",
            "black",
            "red",
            "text",
            "blue",
            "dotlike",
        ),
    ):
        self.T, self.step, self.kind = T, step, T.kind(step)
        L = T.length(step)
        s0, s1 = max(0.0, s0), min(L, s1)
        pts = np.array(T.stretch(step, s0, s1, 2.0))
        self.lat0 = float(pts[:, 1].mean())
        self.lon0 = float(pts[:, 0].mean())
        self.mx, self.my = _frame(self.lat0)
        X = (pts[:, 0] - self.lon0) * self.mx
        Y = (pts[:, 1] - self.lat0) * self.my
        self.xmin, self.ymin = X.min() - pad, Y.min() - pad
        self.nx, self.ny = (
            int(X.max() + pad - self.xmin) + 1,
            int(Y.max() + pad - self.ymin) + 1,
        )
        iy, ix = np.mgrid[0 : self.ny, 0 : self.nx]
        iy, ix = iy.ravel(), ix.ravel()
        lons = self.lon0 + (self.xmin + ix + 0.5) / self.mx
        lats = self.lat0 + (self.ymin + iy + 0.5) / self.my
        k = (
            "contour"
            if self.kind == "contour"
            else ("road" if self.kind == "road" else "creek")
        )
        ink_c, have, ext = cl.sample_ink(
            sheets(), k, lons, lats, extra=tuple(e for e in extra if e != k)
        )
        self.m = {k: ink_c.reshape(self.ny, self.nx)}
        for e, v in ext.items():
            self.m[e] = v.reshape(self.ny, self.nx)
        self.have = have.reshape(self.ny, self.nx)
        self.ink = self.m[k]

    def xy(self, lon, lat):
        return (
            (lon - self.lon0) * self.mx - self.xmin,
            (lat - self.lat0) * self.my - self.ymin,
        )

    def ll(self, x, y):
        return (
            self.lon0 + (x + self.xmin) / self.mx,
            self.lat0 + (y + self.ymin) / self.my,
        )

    def cell(self, lon, lat):
        x, y = self.xy(lon, lat)
        return int(min(max(y, 0), self.ny - 1)), int(
            min(max(x, 0), self.nx - 1)
        )


def _smooth_ll(g, pts, sigma=1.5):
    XY = np.array([g.xy(*p) for p in pts])
    a, b = XY[0].copy(), XY[-1].copy()
    if len(XY) > 4 and sigma:
        XY = cl.resample(cl.smooth(XY, sigma), 1.0)
        XY[0], XY[-1] = a, b
    keep = cl.rdp(XY, 0.25)
    return [g.ll(*XY[i]) for i in keep]


def cost_field(
    g, ink=None, off_cost=40.0, near_cost=4.0, avoid=None, prefer=None
):
    """cost per m: 1 + 4*(ridge - edt)^2 on ink (the centre of the printed line is cheapest), near_cost within 1.5 m
    of ink, off_cost elsewhere; avoid / prefer: masks made dearer / cheaper"""
    m = g.ink if ink is None else ink
    edt = ndimage.distance_transform_edt(m)
    ridge = ndimage.maximum_filter(edt, size=5)
    d_out = ndimage.distance_transform_edt(~m)
    cost = np.where(
        m,
        1.0 + np.minimum(4.0 * (ridge - edt) ** 2, 6.0),
        np.where(d_out <= 1.5, near_cost, off_cost),
    )
    if avoid is not None:
        cost = np.where(avoid, cost + 60.0, cost)
    if prefer is not None:
        cost = np.where(prefer, np.minimum(cost, 1.0), cost)
    return cost


def _path(g, cost, a, b):
    ny, nx = cost.shape
    N = ny * nx
    idx = np.arange(N).reshape(ny, nx)
    A, B, W = [], [], []
    for dr, dc, ln in (
        (0, 1, 1.0),
        (1, 0, 1.0),
        (1, 1, math.sqrt(2)),
        (1, -1, math.sqrt(2)),
    ):
        r0, r1 = 0, ny - dr
        c0, c1 = max(0, -dc), nx - max(0, dc)
        u = idx[r0:r1, c0:c1].ravel()
        v = idx[r0 + dr : r1 + dr, c0 + dc : c1 + dc].ravel()
        w = (
            ln
            * 0.5
            * (
                cost[r0:r1, c0:c1].ravel()
                + cost[r0 + dr : r1 + dr, c0 + dc : c1 + dc].ravel()
            )
        )
        A.append(u)
        B.append(v)
        W.append(w)
    G = sparse.csr_matrix(
        (np.concatenate(W), (np.concatenate(A), np.concatenate(B))),
        shape=(N, N),
    )
    sa = idx[g.cell(*a)]
    sb = idx[g.cell(*b)]
    dist, pred = csgraph.dijkstra(
        G, directed=False, indices=sa, return_predecessors=True
    )
    if not np.isfinite(dist[sb]):
        raise RuntimeError("no path")
    path = [sb]
    while path[-1] != sa:
        path.append(pred[path[-1]])
    rr, cc = np.divmod(np.array(path[::-1]), nx)
    return [g.ll(c + 0.5, r + 0.5) for r, c in zip(rr[1:-1], cc[1:-1])]


def follow(
    g,
    s0,
    s1,
    ink=None,
    via=(),
    off_cost=40.0,
    near_cost=4.0,
    avoid=None,
    prefer=None,
    sigma=1.5,
):
    """least-cost path from the trace point at s0 to the trace point at s1 on the RAW ink (no gap fill, no growing,
    so it does not cut a V tip or a bend), passing through the `via` points in order. ink: the mask to follow
    (default the step's own class; at a V tip printed partly brown/black pass e.g. g.m["brown"] | g.ink).
    via: [(lon, lat)] -- points YOU read off the render (g.ll(x, y) converts the panel's metres) that the line must
    pass, e.g. the apex of a V tip or the middle of a label. Smoothing keeps the ends exactly on the trace."""
    cost = cost_field(g, ink, off_cost, near_cost, avoid, prefer)
    a = g.T.point_at(g.step, s0)
    b = g.T.point_at(g.step, s1)
    stops = [a] + list(via) + [b]
    pts = [a]
    for u, v in zip(stops, stops[1:]):
        pts += _path(g, cost, u, v) + [v]
    return _smooth_ll(g, pts, sigma)


def polyline(T, step, s0, s1, via):
    """a hand-placed line: the trace point at s0, then the `via` points [(lon, lat)] you read off the render, then the
    trace point at s1 (for a stretch where no ink class is usable, e.g. a road edge you can see but ink.py misses)"""
    return [T.point_at(step, s0)] + list(via) + [T.point_at(step, s1)]


def straight(T, step, s0, s1):
    """a straight bridge between the trace points at s0 and s1 (label crossings, dot gaps, missing dashes)"""
    return [T.point_at(step, s0), T.point_at(step, s1)]


def road_centre(g, s0, s1, width=None, sigma=6.0):
    """the road's centre between its casings on the stretch, read on cross-sections every metre of the OLD trace
    (centerline.edge_offsets: both casings -> midpoint; one casing -> it + half the road width), smoothed, the ends
    tapered to the trace points at s0 and s1. width: the road's casing separation (default: the step's road_width_m)."""
    width = width or g.T.F[g.step]["properties"].get("road_width_m")
    C = np.array([g.xy(*p) for p in g.T.stretch(g.step, s0, s1, 1.0)])
    faint = g.m.get("road_faint")
    m, w = cl.edge_offsets(C, g.ink, 0.0, 0.0, width=width, faint=faint)
    sh = cl.robust_offsets(m, sigma, med_size=21)
    k = np.arange(len(sh), dtype=float)
    taper = np.minimum(1.0, np.minimum(k, len(sh) - 1 - k) / 10.0)
    C2 = C + (sh * taper)[:, None] * cl.normals(C)
    pts = [g.ll(*p) for p in C2]
    pts[0] = g.T.point_at(g.step, s0)
    pts[-1] = g.T.point_at(g.step, s1)
    return _smooth_ll(g, pts, 0)


def sample_rgb(lons, lats):
    n = len(lons)
    out = np.full((n, 3), 255, np.uint8)
    done = np.zeros(n, bool)
    for sh in sheets():
        todo = np.flatnonzero(~done)
        if not len(todo):
            break
        c, r, inside, _ = sh.pixels(lons[todo], lats[todo])
        if not inside.any():
            continue
        sel = np.flatnonzero(inside)
        ci = np.floor(c[sel]).astype(int)
        ri = np.floor(r[sel]).astype(int)
        a, c0, r0 = sh.read(ci.min(), ri.min(), ci.max() + 1, ri.max() + 1)
        ok = (
            (ri - r0 >= 0)
            & (ri - r0 < a.shape[1])
            & (ci - c0 >= 0)
            & (ci - c0 < a.shape[2])
        )
        out[todo[sel[ok]]] = a[:, ri[ok] - r0, ci[ok] - c0].T
        done[todo[sel]] = True
    return out


def render(g, patch, png, s0=None, s1=None, title="", res=0.5):
    """two panels: the scan (0.5 m cells) and the ink classes, with the old trace (purple), the prior (red, thin) and
    the patch (orange, with its vertices). Read it with the Read tool before saving the patch."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pts = [g.xy(*p) for p in patch]
    if s0 is not None:
        pts += [g.xy(*g.T.point_at(g.step, s)) for s in (s0, s1)]
    P = np.array(pts)
    x0, x1 = P[:, 0].min() - 25, P[:, 0].max() + 25
    y0, y1 = P[:, 1].min() - 25, P[:, 1].max() + 25
    xs = np.arange(x0, x1, res)
    ys = np.arange(y0, y1, res)
    XX, YY = np.meshgrid(xs, ys)
    lons = g.lon0 + (XX.ravel() + g.xmin) / g.mx
    lats = g.lat0 + (YY.ravel() + g.ymin) / g.my
    rgb = sample_rgb(lons, lats).reshape(len(ys), len(xs), 3)
    fig, ax = plt.subplots(
        1, 2, figsize=(16, 8 * (y1 - y0) / max(x1 - x0, 1) + 1)
    )
    ext = (x0, x1, y0, y1)
    ax[0].imshow(rgb, origin="lower", extent=ext, interpolation="nearest")
    cls = np.full(g.ink.shape + (3,), 1.0)
    for key, col in (
        ("brown", (0.75, 0.5, 0.2)),
        ("black", (0.2, 0.2, 0.2)),
        ("blue", (0.1, 0.4, 0.9)),
        ("red", (0.9, 0.2, 0.2)),
        ("text", (0.9, 0.0, 0.9)),
    ):
        if key in g.m:
            cls[g.m[key]] = col
    cls[g.ink] = np.array(cls[g.ink]) * 0.6 + np.array([0.0, 0.6, 0.0]) * 0.4
    ax[1].imshow(
        cls, origin="lower", extent=(0, g.nx, 0, g.ny), interpolation="nearest"
    )
    old = np.array(
        [g.xy(*p) for p in g.T.stretch(g.step, 0, g.T.length(g.step), 1.0)]
    )
    pri = (
        np.array(
            [g.xy(*p[:2]) for p in g.T.P[g.step]["geometry"]["coordinates"]]
        )
        if g.step in g.T.P
        else None
    )
    for a in ax:
        a.plot(old[:, 0], old[:, 1], color="#8000ff", lw=1.2, label="old trace")
        if pri is not None:
            a.plot(pri[:, 0], pri[:, 1], color="red", lw=0.6, label="prior")
        Q = np.array([g.xy(*p) for p in patch])
        a.plot(
            Q[:, 0],
            Q[:, 1],
            color="#ff8c00",
            lw=1.6,
            marker="o",
            ms=2.5,
            label="patch",
        )
        a.set_xlim(x0, x1)
        a.set_ylim(y0, y1)
        a.set_aspect("equal")
    ax[0].legend(loc="upper right", fontsize=7)
    ax[0].set_title(
        f"step {g.step} ({g.kind}) {title} -- scan; grid 1 m, ticks in m",
        fontsize=9,
    )
    ax[1].set_title(
        "ink classes: brown contour, black road/text, blue creek, red fill, magenta lettering; green = this step's class",
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(png, dpi=110)
    plt.close(fig)
    return png


def save(
    path,
    step,
    spot,
    line,
    method,
    reason,
    who="Claude agent (usgs-quad-fix), for Dan McLaughlin",
):
    """append one patch (LineString, EPSG:4269) to the agent's GeoJSON; refuses an end within PIN_TIE of a pin unless it
    sits ON the pin (T.point_at(step, 0) or T.point_at(step, T.length(step))): a patch run to the pin"""
    T = Trace()
    L = T.length(step)
    for p in (line[0], line[-1]):
        s = T.nearest_s(step, *p)
        if 0.3 < s < PIN_TIE + 0.5 or L - PIN_TIE - 0.5 < s < L - 0.3:
            raise ValueError(
                f"patch end at {s:.1f} m of {L:.0f} m is within {PIN_TIE} m of a pin (end it ON the pin, or more than {PIN_TIE} m away)"
            )
    fc = (
        json.load(open(path))
        if os.path.exists(path)
        else {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:EPSG::4269"},
            },
            "features": [],
        }
    )
    fc["features"] = [
        f for f in fc["features"] if f["properties"].get("spot") != spot
    ]  # re-saving a spot replaces it
    fc["features"].append(
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[round(x, 9), round(y, 9)] for x, y in line],
            },
            "properties": {
                "step": int(step),
                "spot": spot,
                "method": "agent on the ink: " + method,
                "who": who,
                "when": datetime.datetime.now().isoformat(timespec="seconds"),
                "reason": reason,
            },
        }
    )
    json.dump(fc, open(path, "w"), indent=1)
    return len(fc["features"])


def validate(path):
    """dry run of apply_patches.py on this file alone (ends on the trace within 0.5 m, out of the pin zones, no overlap)"""
    out = os.path.splitext(path)[0] + "-validate-out.geojson"
    r = subprocess.run(
        [
            sys.executable,
            "-E",
            "-s",
            "-B",
            APPLY,
            "--traced",
            TRACED,
            "--patches",
            path,
            "--out",
            out,
        ],
        capture_output=True,
        text=True,
    )
    print(r.stdout[-3000:], r.stderr[-2000:])
    return r.returncode == 0
