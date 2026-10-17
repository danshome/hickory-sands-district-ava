"""Side-by-side comparison for TTB of the steps that change.

One row per proposed step that differs from TTB's published text: TTB's
published text (Notice No. 243) | the original petition (reference, not
marked) | proposed text | why. Marking compares the proposed text with TTB's
text only:

  red strikethrough  TTB's words the proposed text drops
  yellow             words the proposed text adds to TTB's text

("Proposed", never "final": the text is a proposal until TTB adopts it.)
Every other step is TTB's published text word for word and is not shown.
"""

import difflib
import html
import json
import os
import re

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)  # the repository root
HERE = os.environ.get("HSD_WORK") or os.path.join(
    ROOT, "target", "work"
)  # build work dir (build.sh stages resources/ here)
DESCRIPTION = os.path.join(ROOT, "resources", "boundary", "description")


def load_json(path, encoding=None):
    """The JSON file at PATH, read with ENCODING (the locale's by default)."""
    with open(path, encoding=encoding) as f:
        return json.load(f)


S = {
    s["step"]: s
    for s in load_json(os.path.join(HERE, "agreed-steps.json"))["steps"]
}
# TTB's steps word for word from the Federal Register's own text of Notice
# No. 243 (document 2026-16670, full-text XML, downloaded 2026-10-15; the PDF
# is byte-identical to our copy and its text identical to the regulations.gov
# copy)
NPRM = {
    int(k): v
    for k, v in load_json(
        os.path.join(DESCRIPTION, "ttb-notice-243-steps.json"),
        encoding="utf-8",
    ).items()
}
assert "light-duty" in NPRM[15] and "Mason-McCulloch" in NPRM[19]
assert "light-duty" in NPRM[91]
# the petition as filed in the docket (TTB-2026-0005-0012), downloaded
# 2026-10-15
PET = {
    int(k): v
    for k, v in load_json(
        os.path.join(DESCRIPTION, "petition-steps-docket.json"),
        encoding="utf-8",
    ).items()
    if v
}
PET[102] = PET[102][
    : PET[102].index("beginning point.") + len("beginning point.")
]


def step_body(t):
    """Step text T without its number: "(10) Proceed ..." -> "Proceed ..."."""
    return re.sub(r"^\(\d+\)\s*", "", t)


e = html.escape
TOK = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9.,’'\-]*[A-Za-z0-9]|[A-Za-z0-9]|[^\sA-Za-z0-9]"
)


def tok(t):
    """The tokens of T: words, with inner punctuation, and single symbols.

    A word keeps the dots, commas, apostrophes (straight or curly) and hyphens
    inside it ("1,727-foot", "U.S."); any other character is a token of its
    own.
    """
    return TOK.findall(t)


def render(pieces):
    """Marked tokens as HTML, spaced as normal text.

    Consecutive tokens of one class share one tag.

    Args:
        pieces: [(token, cls)]: cls is a tag name (del, ins) or None.

    Returns:
        The HTML.
    """
    out = []
    prev = None
    for t, c in pieces:
        sp = "" if (not out or t in ",;:.)”" or prev in ("(", "“")) else " "
        w = e(t)
        if c and out and out[-1][1] == c and sp == " ":
            out[-1] = (out[-1][0] + " " + w, c)
        elif c and out and out[-1][1] == c:
            out[-1] = (out[-1][0] + w, c)
        else:
            out.append((sp + w if not c else sp + "\0" + w, c))
        prev = t
    res = ""
    for txt, c in out:
        if c:
            lead = txt[: txt.index("\0")]
            body_ = txt[txt.index("\0") + 1 :]
            res += lead + f"<{c}>{body_}</{c}>"
        else:
            res += txt
    return res


def marks(src, final):
    """SRC as HTML, its words that FINAL does not have struck (<del>)."""
    a, b = tok(src), tok(final)
    pieces = []
    for op, i1, i2, _j1, _j2 in difflib.SequenceMatcher(
        None, a, b, autojunk=False
    ).get_opcodes():
        for t in a[i1:i2]:
            pieces.append((t, None if op == "equal" else "del"))
    return render(pieces)


