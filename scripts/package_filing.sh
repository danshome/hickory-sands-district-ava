#!/usr/bin/env bash
# Package the exact Regulations.gov upload set into one zip, after the PDFs are signed.
#   .local/filing/TTB-2026-0005-upload-files.zip   files 01 to 12, nothing else
#   .local/filing/COMMENT-BOX.txt                   the text to paste into the comment box (not uploaded)
# Refuses unless make check passes and files 01 and 02 are digitally signed with text matching the latest build.
# The zip is a checklist: unzip it and upload the 12 files one by one; do not upload the zip itself.
set -euo pipefail
cd "$(dirname "$0")/.."
U=.local/filing/upload-to-regulations-gov
OUT=.local/filing/TTB-2026-0005-upload-files.zip
out=$(scripts/check.sh 2>&1) || { echo "$out" | /usr/bin/grep -E "FAIL|WARN" ; echo "make check failed; not packaging" >&2; exit 1; }
for f in "$U"/01_*.pdf "$U"/02_*.pdf; do
  echo "$out" | /usr/bin/grep -q "ok    $f is signed and its text matches the latest build" \
    || { echo "not signed (or not matching the latest build): $f" >&2; echo "sign it in Acrobat Sign, then run make package again" >&2; exit 1; }
done
n=$(ls "$U" | /usr/bin/grep -c -E '^(0[1-9]|1[0-2])_' || true)
[ "$n" = 12 ] || { echo "expected 12 numbered files in $U, found $n" >&2; exit 1; }
rm -f "$OUT"
(cd "$U" && zip -q -X "../$(basename "$OUT")" $(ls | /usr/bin/grep -E '^(0[1-9]|1[0-2])_'))
python3 - <<'PY'
import re
s = open(".local/filing/README.md", encoding="utf-8").read()
box = re.search(r"## 2\. Comment box.*?```\n(.*?)```", s, re.S).group(1).strip()
open(".local/filing/COMMENT-BOX.txt", "w", encoding="utf-8").write(box + "\n")
print(f"comment box text: {len(box)} characters (limit 5,000)")
PY
echo "packaged $(unzip -l "$OUT" | tail -1 | awk '{print $2}') files into $OUT:"
unzip -l "$OUT" | awk 'NR>3 && $4 ~ /^[0-9]/ {print "  " $4}'
echo "Unzip and upload these 12 files individually; paste .local/filing/COMMENT-BOX.txt into the comment box."
