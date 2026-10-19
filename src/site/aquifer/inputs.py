"""The downloaded inputs of the 3D aquifer page, in resources/aquifer/cache/.

Each file resources/aquifer/inputs.csv lists is fetched into the cache when
it is missing, then checked against its byte count and SHA-256. TWDB serves
its well databases as one URL that always gives today's file, so the
manifest pins the snapshot the page was made from, and a different file
stops the run, naming the input: refreshing a snapshot is a deliberate
change to the manifest (BUILD.md says how). Standard library only.
"""

import contextlib
import os
import urllib.request

from . import record

USER_AGENT = "hickory-sands-district-ava build (src/site/make_aquifer_3d.py)"
TIMEOUT_S = 120


def download(url, path):
    """Downloads a URL to a file.

    Args:
        url: An https URL from the manifest.
        path: Where the file goes (ensure() gives a ".part" name, renamed
            only once the file matches the manifest).

    Raises:
        ValueError: The URL is not https.
    """
    if not url.startswith("https://"):
        raise ValueError(f"{url}: not https")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with (
        urllib.request.urlopen(request, timeout=TIMEOUT_S) as response,
        open(path, "wb") as fh,
    ):
        for block in iter(lambda: response.read(1 << 20), b""):
            fh.write(block)


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
            # Fetched into a ".part" file, kept only when it is the pinned
            # snapshot, so a wrong download never stays in the cache.
            print(f"fetching {row['name']}: {row['url']}")
            part = path + ".part"
            try:
                download(row["url"], part)
                why = mismatch(row, part)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.remove(part)
                raise
            if why:
                os.remove(part)
                raise SystemExit(
                    f"{row['name']}: the download is {why}, so it was "
                    "deleted. The source now serves a different file from "
                    "the snapshot resources/aquifer/inputs.csv pins; to move "
                    "to it, see BUILD.md (refreshing the aquifer page's "
                    "inputs)"
                )
            os.replace(part, path)
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
