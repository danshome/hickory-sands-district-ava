"""Exhibit D: the Grit section and both routings over an excerpt of the Bureau of Economic Geology's 1:24,000
geologic map of the Grit quadrangle (Hunt, Johnson, and Helper, 2021, Open-File Map 252).

The BEG map is a purchased publication and is not in this repository. Its georeferenced copy (corner GCPs from the
printed neatline, UTM 14N NAD83, 2 m residuals) is read from the private .local/ folder; without it this script
does nothing and the comment is built without Exhibit D.
usage: exhibit_d_beg.py <georef_tif> <docket_attachments_dir> <out_png>"""
import json, math, os, subprocess, sys, tempfile
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPoly
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from PIL import Image

TIF, GIS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
if not os.path.exists(TIF):
    print(f"skip  Exhibit D: {TIF} not found (private BEG map)"); sys.exit(0)

lon0, lon1, lat0, lat1 = -99.372, -99.284, 30.7505, 30.803    # Grit section; south edge at the quadrangle neatline (30 deg 45 min)
k = math.cos(math.radians((lat0 + lat1) / 2))
W = 2400; H = int(W * (lat1 - lat0) / ((lon1 - lon0) * k))
with tempfile.TemporaryDirectory() as td:
    crop = os.path.join(td, "crop.tif")
    subprocess.run(["gdalwarp", "-q", "-t_srs", "EPSG:4269", "-te", str(lon0), str(lat0), str(lon1), str(lat1),
                    "-ts", str(W), str(H), "-r", "bilinear", TIF, crop], check=True)
    img = Image.open(crop).convert("RGB")

def load(name): return json.load(open(os.path.join(GIS, name)))["features"]
grit = [f for f in load("grit-section-EPSG4269.geojson") if f["properties"]["direction"].startswith("In proposed") and f["properties"]["acres"] > 1000][0]
grit_ring = grit["geometry"]["coordinates"][0]
prop_lines = [f["geometry"]["coordinates"] for f in load("boundary-per-proposed-text-line-EPSG4269.geojson")]
pet = load("boundary-with-petition-western-routing-line-EPSG4269.geojson")[0]["geometry"]
pet_lines = pet["coordinates"] if pet["type"] == "MultiLineString" else [pet["coordinates"]]

fig, ax = plt.subplots(figsize=(8, 8 * H / W), dpi=200)
ax.imshow(img, extent=(lon0, lon1, lat0, lat1), zorder=0)
ax.add_patch(MPoly(grit_ring, closed=True, facecolor="none", edgecolor="white", hatch="////", lw=0, alpha=0.55, zorder=3))
for ln in prop_lines:
    ax.plot([p[0] for p in ln], [p[1] for p in ln], color="#0072B2", lw=2.4, zorder=5)
for ln in pet_lines:
    ax.plot([p[0] for p in ln], [p[1] for p in ln], color="#1B2428", lw=3.2, zorder=6)
    ax.plot([p[0] for p in ln], [p[1] for p in ln], color="#E69F00", lw=1.8, ls=(0, (4, 3)), zorder=7)
ax.set_xlim(lon0, lon1); ax.set_ylim(lat0, lat1); ax.set_aspect(1 / k); ax.set_xticks([]); ax.set_yticks([])
handles = [
    Patch(facecolor="#D9D9D9", edgecolor="white", hatch="////", label="Grit section (4.32 sq mi)"),
    Line2D([], [], color="#0072B2", lw=2.4, label="Proposed text"),
    Line2D([], [], color="#E69F00", lw=1.8, ls=(0, (4, 3)), label="Petition routing"),
]
leg = ax.legend(handles=handles, loc="lower left", fontsize=7.5, framealpha=1.0, borderpad=0.8); leg.set_zorder(20)
ax.text(0.99, 0.99, "Principal map units: pЄsg Streeter Granite; pЄtm Town Mountain Granite; pЄps Packsaddle Schist;\n"
        "Єrh Hickory Sandstone Member; Qal alluvium; Qat terrace deposits.\n"
        "Geology: Hunt, B.B., Johnson, B., and Helper, M., 2021, Geologic map of the Grit quadrangle,\n"
        "Mason County, Texas: Bureau of Economic Geology Open-File Map 252, 1:24,000 (excerpt).\n"
        "Copyright Bureau of Economic Geology, The University of Texas at Austin; excerpt reproduced with attribution.\n"
        "Boundaries: drawn by the commenter on the USGS 1:24,000 maps.",
        transform=ax.transAxes, ha="right", va="top", fontsize=6.0, color="#1B2428",
        bbox=dict(fc="white", ec="#C9D2CF", alpha=0.95, pad=4), zorder=20)
sb = 1000 / (111320 * k); x0 = lon1 - (lon1 - lon0) * 0.20; y0 = lat0 + (lat1 - lat0) * 0.08
ax.plot([x0, x0 + sb], [y0, y0], color="#1B2428", lw=3, zorder=10)
ax.text(x0 + sb / 2, y0 + (lat1 - lat0) * 0.015, "1 km", ha="center", fontsize=8, zorder=10,
        bbox=dict(fc="white", ec="none", alpha=0.8, pad=1))
fig.tight_layout(); fig.savefig(OUT); print("wrote", OUT)
