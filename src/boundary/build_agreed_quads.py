"""The 13 USGS quads (GeoPDF + GeoTIFF, USGS files unaltered except the added line) with the proposed boundary line,
using src/boundary/build_quad_sheets.py as is. Each line feature already carries its full record (TTB's AVAs_Production
fields + step fields), so it is passed through unchanged. Output: quads/<USGS stem>.pdf / .tif."""

import glob, json, os, re, sys

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)  # the repository root
HERE = os.environ.get("HSD_WORK") or os.path.join(
    ROOT, "target", "work"
)  # build work dir (build.sh stages resources/ here)
sys.path.insert(0, os.path.join(ROOT, "src", "boundary"))
from osgeo import gdal, osr
import ttb_record, build_quad_sheets as q

gdal.UseExceptions()
gdal.SetConfigOption("GDAL_PAM_ENABLED", "NO")
LINE = (
    "hickory-sands-district-boundary-proposed-2026-10-15-line-EPSG4269.geojson"
)
AREA = (
    "hickory-sands-district-boundary-proposed-2026-10-15-area-EPSG4269.geojson"
)
ttb_record.CORRECTED = os.path.join(
    HERE, "gis"
)  # so the builder embeds our line GeoJSON in each GeoPDF
OUT = os.path.join(HERE, "quads")
os.makedirs(OUT, exist_ok=True)
S = dict(
    src=LINE,
    display="step",
    layer="Hickory Sands District boundary - as proposed to TTB, Oct. 15, 2026",
)
line = json.load(open(os.path.join(HERE, "gis", LINE)))
record = json.load(open(os.path.join(HERE, "gis", AREA)))["features"][0][
    "properties"
]
only = sys.argv[1:]
for orig_pdf in sorted(
    glob.glob(os.path.join(ROOT, "resources", "quads", "geopdf", "*_geo.pdf"))
):
    stem = os.path.basename(orig_pdf)[:-4]
    quadname = re.match(r"TX_(.+?)_\d+_", stem).group(1)
    if only and quadname not in only:
        continue
    zip_path = os.path.join(
        ROOT, "resources", "quads", "geotiff", stem + ".tif.zip"
    )
    srs = osr.SpatialReference(
        gdal.Open(f"/vsizip/{zip_path}/{stem}.tif").GetProjection()
    )
    feats = q.project(line, srs)
    base = os.path.join(OUT, stem)
    fp = q.build_pdf(
        orig_pdf, [(p, parts) for p, parts in feats], S, base + ".pdf"
    )
    ft, tiles = q.build_tif(
        zip_path,
        stem + ".tif",
        feats,
        base + ".tif",
        dict(record, OBJECTID=1),
        LINE,
    )
    ds = gdal.Open(base + ".tif", gdal.GA_Update)
    ds.SetMetadataItem(
        "boundary_layer",
        f"{LINE} (NAD83, EPSG:4269): the boundary as proposed to TTB on Oct. 15, 2026",
    )
    ds = None
    print(
        f"{quadname:18s} pdf features={len(fp):3d}  tif features={len(ft):3d}  tiles rewritten={tiles}",
        flush=True,
    )
