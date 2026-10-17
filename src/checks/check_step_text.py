"""Hard check: the boundary's step text uses the Federal Register's characters.

Run by the commit hook and by the build (Dan, 2026-10-17: block the characters
that sneak in from word processors and printed PDFs).

1. TTB's 96 steps (resources/boundary/description/ttb-notice-243-steps.json)
   are identical, character for character, to the Federal Register's own text
   of Notice No. 243: resources/ttb/federal-register-2026-16670-full-text.xml,
   its full-text XML as federalregister.gov publishes it (fetched 2026-10-17,
   kept byte for byte).
2. Every step written for the proposal (the petition's wording in
   petition-steps.json and the steps in src/boundary/build_agreed.py) and,
   after a build, every step of the proposed description
   (target/work/agreed-steps.json) uses only the characters the Federal
   Register uses in step text: printable ASCII and curly double quotes. No en
   or em dashes (the printed notice's dashes are GPO's typesetting; the
   Federal Register's text has hyphens), no curly apostrophes, no
   non-breaking, thin or zero-width spaces, soft hyphens or tabs.

Exit 1 naming each step, character and its fix.

Usage: check_step_text.py [agreed-steps.json]
"""

import ast
import html
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
XML = os.path.join(
    ROOT, "resources", "ttb", "federal-register-2026-16670-full-text.xml"
)
TTB = os.path.join(
    ROOT, "resources", "boundary", "description", "ttb-notice-243-steps.json"
)
PET = os.path.join(
    ROOT, "resources", "boundary", "description", "petition-steps.json"
)
AGREED = os.path.join(ROOT, "src", "boundary", "build_agreed.py")
OK = {chr(c) for c in range(32, 127)} | {"\u201c", "\u201d"}
FIX = {
    "\u2013": "-",
    "\u2014": "-",
    "\u2010": "-",
    "\u2011": "-",
    "\u2212": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u00a0": "a space",
    "\u2009": "a space",
    "\u202f": "a space",
    "\t": "a space",
    "\u00ad": "nothing",
    "\u200b": "nothing",
    "\u200c": "nothing",
    "\u200d": "nothing",
    "\ufeff": "nothing",
}
bad = []


def read(path):
    """Returns the text of a UTF-8 file."""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def chars(where, text):
    """Records each character of text the Federal Register does not use.

    Args:
        where: what the text is, for the message ("proposed step (7)").
        text: the step's text.
    """
    for i, c in enumerate(text):
        if c not in OK:
            name = unicodedata.name(c, f"U+{ord(c):04X}")
            bad.append(
                f"{where}: {name} (U+{ord(c):04X}) at "
                f"'{text[max(0, i - 20) : i + 20]}'; "
                f"use {FIX.get(c, 'a character the Federal Register uses')}"
            )


# 1. TTB's steps = the Federal Register's text (the Hickory Sands District's
# "(c) Boundary." and the numbered steps after it)
xml = read(XML)
paras = [
    re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", p))).strip()
    for p in re.findall(r"<P>(.*?)</P>", xml, re.S)
]
start = max(
    i
    for i, p in enumerate(paras)
    if p.startswith("(c) Boundary.") and "Hickory Sands" in p
)
fr = {}
for p in paras[start + 1 :]:
    if not (m := re.match(r"\((\d+)\) ", p)):
        break
    fr[m.group(1)] = p
ttb = json.loads(read(TTB))
if sorted(ttb, key=int) != sorted(fr, key=int):
    bad.append(
        f"TTB's steps: {len(ttb)} in {TTB}, {len(fr)} in the Federal Register"
    )
for k in ttb:
    if k in fr and re.sub(r"\s+", " ", ttb[k]).strip() != fr[k]:
        a, b = re.sub(r"\s+", " ", ttb[k]).strip(), fr[k]
        # the first character that differs (the texts may differ in length)
        i = next(
            (j for j, (x, y) in enumerate(zip(a, b, strict=False)) if x != y),
            min(len(a), len(b)),
        )
        bad.append(
            f"TTB's step ({k}) differs from the Federal Register at "
            f"'{a[max(0, i - 20) : i + 20]}' / '{b[max(0, i - 20) : i + 20]}'"
        )
    chars(f"TTB's step ({k})", ttb[k])

# 2. the proposal's own wording: the petition's steps, the steps written in
# build_agreed.py, and the built description
for k, v in json.loads(read(PET)).items():
    chars(f"petition step ({k}) in {os.path.basename(PET)}", v)
for node in ast.walk(ast.parse(read(AGREED))):
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("Proceed ")
    ):
        chars(f"step text in build_agreed.py line {node.lineno}", node.value)
if len(sys.argv) > 1:
    for s in json.loads(read(sys.argv[1]))["steps"]:
        chars(f"proposed step ({s['step']})", s["text"])

for b in bad:
    print(b)
if bad:
    sys.exit(1)
print(
    f"step text: TTB's {len(ttb)} steps identical to the Federal Register; "
    "only its characters in the proposal's steps"
)
