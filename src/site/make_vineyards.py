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
parameters, the files written with their sizes and the data's stamp: a short
SHA-256 of every file written, which changes whenever any of them does. The
pages fetch the record unstamped and revalidated (docs/assets/vineyard-data.js)
and load each vineyard file as name?v=stamp, so a browser that cached the old
data for GitHub Pages' ten minutes gets the new data at once after a merge.
The data is made again only when that record would change, or a file it lists
is missing or not its size, or the stamp is not the files'; with --check
nothing is written, and the exit status is 3 when the data is stale. Every
file is written into a new folder that replaces the old one only when every
file is under the hooks' 2 MB.

It also writes the vineyards page's list (#171) between two markers in
docs/vineyards.html, from register.json, so the page names every vineyard
without JavaScript; docs/assets/vineyard-list.js draws the list again with
its buttons. The list is stale, like the data, when it differs from what
register.json would make. Standard library only.

Usage:
    make_vineyards.py [--check] [--root DIR]
"""

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # src/site
from aquifer import params
from aquifer import record
from aquifer import vineyards

STALE = 3  # --check's exit status when the data is stale
STAMP_DIGITS = 7  # hex digits of the stamp, as the scripts' (stamp_assets.py)
OUT = os.path.join("docs", "assets", "vineyards")
INPUTS = {
    "vineyards": "resources/vineyards/vineyards-EPSG4269.geojson",
    "wells": "docs/assets/aquifer/wells",
    "context": "docs/assets/aquifer/context.geojson",
}

PAGE = os.path.join("docs", "vineyards.html")
START = (
    "<!-- vineyard list: made by src/site/make_vineyards.py from "
    "the vineyard data's register.json; never edit it by hand -->"
)
END = "<!-- end of the vineyard list -->"
# The list's groups and their headings, as docs/assets/vineyard-list.js has
# them (GROUPS there; a test checks the two agree).
GROUPS = (
    ("hsd", "In the proposed Hickory Sands District"),
    ("llano-uplift", "Elsewhere in the proposed Llano Uplift AVA"),
    ("under-development", "Under development"),
    ("historical", "Historical"),
)
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


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


def data_stamp(folder):
    """The stamp of the vineyard data: a short SHA-256 of every file.

    Every file but the record is hashed with its path, in path order, so the
    stamp changes whenever any file's name or bytes change.

    Args:
        folder: The data's folder (docs/assets/vineyards).

    Returns:
        STAMP_DIGITS hex digits.
    """
    digest = hashlib.sha256()
    for rel in sorted(record.listing(folder)):
        digest.update(rel.encode("utf-8") + b"\0")
        digest.update(record.sha256_file(os.path.join(folder, rel)).encode())
        digest.update(b"\n")
    return digest.hexdigest()[:STAMP_DIGITS]


def expected(local, outputs=None, stamp=None):
    """The record a run would write.

    Args:
        local: local_digests().
        outputs: The files written, {path: bytes}; None leaves them out.
        stamp: data_stamp() of the files written; None leaves it out.

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
    if stamp is not None:
        out["stamp"] = stamp
    return out


def data_reasons(root):
    """Why the committed data is stale; empty when it is up to date."""
    out_dir = os.path.join(root, OUT)
    new = dict(expected(local_digests(root)), inputs={})
    files = record.listing(out_dir) if os.path.isdir(out_dir) else {}
    old = record.read_record(out_dir)
    stale = record.differences(old, new, files)
    if (
        old is not None
        and os.path.isdir(out_dir)
        and old.get("stamp") != data_stamp(out_dir)
    ):
        stale.append("stamp is not the data's")
    return stale


def stale_reasons(root):
    """Why the data or the page's list is stale; empty when up to date."""
    return data_reasons(root) + page_reasons(root)


