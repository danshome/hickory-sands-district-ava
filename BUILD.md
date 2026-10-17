# Building the Hickory Sands District AVA package for TTB

One command, run from the repository root, rebuilds everything that goes to TTB from source. No manual steps:

```
./build.sh
```

It installs what is missing (GDAL, poppler, Python 3.14, and on macOS Google Chrome, via Homebrew, on macOS or Linux), checks every Python package it will
install against the OSV vulnerability database, creates the project's Python environment `.venv` from the hash-pinned
`requirements.txt` (nothing global), downloads any USGS quad that is missing or altered, builds, checks, and packages. The result is in `dist/`:

| file | what it is |
|---|---|
| `Hickory-Sands-District-AVA_boundary-as-proposed-2026-10-15.zip` | the package to upload: description (PDF/DOCX/TXT/CSV), TTB's Notice 243 with the changes highlighted, the side-by-side, GIS (GeoPackage, GeoJSON, shapefiles), the 13 USGS quads with the boundary |
| `...-README.txt` | the package's README, for reading without unzipping |
| `SHA256SUMS.txt` | checksums of the above |
| `build-report.txt` | area, step count, check results, source commit |

Other commands:

- `./build.sh env` sets up the tools, `.venv` and the git pre-commit hooks only.
- `./build.sh lint` runs every pre-commit hook on every file.
- `./build.sh audit` re-checks the lock files (OSV) and the installed `.venv` (pip-audit, PyPI and OSV databases).
- `./build.sh upgrade` moves every Python package to its latest compatible version, audits, and rebuilds `.venv`.
- `./build.sh clean` removes `target/` and `dist/`.
- `./build.sh distclean` also removes `.venv`.
- `./build.sh publish` pushes the built package to ArcGIS Online: items, descriptions, metadata, categories, the hosted
  layers (the boundary, the differences from the AVA Map Explorer polygon, the change near Grit, the shifted geology),
  the web map over the 13 quads with TTB's live AVA Map Explorer polygon, and the dashboard that links everything; it
  makes the folder if it is missing and shares everything publicly. It signs in with Dan's saved `arcgis` profile `hsd`.
  Publishing is never part of a normal build; run it only when you mean to update ArcGIS Online. Its last step is
  `check-live`, so a publish ends with the live site's pass/fail report.
