"""The proposed revision's date: one source for every name and label from it.

resources/boundary/revision-date.txt holds the date (YYYY-MM-DD) the proposed
revision carries. The package and its files are named after it, labels such as
"as proposed to TTB, Oct. 15, 2026" print it, and every date the build writes
into what it makes (SOURCE_DATE_EPOCH, in build.sh) is its midnight UTC.
Change the file to date a new revision; nothing else types the date. Two kinds
of date are not the revision's: dates of events (when the changes were
discussed with TTB, when TTB's notice was downloaded), history told in the
text; and the published ArcGIS services' names, which are their URLs and stay
fixed (src/publish/agol_layer.py).

Scripts in src/ import it after putting src/ on sys.path:
    sys.path.insert(0, os.path.join(ROOT, "src"))
    import revision
"""

import datetime
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(ROOT, "resources", "boundary", "revision-date.txt")
# AP style, as the documents print dates ("Oct. 15, 2026"); March to July whole.
SHORT_MONTHS = (
    "Jan.", "Feb.", "March", "April", "May", "June",
    "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec.",
)  # fmt: skip
LONG_MONTHS = (
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
)  # fmt: skip


def read(path=FILE):
    """Returns the revision's date from its file.

    Args:
        path: The file holding the date, YYYY-MM-DD.

    Returns:
        The date.

    Raises:
        SystemExit: When the file cannot be read or does not hold one date
            written YYYY-MM-DD.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read().strip()
    except OSError as error:
        raise SystemExit(
            f"{path}: cannot read the revision date: {error}"
        ) from None
    try:
        date = datetime.date.fromisoformat(text)
    except ValueError:
        date = None
    # Only YYYY-MM-DD, as build.sh reads it too (fromisoformat would also take
    # 20261015 or 2026-W42-4).
    if date is None or date.isoformat() != text:
        raise SystemExit(f"{path}: not a date written YYYY-MM-DD: {text!r}")
    return date


DATE = read()
ISO = DATE.isoformat()  # 2026-10-15, as in the file names
UNDERSCORED = ISO.replace("-", "_")  # 2026_10_15
LONG = f"{LONG_MONTHS[DATE.month - 1]} {DATE.day}, {DATE.year}"
SHORT = f"{SHORT_MONTHS[DATE.month - 1]} {DATE.day}, {DATE.year}"
# The package and its stems.
NAME = f"Hickory-Sands-District-AVA_boundary-as-proposed-{ISO}"
STEM = f"hickory-sands-district-boundary-proposed-{ISO}"
