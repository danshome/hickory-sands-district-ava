"""Makes the data of the website's 3D aquifer page (docs/aquifer.html).

The page shows the whole Hickory Aquifer as TWDB's Llano Uplift groundwater
model draws it, with TWDB's well reports (without people's names), the
proposed district, TTB's proposed Llano Uplift AVA, the counties and towns.
Its data is docs/assets/aquifer/ (src/site/aquifer/ says what each file
holds); the vineyards it draws are docs/assets/vineyards/, made apart by
src/site/make_vineyards.py from these well tiles. It is made from:

- the downloads resources/aquifer/inputs.csv pins (TWDB's model archive,
  its 2017 aquifer outlines and its two well databases, the Census
  counties and places), fetched into the gitignored resources/aquifer/cache/
  when missing and checked against their SHA-256s;
- committed inputs: resources/aquifer/'s fault lines, TTB's Llano Uplift AVA
  in resources/ttb/ and the shifted geology.

docs/assets/aquifer/record.json records those inputs, the generator's
parameters and the files written. The data is made again only when that
record would change, or a file it lists is missing or not its size; with
--check nothing is read but the manifest, the committed inputs and the
record, nothing is fetched or written, and the exit status is 3 when the
data is stale. Every file is written into a new folder that replaces the old
one only when the privacy check (no person's name or address survives) and
the size check (every file under the hooks' 2 MB) have passed.

Usage:
    make_aquifer_3d.py [--check]
"""

import argparse
import math
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # src/site
from aquifer import params
from aquifer import record

STALE = 3  # --check's exit status when the data is stale


def stats(manifest, figures):
    """The page's stats.json: every figure it shows, and the inputs' dates.

    Args:
        manifest: record.read_manifest()'s rows.
        figures: The figures, by name.

    Returns:
        The JSON-ready dict.
    """
    out = dict(figures)
    for row in manifest:
        key = row["name"].replace("-", "_")
        out[f"{key}_snapshot"] = row["snapshot"]
        out[f"{key}_fetched"] = row["fetched"]
    out.update(
        {
            "cell_ft": params.CELL_FT,
            "tile_deg": params.TILE_DEG,
            "detail_deg": params.DETAIL_DEG,
            "overview_deg": params.OVERVIEW_DEG,
            "wells_all_scale": params.WELLS_ALL_SCALE,
            "wells_lines_scale": params.WELLS_LINES_SCALE,
            "shift_lon": params.SHIFT_LON,
            "shift_lat": params.SHIFT_LAT,
            "step_ft": params.STEP_FT,
            "fault_near_ft": params.FAULT_NEAR_CELLS * params.CELL_FT,
            "core_miles": params.CORE_MILES,
            "block_small": params.FACTORS[0],
            "block_large": params.FACTORS[1],
            "ttb_llano_uplift_snapshot": params.TTB_LLANO_UPLIFT_QUERIED,
        }
    )
    out["shift_m"] = math.hypot(out["shift_west_m"], out["shift_north_m"])
    return {
        "about": (
            "Every figure docs/aquifer.html shows, made by "
            "src/site/make_aquifer_3d.py; the page formats them"
        ),
        "figures": dict(sorted(out.items())),
    }


def generate(manifest, local, out_dir):
    """Makes every file of the page's data, then swaps the folder in.

    Args:
        manifest: record.read_manifest()'s rows.
        local: record.local_digests().
        out_dir: docs/assets/aquifer.

    Raises:
        SystemExit: The privacy or the size check failed; the old data is
            left as it was.
    """
    from aquifer import inputs  # noqa: PLC0415 (not needed by --check)
    from aquifer import model  # noqa: PLC0415 (GDAL and NumPy)
    from aquifer import privacy  # noqa: PLC0415
    from aquifer import wells  # noqa: PLC0415 (GDAL)

    paths = inputs.ensure(manifest)
    paths.update(
        {
            name: os.path.join(record.ROOT, rel)
            for name, rel in record.LOCAL.items()
        }
    )
    # Made in the gitignored target/, so a run that fails its checks leaves
    # nothing in docs/ to commit by mistake.
    new = os.path.join(record.ROOT, "target", "aquifer-next")
    shutil.rmtree(new, ignore_errors=True)
    os.makedirs(new)
    words = record.private_words()
    print(f"{len(words)} more words to blank from .private-words")
    figures, lookup = model.write(paths, new)
    print("aquifer, drill grid and context written")
    found, _, names, scrub = wells.write(paths, lookup, new, words)
    print(f"{found['wells_drawn']} wells written")
    figures.update(found)
    record.write_json(
        os.path.join(new, "stats.json"), stats(manifest, figures), indent=1
    )
    bad = privacy.check(new, names, scrub)
    if bad:
        for where, uid, problem in bad[:20]:
            print(f"PRIVACY CHECK FAILED: {where} {uid}: {problem}")
        raise SystemExit(
            f"{len(bad)} privacy check failures: nothing was published; "
            f"the new data is in {new} for inspection"
        )
    files = record.listing(new)
    big = {p: n for p, n in files.items() if n >= params.MAX_FILE_BYTES}
    if big:
        raise SystemExit(
            f"files of 2 MB or more (the hooks refuse them): {big}"
        )
    record.write_json(
        os.path.join(new, record.RECORD),
        record.expected(manifest, local, files),
        indent=1,
    )
    old = os.path.join(record.ROOT, "target", "aquifer-old")
    shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(out_dir):
        os.replace(out_dir, old)
    os.replace(new, out_dir)
    shutil.rmtree(old, ignore_errors=True)
    print(
        f"aquifer data: {len(files)} files, {sum(files.values()):,} bytes, "
        "privacy check passed"
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
        print(f"aquifer data up to date: {len(files)} files")
        return 0
    if args.check:
        print(
            f"STALE aquifer data ({'; '.join(stale[:8])}"
            f"{'; ...' if len(stale) > 8 else ''}): run ./build.sh site-data "
            "(it fetches any missing input into resources/aquifer/cache/)",
            file=sys.stderr,
        )
        return STALE
    print(f"aquifer data stale ({'; '.join(stale[:8])}): making it again")
    generate(manifest, local, out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
