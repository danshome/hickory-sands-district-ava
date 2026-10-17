"""Hard checks on the built boundary (exit 1 on any failure): every pin lies exactly on the end of its step and the
start of the next (Dan, Oct. 16 2026: no line may miss our points); no step line crosses itself; the AVA polygon is
valid; 104 steps and 105 points. Usage: check_build.py <gis dir>"""

import glob, json, math, sys
from osgeo import ogr

ogr.UseExceptions()
g = sys.argv[1]
one = lambda pat: glob.glob(g + "/" + pat)[0]
L = {
    f["properties"]["step"]: f["geometry"]
    for f in json.load(open(one("*-line-EPSG4269.geojson")))["features"]
}
P = {
    f["properties"]["step"]: f["geometry"]["coordinates"]
    for f in json.load(open(one("*-points-EPSG4269.geojson")))["features"]
}
A = json.load(open(one("*-area-EPSG4269.geojson")))["features"][0]["geometry"]
d = lambda a, b: math.hypot((a[0] - b[0]) * 95600, (a[1] - b[1]) * 110850)
ok = True
if len(L) != 104 or len(P) != 105:
    print("COUNT CHECK FAILED: %d steps, %d points" % (len(L), len(P)))
    ok = False
bad = []
for k, p in P.items():
    c = lambda n: L[n]["coordinates"]
    ends = (
        [d(p, c(1)[0]), d(p, c(max(L))[-1])]
        if k == 0
        else [d(p, c(k)[-1])] + ([d(p, c(k + 1)[0])] if k + 1 in L else [])
    )
    if max(ends) > 0.01:
        bad.append((k, round(max(ends), 3)))
print(
    "pin check: all %d points on their step ends" % len(P)
    if not bad
    else "PIN CHECK FAILED: %s" % bad
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
    else "SELF-CROSSING CHECK FAILED: steps %s, polygon valid %s"
    % (cross, poly_ok)
)
ok &= not cross and poly_ok
sys.exit(0 if ok else 1)