def added(final, ttb):
    """FINAL as HTML, its words that TTB's text TTB does not have in <ins>."""
    f = tok(final)
    keep = [False] * len(f)
    if ttb:
        for op, _i1, _i2, j1, j2 in difflib.SequenceMatcher(
            None, tok(ttb), f, autojunk=False
        ).get_opcodes():
            if op == "equal":
                for j in range(j1, j2):
                    keep[j] = True
    return render(
        [(w, None if k else "ins") for w, k in zip(f, keep, strict=True)]
    )


def proposed_step(n):
    """The proposed text of step N, without its number."""
    return step_body(S[n]["text"])


def ttb_step(n):
    """TTB's published text of step N (Notice No. 243), without its number."""
    return step_body(NPRM[n])


def label(s):
    """A step number in bold, for the start of a cell."""
    return f"<b>{s}</b> "


def petition_cell(k):
    """The petition column: petition step K, as filed, with its number."""
    return f"<small>petition step {k}</small><br>{e(PET[k])}"


DASH = "<small>—</small>"


def quoted(t):
    """T escaped, in curly double quotes."""
    return "“" + e(t) + "”"


US = (
    " The petition wrote “U.S. Highway”; we write “US Highway”, as TTB’s "
    "published text does."
)
rows = []  # (ttb, petition, final, why) or ("HEAD", text)

rows.append(
    (
        label("(10)") + marks(ttb_step(10), proposed_step(10)),
        petition_cell(11),
        label("(10)") + added(proposed_step(10), ttb_step(10)),
        "TTB’s published text says “along State Highway 29”, with no lane. "
        "The original petition (step 11) said “along the westbound lane of "
        "State Highway 29”. <b>We are adding “the westbound lane of” back</b> "
        "because the boundary uses this highway twice near Grit: out "
        "(southeast) along the westbound lane in steps (10)–(11), and back "
        "(northwest) along the eastbound lane in steps (91)–(92). Naming the "
        "lanes keeps the two passes on opposite sides of the road. As "
        "discussed with TTB on October 15, 2026, the petition’s lane wording "
        "is used unchanged." + US,
    )
)
rows.append(
    (
        label("(11)") + marks(ttb_step(11), proposed_step(11)),
        petition_cell(12),
        label("(11)") + added(proposed_step(11), ttb_step(11)),
        "TTB’s published text says “along US Highway 377, crossing onto the "
        "Purdy Hill map, to the highway’s intersection with US Highway 87”. "
        "The original petition (step 12) said “along U.S. Highway 377 along "
        "the westbound lane to its intersection with U.S. Highway 87”. <b>We "
        "are adding “along the westbound lane”</b> for the same reason as "
        "step (10). <b>We are removing “crossing onto the Purdy Hill map” and "
        "“the highway’s”</b> only because, as discussed with TTB, we use the "
        "petition’s own words for these steps, and the petition’s step does "
        "not have them. The line is the same, and it still crosses onto the "
        "Purdy Hill map here." + US,
    )
)

