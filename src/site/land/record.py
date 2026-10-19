"""The record of The land page's data, and when that data is stale.

docs/assets/land/record.json says what the data was made from: the
downloads it reads (the USGS 3DEP tiles resources/aquifer/land-inputs.csv
pins, and TWDB's model archive from resources/aquifer/inputs.csv, read from
the same cache as the 3D aquifer page's), every committed input's SHA-256
(the row 239 line and the fault lines, the shifted geology, the site's
boundary, and the 3D aquifer page's files it reads: the Precambrian outcrop,
the well heads and reports in the maps' frame, and its stats), the
generator's parameters (src/site/land/params.py and a digest of the privacy
rules), and the files it wrote with their sizes.

As for the 3D aquifer page (src/site/aquifer/record.py, whose helpers this
uses), the data is stale when the record a run would write differs from the
committed one, or a file the record lists is missing or not its size;
differences() decides it from the manifests, the committed inputs and the
code alone, with no network and none of the downloads. Standard library
only.
"""

import glob
import hashlib
import json
import math
import os

from ..aquifer import privacy
from ..aquifer import record as aquifer_record
from . import params

ROOT = aquifer_record.ROOT
MANIFEST = os.path.join(ROOT, "resources", "aquifer", "land-inputs.csv")
AQUIFER_MANIFEST = aquifer_record.MANIFEST
CACHE = aquifer_record.CACHE  # one cache for the site's downloads
OUT = os.path.join(ROOT, "docs", "assets", "land")
RECORD = aquifer_record.RECORD
# The 3D aquifer page's downloads this page reads too.
FROM_AQUIFER = ("twdb-gam",)
# The committed inputs, by name: paths from the repository's root.
LOCAL = {
    "twdb-gam-row239": "resources/aquifer/twdb-gam-row239-EPSG4269.geojson",
    "twdb-gam-faults": "resources/aquifer/twdb-gam-faults-EPSG4269.geojson",
    "usgs-sgmc-shifted": (
        "resources/geology/usgs-sgmc-geology-shifted-to-naip-EPSG4269.gpkg"
    ),
    "site-boundary": "docs/data/boundary.geojson",
    "aquifer-precambrian": "docs/assets/aquifer/precambrian.geojson",
    "aquifer-stats": "docs/assets/aquifer/stats.json",
}
WELLS = os.path.join(ROOT, "docs", "assets", "aquifer", "wells")

# The helpers the 3D aquifer page's record already has.
sha256_file = aquifer_record.sha256_file
listing = aquifer_record.listing
differences = aquifer_record.differences
write_json = aquifer_record.write_json
write_text = aquifer_record.write_text


def read_manifest():
    """Every download this page reads, as its manifest rows.

    Returns:
        resources/aquifer/land-inputs.csv's rows, then the 3D aquifer page's
        rows FROM_AQUIFER names (aquifer_record.read_manifest()'s form).

    Raises:
        ValueError: A manifest is malformed, an input is named twice, or a
            FROM_AQUIFER input is missing from the aquifer's manifest.
    """
    rows = aquifer_record.read_manifest(MANIFEST)
    shared = {
        r["name"]: r for r in aquifer_record.read_manifest(AQUIFER_MANIFEST)
    }
    for name in FROM_AQUIFER:
        if name not in shared:
            raise ValueError(f"{AQUIFER_MANIFEST}: no {name}")
        rows.append(shared[name])
    names = [r["name"] for r in rows]
    if len(names) != len(set(names)):
        raise ValueError(f"{MANIFEST}: a name is also the aquifer's")
    return rows


def frame_cells():
    """The well report cells (detail files) the maps' frame touches.

    Returns:
        The sorted cell keys ("-1990_613"), as rules.detail_cell() names
        them.
    """
    west, south, east, north = params.FRAME
    step = params.DETAIL_DEG
    return sorted(
        f"{x}_{y}"
        for x in range(math.floor(west / step), math.floor(east / step) + 1)
        for y in range(math.floor(south / step), math.floor(north / step) + 1)
    )


def wells_files(wells=WELLS):
    """The 3D aquifer page's well files this page reads.

    Args:
        wells: Its wells folder.

    Returns:
        The sorted paths: every heads file, and each detail file of a cell
        in the maps' frame that exists.
    """
    heads = glob.glob(os.path.join(wells, "heads-*.json"))
    details = [
        os.path.join(wells, f"detail-{cell}.json") for cell in frame_cells()
    ]
    return sorted(heads + [p for p in details if os.path.exists(p)])


def wells_digest(wells=WELLS):
    """One digest of the well files read: each file's name and SHA-256.

    Args:
        wells: The 3D aquifer page's wells folder.

    Returns:
        "sha256:" and the hex digest, and the number of files.
    """
    digest = hashlib.sha256()
    files = wells_files(wells)
    for path in files:
        digest.update(os.path.basename(path).encode("utf-8"))
        digest.update(sha256_file(path).encode("ascii"))
    return "sha256:" + digest.hexdigest(), len(files)


def local_digests(root=ROOT, wells=WELLS):
    """The committed inputs' digests.

    Args:
        root: The repository.
        wells: The 3D aquifer page's wells folder.

    Returns:
        A dict from LOCAL's names, and "aquifer-wells", to {"file",
        "sha256"} ("sha256:" and hex); the wells' entry also counts its
        files.
    """
    out = {
        name: {
            "file": rel,
            "sha256": "sha256:" + sha256_file(os.path.join(root, rel)),
        }
        for name, rel in LOCAL.items()
    }
    digest, count = wells_digest(wells)
    out["aquifer-wells"] = {
        "file": "docs/assets/aquifer/wells/ (heads, and the frame's reports)",
        "files": count,
        "sha256": digest,
    }
    return out


def parameters():
    """Every parameter of the generator, as the record keeps them."""
    keys = sorted(k for k in vars(params) if k.isupper())
    out = {k.lower(): getattr(params, k) for k in keys}
    out["privacy_rules"] = privacy.rules_digest()
    return json.loads(json.dumps(out))  # tuples as lists, as read back


def expected(manifest, local, outputs=None):
    """The record a run would write.

    Args:
        manifest: read_manifest()'s rows.
        local: local_digests().
        outputs: The files written, {path: bytes}; None leaves them out.

    Returns:
        The record, a JSON-ready dict.
    """
    record = {
        "about": (
            "What docs/assets/land/ was made from, by src/site/make_land.py: "
            "./build.sh checks it and ./build.sh site-data makes the data "
            "again when it changes"
        ),
        "inputs": {
            row["name"]: {
                "file": row["file"],
                "url": row["url"],
                "snapshot": row["snapshot"],
                "fetched": row["fetched"],
                "bytes": row["bytes"],
                "sha256": "sha256:" + row["sha256"],
            }
            for row in manifest
        },
        "local": local,
        "parameters": parameters(),
    }
    if outputs is not None:
        record["outputs"] = dict(sorted(outputs.items()))
    return record


def read_record(folder=OUT):
    """The committed record, or None when it is missing or unreadable."""
    return aquifer_record.read_record(folder)
