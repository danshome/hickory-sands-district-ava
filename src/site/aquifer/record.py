"""The record of the 3D aquifer page's data, and when that data is stale.

docs/assets/aquifer/record.json says what the data was made from: every
downloaded input as resources/aquifer/inputs.csv pins it (its name, URL,
dates, bytes and SHA-256), every committed input's SHA-256 (the vineyards,
the fault lines, TTB's Llano Uplift AVA, the shifted geology), the
generator's parameters (src/site/aquifer/params.py and the privacy rules),
and the files it wrote with their sizes.

The data is stale when the record a run would write differs from the
committed one, or a file the record lists is missing or not its size, or
the folder holds a file the record does not list. differences() decides it
from the manifest, the committed inputs and the code alone: no network and
none of the downloads, so the build checks it on any machine. Standard
library only.
"""

import csv
import hashlib
import json
import os

from . import params
from . import privacy

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)  # the repository (src/site/aquifer/../../..)
MANIFEST = os.path.join(ROOT, "resources", "aquifer", "inputs.csv")
CACHE = os.path.join(ROOT, "resources", "aquifer", "cache")
OUT = os.path.join(ROOT, "docs", "assets", "aquifer")
RECORD = "record.json"
FIELDS = ("name", "file", "url", "snapshot", "fetched", "bytes", "sha256")
# The committed inputs, by name: paths from the repository's root.
LOCAL = {
    "twdb-gam-faults": "resources/aquifer/twdb-gam-faults-EPSG4269.geojson",
    "ttb-llano-uplift": (
        "resources/ttb/ttb-avas-production-llano-uplift-EPSG4269-NAD83.geojson"
    ),
    "usgs-sgmc-shifted": (
        "resources/geology/usgs-sgmc-geology-shifted-to-naip-EPSG4269.gpkg"
    ),
    "vineyards": "resources/vineyards/vineyards-EPSG4269.geojson",
}


def read_manifest(path=MANIFEST):
    """The downloaded inputs, as resources/aquifer/inputs.csv lists them.

    Args:
        path: The manifest.

    Returns:
        A list of dicts with FIELDS; bytes as an int.

    Raises:
        ValueError: The manifest's columns are not FIELDS, a name is listed
            twice, or a row's bytes or SHA-256 is malformed.
    """
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError(f"{path}: columns must be {', '.join(FIELDS)}")
        rows = []
        for row in reader:
            digest = row["sha256"]
            if len(digest) != 64 or digest.strip("0123456789abcdef"):
                raise ValueError(f"{path}: {row['name']}: bad SHA-256")
            if not row["bytes"].isdigit():
                raise ValueError(f"{path}: {row['name']}: bad byte count")
            rows.append(dict(row, bytes=int(row["bytes"])))
    names = [r["name"] for r in rows]
    if len(names) != len(set(names)):
        raise ValueError(f"{path}: a name is listed twice")
    return rows


def sha256_file(path):
    """A file's SHA-256, as lower-case hex."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def local_digests(root=ROOT):
    """The committed inputs' digests.

    Args:
        root: The repository.

    Returns:
        A dict from LOCAL's names to {"file", "sha256"} ("sha256:" and hex).
    """
    return {
        name: {
            "file": rel,
            "sha256": "sha256:" + sha256_file(os.path.join(root, rel)),
        }
        for name, rel in LOCAL.items()
    }


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
        The record, a JSON-ready dict. Each download's SHA-256 is written
        "sha256:" and hex, as in local.
    """
    record = {
        "about": (
            "What docs/assets/aquifer/ was made from, by "
            "src/site/make_aquifer_3d.py: ./build.sh checks it and "
            "./build.sh site-data makes the data again when it changes"
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


def listing(folder):
    """Every file under a folder but the record, with its size.

    Args:
        folder: docs/assets/aquifer.

    Returns:
        {path relative to folder, with "/": bytes}.
    """
    out = {}
    for top, _, names in os.walk(folder):
        for name in names:
            path = os.path.join(top, name)
            rel = os.path.relpath(path, folder).replace(os.sep, "/")
            if rel != RECORD:
                out[rel] = os.path.getsize(path)
    return out


def differences(old, new, files=None):
    """Why the committed data is stale; empty when it is up to date.

    Args:
        old: The committed record, or None when it is missing or unreadable.
        new: expected() without outputs: what a run would record.
        files: listing() of the committed folder, or None to skip the files.

    Returns:
        A list of short reasons.
    """
    if old is None:
        return ["no record"]
    stale = []
    for part in ("inputs", "local", "parameters"):
        before, after = old.get(part, {}), new[part]
        for key in sorted(set(before) | set(after)):
            if before.get(key) != after.get(key):
                stale.append(f"{part} {key}")
    if files is not None:
        listed = old.get("outputs", {})
        for path in sorted(set(listed) | set(files)):
            if path not in files:
                stale.append(f"{path} is missing")
            elif path not in listed:
                stale.append(f"{path} is not in the record")
            elif files[path] != listed[path]:
                stale.append(
                    f"{path} is {files[path]} bytes, not {listed[path]}"
                )
        if not listed:
            stale.append("the record lists no files")
    return stale


def read_record(folder=OUT):
    """The committed record, or None when it is missing or unreadable."""
    try:
        with open(os.path.join(folder, RECORD), encoding="utf-8") as fh:
            return json.load(fh)
    except OSError, ValueError:  # missing or half written: made again
        return None


def write_text(path, text):
    """Writes a text file whole: a temporary file, then a rename.

    Args:
        path: The file.
        text: Its text; a final newline is added when missing (the
            repository's end-of-file hook wants one).
    """
    if not text.endswith("\n"):
        text += "\n"
    part = path + ".part"
    with open(part, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(part, path)


def write_json(path, data, indent=None):
    """Writes JSON whole, compact unless indent is given, with a newline."""
    separators = (",", ":") if indent is None else (",", ": ")
    text = json.dumps(
        data, ensure_ascii=False, indent=indent, separators=separators
    )
    write_text(path, text)


def write_bytes(path, data):
    """Writes a binary file whole: a temporary file, then a rename."""
    part = path + ".part"
    with open(part, "wb") as fh:
        fh.write(data)
    os.replace(part, path)
