"""Plain text of a PDF for a text compare, one paragraph per line.

The compare-text files in folder 2: comparing TTB's notice with the copy that
has the proposed changes shows only the changed steps. Uses poppler's
pdftotext, which Homebrew installs with GDAL, so every machine that builds
makes the same text (Dan, 2026-10-17: no Beyond Compare or other desktop tool
under the covers). Its -bbox-layout mode gives every line with its position,
and the paragraphs are rebuilt from those positions:

- a line indented past its block's left edge starts a paragraph (the Federal
  Register indents every paragraph);
- a block that starts flush carries on the paragraph before it when that one
  stopped at the end of a full line without ending a sentence or clause, so a
  paragraph broken by a column or page break stays on one line;
- the page furniture goes between paragraphs at the page break, the same way
  on every page, so both files place it alike: the running head before the
  page's text; GPO's slug along the bottom and its note in the left margin
  after it, left to right (the copy with the changes moves page 52588's slug
  and note, set level, to its added last page);
- a word broken at a line end is joined, keeping the hyphen when it is a real
  one: after a digit ("1,668-foot"), before a capitalised word
  ("Mason-McCulloch") or another hyphen ("Farm-to-Market"), inside a URL, or
  when the hyphenated form is printed elsewhere in the PDF ("light-duty").

Checks that every printed character is in the text, in order (spaces and
line-end hyphens aside), or exits 1.

Usage: pdf_text.py IN.pdf OUT.txt
"""

import html
import re
import shutil
import subprocess
import sys

# points: running head above y 50; slug below y 750 (text ends at 742); note
# left of x 30
HEAD, FOOT, LEFT = 50, 750, 30
# a line indented > 3 pt starts a paragraph; one ending < 25 pt short is full
INDENT, FULL = 3, 25


def num(attrs, name):
    """The number in attribute `name` of a tag's attribute text `attrs`."""
    return float(re.search(rf'{name}="([-\d.]+)"', attrs).group(1))


def words_of(s):
    """The words of a line of poppler's XHTML, unescaped."""
    return [html.unescape(w) for w in re.findall(r"<word[^>]*>(.*?)</word>", s)]


def paragraphs(xml):
    """Rebuilds the paragraphs from poppler's -bbox-layout XHTML.

    Args:
        xml: The output of pdftotext -bbox-layout.

    Returns:
        (paras, printed): the paragraphs, each a list of lines, each a list of
        words, with the page furniture placed between them at the page
        breaks; and every printed word, in poppler's order.
    """
    # paragraphs (lists of lines, each a list of words); furniture waiting to
    # go out
    paras, pending, printed = [], [], []
    last_full = False  # did the last body line run to its block's right edge?
    for page in re.findall(r"<page[^>]*>(.*?)</page>", xml, re.S):
        blocks = []
        for attrs, block in re.findall(
            r"<block([^>]*)>(.*?)</block>", page, re.S
        ):
            lines = [
                (num(a, "xMin"), num(a, "xMax"), w)
                for a, line in re.findall(
                    r"<line([^>]*)>(.*?)</line>", block, re.S
                )
                if (w := words_of(line))
            ]
            if lines:
                blocks.append(
                    (
                        num(attrs, "xMin"),
                        num(attrs, "yMin"),
                        num(attrs, "xMax"),
                        num(attrs, "yMax"),
                        lines,
                    )
                )
        for b in blocks:
            printed += [w for _, _, ws in b[4] for w in ws]
        head = [b for b in blocks if b[3] < HEAD]
        foot = sorted(
            (b for b in blocks if b[1] > FOOT or b[2] < LEFT),
            key=lambda b: (b[0], b[1]),
        )
        pending += [[ws for _, _, ws in b[4]] for b in head]
        for b in blocks:
            if b in head or b in foot:
                continue
            left, right = (
                min(x0 for x0, _, _ in b[4]),
                max(x1 for _, x1, _ in b[4]),
            )
            for i, (x0, x1, ws) in enumerate(b[4]):
                carry_on = (
                    paras
                    and (x0 <= left + INDENT)
                    and (
                        i > 0
                        or (
                            last_full
                            and not re.search(
                                r"[.:;?!]\W*$", " ".join(paras[-1][-1])
                            )
                        )
                    )
                )
                if not carry_on:
                    paras += pending
                    pending = []
                    paras.append([])
                paras[-1].append(ws)
                last_full = x1 >= right - FULL
        pending += [[ws for _, _, ws in b[4]] for b in foot]
    paras += pending
    return paras, printed


