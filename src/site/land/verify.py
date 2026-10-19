"""The generator's hard checks on what it wrote, before it is swapped in.

- privacy(): only a well's report number and its driller's words, as the 3D
  aquifer page's cleaned report files give them, leave the build; the words
  pass the privacy rules' scan (src/site/aquifer/privacy.py) and hold no
  private word;
- agree(): section.json agrees with stats.json (every figure the page shows
  that the slice also draws);
- sizes(): every map under its budget, every file under the hooks' 2 MB.

The unit tests run them on the committed files. Standard library only.
"""

import json
import math
import os

from ..aquifer import privacy as aquifer_privacy
from . import params

WELL_KEYS = frozenset({"uid", "s", "depth", "ground", "log"})
UID = frozenset("SG")  # a driller's report or a Groundwater Database well


def privacy(section, reports, extra_words=()):
    """What the slice's wells hold beyond a report number and its words.

    Args:
        section: section.json's data.
        reports: A function from a well's uid to its cleaned report (the 3D
            aquifer page's detail file's record), or None to skip the
            comparison with it.
        extra_words: The private words (.private-words), if any.

    Returns:
        A list of problems; empty when there are none.
    """
    bad = [f"section.json: {p}" for p in aquifer_privacy.named_fields(section)]
    scrub = aquifer_privacy.Scrubber(extra_words)
    for w in section.get("wells", []):
        uid = str(w.get("uid", ""))
        if set(w) - WELL_KEYS:
            bad.append(f"{uid}: fields {sorted(set(w) - WELL_KEYS)}")
        if uid[:1] not in UID or not uid[1:].isdigit():
            bad.append(f"{uid!r}: not a report number")
        words = [seg[3] for seg in w.get("log", [])]
        record = {"Lithology": [{"LithologyDescription": t} for t in words]}
        bad += [f"{uid}: {p}" for p in aquifer_privacy.scan_record(record)]
        bad += [f"{uid}: a private word" for t in words if scrub.extra_in(t)]
        if reports is not None:
            cleaned = {
                (item.get("LithologyDescription") or "").strip()
                for item in reports(uid).get("Lithology", [])
            }
            bad += [
                f"{uid}: words not in its cleaned report"
                for t in words
                if t not in cleaned
            ]
    return bad


def agree(section, figures):
    """Where section.json and stats.json disagree.

    Args:
        section: section.json's data.
        figures: stats.json's figures.

    Returns:
        A list of problems; empty when they agree.
    """
    length = section["length_ft"]
    want = {
        "rule_ft": section["rule_ft"],
        "ve": section["ve"],
        "line_mi": round(length / params.FT_PER_MI, 2),
        "mile_stretches": math.ceil(length / params.FT_PER_MI),
        "district_stretches": len(section["district"]),
        "wells_on_section": len(section["wells"]),
        "cell_ft": section["cols"][0][1] - section["cols"][0][0],
    }
    bad = [
        f"{name}: stats.json {figures.get(name)!r}, section.json {value!r}"
        for name, value in want.items()
        if figures.get(name) != value
    ]
    if length != len(section["cols"]) * params.CELL_FT:
        bad.append(f"length_ft {length}: not the columns' span")
    return bad


def sizes(folder):
    """The files over their budgets.

    Args:
        folder: The data folder.

    Returns:
        A list of problems; empty when every file is within its budget.
    """
    bad = []
    for name in sorted(os.listdir(folder)):
        n = os.path.getsize(os.path.join(folder, name))
        limit = (
            params.MAX_MAP_BYTES
            if name.startswith(("map-", "locator"))
            else params.MAX_FILE_BYTES
        )
        if n > limit:
            bad.append(f"{name}: {n:,} bytes, over {limit:,}")
    return bad


def load(path):
    """A JSON file's data."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
