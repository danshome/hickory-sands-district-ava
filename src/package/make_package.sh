#!/bin/bash
# Builds the package folder and its zip from the build outputs (documents/, gis/, quads/, README.txt, LICENSE.txt).
# The folder is generated entirely by this script; run it after any rebuild. Usage: ./make_package.sh
set -euo pipefail
cd "${HSD_WORK:?set HSD_WORK to the build work dir (build.sh does)}"
NAME=Hickory-Sands-District-AVA_boundary-as-proposed-2026-10-15
P=pkg/$NAME; D=documents
rm -rf "$P"; mkdir -p "$P"/{1_boundary-description,2_TTB-notice-243-with-changes-highlighted,3_changes-side-by-side,4_GIS/shapefiles,5_USGS-quadrangles-with-boundary}
cp README.txt LICENSE.txt "$P"/
cp "$D"/Hickory-Sands-District-boundary-description-as-proposed-2026-10-15{.pdf,.docx,.txt,-steps.csv} "$P"/1_boundary-description/
N="$P"/2_TTB-notice-243-with-changes-highlighted
cp "$D"/TTB-Notice-243-with-proposed-Hickory-Sands-District-changes-2026-10-15-UNOFFICIAL.pdf "$N"/TTB-Notice-243-with-proposed-Hickory-Sands-District-changes-highlighted-2026-10-15-UNOFFICIAL.pdf
cp "$D"/TTB-Notice-243-91FR52576-docket-TTB-2026-0005-0001.pdf "$N"/TTB-Notice-243-as-published-docket-TTB-2026-0005-0001.pdf
cp "$D"/compare-text_TTB-Notice-243-docket.txt "$N"/text-for-comparing-1_TTB-Notice-243-as-published.txt
cp "$D"/compare-text_TTB-Notice-243-with-proposed-changes.txt "$N"/text-for-comparing-2_TTB-Notice-243-with-proposed-changes.txt
cp "$D"/Hickory-Sands-District-boundary-changes-side-by-side-2026-10-15{.pdf,.docx} "$P"/3_changes-side-by-side/
cp gis/*.geojson gis/*.gpkg "$P"/4_GIS/
cp gis/shapefiles/*.zip "$P"/4_GIS/shapefiles/
cp quads/*_geo.pdf quads/*_geo.tif "$P"/5_USGS-quadrangles-with-boundary/
cmp -s "$D"/TTB-Notice-243-91FR52576-docket-TTB-2026-0005-0001.pdf ttb-source-check-2026-10-15/regs-TTB-2026-0005-0001.pdf   # TTB's file, unchanged
(cd pkg && rm -f "../$NAME.zip" && zip -q -r -X "../$NAME.zip" "$NAME" -x '*.DS_Store')
echo "package: $(find "$P" -type f | wc -l | tr -d ' ') files; $NAME.zip $(wc -c < "$NAME.zip" | tr -d ' ') bytes"
