# resources/aquifer: the inputs of the 3D aquifer page and of The land's slice and maps

The website's map (`docs/map.html`; "The Hickory Aquifer in 3D", #135, is its groups below the ground) reads
`docs/assets/aquifer/`, which `src/site/make_aquifer_3d.py` makes from these inputs. The land page's "Sand, height and
water" and "A slice through the district" (`docs/land.html`) read `docs/assets/land/`, which `src/site/make_land.py`
makes from some of them and from the map's data. Map context only: no boundary geometry comes from them.

| file | what it is |
|---|---|
| `inputs.csv` | every downloaded input of the 3D page: its name, the cache file, the URL, the date of the data (`snapshot`), when it was fetched, its bytes and SHA-256 |
| `land-inputs.csv` | the same for the land page's own downloads (the land page also reads `twdb-gam` from `inputs.csv`) |
| `cache/` | the downloads of both (gitignored), fetched when missing and checked against their manifest |
| `twdb-gam-faults-EPSG4269.geojson` | TWDB's fault lines (committed: see below) |
| `twdb-gam-row239-EPSG4269.geojson` | TWDB's section line A–A′ along model row 239 (committed: see below) |

The downloads (`inputs.csv`):

- `twdb-gam`: TWDB's Llano Uplift Aquifer System Groundwater Availability Model v1.01, GAM Properties archive
  (Shi, Boghici, Kohlrenken and Hutchison, 2016); only `lnup_v101/lnup_v101_fp_grid/lnup_v101_flow_props.gpkg` is
  extracted from it (with `bsdtar`, which reads 7z), into `cache/`. Model layer 7 is the Hickory Aquifer, layer 8 the
  Precambrian.
- `twdb-minor-aquifers`: TWDB's Minor Aquifers shapefile of December 2017, for the official Hickory outline, which the
  generator moves by the geology's shift (`resources/geology/README.md`).
- `twdb-sdr`, `twdb-gwdb`: TWDB's Submitted Driller's Reports and Groundwater Database bulk downloads. These URLs
  always serve today's file, so the manifest pins the snapshot the page was made from (files dated 2026-10-16); a
  different file stops the run. People's names and addresses are removed before anything is written
  (`src/site/aquifer/privacy.py`).
- `census-counties`, `census-places`: U.S. Census Bureau 2023 cartographic boundaries (counties, 1:500,000) and the 2023
  Gazetteer's Texas places (towns).

`twdb-gam-faults-EPSG4269.geojson`: the fault lines of the model's source geodatabase,
https://gw-models.s3.amazonaws.com/Download_GAMs/llano/lnup_source_data.gdb.zip (853,921,098 bytes, Last-Modified
2023-02-03, ETag `ba151bb6d7df7f99cad52d9704b79101`), layers `Modified_GAT_Faults` (531 lines) and `Pennsylvanian_Faults`
(135), read on 2026-10-18 by GDAL range requests (the archive is not downloaded whole) and written in NAD83 to 6
decimal places with their attributes. Its third fault layer, `Conceptual_Faults`, is a schematic in drawing units, not
map positions, and is left out. The page uses them for one figure: how many of the steps in the aquifer's top lie near a
fault line.

`twdb-gam-row239-EPSG4269.geojson`: the source geodatabase's layer `Row_239_Xsection` (the same archive as the fault
lines), the line of TWDB's section A–A′ along model row 239 (Shi and others, 2016, Numerical Model Report, Fig. 2.2.2),
read on 2026-10-19 by GDAL range requests and written in NAD83 to 6 decimal places with its attributes. It is two
points, straight in the model's own projection (TWDB's GAM Albers, US survey feet), where `src/site/land/section.py`
measures along it; the land page draws columns 150 to 290 of the row, part of the line.

The land page's downloads (`land-inputs.csv`): the four USGS 3D Elevation Program 1 arc-second tiles of the maps' frame
(n31w100, n32w100, n31w099 and n32w099), from `StagedProducts/Elevation/1/TIFF/current/`: the slice's ground (the first
two) and map 01's ground at 1,500 feet and higher (all four). `snapshot` is each file's Last-Modified date. USGS replaces
a "current" tile when it publishes a newer one, so a later fetch may not match the pinned SHA-256 and the run stops,
naming the tile: move to it as for the 3D page's inputs (BUILD.md). The model's GeoPackage is read from the same cache, as
the 3D page's generator extracts it.

Other committed inputs the 3D page's generator reads: `resources/vineyards/` (its README), TTB's Llano Uplift AVA
(`resources/ttb/ttb-avas-production-llano-uplift-EPSG4269-NAD83.geojson`, AVAs_Production queried 2026-10-18 for
`Name = 'Llano Uplift'`) and the shifted geology (`resources/geology/`). Their SHA-256s are in the page's record,
`docs/assets/aquifer/record.json`. The land page's record, `docs/assets/land/record.json`, pins its inputs the same way,
the 3D page's files it reads among them (the Precambrian outcrop, the stats and the well files). BUILD.md says how the
build checks the records and how to move to a new snapshot.
