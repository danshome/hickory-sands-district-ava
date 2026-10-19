"""Makes the logo vote's Edge Function as one file, for the dashboard.

The function's source (src/vote/functions/vote-api/index.ts) imports the
page's own designs (docs/assets/logo-vote/designs.json), so it accepts votes
only for designs the page knows. Supabase's dashboard editor deploys what is
pasted into it, so this writes one self-contained file,
target/vote-api/index.ts, with the designs' ids as a constant. Nothing is
sent anywhere. With --copy it also puts the file on the clipboard (macOS's
pbcopy), ready to paste (src/vote/SETUP.md).

    .venv/bin/python -E -s -B src/vote/bundle_function.py --copy

It prints the file's size and SHA-256. tests/test_vote_function.py runs this
same file in node against stand-ins for Supabase and Cloudflare. Standard
library only.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
SOURCE = os.path.join(ROOT, "src", "vote", "functions", "vote-api", "index.ts")
DESIGNS = os.path.join(ROOT, "docs", "assets", "logo-vote", "designs.json")
OUT = os.path.join(ROOT, "target", "vote-api", "index.ts")
IMPORT = 'import designs from "./designs.json" with { type: "json" };'


def bundle(source=SOURCE, designs=DESIGNS):
    """The one-file function.

    Args:
        source: The function's index.ts.
        designs: The page's designs.json.

    Returns:
        The file's text.

    Raises:
        SystemExit: The source does not import the designs exactly once, or
            a design has no id.
    """
    with open(source, encoding="utf-8") as fh:
        code = fh.read()
    with open(designs, encoding="utf-8") as fh:
        listed = json.load(fh)
    if code.count(IMPORT) != 1:
        raise SystemExit(f"{source}: expected one line {IMPORT}")
    ids = [d.get("id") for d in listed]
    if not ids or not all(isinstance(i, str) and i for i in ids):
        raise SystemExit(f"{designs}: a design without an id")
    inlined = (
        "// docs/assets/logo-vote/designs.json's ids, inlined by "
        "src/vote/bundle_function.py\n"
        "const designs = "
        + json.dumps([{"id": i} for i in ids], separators=(",", ":"))
        + ";"
    )
    head = (
        "// @ts-nocheck\n"
        "// Made by src/vote/bundle_function.py from "
        "src/vote/functions/vote-api/index.ts: paste it whole into the "
        "Supabase dashboard (src/vote/SETUP.md); edit the sources, never "
        "this.\n"
    )
    return head + code.replace(IMPORT, inlined)


def main(argv=None):
    """Writes the one-file function, and copies it when asked.

    Args:
        argv: The command line's arguments (sys.argv[1:] when None).

    Returns:
        0.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--copy", action="store_true", help="also put it on the clipboard"
    )
    parser.add_argument("--out", default=OUT, help="where to write it")
    args = parser.parse_args(argv)
    text = bundle()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    data = text.encode("utf-8")
    print(
        f"{os.path.relpath(args.out, ROOT)}: {len(data):,} bytes, "
        f"SHA-256 {hashlib.sha256(data).hexdigest()}"
    )
    if args.copy:
        subprocess.run(["pbcopy"], input=data, check=True)
        print("copied: paste it into the dashboard's editor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
