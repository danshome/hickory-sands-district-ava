"""Makes the website's vineyard data (docs/assets/vineyards/).

The vineyards page (docs/vineyards.html) lists the vineyards and the 3D
aquifer page (docs/aquifer.html) draws their blocks, each with the TWDB
wells near it. Their data is made here, apart from the rest of the 3D page's
data, from committed files only:

- resources/vineyards/vineyards-EPSG4269.geojson, the vineyard blocks (see
  its README.md);
- docs/assets/aquifer/wells/index.json and its drawing tiles draw-*.json,
  every well the 3D page draws, as src/site/make_aquifer_3d.py wrote them;
- docs/assets/aquifer/context.geojson, for the county lines.

So it needs none of the 3D page's downloads, and it runs anywhere: on Dan's
Mac (./build.sh site-data), in the build's check (./build.sh), and on
GitHub's runners, where the vineyard-approve Action makes the data of a
vineyard sent through the website's form (src/vineyards/approve.py).
src/site/aquifer/vineyards.py says what each file holds.

docs/assets/vineyards/record.json records the inputs' SHA-256s, the
parameters and the files written with their sizes. The data is made again
only when that record would change, or a file it lists is missing or not
its size; with --check nothing is written, and the exit status is 3 when
the data is stale. Every file is written into a new folder that replaces
the old one only when every file is under the hooks' 2 MB. Standard library
only.

Usage:
    make_vineyards.py [--check] [--root DIR]
"""

import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # src/site
from aquifer import params
from aquifer import record
from aquifer import vineyards

STALE = 3  # --check's exit status when the data is stale
OUT = os.path.join("docs", "assets", "vineyards")
INPUTS = {
    "vineyards": "resources/vineyards/vineyards-EPSG4269.geojson",
    "wells": "docs/assets/aquifer/wells",
    "context": "docs/assets/aquifer/context.geojson",
}


def paths(root):
    """The inputs, by name, as paths under root."""
    return {name: os.path.join(root, rel) for name, rel in INPUTS.items()}


def local_digests(root):
    """The inputs' digests: each file's SHA-256, the well tiles' digest.

    Args:
        root: The repository.

    Returns:
        A dict from INPUTS' names to {"file", "sha256"} ("sha256:" and hex).
    """
    where = paths(root)
    return {
        "vineyards": {
            "file": INPUTS["vineyards"],
            "sha256": "sha256:" + record.sha256_file(where["vineyards"]),
        },
        "wells": {
            "file": INPUTS["wells"] + "/index.json and draw-*.json",
            "sha256": vineyards.tiles_digest(where["wells"]),
        },
        "context": {
            "file": INPUTS["context"],
            "sha256": "sha256:" + record.sha256_file(where["context"]),
        },
    }


def parameters():
    """Every parameter of the vineyard data, as the record keeps them."""
    out = {
        "version": vineyards.VERSION,
        "fields": vineyards.FIELDS,
        "wells_m": vineyards.WELLS_M,
        "categories": vineyards.CATEGORIES,
        "counties": vineyards.COUNTIES,
        "privacy_rules": vineyards.rules_digest(),
    }
    return json.loads(json.dumps(out))  # tuples as lists, as read back


def expected(local, outputs=None):
    """The record a run would write.

    Args:
        local: local_digests().
        outputs: The files written, {path: bytes}; None leaves them out.

    Returns:
        The record, a JSON-ready dict.
    """
    out = {
        "about": (
            "What docs/assets/vineyards/ was made from, by "
            "src/site/make_vineyards.py: ./build.sh checks it and "
            "./build.sh site-data makes the data again when it changes"
        ),
        "local": local,
        "parameters": parameters(),
    }
    if outputs is not None:
        out["outputs"] = dict(sorted(outputs.items()))
    return out


def stale_reasons(root):
    """Why the committed data is stale; empty when it is up to date."""
    out_dir = os.path.join(root, OUT)
    new = dict(expected(local_digests(root)), inputs={})
    files = record.listing(out_dir) if os.path.isdir(out_dir) else {}
    return record.differences(record.read_record(out_dir), new, files)


def stats(figures):
    """The vineyard figures the pages show, as stats.json holds them."""
    return {
        "about": (
            "Every vineyard figure docs/aquifer.html and docs/vineyards.html "
            "show, made by src/site/make_vineyards.py; the pages format them"
        ),
        "figures": dict(sorted(figures.items())),
    }


def generate(root, words=()):
    """Makes every file of the vineyard data, then swaps the folder in.

    Args:
        root: The repository.
        words: More words never to publish (.private-words).

    Raises:
        SystemExit: A block names someone or has no category, or a file is
            2 MB or more; the old data is left as it was.
    """
    out_dir = os.path.join(root, OUT)
    new = os.path.join(root, "target", "vineyards-next")
    shutil.rmtree(new, ignore_errors=True)
    os.makedirs(new)
    figures = vineyards.write(paths(root), new, words)
    record.write_json(os.path.join(new, "stats.json"), stats(figures), indent=1)
    files = record.listing(new)
    big = {p: n for p, n in files.items() if n >= params.MAX_FILE_BYTES}
    if big:
        raise SystemExit(
            f"files of 2 MB or more (the hooks refuse them): {big}"
        )
    record.write_json(
        os.path.join(new, record.RECORD),
        expected(local_digests(root), files),
        indent=1,
    )
    old = os.path.join(root, "target", "vineyards-old")
    shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(out_dir):
        os.replace(out_dir, old)
    os.replace(new, out_dir)
    shutil.rmtree(old, ignore_errors=True)
    print(
        f"vineyard data: {figures['vineyard_blocks']} blocks, "
        f"{len(files)} files, {sum(files.values()):,} bytes"
    )


def main(argv=None):
    """Checks the vineyard data, or makes it again when it is stale.

    Args:
        argv: The command line's arguments (sys.argv[1:] when None).

    Returns:
        The exit status: 0, or STALE with --check when the data is stale.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--check", action="store_true", help="exit 3 if stale; write nothing"
    )
    parser.add_argument(
        "--root", default=record.ROOT, help="the repository (default: this)"
    )
    args = parser.parse_args(argv)
    stale = stale_reasons(args.root)
    if not stale:
        print("vineyard data up to date")
        return 0
    if args.check:
        print(
            f"STALE vineyard data ({'; '.join(stale[:8])}"
            f"{'; ...' if len(stale) > 8 else ''}): run ./build.sh site-data, "
            "or src/site/make_vineyards.py",
            file=sys.stderr,
        )
        return STALE
    print(f"vineyard data stale ({'; '.join(stale[:8])}): making it again")
    words = record.private_words()
    print(f"{len(words)} more words to refuse from the private lists")
    generate(args.root, words)
    return 0


if __name__ == "__main__":
    sys.exit(main())
