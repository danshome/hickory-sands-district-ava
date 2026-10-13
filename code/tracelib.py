#!/usr/bin/env python3
"""Digitization toolkit: cross-quad sampling, ray probing, least-cost ink following.

Scan-ink classes (HTMC 1:24k scans, these 13 sheets):
  black  cultural ink: unimproved roads, buildings, PLSS lines, lettering
  red    highway fill (US and state highways)
  blue   hydrography
  index  heavy brown contour ink, including contour ink under green woodland tint
  inter  light brown contour ink
  green  woodland tint (treated as background when probing)
  bg     paper
Calibrated 2026-10-11 on long_mountain transects.
"""
import heapq, json, math, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from quadlib import Quad, registry

M_LAT = 110574.0
def m_lon(lat): return 111320.0 * math.cos(math.radians(lat))

_CELLS = {}
def cells():
    if not _CELLS:
        for slug in registry():
            q = Quad.get(slug)
            lon_c, lat_c = q.lonlat_of_pix(q.im.width / 2, q.im.height / 2)
            lon0 = math.floor(lon_c / 0.125) * 0.125
            lat0 = math.floor(lat_c / 0.125) * 0.125
            _CELLS[slug] = (lon0, lon0 + 0.125, lat0, lat0 + 0.125)
    return _CELLS

_ARR = {}
def arr(slug):
    if slug not in _ARR:
        _ARR[slug] = np.asarray(Quad.get(slug).im, dtype=np.int16)
    return _ARR[slug]

def quad_of(lon, lat):
    for slug, (a, b, c, d) in cells().items():
        if a <= lon < b and c <= lat < d:
            return slug
    return None

def sample(lon, lat):
    slug = quad_of(lon, lat)
    if slug is None:
        return None, None
    q = Quad.get(slug)
    c, r = q.pix(lon, lat)
    A = arr(slug)
    if not (0 <= int(r) < A.shape[0] and 0 <= int(c) < A.shape[1]):
        return None, slug
    return A[int(r), int(c)], slug

def classify(px):
    if px is None:
        return "nodata"
    r, g, b = int(px[0]), int(px[1]), int(px[2])
    mx = max(r, g, b)
    if mx < 110 and r - b <= 40:
        return "black"
    if b > r + 20 and g > r + 20 and b >= g - 60:
        return "blue"
    if g > r + 12 and g > b + 25 and g > 185:
        return "green"
    if r > 170 and g < 135 and b < 135 and r - b > 60:
        return "red"
    if r - b > 32 and b < 190 and r >= g - 45:
        return "index" if (r < 190 and mx < 205) else "inter"
    if mx < 110:
        return "black"
    if mx < 160 and mx - min(r, g, b) < 45:
        return "gray"
    return "bg"

def walk(lon, lat, bearing_deg, d):
    la = lat + math.cos(math.radians(bearing_deg)) * d / M_LAT
    lo = lon + math.sin(math.radians(bearing_deg)) * d / m_lon(la)
    return lo, la

def ray_runs(lon, lat, bearing_deg, max_m=2500, step_m=1.2, ignore=("green",)):
    """Walk a bearing; group consecutive non-background samples into ink runs.
    Returns [(cls, lon_mid, lat_mid, dist_mid_m, width_m)]."""
    runs = []  # [cls, d0, d1]
    d = step_m
    while d <= max_m:
        lo, la = walk(lon, lat, bearing_deg, d)
        cls = classify(sample(lo, la)[0])
        if cls not in ("bg", "nodata") and cls not in ignore:
            if runs and runs[-1][0] == cls and d - runs[-1][2] <= 5 * step_m:
                runs[-1][2] = d
            else:
                runs.append([cls, d, d])
        d += step_m
    out = []
    for cls, d0, d1 in runs:
        lo, la = walk(lon, lat, bearing_deg, (d0 + d1) / 2)
        out.append((cls, lo, la, (d0 + d1) / 2, d1 - d0))
    return out

def transect_report(lon, lat, bearing_deg, max_m=800, ignore=("green",)):
    for cls, lo, la, d, w in ray_runs(lon, lat, bearing_deg, max_m, ignore=ignore):
        px, slug = sample(lo, la)
        print(f"  {d:7.1f} m  w={w:5.1f}  {cls:6s} rgb={tuple(int(v) for v in px) if px is not None else None} ({slug})")

def nth_hit(lon, lat, bearing_deg, classes=("index",), n=1, max_m=2500, min_w=1.5):
    """lonlat and distance of the nth run of the given classes along the bearing."""
    k = 0
    for cls, lo, la, d, w in ray_runs(lon, lat, bearing_deg, max_m):
        if cls in classes and w >= min_w:
            k += 1
            if k == n:
                return lo, la, d
    return None

