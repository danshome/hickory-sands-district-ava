#!/usr/bin/env python3
"""Download the public source documents from Docket TTB-2026-0005 on Regulations.gov:

    narrative/source/Notice-243-91FR52576-2026-16670.pdf     (TTB-2026-0005-0001)
    narrative/source/Hickory-Sands-District-AVA-Petition.pdf  (TTB-2026-0005-0012)

Run from anywhere:  python3 scripts/fetch_sources.py
"""
import os, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "narrative", "source")
DOCS = [
    ("Notice-243-91FR52576-2026-16670.pdf", "https://downloads.regulations.gov/TTB-2026-0005-0001/content.pdf"),
    ("Hickory-Sands-District-AVA-Petition.pdf", "https://downloads.regulations.gov/TTB-2026-0005-0012/content.pdf"),
]
os.makedirs(OUT, exist_ok=True)
for name, url in DOCS:
    dst = os.path.join(OUT, name)
    if os.path.exists(dst):
        print(f"ok    {name}"); continue
    print(f"fetch {name}")
    req = urllib.request.Request(url, headers={"User-Agent": "hickory-sands-ava-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dst, "wb") as f:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            f.write(chunk)
print("done")
