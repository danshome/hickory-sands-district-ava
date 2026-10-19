"""The page's well classes and logs: the rock a driller names first.

An interval of a well's log takes the class of the rock named earliest in
its description (params.CLASS_RULES; on a tie, the earlier rule). The logs
are read from the 3D aquifer page's report files (docs/assets/aquifer/wells/
detail-<cell>.json), whose free text the privacy rules have already cleaned;
only the report number and those words leave the build. Standard library
only, so the lint workflow tests it.
"""

import math
import re

from . import params

RULES = tuple(
    (params.CLASSES.index(name), re.compile(rx, re.IGNORECASE))
    for name, rx in params.CLASS_RULES
)
OTHER = params.CLASSES.index("other")
UNLOGGED = params.CLASSES.index("unlogged")


def classify(text):
    """The class of the first rock a description names.

    Args:
        text: A driller's description of one interval, or None.

    Returns:
        The class's index in params.CLASSES; "other" when no rock is named.
    """
    best = None
    for cls, rx in RULES:
        found = rx.search(text or "")
        if found and (best is None or found.start() < best[0]):
            best = (found.start(), cls)
    return OTHER if best is None else best[1]


def num(value):
    """A report's number ("1,250", "40+"), or None."""
    try:
        return float(str(value).replace(",", "").replace("+", "").strip())
    except ValueError:
        return None


def log_of(record, depth):
    """A report's logged intervals, cut at its depth.

    Args:
        record: The report, as a detail file holds it.
        depth: Its depth in feet, or None for no limit.

    Returns:
        A sorted list of [top, bottom, class, words]: the driller's words as
        the detail file gives them, stripped.
    """
    limit = depth or math.inf
    out = []
    for item in record.get("Lithology", []):
        top, bot = num(item.get("TopDepth")), num(item.get("BottomDepth"))
        if top is None or bot is None or bot <= top or top >= limit:
            continue
        words = (item.get("LithologyDescription") or "").strip()
        out.append([top, min(bot, limit), classify(words), words])
    out.sort(key=lambda s: (s[0], s[1]))
    return out


def water_interval(segs, water_top, water_bottom, basis):
    """The interval the 3D page colours a well's head by.

    Args:
        segs: log_of()'s intervals.
        water_top: The deepest water-bearing zone's top (heads' field), or
            None.
        water_bottom: Its bottom, or None.
        basis: The 3D page's basis: 0 the water-bearing zone, 1 the bottom
            of the log, 2 unlogged.

    Returns:
        The interval overlapping the water-bearing zone most (basis 0, when
        it overlaps at all), else the deepest; None when there is no log.
    """
    if not segs:
        return None
    if basis == 0 and water_top is not None and water_bottom is not None:

        def overlap(s):
            return min(s[1], water_bottom) - max(s[0], water_top)

        best = max(segs, key=overlap)
        if overlap(best) > 0:
            return best
    return max(segs, key=lambda s: (s[1], s[0]))


def detail_cell(lon, lat):
    """The detail file's cell key of a position, as the 3D page names it."""
    step = params.DETAIL_DEG
    return f"{math.floor(lon / step)}_{math.floor(lat / step)}"
