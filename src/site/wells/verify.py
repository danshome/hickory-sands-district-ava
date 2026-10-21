"""The hard checks of the three wells' data, before anything is written.

- water reaches each well only where it can: every moving-water path and
  every inflow arrow ends on a screen or an open hole of its own well, never
  on blank casing;
- every label fits: inside its drawing, no two overlapping, and, in the
  wide drawings a phone shows, at least params.MIN_LABEL_PX on the
  narrowest phone params.PHONE_PX describes;
- no person's name or address survives: the granite example's report, as
  TWDB's raw download holds it, is read for its owner's, driller's and
  company's names and addresses, and none of them may appear in anything
  written; nor may a private word (.private-words);
- every source a drawing names is in the page's source list;
- every file is within params.MAX_FILE_BYTES.
"""

import itertools
import os
import re
import zipfile

from ..aquifer import privacy as aquifer_privacy
from ..aquifer import wells as aquifer_wells
from . import draw
from . import params

# The raw report's fields that name a person or say where one lives.
PERSONAL = re.compile(r"Name|Address|Addr|Signed", re.IGNORECASE)
SHORTEST = 4  # shorter values ("TX") are not checked: they are not names


def flows(wells):
    """Every flow or inflow that does not end on a screen or open hole."""
    bad = []
    for w in wells:
        open_ = [(a, b) for kind, a, b in w.segments if kind != "casing"]
        for name, lines in (("flow", w.flows), ("inflow", w.inflows)):
            for line in lines:
                u, ft = line[-1]
                if u not in ("wl", "wr"):
                    bad.append(f"{w.key}: a {name} ends off the well ({u})")
                elif not any(a <= ft <= b for a, b in open_):
                    bad.append(
                        f"{w.key}: a {name} ends at {ft:.0f} ft, on casing"
                    )
    return bad


def labels(wells):
    """Labels that overlap, leave the drawing, or are too small."""
    bad = []
    for w in wells:
        for frame in draw.frames(granite=w.granite):
            placed, _ = w.placed[frame.name]
            box_top = getattr(w, "box_top", {}).get(frame.name)
            for col in ("left", "right"):
                spans = sorted(item[3] for item in placed if item[0].col == col)
                for (_, b), (c, _) in itertools.pairwise(spans):
                    if c < b - 0.01:
                        bad.append(f"{w.key} {frame.name}: labels overlap")
            for lb, _, _, (top, bottom) in placed:
                if top < 0 or bottom > frame.height + 0.01:
                    bad.append(f"{w.key} {frame.name}: {lb.text!r} is cut")
                if (
                    box_top is not None
                    and bottom > box_top
                    and lb.y != "sky"
                    and lb.group != "w-unsure"
                ):
                    bad.append(
                        f"{w.key} {frame.name}: {lb.text!r} runs into "
                        "the box under the drawing"
                    )
            if frame.name == "wide":
                scale = params.PHONE_PX * (1 - 2 * params.GUTTER) / frame.width
                for size in frame.fonts.values():
                    if size * scale < params.MIN_LABEL_PX:
                        bad.append(
                            f"{w.key}: a {size} label is "
                            f"{size * scale:.1f}px on a phone"
                        )
    return bad


def personal_values(sdr_zip, report):
    """The raw report's names and addresses, as TWDB publishes them.

    Args:
        sdr_zip: TWDB's driller's report download.
        report: The report's number.

    Returns:
        Each personal field's value of SHORTEST characters or more.

    Raises:
        SystemExit: The report is not in the download.
    """
    with zipfile.ZipFile(sdr_zip) as z:
        for row in aquifer_wells.rows(z, "SDRDownload/WellData.txt"):
            if row["WellReportTrackingNumber"] == report:
                return sorted(
                    {
                        v
                        for k, v in row.items()
                        if PERSONAL.search(k) and len(v) >= SHORTEST
                    }
                )
    raise SystemExit(f"report {report} is not in {sdr_zip}")


def privacy(texts, personal, extra_words=()):
    """Names, addresses or private words in what is written.

    Args:
        texts: {where: text} of everything written.
        personal: personal_values().
        extra_words: The private words.

    Returns:
        A list of problems, naming where, never the word.
    """
    bad = []
    scrub = aquifer_privacy.Scrubber(extra_words)
    for where, text in texts.items():
        low = text.lower()
        for value in personal:
            if value.lower() in low:
                bad.append(f"{where}: a name or address from the report")
        if scrub.extra_in(text):
            bad.append(f"{where}: a private word")
    return bad


def sources(page_text, numbers):
    """Source numbers the drawings name that the page does not list."""
    return [
        f"source {n} is not in docs/land.html's list"
        for n in sorted(set(numbers))
        if f'<li id="source-{n}">' not in page_text
    ]


def sizes(folder):
    """Files over params.MAX_FILE_BYTES."""
    bad = []
    for name in os.listdir(folder):
        size = os.path.getsize(os.path.join(folder, name))
        if size > params.MAX_FILE_BYTES:
            bad.append(f"{name}: {size:,} bytes")
    return bad
