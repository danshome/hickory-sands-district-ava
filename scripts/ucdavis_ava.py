#!/usr/bin/env python3
"""Write the boundary as a UC Davis AVA Project record (https://github.com/UCDavisLibrary/ava):
one GeoJSON FeatureCollection, CRS84 label, one Polygon feature with the project's 20 attribute fields
(template.geojson), exterior ring counterclockwise (RFC 7946), null for no data.

usage: ucdavis_ava.py <out.geojson> [proposed|petition]
  proposed  the boundary as written in Notice No. 243 (default; layers/ polygon)
  petition  the boundary with the petition's western routing near Grit (docket attachment)

The AVA is proposed, not established. The fields that only exist once TTB publishes a final rule
are left null and must be filled from that rule before the record is offered to the UC Davis
project: created, cfr_author, cfr_index, cfr_revision_history, valid_start (and the boundary itself
if the final rule changes it). Coordinates are NAD83, as in the project's own files."""
import csv, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = sys.argv[1]
which = sys.argv[2] if len(sys.argv) > 2 else "proposed"
SRC = {
    "proposed": "layers/hickory-sands-nprm-boundary-polygon-EPSG4269-NAD83.geojson",
    "petition": "public-comment/docket-attachments/boundary-with-petition-western-routing-area-EPSG4269.geojson",
}[which]

def signed_area(r):  # > 0 when counterclockwise (lon/lat treated as planar; orientation only)
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(r, r[1:])) / 2

def orient(poly):  # exterior counterclockwise, holes clockwise
    return [r if (signed_area(r) > 0) == (i == 0) else r[::-1] for i, r in enumerate(poly)]

def area_m2(r):  # local equirectangular approximation; only used to find sub-meter slivers
    import math
    k = math.cos(math.radians(r[0][1]))
    return abs(signed_area([(x * 111320.0 * k, y * 110574.0) for x, y in r]))

g = json.load(open(os.path.join(ROOT, SRC)))["features"][0]["geometry"]
polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
# Drop digitizing artifacts under 10 m2 (the petition-routing layer has two sub-meter slivers and two
# holes with 1 m and 7 m perimeters where the route doubles back on the highway lanes).
MIN_M2 = 10.0
polys = [[r for i, r in enumerate(p) if i == 0 or area_m2(r) >= MIN_M2] for p in polys if area_m2(p[0]) >= MIN_M2]
polys = [orient(p) for p in polys]
geom = {"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1 else {"type": "MultiPolygon", "coordinates": polys}

# Notice No. 243, proposed 27 CFR 9.__ "Hickory Sands District", paragraph (b), verbatim
APPROVED_MAPS = ("(1) Long Mountain, TX., 1970; (2) Grit, TX., 1970; (3) Purdy Hill, TX., 1962; (4) Spy Rock, TX., 1963; "
                 "(5) Fredonia, TX., 1962; (6) Katemcy, TX., 1970; (7) Voca, TX., 1963; (8) Pecan Springs, TX., 1963; "
                 "(9) Pontotoc, TX., 1955; (10) Fly Gap, TX., 1962, photorevised 1982; (11) Mason, TX., 1967, photoinspected 1979; "
                 "(12) Turtle Creek, TX., 1968; and (13) Sheep Run Creek, TX., 1968.")
# Paragraph (c), the 96 steps verbatim
steps = json.load(open(os.path.join(ROOT, "narrative/nprm-steps.json")))
boundary = " ".join(steps[k] for k in sorted(steps, key=int))
if which == "petition":
    boundary += (" [This record's geometry follows the petition's western routing near Grit, described in"
                 " Attachment 1 to the petitioners' comment on Docket TTB-2026-0005, not proposed steps 90 to 92.]")
with open(os.path.join(ROOT, "quads-manifest.csv"), newline="") as f:
    used = "; ".join(f"({i}) {r['quad']}, {r['edition']} (USGS Historical Topographic Map Collection GeoTIFF {r['geotiff']})"
                     for i, r in enumerate(csv.DictReader(f), 1))

props = {
    "ava_id": "hickory_sands_district",
    "name": "Hickory Sands District",
    "aka": None,
    "created": None,                 # final rule publication date (YYYY-MM-DD)
    "removed": None,
    "county": "Llano|Mason|McCulloch|San Saba",
    "state": "TX",
    "within": "Texas Hill Country",  # add Llano Uplift if that proposed AVA is established
    "contains": None,
    "petitioner": "Dan McLaughlin, Robert Clay Vineyards|William R. Parr, Jr., Parr Vineyards and Parr Cellars|Drew Tallent, Tallent Vineyards",
    "cfr_author": None,              # from the final rule's drafting information
    "cfr_index": None,               # final rule section, e.g. 9.2xx
    "cfr_revision_history": None,    # e.g. [T.D. TTB-xxx, 9x FR xxxxx, Mon. d, yyyy]
    "approved_maps": APPROVED_MAPS,
    "boundary_description": boundary,
    "used_maps": used,
    "valid_start": None,             # final rule effective date (YYYY-MM-DD)
    "valid_end": None,
    "lcsh": None,
    "sameas": None,
}
fc = {"type": "FeatureCollection", "name": "hickory_sands_district",
      "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
      "features": [{"type": "Feature", "properties": props, "geometry": geom}]}
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(fc, f, ensure_ascii=False)
print(f"ucd   {out}  ({which}, {geom['type']}, {sum(len(r) for p in polys for r in p)} vertices)")
