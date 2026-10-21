"""Makes the data of The land page's three wells (docs/land.html).

"Three wells, three rocks" compares an outcrop well on the Hickory
Sandstone Member, a granite well and a deep downdip well. Its data is:

    docs/assets/wells/stats.json   every figure the section shows
                                   (make_site_data.py writes them into the
                                   page's data-figure marks, wells_<name>),
                                   and counts kept for review
    docs/assets/wells/record.json  what it was made from
    the drawings in docs/land.html between the "wells drawing" comments:
                                   the outcrop, granite (the documented
                                   example and the screened gravel view)
                                   and deep wells, each tall and wide, and
                                   step 05's depths to one scale

made from:

- the downloads resources/wells/inputs.csv pins (USGS's State Geologic Map
  Compilation for Texas), and TWDB's driller's reports and the Census
  counties as resources/aquifer/inputs.csv pins them: all fetched into the
  one gitignored cache, resources/aquifer/cache/, when missing, and checked
  against their SHA-256s;
- committed inputs: the cited constants (resources/wells/constants.json),
  and the 3D aquifer page's drill grid, stats and well files, whose
  people's names and addresses are already removed.

The wells are grouped by the mapped rock at each well and, downdip, the
depth to the Hickory layer in TWDB's model (src/site/wells/classify.py);
the figures are src/site/wells/figures.py's, the drawings src/site/wells/
draw.py's. As the other generators do, it makes the data again only when
its record would change, a file it lists is missing or not its size, or the
page's drawings are not the recorded ones; with --check nothing is read but
the manifests, the committed inputs, the page and the record, nothing is
fetched or written, and the exit status is 3 when the data is stale. The
data is written only when the hard checks pass (src/site/wells/verify.py):
water enters each well only through a screen or open hole; every label
fits, and is large enough on a phone; no person's name or address from the
granite example's raw report, and no private word, is in anything written;
every source a drawing names is in the page's list; every file is within
its size budget.

Usage:
    make_wells.py [--check]
"""

import argparse
import json
import os
import shutil
import sys

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ),
)  # the repository: the modules are src.site.wells and src.site.aquifer
from src.site.wells import params
from src.site.wells import record

STALE = 3  # --check's exit status when the data is stale
START = (
    "<!-- wells drawing: {slot} (made by src/site/make_wells.py; never edit "
    "it by hand) -->"
)
END = "<!-- end of the wells drawing: {slot} -->"


load = record.load


def constants():
    """The cited constants' values, by name."""
    return {
        k: v["value"] for k, v in load(record.CONSTANTS).items() if k != "about"
    }


class Reports:
    """The 3D page's cleaned well reports, read a cell at a time."""

    def __init__(self, folder=record.WELLS):
        """Starts with no file read."""
        self.folder = folder
        self.files = {}

    def __call__(self, well):
        """A well's report, from its cell's detail file."""
        cell = well["cell"]
        if cell not in self.files:
            self.files[cell] = load(
                os.path.join(self.folder, f"detail-{cell}.json")
            )
        return self.files[cell][well["uid"]]


def write_page(text, drawings):
    """The page with each drawing between its comments.

    Raises:
        SystemExit: A slot's comments are missing from the page.
    """
    for slot, markup in drawings.items():
        start, end = START.format(slot=slot), END.format(slot=slot)
        a, b = text.find(start), text.find(end)
        if a < 0 or b < a:
            raise SystemExit(f"docs/land.html has no {slot} drawing's comments")
        text = text[: a + len(start)] + markup + text[b:]
    return text


