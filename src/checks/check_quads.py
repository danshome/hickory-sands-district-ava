"""The 13 USGS quads the build reads, checked against quads-manifest.csv (MD5 of each GeoTIFF inside its zip, and of
each GeoPDF). Exit 1 if any is missing or altered; build.sh then fetches them (src/quads/fetch_quads.py)"""

import csv, hashlib, os, sys, zipfile

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
bad = []
n = 0
for r in csv.reader(
    open(os.path.join(ROOT, "resources", "quads", "quads-manifest.csv"))
):
    if not r or not r[4].endswith(".tif"):
        continue
    tif, tif_md5, pdf, pdf_md5 = r[4], r[7], r[8], r[11]
    z = os.path.join(ROOT, "resources", "quads", "geotiff", tif + ".zip")
    n += 1
    try:
        with zipfile.ZipFile(z) as zf, zf.open(tif) as fh:
            h = hashlib.md5()
            for b in iter(lambda: fh.read(1 << 20), b""):
                h.update(b)
        if h.hexdigest() != tif_md5:
            bad.append(tif + " (MD5 differs)")
    except FileNotFoundError, KeyError:
        bad.append(z + " (missing)")
    q = os.path.join(ROOT, "resources", "quads", "geopdf", pdf)
    if not os.path.exists(q):
        bad.append(q + " (missing)")
    elif hashlib.md5(open(q, "rb").read()).hexdigest() != pdf_md5:
        bad.append(pdf + " (MD5 differs)")
print(
    "quads: %d GeoTIFFs + %d GeoPDFs match quads-manifest.csv" % (n, n)
    if not bad
    else "QUAD CHECK FAILED:\n  " + "\n  ".join(bad)
)
sys.exit(1 if bad or n != 13 else 0)
