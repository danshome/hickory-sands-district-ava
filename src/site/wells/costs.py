"""The three wells' arithmetic: lift energy and well costs.

Lift energy is the cited kWh per acre-foot per foot (resources/wells/
constants.json) times the lift, static level plus drawdown. Costs are read
between the rows and columns of TWDB's Uniform Costing Model tables and
raised to July 2026 by the cited indexes. Each figure is rounded once, here,
as the page shows it. Standard library only.
"""

import math

from . import params

DASH = "\u2013"  # an en dash, for ranges


def whole(x):
    """A figure as a whole number, rounded half up (NumPy's medians)."""
    return math.floor(x + 0.5)


def span(a, b):
    """A range of whole numbers, their thousands separated, dashed."""
    return f"{whole(a):,}{DASH}{whole(b):,}"


def interp(xs, ys, x):
    """Linear interpolation inside xs."""
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            t = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    raise SystemExit(f"{x} is outside the cost table's {xs[0]}-{xs[-1]}")


def cost(c, table, depths, depth, gpm):
    """A Uniform Costing Model cost, in July 2026 dollars."""
    gpms = c["ucm_capacities_gpm"]
    rows = [interp(gpms, row, gpm) for row in c[table]]
    return interp(c[depths], rows, depth) * to_2026(c)


def to_2026(c):
    """The UCM's January 2023 dollars to July 2026."""
    a, b = c["region_f_reindex"]
    return (a / b) * (c["enr_cci_2026_07"] / c["enr_cci_2023_09"])


def money(x):
    """Dollars to the thousand, or in millions from a million up."""
    if x >= 1e6:
        return f"${x / 1e6:.2f} million"
    return f"${whole(x / 1000) * 1000:,}"


def ratio(a, b):
    """The ratio b / a to one decimal, as text."""
    return f"{b / a:.1f}"


def thousands(x):
    """A cost to the nearest thousand dollars, as "$14,000"."""
    return f"${whole(x / 1000) * 1000:,}"


def energy_figures(c, figs, deep_drawdown):
    """Lift energy: the outcrop well's range, the deep well's, the ratios."""
    kwh = c["lift_kwh_per_acft_ft"]
    low, high = c["assumed_drawdown_ft"]
    mid = (low + high) / 2
    out = figs["outcrop_level"]
    deep = (figs["deep_level_gwdb"], figs["deep_level_sdr"])
    o_low, o_mid, o_high = (kwh * (out + d) for d in (low, mid, high))
    d_low, d_high = (kwh * (lv + deep_drawdown) for lv in deep)
    tens = 10
    return {
        "lift_kwh": f"{kwh:.2f}",
        "lift_whp": f"{c['lift_whp_hr_per_acft_ft']:.3f}",
        "lift_kwh_ideal": (
            f"{c['lift_whp_hr_per_acft_ft'] / c['hp_hr_per_kwh']:.3f}"
        ),
        "drawdown_low": low,
        "drawdown_high": high,
        "drawdown_mid": whole(mid),
        "pumping_mid": whole(out + mid),
        "outcrop_energy": span(
            whole(o_low / tens) * tens, whole(o_high / tens) * tens
        ),
        "deep_energy": span(
            whole(d_low / tens) * tens, whole(d_high / tens) * tens
        ),
        "energy_ratio_mid": f"{d_low / o_mid:.1f} to {d_high / o_mid:.1f}",
        "energy_ratio_range": (
            f"{whole(d_low / o_high)} to {whole(d_high / o_low)}"
        ),
        "depth_ratio": whole(figs["deep_depth"] / figs["outcrop_depth"]),
    }


def cost_figures(c, figs):
    """The cost rows: city grade and irrigation grade, and small wells."""
    d_out = figs["outcrop_irrigation_depth"]
    d_deep = whole(figs["deep_depth"] / params.COST_DEPTH_STEP_FT) * (
        params.COST_DEPTH_STEP_FT
    )
    q_out = figs["outcrop_irrigation_yield"]
    q_deep = figs["deep_yield"]
    pws = ("ucm_public_supply_usd_2023_01", "ucm_depths_public_supply_ft")
    irr = ("ucm_irrigation_usd_2023_01", "ucm_depths_irrigation_ft")
    irr_limit = c["ucm_depths_irrigation_ft"][-1]
    city_out = {q: cost(c, *pws, d_out, q) for q in (q_out, q_deep)}
    city_deep = {q: cost(c, *pws, d_deep, q) for q in (q_out, q_deep)}
    irr_out = cost(c, *irr, d_out, q_out)
    irr_deep = cost(c, *irr, irr_limit, q_out)
    same = [city_deep[q] / city_out[q] for q in (q_out, q_deep)]
    share = c["nrcs_share"]
    pump = c["nrcs_pump_usd"] / share
    enr = c["enr_cci_2026_07"] / c["enr_cci_2023_09"]  # 2023 prices
    shallow = (c["nrcs_well_usd"]["150"] / share + pump) * enr
    deeper = (c["nrcs_well_usd"]["300"] / share + pump) * enr
    region_k = [x * enr for x in c["region_k_private_well_usd"]]
    a, b = c["region_f_reindex"]
    dry = c["dry_borehole_share"]
    extra = [f * dry / (1 - dry) for f in c["dry_hole_cost_share"]]
    fives = 5
    return {
        "cost_depth_outcrop": d_out,
        "cost_depth_deep": d_deep,
        "cost_gpm_outcrop": q_out,
        "cost_gpm_deep": q_deep,
        "city_outcrop_small": money(city_out[q_out]),
        "city_deep_small": money(city_deep[q_out]),
        "city_ratio_small": ratio(city_out[q_out], city_deep[q_out]),
        "city_outcrop_large": money(city_out[q_deep]),
        "city_deep_large": money(city_deep[q_deep]),
        "city_ratio_large": ratio(city_out[q_deep], city_deep[q_deep]),
        "city_ratio_typical": ratio(city_out[q_out], city_deep[q_deep]),
        "depth_alone": f"{whole(min(same))}{DASH}{whole(max(same))}",
        "irrigation_outcrop": money(irr_out),
        "irrigation_limit_ft": irr_limit,
        "irrigation_deep": money(irr_deep),
        "irrigation_ratio": ratio(irr_out, irr_deep),
        "ucm_min_gpm": c["ucm_capacities_gpm"][0],
        "small_outcrop": (
            f"{thousands(deeper)}{DASH}{thousands(max(region_k))}"
        ),
        "small_granite": (
            f"{thousands(shallow)}{DASH}{thousands(max(region_k))}"
        ),
        "reindex": f"{a / b:.4f}",
        "enr_factor": f"{enr:.4f}",
        "bid_spread": f"±{whole(100 * c['bid_spread'])}%",
        "dry_share": f"{whole(100 * dry)}%",
        "dry_extra": (
            f"{whole(100 * min(extra) / fives) * fives}{DASH}"
            f"{whole(100 * max(extra) / fives) * fives}%"
        ),
    }