def generate(manifest, local, out_dir):
    """Makes the data, checks it, then writes it.

    Raises:
        SystemExit: A hard check failed; nothing was written.
    """
    from src.site.aquifer import inputs  # noqa: PLC0415 (not for --check)
    from src.site.aquifer import record as aquifer_record  # noqa: PLC0415
    from src.site.wells import classify  # noqa: PLC0415 (GDAL and NumPy)
    from src.site.wells import draw  # noqa: PLC0415
    from src.site.wells import figures  # noqa: PLC0415 (NumPy)
    from src.site.wells import verify  # noqa: PLC0415

    paths = inputs.ensure(manifest, cache=record.CACHE)
    shape = {
        "counties": "cb_2023_us_county_500k.shp",
        "geology": "TX_geol_poly.shp",
    }
    wells = classify.classify(
        {
            "wells": record.WELLS,
            "counties": (
                f"/vsizip/{paths['census-counties']}/{shape['counties']}"
            ),
            "geology": f"/vsizip/{paths['usgs-sgmc-texas']}/{shape['geology']}",
            "grid_json": os.path.join(
                record.ROOT, record.LOCAL["aquifer-drill-grid"]
            ),
            "grid_bin": os.path.join(
                record.ROOT, record.LOCAL["aquifer-drill-grid-bin"]
            ),
        }
    )
    c = constants()
    reports = Reports()
    figs, counts, extra = figures.make(wells, reports, c, len(wells))
    aquifer = load(os.path.join(record.ROOT, record.LOCAL["aquifer-stats"]))
    figs["snapshot"] = aquifer["figures"]["twdb_sdr_snapshot"]
    drawings, drawn = draw.make(figs, extra, params, params.SOURCES)
    print(
        "the wells: "
        + ", ".join(
            f"{k} {counts[f'{k}_wells']:,}"
            for k in ("outcrop", "granite", "deep")
        )
    )
    with open(record.PAGE, encoding="utf-8") as fh:
        page = fh.read()
    new_page = write_page(page, drawings)
    stats = {
        "about": (
            "Every figure docs/land.html's three wells show, made by "
            "src/site/make_wells.py; src/site/make_site_data.py writes them "
            "into the page's data-figure marks (wells_<name>)"
        ),
        "figures": dict(sorted(figs.items())),
        "counts": dict(sorted(counts.items())),
    }
    text = json.dumps(stats, ensure_ascii=False, indent=1)
    personal = verify.personal_values(
        paths["twdb-sdr"], c["granite_example_report"]
    )
    start = new_page.find('id="three-wells"')
    end = new_page.find("</section>", start)
    if start < 0 or end < 0:
        raise SystemExit("docs/land.html has no three-wells section to check")
    section = new_page[start:end]
    bad = verify.flows(drawn)
    bad += verify.labels(drawn)
    bad += verify.privacy(
        {"stats.json": text, "the drawings and the section": section},
        personal,
        aquifer_record.private_words(),
    )
    bad += verify.sources(new_page, params.SOURCES.values())
    new = os.path.join(record.ROOT, "target", "wells-next")
    shutil.rmtree(new, ignore_errors=True)
    os.makedirs(new)
    record.write_text(os.path.join(new, "stats.json"), text)
    bad += verify.sizes(new)
    if bad:
        for problem in bad[:30]:
            print(f"CHECK FAILED: {problem}")
        raise SystemExit(
            f"{len(bad)} check failures: nothing was written; the new data "
            f"is in {new} for inspection"
        )
    files = record.listing(new)
    record.write_json(
        os.path.join(new, record.RECORD),
        record.expected(
            manifest,
            local,
            files,
            record.blocks_digest(record.blocks(new_page)),
        ),
        indent=1,
    )
    record.write_text(record.PAGE, new_page)
    old = os.path.join(record.ROOT, "target", "wells-old")
    shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(out_dir):
        os.replace(out_dir, old)
    os.replace(new, out_dir)
    shutil.rmtree(old, ignore_errors=True)
    print(
        f"wells data: {len(files)} files and {len(drawings)} drawings, "
        "checks passed"
    )


def main():
    """Checks the section's data, or makes it again when it is stale."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--check", action="store_true", help="exit 3 if stale; write nothing"
    )
    args = parser.parse_args()
    out_dir = record.OUT
    manifest = record.read_manifest()
    local = record.local_digests()
    new = record.expected(manifest, local)
    files = record.listing(out_dir) if os.path.isdir(out_dir) else {}
    with open(record.PAGE, encoding="utf-8") as fh:
        page = fh.read()
    stale = record.differences(record.read_record(out_dir), new, files, page)
    if not stale:
        print(f"wells data up to date: {len(files)} files")
        return 0
    if args.check:
        print(
            f"STALE wells data ({'; '.join(stale[:8])}"
            f"{'; ...' if len(stale) > 8 else ''}): run ./build.sh site-data "
            "(it fetches any missing input into resources/aquifer/cache/)",
            file=sys.stderr,
        )
        return STALE
    print(f"wells data stale ({'; '.join(stale[:8])}): making it again")
    generate(manifest, local, out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
