#!/usr/bin/env python3
"""Minimal shapefile writer (polyline + polygon), pure python. NAD27 .prj included."""
import struct, os

PRJ_NAD27 = ('GEOGCS["GCS_North_American_1927",DATUM["D_North_American_1927",'
             'SPHEROID["Clarke_1866",6378206.4,294.978698213898]],'
             'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')
PRJ_WGS84 = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
             'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
             'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')

def _bbox(all_pts):
    xs = [p[0] for pts in all_pts for p in pts]
    ys = [p[1] for pts in all_pts for p in pts]
    return min(xs), min(ys), max(xs), max(ys)

def _shp(path, shape_type, geoms):
    """geoms: list of list-of-parts; each part a list of (x, y)."""
    records = []
    for gi, parts in enumerate(geoms, 1):
        pts = [p for part in parts for p in part]
        xmin, ymin, xmax, ymax = _bbox([pts])
        nparts, npts = len(parts), len(pts)
        content = struct.pack("<i", shape_type)
        content += struct.pack("<4d", xmin, ymin, xmax, ymax)
        content += struct.pack("<2i", nparts, npts)
        idx = 0
        for part in parts:
            content += struct.pack("<i", idx)
            idx += len(part)
        for x, y in pts:
            content += struct.pack("<2d", x, y)
        records.append(content)
    xmin, ymin, xmax, ymax = _bbox([[p for part in g for p in part] for g in geoms])
    total_words = 50 + sum(4 + len(c) // 2 for c in records)
    hdr = struct.pack(">i5i", 9994, 0, 0, 0, 0, 0) + struct.pack(">i", total_words)
    hdr += struct.pack("<2i", 1000, shape_type)
    hdr += struct.pack("<4d", xmin, ymin, xmax, ymax) + struct.pack("<4d", 0, 0, 0, 0)
    shx_recs, offset = [], 50
    with open(path, "wb") as f:
        f.write(hdr)
        for i, c in enumerate(records, 1):
            f.write(struct.pack(">2i", i, len(c) // 2))
            f.write(c)
            shx_recs.append((offset, len(c) // 2))
            offset += 4 + len(c) // 2
    shx = struct.pack(">i5i", 9994, 0, 0, 0, 0, 0) + struct.pack(">i", 50 + 4 * len(records))
    shx += struct.pack("<2i", 1000, shape_type)
    shx += struct.pack("<4d", xmin, ymin, xmax, ymax) + struct.pack("<4d", 0, 0, 0, 0)
    with open(path[:-4] + ".shx", "wb") as f:
        f.write(shx)
        for off, ln in shx_recs:
            f.write(struct.pack(">2i", off, ln))

def _dbf(path, fields, rows):
    """fields: [(name, type 'C'/'N', length, decimals)]; rows: list of tuples."""
    import datetime
    now = datetime.date.today()
    recsize = 1 + sum(f[2] for f in fields)
    hdr = struct.pack("<4B I 2H 20x", 3, now.year - 1900, now.month, now.day,
                      len(rows), 32 + 32 * len(fields) + 1, recsize)
    out = bytearray(hdr)
    for name, typ, ln, dec in fields:
        out += struct.pack("<11s c 4x 2B 14x", name.encode()[:10], typ.encode(), ln, dec)
    out += b"\x0d"
    for row in rows:
        out += b" "
        for (name, typ, ln, dec), val in zip(fields, row):
            if typ == "N":
                s = (f"{val:.{dec}f}" if dec else str(int(val))).rjust(ln)[:ln]
            else:
                s = str(val)[:ln].ljust(ln)
            out += s.encode("ascii", "replace")
    with open(path, "wb") as f:
        f.write(bytes(out))

def write_polylines(basepath, feats, prj=PRJ_NAD27):
    """feats: [{'pts': [(x,y)...], 'fields': {...}}]; field schema inferred from first."""
    geoms = [[f["pts"]] for f in feats]
    _shp(basepath + ".shp", 3, geoms)
    keys = list(feats[0]["fields"].keys())
    fields = []
    for k in keys:
        v = feats[0]["fields"][k]
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            fields.append((k.upper()[:10], "N", 18, 2 if isinstance(v, float) else 0))
        else:
            fields.append((k.upper()[:10], "C", 60, 0))
    _dbf(basepath + ".dbf", fields, [[f["fields"][k] for k in keys] for f in feats])
    with open(basepath + ".prj", "w") as f:
        f.write(prj)

def write_polygon(basepath, rings, fields_row, field_schema, prj=PRJ_NAD27):
    """rings: list of rings (outer must be clockwise); one feature."""
    fixed = []
    for i, r in enumerate(rings):
        area = sum((r[j + 1][0] - r[j][0]) * (r[j + 1][1] + r[j][1]) for j in range(len(r) - 1))
        cw = area > 0
        rr = list(r)
        if (i == 0 and not cw) or (i > 0 and cw):
            rr = rr[::-1]
        if rr[0] != rr[-1]:
            rr.append(rr[0])
        fixed.append(rr)
    _shp(basepath + ".shp", 5, [fixed])
    _dbf(basepath + ".dbf", field_schema, [fields_row])
    with open(basepath + ".prj", "w") as f:
        f.write(prj)

def write_points(basepath, pts, fields, rows, prj=PRJ_NAD27):
    """pts: [(x, y)]; fields: schema like _dbf; rows aligned with pts."""
    records = []
    for x, y in pts:
        records.append(struct.pack("<i", 1) + struct.pack("<2d", x, y))
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    xmin, ymin, xmax, ymax = min(xs), min(ys), max(xs), max(ys)
    total_words = 50 + sum(4 + len(c) // 2 for c in records)
    hdr = struct.pack(">i5i", 9994, 0, 0, 0, 0, 0) + struct.pack(">i", total_words)
    hdr += struct.pack("<2i", 1000, 1)
    hdr += struct.pack("<4d", xmin, ymin, xmax, ymax) + struct.pack("<4d", 0, 0, 0, 0)
    shx_recs, offset = [], 50
    with open(basepath + ".shp", "wb") as f:
        f.write(hdr)
        for i, c in enumerate(records, 1):
            f.write(struct.pack(">2i", i, len(c) // 2)); f.write(c)
            shx_recs.append((offset, len(c) // 2)); offset += 4 + len(c) // 2
    shx = struct.pack(">i5i", 9994, 0, 0, 0, 0, 0) + struct.pack(">i", 50 + 4 * len(records))
    shx += struct.pack("<2i", 1000, 1)
    shx += struct.pack("<4d", xmin, ymin, xmax, ymax) + struct.pack("<4d", 0, 0, 0, 0)
    with open(basepath + ".shx", "wb") as f:
        f.write(shx)
        for off, ln in shx_recs: f.write(struct.pack(">2i", off, ln))
    _dbf(basepath + ".dbf", fields, rows)
    with open(basepath + ".prj", "w") as f:
        f.write(prj)
