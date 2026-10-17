# Hickory Sands District AVA: the boundary as proposed to TTB

The boundary of the **proposed Hickory Sands District American Viticultural Area** in the Texas Hill Country (Llano,
Mason, McCulloch and San Saba Counties), as the petitioners propose it to the Alcohol and Tobacco Tax and Trade Bureau
(TTB) after public comment on **Notice No. 243** (Docket No. TTB-2026-0005, 91 FR 52576), with the changes discussed
with TTB on October 15, 2026.

This repository builds, from source and with one command, everything that goes to TTB: the boundary description, TTB's
notice with the proposed changes highlighted, a side-by-side comparison, GIS layers, and the 13 USGS 1:24,000
quadrangles with the boundary drawn on them. Every line of the boundary is drawn on the printed linework of those USGS
maps; none is copied from an existing boundary layer.

> **Status: proposed.** This is the petitioners' proposal. TTB has not adopted it. The boundary of an American
> Viticultural Area is the written boundary description TTB adopts in 27 CFR part 9.

## See it (no account needed)

| | |
|---|---|
| **Dashboard** (start here) | https://robertclayvines.maps.arcgis.com/apps/dashboards/c5de8bb3fc1348d99f8afd99c11220b2 |
| Web map over the 13 USGS quadrangles | https://robertclayvines.maps.arcgis.com/home/item.html?id=26a9b3df19ad4093bb4a3c5c32d5c4fc |
| Every document, map and download | https://robertclayvines.maps.arcgis.com/home/group.html?id=65720ee9c5a743f88659ae39228704ec |
| TTB's AVA Map Explorer | https://www.ttb.gov/ava |
| The docket (Notice No. 243 and the public comments) | https://www.regulations.gov/docket/TTB-2026-0005 |

The dashboard shows the boundary on the 13 quadrangles with TTB's AVA Map Explorer polygon, all 104 steps (pick one to
see it on the map and read it), the change near Grit acre by acre, every difference from the AVA Map Explorer polygon,
and a link to every file.

## What is proposed

The proposed boundary description is **Notice No. 243's text word for word, except near Grit**:

- Steps (10)-(11) and (90)-(100) use the petition's own wording (February 2, 2023) in place of Notice No. 243's steps
  (10)-(11) and (90)-(92), written in the notice's style ("US Highway", "1,727-foot") with the roads named as the notice
  names them.
- Within them, **steps (93)-(96) are new**: they go around a lobe of granite northwest of the area near Grit by a
  windmill, a fence line and Topaz Lane, instead of the petition's straight line from the marked 1,737 to the marked
  1,762.
- Step (90) names the unnamed, intermittent tributary the petition's line follows from Honey Creek to the marked 1,727
  (the one correction to the petition's wording).
- Notice No. 243's steps (93)-(96) are unchanged, renumbered (101)-(104).

Result (build of October 16, 2026): **104 steps, 105 points, 193.83 square miles** (true area on the GRS 1980
ellipsoid). The build report in `dist/` always has the current figures.

What the change near Grit moves, with the granite (Town Mountain Granite and younger granitic intrusions, USGS State
Geologic Map Compilation, shifted to the outcrops) in each piece:

| piece | acres | granite (acres) |
|---|---:|---:|
| In Notice No. 243's text, left out by the petition | 2,733 | 2,596 |
| The granite lobe, also left out now by steps (93)-(96) | 140 | 127 |
| Put back, between the marked 1,737 and the windmill | 6 | 0 |
| Added by the petition's lane wording along steps (10)-(11) | 69 | 27 |
| In the petition, not Notice No. 243's text, along steps (99)-(100) | 19 | 16 |

Drawn the same way on the same maps, the AVA measures 198.17 square miles by Notice No. 243's text, 194.03 by the
petition, and 193.83 as proposed.

## How the line is drawn

- **Only the USGS maps.** The 13 USGS 1:24,000 quadrangles cited in paragraph (b) of the proposed rule, as USGS
  publishes them (GeoTIFF and GeoPDF from topoView): Long Mountain (1970), Grit (1970), Katemcy (1970), Turtle Creek
  (1968), Sheep Run Creek (1968), Mason (1967), Purdy Hill (1962), Spy Rock (1963), Voca (1963), Pecan Springs (1963),
  Fredonia (1962), Fly Gap (1962) and Pontotoc (1955). The build checks every file against its recorded MD5.
- **Every coordinate comes from the map.** Each point is a pin on a printed mark or junction (an elevation point, a
  benchmark, a road junction, a windmill), each straight-line step runs between two pins, and each "along the road /
  creek / contour" step is a trace of the centre of the printed ink (`src/tracing/`). TTB's polygon, the petition's
  layers and The National Map's contours were looked at only as hints and for comparison; no geometry comes from them.
- **Hard checks stop the build:** every one of the 105 points lies exactly on its two steps; no step line crosses
  itself; the polygon is valid; the quads match their manifest.
- **Datum.** The quadrangles are NAD27, in polyconic projections. Everything measured on them is moved to NAD83 point by
  point with NOAA's NADCON 5.0 CONUS grid. The layers are NAD83 (EPSG:4269), with TTB's AVAs_Production fields.
- **Lane wording.** Where the proposed text follows a highway's westbound or eastbound lane (steps (10)-(11) and
  (91)-(92)), the line is drawn 30 m from the highway's center line on that side, so it is visible beside the road
  symbol (about 13 m wide on the maps). This is a drawing convention discussed with TTB; the text is unchanged.

