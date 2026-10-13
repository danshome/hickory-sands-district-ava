#!/usr/bin/env python3
"""Shared quad toolkit: registry, polyconic forward/inverse (NAD27/Clarke 1866),
crop and map rendering with graticule, for from-scratch digitization."""
import glob, json, math, os, re, sys
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

Image.MAX_IMAGE_PIXELS = None
QUAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "quads")

# One boundary style for every quad and every zoom: white-cased magenta dash.
BOUND_COLOR = "#c2187e"
BOUND_DASH = (0, (6, 3))
BOUND_LW = 2.4

def registry():
    reg = {}
    for p in glob.glob(os.path.join(QUAD_DIR, "*.tif")):
        base = os.path.basename(p)
        m = re.match(r"TX_(.+?)_\d+_(\d{4})_24000_geo\.tif", base)
        if m:
            slug = m.group(1).lower().replace(" ", "_")
            reg[slug] = p
        else:
            m2 = re.match(r"(grit|turtle_creek)_(\d{4})\.tif", base)
            if m2:
                reg[m2.group(1)] = p
    return reg

class Quad:
    _cache = {}

    @classmethod
    def get(cls, slug):
        if slug not in cls._cache:
            cls._cache[slug] = cls(registry()[slug])
        return cls._cache[slug]

    def __init__(self, path):
        self.path = path
        self.im = Image.open(path)
        t = self.im.tag_v2
        self.sx, self.sy = t[33550][0], t[33550][1]
        tp = t[33922]
        self.i0, self.j0, self.X0, self.Y0 = tp[0], tp[1], tp[3], tp[4]
        doubles = t.get(34736, ())
        gk = t[34735]
        keys = {}
        for n in range(gk[3]):
            kid, loc, cnt, val = gk[4 + 4 * n: 8 + 4 * n]
            keys[kid] = doubles[val] if loc == 34736 else val
        self.lat0 = math.radians(keys.get(3081, 0.0))
        self.lon0 = math.radians(keys.get(3080, 0.0))
        self.FE = keys.get(3082, 0.0); self.FN = keys.get(3083, 0.0)
        invf = keys.get(2059, 294.978698214)
        self.a = keys.get(2057, 6378206.4)
        f = 1.0 / invf
        self.e2 = 2 * f - f * f
        e2 = self.e2
        self.c0 = 1 - e2/4 - 3*e2**2/64 - 5*e2**3/256
        self.c2 = 3*e2/8 + 3*e2**2/32 + 45*e2**3/1024
        self.c4 = 15*e2**2/256 + 45*e2**3/1024
        self.c6 = 35*e2**3/3072
        self.M0 = self.M(self.lat0)

    def M(self, phi):
        return self.a * (self.c0*phi - self.c2*math.sin(2*phi)
                         + self.c4*math.sin(4*phi) - self.c6*math.sin(6*phi))

    def Mp(self, phi):  # dM/dphi
        return self.a * (self.c0 - 2*self.c2*math.cos(2*phi)
                         + 4*self.c4*math.cos(4*phi) - 6*self.c6*math.cos(6*phi))

    def fwd(self, lon, lat):
        phi, lam = math.radians(lat), math.radians(lon)
        if abs(phi) < 1e-12:
            return self.FE + self.a*(lam - self.lon0), self.FN - self.M0
        N = self.a / math.sqrt(1 - self.e2*math.sin(phi)**2)
        E = (lam - self.lon0)*math.sin(phi)
        cot = 1.0/math.tan(phi)
        return (self.FE + N*cot*math.sin(E),
                self.FN + self.M(phi) - self.M0 + N*cot*(1 - math.cos(E)))

    def inv(self, x, y):
        x -= self.FE; y -= self.FN
        a, e2 = self.a, self.e2
        A = (self.M0 + y)/a
        if abs(A) < 1e-12 and abs(x) < 1e-9:
            return math.degrees(self.lon0), 0.0
        B = x*x/(a*a) + A*A
        phi = A
        for _ in range(30):
            s, c = math.sin(phi), math.cos(phi)
            C = math.sqrt(1 - e2*s*s) * (s/c)
            Ma = self.M(phi)/a
            Mp = self.Mp(phi)/a
            s2 = math.sin(2*phi)
            num = A*(C*Ma + 1) - Ma - 0.5*C*(Ma*Ma + B)
            den = (e2*s2*(Ma*Ma + B - 2*A*Ma)/(4*C)
                   + (A - Ma)*(C*Mp - 2/s2) - Mp)
            d = num/den
            phi -= d
            if abs(d) < 1e-13:
                break
        s = math.sin(phi)
        C = math.sqrt(1 - e2*s*s) * (s/math.cos(phi))
        lam = math.asin(max(-1, min(1, x*C/a)))/s + self.lon0
        return math.degrees(lam), math.degrees(phi)

    def pix(self, lon, lat):
        x, y = self.fwd(lon, lat)
        return (x - self.X0)/self.sx + self.i0, (self.Y0 - y)/self.sy + self.j0

    def lonlat_of_pix(self, col, row):
        x = self.X0 + (col - self.i0)*self.sx
        y = self.Y0 - (row - self.j0)*self.sy
        return self.inv(x, y)

    def crop_bbox(self, lon0, lon1, lat0, lat1):
        cs = [self.pix(lo, la) for lo in (lon0, lon1) for la in (lat0, lat1)]
        c0 = max(0, int(min(c for c, r in cs))); c1 = min(self.im.width, int(max(c for c, r in cs))+1)
        r0 = max(0, int(min(r for c, r in cs))); r1 = min(self.im.height, int(max(r for c, r in cs))+1)
        img = self.im.crop((c0, r0, c1, r1))
        ext = (self.X0 + (c0-self.i0)*self.sx, self.X0 + (c1-self.i0)*self.sx,
               self.Y0 - (r1-self.j0)*self.sy, self.Y0 - (r0-self.j0)*self.sy)
        return img, ext, (c0, r0, c1, r1)

