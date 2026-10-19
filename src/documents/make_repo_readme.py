"""Generate the GitHub README from its template and recorded build figures.

The committed figures let prose-only edits and commit hooks work without GIS
outputs. --from-build refreshes them; --check never writes either file.
"""

import argparse
from decimal import Decimal
from decimal import ROUND_HALF_UP
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = Path("documents/repository-README.template.md")
FIGURES = Path("documents/repository-README.figures.json")
TOKEN = re.compile(r"\{\{([a-z_][a-z_0-9]*)\}\}")
GRIT_KEYS = {
    "notice_only": "Notice No. 243, not the petition",
    "lobe": "granite lobe",
    "put_back": "put back",
    "lane": "lane wording",
    "petition_only": "petition, not Notice No. 243",
}


def rounded(value: float) -> str:
    """Format whole units, rounded half up once, with thousands separators."""
    whole = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{int(whole):,}"


def build_figures(work: Path) -> dict[str, str]:
    """Read and format the figures from a checked boundary build.

    Args:
        work: Build work directory containing statistics and GIS outputs.

    Returns:
        Named strings for every template placeholder.

    Raises:
        ValueError: The build does not have exactly one points file.
    """
    steps = json.loads((work / "proposed-steps.json").read_text("utf-8"))
    grit = json.loads(
        (work / "review/grit-change-stats.json").read_text("utf-8")
    )
    diff = json.loads((work / "review/ttb-diff-stats.json").read_text("utf-8"))
    points = list((work / "gis").glob("*-points-EPSG4269.geojson"))
    if len(points) != 1:
        raise ValueError("Expected exactly one build points GeoJSON")
    result = {
        "steps": str(len(steps["steps"])),
        "points": str(
            len(json.loads(points[0].read_text("utf-8"))["features"])
        ),
        "area": f"{steps['sqmi']:.2f}",
        "big": str(diff["big"]),
        "big_m": f"{diff['big_m']:g}",
        "pieces": f"{sum(v['pieces'] for v in diff['areas'].values()):,}",
        "median": rounded(diff["median_m"]),
        "revision_only": rounded(
            diff["areas"]["drawing"]["revision_only_acres"]
        ),
        "map_only": rounded(
            diff["areas"]["drawing"]["map_explorer_only_acres"]
        ),
    }
    for name in ("notice_243", "petition", "revision"):
        result[f"area_{name}"] = f"{grit['sqmi'][name]:.2f}"
    for name, key in GRIT_KEYS.items():
        for field in ("acres", "granite_acres"):
            result[f"{name}_{field}"] = rounded(grit["areas"][key][field])
    return result


def render(template: str, figures: dict[str, str]) -> str:
    """Fill only named placeholders, refusing missing or unknown fields.

    Args:
        template: Editable Markdown with double-braced placeholders.
        figures: Formatted numeric strings from the build.

    Returns:
        Complete README text.

    Raises:
        ValueError: Placeholders or numeric values are invalid.
    """
    names = set(TOKEN.findall(template))
    if names != set(figures):
        raise ValueError(
            "Template placeholders differ from figures: "
            f"{sorted(names.symmetric_difference(figures))}"
        )
    if not all(
        isinstance(v, str) and re.fullmatch(r"\d[\d,.]*", v)
        for v in figures.values()
    ):
        raise ValueError("README figures must be formatted numeric strings")
    rendered = TOKEN.sub(lambda match: figures[match[1]], template)
    if "{{" in rendered or "}}" in rendered:
        raise ValueError("Malformed README placeholder")
    return rendered


def generate(root: Path, work: Path | None, *, check: bool) -> int:
    """Render or check the README, optionally refreshing its build figures.

    Args:
        root: Repository directory.
        work: Build directory, or None to use committed figures.
        check: Compare without writing when true.

    Returns:
        Zero on success, three for stale generated files.
    """
    figures = (
        build_figures(work)
        if work is not None
        else json.loads((root / FIGURES).read_text("utf-8"))
    )
    rendered = render((root / TEMPLATE).read_text("utf-8"), figures)
    outputs = {root / "README.md": rendered}
    if work is not None:
        outputs[root / FIGURES] = (
            json.dumps(figures, indent=2, sort_keys=True) + "\n"
        )
    if check:
        stale = [
            p.name
            for p, text in outputs.items()
            if not p.exists() or p.read_text("utf-8") != text
        ]
        if stale:
            print(
                f"Stale generated files: {', '.join(stale)}. "
                f"Edit {TEMPLATE}, not README.md; run ./build.sh readme "
                "for prose, or ./build.sh site-data for new build figures."
            )
            return 3
        return 0
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8")
    return 0


def main() -> int:
    """Run the README writer or its read-only commit/build check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--from-build", type=Path, metavar="WORK")
    args = parser.parse_args()
    try:
        return generate(ROOT, args.from_build, check=args.check)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"README generation failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
