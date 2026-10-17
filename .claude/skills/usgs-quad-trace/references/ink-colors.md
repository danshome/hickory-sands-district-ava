# Ink colours on scanned USGS 1:24,000 quads (measured Oct. 15, 2026)

Sheets: 13 Texas HTMC sheets (Grit, Katemcy, Mason, Pontotoc, Purdy Hill, Turtle Creek, Voca, Fredonia, Spy Rock,
Long Mountain, Field Creek, Camp Air, Streeter; 1955-1970 editions, scanned by USGS topoView at ~2.03 m/px).
Measured with `src/tracing/inkcheck.py` and direct pixel probes. Values are the pixel's RGB divided by its LOCAL
BACKGROUND (grey closing, 7 px), written k = (kr, kg, kb). That is what `src/tracing/ink.py` classifies on; absolute
RGB is given only to show why absolute thresholds fail.

| what | absolute RGB (typical) | background | k = px / bg |
|---|---|---|---|
| paper | (245, 254, 237) | - | (1, 1, 1) |
| woodland tint | (180, 247, 132) to (190, 255, 139) | - | (1, 1, 1) against itself |
| tint seen against paper (tint edge) | (180, 247, 132) | paper | (0.74, 0.97, 0.56) |
| blue creek over paper | (183, 235, 233) | (241, 255, 253) | (0.76, 0.92, 0.92) |
| blue creek over tint, solid | (72, 182, 83) | (184, 252, 151) | (0.39, 0.72, 0.55) |
| blue creek over tint, teal/dark | (80, 190, 150) .. (50, 160, 100) | tint | kg - kr > 0.1, warmth ~ -0.1 |
| black road edge over tint | (63, 108, 51) | (146, 235, 124) | (0.43, 0.46, 0.41) |
| gray dashed road casing, paper | (180, 198, 176) | (241, 255, 237) | (0.75, 0.78, 0.74) |
| gray dash, faint | (210, 223, 197) | (244, 255, 234) | (0.86, 0.87, 0.84) |
| brown contour over tint, heavy | (137, 195, 83) | (189, 250, 138) | (0.72, 0.78, 0.60) |
| brown contour over paper, heavy | (6, 31, 9) | (222, 237, 211) | (0.03, 0.13, 0.04) |
| brown contour, light (intermediate) | (251, 254, 237) | (254, 255, 239) | (0.99, 1.00, 0.99) -- invisible at 2 m/px |
| red highway fill | (200, 60, 60) | paper | kr > 0.7, kg, kb < 0.62 |

## The classes (ink.py)

- `dark`: kmean < 0.82 and kg < 0.85. The green condition keeps the tint's edge (kg 0.97) out: every ink darkens
  green below ~0.8.
- `warmth` w = (kr - kb) / (1 - kmean): red-vs-blue darkening scaled by darkness, so faint and heavy ink of one
  colour get the same value. Measured: gray dashes +0.04, black road +0.04, brown over tint +0.40, blue over tint
  -0.36, teal over tint about -0.1.
- `brown`: w >= 0.22 AND kg - kb >= 0.06 (contour ink darkens blue more than green: over tint kg - kb 0.11-0.18);
  `black`: w > -0.22 and not brown (dashes over tint: kg - kb 0.00-0.06; faint dashes read w up to +0.28, so warmth
  alone put them in brown and dashed roads lost their casings over the tint -- Dan's 'weaves on green').
  `blue`: w <= -0.22 and kg > kr. `red`: kr > 0.7, kg and kb < 0.62.
- Over some tints a black road dash prints OLIVE, k = (0.66, 0.75, 0.56), kg - kb +0.19, w +0.28: the same colour
  as a brown contour over tint (0.75, 0.80, 0.64; +0.16; +0.41). Colour cannot separate them; `ink.dashes()` adds
  brown pieces that are dash-shaped (8-35 m long, principal-axes elongation >= 3, isolated) to the road class.
- `teal` (creek over tint printed near-neutral): dark, w < 0.1, kg - kr > 0.1.
- `creek` = (blue | teal) minus heavy black grown 1 px (lettering). `contour` = brown minus the same.
  `road` = (black & ~teal) | red, minus lettering (a dark creek over the tint reads near-neutral, so without the
  teal exclusion a road trace jumps onto a creek that runs beside it). `dotlike` = dark & ~brown & ~red: anything a
  dotted creek could be printed with.

## Why absolute thresholds failed

The first calibration (`classes_absolute`, kept in ink.py) used fixed RGB rules. It read dark woodland tint on the
Purdy Hill sheet as road ink (the tint there is (130, 220, 80), darker than the Grit sheet's), classed heavy brown
contours as black, and missed the light gray dashes of unimproved roads entirely. The local-background ratio removes
the sheet-to-sheet and within-sheet tint variation; warmth removes the faint-vs-heavy variation.

## Recalibrating on a new set

1. `src/tracing/inkcheck.py --quads "..." --at lon,lat ... --out check.png` at 5-6 places: a creek over paper and over
   tint, a dotted creek, a dashed road, a highway, a heavy contour over tint, some lettering.
2. Look at the right panels: is each symbol fully in its colour, is the tint edge clear of every class, is lettering
   magenta only?
3. Adjust the thresholds in `classes()` and record the new values here, with the sheet names and scan date.
