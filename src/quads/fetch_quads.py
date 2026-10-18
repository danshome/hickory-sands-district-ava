"""Downloads the 13 USGS quadrangles that the description names.

Downloads the 13 designated USGS 1:24,000 quadrangles listed in
quads-manifest.csv (GeoTIFF and GeoPDF), verifies each against its recorded
MD5, and lays them out the way the QGIS projects and the cropped VRTs expect:

    resources/quads/geotiff/<name>.tif.zip   (one GeoTIFF per zip; /vsizip/)
    resources/quads/geopdf/<name>.pdf

./build.sh runs it whenever a quad is missing or altered.
Already-present files that pass the MD5 check are skipped.
"""

import csv
import hashlib
import os
import sys
import tempfile
import urllib.request
import zipfile

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # repository root (src/quads/..)
TIF_DIR = os.path.join(ROOT, "resources", "quads", "geotiff")
PDF_DIR = os.path.join(ROOT, "resources", "quads", "geopdf")


def md5_of(path):
    """The MD5 of a file, as USGS publishes it (a checksum, not security)."""
    h = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def md5_of_zip_member(zpath, member):
    """The MD5 of file MEMBER inside zip ZPATH, read without extracting it."""
    h = hashlib.md5(usedforsecurity=False)
    with zipfile.ZipFile(zpath) as z, z.open(member) as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, dst):
    """Downloads URL to the file DST, 1 MiB at a time (10-minute timeout)."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "hickory-sands-ava-fetch/1.0"}
    )
    with urllib.request.urlopen(req, timeout=600) as r, open(dst, "wb") as f:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            f.write(chunk)


def fetch_geotiff(row, folder):
    """Makes sure a quad's GeoTIFF is in FOLDER, inside its own zip.

    A GeoTIFF already there whose MD5 matches is kept; otherwise it is
    downloaded to a temporary folder, checked, then stored in its own zip.

    Args:
        row: The quad's manifest row (geotiff, geotiff_url, geotiff_md5).
        folder: Where its <geotiff>.zip goes.

    Returns:
        True when the zip holds the GeoTIFF the manifest records.
    """
    tif, zpath = row["geotiff"], os.path.join(folder, row["geotiff"] + ".zip")
    if (
        os.path.exists(zpath)
        and md5_of_zip_member(zpath, tif) == row["geotiff_md5"]
    ):
        print(f"ok    {tif}")
        return True
    with tempfile.TemporaryDirectory() as tmp:
        tmpfile = os.path.join(tmp, tif)
        print(f"fetch {tif}")
        download(row["geotiff_url"], tmpfile)
        got = md5_of(tmpfile)
        if got != row["geotiff_md5"]:
            print(
                f"  MD5 MISMATCH {got} != {row['geotiff_md5']}",
                file=sys.stderr,
            )
            return False
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
            z.write(tmpfile, tif)
    return True


def main():
    """Fetches every quad that is missing or fails its MD5; exits 1 on a miss.

    A GeoTIFF is stored in its own zip (fetch_geotiff); a GeoPDF is downloaded
    in place, then checked.
    """
    os.makedirs(TIF_DIR, exist_ok=True)
    os.makedirs(PDF_DIR, exist_ok=True)
    failures = 0
    with open(
        os.path.join(ROOT, "resources", "quads", "quads-manifest.csv"),
        newline="",
    ) as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if not fetch_geotiff(row, TIF_DIR):
            failures += 1
            continue
        # GeoPDF
        pdf, ppath = row["geopdf"], os.path.join(PDF_DIR, row["geopdf"])
        if os.path.exists(ppath) and md5_of(ppath) == row["geopdf_md5"]:
            print(f"ok    {pdf}")
        else:
            print(f"fetch {pdf}")
            download(row["geopdf_url"], ppath)
            got = md5_of(ppath)
            if got != row["geopdf_md5"]:
                print(
                    f"  MD5 MISMATCH {got} != {row['geopdf_md5']}",
                    file=sys.stderr,
                )
                failures += 1
    print(f"done: {len(rows)} quadrangles, {failures} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
