# Method: centreline tracing on scanned quads, and what did not work

Built Oct. 15, 2026 on 28 boundary steps of the Hickory Sands District AVA (13 Texas 1:24,000 sheets). Numbers
below are from that set.

## Pipeline (src/tracing/centerline.py)

1. **Frame.** A local metric frame (m east/north of the prior's centroid) at 1 m cells; the prior rasterised with
   its bearing and its arc length per cell; distance-to-prior (EDT) and nearest-prior-cell indices.
2. **Ink.** Each corridor cell samples the sheet whose neatline holds it (`quadsheets.py`: NADCON 5.0 to NAD27,
   then the sheet's polyconic). Cells within 2.5 m of a neatline are no ink.
3. **Dotted creeks.** `chain_dots`: from each end of each solid stretch, hop along the direction of travel to the
   nearest dot or aligned dash (shape-based, from any non-brown ink), update the direction, repeat; a chain counts if
   it has >= 2 pieces or ends in the cone of another solid stretch. Direction at a short stub comes from the prior's
   bearing.
4. **Band.** Dash gaps closed along the prior's direction (roads 20 m, contours 5 m); the ink grown (roads 4 m,
   others 1.5 m) so a road's two edges merge; EDT inside the band and its local maximum = the medial ridge.
5. **Cost.** On the band: 1 + 4 (ridge - edt)^2, capped so anywhere on the band beats a gap. Off the band:
   20 + min(d_out, 20)^2. Plus (d_prior / pull)^2 (roads 25 m, creeks 30 m, contours 20 m).
6. **Path.** Dijkstra over the corridor cells (scipy.sparse.csgraph), 8-neighbour. No edge may join two cells whose
   nearest prior points are > 150 m apart along the prior: that is what stops a contour's loop being cut at its neck.
7. **Roads.** The smoothed path is moved onto the road's centre read from cross-sections every metre on the RAW
   ink (`edge_offsets`, three passes): the road's width is measured once per step (median separation of casing
   pairs 3.5-20 m apart); at each section the centre is the midpoint of both casings where both show, or one casing
   plus half the width where the other's dash is missing (this is what stopped the line bouncing between the
   casings of dashed roads); where no casing pairs exist along the step (a red-filled highway) a 3-9 m run
   straddling the line gives the centre; single-line roads fall back to the centre of symmetry (`sym_offsets`).
   A faint neutral mark (`road_faint`, ~0.86 of the paper) counts as the second casing ONLY where the width says a
   casing should be and the strict ink shows just one -- the lighter casing of an unimproved road often prints
   below the ink threshold, and without this the line centres on the one casing it sees.
   Offsets are median-cleaned (81 m window, 1.5 m) and Gaussian-smoothed over 25 m, LONGER than a dash cycle
   (dashes 10-20 m with like gaps): with a 12 m window the line followed whichever dash row it had just seen and
   bounced from row to row every 30-60 m (Dan saw it in QGIS); the strict within-2 m score drops a few points
   with the longer window, but a road is smooth over 50 m and the eye is right here.
8. **Finish.** Gaussian smoothing by arc length (creeks/contours 2 m), RDP 0.3 m, pins restored exactly.
9. **Check** (`grade`): independent of all of the above -- raw ink, explicit edge/band/line rules, unmeasured when
   ambiguous. Per line: measured %, off-centre median / p95 / within-2 m %, off-centre stretches, gaps, moves from
   the prior, pin offsets.

## Results on the test set (27 traced steps)

- Contours (5): 98-99.8% within 2 m of centre, median 0.25 m, lengths within 2% of the prior after the no-shortcut
  rule (before it, two contours lost 1.5-1.9 km to lobe cuts).
- Creeks (3): 99.3-99.8% within 2 m, measured along 72-76% (the rest is dot gaps and lettering, bridged straight).
- Roads (19): 77-98% within 2 m; the misses are junctions and labels the check cannot grade, and real wobble on
  dashed unimproved roads. Work continues there.
- One step (81) excluded: the road the text follows is not printed on that sheet.

## Lettering (found by the critic pass)

Contour labels ("1800", "1900") are printed in the same brown as the contour, so a colour classifier traces the digits
as contour and the line loops through them (10-22 m); black road names ("GAP") pull road traces the same way.
`ink.lettering()` finds letters by SHAPE: (a) whole pieces of ink of 8-40 m extent carrying >= 4.5 m of ink per metre
of extent (a line gives 2-3, a dash ~3); (b) on the ink eroded by one pixel (letter strokes are heavier than lines),
compact pieces 5-30 m, not elongated, filling >= 20% of their box. Pass (b) still bites pieces out of heavy index
contours, so contours and creeks exclude only pass (a); roads exclude both. Labels that touch their contour
("1800" across its own line) are not caught; the trace bridges the label's gap straight, which is right.

## Alternatives considered (Oct. 15, 2026)

