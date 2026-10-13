#!/usr/bin/env bash
# 1. Generate quads_cropped/<name>_cropped.vrt from the committed templates (*.vrt.in),
#    filling in this checkout's absolute path (GDAL cannot resolve relative paths inside
#    /vsizip/). The NAD27 QGIS project loads these VRTs.
# 2. Write neatline-cropped GeoTIFFs to quads_cropped_geotiff/ (gitignored).
# Each VRT reads its original GeoTIFF from quads_geotiff/<name>.tif.zip, so run
# scripts/fetch_quads.py first. Requires python3 and GDAL (gdal_translate).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'PY'
import glob, os
root = os.getcwd()
for t in sorted(glob.glob("quads_cropped/*.vrt.in")):
    with open(t, encoding="utf-8") as f: s = f.read()
    with open(t[:-3], "w", encoding="utf-8") as f: f.write(s.replace("@REPO_ROOT@", root))
    print("vrt  ", t[:-3])
PY
if [ "${1:-}" = "--vrt-only" ]; then exit 0; fi
command -v gdal_translate >/dev/null || { echo "gdal_translate not found; install GDAL" >&2; exit 1; }
mkdir -p quads_cropped_geotiff
for vrt in quads_cropped/*.vrt; do
  out="quads_cropped_geotiff/$(basename "${vrt%.vrt}").tif"
  echo "tif   $out"
  gdal_translate -q -of GTiff -co COMPRESS=DEFLATE -co TILED=YES "$vrt" "$out"
done
echo "done"
