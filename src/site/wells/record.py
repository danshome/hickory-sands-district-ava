"""The record of the three wells' data, and when it is stale.

docs/assets/wells/record.json says what the data was made from: the
downloads it reads (USGS's State Geologic Map Compilation for Texas, which
resources/wells/inputs.csv pins, and TWDB's driller's reports and the
Census counties, as resources/aquifer/inputs.csv pins them for the 3D
aquifer page, all in the one cache), every committed input's SHA-256 (the
cited constants, the drill grid, the 3D page's stats and its well files),
the generator's parameters, the files it wrote with their sizes, and the
SHA-256 of the drawings it wrote into docs/land.html.

As for The land's slice (src/site/land/record.py), the data is stale when
the record a run would write differs from the committed one, a file it
lists is missing or not its size, or the page's drawings are not the ones
recorded; all of it is decided from the manifests, the committed inputs and
the code, with no network and none of the downloads. Standard library only.
"""

import glob
import hashlib
import json
import os
import re

from ..aquifer import privacy
from ..aquifer import record as aquifer_record
from . import params

ROOT = aquifer_record.ROOT
MANIFEST = os.path.join(ROOT, "resources", "wells", "inputs.csv")
CONSTANTS = os.path.join(ROOT, "resources", "wells", "constants.json")
AQUIFER_MANIFEST = aquifer_record.MANIFEST
CACHE = aquifer_record.CACHE
OUT = os.path.join(ROOT, "docs", "assets", "wells")
PAGE = os.path.join(ROOT, "docs", "land.html")
RECORD = aquifer_record.RECORD
FROM_AQUIFER = ("twdb-sdr", "census-counties")
LOCAL = {
    "wells-constants": "resources/wells/constants.json",
    "aquifer-drill-grid": "docs/assets/aquifer/drill-grid.json",
    "aquifer-drill-grid-bin": "docs/assets/aquifer/drill-grid.bin",
    "aquifer-stats": "docs/assets/aquifer/stats.json",
}
WELLS = os.path.join(ROOT, "docs", "assets", "aquifer", "wells")
# A drawing in the page: between these two comments, by its slot's name.
BLOCK = re.compile(
    r"<!-- wells drawing: (?P<slot>[a-z-]+) \(made by src/site/make_wells\.py;"
    r" never edit it by hand\) -->(?P<body>.*?)"
    r"<!-- end of the wells drawing: (?P=slot) -->",
    re.DOTALL,
)

sha256_file = aquifer_record.sha256_file
listing = aquifer_record.listing
write_json = aquifer_record.write_json
write_text = aquifer_record.write_text
read_record = aquifer_record.read_record


def read_manifest():
    """Every download read: this manifest's rows, then the aquifer's two."""
    rows = aquifer_record.read_manifest(MANIFEST)
    shared = {
        r["name"]: r for r in aquifer_record.read_manifest(AQUIFER_MANIFEST)
    }
    for name in FROM_AQUIFER:
        if name not in shared:
            raise ValueError(f"{AQUIFER_MANIFEST}: no {name}")
        rows.append(shared[name])
    return rows


def wells_files(wells=WELLS):
    """The 3D page's drawing records and reports, sorted."""
    return sorted(
        glob.glob(os.path.join(wells, "draw-*.json"))
        + glob.glob(os.path.join(wells, "detail-*.json"))
    )


def local_digests(root=ROOT, wells=WELLS):
    """The committed inputs' digests, the well files' as one."""
    out = {
        name: {
            "file": rel,
            "sha256": "sha256:" + sha256_file(os.path.join(root, rel)),
        }
        for name, rel in LOCAL.items()
    }
    digest = hashlib.sha256()
    files = wells_files(wells)
    for path in files:
        digest.update(os.path.basename(path).encode("utf-8"))
        digest.update(sha256_file(path).encode("ascii"))
    out["aquifer-wells"] = {
        "file": "docs/assets/aquifer/wells/ (drawing records and reports)",
        "files": len(files),
        "sha256": "sha256:" + digest.hexdigest(),
    }
    return out


def parameters():
    """Every parameter of the generator, as the record keeps them."""
    keys = sorted(k for k in vars(params) if k.isupper())
    out = {k.lower(): getattr(params, k) for k in keys}
    out["privacy_rules"] = privacy.rules_digest()
    out["code"] = code_digest()
    return json.loads(json.dumps(out))


def code_digest():
    """One SHA-256 of the generator's code: make_wells.py and wells/*.py."""
    here = os.path.dirname(os.path.abspath(__file__))
    files = sorted(glob.glob(os.path.join(here, "*.py")))
    files.append(os.path.join(os.path.dirname(here), "make_wells.py"))
    digest = hashlib.sha256()
    for path in files:
        digest.update(os.path.basename(path).encode("utf-8"))
        digest.update(sha256_file(path).encode("ascii"))
    return "sha256:" + digest.hexdigest()


def load(path):
    """A JSON file's data."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def blocks(text):
    """The page's drawings: {slot: markup}."""
    return {m["slot"]: m["body"] for m in BLOCK.finditer(text)}


def blocks_digest(found):
    """One SHA-256 of the drawings, by slot."""
    digest = hashlib.sha256()
    for slot in sorted(found):
        digest.update(slot.encode("utf-8"))
        digest.update(found[slot].encode("utf-8"))
    return "sha256:" + digest.hexdigest()


def expected(manifest, local, outputs=None, page=None):
    """The record a run would write.

    Args:
        manifest: read_manifest()'s rows.
        local: local_digests().
        outputs: The files written, {path: bytes}; None leaves them out.
        page: blocks_digest() of the drawings written; None leaves it out.

    Returns:
        The record, a JSON-ready dict.
    """
    record = {
        "about": (
            "What docs/assets/wells/ and the three wells' drawings in "
            "docs/land.html were made from, by src/site/make_wells.py: "
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
    if page is not None:
        record["page"] = page
    return record


def differences(old, new, files=None, page_text=None):
    """Why the data is stale: the aquifer's reasons, and the page's.

    Args:
        old: The committed record, or None.
        new: expected() without outputs.
        files: listing() of the committed folder.
        page_text: docs/land.html's text, or None to skip it.

    Returns:
        A list of short reasons; empty when the data is up to date.
    """
    stale = aquifer_record.differences(old, new, files)
    if old is not None and page_text is not None:
        found = blocks(page_text)
        if set(found) != set(params.SLOTS):
            stale.append(
                "docs/land.html's drawings are not the slots "
                + ", ".join(params.SLOTS)
            )
        elif blocks_digest(found) != old.get("page"):
            stale.append("docs/land.html's drawings are not the recorded ones")
    return stale
