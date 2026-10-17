"""TTB's Notice No. 243 PDF (docket copy TTB-2026-0005-0001) with only the Hickory Sands District steps that change
set into TTB's own pages, so a text compare against TTB's PDF shows only those changes.

- Pages 52577-52585 are TTB's pages untouched; on page 52576 only GPO's seal goes (see below) and a note is added.
- Page 52586, column 3: steps (10)-(11) are set anew; they take one line more than TTB's, so the column's lines are
  re-spaced evenly (9.74 pt; GPO's own spacing there varies from 9.5 to 10) to end level with columns 1 and 2.
- Page 52587, column 3, step (49), and page 52588, column 2, step (85): one word of TTB's step is corrected (issue #38:
  "1,586-foot elevation point", "1,802-foot summit"). Each step still takes as many lines as TTB's, so only the lines
  whose words change are cleared and set anew, on TTB's baselines; TTB's own glyphs stay on the other lines.
- Page 52588: column 1 and column 2 down to step (89) are untouched, but for step (85). From step (90), the new steps
  and TTB's steps (93)-(96) renumbered (101)-(104) fill column 2 and continue in column 3, followed by TTB's signature block.
  The next document (Kaw Valley, which began in column 3), the margin text and the slug move unchanged, in place,
  to an added last page, so the text reads in TTB's order.
New lines are set the way GPO set this notice: Melior 9 pt, 9.5 pt leading, ragged right, one fixed word space,
breaking only at spaces (not after hyphens, so text extraction never joins "north-easterly" into one word). The first page carries a small red "unofficial copy" note as an image
(so it does not show in a text compare, and adds no font: every font in the copy is embedded).
The copy is altered, so it must not pass for GPO's signed file (QA issue #39):
- GPO's digital signature is removed (the field USGPOSignature, the AcroForm that held only it, and the DocMDP /Perms),
  and with it GPO's "Authenticated U.S. Government Information" seal, which is that signature field's appearance;
- the metadata says it is the petitioner's unofficial copy (GPO's XMP packet, with govinfo's creator and dates, is dropped);
- pages 52586, 52587 and 52588 and the added last page carry a red running line in the top margin, drawn in the page content
  as an image like the first-page note, so it prints and survives annotation stripping, and the compare text still
  shows only the changed steps;
- the yellow highlights are filled shapes drawn in the page content under the text, not annotations (the same outline
  and colour the highlight annotations had, so they look the same, and they print).
Usage: python make_notice_copy.py
"""

import io
import json
import os
import re

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import pymupdf

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)  # the repository root
HERE = os.environ.get("HSD_WORK") or os.path.join(
    ROOT, "target", "work"
)  # build work dir (build.sh stages resources/ here)
SRC = os.path.join(
    HERE, "ttb-source-check-2026-10-15", "regs-TTB-2026-0005-0001.pdf"
)
OUT = os.path.join(
    HERE,
    "documents",
    "TTB-Notice-243-with-proposed-Hickory-Sands-District-changes-2026-10-15-UNOFFICIAL.pdf",
)
S = {
    s["step"]: s["text"]
    for s in json.load(open(os.path.join(HERE, "agreed-steps.json")))["steps"]
}

doc = pymupdf.open(SRC)
pristine = pymupdf.open(SRC)
COLX = [45.0, 222.0, 399.0]
INDENT, SIZE, LEAD, TOP, BOTTOM = 9.0, 9.0, 9.5, 67.0, 739.0
P86, P87, P88 = 10, 11, 12  # page indexes of 52586, 52587 and 52588
col_of = lambda x: 0 if x < 215 else (1 if x < 392 else 2)

FONTS = {}
for pno in (P86, P87, P88):
    for xref, ext, typ, name, *_ in doc[pno].get_fonts():
        FONTS.setdefault(
            name.split("+")[-1],
            pymupdf.Font(fontbuffer=doc.extract_font(xref)[3]),
        )
MEL = FONTS["Melior"]
adv = lambda c, f="Melior", s=SIZE: FONTS[f].text_length(c, s)


