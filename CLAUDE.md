# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A GIS deliverable package, not an application: the Hickory Sands District AVA boundary
(TTB Notice No. 243, 91 FR 52576, Docket TTB-2026-0005), redrawn from scratch off the 13
USGS 1:24,000 historical quadrangles by following the NPRM's 96-step narrative. A git repo (branch main) published as danshome's GitHub repository;
`.local/` holds private material (correspondence, drafts, the filing kit) and is never committed.
README.md, DATA_SOURCES.md, and NOTES-interpretation-and-divergences.md are the authoritative
write-ups; read them before changing geometry or numbers.

Core invariant: **no geometry comes from an existing boundary layer.** TTB's published polygon,
the petition layer, and USGS TNM 3DEP contours are used only as search priors / routing hints
and for comparison stats. Every output coordinate is either a pin on a printed mark or a trace
of the sheet's ink.

## Layout

- `comparison/` – GeoJSON snapshots of TTB's published polygon and the petition's points/poly/polyline
  services (EPSG4269-NAD83). Priors and comparison only, never geometry sources.
- `layers/` – final deliverables, stored ONLY in NAD83 (`-EPSG4269-NAD83`, TTB's AVAs_Production CRS).
  Dan's rule (2026-10-11): the TIFFs are the only NAD27 data; never store layers in NAD27. QGIS shifts NAD83
  to the quads' NAD27 for display via the pinned NADCON5 grid. `gazetteer.csv` holds per-step endpoints
  (NAD83, `crs` column) and divergence notes.
- `narrative/` – the verbatim 96-step text (`nprm-steps.json`) and chord/follow classification
  (`nprm-step-kinds.json`).
- `quads_geotiff/` – each USGS GeoTIFF **kept inside its own zip on purpose** (bare TIFFs were
  corrupted in transfer and lost their GeoKeys). Do not unzip in place or rename; verify against
  md5s in `quads-manifest.csv`. `quads_geopdf/` holds the matching print GeoPDFs.
- `quads_cropped/` – 13 GDAL VRT templates (`*.vrt.in`, one per sheet; `scripts/build_cropped_quads.sh` writes the `*.vrt`, gitignored) that read the original GeoTIFFs straight from their zips and crop
  them to the 7.5-minute neatline (cutline stored inside each VRT, same 2.032 m grid, no resampling). Display only;
  the originals are untouched. The templates were made with gdalwarp -of VRT -cutline <neatline WKT> -cutline_srs EPSG:4267 -crop_to_cutline -dstalpha.
- `qgis_projects/` – two `.qgs` files (QGIS 4.2 format, relative paths) that read the GeoTIFFs
  via `/vsizip/../quads_geotiff/<name>.zip/<name>`. The NAD83 project pins the NADCON5 CONUS
  transform and also loads TTB's live feature service.
- `public-comment/` – the filed comment and Attachment 1 (Markdown sources), `docket-attachments/` (the 10 GIS layers filed
  as Attachment 2, exactly as filed; never edit), the Exhibit B source image, and `agol-metadata/metadata.json`.
- `data/` – snapshots for the exhibits (OpenStreetMap extract, TTB San Pasqual Valley feature), retrieved 2026-10-12.
- `build/` (gitignored) – everything `make build` produces. Old renders (`print/`, `maps/`) are in `.local/outputs-old/`.
- `code/` – the pipeline (below).

## Code architecture

Pure Python 3 with numpy, Pillow, matplotlib only — no GDAL/pyproj/shapely. Projection math,
shapefile writing, and tracing are all hand-rolled:

- `quadlib.py` – quad registry and `Quad` class: reads each GeoTIFF's GeoKeys and implements
  NAD27/Clarke 1866 polyconic forward/inverse (`pix(lon,lat)`, `lonlat_of_pix(c,r)`); also
  `render_map` with the shared boundary style (`BOUND_COLOR` cased magenta dash). Running it
  directly is the self-test: `python3 quadlib.py` prints round-trip pixel error per quad.
- `tracelib.py` – the digitizer: ink-color classification calibrated to these scans, ray probes,
  Dijkstra least-cost ink following with full-res corridor refinement, despurring, RDP + Chaikin.
- `shplib.py` – minimal shapefile writer (polyline/polygon/point + .prj).
- Final-pass stages: `build_contours2.py` (contour layer) → `assemble.py` (gazetteer + step
  texts + traced segments → boundary steps/polygon/points, NAD27 + shifted) → `make_nad83.py`
  (NAD83 GeoJSON + shapefile zips) → `print_page.py` (one quad page).
- Earlier-stage scripts, `ringlib.py`, `fetch_fresh_quads.py` and `make_qgis_projects.py` were moved to
  `.local/code-earlier/` (not in the repository). Quads are fetched with `scripts/fetch_quads.py`.
- `scripts/` holds the repository build: `fetch_quads.py`, `fetch_sources.py`, `build_cropped_quads.sh`,
  `build_all.sh` (exhibits, thumbnails, PDFs, shapefiles and the UC Davis AVA Project record into `build/`), `stage_filing.sh`.

## Running the pipeline

Scripts use CWD-relative `data/` and `out/` paths and are run from `code/`; `quadlib.QUAD_DIR`
is `code/data/quads/` and globs bare `*.tif` (it does not read the zips). README's rerun recipe:

```
cd code
# unzip the 13 GeoTIFFs from ../quads_geotiff/ into code/data/quads/ (copies, not in place)
python3 -I build_contours2.py && python3 -I assemble.py && python3 -I make_nad83.py
```

Caveat: `data/` and `out/` are **not in this package**. Besides the quads, the stages need
intermediates that weren't shipped: `out/trace/gaz.csv` and `out/trace/seg_s*.json` (traced
segments), `data/nprm-steps.json` / `data/nprm-step-kinds.json` (copies of `narrative/`),
`data/tnm/*.json` (TNM contour hints), and `data/ttb_poly.geojson` / `data/rcv_poly.geojson`
(comparison rings). Script output names (e.g. `out/...-nad27.geojson`, `...-steps.geojson`)
also differ from the renamed files in `layers/`. So a full rebuild is not currently possible
from this folder alone; `quadlib.py`'s self-test is.

