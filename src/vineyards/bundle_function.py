"""Makes the vineyard form's Edge Function as one file, for the dashboard.

The function's source (src/vineyards/functions/vineyard-submit/index.ts)
imports the site's rules (docs/assets/vineyard-blocks.js, the module the
page runs) and TTB's proposed Llano Uplift AVA as the site publishes it
(docs/assets/aquifer/llano-uplift.geojson). Supabase's dashboard editor
deploys what is pasted into it, so this writes one self-contained file,
target/vineyard-submit/index.ts: the rules inlined (their exports kept as
the names the function uses), and the Llano Uplift polygon as a constant.
The listed vineyards, which a change must name, are not bundled: the
function reads the site's assets/vineyards/known.json when a change comes,
so a merged vineyard needs no new deploy; only a change to these files does.
Nothing is sent anywhere. With --copy it also puts the file on the
clipboard (macOS's pbcopy), ready to paste (src/vineyards/SETUP.md).

    .venv/bin/python -E -s -B src/vineyards/bundle_function.py --copy

It prints the file's size and SHA-256. tests/test_vineyard_function.py
runs this same file in node against stand-ins for Supabase, Cloudflare and
GitHub. Standard library only.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
SOURCE = os.path.join(
    ROOT, "src", "vineyards", "functions", "vineyard-submit", "index.ts"
)
RULES = os.path.join(ROOT, "docs", "assets", "vineyard-blocks.js")
LLANO = os.path.join(ROOT, "docs", "assets", "aquifer", "llano-uplift.geojson")
OUT = os.path.join(ROOT, "target", "vineyard-submit", "index.ts")
IMPORT_RULES = 'import * as rules from "./vineyard-blocks.js";'
IMPORT_LLANO = (
    'import llanoUplift from "./llano-uplift.json" with { type: "json" };'
)
EXPORT = re.compile(r"^export (const|function|class) (\w+)", re.MULTILINE)


def bundle(source=SOURCE, rules=RULES, llano=LLANO):
    """The one-file function.

    Args:
        source: The function's index.ts.
        rules: The site's vineyard-blocks.js.
        llano: The Llano Uplift polygon (GeoJSON).

    Returns:
        The file's text.

    Raises:
        SystemExit: The source does not import the two files exactly once
            each, or the rules export something this cannot inline.
    """
    with open(source, encoding="utf-8") as fh:
        code = fh.read()
    with open(rules, encoding="utf-8") as fh:
        module = fh.read()
    with open(llano, encoding="utf-8") as fh:
        polygon = json.dumps(json.load(fh), separators=(",", ":"))
    for line in (IMPORT_RULES, IMPORT_LLANO):
        if code.count(line) != 1:
            raise SystemExit(f"{source}: expected one line {line}")
    names = [m.group(2) for m in EXPORT.finditer(module)]
    if module.count("export ") != len(names) or not names:
        raise SystemExit(f"{rules}: an export this cannot inline")
    inlined = EXPORT.sub(r"\1 \2", module)
    rules_block = "\n".join(
        [
            (
                "// docs/assets/vineyard-blocks.js, inlined by "
                "src/vineyards/bundle_function.py"
            ),
            "const rules = (() => {",
            inlined.rstrip("\n"),
            f"return {{ {', '.join(names)} }};",
            "})();",
        ]
    )
    llano_block = (
        "// docs/assets/aquifer/llano-uplift.geojson, inlined\n"
        f"const llanoUplift = {polygon};"
    )
    code = code.replace(IMPORT_RULES, rules_block).replace(
        IMPORT_LLANO, llano_block
    )
    head = (
        "// @ts-nocheck\n"
        "// Made by src/vineyards/bundle_function.py from "
        "src/vineyards/functions/vineyard-submit/index.ts: paste it whole "
        "into the Supabase dashboard (src/vineyards/SETUP.md); edit the "
        "sources, never this.\n"
    )
    return head + code


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
