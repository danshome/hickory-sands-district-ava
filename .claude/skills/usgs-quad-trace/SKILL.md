---
name: usgs-quad-trace
description: Trace roads, highways, creeks and contour lines on scanned USGS topographic quadrangles (historical topoView/HTMC GeoTIFFs, 1:24,000 and similar) onto the exact centre of the printed ink, between fixed endpoints, and PROVE it with numbers and review sheets. Use this whenever linework must "follow" a feature shown on a USGS quad -- AVA or other legal boundary descriptions that run "along" a road, creek or contour, digitizing or correcting GIS lines against quad ink, checking whether an existing line sits on the map's ink, or when someone says a line cuts corners, rides the edge of a road, misses a creek's bends, or is "off the ink". Handles NAD27 sheets (NADCON 5.0), neatlines and sheet edges, woodland tint, dashed/dotted symbols, lettering over features, double-line roads and red-fill highways. Also use it to review traced lines with a problem finder and reviewer agents.
---

> Since Oct. 16, 2026 the scripts live in the project's `src/` (built by `./build.sh`, see BUILD.md); paths below are relative to the repository root.

# usgs-quad-trace

Put a line on the centre of a feature's printed ink on scanned USGS quads, and show that it is there.

Why this exists: lines digitized "along" a road or creek by eye, or by a tracer that treats any ink pixel as equally
good, ride one edge of a symbol and cut across bends -- 10-30 m on creeks, several metres on roads. On a legal
boundary that is the difference between a parcel being in or out. The method here was built and tested on 28 real
boundary steps (Hickory Sands District AVA, 13 Texas 1:24,000 sheets, 1955-70): creeks and contours reach 98-99.8%
of their length within 2 m of the ink's centre.

## What you need

- The quads as GeoTIFFs (bare or inside their topoView .zip -- read in place, never unzip or rename them).
- An approximate line (the "prior") per feature, NAD83 lon/lat GeoJSON, whose FIRST and LAST points are the fixed
  endpoints (pins: marks on the sheet, intersections). The prior only needs to be on the right feature; the trace
  stays within a corridor of it (roads 50 m, creeks 120 m, contours 30 m).
- Each feature's kind: `road` (any road or highway symbol), `creek`, or `contour`.
- Python with GDAL/OSR, numpy, scipy, Pillow; PROJ able to find `us_noaa_nadcon5_nad27_nad83_1986_conus.tif`.

## Workflow

1. **Trace** -- `src/tracing/centerline.py --quads "<glob>" --lines prior.geojson --out traced.geojson [--ids ...]`
   One LineString per feature with the check's figures as properties. Pins are kept exactly.
2. **Review sheets** -- `src/tracing/review.py --quads ... --traced traced.geojson --prior prior.geojson
   --title-field <field> --out-dir review/` : one PNG per line, the whole line plus close-ups of its worst spots.
   Point the person at this folder; they watch it while you work.
3. **Find problems** -- `src/tracing/problems.py --quads ... --traced ... --prior ... --out-dir review/problems/` :
   close-ups of every suspect spot (worst first per type) plus random controls, and `problems.json`.
4. **Critic pass** -- split `problems.json` into batches and give each to a reviewer agent with
   `references/review-rubric.md`; each returns JSON labels (purple centred/near/off, better line, cause). Tally the
   causes. A reviewer is a second opinion, not ground truth: reviewers are right roughly 3 times in 4 on map
   judgements, so check a sample yourself and believe numbers + pictures together.
5. **Fix the cause, not the spot** -- change the ink classes (`src/tracing/ink.py`, check them with `src/tracing/inkcheck.py`)
   or the tracer parameters, re-run ALL lines, and compare per line: nothing that passed may get worse. Keep the
   labelled spots as regression cases.
6. **Hand over** -- the traced lines plus the numbers per line and the review sheets. Endpoints more than 2 m off a
   centreline are listed for the person to decide; never move a pin silently.

## The check (what "on the ink" means)

`grade()` in centerline.py, deliberately independent of the tracing: on the raw ink (no gap closing), across the
line every metre --
- an ink run each side, 3-20 m apart, both thin -> their midpoint (double-line road);
- one wide run straddling the line -> its middle (red-fill highway);
- creeks, contours, single-line roads -> the nearest run within 6 m.
Anything else (junction, lettering, a missing edge) is *unmeasured*, not failed. Report per line: share measured,
off-centre median and 95th percentile, share within 2 m, stretches > 2 m off, gaps, largest move from the prior,
pin offsets. Never grade a line with the same measurement that moved it -- that was the first mistake made here.

## What these scans do (read before changing ink.py)

See `references/ink-colors.md` for the measured values and `references/method.md` for the algorithm and the
dead ends. The short version:
- Classify ink by each pixel's ratio to its LOCAL background (paper or woodland tint), not by absolute colour: the
  tint's shade varies between sheets and within one, and fixed thresholds mistake dark tint for road ink.
- "Warmth" (red-ratio minus blue-ratio, divided by darkness) separates blue (< -0.22), black/gray (|w| < 0.22) and
  brown (> 0.22) whether the ink is faint or heavy.
- Woodland tint seen against paper keeps green near 0.97 of the paper; every ink darkens green below ~0.8.
- Creek ink over the tint can print as near-neutral teal: keep it by "green lighter than red".
- Heavy black is lettering: never creek or contour ink, so a trace bridges straight across a label.
- Read each point from the sheet whose neatline holds it; ignore 2.5 m around neatlines.
- A lone line is symmetric about itself: choose a road's centre by ink paired with its mirror (both edges), not by
  symmetry alone, or the line jumps between the centre and one edge.