def _row(entry):
    """One vineyard's row of the list, as vineyard-list.js's row() makes it.

    Args:
        entry: One entry of register.json.

    Returns:
        The row's HTML; every text from the data escaped.
    """
    name = html.escape(entry["name"], quote=True)
    n = len(entry["vids"])
    facts = [f"{n} block{'' if n == 1 else 's'}"]
    if entry.get("year"):
        facts.append(f"first planted {int(entry['year'])}")
    text = (
        f'<h4 class="vy-name">{name}</h4>'
        f'<p class="vy-facts">{html.escape(" · ".join(facts))}</p>'
    )
    if entry.get("varieties"):
        varieties = html.escape(", ".join(entry["varieties"]))
        text += f'<p class="vy-varieties">{varieties}</p>'
    out = f'<li class="vy-row"><div class="vy-text">{text}</div>'
    # "Suggest a change": vineyard-wizard.js opens the form from the address
    vid = entry.get("id")
    if isinstance(vid, str) and SLUG.match(vid):
        out += (
            f'<div class="vy-actions"><a class="vy-change" '
            f'href="#change={vid}" aria-label="Suggest a change to {name}">'
            "Suggest a change</a></div>"
        )
    return out + "</li>"


def render_list(entries):
    """The page's list of vineyards, grouped as vineyard-list.js groups it.

    Args:
        entries: register.json's "vineyards".

    Returns:
        The HTML between the markers, lines ending in a newline.
    """
    lines = []
    for category, heading in GROUPS:
        found = [e for e in entries if e["category"] == category]
        if not found:
            continue
        hid = f"vy-{category}"
        lines.append(
            f'<section class="vy-group" aria-labelledby="{hid}">'
            f'<h3 class="vy-heading" id="{hid}">{html.escape(heading)}</h3>'
            '<ul class="vy-rows">'
        )
        lines += [_row(e) for e in found]
        lines.append("</ul></section>")
    return "".join(f"{line}\n" for line in lines)


def _page_parts(text):
    """The page split at the markers: before, the list, after; or None."""
    if text.count(START) != 1 or text.count(END) != 1:
        return None
    head, rest = text.split(START, 1)
    body, tail = rest.split(END, 1)
    if not body.startswith("\n"):
        return None
    return head + START + "\n", body[1:], END + tail


def _wanted_list(root):
    """The list register.json makes, or None when it cannot be read."""
    try:
        with open(
            os.path.join(root, OUT, "register.json"), encoding="utf-8"
        ) as fh:
            return render_list(json.load(fh)["vineyards"])
    except OSError, ValueError, KeyError:
        return None


def page_reasons(root):
    """Why the page's list is stale; empty when it is up to date."""
    try:
        with open(os.path.join(root, PAGE), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return [f"{PAGE} is missing"]
    parts = _page_parts(text)
    if parts is None:
        return [f"{PAGE} has not its two vineyard-list markers"]
    want = _wanted_list(root)
    if want is None:
        return []  # no register.json: data_reasons() says so
    return [] if parts[1] == want else [f"{PAGE}'s vineyard list"]


def write_list(root):
    """Writes the page's list from register.json when it differs.

    Args:
        root: The repository.

    Raises:
        SystemExit: The page, its markers or register.json are missing.
    """
    where = os.path.join(root, PAGE)
    with open(where, encoding="utf-8") as fh:
        text = fh.read()
    parts = _page_parts(text)
    if parts is None:
        raise SystemExit(f"{PAGE}: the vineyard list's markers are missing")
    want = _wanted_list(root)
    if want is None:
        raise SystemExit(f"{OUT}/register.json could not be read")
    if parts[1] == want:
        return
    with open(where, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(parts[0] + want + parts[2])
    print(f"{PAGE}: the vineyard list written")


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
        expected(local_digests(root), files, data_stamp(new)),
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
    if data_reasons(args.root):
        print(f"vineyard data stale ({'; '.join(stale[:8])}): making it again")
        words = record.private_words()
        print(f"{len(words)} more words to refuse from the private lists")
        generate(args.root, words)
    write_list(args.root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
