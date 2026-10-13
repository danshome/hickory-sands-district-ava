#!/usr/bin/env python3
"""Produce the TTB-facing EPSG:4269 (NAD83) set from the assembled layers.
The layers are built in the sheets' native NAD27; NADCON 5.0 takes NAD27 to
NAD83(1986), which is EPSG:4269, the CRS of TTB's AVAs_Production service."""
import json, os, zipfile, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shplib

NOTE83 = ("EPSG:4269 NAD83, the CRS of TTB's AVAs_Production service. Built in the sheets' native "
          "NAD27 (each sheet's own polyconic projection), then transformed NAD27 -> NAD83(1986) "
          "by NADCON 5.0 (dLon -0.0003381665, dLat +0.0001778510; uniform to <1.5 m across the AVA)")
CRS83 = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4269"}}
PRJ83 = ('GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",'
         'SPHEROID["GRS_1980",6378137.0,298.257222101]],'
         'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')

def retag(src, dst):
    gj = json.load(open(src))
    gj["crs"] = CRS83
    if "properties" in gj and isinstance(gj["properties"], dict):
        gj["properties"]["datum_note"] = NOTE83
    for f in gj["features"]:
        if "datum_note" in f.get("properties", {}): f["properties"]["datum_note"] = NOTE83
    json.dump(gj, open(dst, "w"))
    return gj

pl = retag("out/hickory-sands-nprm-boundary-steps.geojson", "out/hickory-sands-nprm-boundary-polyline-nad83.geojson")
pg = retag("out/hickory-sands-nprm-boundary-polygon.geojson", "out/hickory-sands-nprm-boundary-polygon-nad83.geojson")
pt = retag("out/hickory-sands-nprm-boundary-points.geojson", "out/hickory-sands-nprm-boundary-points-nad83.geojson")
ct = retag("out/hickory-sands-quad-contours.geojson", "out/hickory-sands-quad-contours-nad83.geojson")

os.makedirs("out/shp83", exist_ok=True)
lines = [{"pts": f["geometry"]["coordinates"], "fields": {
    "step": f["properties"]["step"], "kind": f["properties"]["kind"],
    "endpoint": f["properties"]["endpoint"][:58], "length_m": f["properties"]["length_m"]}} for f in pl["features"]]
shplib.write_polylines("out/shp83/hsd-nprm-boundary-polyline-nad83", lines, prj=PRJ83)
ring = pg["features"][0]["geometry"]["coordinates"][0]
shplib.write_polygon("out/shp83/hsd-nprm-boundary-polygon-nad83", [ring],
                     [pg["features"][0]["properties"]["Name"][:58], pg["features"][0]["properties"]["area_sqmi_spherical"]],
                     [("name","C",60,0),("area_sqmi","N",12,2)], prj=PRJ83)
ppts = [tuple(f["geometry"]["coordinates"]) for f in pt["features"]]
prows = [[f["properties"]["step"], f["properties"]["name"][:58], f["properties"]["quad"][:20]] for f in pt["features"]]
shplib.write_points("out/shp83/hsd-nprm-boundary-points-nad83", ppts,
                    [("step","C",6,0),("name","C",60,0),("quad","C",20,0)], prows, prj=PRJ83)
cl = [{"pts": f["geometry"]["coordinates"], "fields": {
    "elev_ft": f["properties"]["elevation_ft"], "quad": f["properties"]["quad"],
    "edition": f["properties"]["quad_edition"] or 0, "length_km": f["properties"]["length_km"]}} for f in ct["features"]]
shplib.write_polylines("out/shp83/hickory-sands-quad-contours-nad83", cl, prj=PRJ83)
with zipfile.ZipFile("out/hickory-sands-nprm-boundary-nad83-shp.zip","w",zipfile.ZIP_DEFLATED) as z:
    for base in ("hsd-nprm-boundary-polyline-nad83","hsd-nprm-boundary-polygon-nad83","hsd-nprm-boundary-points-nad83"):
        for ext in (".shp",".shx",".dbf",".prj"): z.write(f"out/shp83/{base}{ext}", f"{base}{ext}")
with zipfile.ZipFile("out/hickory-sands-quad-contours-nad83-shp.zip","w",zipfile.ZIP_DEFLATED) as z:
    for ext in (".shp",".shx",".dbf",".prj"):
        z.write(f"out/shp83/hickory-sands-quad-contours-nad83{ext}", f"hickory-sands-quad-contours-nad83{ext}")
print("EPSG:4269 set written")
