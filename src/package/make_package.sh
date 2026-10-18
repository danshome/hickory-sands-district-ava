#!/bin/bash
# Builds the package folder and its zip from the build outputs (documents/, gis/, quads/, README.txt, LICENSE.txt).
# The folder is generated entirely by this script; run it after any rebuild. Usage: ./make_package.sh
set -euo pipefail
REVISION="$(tr -d '[:space:]' < "$(dirname "$0")/../../resources/boundary/revision-date.txt")"   # the one place it is typed
cd "${HSD_WORK:?set HSD_WORK to the build work dir (build.sh does)}"
NAME="Hickory-Sands-District-AVA_boundary-as-proposed-$REVISION"
P=pkg/$NAME; D=documents
rm -rf "$P"; mkdir -p "$P"/{1_boundary-description,2_TTB-notice-243-with-changes-highlighted,3_changes-side-by-side,4_GIS/shapefiles,5_USGS-quadrangles-with-boundary}
cp README.txt LICENSE.txt "$P"/
cp "$D/Hickory-Sands-District-boundary-description-as-proposed-$REVISION"{.pdf,.docx,.txt,-steps.csv} "$P"/1_boundary-description/
N="$P"/2_TTB-notice-243-with-changes-highlighted
cp "$D/TTB-Notice-243-with-proposed-Hickory-Sands-District-changes-$REVISION-UNOFFICIAL.pdf" "$N/TTB-Notice-243-with-proposed-Hickory-Sands-District-changes-highlighted-$REVISION-UNOFFICIAL.pdf"
cp "$D"/TTB-Notice-243-91FR52576-docket-TTB-2026-0005-0001.pdf "$N"/TTB-Notice-243-as-published-docket-TTB-2026-0005-0001.pdf
cp "$D"/compare-text_TTB-Notice-243-docket.txt "$N"/text-for-comparing-1_TTB-Notice-243-as-published.txt
cp "$D"/compare-text_TTB-Notice-243-with-proposed-changes.txt "$N"/text-for-comparing-2_TTB-Notice-243-with-proposed-changes.txt
cp "$D/Hickory-Sands-District-boundary-changes-side-by-side-$REVISION"{.pdf,.docx} "$P"/3_changes-side-by-side/
cp gis/*.geojson gis/*.gpkg "$P"/4_GIS/
cp gis/shapefiles/*.zip "$P"/4_GIS/shapefiles/
cp quads/*_geo.pdf quads/*_geo.tif "$P"/5_USGS-quadrangles-with-boundary/
cmp -s "$D"/TTB-Notice-243-91FR52576-docket-TTB-2026-0005-0001.pdf "ttb-source-check-$REVISION/regs-TTB-2026-0005-0001.pdf"   # TTB's file, unchanged
# Every file and folder in the zip dated SOURCE_DATE_EPOCH (build.sh sets it to the package's date; the present time
# when it is not set), not the time it was copied, so the same files give the same zip. A zip holds local times, so
# touch and zip run in UTC; -X leaves out the other times (and owners) zip would add.
EPOCH="${SOURCE_DATE_EPOCH:-$(date +%s)}"
STAMP="$(date -u -r "$EPOCH" +%Y%m%d%H%M.%S 2>/dev/null || date -u -d "@$EPOCH" +%Y%m%d%H%M.%S)"   # BSD date, GNU date
find "$P" -exec env TZ=UTC touch -t "$STAMP" {} +
(cd pkg && rm -f "../$NAME.zip" && TZ=UTC zip -q -r -X "../$NAME.zip" "$NAME" -x '*.DS_Store')
echo "package: $(find "$P" -type f | wc -l | tr -d ' ') files; $NAME.zip $(wc -c < "$NAME.zip" | tr -d ' ') bytes"
