#!/usr/bin/env bash
# Copy the built comment PDFs and the GIS layers into the private filing kit
# (.local/filing/upload-to-regulations-gov/, not in the repository) with the upload names.
# A staged PDF that has been digitally signed (Acrobat Sign) is never overwritten unless FORCE=1.
set -euo pipefail
cd "$(dirname "$0")/.."
U=.local/filing/upload-to-regulations-gov
[ -d "$U" ] || { echo "no filing kit at $U" >&2; exit 1; }
signed() { [ -f "$1" ] && LC_ALL=C /usr/bin/grep -a -q "/ByteRange" "$1"; }
put() { # build-pdf staged-name
  if signed "$2" && [ "${FORCE:-0}" != 1 ]; then
    echo "keep  $2 (signed; not overwritten, use FORCE=1 to replace it with an unsigned rebuild)"
  else
    cp "$1" "$2"; echo "copy  $2  (UNSIGNED: sign it in Acrobat Sign before uploading)"
  fi
}
put build/pdf/TTB-2026-0005-boundary-correction-comment.pdf "$U/01_McLaughlin_Comment_TTB-2026-0005_2026-10-13.pdf"
put build/pdf/boundary-narrative-comparison.pdf "$U/02_Attachment-1_Boundary-Narrative-Comparison.pdf"
if [ -f build/pdf/TTB-2026-0005-boundary-correction-comment-fallback.pdf ]; then
  put build/pdf/TTB-2026-0005-boundary-correction-comment-fallback.pdf "$U/fallback-if-txt-refused/01_McLaughlin_Comment_TTB-2026-0005_2026-10-13.pdf"
fi
n=3
for f in boundary-per-proposed-text-line boundary-per-proposed-text-area boundary-per-proposed-text-points \
         boundary-with-petition-western-routing-line boundary-with-petition-western-routing-area boundary-with-petition-western-routing-points \
         grit-section published-polygon-departures granite-rock-crawling-parks ttb-published-san-pasqual-valley; do
  cp "public-comment/docket-attachments/$f-EPSG4269.geojson" "$U/$(printf %02d $n)_Attachment-2_${f}_EPSG4269.geojson.txt"
  n=$((n+1))
done
echo "staged into $U"
