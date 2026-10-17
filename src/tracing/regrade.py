"""Re-run THE CHECK (centerline.grade) on already-traced lines without re-tracing: raw ink sampled around each line,
the grader's figures rewritten into the GeoJSON properties, plus the STRICT figure (within 2 m of the whole line,
unmeasured metres counted as failed -- Dan's rule) and the unmeasured stretches as a review list.
CLI: regrade.py --quads "GLOB" --traced traced.geojson [--ids 3 6 ...] [--kind-field kind]"""
import argparse, datetime, json, math, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import centerline as cl
from quadsheets import open_sheets

def regrade(sheets, coords, kind):
    lon0 = float(np.mean([c[0] for c in coords])); lat0 = float(np.mean([c[1] for c in coords]))
    mx, my = 111320.0 * math.cos(math.radians(lat0)), 110574.0
    XY = np.array([[(c[0] - lon0) * mx, (c[1] - lat0) * my] for c in coords])
    C = cl.resample(XY, 1.0); C[0], C[-1] = XY[0], XY[-1]
    pad = 16.0; xmin, ymin = C[:, 0].min() - pad, C[:, 1].min() - pad
    nx, ny = int((C[:, 0].max() + pad - xmin) / cl.RES) + 1, int((C[:, 1].max() + pad - ymin) / cl.RES) + 1
    # ink only within 14 m of the line (what grade() reads), sampled on the sheets
    near = np.zeros((ny, nx), bool)
    rr = np.clip(((C[:, 1] - ymin) / cl.RES).astype(int), 0, ny - 1); cc = np.clip(((C[:, 0] - xmin) / cl.RES).astype(int), 0, nx - 1)
    near[rr, cc] = True
    from scipy import ndimage
    near = ndimage.binary_dilation(near, structure=cl.disk(14 / cl.RES))
    iy, ix = np.nonzero(near)
    lons = lon0 + (xmin + (ix + 0.5) * cl.RES) / mx; lats = lat0 + (ymin + (iy + 0.5) * cl.RES) / my
    if kind == "creek":
        ink_c, have, ext = cl.sample_ink(sheets, kind, lons, lats, extra=("dotlike",))
        ink = np.zeros((ny, nx), bool); ink[iy, ix] = ink_c
        dl = np.zeros((ny, nx), bool); dl[iy, ix] = ext["dotlike"]
        ink |= cl.chain_dots(ink, dl, cl.RES)        # as trace() does: the dots of a dotted creek are creek ink
    else:
        ink_c, have = cl.sample_ink(sheets, kind, lons, lats)
        ink = np.zeros((ny, nx), bool); ink[iy, ix] = ink_c
    meas, symbol = cl.grade(C, ink, xmin, ymin, kind)
    core = np.zeros(len(C), bool); core[10:-10] = True
    resid = np.abs(meas); r_ok = resid[core & ~np.isnan(resid)]
    n_core = int(core.sum())
    off_runs, gaps = [], []
    for a, b in cl.runs(core & (np.nan_to_num(resid, nan=0) > 2)):
        if b - a >= 3:
            k = a + int(np.nanargmax(resid[a:b])); x, y = C[k]
            off_runs.append([round(lon0 + x / mx, 6), round(lat0 + y / my, 6), int(b - a), round(float(np.nanmax(resid[a:b])), 1)])
    for a, b in cl.runs(np.isnan(meas)):
        if b - a >= 8:
            x, y = C[(a + b) // 2]; gaps.append([round(lon0 + x / mx, 6), round(lat0 + y / my, 6), int(b - a)])
    pin_off = [round(float(np.nanmedian(np.abs(meas[sl]))), 1) if (~np.isnan(meas[sl])).any() else None
               for sl in (slice(1, 16), slice(-16, -1))]
    strict = 100 * float((r_ok <= 2).sum()) / max(n_core, 1)
    return dict(symbol=symbol, graded=datetime.datetime.now().isoformat(timespec="seconds"),
                measured_pct=round(100 * float((~np.isnan(meas[core])).mean()), 1),
                off_center_median_m=round(float(np.median(r_ok)), 2) if len(r_ok) else None,
                off_center_p95_m=round(float(np.percentile(r_ok, 95)), 2) if len(r_ok) else None,
                within_2m_pct=round(100 * float((r_ok <= 2).mean()), 1) if len(r_ok) else None,
                strict_within_2m_pct=round(strict, 1),
                off_center_runs=sorted(off_runs, key=lambda q: -q[2] * q[3]), gaps=gaps,
                pin_start_off_center_m=pin_off[0], pin_end_off_center_m=pin_off[1])

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quads", action="append", required=True); ap.add_argument("--traced", required=True)
    ap.add_argument("--ids", nargs="*"); ap.add_argument("--kind-field", default="kind")
    a = ap.parse_args()
    sheets = open_sheets(a.quads)
    out = json.load(open(a.traced))
    for f in out["features"]:
        fid = str(f["properties"]["id"]); kind = f["properties"][a.kind_field]
        if a.ids and fid not in a.ids: continue
        st = regrade(sheets, f["geometry"]["coordinates"], kind)
        f["properties"].update(st)
        print(f"{fid:>4} {kind:8} measured {st['measured_pct']:5.1f}%  within 2 m {st['within_2m_pct']}%  STRICT {st['strict_within_2m_pct']:5.1f}%  "
              f"gaps>=8 m {len(st['gaps'])}  off-centre runs {len(st['off_center_runs'])}", flush=True)
    json.dump(out, open(a.traced, "w"))

if __name__ == "__main__":
    main()
