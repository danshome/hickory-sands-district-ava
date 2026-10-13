"""Build the San Pasqual Valley exhibit from TTB's AVAs_Production feature (NAD83): GeoJSON attachment + PNG map."""
import json, math, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPoly

SRC, OUT_GEOJSON, OUT_PNG = sys.argv[1], sys.argv[2], sys.argv[3]
URL = "https://services7.arcgis.com/ykuAbKu9MbV93nAe/ArcGIS/rest/services/AVAs_Production/FeatureServer/0"
R = 6371008.8

def d(a, b):
    la = math.radians((a[1] + b[1]) / 2)
    return R * math.hypot(math.radians(b[0] - a[0]) * math.cos(la), math.radians(b[1] - a[1]))

def acres(ring):
    s = 0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        s += math.radians(x2 - x1) * (2 + math.sin(math.radians(y1)) + math.sin(math.radians(y2)))
    return abs(s) * 6371007.18 ** 2 / 2 / 4046.86

src = json.load(open(SRC))["features"][0]
ring0 = src["geometry"]["coordinates"][0]
n = len(ring0) - 1
# Rotate the ring by half so an out-and-back that wraps around vertex 0 becomes contiguous.
h = n // 2
ring = ring0[h:n] + ring0[:h] + [ring0[h]]

# Shared (out-and-back) vertices: vertex k coincides (<0.5 m) with a vertex far away along the ring.
cum = [0.0]
for k in range(n): cum.append(cum[-1] + d(ring[k], ring[k + 1]))
T = cum[-1]
pairs = []
for i in range(n):
    for j in range(i + 2, n):
        along = cum[j] - cum[i]
        if min(along, T - along) > 100 and d(ring[i], ring[j]) < 3.0:
            pairs.append((i, j))
if not pairs: sys.exit("no out-and-back found")
# The spur: indices on the "outbound" side; it wraps around vertex 0.
outb = sorted(set(min(p) for p in pairs)); back = sorted(set(max(p) for p in pairs))
tip_i, tip_j = max(outb), min(back)          # where the spur meets the hillock loop
# Extend the spur while the outbound and return paths keep coinciding (segments with no interior vertices).
while tip_i + 1 < tip_j - 1 and d(ring[tip_i + 1], ring[tip_j - 1]) < 3.0:
    tip_i += 1; tip_j -= 1
spur = ring[min(outb):tip_i + 1]
spur_len = sum(d(spur[k], spur[k + 1]) for k in range(len(spur) - 1))
loop = ring[tip_i:tip_j + 1] + [ring[tip_i]]
loop_ac = acres(loop)
if loop_ac > acres(ring0) / 2: sys.exit(f"loop selection looks wrong ({loop_ac:.0f} ac)")
junction = ring[min(outb)]

props = dict(src["properties"])  # TTB attributes, verbatim
common = {"source": URL + " (TTB AVAs_Production), Name = 'San Pasqual Valley'", "retrieved": "2026-10-12", "crs": "EPSG:4269 (NAD83)"}
fc = {
    "type": "FeatureCollection",
    "name": "ttb-published-san-pasqual-valley-EPSG4269",
    "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4269"}},
    "source": common["source"], "retrieved": common["retrieved"],
    "note": "Feature 1 is TTB's San Pasqual Valley feature exactly as served (geometry and attributes unaltered). Features 2 and 3 were added by the commenter to mark the shared out-and-back line and the excluded hillock, using TTB's own vertices.",
    "features": [
        {"type": "Feature", "properties": props, "geometry": src["geometry"]},
        {"type": "Feature", "properties": {**common, "added_by": "commenter", "part": "Shared boundary line (traversed out and back)",
            "length_m": round(spur_len), "cfr_text": "follows the Escondido Corporate Boundary line to the 500-foot contour line on the hillock and circumnavigates said hillock back to the Escondido Corporate Boundary line (27 CFR 9.25(c)(2))",
            "derived": "vertices of the TTB polygon that coincide within 3 m with vertices traversed in the opposite direction"},
         "geometry": {"type": "LineString", "coordinates": spur}},
        {"type": "Feature", "properties": {**common, "added_by": "commenter", "part": "Hillock left outside the AVA", "acres": round(loop_ac, 1),
            "derived": "loop of the TTB polygon beyond the shared line; all test points inside it fall outside the AVA polygon"},
         "geometry": {"type": "Polygon", "coordinates": [loop]}},
    ],
}
json.dump(fc, open(OUT_GEOJSON, "w"), ensure_ascii=False)
print(f"spur {spur_len:.0f} m over {len(spur)} vertices; hillock {loop_ac:.1f} acres; junction {junction}")

