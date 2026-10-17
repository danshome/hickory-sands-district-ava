# Reviewing close-ups from problems.py

You are the critic. Each PNG is one place on one traced line, about 130 m across (each scan pixel is ~2 m; the image
is enlarged so one scan pixel is a block of about 6 x 6 screen pixels).

- **Left panel**: the USGS scan. RED is the prior (the line before re-tracing). PURPLE is the traced line. The small
  black circle is the spot that was flagged.
- **Right panel**: what the tracer thinks is ink -- magenta black/gray (roads, lettering), orange red (highway fill),
  green brown (contours), blue blue or teal (creeks) -- with the purple traced line.
- **Header**: the spot id (`<line>-<nn>-<type>`), the feature kind (road, creek, contour), the sheet, and why it was
  flagged.

The feature being followed is the one the line is supposed to be on: a **creek** is the blue line (solid, dashed or
dash-dot-dot; over the green woodland tint it can look dark teal); a **contour** is the brown line; a **road** is a
double line (two solid or dashed black/gray edges), a highway (two black edges with red fill, sometimes the red in
dashes), or a single black line. The CENTRE of a creek or contour is the middle of the line; of a double-line road
or highway, midway between the two edges.

## For each image decide

1. `purple`: where the purple line is at the flagged spot (circle) and within ~30 m either side:
   - `centred` -- on the feature's centre, within about 1 scan pixel (2 m);
   - `near` -- on the feature but 2-4 m off centre (e.g. riding one edge of a double-line road);
   - `off` -- more than ~4 m off the feature, or on a different feature, or cutting across a bend;
   - `unclear` -- you cannot tell (feature not visible, image ambiguous).
2. `red`: the same judgement for the red prior (use `none` if no red line is shown).
3. `better`: `purple`, `red`, `same`, or `neither`.
4. `cause` (for `near`/`off`, else `none`), one of:
   - `lettering` -- a label or number printed over or beside the feature pulled the line;
   - `tint_ink_missed` -- the feature's ink over the green tint is not shown as ink in the right panel;
   - `ink_missed_other` -- the feature's ink is visible but not classed as ink (paper, faint print);
   - `wrong_class` -- other ink (a contour, a fence, a creek) is classed as the feature's ink and pulled the line;
   - `junction` -- a crossing or joining road/creek pulled the line;
   - `dashed_gap` -- gaps in a dashed/dotted symbol made it wander or cut across;
   - `corner_cut` -- the line cuts across a bend that the ink follows;
   - `wobble` -- the line oscillates side to side along a straight feature;
   - `sheet_edge` -- a jog or mismatch at the neatline between two sheets;
   - `pin` -- the line runs to an endpoint (pin) that is off the feature;
   - `other` -- say what in the note.
5. `offset_m`: your estimate of how far the purple is from the centre at the circle (0 if centred).
6. `note`: one short sentence -- what you see, in plain words.

Be literal: judge only what the scan shows. If the red and purple agree and both sit on the centre, that is a good
outcome even though the spot was flagged (the check itself can be fooled at junctions and labels -- say so in the
note when that is what happened: `purple: centred`, `cause: none`, note "flag was the check, not the line").

## Output

A JSON array, one object per image, in the order given:

```json
[{"pid": "9-03-gap", "purple": "centred", "red": "off", "better": "purple", "cause": "none", "offset_m": 0,
  "note": "purple follows the dotted creek through the tint; red cuts the bend by ~15 m"}]
```