def col_lines(pno, col):
    """TTB's lines in one column, top to bottom: dict(y, ch=[(char, x relative to the column, font, size)], text)"""
    rows = {}
    for b in doc[pno].get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                for c in s["chars"]:
                    x, y = c["origin"]
                    if y < 55 or y > 765 or x < 40 or col_of(x) != col:
                        continue
                    rows.setdefault(round(y, 2), []).append(
                        (c["c"], x - COLX[col], s["font"], s["size"])
                    )
    out = []
    for y, ch in sorted(rows.items()):
        ch.sort(key=lambda t: t[1])
        out.append(dict(y=y, ch=ch, text="".join(c[0] for c in ch)))
    assert all(f in FONTS for l in out for _, _, f, _ in l["ch"])
    return out


# GPO's word space and measure, from the notice itself
gaps, widths = [], []
for pno in (P86, P87, P88):
    for col in (0, 1, 2):
        for l in col_lines(pno, col):
            ch = l["ch"]
            if not all(f == "Melior" and s == SIZE for _, _, f, s in ch):
                continue
            for i in range(1, len(ch) - 1):
                if ch[i][0] == " " and ch[i + 1][0] != " ":
                    gaps.append(ch[i + 1][1] - ch[i - 1][1] - adv(ch[i - 1][0]))
            ink = [c for c in ch if c[0] != " "]
            if ink:
                widths.append(ink[-1][1] + adv(ink[-1][0]))
WORDSP = sorted(gaps)[len(gaps) // 2]
MEASURE = max(widths)
print(f"GPO word space {WORDSP:.3f} pt, measure {MEASURE:.2f} pt")


def pieces_of(text, at_hyphens=True):
    out = []
    for w in text.split(" "):
        parts = (re.findall(r"[^-]+-|[^-]+$", w) or [w]) if at_hyphens else [w]
        out += [(p, k == 0) for k, p in enumerate(parts)]
    return out


def set_lines(text, breaks=None, mark=None):
    """GPO style: ragged right, fixed word space, first line indented; breaks = TTB's pieces per line, to keep them.
    mark: True (all), or one flag per piece; flagged glyphs carry a 5th element True and are highlighted.
    """
    P = pieces_of(text, at_hyphens=bool(breaks))
    lines, i = (
        [],
        0,
    )  # new text never breaks at a hyphen (reads cleanly in a text compare)
    M = [bool(mark)] * len(P) if not isinstance(mark, list) else mark
    assert len(M) == len(P), (text[:40], len(M), len(P))
    while i < len(P):
        x0 = INDENT if not lines else 0.0
        if breaks:
            j = i + breaks[len(lines)]
        else:
            j = i + 1
            while j < len(P):
                w = (
                    x0
                    + sum(adv(p) for p, _ in P[i : j + 1])
                    + WORDSP * sum(1 for _, sb in P[i + 1 : j + 1] if sb)
                )
                if w > MEASURE + 0.01:
                    break
                j += 1
        lines.append((x0, P[i:j]))
        i = j
    out = []
    k = 0
    for x0, L in lines:
        g, x = [], x0
        for n, (p, sb) in enumerate(L):
            if n and sb:
                g.append((" ", x, "Melior", SIZE, M[k] and M[k - 1]))
                x += WORDSP
            for c in p:
                g.append((c, x, "Melior", SIZE, M[k]))
                x += adv(c)
            k += 1
        assert x <= MEASURE + 0.01, (text[:50], x)
        g.append((" ", x, "Melior", SIZE, False))
        out.append(g)
    return out


# what the proposed text adds to TTB's step, word by word (as the side-by-side marks it)
TTB_STEPS = {
    int(k): v
    for k, v in json.load(
        open(
            os.path.join(
                ROOT,
                "resources",
                "boundary",
                "description",
                "ttb-notice-243-steps.json",
            ),
            encoding="utf-8",
        )
    ).items()
}


def added_words(n):
    import difflib

    key = lambda w: w.strip(
        ",;:"
    )  # "377," in TTB's text is the same word as "377"
    a, b = (
        [key(w) for w in TTB_STEPS[n].split(" ")],
        [key(w) for w in S[n].split(" ")],
    )
    keep = [False] * len(b)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, a, b, autojunk=False
    ).get_opcodes():
        if op == "equal":
            for j in range(j1, j2):
                keep[j] = True
    return [not k for k in keep]