- QGIS Raster Tracer plugin: interactive click-to-click colour following; the same least-cost idea, one feature at
  a time, no check, no lettering/dash/double-line handling. Fine for a person fixing one line.
- GRASS r.thin + r.to.vect (colour separation, clean, thin, vectorize): batch skeletons; breaks at labels and
  overlaps, and a double-line road gives two skeletons, not the centre.
- Modern vectors (NHD, TNM roads, 3DEP contours) over the scan: not allowed as geometry where the legal line is the
  printed one (priors only).

## Tint-gated ink rules (the last fix of Oct. 15)

Dashed roads on paper were right; on the woodland tint they weaved. Over tint a road dash prints olive, the colour
of a brown contour, and faint dashes read warm. Two rules fix it, both applied ONLY where the local background is
the tint (`tinted` = background green > red + 25 and > blue + 40): brown needs kg - kb >= 0.06 (contour ink darkens
blue more than green; dashes darken all alike), and brown pieces that are dash-shaped (8-35 m, elongation >= 3)
count as road ink. Applied everywhere, the same rules counted contour fragments on paper as road dashes and two
highways dropped 30-50 points. Gate on the background; the paper rules were already right.

## Dead ends (do not repeat)

- **Grading with the same measurement that moves the line.** Every parameter change "improved" the grade. The grader
  must be independent (raw ink, explicit rules) or the numbers mean nothing.
- **Absolute colour thresholds** for ink: break on the next sheet's tint. Use local-background ratios + warmth.
- **Binary closing to merge a road's two edges**: only fills where dashes coincide on both edges. Dilation (grow)
  merges them everywhere; the ridge of the grown band is the centre.
- **Median pooling of cross-sections** (to outvote side roads): also outvotes the dashes of unimproved roads, which
  cover less than half the window; a step lost a third of its readings. Mean pooling, and let the robust-offset
  median clean the junctions.
- **Symmetry alone to find a road's centre**: a lone edge is symmetric about itself, so the line jumps between the
  centre and one edge. Score by paired ink mass times symmetry.
- **Big GAP cost to stop shortcuts**: a 20 m neck cut is always cheaper than 1.5 km around. Forbid the edge by arc
  length instead.
- **Tuning on four steps**: run all of them after each change; a fix for one road broke two creeks twice.
- **A "faint gray" road class** (kmean < 0.92, neutral) to catch the lighter dashes of unimproved roads: it also
  catches the scan's halo around every symbol; six road steps dropped 15-20 points within-2 m. Faint dashes are
  better handled by pooling cross-sections along the road than by lowering the ink threshold.
- **Lettering detection on all ink colours**: a short thick creek stroke over the woodland tint (3-4 px wide with
  its halo) passes the whole-shape letter test and vanished from the creek; Dan spotted the missed dot in QGIS.
  Labels on these sheets are brown or black, so letters are searched in non-blue ink only.
- **Box-based compactness for letters**: a diagonal dash has a square bounding box, so the dashes of an unimproved
  road over the tint (heavy, 12-15 m) were taken for letters and a whole road lost its ink (Stark Road, step 31,
  measured 18%). Elongation is measured on the pixels' principal axes (ratio <= 2.5), not the box.
- **Applying the eroded-core lettering pass to contours**: catches "18" but also 30 m chunks of heavy contour, which
  become gaps the path shortcuts across; three contours lost 3-5% of their length. Roads only.
- **Letting the straddling-run rule and 2.5 m casing pairs apply everywhere**: on dashed roads a casing plus a
  side road reads as a "straddling run" and the pair rule picks up casing + fence; four roads dropped 10-15 points.
  The pair rule needs 3.5 m and a measured width; the straddling rule only where no pairs exist.
- **A fixed 3-cell running mean** for smoothing: zigzags on diagonals. Smooth by arc length.

## Oct. 16, 2026: pins, junctions, highways, labels on contours

