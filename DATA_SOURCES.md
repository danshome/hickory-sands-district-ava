# Data sources and provenance (Hickory Sands NPRM trace)

Retrieved 2026-10-11 unless noted. All USGS and Federal Register material is public domain.

## Base maps (the quadrangles the petition and notice cite)
13 USGS Historical Topographic Map Collection sheets, 1:24,000, NAD27, polyconic:
Long Mountain (1970), Grit (1970), Katemcy (1970), Turtle Creek (1968), Sheep Run Creek (1968),
Mason (1967), Purdy Hill (1962), Spy Rock (1963), Voca (1963), Pecan Springs (1963),
Fredonia (1962), Fly Gap (1962), Pontotoc (1955).
- GeoTIFF scans: prd-tnm.s3.amazonaws.com via tnmaccess.nationalmap.gov product API (dataset "Historical Topographic Maps").
- GeoPDF print sheets (same editions, delivered to Dan for printing): same API, GeoPDF format.
- Georeferencing read from each GeoTIFF's GeoKeys (polyconic, Clarke 1866, per-sheet central meridian); round-trip residual < 1e-9 px (quadlib.py self-test).

## Rulemaking texts
- Notice No. 243, 91 FR 52576 (Aug 14, 2026), Docket TTB-2026-0005: official PDF from govinfo.gov (FR-2026-08-14, doc 2026-16670); full text consulted at federalregister.gov. Boundary steps (1)-(96).
- Petition (Robert Clay Vineyards ArcGIS item 79bbd20a87a343429b5cf0d5c9317f5e, cover "February, 2023"): written boundary description steps 1-102.

## Comparison layers (not used as geometry sources for the new layer)
- TTB AVAs_Production "Hickory Sands" published polygon (services7.arcgis.com), retrieved earlier same day.
- Petitioner's boundary polygon (services3.arcgis.com, Hickory_Sands_AVA_Boundary_Poly).
- Local snapshots in comparison/ (fetched 2026-10-11 as GeoJSON, outSR 4269): TTB AVAs_Production
  layer 0 where Name = 'Hickory Sands District', and the petition's Hickory_Sands_AVA_Boundary_Points,
  _Poly and _Polyline feature services. Priors and comparison only, never geometry sources.
- USGS TNM Elevation Contours (carto.nationalmap.gov/arcgis/rest/services/contours), large-scale index contours 1800 and 1900: modern 3DEP-derived vectors. Used ONLY as routing hints, snapped to the printed ink before any tracing; they contribute no coordinates to outputs. Comparison render: out/trace/cmp_1800_tnm.png.

## Datum
Quads are NAD27. Outputs are NAD83(1986)~WGS84: NADCON 5.0 shift from NOAA NCAT at three points across the AVA
(dLat +19.7/+19.0/+18.8 m, dLon -32.4/-31.2/-31.5 m; spread < 1.5 m), originally applied as constants
(dLon -0.0003381665, dLat +0.0001778510). Since 2026-10-11 the NAD83 files use the NADCON 5.0 CONUS grid point by point
(us_noaa_nadcon5_nad27_nad83_1986_conus.tif); the constant differs from the grid by <=0.4 m. Sub-meter NADCON sigma.

## Methods
- quadlib.py: registry, polyconic forward/inverse, rendering with graticule and scale bar.
- tracelib.py: ink classification calibrated on these scans (classes: black, red, blue, green tint, index/inter brown),
  ray probing, least-cost (Dijkstra) ink following with full-resolution corridor refinement, despurring,
  RDP + Chaikin smoothing. Contour-following boundary segments are cut as literal subsets of the traced
  contour layer (out/hickory-sands-quad-contours.geojson).
- Gazetteer of step endpoints with notes: out/trace/gaz.csv.

## Final deliverables (2026-10-11, second pass)
- Boundary per the 96-step NPRM narrative, drawn from scratch: polygon, per-step lines, points,
  stored as NAD83 (EPSG:4269) GeoJSON in layers/; shapefiles are built by `make build`. Area 198.07 sq mi (GRS 1980),
  boundary length 308.7 km (steps 2-3 corrected 2026-10-11, later corrections 2026-10-12; see NOTES).
- Contour layer grown to six features (1800 LM, extended to 12.81 km with the step 2-3 fix, 1900 Grit, 1800 Fredonia, 1800 Pontotoc,
  1700 Pontotoc, 1500 Mason); boundary contour steps are exact subsets.
- 13 quad print pages at 300 dpi + combined PDF; comparison figure; narrative text reflowed
  verbatim from the FR layout (per-page column detection, hyphenation repaired).
- Official narrative source for the trace: proposed 27 CFR 9.___(c) steps (1)-(96) as printed
  at 91 FR 52587-52588.

## Quadrangle refresh and transfer integrity (2026-10-11, same day, later)
All 13 GeoTIFFs and GeoPDFs were re-downloaded fresh from the USGS TNM product API (the same
HTMC products topoView serves), at Dan's request, with provenance in quads-manifest.csv
(product title, source id, download URL, bytes, full md5 for every file). The fresh downloads
are byte-identical to the originally pulled files (same md5s), so the USGS source was never
the problem, and nothing in this project ever came from the petitioner's ArcGIS Online copies.
(An earlier revision of this note said USGS had "re-staged" the products; that was wrong.)

The damaged on-drive copies were damaged in transit, not at the source: the chat-to-device
file transfer re-encodes bare image files (TIFF), which changed their bytes, stripped the
embedded GeoTIFF georeferencing keys (QGIS: "no projection specification"), and left three
sheets (Grit, Mason, Voca) unreadable. GeoPDFs passed through unchanged. Fix: each GeoTIFF travels
and STAYS inside its own zip archive in quads_geotiff/ (zips arrive byte-clean), and the QGIS
projects read the GeoTIFF directly inside the zip via GDAL vsizip, so the USGS bytes and the
embedded georeferencing are never touched. Verified on the drive 2026-10-11: the 13 GeoTIFF
members inside the zips and 13/13 GeoPDFs match the USGS md5s in quads-manifest.csv exactly.
The traced layers align with these rasters unchanged.