- `./build.sh check-live` checks the public site the way TTB sees it, without signing in (`src/publish/agol_check.py`,
  anonymous read-only requests; it changes nothing, so it is safe to run any time). One line per check, and every failure
  names the item and what is wrong; it exits 1 on any failure:
  - security: no hosted feature service in the group, nor any of its layers, allows Create, Update, Delete, Editing or
    Sync, and sync is off;
  - sharing: the group and every item in it are public, one item for each number (0 Read me first, 0 Dashboard,
    1a-1d, 2a-2d, 3a-3b, 4a-4o, a 5a and a 5b for each of the 13 quadrangles; `CODES` in the script);
  - links: every URL in the group's description, the items' descriptions, snippets, licenses and credits, and the
    dashboard answers 200, and every link to an item goes to a public item in the group with the title it names;
  - web map: every layer and basemap URL answers without an error and each layer's item is in the group;
  - dashboard: its JSON parses, its layout, data sources and actions name widgets and web map layers that exist, its
    map is the group's web map and it links every other item; no phone layout (`mobileView`) yet is only a note (#49);
  - figures, against the build's outputs in `target/work` (run by hand, `HSD_WORK` can point at another copy of them;
    `./build.sh` always sets it to `target/work`): the AVA polygon's area (0.01 sq mi), the 104
    steps and 105 points, the differences from the AVA Map Explorer polygon (pieces and acres by cause and side, each
    big difference's acres, 0.1 acre), the change near Grit (acres, granite, sandstone, 0.01 acre);
  - files: each uploaded file is the size of the one just built (and, up to 4 MB, downloaded and the same SHA-256),
    and the documents attached to the AVA polygon match the build's.

  Without build outputs the figures and files are skipped with a note. Right after a publish ArcGIS can take a minute to
  show a change to anonymous users: run `./build.sh check-live` again before chasing a failure.

The only prerequisites are Homebrew (https://brew.sh, on macOS or Linux), Google Chrome on Linux, and network access the
first time (packages and quads).

## Project layout

```
build.sh                 the build
requirements.in          the Python packages the build uses (edit this)
requirements.txt         compiled from it: every package and indirect dependency pinned, with SHA-256 hashes
requirements-dev.in/.txt the same for the lint, audit and lock tools
.pre-commit-config.yaml  the hooks; .githooks/pre-commit runs them; ruff.toml, .codespellrc, .secrets.baseline
README.md, BUILD.md      this documentation; CLAUDE.md: notes for Claude Code; LICENSE.txt
src/
  setup/                 packages.py: the security audit of the lock files (standard library only), lock helper
  quads/                 fetch_quads (the 13 USGS quads, MD5-checked), build_cropped_quads (neatline VRTs for viewing)
  tracing/               traces each "along the road / creek / contour" step onto the centre of the printed ink
  fixing/                hand patches: patchlib (making them) and apply_patches (splicing them onto the traces)
  review/                tipcheck (tips the line stops short of), compare_ttb (vs the AVA Map Explorer polygon),
                         grit_change (the change near Grit, acre by acre, with its granite), triage tools
  boundary/              ink_centerline (runs the tracer), build_agreed (pins, polygon, GIS), quad sheets, TTB record
  documents/             description, side-by-side, notice copy, DOCX, README / read-me-first, PDF text
  checks/                hard checks: quads vs manifest, every pin on its line, no self-crossing, valid polygon;
                         check_outputs: what reaches TTB (PDF fonts, compare text, figures, wording, GIS, zip paths)
  package/               make_package.sh (the zip)
  publish/               ArcGIS Online
resources/
  boundary/              what the boundary is built from (edit these, never the outputs); see resources/boundary/README.md
    description/         the step texts: TTB's Notice 243, the petition
    proposed/            the proposed ring (Oct. 15), the Oct. 14 step lines and points, the Grit detour pins
    tracing/             pin-moves.json, trace priors, route overrides, hand-patches-EPSG4269.geojson
  ttb/                   TTB's Notice 243 PDF, the AVAs_Production record and polygon snapshot
  geology/               USGS SGMC units shifted to the outcrops, for the map only; see resources/geology/README.md
  quads/                 quads-manifest.csv, cropped/ (neatline VRT templates); geotiff/ and geopdf/ are downloaded
documents/               hand-written texts: README.template.txt ({AREA_SQMI} filled by the build),
                         read-me-first.template.html
LICENSE.txt              CC0 1.0 (also copied into the package)
.venv/                   the project's Python environment (made by build.sh; not in git)
target/                  everything the build makes (not in git): work/ (recreated on every run), quads-cropped/
dist/                    the distribution (not in git)
tobedeleted/             set aside for review and deletion, used by nothing (not in git)
```

## The stages and the checks

1. **tools and .venv** - Homebrew GDAL / Python 3.14 / Chrome if missing; the security audit; `.venv` from the lock.
2. **quads** - the 13 quads checked against their MD5s in `quads-manifest.csv`; missing or altered ones downloaded.
3. **stage** - a fresh `target/work/`; the inputs are read in place from `resources/`.
4. **trace** - every follow step traced onto the ink (`src/boundary/ink_centerline.py`), pins from `tracing/pin-moves.json`,
   route hints from `tracing/route-overrides-EPSG4269.geojson`. Deterministic: two runs give identical lines.
5. **hand patches** - spliced onto the traces; a patch whose ends no longer lie on the trace stops the build (redo
   that patch). Patch joins that turn more than 25 degrees are rounded.
6. **boundary** - pins, straight-line steps, traced steps, polygon, points, GeoPackage, shapefiles.
7. **checks** - hard (stop the build): every one of the 105 pins exactly on its two steps; no step line crosses
   itself; the polygon is valid. Reports (in `target/work/review/`): tips of contours the line stops short of; where the
   proposed revision and the AVA Map Explorer polygon differ (rings beyond hand-drawing noise, the big differences 100 m
   or more apart, and every piece of land between the two lines); the change near Grit, line by line and acre by acre,
   with the granite in each piece (`src/review/grit_change.py`).
8. **documents**, 9. **quad sheets**, 10. **package** into `dist/`, with `build-report.txt`. Then hard checks on what
   reaches TTB (`src/checks/check_outputs.py`, output in `target/work/review/output-checks.txt` and the build report):
   every font embedded in the PDFs the build makes and none Mac-only (Helvetica Neue, Menlo); the notice copy (2a)
   with no AcroForm, /Perms, document XMP, signature or annotation but links; the two compare-text files differing in
   exactly the steps whose `change` in `agreed-steps.json` is not "unchanged", as the proposed text, and README.txt
   naming those steps; the area and README.md's figures equal to the build's statistics, rounded once, half up;
   no "agreed", "ours", "our boundary", "TTB's published polygon", "final text" or bare "Hickory Sandstone" in a
   generated document; every point's and step end's `quad` the quadrangle whose neatline holds it (the 7.5-minute
   NAD27 cell, through NADCON 5.0 CONUS), every `length_m` geodesic, every layer and `.prj` NAD83. A warning, not a
   failure: zip paths longer than Windows' 260-character limit when Explorer extracts the zip under
   `C:\Users\<name>\Downloads\` (Dan: leave the names for now).

## Python packages and security

`requirements.in` and `requirements-dev.in` name the packages; `./build.sh upgrade` compiles them (pip-compile) into
`requirements.txt` and `requirements-dev.txt`, with every package, every indirect dependency and pip itself pinned to the
latest compatible version and every downloadable file's SHA-256 recorded. Never edit the `.txt` files by hand.

Every build, before installing anything, sends every pinned version to the OSV vulnerability database (osv.dev: PyPA and
GitHub advisories, CVEs) with `src/setup/packages.py`, which uses only Python's standard library. Any known
vulnerability stops the build, naming the advisory, the CVE and the fixed version. When the lock files change, `.venv` is
recreated and filled only from them with `pip install --require-hashes`, so a download that does not match its recorded
hash is refused. Offline, a build continues only when `.venv` already holds exactly the audited lock.

Three indirect dependencies are held below their latest versions by Esri's `arcgis` package (latest 2.4.3): dask < 2025.3,
pyarrow < 24, puremagic < 2. They stay at the newest versions `arcgis` allows, and the audit covers them like every
other package. `GDAL` must equal Homebrew's GDAL library (`gdal-config --version`); the build stops if they differ.

## Commits: the pre-commit hooks

`./build.sh env` (and every build) installs the lint tools into `.venv` and points git at `.githooks/`, so every
`git commit` runs the hooks in `.pre-commit-config.yaml` on the staged files, all from `.venv` (nothing global):

- files: no files over 2 MB, no case clashes or names Windows cannot hold, no merge-conflict markers, no broken or
  replaced symlinks, no submodules, shebangs and executable bits agree, LF line endings, no trailing whitespace, one
  final newline, no byte-order marks, JSON/GeoJSON/YAML/TOML parse, permanent links to code;
- secrets and private material: no private keys; detect-secrets (passwords, tokens, API keys; the three known false
  alarms are recorded in `.secrets.baseline`); no word listed in `.private-words` (gitignored: put names that must
  never be committed there, one per line); the OSV audit whenever a requirements file changes;
- Python: parses, no debugger calls, literals not `list()`; ruff with the bug-finding rules in `ruff.toml`;
- shell: shellcheck (warnings and errors); spelling: codespell (`.codespellrc`).

Hooks that fix files (whitespace, newlines, line endings) stop the commit after fixing; `git add` the fixes and
commit again. Run them all with `./build.sh lint`.

## GitHub Actions and releases

Three workflows in `.github/workflows/`, every action pinned to a commit:

- **lint** (`lint.yml`, GitHub's Linux machines): every pre-commit hook on every file, on every pull request and every
  push to `main`. The lint tools come from `requirements-dev.txt`, audited first, as on the Mac.
- **build** (`build.yml`, GitHub's Linux machines): the whole `./build.sh` on pull requests that change what the build
  reads (`build.sh`, `src/`, `resources/`, `documents/`, the lock files) and by hand (Actions > build > Run workflow).
  Linux, not GitHub's Mac machines, whose minutes cost ten times as much (Dan, 2026-10-17). Homebrew on Linux installs
  the same versions of the tools as on the Mac (GDAL, PROJ with the NADCON5 grid, poppler, Python 3.14); the PDFs ask
  for Times New Roman, Arial and Courier New and get the Liberation fonts there, which have the same character widths,
  so lines and pages break in the same places. The 13 USGS quads are cached between runs (the build still checks their
  MD5s). It keeps the build report, the checksums and the GIS lines for 14 days, not the 290 MB zip.
- **release** (`release.yml`, Linux): push a tag such as `v2026.10.20` and it builds that commit and makes a GitHub
  release of the same name with `dist/` attached (the package zip, its README, `SHA256SUMS.txt`, `build-report.txt`).
  Run it by hand with an existing tag to rebuild that release's files.

```
git tag v2026.10.20 && git push origin v2026.10.20
```

Publishing to ArcGIS Online is not in Actions: it stays `./build.sh publish`, run by Dan. Changes only to `src/publish/`
do not start a build (that code never touches `dist/`).

The runners install whatever GDAL Homebrew has that day, and the build stops when it differs from the `GDAL==` pin in
the lock (the Python bindings must match the library). When Homebrew moves GDAL on, every build stops with that message
until the lock follows: `brew upgrade gdal`, then `./build.sh upgrade` on the Mac, in a pull request.

## Changing the boundary

Change only the inputs in `resources/boundary/` (a pin in `tracing/pin-moves.json`, a patch in
`tracing/hand-patches-EPSG4269.geojson`, a route hint in `tracing/route-overrides-EPSG4269.geojson`) or the step texts, then run `./build.sh`. The area and every figure in the
README and the ArcGIS descriptions come from the build, so nothing else needs editing by hand.