# ---- exhibit map ----
xs = [p[0] for p in loop + spur]; ys = [p[1] for p in loop + spur]
cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
k = math.cos(math.radians(cy))
half = max((max(xs) - min(xs)) * k, max(ys) - min(ys)) * 0.9
fig, ax = plt.subplots(figsize=(8, 8), dpi=200)
ax.set_facecolor("#F4F4F2")
ax.add_patch(MPoly(ring, closed=True, facecolor="#7B5EA7", alpha=0.45, edgecolor="none"))
ax.plot([p[0] for p in ring], [p[1] for p in ring], color="#1B2428", lw=1.6, solid_joinstyle="round")
ax.add_patch(MPoly(loop, closed=True, facecolor="#FFFFFF", alpha=0.85, edgecolor="#1B2428", lw=1.6, hatch="//"))
ax.plot([p[0] for p in spur], [p[1] for p in spur], color="#D55E00", lw=5, solid_capstyle="round", zorder=5)
ax.set_xlim(cx - half / k * 1.0, cx + half / k * 1.0); ax.set_ylim(cy - half, cy + half)
ax.set_aspect(1 / k)
ax.set_xticks([]); ax.set_yticks([])
mx, my = sum(p[0] for p in loop) / len(loop), sum(p[1] for p in loop) / len(loop)
ax.annotate(f"Hillock left outside the AVA\n(about {loop_ac:.0f} acres)", (mx, my), ha="center", va="center", fontsize=11, weight="bold", color="#1B2428",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#1B2428", lw=0.8))
sx, sy = spur[len(spur) // 2]
ax.annotate(f"Same line used out and back\n(about {spur_len:.0f} m)", (sx, sy), xytext=(sx + half / k * 0.35, sy - half * 0.35), fontsize=11, weight="bold", color="#8A3A00",
            arrowprops=dict(arrowstyle="->", color="#8A3A00", lw=1.5), bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#8A3A00", lw=0.8))
ax.text(0.02, 0.98, "San Pasqual Valley AVA (27 CFR 9.25), as published by TTB", transform=ax.transAxes, va="top", fontsize=12, weight="bold",
        bbox=dict(fc="white", ec="none", alpha=0.9))
ax.text(0.02, 0.02, "Shaded: inside the AVA.  Source: TTB AVAs_Production feature service, retrieved October 12, 2026.\nGeometry unaltered (NAD83); shared line and hillock identified from the published vertices.",
        transform=ax.transAxes, va="bottom", fontsize=8, color="#1B2428", bbox=dict(fc="white", ec="none", alpha=0.9))
# scale bar 200 m
sb = 200 / (111320 * k)
x0, y0 = cx + half / k * 0.55, cy - half * 0.80
ax.add_patch(plt.Rectangle((x0 - sb * 0.1, y0 - half * 0.03), sb * 1.2, half * 0.09, fc="white", ec="none", alpha=0.9, zorder=6))
ax.plot([x0, x0 + sb], [y0, y0], color="#1B2428", lw=4, solid_capstyle="butt", zorder=7)
ax.plot([x0, x0], [y0 - half * 0.012, y0 + half * 0.012], color="#1B2428", lw=2, zorder=7)
ax.plot([x0 + sb, x0 + sb], [y0 - half * 0.012, y0 + half * 0.012], color="#1B2428", lw=2, zorder=7)
ax.text(x0 + sb / 2, y0 + half * 0.025, "200 m", ha="center", fontsize=10, zorder=7)
fig.tight_layout(); fig.savefig(OUT_PNG); print("wrote", OUT_PNG)