def paragraphs(lines):
    paras = []
    for l in lines:
        if (
            abs(l["ch"][0][1] - INDENT) < 1.0
            and l["ch"][0][3] == SIZE
            and re.match(r"\(\d+\) ", l["text"])
        ):
            paras.append([l])
        else:
            paras[-1].append(l)
    return paras


num = lambda p: int(re.match(r"\((\d+)\) ", p[0]["text"]).group(1))
body = lambda t: re.sub(r"^\(\d+\)\s*", "", t)

# Check with a reading-order text conversion (src/documents/pdf_text.py, poppler's pdftotext, makes the compare-text
# files); a column-blind conversion (Beyond Compare's default -simple mode) runs the three columns together even on
# TTB's own pages.

# ------------------------------------------------------------------ page 52586, column 3: steps (10)-(11)
c3 = col_lines(P86, 2)
i10 = next(i for i, l in enumerate(c3) if l["text"].startswith("(10) Proceed"))
i12 = next(i for i, l in enumerate(c3) if l["text"].startswith("(12) Proceed"))
tail = (
    set_lines(S[10], mark=added_words(10))
    + set_lines(S[11], mark=added_words(11))
    + [l["ch"] for l in c3[i12:]]
)
col86 = (
    [l["ch"] for l in c3[:i10]] + tail
)  # the whole column, re-spaced evenly so it still ends level with columns 1-2
lead86 = (c3[-1]["y"] - c3[0]["y"]) / (len(col86) - 1)
place86 = [(c3[0]["y"] + k * lead86, g) for k, g in enumerate(col86)]
print(
    f"52586 col 3: steps (10)-(11) {i12 - i10} -> {len(tail) - (len(c3) - i12)} lines; column leading {lead86:.3f} pt (TTB's 9.5-10.0)"
)

# ------------------------------------------------------------------ page 52588, column 2 from step (90); the rest on an added page
c2 = col_lines(P88, 1)
i90 = next(i for i, l in enumerate(c2) if l["text"].startswith("(90) Proceed"))
isig = next(i for i, l in enumerate(c2) if l["text"].startswith("Signed:"))
old = paragraphs(c2[i90:isig])
assert [num(p) for p in old] == list(range(90, 97))
lines88 = []
for k in range(90, 101):
    lines88 += [
        (g, n == 0) for n, g in enumerate(set_lines(S[k], mark=True))
    ]  # replace TTB's (90)-(92)
for p in old[3:]:  # TTB's (93)-(96) -> (101)-(104), TTB's line breaks kept
    n = num(p)
    new = S[n + 8]
    assert body(new) == body(
        " ".join(l["text"].strip() for l in p).replace("- ", "-")
    ), n
    br = [len(pieces_of(l["text"].strip())) for l in p]
    assert sum(br) == len(pieces_of(new)), (n, br)
    lines88 += [
        (g, m == 0)
        for m, g in enumerate(
            set_lines(
                new, br, mark=[True] + [False] * (len(pieces_of(new)) - 1)
            )
        )
    ]  # new number only
sig = c2[isig:]
sig_dy = [l["y"] - sig[0]["y"] for l in sig]
gap_sig = sig[0]["y"] - c2[isig - 1]["y"]

# Columns 2 and 3 from step (90) take the spacing TTB used in column 2 of this page: 10.4 pt between the lines of a step
# and 13.2 pt between steps. Column 2 holds as many lines as leave column 3 enough text above the signature block for a
# text converter to read TTB's signature lines as separate lines, as it does in TTB's file (xpdf joins them when only a
# few lines stand above them); the spare space at the foot of column 2 is spread between its steps, as GPO does.
WITHIN = BETWEEN = float(
    os.environ.get("NOTICE_LEAD", "9.5")
)  # GPO's 9.5 pt, even: no extra space between steps (a gap there also makes xpdf join the signature lines)
COL2_MAX = int(
    os.environ.get("NOTICE_COL2_LINES", "999")
)  # test switch; by default column 2 is filled


