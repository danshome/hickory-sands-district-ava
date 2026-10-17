# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

The Hickory Sands District AVA boundary as proposed to TTB (Docket TTB-2026-0005, Notice No. 243, 91 FR 52576): TTB's
published description with the changes discussed with TTB on Oct. 15, 2026, drawn onto the 13 USGS 1:24,000 historical
quadrangles and packaged for TTB. A git repo (branch main) published as danshome's GitHub repository. Say "proposed",
never "agreed". The Oct. 13 public comment is filed and public; its pipeline is finished and set aside in `tobedeleted/`.

Core invariant: **no geometry comes from an existing boundary layer.** TTB's published polygon, the petition layers and
TNM contours may be looked at (priors, routing hints, comparison), never copied. Every coordinate is a pin on a printed
mark or junction, a straight line between pins, or a trace of the centre of the printed ink.

## Build: `./build.sh` -> `dist/` (see BUILD.md)

One command from the root, no manual steps: it installs missing tools with Homebrew (GDAL, python@3.14, Chrome), audits
every pinned Python package against OSV before installing anything (`src/setup/packages.py`), makes the project's `.venv`
from the hash-pinned lock `requirements.txt` (compiled from `requirements.in` by `./build.sh upgrade`; never edit the
`.txt` by hand; all Python runs in `.venv`, `-E -s -B`; nothing global), downloads/verifies the
13 quads, then stages, traces, splices patches, builds the boundary, checks, makes the documents and quad sheets, and
zips the package into `dist/` with `SHA256SUMS.txt` and `build-report.txt`. `./build.sh clean | distclean | env | lint | audit | upgrade | publish`.

- `src/` all code: `quads/`, `tracing/` (the ink tracer), `fixing/` (patchlib, apply_patches), `review/` (tipcheck,
  compare_ttb), `boundary/` (ink_centerline, build_agreed, quad sheets, TTB record), `documents/`, `checks/`,
  `package/`, `publish/` (ArcGIS Online).
- `resources/` the inputs: `boundary/` (`description/` step texts, `proposed/` ring and Oct. 14 step lines/points and
  Grit detour pins, `tracing/` pin-moves, trace priors, route overrides, hand patches; see its README.md),
  `ttb/` (Notice 243 PDF, AVAs_Production record and polygon snapshot), `geology/` (USGS SGMC units shifted ~400 m to
  the outcrops, map context only), `quads/` (`quads-manifest.csv`, `cropped/`
  VRT templates; `geotiff/` zips and `geopdf/` are downloaded, gitignored; keep each GeoTIFF inside its zip).
- `documents/` README and read-me-first templates (figures filled by the build); `LICENSE.txt` (CC0) at the root.
- `target/` (gitignored) everything the build makes: `work/` (recreated each run; GIS in `work/gis/`, reviews in
  `work/review/`), `quads-cropped/` (neatline VRTs for QGIS). `dist/` (gitignored) the distribution.
- `tobedeleted/` (gitignored) is where things no build uses go for Dan to review and delete. Nothing may depend on it.

Change the boundary only through `resources/boundary/` and rebuild; never edit outputs. Hard checks stop the build:
quads vs manifest, every pin exactly on its two steps, no step line crossing itself, valid polygon. Current build:
104 steps, 105 pins, 193.83 sq mi (GRS 1980); the figures in the README and ArcGIS descriptions come from the build.

Commits run the pre-commit hooks (`.pre-commit-config.yaml`, tools from `requirements-dev.txt` in `.venv`, via
`.githooks/pre-commit`; `./build.sh lint` runs them all): file hygiene, JSON/YAML/TOML, detect-secrets, a
private-words check against the gitignored `.private-words`, ruff (`ruff.toml`), shellcheck, codespell.

Rules: `./build.sh publish` (ArcGIS Online) is outward-facing, only on Dan's explicit say-so. Commit only with Dan's OK,
on a new branch unless he says main. Never commit `tobedeleted/` or private material.

## Datum

- Layers are stored in NAD83 (EPSG:4269, TTB's AVAs_Production CRS). The quads are the only NAD27 data. Anything measured
  on a scan in NAD27 goes to NAD83 point by point with the NADCON 5.0 CONUS grid
  (us_noaa_nadcon5_nad27_nad83_1986_conus.tif); never the old uniform shift constant.
- macOS forbids `:` in filenames, so EPSG codes are written `EPSG4269`.
- Colours with Dan: red = petition, green/ours = drawn from the description, blue = TTB.

## Skills

`.claude/skills/usgs-quad-trace/` (ink-centreline tracing; read its SKILL.md and `references/method.md`,
`references/ink-colors.md` before touching any "follow a road/creek/contour" geometry), `usgs-quad-review/` (finds bad
spots), `usgs-quad-fix/` (patches on the ink), `ttb-boundary-compare/` (rings where ours differs from TTB's polygon beyond
hand-drawing noise). Their code now lives in `src/` (tracing, fixing, review). `~/.claude/skills/usgs-quad-trace` is a
symlink to the committed skill. In this shell `grep` is a wrapper function; for exact or privacy scans use
`/usr/bin/grep` or `git grep`.

## Live QGIS (MCP)

QGIS 4.2.3 can be driven through the `qgis` MCP server (`mcp__qgis__*`; check `mcp__qgis__ping` first). For viewing and
QA only: never edit deliverable features through it. Load ours from `target/work/gis/*.gpkg`, TTB's live layer
(`arcgisfeatureserver`, AVAs_Production FeatureServer/0, subset `Name = 'Hickory Sands District'`), and the quads from
`target/quads-cropped/*.vrt`. The quads are in five custom NAD27 polyconic CRSs; pin NAD27->NAD83 to the NADCON5 *CONUS*
grid (not the Alaska or Canadian grids QGIS offers). Do not render online tile layers off-screen through MCP (it crashed
QGIS); let the canvas draw them. Don't save over a project without Dan's OK.