def _masks(A):
    r = A[..., 0].astype(np.int16); g = A[..., 1].astype(np.int16); b = A[..., 2].astype(np.int16)
    mx = np.maximum(np.maximum(r, g), b)
    rb = r - b
    red = (r > 170) & (g < 135) & (b < 135) & (rb > 60)
    brown = (rb > 32) & (b < 190) & (r >= g - 45) & ~red
    index = brown & (r < 190) & (mx < 205)
    return {
        "blue": (b > r + 20) & (g > r + 20) & (b >= g - 60),
        "green": (g > r + 12) & (g > b + 25) & (g > 185),
        "red": red,
        "brown": brown,
        "index": index,
        "inter": brown & ~index,
        "black": (mx < 110) & (rb <= 40),
        "gray": (mx < 160) & ((mx - np.minimum(np.minimum(r, g), b)) < 45),
    }

def _dijkstra(cost, sa, sb):
    Hh, Ww = cost.shape
    dist = np.full((Hh, Ww), np.inf, np.float32)
    prev = np.full((Hh, Ww, 2), -1, np.int32)
    dist[sa] = 0.0
    pq = [(0.0, sa)]
    moves = [(-1,-1,1.414),(-1,0,1.0),(-1,1,1.414),(0,-1,1.0),(0,1,1.0),(1,-1,1.414),(1,0,1.0),(1,1,1.414)]
    while pq:
        dcur, (ri, ci) = heapq.heappop(pq)
        if (ri, ci) == sb:
            break
        if dcur > dist[ri, ci]:
            continue
        for dr, dc, w in moves:
            r2, c2 = ri + dr, ci + dc
            if 0 <= r2 < Hh and 0 <= c2 < Ww:
                nd = dcur + w * 0.5 * (cost[ri, ci] + cost[r2, c2])
                if nd < dist[r2, c2]:
                    dist[r2, c2] = nd
                    prev[r2, c2] = (ri, ci)
                    heapq.heappush(pq, (nd, (r2, c2)))
    path = [sb]
    while tuple(path[-1]) != sa and prev[path[-1][0], path[-1][1]][0] >= 0:
        p = prev[path[-1][0], path[-1][1]]
        path.append((int(p[0]), int(p[1])))
    path.reverse()
    return path

def snap_to_ink(lon, lat, target_classes=("index",), radius_px=28, slug=None):
    """Nearest pixel of the target classes within radius; returns (lon, lat) or the input."""
    slug = slug or quad_of(lon, lat)
    q = Quad.get(slug)
    c, r = q.pix(lon, lat)
    c, r = int(c), int(r)
    A0 = arr(slug)
    r0, r1 = max(0, r - radius_px), min(A0.shape[0], r + radius_px + 1)
    c0, c1 = max(0, c - radius_px), min(A0.shape[1], c + radius_px + 1)
    m = _masks(A0[r0:r1, c0:c1])
    tgt = np.zeros((r1 - r0, c1 - c0), bool)
    for t in target_classes:
        tgt |= m[t]
    ys, xs = np.nonzero(tgt)
    if len(ys) == 0:
        return lon, lat
    k = int(np.argmin((ys - (r - r0)) ** 2 + (xs - (c - c0)) ** 2))
    return q.lonlat_of_pix(c0 + xs[k] + 0.5, r0 + ys[k] + 0.5)