rows.append(
    (
        "HEAD",
        (
            "<b>Away from the area near Grit: two flagged corrections to "
            "Notice No. 243’s own wording.</b> Steps (49) and (85) are TTB’s "
            "published steps with one word corrected in each; they are not "
            "part of the change near Grit. The line, the points and the area "
            "do not change."
        ),
    )
)
rows.append(
    (
        label("(49)") + marks(ttb_step(49), proposed_step(49)),
        petition_cell(50),
        label("(49)") + added(proposed_step(49), ttb_step(49)),
        (
            "<b>Editorial correction.</b> TTB’s published text says “the "
            "marked 1,586-elevation point”, without “-foot”. Everywhere else "
            "in its 96 steps an elevation is written “N-foot” (72 times), as "
            "TTB writes elevations throughout 27 CFR part 9 (about 500 times, "
            "such as “the marked N-foot elevation point”), and the original "
            "petition (step 50) says “the marked 1,586-foot elevation point”. "
            "<b>We are supplying “-foot”</b>: “the marked 1,586-foot "
            "elevation point”. The Pecan Springs map prints the point x1586. "
            "<b>The line does not change.</b>"
        ),
    )
)
rows.append(
    (
        label("(85)") + marks(ttb_step(85), proposed_step(85)),
        petition_cell(86),
        label("(85)") + added(proposed_step(85), ttb_step(85)),
        (
            "<b>Correction.</b> TTB’s published text says “the marked "
            "1,801-foot summit”. The step ends at a summit on the Turtle "
            "Creek, TX, 1968 map (−99.25899, 30.72613, NAD83), and the map "
            "prints that summit <b>x1802</b>. The 1,801 comes from the "
            "original petition’s written description (step 86, “the marked "
            "1801-foot summit”). <b>We are correcting it to “the marked "
            "1,802-foot summit”</b>, the elevation the map prints at the "
            "step’s end point. <b>The line does not change.</b>"
        ),
    )
)

rows.append(
    (
        "HEAD",
        (
            "<b>Near Grit: TTB’s steps (90)–(92) are replaced as a whole by "
            "the original petition’s route, in the petition’s own words, as "
            "discussed with TTB on October 15, 2026.</b> The area near Grit "
            "becomes proposed steps (90)–(100), eleven steps in place of "
            "TTB’s three. TTB’s three steps are shown beside the proposed "
            "steps closest to them; rows with “—” have no TTB step."
        ),
    )
)


def whole_step(n, txt, tag):
    """Step N's text TXT, all of it marked with TAG (del or ins)."""
    return f"<b>({n})</b> <{tag}>{e(txt)}</{tag}>"


rows.append(
    (
        whole_step(90, ttb_step(90), "del"),
        petition_cell(91),
        whole_step(90, proposed_step(90), "ins"),
        "TTB’s published text follows Honey Creek, crossing onto the Grit "
        "map, only as far as the highway at the marked 1,668-foot elevation "
        "point, then follows the highway to Old Junction Road (TTB’s step "
        "(91)). The original petition (step 91) said the line follows Honey "
        "Creek all the way “to the marked 1727-foot elevation point at its "
        "intersection with State Highway 29”. <b>We are using the petition’s "
        "step with two flagged changes, discussed with TTB.</b> First, the "
        "tributary: on the Grit map, the stream labelled Honey Creek reaches "
        "the highway at the marked 1668, not the 1727. The petition’s line "
        "leaves Honey Creek where an unnamed, intermittent tributary joins it "
        "and follows that tributary, past Bench Mark 1680, to the 1727. So "
        "the petition’s "
        + quoted(
            "north-easterly, then north-westerly, then north-easterly along "
            "Honey Creek to the marked 1727…"
        )
        + " becomes "
        + quoted(
            "northeasterly, then northwesterly along Honey Creek to its "
            "confluence with an unnamed, intermittent tributary, then "
            "northeasterly along the tributary to the marked 1,727…"
        )
        + ". The words now match the line; <b>the line does not move.</b> "
        "Second, <b>we name the road at the 1,727 “US Highway 377”</b>, as "
        "TTB’s published text names the road that US Highway 377 and State "
        "Highway 29 share from the junction near Grit to Mason (TTB’s step "
        "(11)); the petition called it “State Highway 29”. We also write "
        "“northeasterly”, “northwesterly” and “1,727-foot” the way TTB’s "
        "published text does (the petition wrote “north-easterly”, "
        "“north-westerly” and “1727-foot”). (The petition’s words don’t "
        "mention the Grit map; the line does cross onto it here.)",
    )
)
rows.append(
    (
        whole_step(91, ttb_step(91), "del"),
        petition_cell(92),
        whole_step(91, proposed_step(91), "ins"),
        "TTB’s published text runs southwest, then northwest, along the "
        "highway to Old Junction Road; the proposed text does not use that "
        "route. The original petition (step 92) said "
        + quoted(PET[92].rstrip(",").rsplit("; then", 1)[0])
        + ". <b>We are using the petition’s step</b>, the return pass along "
        "the eastbound lane (see step (10)), <b>with the roads named as TTB "
        "names them</b>: from the 1,727 back to the junction near Grit the "
        "road is the one US Highway 377 and State Highway 29 share, which "
        "TTB’s text calls “US Highway 377” (its step (11)); northwest of "
        "the junction it is “State Highway 29” (its step (10)). The lane "
        "wording is the petition’s, unchanged. The petition’s “then,” is "
        "written “then”, as TTB writes it.",
    )
)
rows.append(
    (
        DASH,
        petition_cell(93),
        whole_step(92, proposed_step(92), "ins"),
        (
            "Not in TTB’s published text. <b>The original petition’s step 93, "
            "word for word</b>, written in TTB’s style: “1,737-foot” (the "
            "petition wrote “1737-foot”) and “then” without a comma. The line "
            "continues along the eastbound lane to the marked 1,737."
        ),
    )
)
rows.append(
    (
        DASH,
        petition_cell(94),
        whole_step(93, proposed_step(93), "ins"),
        (
            "<b>New step, proposed (steps (93)–(96)), as discussed with TTB "
            "on October 15, 2026.</b> The original petition (step 94) said "
            "“Proceed southwest in a straight line to the marked 1762-foot "
            "elevation point”. That straight line takes in a lobe of granite "
            "(not the Hickory Sandstone Member formation) northwest of the "
            "area near Grit. <b>We are replacing that one straight line with "
            "four steps</b> that go around the lobe and leave it out of the "
            "AVA, using points shown on the Grit map: a windmill, a fence "
            "line where it meets Topaz Lane, and Topaz Lane’s westernmost "
            "point, east of a stock pond; step (96) then goes on to the same "
            "marked 1,762."
        ),
    )
)
for n in (94, 95, 96):
    rows.append(
        (
            DASH,
            "<small>— (replaces petition step 94; see step (93))</small>",
            whole_step(n, proposed_step(n), "ins"),
            "New, proposed; see step (93).",
        )
    )
