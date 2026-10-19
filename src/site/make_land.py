"""Makes the data of The land page's slice and maps (docs/land.html).

"Sand, height and water" shows four small maps of one frame (src/site/land/
maps.py) and "A slice through the district" part of TWDB's section line
A-A', model row 239, drawn to scale with real wells (src/site/land/
section.py). Their data is docs/assets/land/:

    section.json      what docs/assets/land.js draws along the slice
    section.svg       the same, every layer shown, for readers without
                      JavaScript and for print
    map-elevation.svg, map-sand.svg, map-water.svg, map-together.svg,
    locator.svg       the four maps and the slice's locator
    stats.json        every figure the page shows (make_site_data.py writes
                      them into the page's data-figure marks), and counts
    record.json       what it was made from

made from:

- the downloads resources/aquifer/land-inputs.csv pins (the four USGS 3DEP
  1 arc-second tiles) and TWDB's model archive, as resources/aquifer/
  inputs.csv pins it for the 3D aquifer page: both are fetched into the one
  gitignored cache, resources/aquifer/cache/, when missing, and checked
  against their SHA-256s; the model's GeoPackage is the one the 3D page's
  generator extracts there;
- committed inputs: TWDB's row 239 line and fault lines (resources/
  aquifer/), the shifted geology, the site's boundary (docs/data/), and the
  3D aquifer page's Precambrian outcrop, stats and well files, whose
  people's names and addresses are already removed.

As make_aquifer_3d.py does, it makes the data again only when its record
would change, or a file it lists is missing or not its size; with --check
nothing is read but the manifests, the committed inputs and the record,
nothing is fetched or written, and the exit status is 3 when the data is
stale. Nothing is written when a map's outline or its wells, or a part of
the slice, comes out empty (an input that misses the frame). Every file is
written into a new folder that replaces the old one only when three hard
checks pass: only a report number and its driller's cleaned words leave the
build for each well; section.json agrees with stats.json and with the
parameters land.js draws by; and every file is within its size budget.

Usage:
    make_land.py [--check]
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
)  # the repository: the modules are src.site.land and src.site.aquifer
from src.site.land import params
from src.site.land import record

STALE = 3  # --check's exit status when the data is stale


def drawings():
    """The maps and the locator: each file, its kind and its title."""
    rule = f"{params.RULE_FT:,} feet"
    return (
        (
            "map-elevation.svg",
            "high",
            f"Ground at {rule} and higher, with the proposed district",
        ),
        (
            "map-sand.svg",
            "sand",
            (
                "The Hickory Sandstone Member formation and the Precambrian "
                "rock of TWDB's model, with the proposed district"
            ),
        ),
        (
            "map-water.svg",
            "water",
            (
                "Wells coloured by the first rock their drillers name, with "
                "the proposed district"
            ),
        ),
        (
            "map-together.svg",
            "together",
            f"The formation at {rule} and higher, with the proposed district",
        ),
        (
            "locator.svg",
            "locator",
            (
                "Where the slice runs, from its north-west end to its "
                "south-east end, across the proposed district, over the "
                "formation and the Precambrian rock"
            ),
        ),
    )


SECTION_LABEL = (
    "A slice from north-west to south-east through the proposed district, "
    "along part of TWDB's section line A to A-prime: the ground, the Hickory "
    "Sandstone Member formation and the Hickory Aquifer within it, the "
    "younger rock above it and the Precambrian rock below it, real wells, "
    "and the district"
)


def load(path):
    """A JSON file's data."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class Reports:
    """The 3D aquifer page's cleaned well reports, read a cell at a time."""

    def __init__(self, folder=record.WELLS):
        """Starts with no file read.

        Args:
            folder: The 3D aquifer page's wells folder.
        """
        self.folder = folder
        self.files = {}
        self.cells = {}

    def get(self, cell, uid):
        """A well's report, from its cell's detail file."""
        if cell not in self.files:
            self.files[cell] = load(
                os.path.join(self.folder, f"detail-{cell}.json")
            )
        self.cells[uid] = cell
        return self.files[cell][uid]

    def of(self, uid):
        """A well's report by its uid alone, once get() has found it."""
        return self.get(self.cells[uid], uid)


def page_figures(figures, counts):
    """The figures the page shows, as stats.json holds them.

    Args:
        figures: The section's and the maps' figures.
        counts: The section's and the maps' counts.

    Returns:
        stats.json's dict: "figures" (each one a data-figure on the page,
        named without its "land_") and "counts" (the rest, for review).
    """
    return {
        "about": (
            "Every figure docs/land.html's slice and maps show, made by "
            "src/site/make_land.py; src/site/make_site_data.py writes them "
            "into the page's data-figure marks (land_<name>)"
        ),
        "figures": dict(sorted(figures.items())),
        "counts": dict(sorted(counts.items())),
    }


def and_list(words):
    """Words joined as the page writes a list: "a", "a and b", "a, b and c"."""
    words = list(words)
    return (
        ", ".join(words[:-1]) + (" and " if len(words) > 1 else "") + words[-1]
    )


def tile_figures(manifest):
    """The 3DEP tiles and their years, as the page's source gives them.

    Args:
        manifest: record.read_manifest()'s rows.

    Returns:
        dem_years ("2022 and 2025") and dem_tiles ("n31w100 and n32w100
        (2022), n31w099 and n32w099 (2025)"), each tile by the year of its
        snapshot (the file's Last-Modified date), in the manifest's order.
    """
    years = {}
    for row in manifest:
        if row["name"] in params.DEM_TILES:
            tile = row["name"].rsplit("-", 1)[1]
            years.setdefault(row["snapshot"][:4], []).append(tile)
    order = sorted(years)
    return {
        "dem_years": and_list(order),
        "dem_tiles": ", ".join(f"{and_list(years[y])} ({y})" for y in order),
    }