def follow(start, end, target_classes=("black",), vias=(), scale=2, margin_px=140,
           gap_cost=35.0, slug=None, eps_px=1.8, refine=True, snap_vias=True, snap_radius_px=28):
    """Least-cost path along target ink from start to end, leg by leg through vias.
    All points must sit on ONE quad (pass slug explicitly or it is inferred from start).
    With refine=True the coarse path is re-solved at full resolution inside a narrow
    corridor, lightly simplified, and Chaikin-smoothed so contour lines print smooth.
    Returns a lonlat list including the endpoints."""
    slug = slug or quad_of(*start)
    q = Quad.get(slug)
    A0 = arr(slug)
    if snap_vias:
        vias = [snap_to_ink(lo, la, target_classes, radius_px=snap_radius_px, slug=slug) for lo, la in vias]
    pts = [start] + list(vias) + [end]
    pix = [q.pix(lo, la) for lo, la in pts]
    full_path = []
    for (ca, ra), (cb, rb_) in zip(pix[:-1], pix[1:]):
        c0 = max(0, int(min(ca, cb)) - margin_px); c1 = min(q.im.width, int(max(ca, cb)) + margin_px)
        r0 = max(0, int(min(ra, rb_)) - margin_px); r1 = min(q.im.height, int(max(ra, rb_)) + margin_px)
        A = A0[r0:r1, c0:c1]
        m = _masks(A)
        tgt = np.zeros(A.shape[:2], bool)
        for t in target_classes:
            tgt |= m[t]
        s = scale
        H = (tgt.shape[0] // s) * s; W = (tgt.shape[1] // s) * s
        T = tgt[:H, :W].reshape(H // s, s, W // s, s).any(axis=(1, 3))
        cost = np.where(T, 1.0, gap_cost).astype(np.float32)
        sa = (min(max(0, int((ra - r0) / s)), T.shape[0] - 1), min(max(0, int((ca - c0) / s)), T.shape[1] - 1))
        sb = (min(max(0, int((rb_ - r0) / s)), T.shape[0] - 1), min(max(0, int((cb - c0) / s)), T.shape[1] - 1))
        path = _dijkstra(cost, sa, sb)
        if refine and s > 1:
            # second pass: full-resolution Dijkstra inside a corridor around the coarse path
            corr = np.zeros(tgt.shape, bool)
            rad = 5 * s
            for rr, cc in path:
                rr2, cc2 = rr * s + s // 2, cc * s + s // 2
                corr[max(0, rr2 - rad):rr2 + rad + 1, max(0, cc2 - rad):cc2 + rad + 1] = True
            costf = np.where(tgt & corr, 1.0, np.where(corr, gap_cost, np.inf)).astype(np.float32)
            fa = (min(max(0, int(ra - r0)), tgt.shape[0] - 1), min(max(0, int(ca - c0)), tgt.shape[1] - 1))
            fb = (min(max(0, int(rb_ - r0)), tgt.shape[0] - 1), min(max(0, int(cb - c0)), tgt.shape[1] - 1))
            corr[fa] = corr[fb] = True
            costf[fa] = min(costf[fa], gap_cost); costf[fb] = min(costf[fb], gap_cost)
            path = _dijkstra(costf, fa, fb)
            leg = [(c0 + cc + 0.5, r0 + rr + 0.5) for rr, cc in path]
        else:
            leg = [(c0 + cc * s + s / 2, r0 + rr * s + s / 2) for rr, cc in path]
        full_path.extend(leg if not full_path else leg[1:])
    eff = eps_px * (1.0 if refine else scale)
    simp = rdp(full_path, eps=eff)
    simp = chaikin(simp, 2)
    return [q.lonlat_of_pix(c, r) for c, r in simp]

def chaikin(pts, iters=2):
    """Corner-cutting smoothing; keeps endpoints fixed."""
    P = [tuple(p) for p in pts]
    for _ in range(iters):
        if len(P) < 3:
            return P
        out = [P[0]]
        for a, b in zip(P[:-1], P[1:]):
            out.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            out.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        out.append(P[-1])
        P = out
    return P

def snap(lon, lat, classes=("index",), r_m=70):
    """Move a point to the nearest pixel of the given ink classes within r_m."""
    slug = quad_of(lon, lat)
    q = Quad.get(slug)
    c, r = q.pix(lon, lat)
    rr = max(4, int(r_m / 2.2))
    r0, c0 = max(0, int(r) - rr), max(0, int(c) - rr)
    A = arr(slug)[r0:int(r) + rr, c0:int(c) + rr]
    m = _masks(A)
    tgt = np.zeros(A.shape[:2], bool)
    for t in classes:
        tgt |= m[t]
    ys, xs = np.nonzero(tgt)
    if len(ys) == 0:
        return lon, lat
    d2 = (ys + r0 - r) ** 2 + (xs + c0 - c) ** 2
    k = int(np.argmin(d2))
    return q.lonlat_of_pix(c0 + xs[k] + 0.5, r0 + ys[k] + 0.5)

def rdp(pts, eps):
    if len(pts) < 3:
        return pts
    P = np.asarray(pts, float)
    keep = [0, len(pts) - 1]
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        dx, dy = P[j] - P[i]
        L = math.hypot(dx, dy) or 1.0
        d = np.abs(dx * (P[i + 1:j, 1] - P[i, 1]) - dy * (P[i + 1:j, 0] - P[i, 0])) / L
        k = int(np.argmax(d))
        if d[k] > eps:
            mpt = i + 1 + k
            keep.append(mpt)
            stack.extend([(i, mpt), (mpt, j)])
    keep.sort()
    return [pts[k] for k in keep]

def ink_vias(seed, target_classes=("blue",), corridor_m=150, spacing_m=100, slug=None):
    """Auto-waypoints: walk the seed line, and at each spacing step take the centroid of
    the nearest cluster of target-class pixels within the corridor. Returns via list."""
    slug = slug or quad_of(*seed[0])
    q = Quad.get(slug)
    A = arr(slug)
    out, acc = [], 0.0
    samples = [seed[0]]
    for a, b in zip(seed[:-1], seed[1:]):
        acc += math.hypot((b[0]-a[0])*m_lon(a[1]), (b[1]-a[1])*M_LAT)
        if acc >= spacing_m:
            samples.append(b); acc = 0.0
    rad_px = int(corridor_m / 2.4) + 1
    for lon, lat in samples:
        c, r = q.pix(lon, lat)
        c, r = int(c), int(r)
        r0, r1 = max(0, r-rad_px), min(A.shape[0], r+rad_px+1)
        c0, c1 = max(0, c-rad_px), min(A.shape[1], c+rad_px+1)
        m = _masks(A[r0:r1, c0:c1])
        tgt = np.zeros((r1-r0, c1-c0), bool)
        for t in target_classes:
            tgt |= m[t]
        ys, xs = np.nonzero(tgt)
        if len(ys) == 0:
            continue
        d2 = (ys-(r-r0))**2 + (xs-(c-c0))**2
        k = int(np.argmin(d2))
        sel = (ys-ys[k])**2 + (xs-xs[k])**2 < (18)**2
        cy, cx = ys[sel].mean(), xs[sel].mean()
        out.append(q.lonlat_of_pix(c0+cx+0.5, r0+cy+0.5))
    return out

def despur(pts, close_m=4.0, min_m=18.0, max_m=420.0, thin_m=2.5):
    """Remove out-and-back spurs: loops that nearly close, are 18-420 m around,
    and enclose almost no area (thin). Real contour hairpins enclose area and survive."""
    P = [tuple(p) for p in pts]
    i = 0
    while i < len(P) - 3:
        acc, j, cut_j = 0.0, i + 1, None
        while j < len(P):
            acc += math.hypot((P[j][0]-P[j-1][0])*m_lon(P[j][1]), (P[j][1]-P[j-1][1])*M_LAT)
            if acc > max_m:
                break
            if acc >= min_m:
                d = math.hypot((P[j][0]-P[i][0])*m_lon(P[i][1]), (P[j][1]-P[i][1])*M_LAT)
                if d < close_m:
                    mx = m_lon(P[i][1])
                    area = 0.0
                    for k in range(i, j):
                        x1, y1 = (P[k][0]-P[i][0])*mx, (P[k][1]-P[i][1])*M_LAT
                        x2, y2 = (P[k+1][0]-P[i][0])*mx, (P[k+1][1]-P[i][1])*M_LAT
                        area += x1*y2 - x2*y1
                    if abs(area) / 2.0 < thin_m * acc:
                        cut_j = j
            j += 1
        if cut_j is not None:
            P = P[:i+1] + P[cut_j+1:]
        else:
            i += 1
    return P

def cut_between(line, A, B):
    """Slice a traced line between the nearest points to A and B; endpoints become exactly A and B."""
    def ix(p):
        return min(range(len(line)), key=lambda i: (line[i][0]-p[0])**2 + (line[i][1]-p[1])**2)
    ia, ib = ix(A), ix(B)
    seg = line[ia:ib+1] if ia <= ib else line[ib:ia+1][::-1]
    return [tuple(A)] + [tuple(p) for p in seg[1:-1]] + [tuple(B)]

def seg_m(line):
    t = 0.0
    for (a, b), (c, d) in zip(line[:-1], line[1:]):
        t += math.hypot((c - a) * m_lon((b + d) / 2), (d - b) * M_LAT)
    return t

if __name__ == "__main__":
    print("A: north across the 1800-contour zone near step 3, from (-99.39011, 30.8098):")
    transect_report(-99.39011, 30.8098, 0, 500)
    print("B: north across US 377 at the begin point, from (-99.40967, 30.7638):")
    transect_report(-99.40967, 30.7638, 0, 250)
    print("C: north across Big Bluff Creek, from (-99.41056, 30.7810):")
    transect_report(-99.41056, 30.7810, 0, 500)
    print("D: east across the Big Bluff Creek drainage at the 1705 latitude, from (-99.4140, 30.78257):")
    transect_report(-99.4140, 30.78257, 90, 900)
    print("woodland sample at (-99.3900, 30.8125):", classify(sample(-99.3900, 30.8125)[0]),
          tuple(int(v) for v in sample(-99.3900, 30.8125)[0]))
