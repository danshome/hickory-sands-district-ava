#!/bin/bash
# Hickory Sands District AVA - the boundary as proposed to TTB (Oct. 15-16, 2026): build everything from source.
#
#   ./build.sh            set up what is missing, then build the package for TTB into dist/ (same as ./build.sh all)
#   ./build.sh env        only set up the tools, the project's Python environment (.venv) and the git hooks
#   ./build.sh lint       run every pre-commit hook on every file (.pre-commit-config.yaml)
#   ./build.sh test       run the unit tests (tests/, pytest.ini)
#   ./build.sh audit      security audit of the Python lock files and the installed .venv
#   ./build.sh upgrade    every Python package to its latest compatible version (requirements*.in), audited, reinstalled
#   ./build.sh clean      remove target/ and dist/ (keeps .venv and the downloaded quads)
#   ./build.sh distclean  also remove .venv
#   ./build.sh publish    push the built package to ArcGIS Online (Dan's account; run only when you mean it), then check-live;
#                         it runs the publish dry run first and uploads nothing if one of its checks fails
#   ./build.sh publish-dry-run  (or publish --dry-run) build everything publish would send, without signing in, into
#                         target/publish/ as JSON, and check it (src/publish/agol_dryrun.py)
#   ./build.sh check-live check the public ArcGIS Online site anonymously, as TTB sees it, against the build (read-only)
#   ./build.sh site-data  refresh the website's map data (docs/data/, walk.html, the pages' figures) from the last build; commit it
#
# No manual steps, on macOS or Linux: missing tools are installed with Homebrew (GDAL, poppler, Python 3.14; on macOS
# also Google Chrome, which Linux needs installed); every Python package in the lock files is checked against the OSV
# vulnerability database before anything is installed, then installed into the project's .venv from requirements.txt
# with every download's SHA-256 checked (nothing global); and any missing or altered USGS quad is downloaded and checked
# against resources/quads/quads-manifest.csv. Inputs: src/ (code), resources/ (boundary decisions, TTB files, quads),
# documents/ (README templates), LICENSE.txt. Everything made along the way: target/. The distribution: dist/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"
NAME=Hickory-Sands-District-AVA_boundary-as-proposed-2026-10-15
STEM=hickory-sands-district-boundary-proposed-2026-10-15
TARGET="$ROOT/target"; WORK="$TARGET/work"; DIST="$ROOT/dist"; export HSD_WORK="$WORK"
# One date for every date and time the build writes into what it makes (the PDFs' and Word files' dates, zip members'
# times, the GeoPackage's and the .dbf headers' dates): the package's date, as in the file names, Oct. 15, 2026, 00:00
# UTC, so two builds of the same commit give the same bytes. SOURCE_DATE_EPOCH is the reproducible-builds.org convention
# (https://reproducible-builds.org/specs/source-date-epoch/); the scripts read it, and a date set in the environment wins.
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1792022400}"
mkdir -p "$TARGET/tmp"; export TMPDIR="$TARGET/tmp" PIP_CACHE_DIR="$TARGET/pip-cache"   # temp files and downloads stay in target/
VENV="$ROOT/.venv"; PY="$VENV/bin/python"
OS="$(uname -s)"                        # Darwin (Dan's Mac) or Linux (GitHub Actions); the tools come from Homebrew on both
if [ "$OS" = Darwin ]; then CHROME="${HSD_CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
else CHROME="${HSD_CHROME:-$(command -v google-chrome || command -v google-chrome-stable || echo /usr/bin/google-chrome)}"; fi
step() { printf '\n== %s\n' "$*"; }
sha256() { if command -v shasum >/dev/null; then shasum -a 256 "$@"; else sha256sum "$@"; fi; }   # same output either way
fsize() { wc -c < "$1" | tr -d ' '; }                                                           # bytes (BSD and GNU)
run() { "$PY" -E -s -B "$@"; }          # the project's Python only; -B: no __pycache__ in src/

need_brew() { command -v brew >/dev/null || { echo "Homebrew is needed to install $1: https://brew.sh"; exit 1; }; }