- **Pins (step endpoints) moved onto the ink** (`src/boundary/fix_pins.py`; reviewed moves go in `resources/boundary/tracing/pin-moves.json`): each feature is traced FREE
  through its junction (the step's prior clipped to its last 300 m and extended 40 m straight past the pin, so the
  pin is an interior point), then the pin is the intersection of two free centrelines (both steps traced), the
  crossing of the free line with a highway lane line (steps 9, 90), or the nearest point on the one free line
  (lateral move only). Applied automatically only where the evidence is clean (intersections, lane crossings, lateral
  moves <= 3 m with the free line >= 85% within 2 m); larger one-sided moves are listed for a person: at point 78
  the free line cut the inside of a bend and the 10 m "move" was wrong. Pins defined "due east of" a spot elevation
  (58, 64, 82) are not moved laterally by the script (82 was moved on Dan's say-so). Dead end: a straight fit of the
  trace 20-50 m from the pin, extrapolated to the pin -- 9 m "moves" for pins that sat on a bending contour.
- **Junctions.** Road cross-section readings within 20 m of a pin are dropped (END_BLANK) and the path is pulled to
  the prior at 5 m within 40 m of a pin (END_PULL). Elongated road ink crossing the prior's bearing by > 30 deg
  (fences, side roads; pieces up to 400 m) is not road ink (`drop_crossing`).
- **Highways: the red fill is not road ink** (Dan). The casings beside the fill print warm and classed brown, so
  brown ink touching the fill (2 px) counts as casing (`casing` in ink.py). 21 and 27 still grade 72-74% within 2 m:
  the grader cannot read them well either (27 is a narrow double line whose casings merge at this scan).
- **Lettering is two-strength**: loose (fill 4.5, Oct. 15) for contours and creeks; strict (fill 5.5, >= 20 px) for
  roads -- the loose pass took a 43 px blob of two dash rows joined by a fence (fill 5.1) at point 94 and the road lost
  its casings at the junction. The two settings give IDENTICAL contour traces; the strict one is only for roads.
- **Contour labels printed on the line** (`digit_holes`): found by the holes of 0, 8, 6, 9 (30-450 m2, round, no
  morphological closing first -- closing welds contours on a steep slope and the pockets between them become holes;
  black text and its halo excluded first; a hole counts only with another within 40 m, a lone one is a tiny closed
  contour). What is removed from the contour ink is the digits' strokes grown 4 px (8 m); the ridge path bridges
  them like any gap. Result on the "1800"/"1700" labels: the loops through the 8 and the 0s are gone, a small spike
  toward a 1 (no hole) can remain. Dead ends, both tried Oct. 16: masking the whole label STRIP and crossing it on
  the prior's line (a straight bridge across "1700" on step 65 came out on the neighbouring contour), and the strip
  with the contour's own ink as tie-breaker (at the "1885" spot elevation on step 59, contours 6 m apart, the line
  still left on the wrong contour for 300 m -- Dan: "much worse"). On a steep slope the prior cannot pick the
  contour; only the ink can, so never blank more than the digits.

## Oct. 16, 2026, late morning: what a code review and three specialist reviews found and fixed

- **Labels on contours (the real fix).** The hops and loops at labels came from the GAP cost: off the band a gap costs
  GAP + d_out^2 (up to 420 per m mid-gap), so crossing a 40-60 m label was dearer than riding a leftover digit stroke
  or the NEIGHBOURING contour. Inside the label zone (digit_holes strip + brown lettering removed from the contour
  ink, grown 10 m) the off-band cost is now a flat GAP; all ink and band costs are kept. At Dan's four spots the worst
  offset from the prior fell from ~28 m to 4-9 m; roads and creeks unaffected. NOT the strip dead end above.
- **V tips:** MAX_ARC_JUMP 40 m for contours (150 m let the path cut the neck of a narrow V up a creek; 25 m overshoots).
- **The 6 m contour prior pull stays.** Last night's contours were WORSE: step 59 had 550 m on the wrong contour, step
  65 had 343 m; where the versions disagree the 6 m pull keeps the line on the heavy index ink at 30 of 38 places.
- **Creeks moved because of an ink edit made after their last run:** the tint-gated brown rule (kg - kb >= 0.06)
  turned the anti-aliased edges of contours over the tint into "dotlike", and chain_dots took them for creek dots.
  dotlike now uses the warmth-only brown (brown_dots). Last night's creek lines are reproduced exactly.
- **Road end hooks** are mostly pin positions, not code (measure them in the SPLICED ring: build_proposed ties the last
  12 m straight). One real kink fixed by name (start of step 68 at pin 67); an automatic on-centre test at a junction
  pin is not reliable.
- **The check.** grade() cannot see a hop: it asks "is ink of the class within 6 m". featurecheck.py (new) tracks
  lanes of raw ink across the line and reports VERIFIED / FLAGGED / UNMEASURED per metre plus a clustered review
  queue with crops; validated for contours only. Headline = VERIFIED %, never within-2 m of measured alone.
  regrade.py samples ink differently from trace() and rewrites its input: only on copies.
- **Process.** Every rule change runs all 27 steps and is compared with a FIXED reference (not the previous run);
  snapshot the code first (the skill is not under git). Checking a change on one spot is what broke this morning.

## Oct. 19, 2026: independent of NumPy's CPU-chosen exp (#116)

- **Never NumPy's exp in the tracer.** NumPy picks its float64 `exp` by the CPU (an AVX-512 kernel where there is one,
  the C library's elsewhere) and the two differ in the last bit of some values. On a straight north-south or east-west
  road the Dijkstra path sits on cell centres, so the first centring pass (`edge_offsets`, 0.5 m steps across) samples
  the ink exactly on cell edges, and the last bit of a smoothing weight decides which cell is read: two GitHub Linux
  runners put step 13 0.34 m apart. `smooth` and `robust_offsets` take their Gaussian weights from `libm_exp`
  (`math.exp`, which NumPy itself calls on the Mac, so the lines did not change). The knife edge itself remains: a
  deterministic rule for samples on a cell edge would move step 13 and others, so it waits for a re-trace.
