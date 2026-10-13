"""600x400 ArcGIS Online thumbnails for each public layer, drawn from the attachment GeoJSON."""
import json, math, sys, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPoly

SRC, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
def feats(name): return json.load(open(f"{SRC}/{name}"))["features"]
def rings(g):
    t, c = g["type"], g["coordinates"]
    if t == "Polygon": return [c[0]]
    if t == "MultiPolygon": return [p[0] for p in c]
    return []
def lines(g):
    t, c = g["type"], g["coordinates"]
    if t == "LineString": return [c]
    if t == "MultiLineString": return c
    if t in ("Polygon", "MultiPolygon"): return rings(g)
    return []

ava = rings(feats("boundary-per-proposed-text-area-EPSG4269.geojson")[0]["geometry"])
grit = [r for f in feats("grit-section-EPSG4269.geojson") if f["properties"]["acres"] > 1000 for r in rings(f["geometry"])]
BLUE, ORANGE, INK, VERM, WINE, SKY = "#0072B2", "#E69F00", "#1B2428", "#D55E00", "#882255", "#56B4E9"

def canvas(bbox, title, sub):
    lon0, lon1, lat0, lat1 = bbox
    k = math.cos(math.radians((lat0 + lat1) / 2))
    fig = plt.figure(figsize=(6, 4), dpi=100)
    ax = fig.add_axes([0, 0, 1, 0.80]); ax.set_facecolor("#F6F5F1")
    w = (lon1 - lon0) * k; h = lat1 - lat0; aspect = 6 / (4 * 0.80)
    if w / h < aspect:
        pad = (h * aspect - w) / 2 / k; lon0 -= pad; lon1 += pad
    else:
        pad = (w / aspect - h) / 2; lat0 -= pad; lat1 += pad
    ax.set_xlim(lon0, lon1); ax.set_ylim(lat0, lat1); ax.set_aspect(1 / k); ax.axis("off")
    fig.patch.set_facecolor("white")
    fig.text(0.03, 0.92, title, fontsize=15, weight="bold", color=INK, va="center")
    fig.text(0.03, 0.845, sub, fontsize=9.5, color="#4A565C", va="center")
    return fig, ax

def bb(rs, pad=0.08):
    xs = [p[0] for r in rs for p in r]; ys = [p[1] for r in rs for p in r]
    dx, dy = (max(xs) - min(xs)) * pad, (max(ys) - min(ys)) * pad
    return (min(xs) - dx, max(xs) + dx, min(ys) - dy, max(ys) + dy)

def outline(ax, rs, **kw):
    for r in rs: ax.plot([p[0] for p in r], [p[1] for p in r], **kw)

AVA_BB = bb(ava, 0.05)
GRIT_BB = (-99.378, -99.282, 30.742, 30.804)
jobs = []

def save(fig, name):
    p = f"{OUT}/{name}.png"; fig.savefig(p, dpi=100); plt.close(fig); jobs.append(p)

# 1 proposed line
fig, ax = canvas(AVA_BB, "Boundary per Proposed Text", "96 steps drawn on USGS 1:24,000 maps, Notice No. 243")
for f in feats("boundary-per-proposed-text-line-EPSG4269.geojson"):
    for l in lines(f["geometry"]): ax.plot([p[0] for p in l], [p[1] for p in l], color=BLUE, lw=1.6)
save(fig, "boundary-per-proposed-text-line")
# 2 proposed area
fig, ax = canvas(AVA_BB, "Boundary per Proposed Text (Area)", "About 198.1 square miles, Notice No. 243")
for r in ava: ax.add_patch(MPoly(r, closed=True, fc=BLUE, alpha=0.18, ec=BLUE, lw=1.6))
save(fig, "boundary-per-proposed-text-area")
# 3 proposed points
fig, ax = canvas(AVA_BB, "Boundary Points per Proposed Text", "97 points on the printed marks of the designated maps")
outline(ax, ava, color="#9AA7AC", lw=0.8)
for f in feats("boundary-per-proposed-text-points-EPSG4269.geojson"):
    x, y = f["geometry"]["coordinates"][:2]; ax.plot(x, y, "o", ms=4.5, mfc="white", mec=BLUE, mew=1.4)
save(fig, "boundary-per-proposed-text-points")
# 4 petition line
fig, ax = canvas(AVA_BB, "Boundary with Petition Western Routing", "Proposed text with the petition's route near Grit restored")
for f in feats("boundary-with-petition-western-routing-line-EPSG4269.geojson"):
    for l in lines(f["geometry"]):
        ax.plot([p[0] for p in l], [p[1] for p in l], color=INK, lw=2.6); ax.plot([p[0] for p in l], [p[1] for p in l], color=ORANGE, lw=1.4, ls=(0, (4, 2)))
