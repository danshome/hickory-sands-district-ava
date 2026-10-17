"""Pre-commit hook: refuse to commit a file that contains a word listed in .private-words (one word or phrase per line,
case-insensitive; # starts a comment). .private-words is gitignored, so the list itself is never committed. Binary
files are skipped. Exit 1 and name each file and line when a word is found."""
import os, re, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LIST = os.path.join(ROOT, ".private-words")
if not os.path.exists(LIST): sys.exit(0)
words = [w.strip() for w in open(LIST, encoding="utf-8") if w.strip() and not w.lstrip().startswith("#")]
if not words: sys.exit(0)
pat = re.compile("|".join(re.escape(w) for w in words), re.I)
bad = 0
for path in sys.argv[1:]:
    try: data = open(path, "rb").read()
    except OSError: continue
    if b"\0" in data[:8192]: continue
    for i, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
        if pat.search(line): print(f"{path}:{i}: contains a word from .private-words"); bad += 1
sys.exit(1 if bad else 0)
