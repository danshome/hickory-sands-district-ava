# resources/boundary: what the boundary is built from

These files are the inputs. To change the boundary, change them and run `./build.sh`; never edit the build's outputs.
All coordinates are NAD83 (EPSG:4269), longitude first.

## description/ - the words the boundary follows

| file | what it is | read by |
|---|---|---|
| `ttb-notice-243-steps.json` | TTB's 96 steps word for word, from the Federal Register's full-text XML of Notice No. 243 (kept as `resources/ttb/federal-register-2026-16670-full-text.xml`; `src/checks/check_step_text.py` holds them identical, character for character, on every commit and build) | boundary, description, side-by-side, notice copy |
| `petition-steps.json` | the petition's steps used for the proposed Grit wording | boundary, description |
| `petition-steps-docket.json` | the petition's description as filed in the docket | side-by-side |

## proposed/ - the proposed boundary (Oct. 14-15, 2026)

| file | what it is | read by |
|---|---|---|
| `proposed-ring.json` | the proposed ring of Oct. 15 (TTB's text with the changes discussed with TTB), with the two highway lanes | boundary |
| `step-lines-2026-10-14-EPSG4269.geojson` | the Oct. 14 per-step lines; the build takes each step's attributes from it | boundary |
| `step-points-2026-10-14-EPSG4269.geojson` | the Oct. 14 numbered points (pin records) | boundary |
| `grit-detour-pins.json` | the Grit detour pins measured on the scan: windmill, points C and D, Topaz Lane from C to D | boundary |
| `western-routing-points-EPSG4269.geojson` | the petition's western routing points (used where the proposed text follows the petition) | boundary |

## tracing/ - putting the lines on the printed ink

| file | what it is | read by |
|---|---|---|
| `pin-moves.json` | every pin moved onto the centre of a printed junction or mark: old, new, metres moved, method, reason | tracer, boundary |
| `trace-priors-EPSG4269.geojson` | each "follow" step's rough route, which the tracer searches along (never copied) | tracer |
| `route-overrides-EPSG4269.geojson` | route hints that replace a step's prior (steps 72-73 on the light-duty road) | tracer |
| `hand-patches-EPSG4269.geojson` | 65 hand fixes on the ink, one line per stretch, each with its step, spot, method, reason and time | patches |
