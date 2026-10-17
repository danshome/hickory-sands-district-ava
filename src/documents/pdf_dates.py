"""The build's date in the PDFs Chrome prints, not the time it printed them.

build.sh runs it on each PDF that Chrome prints (--print-to-pdf stamps the
time of printing and cannot be told another), so that two builds of the same
commit give the same bytes. The Info dictionary's CreationDate and ModDate are
set to SOURCE_DATE_EPOCH, which build.sh exports as the package's date (Oct.
15, 2026, 00:00 UTC; the reproducible-builds.org convention), or to the
present time when it is not set; every other entry (the title, Chrome as the
creator, Skia as the producer) stays as it is. MuPDF writes the file again
whole, every object and stream as it was, so the fonts stay embedded, and adds
no file identifier (/ID), as Chrome writes none.

make_notice_copy.py dates the notice copy with pdf_date() too.

Usage: pdf_dates.py FILE.pdf ...
"""

import os
import sys
import time

import pymupdf


def pdf_date():
    """SOURCE_DATE_EPOCH, else the present time, as a PDF date in UTC.

    Returns:
        The date as Chrome writes one, D:YYYYMMDDHHmmSS+00'00'.
    """
    t = int(os.environ.get("SOURCE_DATE_EPOCH", time.time()))
    return time.strftime("D:%Y%m%d%H%M%S+00'00'", time.gmtime(t))


def set_dates(path):
    """Sets a PDF's CreationDate and ModDate to pdf_date(), in place.

    Args:
        path: the PDF.
    """
    doc = pymupdf.open(path)
    kind, ref = doc.xref_get_key(-1, "Info")
    assert kind == "xref", f"{path}: no Info dictionary"
    info = int(ref.split()[0])
    for key in ("CreationDate", "ModDate"):
        doc.xref_set_key(info, key, pymupdf.get_pdf_str(pdf_date()))
    doc.save(path + ".tmp", no_new_id=True)
    doc.close()
    os.replace(path + ".tmp", path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: pdf_dates.py FILE.pdf ...")
    for p in sys.argv[1:]:
        set_dates(p)