env_setup() {
    step "tools, the security audit, and the project's Python environment (.venv)"
    command -v gdal-config >/dev/null || { need_brew GDAL; brew install gdal; }
    command -v pdftotext >/dev/null || { need_brew poppler; brew install poppler; }     # the compare-text files (GDAL brings it)
    local base="${HSD_PYTHON:-$(brew --prefix 2>/dev/null || echo /opt/homebrew)/bin/python3.14}"
    [ -x "$base" ] || { need_brew "Python 3.14"; brew install python@3.14; }
    if [ ! -x "$CHROME" ]; then                                                    # Homebrew casks are macOS-only
        [ "$OS" = Darwin ] || { echo "Google Chrome is needed to print the PDFs: install it, or set HSD_CHROME"; exit 1; }
        need_brew "Google Chrome"; brew install --cask google-chrome
    fi
    local want; want="$(sed -n 's/^gdal==\([^ ]*\).*/\1/Ip' requirements.txt)"
    [ "$want" = "$(gdal-config --version)" ] || { echo "Homebrew's GDAL is $(gdal-config --version) but requirements.in pins GDAL==$want: set it to match, then ./build.sh upgrade"; exit 1; }
    local lock; lock="$(cat requirements.txt requirements-dev.txt | sha256 | cut -c1-64)"
    local installed=""; [ -f "$VENV/.lock-sha256" ] && installed="$(cat "$VENV/.lock-sha256")"
    local fresh=0
    if [ "$installed" != "$lock" ] || [ ! -x "$PY" ]; then                         # the lock changed: a fresh .venv
        rm -rf "$VENV"; "$base" -m venv "$VENV"; fresh=1                           # (standard library + bundled pip only)
    fi
    # 1. every pinned package (requirements.txt + requirements-dev.txt, indirect dependencies and pip included) is checked
    #    against the OSV vulnerability database BEFORE anything is installed (the audit uses the standard library only)
    local rc=0; "$PY" -I -B src/setup/packages.py audit requirements.txt requirements-dev.txt || rc=$?
    if [ $rc = 1 ]; then exit 1; fi
    if [ $rc = 2 ]; then
        [ $fresh = 0 ] || { echo "cannot install without the security audit: check the network and run again"; exit 1; }
        echo "WARNING: security audit skipped (offline); .venv already holds exactly the audited lock, nothing is installed"
    fi
    # 2. installed only from the lock, every download's SHA-256 checked against it
    if [ $fresh = 1 ]; then
        local P=(-m pip install -q --disable-pip-version-check --require-hashes --no-deps)
        "$PY" -I -B src/setup/packages.py pick requirements.txt pip > "$TARGET/tmp/stage-pip.txt"
        "$PY" "${P[@]}" -r "$TARGET/tmp/stage-pip.txt"
        # GDAL's bindings are compiled against Homebrew's GDAL library and need NumPy, setuptools and wheel present first
        "$PY" -I -B src/setup/packages.py pick requirements.txt numpy setuptools wheel > "$TARGET/tmp/stage-build.txt"
        "$PY" "${P[@]}" -r "$TARGET/tmp/stage-build.txt"
        "$PY" -m pip install -q --disable-pip-version-check --require-hashes --no-build-isolation -r requirements.txt -r requirements-dev.txt
        "$PY" -m pip check -q >/dev/null || { "$PY" -m pip check; exit 1; }
        echo "$lock" > "$VENV/.lock-sha256"
    fi
    if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then                    # the pre-commit hooks (.githooks/pre-commit)
        git -C "$ROOT" config core.hooksPath .githooks
    fi
    run -c "import sys; from osgeo import gdal; import numpy, scipy, matplotlib, PIL, pypdf, pymupdf; print('python', sys.version.split()[0], 'in', sys.prefix, '| GDAL', gdal.__version__, '| numpy', numpy.__version__, '| pillow', PIL.__version__, '| pypdf', pypdf.__version__, '| pymupdf', pymupdf.__version__)"
}

upgrade() {
    step "every Python package to its latest compatible version (requirements*.in -> requirements*.txt, hash-pinned)"
    [ -x "$VENV/bin/pip-compile" ] || env_setup
    local C=(--quiet --allow-unsafe --generate-hashes --strip-extras --no-emit-index-url --upgrade)
    "$VENV/bin/pip-compile" "${C[@]}" -o requirements.txt requirements.in
    "$VENV/bin/pip-compile" "${C[@]}" -o requirements-dev.txt requirements-dev.in
    git --no-pager diff --no-color -U0 -- requirements.txt requirements-dev.txt 2>/dev/null | grep -E '^[-+][A-Za-z0-9]' || echo "(no version changes)"
    env_setup                                                                       # audit, then reinstall .venv
}

