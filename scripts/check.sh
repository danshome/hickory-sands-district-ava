#!/usr/bin/env bash
# Read-only consistency checks. Edits nothing; exits non-zero if any check fails.
#   1. layer fingerprints   GeoJSON in layers/, public-comment/docket-attachments/, comparison/
#                           match scripts/layer-checksums.sha256 (re-record with --record after
#                           a deliberate edit)
#   2. layer sanity         parses, EPSG:4269, inside the AVA region, rings closed, 96 steps / 97 points
#   3. numbers              areas (GRS80 ellipsoid, sq mi) agree with the layer attributes, the
#                           comment, Attachment 1, README, DATA_SOURCES and NOTES
#   4. projection self-test code/quadlib.py, when the quads are in code/data/quads/
#   5. filed copies         each PDF staged in .local/filing/ is either identical to its build, or digitally
#                           signed with the same text as its build (signature stamp lines allowed); warns if unsigned
# Requires python3 with pyproj (pip install -r requirements.txt).
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
SUMS=scripts/layer-checksums.sha256
FILES=$(ls layers/*.geojson layers/*.csv public-comment/docket-attachments/*.geojson comparison/*.geojson)

if [ "${1:-}" = "--record" ]; then
  shasum -a 256 $FILES > "$SUMS"; echo "recorded $(wc -l < "$SUMS" | tr -d ' ') fingerprints in $SUMS"; exit 0
fi

fail=0
echo "== 1. layer fingerprints"
if out=$(shasum -a 256 -c "$SUMS" 2>&1); then echo "ok    $(wc -l < "$SUMS" | tr -d ' ') files unchanged"
else echo "$out" | grep -v ': OK$' | sed 's/^/FAIL  /'; fail=1; fi
for f in $FILES; do grep -q " $f\$" "$SUMS" || { echo "FAIL  $f has no recorded fingerprint"; fail=1; }; done

echo "== 2-3. layer sanity and numbers"
"$PY" -I - <<'PY' || fail=1
import glob, json, re, sys
from pyproj import Geod
G, SQMI = Geod(ellps="GRS80"), 2589988.110336
bad = []
def ok(msg): print("ok   ", msg)
def no(msg): print("FAIL ", msg); bad.append(msg)

def polys(g):
    return [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"] if g["type"] == "MultiPolygon" else []
def area(path):
    a = 0.0
    for f in json.load(open(path))["features"]:
        for p in polys(f["geometry"]):
            for i, r in enumerate(p):
                v = abs(G.polygon_area_perimeter([c[0] for c in r], [c[1] for c in r])[0])
                a += v if i == 0 else -v
    return a / SQMI

def coords(g):
    t, c = g["type"], g["coordinates"]
    if t == "Point": yield c
    elif t in ("LineString", "MultiPoint"): yield from c
    elif t in ("Polygon", "MultiLineString"): yield from (x for r in c for x in r)
    elif t == "MultiPolygon": yield from (x for p in c for r in p for x in r)

# AVA region (Mason, Llano, Gillespie, McCulloch counties), generous
BOX = (-99.9, 30.4, -98.6, 31.3)
for p in sorted(glob.glob("layers/*.geojson") + glob.glob("public-comment/docket-attachments/*.geojson") + glob.glob("comparison/*.geojson")):
    try: d = json.load(open(p))
    except Exception as e: no(f"{p}: does not parse ({e})"); continue
    crs = json.dumps(d.get("crs", ""))
    if "4269" not in crs and "4326" not in crs and d.get("crs") is not None: no(f"{p}: CRS {crs}")
    if "san-pasqual" in p: continue  # California precedent layer
    pts = [c for f in d["features"] for c in coords(f["geometry"])]
    out = [c for c in pts if not (BOX[0] <= c[0] <= BOX[2] and BOX[1] <= c[1] <= BOX[3])]
    if out: no(f"{p}: {len(out)} coordinates outside the AVA region")
    for f in d["features"]:
        for poly in polys(f["geometry"]):
            for r in poly:
                if r[0] != r[-1]: no(f"{p}: unclosed ring")
ok("layers parse, are NAD83, lie in the AVA region, rings closed") if not bad else None

for p, n in [("layers/hickory-sands-nprm-boundary-polyline-EPSG4269-NAD83.geojson", 96),
             ("layers/hickory-sands-nprm-boundary-points-EPSG4269-NAD83.geojson", 97),
             ("public-comment/docket-attachments/boundary-per-proposed-text-line-EPSG4269.geojson", 96),
             ("public-comment/docket-attachments/boundary-per-proposed-text-points-EPSG4269.geojson", 97)]:
    k = len(json.load(open(p))["features"])
    (ok if k == n else no)(f"{p.split('/')[-1]}: {k} features (expected {n})")

A = {
    "proposed": area("public-comment/docket-attachments/boundary-per-proposed-text-area-EPSG4269.geojson"),
    "petition": area("public-comment/docket-attachments/boundary-with-petition-western-routing-area-EPSG4269.geojson"),
    "ttb":      area("comparison/ttb-avas-production-hickory-sands-district-EPSG4269-NAD83.geojson"),
}
lay = area("layers/hickory-sands-nprm-boundary-polygon-EPSG4269-NAD83.geojson")
print(f"      areas (GRS80): proposed text {A['proposed']:.2f}, petition routing {A['petition']:.2f}, TTB published {A['ttb']:.2f} sq mi")
(ok if abs(lay - A["proposed"]) < 0.005 else no)(f"layers/ polygon area {lay:.2f} = docket proposed-text area")

for p, key in [("layers/hickory-sands-nprm-boundary-polygon-EPSG4269-NAD83.geojson", "proposed"),
               ("public-comment/docket-attachments/boundary-per-proposed-text-area-EPSG4269.geojson", "proposed"),
               ("public-comment/docket-attachments/boundary-with-petition-western-routing-area-EPSG4269.geojson", "petition")]:
    v = json.load(open(p))["features"][0]["properties"].get("area_sqmi")
    (ok if v is not None and abs(v - A[key]) < 0.006 else no)(f"{p.split('/')[-1]}: area_sqmi attribute {v} vs {A[key]:.2f}")

# Every "NNN.N sq mi" quoted in the documents must be one of the computed areas (1 or 2 decimals).
allowed = {f"{v:.1f}" for v in A.values()} | {f"{v:.2f}" for v in A.values()}
for doc in ["public-comment/TTB-2026-0005-boundary-correction-comment.md", "public-comment/boundary-narrative-comparison.md",
            "README.md", "DATA_SOURCES.md", "NOTES-interpretation-and-divergences.md"]:
    # Dated history lines ("198.76 -> 197.96") keep their figures of the time and are skipped.
    text = "\n".join(l for l in open(doc, encoding="utf-8").read().splitlines() if "->" not in l)
    found = re.findall(r"\b(19\d\.\d{1,2})\s*(?:sq\.?\s*mi|square miles)", text)
    stale = sorted(set(found) - allowed)
    if stale: no(f"{doc}: quotes {', '.join(stale)} sq mi, not a current computed area")
    elif found: ok(f"{doc}: {len(found)} area figure(s) match")
sys.exit(1 if bad else 0)
PY

echo "== 4. projection self-test"
if ls code/data/quads/*.tif >/dev/null 2>&1; then
  (cd code && "$PY" -I quadlib.py) || { echo "FAIL  quadlib self-test"; fail=1; }
else echo "skip  quads not unzipped into code/data/quads/"; fi

echo "== 5. filed copies"
U=.local/filing/upload-to-regulations-gov
if [ -d build/pdf ] && [ -d "$U" ]; then
  for pair in "TTB-2026-0005-boundary-correction-comment.pdf:01_McLaughlin_Comment_TTB-2026-0005_2026-10-13.pdf" \
              "boundary-narrative-comparison.pdf:02_Attachment-1_Boundary-Narrative-Comparison.pdf" \
              "TTB-2026-0005-boundary-correction-comment-fallback.pdf:fallback-if-txt-refused/01_McLaughlin_Comment_TTB-2026-0005_2026-10-13.pdf"; do
    b="build/pdf/${pair%%:*}"; s="$U/${pair##*:}"
    [ -f "$b" ] && [ -f "$s" ] || continue
    if LC_ALL=C /usr/bin/grep -a -q "/ByteRange" "$s"; then
      # Signed: every line of the build's text must appear, in order, in the signed file.
      if "$PY" -I - "$b" "$s" <<'PYTXT'
import difflib, subprocess, sys
t = lambda p: [l.strip() for l in subprocess.run(["pdftotext", "-layout", p, "-"], capture_output=True, text=True).stdout.splitlines() if l.strip()]
b, s = t(sys.argv[1]), t(sys.argv[2])
lost = [l for op, l in ((l[0], l[2:]) for l in difflib.ndiff(b, s)) if op == "-"]
added = [l for op, l in ((l[0], l[2:]) for l in difflib.ndiff(b, s)) if op == "+"]
for l in lost[:5]: print("      missing or changed after signing:", l[:100])
for l in added[:3]: print("      added by signing:", l[:100])
sys.exit(1 if lost else 0)
PYTXT
      then echo "ok    $s is signed and its text matches the latest build"
      else echo "FAIL  $s is signed but its text differs from $b (signed an old build? re-sign after make stage FORCE=1)"; fail=1; fi
    elif cmp -s "$b" "$s"; then echo "WARN  $s matches the latest build but is NOT signed yet"
    else echo "FAIL  $s differs from $b (run make stage)"; fail=1; fi
  done
  # The upload folder must hold exactly files 01 to 12 (plus the fallback folder and the README-listed files).
  extra=$(cd "$U" && ls -A | /usr/bin/grep -v -E '^(0[1-9]|1[0-2])_.*\.(pdf|geojson\.txt)$|^fallback-if-txt-refused$' || true)
  n=$(cd "$U" && ls -A | /usr/bin/grep -c -E '^(0[1-9]|1[0-2])_' || true)
  if [ -n "$extra" ]; then echo "FAIL  unexpected file(s) in $U, do not upload them: $(echo $extra)"; fail=1
  elif [ "$n" != 12 ]; then echo "FAIL  $U holds $n numbered files, expected 12"; fail=1
  else echo "ok    upload folder holds exactly files 01 to 12"; fi
else echo "skip  no build/pdf or no private filing kit"; fi

echo; if [ $fail -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "CHECKS FAILED"; fi
exit $fail
