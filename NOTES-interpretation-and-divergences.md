# Interpretation notes and divergence record
Hickory Sands District AVA, Notice No. 243 narrative trace. 2026-10-11.

## Conventions used while tracing

1. "Proceed in a straight line" steps are chords between the named endpoints. "Proceed along"
   steps follow the printed feature; they were traced from the sheet ink itself.
2. Compound intersections are honored literally. At step 80 the text ends at the intersection
   of Old Pontotoc Rd with E SH 29 "and" Copperhead Rd; on the Mason sheet Old Pontotoc tees
   into SH 29 at -99.1992 and Copperhead leaves SH 29 about 320 m further west, so the boundary
   jogs west along the highway between the two (kept as a node in the points layer).
3. Step 82's endpoint is constructed strictly: the point on the walked 1,500-ft contour that
   lies due east of the printed 1511 spot on the road locally known as RR 1723. The traced
   contour crosses that latitude 39 m east of the road point, on the hook around the Rafael
   Creek valley head. Step 83 then runs due west at that latitude to the 1,700-ft contour ink.
4. Where a followed feature crosses a sheet boundary (Fly Gap Rd, Old Pontotoc Rd, Honey Creek,
   the 1,800-ft contour), each sheet's own ink was traced and the legs joined at the shared edge.
5. Contour-following steps (3, 6, 59, 65, 82) are exact vertex subsets of the delivered contour
   layer. Road and creek traces were simplified to 2.5 m to remove double-casing jitter;
   contours keep full resolution.
6. Datum: all tracing in each sheet's native NAD27; NAD83 (EPSG:4269) files apply the NADCON 5.0 NAD27-to-NAD83(1986) transformation, matching the CRS of TTB's AVAs_Production service; TTB-facing exports come from these
   (NADCON 5.0 CONUS grid, us_noaa_nadcon5_nad27_nad83_1986_conus.tif, point by point since 2026-10-11; about 32 m W and 20 m N here).

## Where the published polygons depart from the narrative text

The gazetteer (layers/gazetteer.csv) carries the full per-step notes; these are the headlines.
"Both rings" means TTB's published AVAs polygon and the petition's published boundary layer,
which share these departures except where noted.

1. Step 4 (marked 1,866): both published rings run roughly due north from the step 3 corner
   toward BM 1866 on SH 29, about 1.2 km WNW of the printed x1866, and never touch the marked
   point the text names.
2. Step 16 (marked 1,653 on Thomas Rd, Spy Rock sheet): both rings cut straight through,
   skipping the 1,653 corner by roughly 440 m.
3. Step 23 (marked 1,625): skipped by roughly 290 m.
4. Steps 37-38 (US 377 x Katemcy Rd intersection, then marked 1,726): the rings miss the two
   corners by roughly 390 m and 640 m.
5. Steps 80-81 (Old Pontotoc Rd south run): both rings run a straight line south at longitude
   -99.199 from the Behrens School Rd corner to the 1,500-ft contour. The text follows Old
   Pontotoc Rd to its tee into E SH 29, jogs ~320 m west along the highway to Copperhead Rd,
   and follows Copperhead's winding course to the contour crossing (max departure ~300 m).
6. Step 82 (walk end): the rings end the 1,500-ft contour walk at the hook apex, ~80 m
   northwest of the text's due-east-of-1511 construction.
7. Steps 89-92 (the southwest rewrite): TTB rewrote this stretch of the petition's narrative.
   The published TTB polygon follows the rewritten text (Honey Creek's west branch to the
   bridge marked BR 1668, then US 377 southwest then northwest to Old Junction Rd). The
   petition layer still shows the original routing up SH 29 to spot 1737, which excludes about
   4.3 sq mi that the rewrite brings in. This is a rewrite, not a digitizing error, but it is
   the main reason the petition layer and the notice disagree in the southwest.
8. Step 2 (northeast from 1705 to the 1,800-ft contour): the text gives a direction, not a bearing.
   The chord runs 828 m at about 77 deg to the heavy 1800 ink where the main contour run begins,
   passing just south of the tips of two small 1800 tongues (it crosses only light intermediate
   contours). From there the contour runs east, then southeast, then north, exactly as step 3 says.
   The endpoint is pinned on the ink, 4 m from the petition's vertex; both rings agree.

## Corrections

- 2026-10-11: steps 2-3 redrawn. The first build ran the step 2 chord 2,363 m to a later 1800
  crossing and never followed the contour's southern loop past x1822 (the east, then southeast,
  then north run the text describes). An interim fix read 'northeast' as a strict 45-deg bearing and
  wrapped two small tongues; corrected the same day. Step 2 now ends on the 1800 ink where the main
  run starts (828 m), and step 3 follows the ink for 12.1 km; the Long Mountain 1800 contour feature
  was extended to match (12.81 km). Area 198.76 -> 197.96 sq mi, perimeter 296.5 -> 304.3 km (spherical, at that time).
  Current polygon after the 2026-10-12 corrections: 198.07 sq mi on GRS 1980 (198.26 spherical), 308.7 km boundary length.
  Pre-fix layers were deleted at the petitioner's request (no going back to them).