def stack(items, y):
    out = []
    for k, (g, first) in enumerate(items):
        if k:
            y += BETWEEN if first else WITHIN
        out.append([y, g, first])
    return out


fit = 1
while (
    fit < len(lines88)
    and stack(lines88[: fit + 1], c2[i90]["y"])[-1][0] <= BOTTOM + 0.01
):
    fit += 1
n2 = min(
    fit, COL2_MAX, len(lines88) - int(os.environ.get("NOTICE_MIN3", "0"))
)  # column 3 keeps >= 16 step lines above TTB's signature block, which a text
# converter (xpdf) needs to read the signature lines separately, as in TTB's file
# column 2 fills to the bottom; a step may continue into column 3, as TTB's step (82) runs from column 1 into column 2
place88 = {1: stack(lines88[:n2], c2[i90]["y"]), 2: stack(lines88[n2:], TOP)}
spare = BOTTOM - place88[1][-1][0]
starts = list(
    range(1, len(place88[1]))
)  # spread over every line gap, not only between steps
acc = 0.0
for k, q in enumerate(place88[1]):
    if k in starts:
        acc += spare / len(starts)
    q[0] += acc
ysig = place88[2][-1][0] + gap_sig
assert ysig + sig_dy[-1] <= BOTTOM + 0.01, (
    "signature block runs past the bottom of column 3"
)
place88[2] += [[ysig + dy, l["ch"], False] for dy, l in zip(sig_dy, sig)]
print(
    f"52588: col 2 {n2} lines from step (90) (room for {fit}; {spare:.2f} pt spread over {len(starts)} gaps); "
    f"col 3 {len(lines88) - n2} step lines, then TTB's signature block; BILLING CODE at y {place88[2][-1][0]:.2f}"
)


# ------------------------------------------------------------------ steps (49) and (85): one word corrected, in place
# Each corrected step is set in GPO's style and must take as many lines as TTB's; the lines whose words are unchanged keep
# TTB's glyphs, and only the lines that change are cleared (a band from 6 pt above to 1 pt below the baseline, inside the
# glyphs of that line and clear of the lines above and below, 9.5-10.4 pt away) and set anew on TTB's baseline.
def in_place(pno, col, n):
    L = col_lines(pno, col)
    k = next(
        i
        for i, l in enumerate(L)
        if l["text"].startswith(f"({n}) Proceed")
        and abs(l["ch"][0][1] - INDENT) < 1.0
    )
    j = next(
        i
        for i in range(k + 1, len(L))
        if re.match(r"\(\d+\) ", L[i]["text"])
        and abs(L[i]["ch"][0][1] - INDENT) < 1.0
    )
    old = L[k:j]
    assert body(
        " ".join(l["text"].strip() for l in old).replace("- ", "-")
    ) == body(TTB_STEPS[n]), n
    new = set_lines(S[n], mark=added_words(n))
    assert len(new) == len(old), (
        n,
        "the corrected step takes more lines than TTB's",
        len(old),
        len(new),
    )
    text = lambda g: "".join(c[0] for c in g).strip()
    placed = [
        (l["y"], g) for l, g in zip(old, new) if text(g) != l["text"].strip()
    ]
    assert not any(
        len(c) > 4 and c[4]
        for l, g in zip(old, new)
        if text(g) == l["text"].strip()
        for c in g
    ), n
    assert placed and body(" ".join(text(g) for g in new)) == body(S[n]), n
    return placed, L


