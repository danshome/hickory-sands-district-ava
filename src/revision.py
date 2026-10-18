"""The proposed revision's date: one source for every name and label from it.

resources/boundary/revision-date.txt holds the date (YYYY-MM-DD) the proposed
revision carries. The package and its files are named after it, labels such as
"as proposed to TTB, Oct. 15, 2026" print it, the ArcGIS Online services are
named after it, and every date the build writes into what it makes
(SOURCE_DATE_EPOCH, in build.sh) is its midnight UTC. Change the file to
date a new revision; nothing else types the date. Dates of events (when the
changes were discussed with TTB, when TTB's notice was downloaded) are history
and stay in the text that tells them.

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
        SystemExit: When the file does not hold one date.
    """
    with open(path, encoding="utf-8") as fh:
        text = fh.read().strip()
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        raise SystemExit(f"{path}: not a date (YYYY-MM-DD): {text!r}") from None


DATE = read()
ISO = DATE.isoformat()  # 2026-10-15, as in the file names
UNDERSCORED = ISO.replace("-", "_")  # 2026_10_15, as in the service names
LONG = f"{LONG_MONTHS[DATE.month - 1]} {DATE.day}, {DATE.year}"
SHORT = f"{SHORT_MONTHS[DATE.month - 1]} {DATE.day}, {DATE.year}"
# The package and its stems.
NAME = f"Hickory-Sands-District-AVA_boundary-as-proposed-{ISO}"
STEM = f"hickory-sands-district-boundary-proposed-{ISO}"
