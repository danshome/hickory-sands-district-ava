#!/usr/bin/env python3
"""Set a built PDF's document properties to match the author's earlier comment on this docket
(TTB-2026-0005-0015): Title, Subject (the docket), Author.
usage: pdf_meta.py <kind: comment|fallback|attachment1> <pdf>   (rewrites the file in place)"""
import os, sys
from pypdf import PdfReader, PdfWriter

kind, path = sys.argv[1], sys.argv[2]
TITLE = {
    # Same wording as the HTML <title> in build_comment_html.py
    "comment": "Comment of Dan McLaughlin on Notice No. 243 (Docket No. TTB-2026-0005)",
    "fallback": "Comment of Dan McLaughlin on Notice No. 243 (Docket No. TTB-2026-0005)",
    "attachment1": "Attachment 1: Boundary Narrative Comparison (Docket No. TTB-2026-0005, Notice No. 243)",
}[kind]
w = PdfWriter(clone_from=PdfReader(path))
w.add_metadata({
    "/Title": TITLE,
    "/Subject": "Docket No. TTB-2026-0005",
    "/Author": "Dan McLaughlin, Robert Clay Vineyards",
    "/Keywords": "TTB-2026-0005; Notice No. 243; Hickory Sands District; American Viticultural Area",
})
tmp = path + ".tmp"
with open(tmp, "wb") as f:
    w.write(f)
os.replace(tmp, path)
print(f"meta  {path}")