FIXED = {P87: (2, 49), P88: (1, 85)}  # page -> (column, step)
assert all(S[n] != TTB_STEPS[n] for _, n in FIXED.values()), (
    "a corrected step is TTB's text"
)
place_fix = {}
for pno, (col, n) in FIXED.items():
    place_fix[pno], before = in_place(pno, col, n)
    for y, _ in place_fix[pno]:
        doc[pno].add_redact_annot(
            pymupdf.Rect(
                COLX[col] - 2, y - 6.0, COLX[col] + MEASURE + 4, y + 1.0
            ),
            fill=False,
        )
    doc[pno].apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
    )
    gone = {y for y, _ in place_fix[pno]}
    assert [l["text"] for l in col_lines(pno, col)] == [
        l["text"] for l in before if l["y"] not in gone
    ], (n, "clearing the changed lines touched others")
    print(
        f"step ({n}): {len(place_fix[pno])} line(s) set anew in place on page {52576 + pno}, column {col + 1}"
    )

# ------------------------------------------------------------------ the next document moves, unchanged and in place, to an added last page
# In TTB's reading order page 52588 runs: running head, columns 1-3 (column 3 = Kaw Valley), margin text, slug.
# The added page keeps Kaw Valley, the margin text and the slug where they were, so the order is unchanged.
doc.insert_pdf(pristine, from_page=P88, to_page=P88)
p86, p87, p88, added = doc[P86], doc[P87], doc[P88], doc[-1]
for r in (pymupdf.Rect(0, 0, 612, 55), pymupdf.Rect(40, 55, 395, 766)):
    added.add_redact_annot(r, fill=False)
added.apply_redactions(
    images=pymupdf.PDF_REDACT_IMAGE_NONE,
    graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
)

# ------------------------------------------------------------------ clear the replaced areas and set the text
p86.add_redact_annot(pymupdf.Rect(395, 55, 600, 766), fill=False)
p86.apply_redactions(
    images=pymupdf.PDF_REDACT_IMAGE_NONE,
    graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
)
p88.add_redact_annot(
    pymupdf.Rect(218, c2[i90 - 1]["y"] + 3, 394, 766), fill=False
)  # column 2 from step (90)
p88.add_redact_annot(
    pymupdf.Rect(395, 55, 600, 766), fill=False
)  # column 3 (moved)
p88.add_redact_annot(pymupdf.Rect(0, 766, 612, 792), fill=False)  # slug (moved)
p88.add_redact_annot(
    pymupdf.Rect(0, 55, 40, 792), fill=False
)  # margin text (moved)
p88.apply_redactions(
    images=pymupdf.PDF_REDACT_IMAGE_NONE,
    graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
)

# GPO's margin stamp on the added page ("lotter on DSK8BHNXB4PROD with PROPOSALS1", rotated, left margin): a text
# converter reads rotated text last on a page with text in only one column, which would put it after the slug line;
# set horizontally just above the slug, it reads stamp, then slug, as on TTB's page 52588.
stamp = [
    l
    for b in pristine[P88].get_text("rawdict")["blocks"]
    for l in b.get("lines", [])
    if l["spans"][0]["chars"][0]["origin"][0] < 24
]
assert len(stamp) == 1, len(stamp)
STAMP = "".join(c["c"] for sp in stamp[0]["spans"] for c in sp["chars"])
STAMP_F, STAMP_S = stamp[0]["spans"][0]["font"], stamp[0]["spans"][0]["size"]
added.add_redact_annot(pymupdf.Rect(0, 55, 24, 792), fill=False)
added.apply_redactions(
    images=pymupdf.PDF_REDACT_IMAGE_NONE,
    graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
)
tw = pymupdf.TextWriter(added.rect)
tw.append(pymupdf.Point(25, 764), STAMP, font=FONTS[STAMP_F], fontsize=STAMP_S)
tw.write_text(
    added, color=(1, 1, 1)
)  # white, as GPO sets its stamp and slug on TTB's pages ("1 g"): text only


def write(page, col, placed, per_line=False):
    tw = pymupdf.TextWriter(page.rect)
    for y, g, *_ in placed:
        for c, x, f, s, *_ in g:
            tw.append(
                pymupdf.Point(COLX[col] + x, y), c, font=FONTS[f], fontsize=s
            )
        if per_line:
            tw.write_text(page)
            tw = pymupdf.TextWriter(page.rect)
    tw.write_text(page)


