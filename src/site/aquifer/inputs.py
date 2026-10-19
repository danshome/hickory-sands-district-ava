"""The downloaded inputs of the 3D aquifer page, in resources/aquifer/cache/.

Each file resources/aquifer/inputs.csv lists is fetched into the cache when
it is missing, then checked against its byte count and SHA-256. TWDB serves
its well databases as one URL that always gives today's file, so the
manifest pins the snapshot the page was made from, and a different file
stops the run, naming the input: refreshing a snapshot is a deliberate
change to the manifest (BUILD.md says how). Standard library only.
"""

import os
import urllib.request

from . import record

USER_AGENT = "hickory-sands-district-ava build (src/site/make_aquifer_3d.py)"
TIMEOUT_S = 120


def download(url, path):
    """Downloads a URL to a file: a temporary file, then a rename.

    Args:
        url: An https URL from the manifest.
        path: Where the file goes.

    Raises:
        ValueError: The URL is not https.
    """
    if not url.startswith("https://"):
        raise ValueError(f"{url}: not https")
    part = path + ".part"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with (
        urllib.request.urlopen(request, timeout=TIMEOUT_S) as response,
        open(part, "wb") as fh,
    ):
        for block in iter(lambda: response.read(1 << 20), b""):
            fh.write(block)
    os.replace(part, path)


def mismatch(row, path):
    """Why a cached file is not the manifest's snapshot, or None.

    Args:
        row: The input's manifest row.
        path: The cached file.

    Returns:
        A short reason, or None when its size and SHA-256 match.
    """
    size = os.path.getsize(path)
    if size != row["bytes"]:
        return f"{size} bytes, the manifest pins {row['bytes']}"
    digest = record.sha256_file(path)
    if digest != row["sha256"]:
        return f"SHA-256 {digest}, the manifest pins {row['sha256']}"
    return None


def ensure(rows, cache=record.CACHE):
    """Every input in the cache, each checked against the manifest.

    Args:
        rows: record.read_manifest()'s rows.
        cache: The cache folder.

    Returns:
        A dict from each input's name to its cached path.

    Raises:
        SystemExit: A download is not the snapshot the manifest pins.
    """
    os.makedirs(cache, exist_ok=True)
    paths = {}
    for row in rows:
        path = os.path.join(cache, row["file"])
        if not os.path.isfile(path):
            print(f"fetching {row['name']}: {row['url']}")
            download(row["url"], path)
        why = mismatch(row, path)
        if why:
            raise SystemExit(
                f"{row['name']} ({path}): {why}. The source now serves a "
                "different file from the snapshot resources/aquifer/inputs.csv "
                "pins; to move to it, see BUILD.md (refreshing the aquifer "
                "page's inputs)"
            )
        paths[row["name"]] = path
    return paths
