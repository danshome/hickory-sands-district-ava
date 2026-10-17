# Triage rubric: one brief per feature kind (paste into each reviewer agent's prompt)

Common to all: "You are a map reviewer. Batch file: <batch-K.json> (N items; each has item, step, lon, lat, types, why
-- what the automatic check suspects; it over-flags -- and crop, a close-up PNG). Open every crop with the Read tool and
read its header for the panels and colours. For each item decide `verdict`: ok / fix / unsure, plus `problem`,
`offset_m` (your estimate, 0 if ok) and `note` (one short sentence of what you see). Judge only what the scan shows; do
not assume a flag means a defect, and do not wave off a real one. Write a JSON array, one object per item in batch
order with keys item, step, lon, lat, verdict, problem, offset_m, note, to <verdicts-K.json>, progressively (every 15
items). Edit no other file; no QGIS/MCP tools. Final message: counts of ok/fix/unsure and the fix items."

## Contours
The feature: a boundary step that follows ONE named contour (brown; usually the heavier index contour). The line
should run along the CENTRE of that one brown line; where a label or spot elevation is printed on the contour it
should cross the label roughly straight, through the middle of the digits, and come out on the SAME contour; where
the contour is faint, broken, or under lettering or the green tint, it continues where the contour plainly runs.
- ok: on the centre of the right contour within ~2 m, or a straight label/gap crossing on the right line.
- fix: wrong contour, hop, loops or spikes into digits, cuts a bend or a V tip the ink follows, > ~2 m off centre
  for 10 m or more.
- problem: wrong_contour, hop, label_loop, label_spike, corner_cut, off_centre, other, none.

## Creeks
The feature: the blue line (solid, dashed, dash-dot-dot; dark teal over the green tint). The line runs along its
middle, follows the chain of dots/dashes through dotted stretches, never jumps onto a brown contour or a road, and
stays on its own branch at a confluence.
- problem: off_creek, onto_contour, wrong_branch, corner_cut, other, none.

## Roads
The feature: a double line (two solid or dashed black/grey edges), a highway (two black edges with red fill between,
the red sometimes dashed; the red is not an edge), or a single black line. The line runs along the CENTRE (midway
between the edges); at a junction it continues along its own road; a pin (the line's end) may sit at a junction.
- problem: one_edge, wrong_road, junction_hook, wobble, corner_cut, other, none.

## Lessons (Oct. 16, 2026, 372 items)
- ~78% of flags were the check's own confusion (dash gaps, crossings, lettering, tint) -- triage is what makes the
  queue workable. Contours 48 fixes of 183; creeks 9 of 83; roads 19 of 106.
- The defect is often tens of metres from the flagged point (a label up-line, a cut tip next to the stretch): ask the
  reviewer to look at the whole crop, and to name the spot when it is outside the flagged stretch.
- Several rings can be the SAME label or stretch: the reviewer says so in the note; the fixer makes one patch.
- A step that fails as a whole (step 27: 8 edge-ride items, sides switching) is better fixed as one long patch.
