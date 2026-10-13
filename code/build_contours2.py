#!/usr/bin/env python3
"""Contour layer v2: six per-quad features traced from the original sheets' ink.
Boundary contour segments (s3, s6, s59, s65, s82) are literal subsets.
Modern TNM lines steer only the short extension tails beyond the walked stretches."""
import json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tracelib as T
import shplib

DLON, DLAT = -0.0003381665, 0.0001778510

def tnm_parts(path):
    gj = json.load(open(path))
    out = []
    for f in gj["features"]:
        g = f["geometry"]
        parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        for p in parts:
            out.append([(x - DLON, y - DLAT) for x, y, *r in p])
    return out

def tail(seg, end_idx, parts, slug, ext_m=700):
    E = seg[end_idx]
    inner = seg[-12 if end_idx == -1 else 11]
    best = (1e18, None, None)
    for pi, p in enumerate(parts):
        for vi, v in enumerate(p):
            d2 = ((v[0]-E[0])*T.m_lon(E[1]))**2 + ((v[1]-E[1])*T.M_LAT)**2
            if d2 < best[0]: best = (d2, pi, vi)
    d0 = math.sqrt(best[0])
    if best[1] is None or d0 > 160:
        print(f"    no TNM hint near end ({d0:.0f} m); skipping tail")
        return []
    p, vi = parts[best[1]], best[2]
    def side_len(step):
        d, i = 0.0, vi
        while 0 < i < len(p)-1 and d < ext_m:
            j = i + step
            d += math.hypot((p[j][0]-p[i][0])*T.m_lon(p[i][1]), (p[j][1]-p[i][1])*T.M_LAT)
            i = j
        return d, i
    dA, iA = side_len(-1); dB, iB = side_len(1)
    def away(idx):
        return math.hypot((p[idx][0]-inner[0])*T.m_lon(E[1]), (p[idx][1]-inner[1])*T.M_LAT)
    step = -1 if away(iA) > away(iB) else 1
    i, acc, vias = vi, 0.0, []
    while 0 < i < len(p)-1 and acc < ext_m:
        j = i + step
        acc += math.hypot((p[j][0]-p[i][0])*T.m_lon(p[i][1]), (p[j][1]-p[i][1])*T.M_LAT)
        i = j
        if len(vias) == 0 or acc - vias[-1][1] > 110:
            vias.append((p[i], acc))
    if not vias: return []
    pts = [v[0] for v in vias]
    tr = T.follow(tuple(E), pts[-1], target_classes=("index",), vias=pts[:-1], slug=slug,
                  margin_px=100, scale=2, eps_px=1.0, refine=True)
    return T.despur(tr)

def mk_feature(line, elev, quad_slug, year, extra=""):
    L = T.seg_m(line)
    return {
        "type": "Feature",
        "properties": {
            "elevation_ft": elev,
            "quad": quad_slug.replace("_", " ").title() + ", TX",
            "quad_edition": year,
            "source": "USGS HTMC 1:24,000 GeoTIFF scan, printed contour ink traced at full resolution" + extra,
            "method": "least-cost raster trace of the index-contour ink; NAD27 to NAD83(1986) via NADCON 5.0",
            "length_km": round(L/1000, 2),
        },
        "geometry": {"type": "LineString",
                     "coordinates": [[round(x+DLON, 6), round(y+DLAT, 6)] for x, y in line]},
    }

def main():
    old = json.load(open("out/hickory-sands-quad-contours.geojson"))
    feats = [f for f in old["features"]]           # LM 1800, Grit 1900 unchanged
    years = {"fredonia": 1962, "pontotoc": 1955, "mason": 1967}

    s59 = [tuple(p) for p in json.load(open("out/trace/seg_s59.json"))]
    p18 = tnm_parts("data/tnm/c1800_east.json")
    tW = tail(s59, 0, p18, "fredonia"); tE = tail(s59, -1, p18, "pontotoc")
    full59 = list(reversed(tW))[:-1] + s59 + tE[1:]
    # split at the Fredonia/Pontotoc join (lon -99.0)
    cross = next(i for i in range(len(full59)-1) if (full59[i][0]+99.0)*(full59[i+1][0]+99.0) <= 0)
    a, b = full59[cross], full59[cross+1]
    t = (-99.0 - a[0]) / ((b[0]-a[0]) or 1e-12)
    J = (-99.0, a[1] + t*(b[1]-a[1]))
    west = full59[:cross+1] + [J]; east = [J] + full59[cross+1:]
    if west[0][0] > west[-1][0]: pass
    feats.append(mk_feature(west if west[0][0] < -99.0 else east, 1800, "fredonia", 1962,
                            "; continues onto the Pontotoc sheet"))
    feats.append(mk_feature(east if west[0][0] < -99.0 else west, 1800, "pontotoc", 1955,
                            "; continues onto the Fredonia sheet"))

    s65 = [tuple(p) for p in json.load(open("out/trace/seg_s65.json"))]
    p17 = tnm_parts("data/tnm/c1700_pont.json")
    tA = tail(s65, 0, p17, "pontotoc"); tB = tail(s65, -1, p17, "pontotoc")
    full65 = list(reversed(tA))[:-1] + s65 + tB[1:]
    feats.append(mk_feature(full65, 1700, "pontotoc", 1955))

    s82 = [tuple(p) for p in json.load(open("out/trace/seg_s82.json"))]
    p15 = tnm_parts("data/tnm/c1500_mason.json")
    tA = tail(s82, 0, p15, "mason"); tB = tail(s82, -1, p15, "mason")
    full82 = list(reversed(tA))[:-1] + s82 + tB[1:]
    feats.append(mk_feature(full82, 1500, "mason", 1967))

    gj = {"type": "FeatureCollection",
          "name": "Hickory Sands quad contours (traced from original quadrangles)",
          "features": feats}
    json.dump(gj, open("out/hickory-sands-quad-contours.geojson", "w"))
    gj27 = {"type": "FeatureCollection",
            "name": gj["name"] + " NAD27",
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4267"}},
            "features": []}
    shp_feats = []
    for f in feats:
        c27 = [[round(x-DLON, 6), round(y-DLAT, 6)] for x, y in f["geometry"]["coordinates"]]
        g = dict(f); g = json.loads(json.dumps(f))
        g["geometry"]["coordinates"] = c27
        gj27["features"].append(g)
        pr = f["properties"]
        shp_feats.append({"pts": c27, "fields": {
            "elev_ft": pr["elevation_ft"], "quad": pr["quad"], "edition": pr["quad_edition"] or 0,
            "length_km": pr["length_km"]}})
    json.dump(gj27, open("out/hickory-sands-quad-contours-nad27.geojson", "w"))
    os.makedirs("out/shp27", exist_ok=True)
    shplib.write_polylines("out/shp27/hickory-sands-quad-contours-nad27", shp_feats)
    import zipfile
    with zipfile.ZipFile("out/hickory-sands-quad-contours-nad27-shp.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for ext in (".shp", ".shx", ".dbf", ".prj"):
            z.write(f"out/shp27/hickory-sands-quad-contours-nad27{ext}",
                    f"hickory-sands-quad-contours-nad27{ext}")
    for f in feats:
        p = f["properties"]
        print(f"  {p['elevation_ft']} ft  {p['quad']:18s} {p['length_km']:6.2f} km  ({len(f['geometry']['coordinates'])} v)")
    print("layer v2 written (wgs84 geojson, nad27 geojson, nad27 shp zip)")

if __name__ == "__main__":
    main()