save(fig, "boundary-with-petition-western-routing-line")
# 5 petition area
pet = [r for f in feats("boundary-with-petition-western-routing-area-EPSG4269.geojson") for r in rings(f["geometry"])]
fig, ax = canvas(AVA_BB, "Petition Western Routing (Area)", "About 193.8 square miles")
for r in pet: ax.add_patch(MPoly(r, closed=True, fc=ORANGE, alpha=0.22, ec="#8A5A00", lw=1.4))
save(fig, "boundary-with-petition-western-routing-area")
# 6 petition points
fig, ax = canvas(AVA_BB, "Boundary Points, Petition Routing", "102 points with petition and proposed-text numbers")
outline(ax, pet, color="#9AA7AC", lw=0.8)
for f in feats("boundary-with-petition-western-routing-points-EPSG4269.geojson"):
    x, y = f["geometry"]["coordinates"][:2]; ax.plot(x, y, "o", ms=4, mfc=ORANGE, mec=INK, mew=0.8)
save(fig, "boundary-with-petition-western-routing-points")
# 7 grit section
fig, ax = canvas(GRIT_BB, "Grit Section", "4.32 sq mi added by the proposed text, plus small lane pieces")
for f in feats("grit-section-EPSG4269.geojson"):
    c = VERM if f["properties"]["direction"].startswith("In proposed") else "#F0E442"
    for r in rings(f["geometry"]): ax.add_patch(MPoly(r, closed=True, fc=c, alpha=0.55, ec=INK, lw=1.0))
save(fig, "grit-section")
# 8 departures
fig, ax = canvas(AVA_BB, "Published Polygon Departures", "69 places, about 790 acres, where TTB's map differs from the text")
outline(ax, ava, color=BLUE, lw=1.0)
for f in feats("published-polygon-departures-EPSG4269.geojson"):
    c = SKY if "includes land" in f["properties"]["direction"] else WINE
    for r in rings(f["geometry"]):
        cx = sum(q[0] for q in r) / len(r); cy = sum(q[1] for q in r) / len(r)
        ax.plot(cx, cy, "o", ms=3 + 1.2 * math.sqrt(f["properties"]["acres"]), mfc=c, mec=INK, mew=0.6, alpha=0.9)
save(fig, "published-polygon-departures")
# 9 parks
fig, ax = canvas(GRIT_BB, "Granite Rock-Crawling Parks", "Approximate, inside the Grit section; not surveyed")
for r in grit: ax.add_patch(MPoly(r, closed=True, fc=VERM, alpha=0.15, ec="#7A2E00", lw=1.0))
for f in feats("granite-rock-crawling-parks-EPSG4269.geojson"):
    for r in rings(f["geometry"]):
        ax.add_patch(MPoly(r, closed=True, fc="#8A9196", alpha=0.45, ec=INK, lw=1.4, ls="--"))
        cx = sum(p[0] for p in r) / len(r); cy = sum(p[1] for p in r) / len(r)
        ax.text(cx, cy, f["properties"]["name"], ha="center", va="center", fontsize=9, weight="bold", color=INK, bbox=dict(fc="white", ec="none", alpha=0.8))
save(fig, "granite-rock-crawling-parks")
# 10 san pasqual
sp = feats("ttb-published-san-pasqual-valley-EPSG4269.geojson")
hill = [r for f in sp if f["properties"].get("part", "").startswith("Hillock") for r in rings(f["geometry"])]
spur = [l for f in sp if f["geometry"]["type"] == "LineString" for l in lines(f["geometry"])]
main = rings(sp[0]["geometry"])
fig, ax = canvas(bb(hill + spur, 0.9), "San Pasqual Valley AVA (27 CFR 9.25)", "TTB polygon: one line used out and back around an excluded hillock")
for r in main: ax.add_patch(MPoly(r, closed=True, fc="#7B5EA7", alpha=0.4, ec=INK, lw=1.2))
for r in hill: ax.add_patch(MPoly(r, closed=True, fc="white", ec=INK, lw=1.2, hatch="//"))
for l in spur: ax.plot([p[0] for p in l], [p[1] for p in l], color=VERM, lw=4)
save(fig, "ttb-published-san-pasqual-valley")
print("\n".join(jobs))