write(p86, 2, place86)
write(p87, 2, place_fix[P87])
write(p88, 1, place_fix[P88])  # steps (49) and (85)
write(p88, 1, place88[1])
write(p88, 2, place88[2], per_line=True)

# The red notes (the running line here, the first-page note below) are images: red bold sans rendered to a PNG at 8 px per
# point, so they print crisply, add no font (every font in the copy stays embedded) and stay out of the compare text.
BOLD = next(
    (
        f
        for f in (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        )
        if os.path.exists(f)
    ),
    None,
)
assert BOLD, (
    "no bold sans font for the red notes (Arial Bold, Liberation Sans Bold or DejaVu Sans Bold)"
)
PX, NOTE_X0, NOTE_X1 = (
    8,
    45,
    567,
)  # pixels per point; the page's text width (GPO's seal, removed below, stood at x 42-82)


def red_note(text, size):
    """text in red bold sans, size pt, wrapped at spaces to the page's text width: PNG bytes, rows, height (pt), pixel size"""
    fnt = ImageFont.truetype(BOLD, round(size * PX))
    W = (NOTE_X1 - NOTE_X0) * PX
    rows, cur = [], ""
    dr = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    for w in text.split(" "):
        t = (cur + " " + w).strip()
        if dr.textlength(t, font=fnt) > W and cur:
            rows.append(cur)
            cur = w
        else:
            cur = t
    rows.append(cur)
    lead, pad = (
        round(1.3 * size * PX),
        round(0.1 * size * PX),
    )  # 52 px lines and 4 px margins for the 5 pt note
    im = Image.new("RGBA", (W, lead * len(rows) + 2 * pad), (255, 255, 255, 0))
    dr = ImageDraw.Draw(im)
    for k, t in enumerate(rows):
        dr.text((0, pad + lead * k), t, font=fnt, fill=(190, 0, 0, 255))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue(), len(rows), im.height / PX, im.size


# a running line in the top margin of every page this script changes, in the page content (not an annotation), set after
# the redactions above (the added page's top was cleared): 7 pt, its baseline at about y 24, above GPO's running head (y 33.8)
RUNNING = "UNOFFICIAL COPY - petitioner's copy with the proposed changes set in and highlighted; not the official Federal Register text"
png, n, h, RUN_PX = red_note(RUNNING, 7.0)
assert n == 1, "running line wider than the page's text"
run_rect = pymupdf.Rect(NOTE_X0, 27.5 - h, NOTE_X1, 27.5)
run_xref = p86.insert_image(run_rect, stream=png)
for page in (p87, p88, added):
    page.insert_image(
        run_rect, xref=run_xref
    )  # the same image object on all four pages

# yellow highlights over the changed wording: filled shapes drawn in the page content beneath everything on the page (so
# they print and survive annotation stripping; they add no text, so a text compare is unaffected)
YELLOW = (1.0, 0.93, 0.3)


def highlight(page, cols_placed):
    rects = []
    for col, placed in cols_placed:
        for y, g, *_ in placed:
            run = []
            for t in g + [(" ", 0, "Melior", SIZE, False)]:
                if len(t) > 4 and t[4]:
                    run.append(t)
                    continue
                while run and run[-1][0] == " ":
                    run.pop()
                if run:
                    x0, x1 = (
                        COLX[col] + run[0][1],
                        COLX[col] + run[-1][1] + adv(run[-1][0]),
                    )
                    rects.append(
                        pymupdf.Rect(x0 - 0.4, y - 6.9, x1 + 0.4, y + 2.3)
                    )
                run = []
    if rects:  # the outline MuPDF draws for a highlight annotation: the box with rounded ends bulging out h/(3 sqrt 2)
        sh = page.new_shape()
        P = pymupdf.Point
        for r in rects:
            k = r.height / (3 * 2**0.5)
            sh.draw_bezier(
                P(r.x0, r.y1),
                P(r.x0 - k, r.y1 - k),
                P(r.x0 - k, r.y0 + k),
                P(r.x0, r.y0),
            )
            sh.draw_line(P(r.x0, r.y0), P(r.x1, r.y0))
            sh.draw_bezier(
                P(r.x1, r.y0),
                P(r.x1 + k, r.y0 + k),
                P(r.x1 + k, r.y1 - k),
                P(r.x1, r.y1),
            )
        sh.finish(color=None, fill=YELLOW, width=0, closePath=True)
        sh.commit(overlay=False)  # overlay=False: under all the page's content
    return len(rects)