def render_map(slug, bbox, out, points=(), lines=(), grat=0.005, title="", upscale=1.0):
    """bbox = (lon0, lon1, lat0, lat1); points = [(lon, lat, label)]; lines = [[(lon,lat),...]]"""
    q = Quad.get(slug)
    img, ext, _ = q.crop_bbox(*bbox)
    w = 12.0
    fig, ax = plt.subplots(figsize=(w, w*img.height/img.width), dpi=int(170*upscale))
    fig.set_facecolor("#fcfcfb")
    ax.imshow(img, extent=ext, interpolation="bilinear")
    # graticule in lon/lat drawn into projected space
    lon_a = math.floor(bbox[0]/grat)*grat
    while lon_a <= bbox[1]:
        pts = [q.fwd(lon_a, bbox[2] + k*(bbox[3]-bbox[2])/20) for k in range(21)]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#555555", lw=0.5, alpha=0.6)
        ax.annotate(f"{lon_a:.3f}", q.fwd(lon_a, bbox[2]), fontsize=6, color="#333333",
                    ha="center", va="top", xytext=(0, -2), textcoords="offset points")
        lon_a = round(lon_a + grat, 6)
    lat_a = math.floor(bbox[2]/grat)*grat
    while lat_a <= bbox[3]:
        pts = [q.fwd(bbox[0] + k*(bbox[1]-bbox[0])/20, lat_a) for k in range(21)]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#555555", lw=0.5, alpha=0.6)
        ax.annotate(f"{lat_a:.3f}", q.fwd(bbox[0], lat_a), fontsize=6, color="#333333",
                    ha="left", va="center", xytext=(2, 0), textcoords="offset points")
        lat_a = round(lat_a + grat, 6)
    for ln in lines:
        if isinstance(ln, dict):
            pts_, col, ls, lw = ln["pts"], ln.get("color", BOUND_COLOR), ln.get("ls", BOUND_DASH), ln.get("lw", BOUND_LW)
            halo = ln.get("halo", True)
        else:
            pts_, col, ls, lw, halo = ln, BOUND_COLOR, BOUND_DASH, BOUND_LW, True
        xy = np.array([q.fwd(lo, la) for lo, la in pts_])
        if halo:
            ax.plot(xy[:, 0], xy[:, 1], color="#ffffff", lw=lw * 2.4 + 1.0, ls="-", alpha=0.9,
                    solid_capstyle="round", zorder=5)
        ax.plot(xy[:, 0], xy[:, 1], color=col, lw=lw, ls=ls, zorder=6)
    for lon, lat, lab in points:
        x, y = q.fwd(lon, lat)
        ax.plot([x], [y], marker="o", ms=9, mfc="none", mec="#ffffff", mew=3.0, zorder=7)
        ax.plot([x], [y], marker="o", ms=9, mfc="none", mec="#c2187e", mew=1.6, zorder=8)
        if lab:
            ax.annotate(lab, (x, y), fontsize=7.5, color="#8a1060", xytext=(6, 6), textcoords="offset points",
                        zorder=9, bbox=dict(fc="#ffffff", ec="none", alpha=0.78, pad=1.2))
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
    ax.set_aspect(1); ax.axis("off")
    # scale bar in projected meters
    wm = ext[1] - ext[0]
    bar = 5000
    for cand in (100, 200, 500, 1000, 2000, 5000):
        if cand >= wm / 6:
            bar = cand
            break
    bx = ext[0] + 0.04 * wm; by = ext[2] + 0.045 * (ext[3] - ext[2])
    ax.plot([bx, bx + bar], [by, by], color="#0b0b0b", lw=2.5, solid_capstyle="butt", zorder=10)
    ax.annotate(f"{bar} m", (bx + bar / 2, by), xytext=(0, 3), textcoords="offset points",
                ha="center", fontsize=7, color="#0b0b0b", zorder=10,
                bbox=dict(fc="#fcfcfb", ec="none", alpha=0.7, pad=0.8))
    if title:
        ax.set_title(title, fontsize=10, loc="left", color="#0b0b0b")
    fig.tight_layout()
    fig.savefig(out, facecolor="#fcfcfb")
    plt.close(fig)
    return out

if __name__ == "__main__":
    reg = registry()
    print(f"{len(reg)} quads registered:")
    worst = 0.0
    for slug, path in sorted(reg.items()):
        q = Quad.get(slug)
        # roundtrip test at 5 interior points
        cx, cy = q.im.width/2, q.im.height/2
        errs = []
        for dc, dr in ((0,0), (-2000,-2000), (2000,-2000), (-2000,2000), (2000,2000)):
            lon, lat = q.lonlat_of_pix(cx+dc, cy+dr)
            c2, r2 = q.pix(lon, lat)
            errs.append(math.hypot(c2-(cx+dc), r2-(cy+dr)))
        e = max(errs)
        worst = max(worst, e)
        print(f"  {slug:16s} lon0={math.degrees(q.lon0):9.4f} roundtrip max {e:.2e} px  center=({q.lonlat_of_pix(cx,cy)[0]:.4f},{q.lonlat_of_pix(cx,cy)[1]:.4f})")
    print(f"worst roundtrip error: {worst:.2e} px")
