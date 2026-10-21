"""Every figure of The land page's three wells, from the groups' records.

Each measure, per group (classify.groups()):

- depth: the completed depth on the record;
- yield: the largest test on each report, 0-gpm tests kept; its test type
  is the type of the test behind the reported yield;
- water level: TWDB's latest measurement for a Groundwater Database well,
  the driller's level at completion for a driller's report;
- drawdown: of a record's tests with both a yield and a drawdown, the one
  with the highest specific capacity;
- logged water-bearing stratum: the rock a driller logged over the water
  (the drawing record's water class, where its basis is the log).

Lift energy is the cited kWh per acre-foot per foot (resources/wells/
constants.json) times the lift, static level plus drawdown. Costs are read
between the rows and columns of TWDB's Uniform Costing Model tables and
raised to July 2026 by the cited indexes. Each figure is rounded once, here,
as the page shows it.
"""

import collections
import re

import numpy as np

from ..aquifer import params as aquifer_params
from . import classify
from . import costs
from . import params

# The page's words for TWDB's test types and use groups.
TEST_WORDS = {"": "not stated"}
USE_WORDS = (
    "irrigation",
    "domestic",
    "stock",
    "public supply",
    "industrial",
    "recreation",
    "other or unknown",
)
SANDSTONE = aquifer_params.CLASSES.index("sandstone")
GRANITE = aquifer_params.CLASSES.index("granite")


def num(text):
    """A report's number ("1,200", "45+"), or None."""
    try:
        return float(str(text).replace(",", "").replace("+", "").strip())
    except ValueError:
        return None


def quartiles(values):
    """The 25th, 50th and 75th percentiles (NumPy's linear), and the count."""
    v = np.array([x for x in values if x is not None], float)
    if not len(v):
        raise SystemExit("an empty group: an input misses the counties")
    a, b, c = np.percentile(v, [25, 50, 75])
    return float(a), float(b), float(c), len(v)


def median(values):
    """The median and the count."""
    return quartiles(values)[1:4:2]


def mix(counter, words=None):
    """Counts as "word n, word n": the commonest first, ties by name."""
    words = words or {}
    items = sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))
    return ", ".join(f"{words.get(k, str(k).lower())} {n:,}" for k, n in items)


def tests(report):
    """A well's tests, its Groundwater Database record's included."""
    found = list(report.get("WellTests") or [])
    for g in report.get("GWDB") or []:
        found += g.get("WellTests") or []
    return found


def best_drawdown(report):
    """The test with the highest specific capacity: (drawdown, type)."""
    best = None
    for t in tests(report):
        y, d = num(t.get("Yield")), num(t.get("Drawdown"))
        if y and d and y > 0 and d > 0 and (best is None or y / d > best[0]):
            best = (y / d, d, t.get("TestType") or "")
    return None if best is None else best[1:]


def group_figures(name, wells, report):
    """One group's figures and counts.

    Args:
        name: Its name ("outcrop").
        wells: Its wells.
        report: A well's report, by the well.

    Returns:
        (figures, counts): dicts keyed name_measure.
    """
    figs, counts = {}, {}
    p25, p50, p75, n = quartiles(w["depth"] for w in wells)
    figs[f"{name}_depth"] = costs.whole(p50)
    figs[f"{name}_depth_mid"] = costs.span(p25, p75)
    counts[f"{name}_wells"] = len(wells)
    figs[f"{name}_n"] = len(wells)
    figs[f"{name}_with_depth"] = n
    tested = [w for w in wells if w["yield"] is not None]
    figs[f"{name}_yield"] = costs.whole(median(w["yield"] for w in tested)[0])
    figs[f"{name}_yield_n"] = len(tested)
    figs[f"{name}_yield_types"] = mix(
        collections.Counter(w["ytest"] for w in tested), TEST_WORDS
    )
    big = sum(1 for w in tested if w["yield"] >= params.BIG_YIELD_GPM)
    figs[f"{name}_yield_big"] = "none" if big == 0 else f"{big:,}"
    levels = [w for w in wells if w["level"] is not None]
    figs[f"{name}_level"] = costs.whole(median(w["level"] for w in levels)[0])
    gwdb = [w["level"] for w in levels if w["uid"].startswith("G")]
    sdr = [w["level"] for w in levels if w["uid"].startswith("S")]
    figs[f"{name}_level_n"] = len(levels)
    figs[f"{name}_level_gwdb_n"] = len(gwdb)
    figs[f"{name}_level_sdr_n"] = len(sdr)
    drawdowns = [d for d in (best_drawdown(report(w)) for w in wells) if d]
    figs[f"{name}_drawdown_n"] = len(drawdowns)
    figs[f"{name}_drawdown_types"] = (
        mix(collections.Counter(t for _, t in drawdowns), TEST_WORDS) or "none"
    )
    if drawdowns:
        a, b, c, _ = quartiles(d for d, _ in drawdowns)
        counts[f"{name}_drawdown_quartiles"] = [a, b, c]
    logs = [w for w in wells if w["wbasis"] == params.LOGGED_BASIS]
    counts[f"{name}_logs"] = len(logs)
    counts[f"{name}_logs_sandstone"] = sum(
        1 for w in logs if w["wclass"] == SANDSTONE
    )
    counts[f"{name}_logs_granite"] = sum(
        1 for w in logs if w["wclass"] == GRANITE
    )
    return figs, counts, levels, drawdowns


