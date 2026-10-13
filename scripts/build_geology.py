#!/usr/bin/env python3
"""Rebuild the four geology layers (USGS data shifted to match aerial imagery, see SGMC_SHIFT) of the QGIS projects from official USGS sources, into build/geology/
(NAD83, EPSG:4269, like every layer in this repository):

  hickory-sandstone-member      USGS SGMC unit TXCAh;0   Hickory Sandstone Member
  town-mountain-granite         USGS SGMC unit TXpCAt;0  Town Mountain Granite
  younger-granitic-intrusion    USGS SGMC unit TXpCAy;0  younger granitic intrusions
  hickory-sands-above-1500ft    TXCAh;0 where the USGS 3DEP 1 arc-second DEM is at or above 1,500 ft (457.2 m),
                                clipped to the petition boundary

Sources (downloaded to data/fetched/, gitignored):
  SGMC: Horton, J.D., San Juan, C.A., and Stoeser, D.B., 2017, The State Geologic Map Compilation (SGMC)
        geodatabase of the conterminous United States: USGS Data Series 1052, https://doi.org/10.3133/ds1052 ;
        per-unit shapefiles from https://mrdata.usgs.gov/geology/state/ (geographic, WGS84).
  DEM:  USGS 3D Elevation Program, 1 arc-second, tiles n31w100 n31w099 n32w100 n32w099
        (NAD83 horizontal, NAVD88 vertical, meters).
Datum: SGMC is published as WGS84 and is converted to NAD83 with PROJ's EPSG:4326 to EPSG:4269 operation
(at most a meter or two, far below the compilation's accuracy); the DEM is already NAD83. QGIS shows NAD83 on
the NAD27 quads through the NADCON5 CONUS grid pinned in the projects.

Requires GDAL command-line tools (ogr2ogr, gdalbuildvrt, gdalwarp, gdal_contour) and python3 with shapely and
pyproj. Run from anywhere:  python3 scripts/build_geology.py
"""
import json, os, re, subprocess, sys
from shapely.geometry import shape, mapping
from shapely.affinity import translate
from shapely.ops import unary_union
from pyproj import Geod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FETCH = os.path.join(ROOT, "data", "fetched")
OUT = os.path.join(ROOT, "build", "geology")
UNITS = [("TXCAh", "hickory-sandstone-member", "Hickory Sandstone Member"),
         ("TXpCAt", "town-mountain-granite", "Town Mountain Granite"),
         ("TXpCAy", "younger-granitic-intrusion", "Younger granitic intrusion")]
TILES = ["n31w100", "n31w099", "n32w100", "n32w099"]
BBOX = (-99.70, 30.45, -98.70, 31.25)          # AVA region, generous
FT1500 = 1500 * 0.3048                          # 457.2 m
# The SGMC source sheet is misregistered in this area: every unit sits about 380 m south-east of where it shows
# on USDA NAIP imagery. Evidence: (1) the petitioner's corrected Hickory Sandstone layer, a uniform shift fitted
# here from 40 matched polygons (applying it reproduces his layer at 99.8% overlap), and the sandstone edge then
# follows the edge of the cultivated land; (2) an independent check, a Town Mountain Granite outcrop east of Flat
# Rock Road traced on NAIP lies 225 m west and 331 m north of its SGMC polygon (agreeing within about 30 m).
# The outcrop offset is used (Dan: the sandstone fit still sits slightly south-east). The same shift is applied to all three units. The DEM is correctly positioned and is not shifted.
SGMC_SHIFT = (-0.002356, +0.002993)             # degrees lon, lat (225 m west, 331 m north, from the granite outcrop trace)
UA = {"User-Agent": "Mozilla/5.0 (hickory-sands-ava build_geology)"}
G = Geod(ellps="GRS80"); AC = 4046.8564224

def get(url, dst):
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return dst
    print("fetch", url)
    subprocess.run(["curl", "-fsSL", "-A", UA["User-Agent"], "-o", dst + ".part", url], check=True)
    os.replace(dst + ".part", dst)
    return dst