nh = (
    highlight(p86, [(2, place86)])
    + highlight(p87, [(2, place_fix[P87])])
    + highlight(p88, [(1, place_fix[P88] + place88[1]), (2, place88[2])])
)
print(f"highlighted {nh} runs of changed wording")

# ------------------------------------------------------------------ GPO's digital signature and seal
# GPO signs its file (the field USGPOSignature, locked by DocMDP /Perms); its signed byte range cannot hold for this altered
# copy, so a viewer that checks it would report GPO's signature broken. The field's widget also draws GPO's "Authenticated
# U.S. Government Information" seal at the top left of page 1. Remove the widget (and so the seal), the AcroForm that held
# only this field, and /Perms; garbage collection on save drops the signature itself. The links on page 1 stay.
cat = doc.pdf_catalog()
acro = int(doc.xref_get_key(cat, "AcroForm")[1].split()[0])
fields = [
    int(x)
    for x in re.findall(r"(\d+) 0 R", doc.xref_get_key(acro, "Fields")[1])
]
assert [doc.xref_get_key(f, "FT")[1] for f in fields] == ["/Sig"], (
    "the docket PDF's AcroForm holds more than GPO's signature"
)
p1 = doc[0]
sig = [w for w in p1.widgets() if w.xref in fields]
assert [w.field_name for w in sig] == ["USGPOSignature"], [
    w.field_name for w in sig
]
p1.delete_widget(sig[0])
cat_src = doc.xref_object(cat, compressed=True)
doc.update_object(
    cat, re.sub(r"/(AcroForm|Perms)\s*\d+\s+0\s+R", "", cat_src)
)  # the keys go, not just set to null

# ------------------------------------------------------------------ first-page note (an image, so it is not text)
NOTE = (
    "UNOFFICIAL COPY prepared by the petitioner (Dan McLaughlin): TTB's Notice No. 243 with the Hickory Sands District boundary "
    "changes proposed to TTB (discussed with TTB on October 15, 2026) set into TTB's pages 52586, 52587 and 52588 and highlighted in yellow (the start of the next document, Kaw Valley, "
    "is moved to an added last page). Not the official Federal Register text; the official notice is FR Doc. 2026-16670 on govinfo.gov. "
    "GPO's digital signature and authentication seal are removed, as this copy is altered."
)
png, n, h, NOTE_PX = red_note(NOTE, 5.0)
assert n <= 3 and 33 - h >= 12, (
    n,
    h,
)  # three lines, above GPO's running head as before
p1.insert_image(pymupdf.Rect(NOTE_X0, 33 - h, NOTE_X1, 33), stream=png)

# the metadata names the petitioner's copy, not GPO's file: the Info dictionary only (GPO's XMP packet, which viewers
# prefer, still carried govinfo's creator, producer and dates)
doc.del_xml_metadata()
now = pymupdf.get_pdf_now()
doc.set_metadata(
    {
        "title": "Notice No. 243 (91 FR 52576) - UNOFFICIAL copy with the proposed Hickory Sands District changes (Oct. 15, 2026)",
        "author": "Dan McLaughlin (petitioner), from TTB's docket copy TTB-2026-0005-0001",
        "subject": "The petitioner's unofficial copy, modified from FR Doc. 2026-16670; not the official Federal Register text",
        "keywords": "",
        "creator": "The petitioner's unofficial copy, modified from FR Doc. 2026-16670 (src/documents/make_notice_copy.py)",
        "producer": f"PyMuPDF {pymupdf.VersionBind}; GPO's digital signature removed (altered copy)",
        "creationDate": now,
        "modDate": now,
        "trapped": "",
    }
)
doc.save(OUT + ".tmp", garbage=3, deflate=True)