def percent(part, whole_):
    """A share as a whole percent."""
    return costs.whole(100 * part / whole_)


def example_figures(rep):
    """The granite example's figures, from its report's own fields.

    Args:
        rep: The report (the 3D page's cleaned record).

    Returns:
        The figures the page and the drawing show: only depths, the
        casing, the test and the date; never a position or a name.
    """
    lith = [
        (num(x["TopDepth"]), num(x["BottomDepth"]), x["LithologyDescription"])
        for x in rep["Lithology"]
    ]
    casing = rep["Casing"][0]
    strata = rep["WaterStrata"][0]
    level = rep["WaterLevels"][0]
    test = rep["WellTests"][0]
    material = re.search(r"\(([^)]+)\)", casing["CasingMaterial"])
    return {
        "example_report": rep["WellReportTrackingNumber"],
        "example_county": rep["County"],
        "example_use": rep["ProposedUse"].lower(),
        "example_drilled": rep["DrillingEndDate"],
        "example_year": rep["DrillingEndDate"][:4],
        "example_layers": [[a, b, d.lower()] for a, b, d in lith],
        "example_soil_ft": costs.whole(lith[0][1]),
        "example_gravel_ft": costs.whole(lith[1][1]),
        "example_gravel": lith[1][2].lower(),
        "example_rock": lith[2][2].lower(),
        "example_depth": costs.whole(lith[-1][1]),
        "example_casing_ft": costs.whole(num(casing["BottomDepth"])),
        "example_casing": (
            f"{casing['CasingType'].lower()} "
            f"{material[1] if material else casing['CasingMaterial']}"
        ),
        "example_water": costs.span(
            num(strata["TopDepth"]), num(strata["BottomDepth"])
        ),
        "example_water_top": num(strata["TopDepth"]),
        "example_water_bottom": num(strata["BottomDepth"]),
        "example_level": costs.whole(num(level["Measurement"])),
        "example_level_method": level["MeasurementMethod"].lower(),
        "example_level_date": level["MeasurementDate"],
        "example_yield": num(test["Yield"]),
        "example_test": test["TestType"].lower(),
    }


def make(wells, report, c, total):
    """Every figure.

    Args:
        wells: classify.classify()'s wells.
        report: A well's report, by the well.
        c: The constants (each one's "value").
        total: The number of wells read.

    Returns:
        (figures, counts, drawing): what the page shows, what is kept for
        review, and what the drawings are drawn from.
    """
    groups = classify.groups(wells)
    figs, counts = {"records": total}, {}
    per = {}
    for name, sel in groups.items():
        f, k, levels, drawdowns = group_figures(name, sel, report)
        figs.update(f)
        counts.update(k)
        per[name] = (sel, levels, drawdowns)
    deep, deep_levels, deep_drawdowns = per["deep"]
    gwdb = [w["level"] for w in deep_levels if w["uid"].startswith("G")]
    sdr = [w["level"] for w in deep_levels if w["uid"].startswith("S")]
    figs["deep_level_gwdb"] = costs.whole(median(gwdb)[0])
    figs["deep_level_sdr"] = costs.whole(median(sdr)[0])
    figs["deep_drawdown"] = costs.whole(median(d for d, _ in deep_drawdowns)[0])
    tops = [classify.top_depth(w) for w in deep]
    top = median(tops)[0]
    figs["deep_top"] = (
        costs.whole(top / params.TOP_STEP_FT) * params.TOP_STEP_FT
    )
    bottoms = [w["ground"] - w["bot7"] for w in deep if w["bot7"] is not None]
    counts["deep_top_median"] = top
    figs["deep_top_low"], figs["deep_top_high"] = params.DEEP_TOP_FT
    uses = collections.Counter(
        USE_WORDS[w["use"]] for w in deep if w["yield"] is not None
    )
    figs["deep_uses"] = mix(uses, {u: u for u in USE_WORDS})
    figs["deep_irrigation_n"] = uses.get("irrigation", 0)
    for name in ("outcrop", "granite", "deep"):
        logs = counts[f"{name}_logs"]
        figs[f"{name}_logs"] = logs
        for rock in ("sandstone", "granite"):
            n = counts[f"{name}_logs_{rock}"]
            figs[f"{name}_logs_{rock}"] = n
            figs[f"{name}_logs_{rock}_pct"] = percent(n, logs) if logs else 0
    figs["big_yield_gpm"] = params.BIG_YIELD_GPM
    figs["counties"] = len(params.COUNTIES)
    figs.update(costs.energy_figures(c, figs, figs["deep_drawdown"]))
    figs.update(costs.cost_figures(c, figs))
    example = example_figures(report_by_id(wells, report, c))
    layers = example.pop("example_layers")
    figs.update(example)
    gravel = c["gravel_view_ft"]
    figs.update({f"gravel_{k}": v for k, v in gravel.items()})
    drawing = {
        "example_layers": layers,
        "deep_bottom": (
            median(bottoms)[0] if bottoms else figs["deep_depth"] * 1.05
        ),
        "deep_top": top,
    }
    return figs, counts, drawing


def report_by_id(wells, report, c):
    """The granite example's report, found by its number."""
    uid = "S" + c["granite_example_report"]
    for w in wells:
        if w["uid"] == uid:
            return report(w)
    raise SystemExit(f"no report {c['granite_example_report']} in the wells")