def aquifer_figures(stats_path):
    """The figures this page takes from the 3D aquifer page's stats.

    Args:
        stats_path: docs/assets/aquifer/stats.json.

    Returns:
        geology_shift_m (the geology's shift, to the nearest 100 m) and
        wells_snapshot (the well databases' date, ISO).

    Raises:
        SystemExit: The two well databases' snapshots differ, so the
            page's one date would not hold.
    """
    figs = load(stats_path)["figures"]
    sdr, gwdb = figs["twdb_sdr_snapshot"], figs["twdb_gwdb_snapshot"]
    if sdr != gwdb:
        raise SystemExit(
            f"the driller's reports ({sdr}) and the Groundwater Database "
            f"({gwdb}) are of different dates: the page's source gives one"
        )
    return {
        "geology_shift_m": int(round(figs["shift_m"], -2)),
        "wells_snapshot": sdr,
    }


def generate(manifest, local, out_dir):
    """Makes every file of the page's data, then swaps the folder in.

    Args:
        manifest: record.read_manifest()'s rows.
        local: record.local_digests().
        out_dir: docs/assets/land.

    Raises:
        SystemExit: A hard check failed; the old data is left as it was.
    """
    from src.site.aquifer import inputs  # noqa: PLC0415 (not for --check)
    from src.site.aquifer import model  # noqa: PLC0415 (GDAL and NumPy)
    from src.site.aquifer import record as aquifer_record  # noqa: PLC0415
    from src.site.land import draw  # noqa: PLC0415
    from src.site.land import maps  # noqa: PLC0415 (GDAL and NumPy)
    from src.site.land import section  # noqa: PLC0415 (GDAL)
    from src.site.land import verify  # noqa: PLC0415

    paths = inputs.ensure(manifest, cache=record.CACHE)
    paths["gpkg"] = model.extract_gam(paths["twdb-gam"], record.CACHE)
    paths.update(
        {
            name: os.path.join(record.ROOT, rel)
            for name, rel in record.LOCAL.items()
        }
    )
    paths["heads"] = [
        p
        for p in record.wells_files()
        if os.path.basename(p).startswith("heads-")
    ]
    reports = Reports()
    sec, figures, counts = section.make(paths, reports.get)
    print(
        f"the slice: {counts['columns']} model cells, "
        f"{figures['wells_on_section']} wells"
    )
    heads = []
    for path in paths["heads"]:
        heads += load(path)
    drawn, map_figures, map_counts = maps.make(
        paths, heads, reports.get, counts["ends_nad83"]
    )
    print(f"the maps: {map_figures['wells_on_map']} wells")
    figures.update(map_figures)
    figures.update(aquifer_figures(paths["aquifer-stats"]))
    figures.update(tile_figures(manifest))
    counts.update({f"map_{k}": v for k, v in map_counts.items()})
    empty = verify.outlines(drawn, sec)
    if empty:
        for problem in empty:
            print(f"CHECK FAILED: {problem}")
        raise SystemExit(
            f"{len(empty)} empty outlines or parts: nothing was written"
        )

    new = os.path.join(record.ROOT, "target", "land-next")
    shutil.rmtree(new, ignore_errors=True)
    os.makedirs(new)
    record.write_json(os.path.join(new, "section.json"), sec)
    record.write_text(
        os.path.join(new, "section.svg"), draw.Slice(sec).svg(SECTION_LABEL)
    )
    for name, kind, label in drawings():
        record.write_text(
            os.path.join(new, name), draw.map_svg(drawn, kind, label)
        )
    stats = page_figures(figures, counts)
    record.write_json(os.path.join(new, "stats.json"), stats, indent=1)

    bad = verify.privacy(sec, reports.of, aquifer_record.private_words())
    bad += verify.agree(sec, stats["figures"])
    bad += verify.sizes(new)
    if bad:
        for problem in bad[:20]:
            print(f"CHECK FAILED: {problem}")
        raise SystemExit(
            f"{len(bad)} check failures: nothing was published; the new "
            f"data is in {new} for inspection"
        )
    files = record.listing(new)
    record.write_json(
        os.path.join(new, record.RECORD),
        record.expected(manifest, local, files),
        indent=1,
    )
    old = os.path.join(record.ROOT, "target", "land-old")
    shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(out_dir):
        os.replace(out_dir, old)
    os.replace(new, out_dir)
    shutil.rmtree(old, ignore_errors=True)
    print(
        f"land data: {len(files)} files, {sum(files.values()):,} bytes, "
        "checks passed"
    )


def main():
    """Checks the page's data, or makes it again when it is stale."""
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
    stale = record.differences(record.read_record(out_dir), new, files)
    if not stale:
        print(f"land data up to date: {len(files)} files")
        return 0
    if args.check:
        print(
            f"STALE land data ({'; '.join(stale[:8])}"
            f"{'; ...' if len(stale) > 8 else ''}): run ./build.sh site-data "
            "(it fetches any missing input into resources/aquifer/cache/)",
            file=sys.stderr,
        )
        return STALE
    print(f"land data stale ({'; '.join(stale[:8])}): making it again")
    generate(manifest, local, out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