def join(lines, flat):
    """Joins a paragraph's lines into one line of text.

    A word broken at a line end is joined, keeping its hyphen when it is a
    real one (see the module docstring).

    Args:
        lines: The paragraph's lines, each a list of words.
        flat: Every printed word, joined by spaces, so that a hyphenated form
            printed elsewhere keeps its hyphen.

    Returns:
        The paragraph, as one string.
    """
    s = " ".join(lines[0])
    for ws in lines[1:]:
        a, y = s.split()[-1], ws[0]
        if a.endswith("-") and len(a) > 1:
            x, word = a[:-1], re.match(r"[\w-]*", y).group()
            real = (
                x[-1].isdigit()
                or re.match(r"[A-Z][a-z]", y)
                or "-" in y
                or "/" in x
                or f"{x}-{word}" in flat
            )
            # "/" in x: a URL, broken only at its own slashes and hyphens
            s = (s if real else s[:-1]) + " ".join(ws)
        elif a.endswith(("–", "—", "/")):
            # a dash or a URL's slash at a line end: no space after it
            s += " ".join(ws)
        else:
            s += " " + " ".join(ws)
    return s


def squash(s):
    """S without spaces or hyphens, to compare text before and after joining."""
    return re.sub(r"[\s\-]", "", s)


def text_of(paras, printed, out):
    """The text, one line per paragraph; exits if anything went missing.

    Exits, naming `out`, if joining a paragraph lost or added a character, or
    if a printed word is in no paragraph.

    Args:
        paras: The paragraphs, from paragraphs().
        printed: Every printed word, from paragraphs().
        out: The name of the file the text is for (for the messages).

    Returns:
        The lines of text, one per paragraph; GPO's "* * * * *", one star per
        line in the PDF, on one line.
    """
    flat = " ".join(printed)
    text = []
    for p in paras:
        # "ACTION :": the bold caps and their colon
        t = re.sub(r"(?<=\S) :(?=\s|$)", ":", join(p, flat))
        # joining lost or added a character
        if squash(t) != squash(" ".join(w for ws in p for w in ws)):
            sys.exit(f"{out}: a paragraph lost text in joining: {t[:80]}")
        star = set(t) <= {"*", " "}  # GPO's "* * * * *", one star per line here
        if star and text and set(text[-1]) <= {"*", " "}:
            text[-1] += " " + t
        else:
            text.append(t)
    # every printed word went somewhere
    if sum(len(ws) for p in paras for ws in p) != len(printed):
        sys.exit(
            f"{out}: {len(printed)} printed words but "
            f"{sum(len(ws) for p in paras for ws in p)} in the text"
        )
    return text


def main(src, out):
    """Writes the compare text of a PDF and prints how many paragraphs.

    Args:
        src: The PDF.
        out: The text file to write.
    """
    exe = shutil.which("pdftotext") or sys.exit(
        "pdftotext (poppler) is needed: brew install poppler"
    )
    xml = subprocess.run(
        [exe, "-enc", "UTF-8", "-bbox-layout", src, "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    paras, printed = paragraphs(xml)
    text = text_of(paras, printed, out)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(text) + "\n")
    print(
        f"{out.split('/')[-1]}: {len(text)} paragraphs from {len(printed)} "
        "printed words"
    )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