## Comparison with TTB's AVA Map Explorer polygon

TTB's AVA Map Explorer polygon for Notice No. 243 (its AVAs_Production layer) was digitized by hand; the proposed
revision follows the centre of the printed linework. So the two lines differ a little almost everywhere: measured every
2 m along each line, the median distance to the other line is 11 m. The build compares them (`src/review/compare_ttb.py`)
and reports:

- **6 big differences**, where the lines are 100 m or more apart: five where the two lines take different paths, and
  the proposed text change near Grit;
- **every piece of land between the two lines** (990 pieces): from the same text drawn differently, 682 acres are in
  the proposed revision only and 368 acres in the Map Explorer polygon only; the change near Grit accounts for the rest.

Both are published as map layers and listed on the dashboard.

## Build it yourself

Requirements: macOS or Linux with [Homebrew](https://brew.sh) (and Google Chrome on Linux), and network access the first
time. The build installs the rest (GDAL, poppler, Python 3.14, and Chrome on macOS) and keeps every Python package in the
project's own `.venv`.

```
./build.sh            # everything: tools, audit, quads, trace, boundary, checks, documents, quad sheets, package
./build.sh lint       # every pre-commit hook on every file
./build.sh clean      # remove target/ and dist/
```

The result is in `dist/`: the package zip, its README, `SHA256SUMS.txt` and `build-report.txt` (area, step count, check
results, source commit). The build is deterministic: two runs give identical lines.

To change the boundary, change only the inputs in `resources/boundary/` (a pin, a hand patch, a route hint, or the step
texts) and run `./build.sh`; every figure in the documents and the ArcGIS descriptions comes from the build.
[BUILD.md](BUILD.md) has the stages, the layout, the security checks on Python packages, and the commit hooks.

Every pull request is checked on GitHub (the commit hooks, and the whole build on Linux when the build's inputs
change), and each release (a `v...` tag) is built on GitHub and attached to the repository's Releases page; see
[BUILD.md](BUILD.md#github-actions-and-releases).

`./build.sh publish` updates the ArcGIS Online items, layers, web map and dashboard from the last build. It needs the
maintainer's saved ArcGIS sign-in and is never part of a normal build.

## Repository layout

```
build.sh        the build (see BUILD.md)
.github/        GitHub Actions: lint, build, release
src/            all code: quads, tracing, fixing, review, boundary, documents, checks, package, publish
resources/      the inputs: boundary/ (step texts, proposed ring and pins, tracing inputs), ttb/ (Notice No. 243,
                the AVAs_Production record), quads/ (manifest, VRT templates), geology/ (shifted USGS units)
documents/      the README and read-me templates (figures filled by the build)
LICENSE.txt     CC0 1.0
```

The USGS quadrangles themselves are downloaded by the build and not stored here.

## Sources and credits

- **USGS** 1:24,000 topographic quadrangles (public domain), via topoView / The National Map.
- **TTB**, Notice No. 243, 91 FR 52576 (a U.S. Government work, public domain); TTB's AVAs_Production layer, used for
  comparison only.
- **USGS** State Geologic Map Compilation (Horton and others, 2017, USGS Data Series 1052), shifted about 400 m to sit on
  the outcrops seen on USDA NAIP imagery; context only (see `resources/geology/README.md`).
- **NOAA NGS** NADCON 5.0 for NAD27 to NAD83.
- The web map uses Esri's USA Historical Topo Maps, World Topographic Map, World Street Map, World Imagery and USA Topo
  Maps services for display, under Esri's terms; nothing from them is in this repository or the package.

## License

The petitioners' work here (the code, the boundary linework and records, the documents and this README) is dedicated to
the public domain under **CC0 1.0** ([LICENSE.txt](LICENSE.txt)): anyone, TTB and its contractors included, may copy,
change and use it for any purpose without asking or giving credit. TTB's notice text and the USGS maps are works of the
United States Government and are in the public domain.

Provided as is, without warranty of any kind.

## Contact

Dan McLaughlin, Robert Clay Vineyards (petitioner), Mason, Texas: dan@robertclayvineyards.com
