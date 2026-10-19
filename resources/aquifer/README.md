# resources/aquifer: the inputs of the 3D aquifer page

The website's page "The Hickory Aquifer in 3D" (`docs/aquifer.html`, #135) reads `docs/assets/aquifer/`, which
`src/site/make_aquifer_3d.py` makes from these inputs. Map context only: no boundary geometry comes from them.

| file | what it is |
|---|---|
| `inputs.csv` | every downloaded input: its name, the cache file, the URL, the date of the data (`snapshot`), when it was fetched, its bytes and SHA-256 |
| `cache/` | the downloads (gitignored), fetched when missing and checked against `inputs.csv` |
| `twdb-gam-faults-EPSG4269.geojson` | TWDB's fault lines (committed: see below) |

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

Other committed inputs the generator reads: `resources/vineyards/` (its README), TTB's Llano Uplift AVA
(`resources/ttb/ttb-avas-production-llano-uplift-EPSG4269-NAD83.geojson`, AVAs_Production queried 2026-10-18 for
`Name = 'Llano Uplift'`) and the shifted geology (`resources/geology/`). Their SHA-256s are in the page's record,
`docs/assets/aquifer/record.json`. BUILD.md says how the build checks the record and how to move to a new snapshot.
