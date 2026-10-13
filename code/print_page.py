#!/usr/bin/env python3
import sys, json, csv, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quadlib as Q
slug, yr = sys.argv[1], sys.argv[2]
ring = json.load(open("out/hickory-sands-nprm-boundary-polygon-nad27.geojson"))["features"][0]["geometry"]["coordinates"][0]
pts = []
for r in list(csv.reader(open("out/trace/gaz.csv")))[1:]:
    if r and r[1] in ("begin","end"):
        pts.append((float(r[3]), float(r[4]), "begin" if r[1]=="begin" else r[0]))
q = Q.Quad.get(slug)
ul = q.lonlat_of_pix(0, 0); lr = q.lonlat_of_pix(q.im.width, q.im.height)
w = round(ul[0]*8)/8; e = round(lr[0]*8)/8; n = round(ul[1]*8)/8; s = round(lr[1]*8)/8
inside = [(x,y) for x,y in ring if w <= x <= e and s <= y <= n]
if not inside:
    print(slug, "EMPTY"); sys.exit(0)
xs = [p[0] for p in inside]; ys = [p[1] for p in inside]
m = 0.0045
bb = (max(w, min(xs)-m), min(e, max(xs)+m), max(s, min(ys)-m), min(n, max(ys)+m))
labs = [(x,y,l) for x,y,l in pts if bb[0]-0.001 <= x <= bb[1]+0.001 and bb[2]-0.001 <= y <= bb[3]+0.001]
title = f"Proposed Hickory Sands District AVA - boundary per Notice No. 243 narrative - {slug.replace('_',' ').title()}, TX ({yr}) USGS 1:24,000"
outp = f"out/print/hsd-nprm-quad-{slug}.png"
Q.render_map(slug, bb, outp, lines=[ring], points=labs, grat=0.025 if (bb[1]-bb[0])>0.1 else 0.01, title=title, upscale=1.765)
print("page", slug, os.path.getsize(outp)//1024, "KB")
