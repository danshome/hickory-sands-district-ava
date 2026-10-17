"""Hard checks on the built boundary (exit 1 on any failure).

Every pin lies exactly on the end of its step and the start of the next (Dan,
Oct. 16 2026: no line may miss our points); no step line crosses itself; the
AVA polygon is valid; 104 steps and 105 points.

Usage: check_build.py <gis dir>
"""

import glob
import json
import math
import sys

from osgeo import ogr

ogr.UseExceptions()
g = sys.argv[1]


def load(pattern):
    """Reads the GeoJSON file in the GIS folder whose name matches pattern."""
    with open(glob.glob(g + "/" + pattern)[0]) as fh:
        return json.load(fh)


def metres_apart(a, b):
    """Returns the distance in metres between two lon/lat points, roughly."""
    return math.hypot((a[0] - b[0]) * 95600, (a[1] - b[1]) * 110850)


L = {
    f["properties"]["step"]: f["geometry"]
    for f in load("*-line-EPSG4269.geojson")["features"]
}
P = {
    f["properties"]["step"]: f["geometry"]["coordinates"]
    for f in load("*-points-EPSG4269.geojson")["features"]
}
A = load("*-area-EPSG4269.geojson")["features"][0]["geometry"]
ok = True
if len(L) != 104 or len(P) != 105:
    print(f"COUNT CHECK FAILED: {len(L):d} steps, {len(P):d} points")
    ok = False


def coords(n):
    """Returns the coordinates of step n's line."""
    return L[n]["coordinates"]


bad = []
for k, p in P.items():
    ends = (
        [metres_apart(p, coords(1)[0]), metres_apart(p, coords(max(L))[-1])]
        if k == 0
        else [metres_apart(p, coords(k)[-1])]
        + ([metres_apart(p, coords(k + 1)[0])] if k + 1 in L else [])
    )
    if max(ends) > 0.01:
        bad.append((k, round(max(ends), 3)))
print(
    f"pin check: all {len(P):d} points on their step ends"
    if not bad
    else f"PIN CHECK FAILED: {bad}"
)
ok &= not bad
cross = [
    k
    for k, geom in L.items()
    if not ogr.CreateGeometryFromJson(json.dumps(geom)).IsSimple()
]
poly_ok = ogr.CreateGeometryFromJson(json.dumps(A)).IsValid()
print(
    "self-crossing check: no step line crosses itself; polygon valid"
    if not cross and poly_ok
    else f"SELF-CROSSING CHECK FAILED: steps {cross}, polygon valid {poly_ok}"
)
ok &= not cross and poly_ok
sys.exit(0 if ok else 1)