## Datum and numbers to keep consistent

- NAD27 → NAD83(1986): the NADCON 5.0 CONUS grid (us_noaa_nadcon5_nad27_nad83_1986_conus.tif), point by point (since 2026-10-11).
  Layers are stored and edited in NAD83 only. Anything measured on a scan in NAD27 is converted to NAD83 with that grid
  before it is written; the QGIS projects pin the same grid (4267↔4269, 3857→4267, 4326→4267), so NAD83 displays back on
  the ink to <0.1 m. The old uniform constant (dLon −0.0003381665, dLat +0.0001778510) remains only in old pipeline
  scripts (which also write NAD27 out/ files) and must not be used for layers/.
- Working convention with Dan: red = petition (PostGIS copies), green = layer drawn from the NPRM, blue = TTB.
  Red and green are stored in NAD83 (EPSG:4269) like TTB; QGIS shifts them to NAD27 to match the quads.
- Headline figures, GRS80 ellipsoidal area (what the comment quotes and `scripts/check.sh` verifies): 96 steps,
  proposed text 198.07 sq mi, petition routing 193.79, TTB published polygon 197.63; boundary length 308.7 km
  (sum of step `length_m`). Dated history lines (containing `->`) in NOTES keep their old figures.
  If geometry changes, update README, DATA_SOURCES, NOTES, and layer properties together.
- macOS forbids `:` in filenames, so EPSG codes are written `EPSG4269`, not `EPSG:4269`.

## Build and checks

`make fetch` (quads + docket PDFs), `make quads` (cropped GeoTIFFs, needs GDAL), `make build` (exhibits, thumbnails,
PDFs, shapefiles into `build/`), `make geology` (USGS SGMC units + 3DEP 1,500 ft layer into `build/geology/`; all three SGMC units shifted by SGMC_SHIFT, about 400 m north-west (225 m W, 331 m N), to match NAIP imagery, per Dan; SGMC is misregistered here; DEM not shifted), `make check` (read-only: layer fingerprints, NAD83/region/ring sanity, area figures in
every doc vs the layers, quadlib self-test, filed PDFs vs latest build), `make stage` (copy into `.local/filing/`).
After a deliberate layer edit, re-record fingerprints with `scripts/check.sh --record`. In this shell `grep` is a
wrapper function; for secret or privacy scans use `git grep` or `/usr/bin/grep`.

## Live QGIS (MCP)

A running QGIS desktop can be driven directly through the `qgis` MCP server (`mcp__qgis__*`
tools: load projects, add/inspect layers, query features, render the canvas, export layouts).

- Setup: the `qgis_mcp_plugin` QGIS plugin, installed in the QGIS 4 profile
  (`~/Library/Application Support/QGIS/QGIS4/profiles/default/`), plus the `qgis` MCP server
  registered at user scope in Claude Code (`uvx ... qgis-mcp-server` from nkarasiak/qgis-mcp).
  Verified against QGIS 4.2.3.
- QGIS must be open with the plugin's server started; check with `mcp__qgis__ping` first.
- The `.qgs` files in `qgis_projects/` were upgraded to QGIS 4.2.3 format on 2026-10-11 (open them
  with QGIS 4.x, not 3.x). Saving writes a `.qgs~` backup (previous version, disposable) and an
  `_attachments.zip` (auxiliary styles DB, must stay beside the project). After any re-save, confirm the
  datasources are still relative (`/vsizip/../quads_geotiff/...`, `../layers/...`) and the NAD83
  project still carries its NADCON5 `transformContext` pins.
- NAD83 project transforms: the quads are in five custom NAD27 polyconic CRSs (no EPSG code;
  `lon_0` = −98.938, −99.063, −99.188, −99.313, −99.438), and QGIS pins transforms per exact CRS
  pair, so there are six pins: EPSG:4267→4269 plus one per polyconic CRS, all using
  `us_noaa_nadcon5_nad27_nad83_1986_conus.tif`. If a "select transformation" dialog appears
  when adding quads, choose NADCON5 *CONUS*; the defaults it offers include the Alaska and Canadian
  (`ca_nrc_ntv2_0`) grids, which are wrong here.
- Use QGIS for viewing/QA and comparison only. Deliverable geometry still comes from the Python
  pipeline (core invariant above); don't edit features in `layers/` through the MCP tools.
