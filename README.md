# Hickory Sands District AVA - NPRM boundary, drawn from scratch off the original quadrangles

Robert Clay Vineyards / Dan McLaughlin. Built 2026-10-11 with Claude.
Docket TTB-2026-0005, Notice No. 243, 91 FR 52576 (Aug 14, 2026). Comments close 2026-10-13.

## What this is

The boundary polygon that the NPRM's rewritten 96-step narrative actually describes, digitized
from scratch against the same 13 USGS 1:24,000 historical quadrangles the petition cites.
No existing boundary layer contributed any geometry: the TTB and petition polygons were used
only as search priors and for comparison statistics. Every "proceed along" step (roads, creeks,
elevation contours) was traced from the printed ink of the sheet at full scan resolution with a
least-cost path follower; every "proceed in a straight line" step is a chord between endpoints
pinned on the sheets (spot elevations, benchmarks, junctions, summits, cemeteries, mines).

Headline numbers (GRS 1980 ellipsoid, the figures used in the public comment): 96 steps, 198.07 sq mi,
308.7 km boundary length (sum of the 96 steps). TTB's published polygon measures 197.63 sq mi; the boundary
with the petition's western routing near Grit, 193.79.

## Cropped quads (quads_cropped/)

One small GDAL VRT per sheet that reads the original GeoTIFF directly from its zip and crops it to the sheet's
7.5-minute neatline, so adjoining sheets meet edge to edge with no white margins. Same pixel grid as the original
(no resampling); the originals are untouched. In the NAD27 QGIS project they are a separate group ("Quads: cropped
(no borders)"), and the originals stay available in "Quads: originals (with borders)"; toggle either group.
The VRTs are generated from the committed `*.vrt.in` templates by `scripts/build_cropped_quads.sh`, which fills in the checkout path (GDAL cannot resolve a relative path inside `/vsizip/`).

## Comparison snapshots (comparison/)

GeoJSON snapshots (EPSG4269-NAD83) of TTB's published Hickory Sands District polygon and the
petition's boundary points, polygon and polyline services, fetched 2026-10-11 for side-by-side
viewing in QGIS. Comparison only; no geometry from them is used in layers/.

## Layers (layers/)

Every layer is stored in NAD83 (EPSG:4269) only, the CRS TTB uses for its AVAs_Production service. The original quad
scans are the only NAD27 data; GIS software shifts the NAD83 layers onto them for display (see the project settings below).

- hickory-sands-nprm-boundary-polygon-EPSG4269-NAD83.geojson  the closed boundary
- hickory-sands-nprm-boundary-polyline[...]      96 line features, one per narrative step; each
                                              carries the verbatim step text, endpoint name,
                                              quad, and length
- hickory-sands-nprm-boundary-points-EPSG4269-NAD83     the gazetteer as points: begin point, 96 step
                                              ends, plus construction nodes (SH 29 x Copperhead,
                                              the 1511 reference on RR 1723)
- hickory-sands-quad-contours-EPSG4269-NAD83            the six traced index-contour features the boundary
                                              follows (1800 Long Mountain, 1900 Grit, 1800
                                              Fredonia + Pontotoc, 1700 Pontotoc, 1500 Mason);
                                              the boundary's contour steps are literal vertex
                                              subsets of these lines
- hickory-sands-nprm-boundary-shp-EPSG4269-NAD83.zip   polyline + polygon + points shapefiles
- hickory-sands-quad-contours-shp-EPSG4269-NAD83.zip   contour shapefiles
- gazetteer.csv                               step, kind, feature, lon, lat (NAD83), quad, notes, crs
                                              including every divergence found while tracing

## Maps

- maps/hickory-sands-boundary-comparison.png  the three rings side by side with callouts
- print/hickory-sands-nprm-quad-pages.pdf     all 13 quads at 300 dpi, boundary in the same
                                              cased magenta on every sheet, step numbers labeled
- print/hsd-nprm-quad-*.png                   the individual pages
- maps/qa*.png                                sector QA frames from the tracing run

## Narrative (narrative/)

- nprm-narrative-steps.txt   the exact 96-step boundary narrative, reflowed verbatim from the
                             official Federal Register text (the file this work traced)
- nprm-steps.json            the same, one JSON entry per step
- nprm-step-kinds.json       chord vs follow classification derived from the text

## Code (code/)

Pure Python 3 (numpy, Pillow, matplotlib; no GIS libraries, no installs needed).

- quadlib.py          quad registry, NAD27 polyconic forward/inverse from each GeoTIFF's
                      GeoKeys, cropping, map rendering (graticule, scale bar, cased line style)
- tracelib.py         the digitizer: ink classification calibrated on these scans, ray probes,
                      least-cost (Dijkstra) ink following with full-resolution corridor
                      refinement, despurring, RDP + Chaikin smoothing
- shplib.py           minimal shapefile writer (polyline, polygon, point) with NAD27 .prj
- build_contours2.py  the traced contour layer
- assemble.py         gazetteer + step texts + traced segments -> the three boundary layers
- print_page.py       one 300 dpi quad page

To rerun: put the 13 HTMC GeoTIFFs under data/quads/ (sources in DATA_SOURCES.md), then
python3 -I build_contours2.py && python3 -I assemble.py && python3 -I make_nad83.py

## Accuracy

Point pins were verified by zooming the scans to the printed marks; traced lines ride the ink
within a pixel or two (the scans are about 2.4 m per pixel). The NAD27 to NAD83(1986) shift is
NADCON 5.0, uniform to under 1.5 m across the AVA. Treat individual coordinates as good to
roughly 30-50 m against the real world, which is the precision of the source maps themselves.


File naming: the CRS is in every layer filename (EPSG4269-NAD83 = TTB's CRS). macOS does not allow a colon in filenames, so EPSG:4269 is written EPSG4269.


## GIS project settings (QGIS / ArcGIS Pro)

Two valid setups, depending on which layer set you are working with. Mixing them without the
right datum transformation puts everything 30 to 40 m off, so set these before loading data.

### Working against the original quad scans

The scans are NAD27 (each sheet in its own polyconic projection). Use project CRS "EPSG:4267 - NAD27" with ellipsoid
"Clarke 1866 (EPSG:7008)" (not the look-alikes "Clarke 1866 Authalic Sphere (EPSG:7052)", "Clarke 1858" or "Clarke 1880"),
load the NAD83 layers, and make sure the NAD83 -> NAD27 transformation is the NADCON5 CONUS grid
(us_noaa_nadcon5_nad27_nad83_1986_conus.tif). The NAD27 QGIS project already pins it.

### Working in TTB's CRS (the -EPSG4269-NAD83 layers)

Use this setup for anything alongside TTB's AVAs_Production service or modern data.

- Project / map CRS: "EPSG:4269 - NAD83" (North American Datum of 1983)
- QGIS measurement ellipsoid: pick exactly "GRS 1980 (EPSG:7019)", the Geodetic Reference
  System 1980; semi-major 6,378,137.000 m, semi-minor 6,356,752.314 m.
  Do NOT pick "GRS 1980 Authalic Sphere (EPSG:7048)", "GRS 1980 Adj WI CP (ESRI:107806)",
  or "GRS 1967 (EPSG:7036)", which sit next to it in the list
- Units: meters / square meters (display coordinates in map units, degrees)

### If you must mix NAD27 and NAD83 content in one project

Make the software use the NADCON grid transformation, not its default fallback:

- QGIS: Project Properties > Transformations (or the dialog that pops up when the second datum
  loads): pick the NAD27 to NAD83 operation that names NADCON (CONUS grid). If QGIS silently
  uses a null or Helmert fallback, NAD27 layers will plot roughly 32 m east of where they belong.
- ArcGIS Pro: Map Properties > Coordinate Systems sets the map CRS; the Transformation tab must
  show NAD_1927_To_NAD_1983_NADCON (CONUS). ArcGIS otherwise picks a default that may not be
  the grid method.

The NAD83 layers are transformed from the NAD27 layers point by point with the NOAA NADCON 5.0 CONUS grid
(us_noaa_nadcon5_nad27_nad83_1986_conus.tif); at this AVA the shift is about 32 m west and 20 m north going NAD27 to NAD83. The QGIS
projects pin the same grid, so the NAD83 layers display back on the traced NAD27 ink to under 0.1 m.

### Area measurement note

The polygon carries two area attributes: `area_sqmi` (198.07, ellipsoidal on GRS 1980, the same
method as QGIS ellipsoidal or ArcGIS Pro geodesic measurement, and the figure the comment quotes) and
`area_sqmi_spherical` (198.26, a spherical computation on the authalic radius 6,371,007.18 m). The
difference is the measurement method, not the geometry. `scripts/check.sh` recomputes the ellipsoidal
areas and fails if any document quotes a different figure.

## QGIS projects (qgis_projects/)

Two ready-made project files, each preconfigured per the settings section above and using
relative paths, so they work as long as the folder structure stays intact.

The 13 USGS GeoTIFFs live in quads_geotiff/ as one zip per sheet, and both projects read each
GeoTIFF directly inside its zip (GDAL vsizip). Leave them zipped and keep the filenames as they
are; the zip is what guarantees the USGS bytes (and the embedded georeferencing) are untouched.
Verify any sheet against the md5 column in quads-manifest.csv.

- HickorySandsDistrictAVA-EPSG4267-NAD27.qgs: project CRS EPSG:4267 (to match the scans), measurement ellipsoid
  Clarke 1866 (EPSG:7008). Loads the NAD83 layers over all 13 original USGS sheets; the NADCON5 CONUS grid is
  pinned for every NAD83/WGS84/Web Mercator -> NAD27 shift.
- HickorySandsDistrictAVA-EPSG4269-NAD83.qgs: project CRS EPSG:4269, measurement ellipsoid
  GRS 1980 (EPSG:7019). Loads the four EPSG4269-NAD83 layers and TTB's AVAs_Production
  feature service (layer 0, needs internet) over the same 13 original sheets, reprojected on
  the fly. The NAD27 to NAD83 datum shift is pinned in the project to the NADCON5 CONUS grid
  pipeline (with fallback allowed), so the transformation dialog should not appear; confirm in
  Project Properties > Transformations if you want to see it.

Both are saved in QGIS 4.2 format (upgraded from the original 3.28 schema on 2026-10-11), so
open them with QGIS 4.x; each project's _attachments.zip must stay beside it. Symbology: boundary polyline in
white-cased dashed magenta, polygon as a light fill with dotted outline, contours brown,
points dark circles; restyle freely.

## Rebuilding large files

Downloaded source files and build outputs are not stored in this repository. From the repository root:

1. `python3 scripts/fetch_quads.py` downloads the 13 designated USGS 1:24,000 quadrangles (GeoTIFF and GeoPDF) from the URLs in `quads-manifest.csv`, checks each against its recorded MD5, and stores them in `quads_geotiff/` (one GeoTIFF per zip, read by the QGIS projects through `/vsizip/`) and `quads_geopdf/`.
2. `python3 scripts/fetch_sources.py` downloads Notice No. 243 and the Hickory Sands District petition from Docket TTB-2026-0005 into `narrative/source/`.
3. `scripts/build_cropped_quads.sh` (requires GDAL) generates `quads_cropped/*.vrt` from the committed `*.vrt.in` templates and writes neatline-cropped GeoTIFFs to `quads_cropped_geotiff/`.
4. `scripts/build_all.sh` (requires `pip install -r requirements.txt`, Google Chrome, and GDAL for shapefiles) builds into `build/`: Exhibits A and C, the ArcGIS Online thumbnails, the comment and Attachment 1 PDFs, shapefile zips of the GIS layers, and the boundary as a [UC Davis AVA Project](https://github.com/UCDavisLibrary/ava) record (`build/ucdavis/hickory_sands_district.geojson`: their 20-field template, CRS84, counterclockwise; the fields that come from a final rule, such as `created`, `cfr_index` and `valid_start`, stay null until TTB publishes one). Exhibit A is drawn from the OpenStreetMap extract in `data/osm/` (ODbL, OpenStreetMap contributors) and Exhibit C from TTB's San Pasqual Valley feature in `data/ttb/`, both retrieved October 12, 2026.

5. `make geology` (requires GDAL, shapely, pyproj) rebuilds the four geology layers into `build/geology/` (NAD83) from official USGS sources: State Geologic Map Compilation units TXCAh;0 (Hickory Sandstone Member), TXpCAt;0 (Town Mountain Granite) and TXpCAy;0 (younger granitic intrusions) (Horton and others, 2017, USGS Data Series 1052), and the USGS 3DEP 1 arc-second DEM for the Hickory Sandstone above 1,500 ft, clipped to the petition boundary. The SGMC source sheet is misregistered here by about 380 m to the south-east relative to USDA NAIP imagery (shown by the sandstone's edge against the cultivated land and by a Town Mountain Granite outcrop east of Flat Rock Road), so the build shifts all three units by one offset (`SGMC_SHIFT` in `scripts/build_geology.py`); the 3DEP DEM is not shifted.

The QGIS projects in `qgis_projects/` open once steps 1, 3 and 5 are done. Layers that pointed to the author's local PostGIS database are kept for reference without credentials and will not load.

## Public comment

`public-comment/` holds the source of the comment filed on TTB Docket No. TTB-2026-0005 (Notice No. 243) and of Attachment 1 (Markdown), the GIS layers attached to it (`docket-attachments/`, NAD83), the Exhibit B source image (drawn on Esri World Imagery; imagery: Esri, Maxar, Earthstar Geographics, and the GIS User Community), and the ArcGIS Online item metadata. The filed documents on Regulations.gov are the version of record.
