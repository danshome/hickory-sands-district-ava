"""Exhibit A: rock-crawling trails in the Grit section, from OpenStreetMap (ODbL), with the Grit section, park outlines and both routes."""
import json, math, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPoly

OSM, CLEAN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
R = 6371008.8

def d(a, b):
    la = math.radians((a[1] + b[1]) / 2)
    return R * math.hypot(math.radians(b[0] - a[0]) * math.cos(la), math.radians(b[1] - a[1]))

def inside(pt, ring):
    x, y = pt; c = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1): c = not c
    return c

def load(name):
    return json.load(open(f"{CLEAN}/{name}"))["features"]

grit = [f for f in load("grit-section-EPSG4269.geojson") if f["properties"]["direction"].startswith("In proposed") and f["properties"]["acres"] > 1000][0]
grit_ring = grit["geometry"]["coordinates"][0]
parks = [(f["properties"]["name"], f["geometry"]["coordinates"][0]) for f in load("granite-rock-crawling-parks-EPSG4269.geojson")]
prop_lines = [f["geometry"]["coordinates"] for f in load("boundary-per-proposed-text-line-EPSG4269.geojson")]
pet = load("boundary-with-petition-western-routing-line-EPSG4269.geojson")[0]["geometry"]
pet_lines = pet["coordinates"] if pet["type"] == "MultiLineString" else [pet["coordinates"]]

osm = json.load(open(OSM))
stamp = osm.get("osm3s", {}).get("timestamp_osm_base", "")[:10]
ways = [e for e in osm["elements"] if e.get("geometry")]
trail_types = {"track", "path"}
def coords(e): return [(p["lon"], p["lat"]) for p in e["geometry"]]
def is_trail(e):
    t = e["tags"]
    return t.get("highway") in trail_types or (t.get("highway") == "unclassified" and t.get("surface") in ("dirt", "unpaved", "ground", "rock"))

# Length of trail inside the Grit section and inside the parks (segment midpoints)
L_grit = 0.0; L_parks = 0.0; names = set()
for e in ways:
    if not is_trail(e): continue
    c = coords(e)
    for a, b in zip(c, c[1:]):
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2); seg = d(a, b)
        if inside(m, grit_ring):
            L_grit += seg
            if e["tags"].get("name"): names.add(e["tags"]["name"])
        if any(inside(m, r) for _, r in parks): L_parks += seg
print(f"OSM base {stamp}; trail inside Grit section {L_grit/1609.34:.1f} mi; inside parks {L_parks/1609.34:.1f} mi; named trails in Grit section: {len(names)}")

lon0, lon1, lat0, lat1 = -99.378, -99.282, 30.742, 30.804
k = math.cos(math.radians((lat0 + lat1) / 2))
fig, ax = plt.subplots(figsize=(8, 8 * (lat1 - lat0) / ((lon1 - lon0) * k)), dpi=200)
ax.set_facecolor("#F7F6F2")
ax.add_patch(MPoly(grit_ring, closed=True, facecolor="#D55E00", alpha=0.18, edgecolor="#7A2E00", lw=1.2, zorder=1))
for e in ways:
    t = e["tags"]; c = coords(e); xs = [p[0] for p in c]; ys = [p[1] for p in c]
    if t.get("waterway"):
        ax.plot(xs, ys, color="#6FA8C9", lw=0.8, zorder=2)
    elif t.get("highway") in ("primary", "secondary", "trunk"):
        ax.plot(xs, ys, color="#8A8F93", lw=3.0, zorder=3)
    elif is_trail(e):
        ax.plot(xs, ys, color="#3B2A1A", lw=0.9, zorder=4)
    else:
        ax.plot(xs, ys, color="#B5B9BC", lw=0.9, zorder=2)
for name, r in parks:
    ax.plot([p[0] for p in r], [p[1] for p in r], color="#1B2428", lw=1.4, ls=(0, (5, 3)), zorder=5)
for ln in prop_lines:
    ax.plot([p[0] for p in ln], [p[1] for p in ln], color="#0072B2", lw=2.4, zorder=6)
for ln in pet_lines:
    ax.plot([p[0] for p in ln], [p[1] for p in ln], color="#1B2428", lw=3.2, zorder=7)
    ax.plot([p[0] for p in ln], [p[1] for p in ln], color="#E69F00", lw=1.8, ls=(0, (4, 3)), zorder=8)
for name, r in parks:
    cx = sum(p[0] for p in r) / len(r); cy = sum(p[1] for p in r) / len(r)
    ax.text(cx, cy, name, ha="center", va="center", fontsize=9, weight="bold", color="#1B2428",
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#1B2428", lw=0.6, alpha=0.9), zorder=9)
ax.set_xlim(lon0, lon1); ax.set_ylim(lat0, lat1); ax.set_aspect(1 / k)
ax.set_xticks([]); ax.set_yticks([])
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
handles = [
    Line2D([], [], color="#3B2A1A", lw=1.2, label="Dirt tracks and trails (OpenStreetMap)"),
    Patch(facecolor="#D55E00", alpha=0.18, edgecolor="#7A2E00", label="Grit section (4.32 sq mi)"),
    Line2D([], [], color="#1B2428", lw=1.4, ls=(0, (5, 3)), label="Rock-crawling parks, approximate"),
    Line2D([], [], color="#0072B2", lw=2.4, label="Proposed text"),
    Line2D([], [], color="#E69F00", lw=1.8, ls=(0, (4, 3)), label="Petition routing"),
]
leg = ax.legend(handles=handles, loc="lower left", fontsize=7.5, framealpha=1.0, borderpad=0.8)
leg.set_zorder(20)
ax.text(0.99, 0.01, f"Trails and roads: © OpenStreetMap contributors, ODbL (data as of {stamp}).\nBoundaries: drawn by the commenter on the USGS 1:24,000 maps.",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=6.5, color="#1B2428", bbox=dict(fc="white", ec="#C9D2CF", alpha=1.0, pad=4), zorder=20)
sb = 1000 / (111320 * k); x0 = lon1 - (lon1 - lon0) * 0.20; y0 = lat0 + (lat1 - lat0) * 0.10
ax.plot([x0, x0 + sb], [y0, y0], color="#1B2428", lw=3, zorder=10); ax.text(x0 + sb / 2, y0 + (lat1 - lat0) * 0.012, "1 km", ha="center", fontsize=8, zorder=10)
fig.tight_layout(); fig.savefig(OUT); print("wrote", OUT)