audit() {
    step "security audit: the lock files (OSV) and the installed .venv (pip-audit, PyPI and OSV)"
    "$PY" -I -B src/setup/packages.py audit requirements.txt requirements-dev.txt
    "$VENV/bin/pip-audit" --progress-spinner off -s osv
    "$VENV/bin/pip-audit" --progress-spinner off -s pypi
}

quads() {
    step "the 13 USGS quads (resources/quads, checked against quads-manifest.csv)"
    run src/checks/check_quads.py || { run src/quads/fetch_quads.py; run src/checks/check_quads.py; }
    src/quads/build_cropped_quads.sh
}

stage() {
    step "a fresh target/work (inputs are read in place from resources/)"
    rm -rf "$WORK"; mkdir -p "$WORK"/{documents,review,ttb-source-check-2026-10-15}
    # regulations.gov serves Notice 243 as regs-TTB-2026-0005-0001.pdf: the same file, kept once in resources/ttb/
    cp resources/ttb/TTB-Notice-243-91FR52576-docket-TTB-2026-0005-0001.pdf "$WORK"/ttb-source-check-2026-10-15/regs-TTB-2026-0005-0001.pdf
    cp resources/ttb/TTB-Notice-243-91FR52576-docket-TTB-2026-0005-0001.pdf "$WORK"/documents/
    cp LICENSE.txt "$WORK"/
}

linework() {
    step "trace every follow step onto the ink of the quads (src/tracing; pins and routes from resources/boundary/tracing)"
    run src/boundary/ink_centerline.py | tail -n 30
    step "hand patches (resources/boundary/tracing/hand-patches-EPSG4269.geojson) spliced onto the traces"
    run src/fixing/apply_patches.py --traced "$WORK/ink-centerline-steps.geojson" --patches resources/boundary/tracing/hand-patches-EPSG4269.geojson \
        --out "$WORK/ink-centerline-steps-patched.geojson" --smooth-joins 25 | tail -n 1
    step "boundary: pins, chords, traced steps, polygon, points, GeoPackage, shapefiles"
    run src/boundary/build_proposed.py | grep -E "^AVA|written|pins moved|traced lines" | cut -c1-160
}

checks() {
    step "checks"
    run src/checks/check_build.py "$WORK/gis"                                            # hard: stops the build on failure
    run src/checks/check_step_text.py "$WORK/proposed-steps.json"                       # hard: the Federal Register's characters
    run src/review/tipcheck.py --line "$WORK/gis/$STEM-line-EPSG4269.geojson" --traced "$WORK/ink-centerline-steps.geojson" \
        --out "$WORK/review/tips-short-EPSG4269.geojson" | head -n 1                       # report
    run src/review/compare_ttb.py --ours-line "$WORK/gis/$STEM-line-EPSG4269.geojson" --ours-area "$WORK/gis/$STEM-area-EPSG4269.geojson" \
        --ttb "$ROOT/resources/ttb/ttb-avas-production-hickory-sands-district-EPSG4269-NAD83.geojson" --steps "$WORK/proposed-steps.json" \
        --out-dir "$WORK/review" 2>/dev/null | grep -E "places ringed|threshold" || true    # report
    run src/review/grit_change.py --line "$WORK/gis/$STEM-line-EPSG4269.geojson" \
        --oct14 "$ROOT/resources/boundary/proposed/step-lines-2026-10-14-EPSG4269.geojson" \
        --geology "$ROOT/resources/geology/usgs-sgmc-geology-shifted-to-naip-EPSG4269.gpkg" --out-dir "$WORK/review"   # report
    touch "$WORK/.checks-passed"             # ./build.sh site-data copies only a boundary that passed the hard checks
}

SITE_DATA=(src/site/make_site_data.py --gis "$WORK/gis" --out docs/data --walk src/site/walk.template.html docs/walk.html --pages docs)

