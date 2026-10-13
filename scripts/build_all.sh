#!/usr/bin/env bash
# Build every derived artifact into build/ (gitignored) from the committed sources.
#   build/images/      Exhibit A (OpenStreetMap trails) and Exhibit C (San Pasqual Valley)
#   build/thumbnails/  ArcGIS Online item thumbnails
#   build/pdf/         the comment PDF and Attachment 1 (and the fallback comment, if its private source exists)
#   build/ucdavis/     the boundary as a UC Davis AVA Project record (github.com/UCDavisLibrary/ava)
#   build/shp/         shapefile zips of the Attachment 2 GIS layers (needs GDAL ogr2ogr)
# Requires python3 with matplotlib, markdown and pypdf (pip install -r requirements.txt) and Google Chrome.
# Quads and source PDFs are separate: scripts/fetch_quads.py, scripts/fetch_sources.py,
# scripts/build_cropped_quads.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
GIS=public-comment/docket-attachments
mkdir -p build/images build/thumbnails build/pdf build/shp build/tmp

echo "== exhibits"
"$PY" scripts/exhibits/exhibit_a_osm.py data/osm/grit-area-ways-2026-10-12.json "$GIS" build/images/exhibit-a-osm-trails.png
"$PY" scripts/exhibits/exhibit_d_beg.py .local/reference/OFM252-Grit-Sheet1-georef-EPSG26914.tif "$GIS" build/images/exhibit-d-beg-grit.png
"$PY" scripts/exhibits/san_pasqual_exhibit.py data/ttb/san-pasqual-valley-AVAs_Production-2026-10-12.geojson build/tmp/san-pasqual-check.geojson build/images/exhibit-c-san-pasqual-valley.png
"$PY" - <<'PYCHK'
import json
a = json.load(open("build/tmp/san-pasqual-check.geojson"))["features"]
b = json.load(open("public-comment/docket-attachments/ttb-published-san-pasqual-valley-EPSG4269.geojson"))["features"]
assert [f["geometry"] for f in a] == [f["geometry"] for f in b], "San Pasqual rebuild differs from the filed attachment"
print("San Pasqual rebuild matches the filed attachment")
PYCHK

echo "== thumbnails"
"$PY" scripts/exhibits/thumbnails.py "$GIS" build/thumbnails >/dev/null

echo "== pdf"
pdf() { # kind md out
  "$PY" scripts/build_comment_html.py "$1" "$2" "build/tmp/$3.html"
  "$CHROME" --headless=new --disable-gpu --no-pdf-header-footer --allow-file-access-from-files \
    --print-to-pdf="build/pdf/$3.pdf" "file://$PWD/build/tmp/$3.html" 2>/dev/null
  "$PY" scripts/pdf_meta.py "$1" "build/pdf/$3.pdf" >/dev/null
  echo "pdf   build/pdf/$3.pdf"
}
pdf comment public-comment/TTB-2026-0005-boundary-correction-comment.md TTB-2026-0005-boundary-correction-comment
pdf attachment1 public-comment/boundary-narrative-comparison.md boundary-narrative-comparison
FB=.local/filing/upload-to-regulations-gov/fallback-if-txt-refused/comment-fallback.md
if [ -f "$FB" ]; then pdf fallback "$FB" TTB-2026-0005-boundary-correction-comment-fallback; fi

echo "== UC Davis AVA Project records"
mkdir -p build/ucdavis
"$PY" scripts/ucdavis_ava.py build/ucdavis/hickory_sands_district.geojson proposed
"$PY" scripts/ucdavis_ava.py build/ucdavis/hickory_sands_district-petition-routing.geojson petition

echo "== shapefiles"
if command -v ogr2ogr >/dev/null; then
  for g in "$GIS"/*.geojson; do
    n="$(basename "${g%.geojson}")"; d="build/tmp/shp-$n"; rm -rf "$d"; mkdir -p "$d"
    # A shapefile holds one geometry type; split mixed layers (San Pasqual: polygons plus one line).
    types="$("$PY" -c 'import json,sys; print(" ".join(sorted({f["geometry"]["type"].replace("Multi","") for f in json.load(open(sys.argv[1]))["features"]})))' "$g")"
    if [ "$(echo $types | wc -w)" -eq 1 ]; then
      ogr2ogr -q -f "ESRI Shapefile" -lco ENCODING=UTF-8 -nlt PROMOTE_TO_MULTI "$d/$n.shp" "$g" 2>/dev/null
    else
      for t in $types; do
        ogr2ogr -q -f "ESRI Shapefile" -lco ENCODING=UTF-8 -nlt PROMOTE_TO_MULTI -where "OGR_GEOMETRY LIKE '%$(echo $t | tr a-z A-Z)%'" "$d/$n-$(echo $t | tr A-Z a-z).shp" "$g" 2>/dev/null
      done
    fi
    (cd "$d" && rm -f "../../shp/$n-shp.zip" && zip -q "../../shp/$n-shp.zip" ./*)
    echo "shp   build/shp/$n-shp.zip"
  done
else
  echo "ogr2ogr not found; skipping shapefiles"
fi
echo "done"
