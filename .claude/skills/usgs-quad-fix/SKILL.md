---
name: usgs-quad-fix
description: Hand-fix flagged stretches of traced lines (contours, creeks, roads) on scanned USGS quads using agents. Use after usgs-quad-trace + featurecheck + a triage pass have produced a fix list; each agent places patch lines on the centre of the printed ink, looks at a render of every patch, and writes patches that apply_patches.py splices into the traces with provenance.
---

> Since Oct. 16, 2026 the scripts live in the project's `src/` (built by `./build.sh`, see BUILD.md); paths below are relative to the repository root.

# usgs-quad-fix: agents hand-fix the flagged spots

Built Oct. 16, 2026 for the Hickory Sands District filing, when 83 spots needed a hand fix before a 2 PM deadline
(Dan: "get agents to manually fix them all"). Pipeline: **usgs-quad-trace** traces -> **usgs-quad-review** finds
and marks the bad spots (featurecheck.py + triage agents -> FIX-LIST) -> **usgs-quad-fix** (this) has agents fix
every marked spot. Input: the FIX-LIST from usgs-quad-review.

## The rule
A patch replaces one stretch of one step. Its two ends lie ON the frozen trace (within 0.5 m; `apply_patches.py`
checks) and more than 12 m from the step's ends (the pins; build_proposed.py ties the last 12 m straight). Its interior
follows the CENTRE of the printed ink, or crosses a label / dot gap straight. No geometry from any boundary layer (TTB,
petition, prior, TNM): the prior may be LOOKED AT, never copied.

## Orchestration (main session)
1. Freeze the traces (copy `ink-centerline-steps.geojson`); no re-trace after patching starts.
2. Split the fix list BY STEP so no two agents touch the same line (overlapping patches are rejected). ~10-15
   spots per agent.
3. Each agent gets: its items file (item, step, lon, lat, problem, offset_m, note, crop), an output GeoJSON path,
   a render folder, a deadline. Brief below.
4. Merge: append the agents' features to `resources/boundary/tracing/hand-patches-EPSG4269.geojson` (the one patch
   file the build reads) and run `./build.sh`; apply_patches.py writes `target/work/ink-centerline-steps-patched.geojson`,
   which build_proposed.py reads.
5. Check: featurecheck.py on a copy of the patched file; a reviewer agent (or the owner) looks at a sample of the
   agents' renders. Rebuild.

## Per-spot recipe (agent), with src/fixing/patchlib.py
```python
import sys; sys.path.insert(0, "/Volumes/CALL5126338086/Hickory Sands District AVA (Claude)/src/fixing")
import patchlib as P
T = P.Trace()                                  # frozen traces
s = T.nearest_s(step, lon, lat)                # the spot along the step (the triage point can be tens of m off the defect)
g = P.Grid(T, step, s - 100, s + 100)          # 1 m ink grid; g.ink = this step's class, g.m["brown"/"black"/"blue"/...]
P.render(g, P.straight(T, step, s - 40, s + 40), "look.png", s - 80, s + 80)   # LOOK FIRST (Read the png)
```
Then choose, per problem:
- **label_loop / label_spike** (line wanders through digits): `P.straight(T, step, sa, sb)` with sa/sb on the
  contour's own ink just outside the label -- the straight crossing through the middle of the digits.
- **corner_cut** (V tip / bend cut): `P.follow(g, sa, sb, ink=g.m["brown"] | g.ink, via=[g.ll(x_apex, y_apex)])`
  -- read the apex in the render's metres (both panels share the grid's coordinates).
- **off_centre / one_edge / wobble / hop / onto_contour / off_creek**: `P.follow(g, sa, sb)` on the right class
  (creeks: `ink=g.m["blue"] | g.ink`; contours: `g.ink`), with `via` points to pin it to the right line; roads:
  `P.road_centre(g, sa, sb)` (midway between the casings, step's road width) or `P.polyline(T, step, sa, sb, via)`
  with via points you place midway between the two edges you see.
- Render the candidate, READ the png, adjust (sa/sb, via, ink) until the orange line sits on the ink centre and
  joins the purple trace on good ink at both ends. 2-4 iterations is normal; do not save what you have not looked at.
- `P.save(OUT, step, item, line, method, reason)` (refuses pin-zone ends); one patch per continuous stretch: two
  items on the same stretch become ONE patch (save it under one item id, note the other in `reason`).
- `P.validate(OUT)` after every few saves (apply_patches dry run on your file alone).
- If a spot is fine on a closer look: do not patch; report it "ok on inspection". If a fix needs a pin moved or is
  within 12 m of a pin: do not patch; report it.

## Dead ends
- QGIS AutoTracer (needs cv2/skimage, grey threshold merges colours), GRASS (not installed): see usgs-quad-trace.
- A flat label cost in the tracer did not fix labels whose digits ink.py does not detect -- hence these patches.
