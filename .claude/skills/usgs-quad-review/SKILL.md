---
name: usgs-quad-review
description: Find and mark the bad spots in lines traced on scanned USGS quads (usgs-quad-trace output). Runs the independent acceptance check (featurecheck.py), has reviewer agents judge every flagged close-up against a per-kind rubric, and builds a numbered fix list (red rings) for QGIS. Use after any (re)trace and before hand-fixing; feed its fix list to usgs-quad-fix.
---

> Since Oct. 16, 2026 the scripts live in the project's `src/` (built by `./build.sh`, see BUILD.md); paths below are relative to the repository root.

# usgs-quad-review: find and mark the bad spots

Three skills, one pipeline: **usgs-quad-trace** traces -> **usgs-quad-review** (this) finds and marks what is wrong ->
**usgs-quad-fix** has agents fix every marked spot. Built Oct. 16, 2026 for the Hickory Sands District filing.

## Why not the old number
grade() (centerline.py) only asks "is ink of the feature's class within 6 m": a line on the NEIGHBOURING contour, or
riding a digit's stroke, scores as centred, and ambiguous metres are left out of the figure. It said 98-99.8% for
contours that visibly hopped. Report featurecheck's VERIFIED %, and count unmeasured as not verified (Dan's rule).

## Steps
1. **Freeze** the traced file (copy it); review the copy.
2. **Check** (the project `.venv`, `-B -E -s`; ~75 s for 5 contours, ~60 s for 22 roads/creeks):
   ```
   featurecheck.py --quads "<quads glob>" --traced COPY.geojson --prior PRIORS.geojson --out-dir OUT [--ids ...]
   ```
   (script: `src/tracing/featurecheck.py`). Outputs: `per_step.csv` (VERIFIED / FLAGGED /
   UNMEASURED, wrong-line metres), `queue.geojson` (clustered items, priority 0 known blind spot / 1 identity / 2
   shape / 3 unmeasured), `crops/*.png`. Contours are validated; creeks and roads are marked "unvalidated" (the
   detector over-flags them) but triage still works on them.
3. **Split** the queue for reviewers: `src/review/split_queue.py --out-dir TRIAGE OUT/queue.geojson [...]`
   (~60 items per batch, kinds separate).
4. **Triage** with one reviewer agent per batch, in parallel, using the brief for its kind in
   `references/triage-rubric.md`. Each writes `TRIAGE/verdicts-<K>.json`. ~10-18 min per 60 items.
5. **Mark**: `src/review/merge_verdicts.py TRIAGE` -> `FIX-LIST-EPSG4269.geojson` (fix + unsure items, numbered in
   boundary order). Load it in QGIS as red rings labelled `#n s<step> <problem> <offset>m` (expression label).
   Re-run it as batches finish; reload the layer with `dataProvider().reloadData()`.
6. Hand the fix list to **usgs-quad-fix**. Unsure items and anything about a PIN (a step end) go to the owner.

## Rules
- Reviewers are fresh agents given the rubric and the crops, not the tracer's reasoning (no anchoring).
- Never re-grade in place (regrade.py rewrites its input); one grader version for every figure you compare.
- Compare against a FIXED reference (the frozen copy), not "the previous run".