site_data() {
    step "the website's map data (docs/data/, walk.html, figures) against this build"   # hard, after the package: a boundary change must reach the site
    run "${SITE_DATA[@]}" --check            # exits 3 when docs/data/ is stale, and says how to refresh it
}

documents() {
    step "documents"
    local D="$WORK/documents" S1=Hickory-Sands-District-boundary-description-as-proposed-2026-10-15 S2=Hickory-Sands-District-boundary-changes-side-by-side-2026-10-15
    run src/documents/make_readme.py
    run src/documents/make_docs.py >/dev/null
    run src/documents/make_compare.py >/dev/null
    for S in $S1 $S2 Hickory-Sands-District-read-me-first-2026-10-15; do
        # shellcheck disable=SC2086   # HSD_CHROME_FLAGS: extra options, split on purpose (GitHub's Linux runners set them)
        # HSD_CHROME_TMPDIR: a short temp dir for Chrome's socket where target/tmp's path is too long for one (Linux: 108 bytes)
        TMPDIR="${HSD_CHROME_TMPDIR:-$TMPDIR}" "$CHROME" --headless=new --disable-gpu --no-pdf-header-footer ${HSD_CHROME_FLAGS:-} \
            --print-to-pdf="$D/$S.pdf" "file://$D/$S.html" 2>"$WORK/chrome.log" || true
        [ -s "$D/$S.pdf" ] || { echo "Chrome did not write $S.pdf:"; tail -n 20 "$WORK/chrome.log"; exit 1; }
        run src/documents/pdf_dates.py "$D/$S.pdf"   # Chrome dates it when it printed it: SOURCE_DATE_EPOCH instead
    done
    run src/documents/html2docx.py "$D/$S1.html" "$D/$S1.docx" "Hickory Sands District AVA: regulatory text as proposed to TTB" "Dan McLaughlin" "Hickory Sands District AVA - boundary description as proposed to TTB (Oct. 15, 2026)"
    run src/documents/html2docx.py "$D/$S2.html" "$D/$S2.docx" "Hickory Sands District AVA: changes to TTB's published boundary description" "Dan McLaughlin" "Hickory Sands District AVA - changes to TTB's published boundary description (Oct. 15, 2026)"
    run src/documents/make_notice_copy.py | grep -E "highlighted" || true
    run src/documents/pdf_text.py "$D/TTB-Notice-243-91FR52576-docket-TTB-2026-0005-0001.pdf" "$D/compare-text_TTB-Notice-243-docket.txt"
    run src/documents/pdf_text.py "$D/TTB-Notice-243-with-proposed-Hickory-Sands-District-changes-2026-10-15-UNOFFICIAL.pdf" "$D/compare-text_TTB-Notice-243-with-proposed-changes.txt"
    echo "documents: $(ls "$D" | wc -l | tr -d ' ') files"
}

quadsheets() {
    step "the 13 USGS quads with the boundary (GeoPDF + GeoTIFF)"
    run src/boundary/build_proposed_quads.py > "$WORK/quads-build.log" 2>&1 || { tail -n 20 "$WORK/quads-build.log"; exit 1; }
    echo "$(ls "$WORK"/quads/*_geo.pdf | wc -l | tr -d ' ') GeoPDFs, $(ls "$WORK"/quads/*_geo.tif | wc -l | tr -d ' ') GeoTIFFs"
}

