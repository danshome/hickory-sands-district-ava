#!/usr/bin/env bash
# The 13 quads cropped to their 7.5-minute neatline, for viewing in QGIS: target/quads-cropped/<name>_cropped.vrt,
# made from the templates in resources/quads/cropped/*.vrt.in (GDAL cannot resolve relative paths inside /vsizip/, so
# the repository's absolute path is filled in). Each VRT reads its GeoTIFF straight from resources/quads/geotiff/<name>.tif.zip.
# Display only; the build itself reads the original zips. Run by ./build.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/target/quads-cropped"; mkdir -p "$OUT"
for t in "$ROOT"/resources/quads/cropped/*.vrt.in; do
    b="$(basename "${t%.in}")"
    sed "s|@REPO_ROOT@|$ROOT|g" "$t" > "$OUT/$b"
done
echo "quads for viewing: $(ls "$OUT"/*.vrt | wc -l | tr -d ' ') neatline-cropped VRTs in target/quads-cropped/"