for n, k in ((97, 95), (98, 96), (99, 97)):
    extra = {
        98: " (The petition already writes “US Highway” here.)",
        99: (
            " Written “1,765-foot”, as TTB writes elevations (the petition "
            "wrote “1765-foot”)."
        ),
    }.get(n, "")
    rows.append(
        (
            DASH,
            petition_cell(k),
            whole_step(n, proposed_step(n), "ins"),
            (
                "Not in TTB’s published text. <b>The original petition’s "
                f"step {k}, word for word.</b>{extra}"
            ),
        )
    )
rows.append(
    (
        whole_step(92, ttb_step(92), "del"),
        petition_cell(98),
        whole_step(100, proposed_step(100), "ins"),
        "TTB’s published text reaches the same place, the end of Lange Road, "
        "by a straight line from Old Junction Road, “crossing onto the Turtle "
        "Creek map”. The original petition (step 98) said "
        + quoted(PET[98].rsplit("; then", 1)[0])
        + ", from the marked 1765 summit. <b>We are using the petition’s step "
        "word for word</b>, as discussed with TTB. (The petition’s words "
        "don’t mention the Turtle Creek map; the line does cross onto it "
        "here.)",
    )
)

rows.append(
    (
        "HEAD",
        (
            "<b>After the area near Grit: TTB’s last four steps, word for "
            "word, renumbered.</b>"
        ),
    )
)
for k in (93, 94, 95, 96):
    n = k + 8
    same_as_pet = ttb_step(k) == PET[k + 6]
    why = (
        f"TTB’s published step ({k}), <b>word for word, renumbered ({n})</b>: "
        "the area near Grit is now eleven steps instead of three, so the "
        "later steps move up by eight."
        if k == 93
        else f"TTB’s published step ({k}), word for word, renumbered ({n})."
    )
    if not same_as_pet:
        why += (
            f" The original petition (step {k + 6}) worded this step a "
            "little differently; TTB’s wording is kept."
        )
    rows.append(
        (
            f"<b>(<del>{k}</del>)</b> " + e(ttb_step(k)),
            petition_cell(k + 6),
            f"<b>(<ins>{n}</ins>)</b> " + e(proposed_step(n)),
            why,
        )
    )


