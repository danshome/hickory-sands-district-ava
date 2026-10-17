"""The 13 USGS quads the build reads, checked against quads-manifest.csv.

Each GeoTIFF's MD5 is taken inside its zip, and each GeoPDF's from the file
(MD5: USGS's checksums in the manifest, not a security measure). Exit 1 if any
is missing or altered; build.sh then fetches them (src/quads/fetch_quads.py).
"""

import csv
import hashlib
import os
import sys
import zipfile

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
bad = []
n = 0
with open(
    os.path.join(ROOT, "resources", "quads", "quads-manifest.csv")
) as manifest:
    rows = list(csv.reader(manifest))
for r in rows:
    if not r or not r[4].endswith(".tif"):
        continue
    tif, tif_md5, pdf, pdf_md5 = r[4], r[7], r[8], r[11]
    z = os.path.join(ROOT, "resources", "quads", "geotiff", tif + ".zip")
    n += 1
    try:
        with zipfile.ZipFile(z) as zf, zf.open(tif) as fh:
            h = hashlib.md5(usedforsecurity=False)
            for b in iter(lambda: fh.read(1 << 20), b""):
                h.update(b)
        if h.hexdigest() != tif_md5:
            bad.append(tif + " (MD5 differs)")
    except FileNotFoundError, KeyError:
        bad.append(z + " (missing)")
    q = os.path.join(ROOT, "resources", "quads", "geopdf", pdf)
    if not os.path.exists(q):
        bad.append(q + " (missing)")
    else:
        with open(q, "rb") as fh:
            pdf_digest = hashlib.md5(fh.read(), usedforsecurity=False)
        if pdf_digest.hexdigest() != pdf_md5:
            bad.append(pdf + " (MD5 differs)")
print(
    f"quads: {n:d} GeoTIFFs + {n:d} GeoPDFs match quads-manifest.csv"
    if not bad
    else "QUAD CHECK FAILED:\n  " + "\n  ".join(bad)
)
sys.exit(1 if bad or n != 13 else 0)
