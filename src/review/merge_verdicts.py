"""Merge triage verdicts (verdicts-*.json) into one QGIS layer: the FIX + UNSURE items, numbered in boundary order.
Usage: merge_verdicts.py TRIAGE_DIR   -> TRIAGE_DIR/../FIX-LIST-EPSG4269.geojson (points; step, item, verdict, problem,
offset_m, note, batch, status, n). The fix list is the input of the usgs-quad-fix skill.
"""

import glob
import json
import os
import sys

T = (
    os.path.abspath(sys.argv[1])
    if len(sys.argv) > 1
    else os.path.dirname(os.path.abspath(__file__)) + "/triage"
)
feats = []
counts = {}
for fn in sorted(glob.glob(T + "/verdicts-*.json")):
    b = os.path.basename(fn)[9:-5]
    try:
        V = json.load(open(fn))
    except Exception as e:
        print("skip", fn, e)
        continue
    for v in V:
        counts.setdefault(b, {}).setdefault(v["verdict"], 0)
        counts[b][v["verdict"]] += 1
        if v["verdict"] in ("fix", "unsure"):
            feats.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [v["lon"], v["lat"]],
                    },
                    "properties": {
                        "step": int(v["step"]),
                        "item": v["item"],
                        "verdict": v["verdict"],
                        "problem": v.get("problem"),
                        "offset_m": v.get("offset_m"),
                        "note": v.get("note"),
                        "batch": b,
                        "status": "open",
                    },
                }
            )
feats.sort(key=lambda f: (f["properties"]["step"], f["properties"]["item"]))
for i, f in enumerate(feats, 1):
    f["properties"]["n"] = i
json.dump(
    {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::4269"},
        },
        "features": feats,
    },
    open(os.path.dirname(T) + "/FIX-LIST-EPSG4269.geojson", "w"),
    indent=1,
)
print(counts)
print(len(feats), "fix/unsure items")