# the proposed column, stripped of marking, is exactly the proposed text;
# TTB's column is exactly TTB's text
def strip_tags(h):
    """The text of HTML H: tags dropped, entities unescaped."""
    return html.unescape(re.sub("<[^>]+>", "", h))


for r in rows:
    if r[0] == "HEAD":
        continue
    m = re.match(r"\((\d+)\) (.*)$", strip_tags(r[2]), re.S)
    assert m and m.group(2) == proposed_step(int(m.group(1))), strip_tags(r[2])[
        :80
    ]
    if r[0] != DASH:
        m = re.match(r"\((\d+)\) (.*)$", strip_tags(r[0]), re.S)
        assert m and m.group(2) == ttb_step(int(m.group(1))), strip_tags(r[0])[
            :80
        ]
    if r[1].startswith("<small>petition step"):
        k = int(re.match(r"<small>petition step (\d+)", r[1]).group(1))
        assert strip_tags(r[1]).endswith(PET[k])
shown = sorted(
    int(re.match(r"\((\d+)\)", strip_tags(r[2])).group(1))
    for r in rows
    if r[0] != "HEAD"
)
assert shown == [10, 11, 49, 85, *range(90, 105)], shown
FIXED = {
    49: (
        "Proceed south in a straight line to the marked 1,586-foot elevation "
        "point along an unnamed road known locally as County Road 220; then"
    ),
    85: (
        "Proceed west in a straight line, crossing onto the Turtle Creek map, "
        "to the marked 1,802-foot summit; then"
    ),
}  # issue #38
assert all(
    proposed_step(n) == ttb_step(n)
    for n in list(range(1, 10)) + list(range(12, 90))
    if n not in FIXED
), "a step outside the table differs from TTB"
assert all(proposed_step(n) == t for n, t in FIXED.items()), (
    "steps (49) and (85) are not the corrected text"
)
pet_of = {
    int(re.match(r"\((\d+)\)", strip_tags(r[2])).group(1)): int(
        re.match(r"<small>petition step (\d+)", r[1]).group(1)
    )
    for r in rows
    if r[0] != "HEAD" and r[1].startswith("<small>petition step")
}  # the STEP NUMBERS box below quotes these
assert [pet_of[n] for n in range(97, 105)] == list(range(95, 103)), (
    "the step-numbers box is out of step with the table"
)
assert all(pet_of[n] == n + 1 for n in (10, 11, 49, 85)), (
    "the step-numbers box (petition = TTB + 1 up to (89)) is out of step with "
    "the table"
)

