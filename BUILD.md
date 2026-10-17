# Building the Hickory Sands District AVA package for TTB

One command, run from the repository root, rebuilds everything that goes to TTB from source. No manual steps:

```
./build.sh
```

It installs what is missing (GDAL, Python 3.14 and Google Chrome via Homebrew), checks every Python package it will
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
  layers (the boundary, the differences from TTB's polygon, the shifted geology), the web map over the 13 quads with
  TTB's live polygon, and the dashboard that links everything. It makes the folder if it is missing. It signs in with Dan's saved `arcgis` profile `hsd`. Publishing is never part of a normal build; run it only when
  you mean to update ArcGIS Online.

The only prerequisite is Homebrew (https://brew.sh) on macOS, and network access the first time (packages and quads).

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
  review/                tipcheck (tips the line stops short of), compare_ttb (vs TTB's published polygon), triage tools
  boundary/              ink_centerline (runs the tracer), build_agreed (pins, polygon, GIS), quad sheets, TTB record
  documents/             description, side-by-side, notice copy, DOCX, README / read-me-first, PDF text
  checks/                hard checks: quads vs manifest, every pin on its line, no self-crossing, valid polygon
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
tobedeleted/             set aside, used by nothing (not in git): the filed Oct. 13 public comment and its pipeline,
                         old scripts, the private .local folder. Review, then delete.
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
   itself; the polygon is valid. Reports (in `target/work/review/`): tips of contours the line stops short of; places
   where our boundary differs from TTB's published polygon by more than the hand-drawing noise.
8. **documents**, 9. **quad sheets**, 10. **package** into `dist/`, with `build-report.txt`.

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

## Changing the boundary

Change only the inputs in `resources/boundary/` (a pin in `tracing/pin-moves.json`, a patch in
`tracing/hand-patches-EPSG4269.geojson`, a route hint in `tracing/route-overrides-EPSG4269.geojson`) or the step texts, then run `./build.sh`. The area and every figure in the
README and the ArcGIS descriptions come from the build, so nothing else needs editing by hand.
