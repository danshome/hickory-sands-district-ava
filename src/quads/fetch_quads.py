"""Download the 13 designated USGS 1:24,000 quadrangles listed in quads-manifest.csv
(GeoTIFF and GeoPDF), verify each against its recorded MD5, and lay them out the way the
QGIS projects and the cropped VRTs expect:

    resources/quads/geotiff/<name>.tif.zip   (one GeoTIFF per zip; read via /vsizip/)
    resources/quads/geopdf/<name>.pdf

./build.sh runs it whenever a quad is missing or altered.
Already-present files that pass the MD5 check are skipped.
"""
import csv, hashlib, os, sys, tempfile, urllib.request, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # repository root (src/quads/..)
TIF_DIR = os.path.join(ROOT, "resources", "quads", "geotiff")
PDF_DIR = os.path.join(ROOT, "resources", "quads", "geopdf")


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def md5_of_zip_member(zpath, member):
    h = hashlib.md5()
    with zipfile.ZipFile(zpath) as z, z.open(member) as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dst):
    req = urllib.request.Request(url, headers={"User-Agent": "hickory-sands-ava-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r, open(dst, "wb") as f:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            f.write(chunk)


def main():
    os.makedirs(TIF_DIR, exist_ok=True)
    os.makedirs(PDF_DIR, exist_ok=True)
    failures = 0
    with open(os.path.join(ROOT, "resources", "quads", "quads-manifest.csv"), newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        # GeoTIFF, stored inside its own zip
        tif, zpath = row["geotiff"], os.path.join(TIF_DIR, row["geotiff"] + ".zip")
        if os.path.exists(zpath) and md5_of_zip_member(zpath, tif) == row["geotiff_md5"]:
            print(f"ok    {tif}")
        else:
            with tempfile.TemporaryDirectory() as tmp:
                tmpfile = os.path.join(tmp, tif)
                print(f"fetch {tif}")
                download(row["geotiff_url"], tmpfile)
                got = md5_of(tmpfile)
                if got != row["geotiff_md5"]:
                    print(f"  MD5 MISMATCH {got} != {row['geotiff_md5']}", file=sys.stderr); failures += 1; continue
                with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
                    z.write(tmpfile, tif)
        # GeoPDF
        pdf, ppath = row["geopdf"], os.path.join(PDF_DIR, row["geopdf"])
        if os.path.exists(ppath) and md5_of(ppath) == row["geopdf_md5"]:
            print(f"ok    {pdf}")
        else:
            print(f"fetch {pdf}")
            download(row["geopdf_url"], ppath)
            got = md5_of(ppath)
            if got != row["geopdf_md5"]:
                print(f"  MD5 MISMATCH {got} != {row['geopdf_md5']}", file=sys.stderr); failures += 1
    print(f"done: {len(rows)} quadrangles, {failures} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