css = (
    "body{font-family:Arial,'Liberation Sans',sans-serif;font-size:9pt;"
    "margin:0.3in 0.4in} h1{font-size:15pt;margin:0 0 3pt}"
    "p{margin:0 0 5pt} "
    "table{border-collapse:collapse;width:100%;table-layout:fixed} "
    "td,th{border:1px solid #999;padding:3pt 4pt;vertical-align:top;"
    "text-align:left;font-size:9pt} "
    "tr{break-inside:avoid;page-break-inside:avoid}"
    "th{background:#e8e8e8} "
    "td.why{font-size:8.5pt;color:#222;line-height:1.25} "
    "td.head{background:#eef2f7} small{color:#777;font-size:7.5pt}"
    "col.t{width:21%} col.w{width:37%}"
    "del{color:#c00000;text-decoration:line-through} "
    "ins{background:#fff176;text-decoration:none}"
    "red{color:#c00000;font-weight:bold;font-size:10.5pt} "
    "p.warn{border:2.5px solid #c00000;padding:5pt 7pt;margin:5pt 0 6pt}"
    "p.src{font-size:8pt;color:#333} @page{size:letter landscape;margin:0}"
)
h = [
    (
        "<html><head><meta charset='utf-8'>"
        '<meta name="orientation" content="landscape">'
        "<title>Hickory Sands District AVA: changes to TTB’s published "
        "boundary description</title>"
        f"<style>{css}</style></head><body>"
    ),
    (
        "<h1>Hickory Sands District AVA: changes to TTB’s published "
        "boundary description</h1>"
    ),
    (
        "<p>Columns: TTB’s published text (Notice No. 243, 91 FR 52576) | the "
        "original petition (February 2, 2023), for reference | the text we "
        "propose, as discussed with TTB on October 15, 2026 | why each change "
        "is made. <b>Only the steps that change are shown. Every other step "
        "is TTB’s published text word for word, with the same step "
        "number.</b></p>"
    ),
    (
        "<p class=warn><red>IMPORTANT – STEP NUMBERS. Up to TTB’s step (89), "
        "the petition’s step numbers are ONE HIGHER than TTB’s. The original "
        "petition used TWO steps for the starting point (step 1: the "
        "beginning point; step 2: the first line from it), which TTB combined "
        "into its step (1). So petition step 11 is step (10) here. Near Grit "
        "the petition used eight steps (91–98) where TTB used three, so from "
        "there on each row names the petition step it shows: TTB’s (93)–(96) "
        "are petition steps 99–102, and the proposed (97)–(100) are petition "
        "steps 95–98. Bold numbers in parentheses, like (10), are TTB’s and "
        "the proposed text’s; the petition’s own numbers are always written "
        "“petition step 11”.</red></p>"
    ),
    (
        "<p>Marking compares the proposed text with TTB’s published text "
        "only: <del>red strikethrough</del> = TTB’s words that the proposed "
        "text drops; <ins>yellow</ins> = words the proposed text adds to "
        "TTB’s text. <b>The petition column is for reference only and is not "
        "marked</b>; the Why column explains how each proposed step compares "
        "with TTB’s text and with the petition.</p>"
    ),
    (
        '<table data-cols="1.93,1.93,1.93,3.41"><colgroup>'
        "<col class=t><col class=t><col class=t><col class=w></colgroup>"
        "<tr><th>TTB’s published text (Notice No. 243)</th>"
        "<th>Original petition (Feb. 2, 2023), for reference</th>"
        "<th>Proposed text</th><th>Why</th></tr>"
    ),
]
for r in rows:
    if r[0] == "HEAD":
        h.append(
            f'<tr><td colspan=4 class=head data-shade="EEF2F7">{r[1]}</td></tr>'
        )
    else:
        h.append(
            f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td>"
            f"<td class=why>{r[3]}</td></tr>"
        )
TABLE_AT = next(i for i, t in enumerate(h) if t.startswith("<table"))
h.append("</table>")
h.insert(
    TABLE_AT,
    "<p class=src>Sources: TTB’s text is the Federal Register’s text of "
    "Notice No. 243 (document 2026-16670), checked on October 15, 2026 "
    "against the official PDF on govinfo.gov and the notice in docket "
    "TTB-2026-0005 (same wording). The petition text is the petition as filed "
    "in the docket (TTB-2026-0005-0012). TTB’s step (1) is kept as published: "
    "on the Long Mountain map the beginning point is just west of Bench Mark "
    "1678, as TTB wrote, not east of it as the petition said.</p>",
)
h[TABLE_AT] = h[TABLE_AT][:-4] + (
    " Prepared by Dan McLaughlin, Robert Clay Vineyards (petitioner). "
    "License: TTB’s text (Notice No. 243) is a U.S. Government work, in the "
    "public domain; the petitioner’s changes and the compilation are CC0 1.0 "
    "(no rights reserved), so TTB, its contractors and anyone else may use "
    "them without attribution.</p>"
)
h.append("</body></html>")
OUT = os.path.join(
    HERE,
    "documents",
    "Hickory-Sands-District-boundary-changes-side-by-side-2026-10-15.html",
)
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(h))
print(OUT, len([r for r in rows if r[0] != "HEAD"]), "rows")
