---
name: ttb-boundary-compare
description: Validate our AVA boundary against TTB's published polygon (AVAs_Production feature service or a snapshot) and ring every place where the two differ by more than the everyday hand-drawn-vs-ink difference, for a look in QGIS. Use after any boundary rebuild, before filing or publishing, or when asked how ours compares with TTB's layer.
---

> Since Oct. 16, 2026 the scripts live in the project's `src/` (built by `./build.sh`, see BUILD.md); paths below are relative to the repository root.

# ttb-boundary-compare: where ours differs from TTB's layer by more than hand-drawing

Built Oct. 16, 2026 for the Hickory Sands District filing (Dan: "anything on ours that is different more than the normal
hand drawn vs our perfect lines, I want circled to look at"). TTB's polygon was digitized by hand; ours follows the centre
of the printed ink (usgs-quad-trace / -review / -fix), so the two differ a little everywhere. This skill measures that
everyday difference from the data and rings only what is beyond it.

## Run (the project `.venv`, `-E -s -B`; ~1 min; `./build.sh` runs it against the snapshot)
```
compare_ttb.py --ours-line gis/<...>-line-EPSG4269.geojson --ours-area gis/<...>-area-EPSG4269.geojson \
   --ttb-url https://services7.arcgis.com/ykuAbKu9MbV93nAe/ArcGIS/rest/services/AVAs_Production/FeatureServer/0 \
   --ttb-name "Hickory Sands District" --steps proposed-steps.json --out-dir review-ttb
```
(or `--ttb resources/ttb/ttb-avas-production-hickory-sands-district-EPSG4269-NAD83.geojson` for the snapshot, offline).
Script: `src/review/compare_ttb.py`. The live query is read-only (`/query?where=Name=...&outSR=4269&f=geojson`).

## Method
1. Both boundaries sampled every 2 m (ours keeps each sample's step number), in NAD83 / Conus Albers (EPSG:5070) metres.
2. Distance from every sample of each boundary to the other boundary (KD-tree), both ways, so an excursion on either side
   is caught (a narrow TTB spike is near ours at its base; only TTB->ours sees it).
3. Everyday difference = median and MAD of all those distances; threshold = median + K x MAD (default K 4), never below
   15 m (`--k`, `--min-threshold`, or a fixed `--threshold`). The run prints how many stretches K = 3..6 would give.
4. Stretches beyond the threshold (gaps under 30 m bridged) are found on both boundaries and paired EXACTLY: a TTB-side
   stretch joins the ours-side stretch its nearest-ours samples fall in. Unpaired stretches join a neighbour only within
   min(max-apart, 100 m) + 60 m, so one big intended change (a lobe) cannot swallow a real difference next to it.
5. Each place: a circle (short) or an outline 40 m round both lines (long stretches); our steps involved; max distance
   apart; length; acres in the proposed revision only / in the Map Explorer polygon only (symmetric difference inside
   the ring); kind (straight line / follows a feature,
   from the step text); each pin's distance to TTB's nearest vertex (a straight-line step moves whole when its pin
   differs); status = "intended: <change>" only when EVERY step in it is changed in the register (proposed-steps.json
   `change` not starting "unchanged"), "CHECK (steps .. unchanged; partly intended: ..)" when mixed, else **CHECK**.

## Outputs (`--out-dir`)
- `ttb-diff-rings-EPSG4269.geojson`: one polygon per place; fields n, steps, max_apart_m, length_m, ours_adds_acres,
  ours_drops_acres, kind, pins, found_from (ours / ttb / both), status, label (`#n s<steps> <m>m CHECK|intended`).
- `ttb-diff-report.md` (table with lon/lat), `ttb-diff-stats.json` (threshold, percentiles, K sweep, areas).

## In QGIS
Load the rings above everything; rule-based style: red outline where `"status" LIKE 'CHECK%'`, grey otherwise; label field
`label`. Add TTB's live layer for context (`arcgisfeatureserver`, `crs='EPSG:4269' url='.../AVAs_Production/FeatureServer/0'`,
subset `Name = 'Hickory Sands District'`, blue outline). Look at every red ring: either the step's change register is
missing an entry (then add it), a pin or route differs from TTB's reading (raise it with the owner), or our line is wrong.

## Notes
- Do not render online tile layers off-screen from the MCP (QgsMapRendererParallelJob on an XYZ layer crashed QGIS on
  Oct. 16); let the canvas draw them.
- "intended" only means the step's TEXT was changed on purpose; still look at its geometry if the acres are surprising.
- Straight-line steps magnify pin differences: a pin 100 m from TTB's vertex shifts the whole chord.
- Areas here are Albers planar (within ~0.1% of GRS80 for this size); the headline figures stay GRS80 (build_proposed.py, in build-report.txt).