def run(*cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

def fresh(path):  # GDAL's GeoJSON driver will not overwrite an existing file
    if os.path.exists(path): os.remove(path)
    return path

def acres(g):
    return abs(G.geometry_area_perimeter(g)[0]) / AC

def write(path, name, geoms, props):
    fc = {"type": "FeatureCollection", "name": name,
          "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4269"}},
          "features": [{"type": "Feature", "properties": dict(props, area_acres=round(acres(g), 1)), "geometry": mapping(g)} for g in geoms]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc, f)
    print(f"wrote {os.path.relpath(path, ROOT)}  ({len(geoms)} features, {sum(acres(g) for g in geoms):,.0f} ac)")

os.makedirs(FETCH, exist_ok=True); os.makedirs(OUT, exist_ok=True)

# 1. SGMC units: fetch the official zipped shapefile, convert WGS84 -> NAD83
sgmc = {}
for code, slug, title in UNITS:
    page = get(f"https://mrdata.usgs.gov/geology/state/unit-shape.php?unit={code};0", os.path.join(FETCH, f"{code}.html"))
    zname = re.search(r"output/([^\"']+\.zip)", open(page, encoding="utf-8", errors="replace").read()).group(1)
    z = get(f"https://mrdata.usgs.gov/geology/state/output/{zname}", os.path.join(FETCH, zname))
    tmp = fresh(os.path.join(FETCH, f"{code}-nad83.geojson"))
    run("ogr2ogr", "-overwrite", "-f", "GeoJSON", "-s_srs", "EPSG:4326", "-t_srs", "EPSG:4269", tmp, f"/vsizip/{z}")
    feats = json.load(open(tmp))["features"]
    geoms = [translate(shape(f["geometry"]).buffer(0), *SGMC_SHIFT) for f in feats]
    sgmc[code] = unary_union(geoms)
    src = feats[0]["properties"]
    write(os.path.join(OUT, f"{slug}-EPSG4269-NAD83.geojson"), slug, geoms,
          {"name": title, "unit_link": src.get("UNIT_LINK"), "generalize": src.get("GENERALIZE"),
           "source": "USGS State Geologic Map Compilation (Horton and others, 2017, USGS Data Series 1052)",
           "unit_url": src.get("URL"),
           "alignment": f"Shifted {SGMC_SHIFT[0]:+.6f} deg lon, {SGMC_SHIFT[1]:+.6f} deg lat (about 400 m) to match USDA NAIP imagery; SGMC as published is offset"})

# 2. Land at or above 1,500 ft from the USGS 3DEP 1 arc-second DEM
tifs = [get(f"https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1/TIFF/current/{t}/USGS_1_{t}.tif",
            os.path.join(FETCH, f"USGS_1_{t}.tif")) for t in TILES]
vrt, dem, cont = (os.path.join(FETCH, n) for n in ("dem.vrt", "dem-ava.tif", "above-1500ft.geojson"))
run("gdalbuildvrt", "-overwrite", vrt, *tifs)
run("gdalwarp", "-overwrite", "-te", *map(str, BBOX), "-co", "COMPRESS=DEFLATE", vrt, dem)
# Polygon mode needs bracketing levels; a single -fl level yields no polygons in GDAL 3.13.
fresh(cont)
run("gdal_contour", "-q", "-p", "-amin", "ELEV_MIN", "-amax", "ELEV_MAX", "-fl", "0", str(FT1500), "10000", "-f", "GeoJSON", dem, cont)
high = unary_union([shape(f["geometry"]).buffer(0) for f in json.load(open(cont))["features"]
                    if f["properties"]["ELEV_MIN"] >= FT1500 - 1e-6])

# 3. Hickory Sandstone Member above 1,500 ft, inside the petition boundary (as in the petitioner's original layer)
pet = unary_union([shape(f["geometry"]).buffer(0) for f in json.load(open(os.path.join(
    ROOT, "public-comment", "docket-attachments", "boundary-with-petition-western-routing-area-EPSG4269.geojson")))["features"]])
inter = sgmc["TXCAh"].intersection(high).intersection(pet)
parts = [g for g in getattr(inter, "geoms", [inter]) if g.geom_type == "Polygon" and acres(g) >= 0.5]
write(os.path.join(OUT, "hickory-sands-above-1500ft-EPSG4269-NAD83.geojson"), "hickory-sands-above-1500ft", parts,
      {"name": "Hickory Sands Above 1500 ft Elevation",
       "source": "USGS SGMC unit TXCAh;0 (shifted to match imagery, SGMC_SHIFT) intersected with USGS 3DEP 1 arc-second DEM >= 457.2 m (1,500 ft, NAVD88), within the petition boundary"})
print("done")