# MuPDF maps the hyphen glyph to U+00AD (soft hyphen) in the ToUnicode maps of the fonts it adds; make it U+002D
d2 = pymupdf.open(OUT + ".tmp")
n = 0
# ... and gives the fonts it adds generic names, flags and metrics (ascent 952 for TTB's 745); give them TTB's, since
# text converters use the ascent and descent to decide which lines belong together
DESC = {}
for xref in range(1, pristine.xref_length()):
    try:
        if pristine.xref_get_key(xref, "Type")[1] == "/FontDescriptor":
            DESC.setdefault(
                pristine.xref_get_key(xref, "FontName")[1],
                {
                    k: pristine.xref_get_key(xref, k)[1]
                    for k in (
                        "Flags",
                        "ItalicAngle",
                        "StemV",
                        "StemH",
                        "Ascent",
                        "Descent",
                        "CapHeight",
                        "XHeight",
                        "FontBBox",
                    )
                    if pristine.xref_get_key(xref, k)[0] != "null"
                },
            )
    except Exception:
        pass
for xref in range(1, d2.xref_length()):
    try:
        is0 = d2.xref_get_key(xref, "Subtype")[1] == "/Type0"
    except Exception:
        continue
    if is0:
        name = d2.xref_get_key(xref, "BaseFont")[1].replace(" Regular", "")
        if name in DESC:
            d2.xref_set_key(xref, "BaseFont", name)
            cid = int(
                d2.xref_get_key(xref, "DescendantFonts")[1]
                .strip("[]")
                .split()[0]
            )
            d2.xref_set_key(cid, "BaseFont", name)
            fd = int(d2.xref_get_key(cid, "FontDescriptor")[1].split()[0])
            d2.xref_set_key(fd, "FontName", name)
            for k, v in DESC[name].items():
                d2.xref_set_key(fd, k, v)
for xref in range(1, d2.xref_length()):
    try:
        is0 = d2.xref_get_key(xref, "Subtype")[1] == "/Type0"
    except Exception:
        continue
    if is0:
        tu = d2.xref_get_key(xref, "ToUnicode")
        if tu[0] == "xref":
            tx = int(tu[1].split()[0])
            s = d2.xref_stream(tx)
            t = re.sub(
                rb"(?m)^(<[0-9A-Fa-f]+>\s+)<00[Aa][Dd]>\s*$", rb"\1<002d>", s
            )  # target values only
            if t != s:
                d2.update_stream(tx, t)
                n += 1
d2.save(OUT, garbage=3, deflate=True)
d2.close()
os.remove(OUT + ".tmp")
print(f"fixed hyphen mapping in {n} font(s); wrote {OUT}")

# the saved copy: no signature, form or XMP left; no annotations but the links; the running-line image on each changed
# page and the note on page 1 (images, not text)
chk = pymupdf.open(OUT)
cat = chk.pdf_catalog()
assert not re.search(
    r"/(AcroForm|Perms|Metadata)\b", chk.xref_object(cat, compressed=True)
), "GPO's signature, form or XMP left in the copy"
assert chk.get_sigflags() == -1 and not chk.is_form_pdf
assert not [a.type for pg in chk for a in pg.annots()] and not any(
    pg.first_widget for pg in chk
), "annotations other than links left"
has = lambda size: [
    i
    for i, pg in enumerate(chk)
    if any(tuple(im[2:4]) == tuple(size) for im in pg.get_images(full=True))
]
assert has(RUN_PX) == [P86, P87, P88, len(chk) - 1], (
    "running line on pages",
    has(RUN_PX),
)
assert has(NOTE_PX) == [0], ("first-page note on pages", has(NOTE_PX))
assert not any("UNOFFICIAL" in pg.get_text() for pg in chk), (
    "a red note became text"
)
chk.close()
