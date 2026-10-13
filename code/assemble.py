#!/usr/bin/env python3
"""Assemble the NPRM narrative boundary: 96 steps -> lines, polygon, points, both datums."""
import csv, json, math, os, zipfile
import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shplib

DLON, DLAT = -0.0003381665, 0.0001778510
R = 6371007.1809; SQMI = 2589988.110336
M_LAT = 110574.0
def m_lon(lat): return 111320.0*math.cos(math.radians(lat))
def seg_m(line):
    return sum(math.hypot((b[0]-a[0])*m_lon(a[1]), (b[1]-a[1])*M_LAT) for a,b in zip(line[:-1],line[1:]))


def rdp_m(pts, eps=2.5):
    import math
    if len(pts) < 3: return pts
    mx = m_lon(pts[0][1]); pts2 = [(p[0]*mx, p[1]*M_LAT) for p in pts]
    keep = [0, len(pts)-1]
    stack = [(0, len(pts)-1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2: continue
        ax, ay = pts2[a]; bx, by = pts2[b]
        dx, dy = bx-ax, by-ay
        L2 = dx*dx+dy*dy or 1e-12
        worst, wi = -1, None
        for i in range(a+1, b):
            t = max(0, min(1, ((pts2[i][0]-ax)*dx + (pts2[i][1]-ay)*dy)/L2))
            d = math.hypot(pts2[i][0]-ax-t*dx, pts2[i][1]-ay-t*dy)
            if d > worst: worst, wi = d, i
        if worst > eps:
            keep.append(wi); stack.append((a, wi)); stack.append((wi, b))
    keep = sorted(set(keep))
    return [pts[i] for i in keep]

rows = list(csv.reader(open("out/trace/gaz.csv")))[1:]
ends, nodes, begin = {}, [], None
for r in rows:
    if not r: continue
    step, kind, feat, lon, lat, quad, note = r[0], r[1], r[2], float(r[3]), float(r[4]), r[5], r[6]
    if kind == "begin": begin = (lon, lat, feat, quad, note)
    elif kind == "end": ends[int(step)] = (lon, lat, feat, quad, note)
    else: nodes.append((step, feat, lon, lat, quad, note))
assert begin and len(ends) == 96, (len(ends))
kinds = {int(k): v for k, v in json.load(open("data/nprm-step-kinds.json")).items()}
texts = {int(k): v for k, v in json.load(open("data/nprm-steps.json")).items()}

P0 = (begin[0], begin[1])
chain_prev = P0
feats27 = []
ring = [P0]
warn = []
for n in range(1, 97):
    tgt = (ends[n][0], ends[n][1])
    if kinds[n] == "follow":
        seg = [tuple(p) for p in json.load(open(f"out/trace/seg_s{n}.json"))]
        d0 = math.hypot((seg[0][0]-chain_prev[0])*m_lon(chain_prev[1]), (seg[0][1]-chain_prev[1])*M_LAT)
        d1 = math.hypot((seg[-1][0]-chain_prev[0])*m_lon(chain_prev[1]), (seg[-1][1]-chain_prev[1])*M_LAT)
        if d1 < d0: seg = seg[::-1]; d0 = d1
        dE = math.hypot((seg[-1][0]-tgt[0])*m_lon(tgt[1]), (seg[-1][1]-tgt[1])*M_LAT)
        if d0 > 60 or dE > 60: warn.append((n, round(d0), round(dE)))
        seg[0] = chain_prev; seg[-1] = tgt
        if n not in (3, 6, 59, 65, 82):
            seg = rdp_m(seg, 2.5)
    else:
        seg = [chain_prev, tgt]
    feats27.append((n, kinds[n], seg))
    ring.extend(seg[1:])
    chain_prev = tgt
closure = math.hypot((ring[-1][0]-ring[0][0])*m_lon(ring[0][1]), (ring[-1][1]-ring[0][1])*M_LAT)
if closure > 0.01: ring.append(ring[0])
else: ring[-1] = ring[0]
print(f"ring: {len(ring)} vertices, closure gap {closure:.1f} m, perimeter {seg_m(ring)/1000:.2f} km")
for w in warn: print("  endpoint warn (step, d_start, d_end):", w)

def area_sqmi(cs):
    tot = 0.0; n = len(cs)
    for i in range(n-1):
        l1,p1 = cs[i]; l2,p2 = cs[i+1]
        tot += math.radians(l2-l1)*(2+math.sin(math.radians(p1))+math.sin(math.radians(p2)))
    return abs(tot*R*R/2.0)/SQMI
ringW = [(x+DLON, y+DLAT) for x,y in ring]
A = area_sqmi(ringW)
import numpy as np
def pub_area(path):
    gj = json.load(open(path)); best, ba = None, -1
    for f in gj["features"]:
        g = f["geometry"]; polys = [g["coordinates"]] if g["type"]=="Polygon" else g["coordinates"]
        for p in polys:
            a = area_sqmi([(c[0],c[1]) for c in p[0]])
            if a > ba: ba, best = a, p[0]
    return ba
print(f"AREA traced narrative: {A:.2f} sq mi | TTB published: {pub_area('data/ttb_poly.geojson'):.2f} | petition layer: {pub_area('data/rcv_poly.geojson'):.2f}")

def F(geom_type, coords, props):
    return {"type": "Feature", "properties": props, "geometry": {"type": geom_type, "coordinates": coords}}
def shift(line): return [[round(x+DLON,6), round(y+DLAT,6)] for x,y in line]
def keep(line): return [[round(x,6), round(y,6)] for x,y in line]

common = {"docket": "TTB-2026-0005", "notice": "Notice No. 243, 91 FR 52576 (2026-08-14)",
          "source": "Drawn from scratch against the 13 USGS HTMC 1:24,000 quadrangles the petition cites",
          "datum_note": "WGS84 file: NAD27 sheet coordinates shifted by NADCON 5.0 (dLon -0.0003381665, dLat +0.0001778510)"}
name = "Hickory Sands District AVA, boundary per NPRM narrative (traced)"

# lines
lf, lf27, shp_lines = [], [], []
for n, kind, seg in feats27:
    L = seg_m(seg)
    pr = {"step": n, "kind": "followed feature" if kind=="follow" else "straight line",
          "endpoint": ends[n][2], "quad": ends[n][3], "length_m": round(L,1), "narrative": texts[n]}
    lf.append(F("LineString", shift(seg), pr))
    lf27.append(F("LineString", keep(seg), pr))
    shp_lines.append({"pts": keep(seg), "fields": {"step": n, "kind": pr["kind"], "endpoint": ends[n][2][:58], "length_m": round(L,1)}})
json.dump({"type":"FeatureCollection","name":name+" - steps","properties":common,"features":lf}, open("out/hickory-sands-nprm-boundary-steps.geojson","w"))
json.dump({"type":"FeatureCollection","name":name+" - steps NAD27","crs":{"type":"name","properties":{"name":"urn:ogc:def:crs:EPSG::4267"}},"properties":common,"features":lf27}, open("out/hickory-sands-nprm-boundary-steps-nad27.geojson","w"))

# polygon
pprops = dict(common); pprops.update({"Name": name, "area_sqmi_spherical": round(A,2),
  "perimeter_km": round(seg_m(ring)/1000,2), "built": "2026-10-11",
  "method": "96 narrative steps: followed features least-cost traced from sheet ink at full scan resolution; straight-line steps as chords between verified endpoints"})
json.dump({"type":"FeatureCollection","features":[F("Polygon",[shift(ring)],pprops)]}, open("out/hickory-sands-nprm-boundary-polygon.geojson","w"))
json.dump({"type":"FeatureCollection","crs":{"type":"name","properties":{"name":"urn:ogc:def:crs:EPSG::4267"}},"features":[F("Polygon",[keep(ring)],pprops)]}, open("out/hickory-sands-nprm-boundary-polygon-nad27.geojson","w"))

# points
pf, pf27, sp_pts, sp_rows = [], [], [], []
allpts = [("0","begin point",begin[2],begin[0],begin[1],begin[3],begin[4])]
for n in range(1,97):
    e = ends[n]; allpts.append((str(n),"step end",e[2],e[0],e[1],e[3],e[4]))
for s,feat,lon,lat,quad,note in nodes:
    allpts.append((s,"node",feat,lon,lat,quad,note))
for s,kind,feat,lon,lat,quad,note in allpts:
    pr = {"step": s, "kind": kind, "name": feat, "quad": quad, "note": note}
    pf.append(F("Point", [round(lon+DLON,6), round(lat+DLAT,6)], pr))
    pf27.append(F("Point", [round(lon,6), round(lat,6)], pr))
    sp_pts.append((lon, lat)); sp_rows.append([s, feat[:58], quad[:20]])
json.dump({"type":"FeatureCollection","name":name+" - points","properties":common,"features":pf}, open("out/hickory-sands-nprm-boundary-points.geojson","w"))
json.dump({"type":"FeatureCollection","name":name+" - points NAD27","crs":{"type":"name","properties":{"name":"urn:ogc:def:crs:EPSG::4267"}},"properties":common,"features":pf27}, open("out/hickory-sands-nprm-boundary-points-nad27.geojson","w"))

os.makedirs("out/shp27", exist_ok=True)
shplib.write_polylines("out/shp27/hsd-nprm-boundary-steps-nad27", shp_lines)
shplib.write_polygon("out/shp27/hsd-nprm-boundary-polygon-nad27", [keep(ring)],
                     [name[:58], round(A,2)], [("name","C",60,0),("area_sqmi","N",12,2)])
shplib.write_points("out/shp27/hsd-nprm-boundary-points-nad27", sp_pts,
                    [("step","C",6,0),("name","C",60,0),("quad","C",20,0)], sp_rows)
with zipfile.ZipFile("out/hickory-sands-nprm-boundary-nad27-shp.zip","w",zipfile.ZIP_DEFLATED) as z:
    for base in ("hsd-nprm-boundary-steps-nad27","hsd-nprm-boundary-polygon-nad27","hsd-nprm-boundary-points-nad27"):
        for ext in (".shp",".shx",".dbf",".prj"):
            z.write(f"out/shp27/{base}{ext}", f"{base}{ext}")
print("wrote steps/polygon/points geojson (x2 datums) + nad27 shapefile bundle")
for f in ("hickory-sands-nprm-boundary-steps.geojson","hickory-sands-nprm-boundary-polygon.geojson","hickory-sands-nprm-boundary-points.geojson","hickory-sands-nprm-boundary-nad27-shp.zip"):
    print(" ", f, os.path.getsize("out/"+f))