package() {
    step "package"
    src/package/make_package.sh
    rm -rf "$DIST"; mkdir -p "$DIST"
    cp "$WORK/$NAME.zip" "$DIST"/
    cp "$WORK/README.txt" "$DIST/$NAME-README.txt"
    ( cd "$DIST" && sha256 "$NAME.zip" "$NAME-README.txt" > SHA256SUMS.txt )
    run src/checks/check_outputs.py "$WORK" "$DIST" | tee "$WORK/review/output-checks.txt"   # hard: what reaches TTB (warnings do not stop)
    {
        echo "Hickory Sands District AVA - boundary as proposed to TTB: build report"
        echo "built      $(date '+%Y-%m-%d %H:%M %Z') on $(hostname -s) ($(uname -s), GDAL $(gdal-config --version), $(pdftotext -v 2>&1 | head -n 1))"
        echo "source     git $(git rev-parse --short HEAD 2>/dev/null || echo '?')$(git diff --quiet 2>/dev/null || echo ' (with uncommitted changes)')"
        run -c "import json; d = json.load(open('$WORK/proposed-steps.json')); print('area       %.3f sq mi (GRS 1980), %d steps' % (d['sqmi'], len(d['steps'])))"
        run src/checks/check_build.py "$WORK/gis" | sed 's/^/check      /'
        grep -E '^(output checks|WARNING)' "$WORK/review/output-checks.txt" | sed 's/^/check      /'
        [ -f "$WORK/review/tips-short-EPSG4269.geojson" ] && run -c "import json; print('tips       %d tips of contours/creeks the line stops short of (report)' % len(json.load(open('$WORK/review/tips-short-EPSG4269.geojson'))['features']))"
        [ -f "$WORK/review/ttb-diff-stats.json" ] && run -c "import json; s = json.load(open('$WORK/review/ttb-diff-stats.json')); a = s['areas']; print('comparison %d big differences from the AVA Map Explorer polygon (lines %.0f m or more apart); %d pieces of land between the two lines, from the same text drawn differently %.0f acres in the proposed revision only and %.0f in the Map Explorer polygon only (reports: target/work/review/)' % (s['big'], s['big_m'], sum(v['pieces'] for v in a.values()), a['drawing']['revision_only_acres'], a['drawing']['map_explorer_only_acres']))"
        echo "package    $NAME.zip  $(fsize "$DIST/$NAME.zip") bytes, $(unzip -Z1 "$DIST/$NAME.zip" | grep -v '/$' | wc -l | tr -d ' ') files"
    } | tee "$DIST/build-report.txt"
}

dry_run() {
    [ -d "$WORK/pkg/$NAME" ] || { echo "nothing built yet: run ./build.sh first"; exit 1; }
    step "publish dry run: everything ArcGIS Online would get, built without signing in (target/publish/), and checked"
    run src/publish/agol_dryrun.py "$TARGET/publish"   # exits 1 if a check fails, which stops a publish here (set -e)
}

publish() {
    dry_run                                  # first: nothing is uploaded if a check fails
    step "ArcGIS Online (Dan's saved profile 'hsd')"
    run src/publish/agol_publish.py
    run src/publish/agol_layer.py
    run src/publish/agol_dashboard.py        # after the layers: it finds the map and layers by title
    run src/publish/agol_org_categories.py   # it categorizes the items the three above put in the folder
    run src/publish/agol_share.py            # everything in the folder, and the group, public (Dan, 2026-10-16)
    check_live                               # last: the public site as TTB sees it, against this build
}

check_live() {
    step "the public site, checked anonymously against the build (security, sharing, links, figures, files)"
    run src/publish/agol_check.py
    run -m pytest -v -m live tests/live      # the dashboard in Google Chrome: two phones, four screens (#68; target/browser-tests/)
}

case "${1:-all}" in
    all)       env_setup; quads; stage; linework; checks; documents; quadsheets; package; site_data ;;
    env)       env_setup ;;
    clean)     rm -rf "$TARGET" "$DIST"; echo "removed target/ and dist/" ;;
    distclean) rm -rf "$TARGET" "$DIST" "$VENV"; echo "removed target/, dist/ and .venv/" ;;
    publish)   env_setup; if [ "${2:-}" = --dry-run ]; then dry_run; else publish; fi ;;
    publish-dry-run) env_setup; dry_run ;;
    check-live) env_setup; check_live ;;
    site-data) env_setup; [ -f "$WORK/.checks-passed" ] || { echo "no checked build: run ./build.sh first"; exit 1; }
               step "the website's map data (docs/data/), walk page and figures from the last build"; run "${SITE_DATA[@]}" ;;
    audit)     env_setup; audit ;;
    upgrade)   upgrade ;;
    lint)      env_setup; step "pre-commit hooks on every file"; PRE_COMMIT_HOME="$TARGET/pre-commit" "$VENV/bin/pre-commit" run --all-files ;;
    test)      env_setup; step "unit tests (tests/, pytest)"; run -m pytest -q tests ;;
    *)         echo "usage: ./build.sh [all|env|lint|test|audit|upgrade|clean|distclean|publish [--dry-run]|publish-dry-run|check-live]"; exit 2 ;;
esac
