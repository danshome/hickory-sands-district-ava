"""Plain text of a PDF for side-by-side comparison (the compare-text files in folder 2). Uses pdftotext (Beyond
Compare's bundled copy or poppler's) when present, so the text matches what reviewers' diff tools see; otherwise
PyMuPDF. pdftotext joins a word broken at a line end by dropping the hyphen, real hyphens too ("West Farm-" / "to-Market"
-> "Farmto-Market"). Its -raw mode keeps the line ends, so those are found there and put back: a hyphen after a digit
("1,668-foot"), before a capitalised word ("Mason-McCulloch") or another hyphen ("Farm-to-Market"), or whose
hyphenated form is printed elsewhere in the PDF ("light-duty"). Usage: pdf_text.py IN.pdf OUT.txt"""
import os, re, shutil, subprocess, sys
src, out = sys.argv[1], sys.argv[2]
for exe in ("/Applications/Beyond Compare.app/Contents/MacOS/pdftotext", shutil.which("pdftotext") or ""):
    if exe and os.path.exists(exe):
        text, raw = (subprocess.run([exe, "-enc", "UTF-8", "-nopgbrk", *m, src, "-"], check=True, capture_output=True,
                                    text=True).stdout for m in ([], ["-raw"]))
        lines, flat, found, back = raw.splitlines(), " ".join(raw.split()), 0, 0
        for a, b in zip(lines, lines[1:]):
            if not (a.rstrip().endswith("-") and b.split()): continue
            x, y = a.split()[-1][:-1], b.split()[0]
            if b.split() == [y] and y.endswith("-"): y = y[:-1]  # broken again at its own line end: the next pair's
            word = re.match(r"[\w-]*", y).group()
            if x and (x[-1].isdigit() or re.match(r"[A-Z][a-z]", y) or "-" in y or "/" in x or f"{x}-{word}" in flat):
                found += 1  # "/" in x: a URL, which the Federal Register breaks only at its own slashes and hyphens
                text, k = re.subn(rf"(?<!\w){re.escape(x + y)}", lambda _: f"{x}-{y}", text, count=1); back += k
        open(out, "w", encoding="utf-8").write(text)
        print(f"{os.path.basename(out)}: {back} of {found} line-end hyphens put back"); sys.exit(back != found)
import pymupdf
with pymupdf.open(src) as doc: open(out, "w", encoding="utf-8").write("".join(p.get_text() for p in doc))
