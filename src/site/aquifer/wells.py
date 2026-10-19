"""TWDB's well reports for the 3D aquifer page, without people's names.

Sources: TWDB's Submitted Driller's Reports (SDRDownload.zip) and
Groundwater Database (GWDBDownload.zip), read in place from the cache.

Which wells: every report whose position lies in a cell of TWDB's Llano
Uplift model where any layer is active (the model's domain: TWDB's Hickory
outline plus about five miles, which takes in the whole Precambrian core of
the uplift, where most wells find no Hickory Aquifer). A driller's report
marked NAD27 is moved to NAD83 with the NADCON 5.0 CONUS grid; the rest, and
every Groundwater Database position, are used as published. A Groundwater
Database well that names a driller's report in the set is drawn once, as
that report, with its record attached.

People's names and addresses are removed before anything is written
(src/site/aquifer/privacy.py), and empty fields are left out (the page
shows only the fields that hold something). Lithology classes and use
groups: src/site/aquifer/params.py.

write() writes wells/index.json (the tiles, the counts, the thinned
overview and every well's filter values), wells/heads-<n>.json (every
well's head, params.HEADS_PER_FILE to a file, for the page's every-well
layer), wells/draw-<tile>.json (what the page draws, its logs included, per
params.TILE_DEG tile) and wells/detail-<cell>.json (the raw reports, per
params.DETAIL_DEG cell, fetched when a well is clicked).
"""

import collections
import csv
import io
import math
import os
import re
import zipfile

from osgeo import osr

from . import params
from . import privacy
from . import record

csv.field_size_limit(10**9)
osr.UseExceptions()

POSITION_DUPES = frozenset({"Dlat", "Mlat", "Slat", "Dlong", "Mlong", "Slong"})
SDR_TABLES = (
    ("WellLithology", "Lithology"),
    ("WellBoreHole", "BoreHole"),
    ("WellCasing", "Casing"),
    ("WellStrata", "WaterStrata"),
    ("WellLevels", "WaterLevels"),
    ("WellTest", "WellTests"),
)
GWDB_TABLES = (
    ("WellLithology", "Lithology"),
    ("WellBoreHole", "BoreHole"),
    ("WellCasing", "Casing"),
    ("WellTest", "WellTests"),
)
GWDB_LEVELS = (
    "WaterLevelsMinor",
    "WaterLevelsMajor",
    "WaterLevelsCombination",
    "WaterLevelsOtherUnassigned",
)
LEVEL_FIELDS = (
    "MeasurementDate",
    "MeasurementYear",
    "DepthFromLSD",
    "WaterElevation",
    "Status",
    "MethodOfMeasurement",
    "MeasuringAgency",
)
LATEST_LEVELS = 5
CLASS_RULES = [
    (params.CLASSES.index(name), re.compile(rx, re.IGNORECASE))
    for name, rx in params.CLASS_RULES
]
OTHER = params.CLASSES.index("other")
UNLOGGED = params.CLASSES.index("unlogged")
NADCON_PIPELINE = (
    "+proj=pipeline +step +proj=axisswap +order=2,1 +step +proj=unitconvert "
    "+xy_in=deg +xy_out=rad +step +proj=hgridshift "
    "+grids=us_noaa_nadcon5_nad27_nad83_1986_conus.tif +step "
    "+proj=unitconvert +xy_in=rad +xy_out=deg +step +proj=axisswap +order=2,1"
)
# NADCON 5.0's shift at Mason, a check that the grid is the one PROJ found.
MASON = (-99.23, 30.75)
NADCON_SHIFT_M = (5.0, 80.0)


def rows(archive, member):
    """The rows of one of TWDB's pipe-separated tables.

    Args:
        archive: An open zipfile.ZipFile.
        member: The table's name in it.

    Yields:
        Each row as a dict, its values stripped; rows of the wrong length
        are skipped.
    """
    with archive.open(member) as raw:
        text = io.TextIOWrapper(raw, encoding="latin-1", newline="")
        reader = csv.reader(text, delimiter="|", quoting=csv.QUOTE_NONE)
        head = next(reader)
        for row in reader:
            if len(row) == len(head):
                yield dict(zip(head, (v.strip() for v in row), strict=True))


def num(value):
    """A report's number, or None."""
    try:
        return float(str(value).replace(",", "").replace("+", "").strip())
    except ValueError:
        return None


def lith_class(text):
    """An interval's class: the first rule its description matches."""
    for cls, rx in CLASS_RULES:
        if rx.search(text or ""):
            return cls
    return OTHER


def water_source(segs, strata):
    """The rock a well's water comes from, and on what basis.

    Args:
        segs: The logged intervals, [top, bottom, class], sorted.
        strata: The water-bearing strata, [top, bottom].

    Returns:
        (class, top, bottom, basis): the class of the logged interval that
        overlaps the deepest water-bearing stratum most (basis 0); else the
        deepest logged interval (basis 1); else unlogged (basis 2).
    """
    if segs and strata:
        top, bot = max(strata, key=lambda s: s[1])
        best = None
        for a, b, cls in segs:
            overlap = min(b, bot) - max(a, top)
            if overlap > 0 and (best is None or overlap > best[0]):
                best = (overlap, cls)
        if best:
            return best[1], top, bot, 0
    if segs:
        a, b, cls = max(segs, key=lambda s: (s[1], s[0]))
        return cls, a, b, 1
    return UNLOGGED, None, None, 2


def max_yield(rec):
    """The highest tested yield on a report (gpm) and its test, or None."""
    best = None
    tests = list(rec.get("WellTests", []))
    for g in rec.get("GWDB", []):
        tests += g.get("WellTests", [])
    for test in tests:
        v = num(test.get("Yield"))
        if v is not None and v >= 0 and (best is None or v > best[0]):
            best = (v, test.get("TestType", ""))
    return best


def use_group(raw):
    """A report's use group (params.USE_GROUPS's index)."""
    return params.USE_MAP.get((raw or "").strip(), params.OTHER_USE)


def segments(lith, depth):
    """A well's logged intervals, cut at its depth, with their classes."""
    out = []
    limit = depth or float("inf")
    for item in lith or []:
        top, bot = num(item.get("TopDepth")), num(item.get("BottomDepth"))
        if top is None or bot is None or bot <= top or top >= limit:
            continue
        out.append(
            [top, min(bot, limit), lith_class(item.get("LithologyDescription"))]
        )
    out.sort()
    return out


def sdr_depth(rec):
    """A driller's report's depth: its deepest bore hole or log interval."""
    cands = [num(b.get("BottomDepth")) for b in rec.get("BoreHole", [])]
    cands += [num(b.get("BottomDepth")) for b in rec.get("Lithology", [])]
    cands = [c for c in cands if c and c > 0]
    return max(cands) if cands else None


def first_level(rec, key):
    """A report's first water level (ft below the ground), or None."""
    for level in rec.get("WaterLevels", []):
        v = num(level.get(key))
        if v is not None and v >= 0:
            return v
    return None


def tile_of(lon, lat, size):
    """A position's tile key: its column and row of size-degree tiles."""
    return f"{math.floor(lon / size)}_{math.floor(lat / size)}"


def compact(item):
    """A record with its empty fields left out, at any depth."""
    if isinstance(item, dict):
        return {k: compact(v) for k, v in item.items() if v != ""}
    if isinstance(item, list):
        return [compact(v) for v in item]
    return item


def r1(value):
    """A value rounded to 0.1, or None."""
    return None if value is None else round(value, 1)


def from_nad27():
    """NAD27 to NAD83 longitude and latitude by the NADCON 5.0 CONUS grid.

    Returns:
        An osr.CoordinateTransformation.

    Raises:
        SystemExit: The shift at Mason is not what NADCON 5.0 gives, so PROJ
            did not find the grid.
    """
    nad83 = osr.SpatialReference()
    nad83.ImportFromEPSG(4269)
    nad83.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    nad27 = osr.SpatialReference()
    nad27.ImportFromEPSG(4267)
    nad27.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    options = osr.CoordinateTransformationOptions()
    options.SetOperation(NADCON_PIPELINE)
    ct = osr.CoordinateTransformation(nad27, nad83, options)
    lon, lat, _ = ct.TransformPoint(*MASON)
    shift = math.hypot((lon - MASON[0]) * 95_700, (lat - MASON[1]) * 110_850)
    if not NADCON_SHIFT_M[0] < shift < NADCON_SHIFT_M[1]:
        raise SystemExit(
            f"NADCON 5.0 shift at Mason looks wrong: {shift:.1f} m"
        )
    return ct


class Domain:
    """The model's domain: cells where any layer is active."""

    def __init__(self, lookup):
        """Takes the drill grid's lookup (model.write_drill_grid()).

        Args:
            lookup: Its polynomial and flags.
        """
        self.poly = lookup["polynomial"]
        self.flags = lookup["flags"]

    def __contains__(self, lonlat):
        """Whether a (longitude, latitude) lies in an active model cell."""
        u = lonlat[0] - self.poly["lon_c"]
        v = lonlat[1] - self.poly["lat_c"]
        t = [
            u ** (n - j) * v**j
            for n in range(self.poly["degree"] + 1)
            for j in range(n + 1)
        ]
        r = round(sum(a * b for a, b in zip(self.poly["row"], t, strict=True)))
        c = round(sum(a * b for a, b in zip(self.poly["col"], t, strict=True)))
        if not (0 <= r < params.ROWS and 0 <= c < params.COLS):
            return False
        return bool(self.flags[r, c] & 16)


def read_sdr(path, domain, scrub, ct):
    """The driller's reports in the model's domain, with their tables.

    Args:
        path: SDRDownload.zip.
        domain: The Domain.
        scrub: The Scrubber, which learns every name it passes.
        ct: from_nad27().

    Returns:
        (reports by tracking number, name words by record id, counts).
    """
    counts = collections.Counter()
    sdr, names = {}, {}
    with zipfile.ZipFile(path) as z:
        for w in rows(z, "SDRDownload/WellData.txt"):
            found = [w[k] for k in privacy.NAMES_SDR]
            scrub.learn(found)
            la, lo = num(w["CoordDDLat"]), num(w["CoordDDLong"])
            if la is None or lo is None:
                continue
            lo = -abs(lo)
            datum = w["HorizontalDatumType"]
            if datum == "NAD27":
                lo, la, _ = ct.TransformPoint(lo, la)
            if (lo, la) not in domain:
                continue
            tid = w["WellReportTrackingNumber"]
            rec = {
                k: v
                for k, v in w.items()
                if k not in privacy.REMOVED_SDR and k not in POSITION_DUPES
            }
            rec["_lonlat"] = [
                round(lo, params.DECIMALS),
                round(la, params.DECIMALS),
            ]
            rec["PositionUsed"] = (
                "moved from NAD27 to NAD83 (NADCON 5.0)"
                if datum == "NAD27"
                else f"as reported ({datum or 'datum not given'})"
            )
            sdr[tid] = rec
            names["S" + tid] = privacy.name_tokens(found)
        counts["sdr_inside"] = len(sdr)
        for table, field in SDR_TABLES:
            for r in rows(z, f"SDRDownload/{table}.txt"):
                tid = r.get("WellReportTrackingNumber")
                if tid in sdr:
                    sdr[tid].setdefault(field, []).append(
                        {
                            k: v
                            for k, v in r.items()
                            if k != "WellReportTrackingNumber"
                        }
                    )
        wanted = {
            r["PluggingReportTrackingNumber"]: t
            for t, r in sdr.items()
            if r.get("PluggingReportTrackingNumber")
        }
        plugs = {}
        for p in rows(z, "SDRDownload/PlugData.txt"):
            found = [p[k] for k in privacy.NAMES_PLUG]
            scrub.learn(found)
            pid = p["PluggingReportTrackingNumber"]
            tid = wanted.get(pid)
            if not tid and p.get("WellReportTrackingNumber") in sdr:
                tid = p["WellReportTrackingNumber"]
            if not tid:
                continue
            names["S" + tid] |= privacy.name_tokens(found)
            rec = {
                k: v
                for k, v in p.items()
                if k not in privacy.REMOVED_PLUG and k not in POSITION_DUPES
            }
            plugs[pid] = rec
            sdr[tid].setdefault("PluggingReports", []).append(rec)
        for r in rows(z, "SDRDownload/PlugRange.txt"):
            pid = r["PluggingReportTrackingNumber"]
            if pid in plugs:
                plugs[pid].setdefault("PlugRanges", []).append(
                    {
                        k: v
                        for k, v in r.items()
                        if k != "PluggingReportTrackingNumber"
                    }
                )
        counts["sdr_plugging_reports"] = len(plugs)
    return sdr, names, counts


def read_gwdb(path, domain, scrub):
    """The Groundwater Database wells in the model's domain.

    Args:
        path: GWDBDownload.zip.
        domain: The Domain.
        scrub: The Scrubber, which learns every name it passes.

    Returns:
        (wells by state well number, name words by record id, counts).
    """
    counts = collections.Counter()
    gw, names = {}, {}
    with zipfile.ZipFile(path) as z:
        for w in rows(z, "GWDBDownload/WellMain.txt"):
            found = [w[k] for k in privacy.NAMES_GWDB]
            scrub.learn(found)
            la, lo = num(w["LatitudeDD"]), num(w["LongitudeDD"])
            if la is None or lo is None:
                continue
            lo = -abs(lo)
            if (lo, la) not in domain:
                continue
            swn = w["StateWellNumber"]
            rec = {
                k: v
                for k, v in w.items()
                if k not in privacy.REMOVED_GWDB and k not in POSITION_DUPES
            }
            rec["_lonlat"] = [
                round(lo, params.DECIMALS),
                round(la, params.DECIMALS),
            ]
            gw[swn] = rec
            names["G" + swn] = privacy.name_tokens(found)
        counts["gwdb_inside"] = len(gw)
        for table, field in GWDB_TABLES:
            for r in rows(z, f"GWDBDownload/{table}.txt"):
                swn = r.get("StateWellNumber")
                if swn in gw:
                    gw[swn].setdefault(field, []).append(
                        {
                            k: v
                            for k, v in r.items()
                            if k not in ("StateWellNumber", "County", "Aquifer")
                        }
                    )
        levels = collections.defaultdict(list)
        for table in GWDB_LEVELS:
            for r in rows(z, f"GWDBDownload/{table}.txt"):
                if r.get("StateWellNumber") in gw:
                    levels[r["StateWellNumber"]].append(
                        {k: r[k] for k in LEVEL_FIELDS}
                    )
    for swn, found in levels.items():
        found.sort(
            key=lambda r: r["MeasurementDate"] or r["MeasurementYear"] or "",
            reverse=True,
        )
        gw[swn]["WaterLevels"] = found[:LATEST_LEVELS]
        gw[swn]["WaterLevelMeasurements"] = str(len(found))
    return gw, names, counts


def draw_record(w):
    """What the page draws for a well, as a list (the page's order)."""
    cls, wtop, wbot, basis = w["water"]
    return [
        w["uid"],
        w["lonlat"][0],
        w["lonlat"][1],
        r1(w["depth"]) if w["depth"] else None,
        [[round(a, 1), round(b, 1), c] for a, b, c in w["segs"]],
        r1(w["level"]),
        [[round(a, 1), round(b, 1)] for a, b in w["strata"]],
        1 if w["hickory"] else 0,
        tile_of(*w["lonlat"], params.DETAIL_DEG),
        w["use"],
        cls,
        r1(wtop),
        r1(wbot),
        basis,
        None if w["yield"] is None else round(w["yield"][0], 1),
        "" if w["yield"] is None else w["yield"][1],
    ]


# A well's head, as wells/heads-<n>.json holds it: what the page draws for
# every well and shows in its popup's first lines, without the log.
HEAD_FIELDS = (
    "uid",
    "lon",
    "lat",
    "depth_ft",
    "hickory (GWDB)",
    "use_group",
    "water_class",
    "water_top_ft",
    "water_bottom_ft",
    "water_basis",
    "yield_gpm",
    "yield_test",
)


def head_record(w):
    """A well's head (HEAD_FIELDS), from its drawing record's values."""
    r = draw_record(w)
    return [r[0], r[1], r[2], r[3], r[7], *r[9:]]


def write(paths, lookup, out_dir, extra_words=()):
    """Writes the wells' files.

    Args:
        paths: The inputs, by name (inputs.ensure()).
        lookup: The drill grid's lookup (model.write_drill_grid()).
        out_dir: The page's new data folder; the files go in its wells/.
        extra_words: Words that blank any free text holding them.

    Returns:
        (figures, wells, names, scrubber): the figures the page shows, the
        wells drawn (dicts: uid, lonlat, depth, water, yield, use, ...), the
        name words by record id and the Scrubber, for privacy.check().
    """
    wells_dir = os.path.join(out_dir, "wells")
    os.makedirs(wells_dir, exist_ok=True)
    domain = Domain(lookup)
    scrub = privacy.Scrubber(extra_words)
    sdr, names, counts = read_sdr(
        paths["twdb-sdr"], domain, scrub, from_nad27()
    )
    gw, gnames, gcounts = read_gwdb(paths["twdb-gwdb"], domain, scrub)
    names.update(gnames)
    counts.update(gcounts)
    for rec in [*sdr.values(), *gw.values()]:
        scrub.count(rec)

    linked = {
        swn: rec["WellReportTrackingNumber"]
        for swn, rec in gw.items()
        if rec.get("WellReportTrackingNumber") in sdr
    }
    for swn, tid in linked.items():
        sdr[tid].setdefault("GWDB", []).append(gw[swn])
        # The report shows the Groundwater Database record inside it, so
        # both records' names are looked for in both.
        names["S" + tid] |= names["G" + swn]
        names["G" + swn] = names["S" + tid]
    wells = []
    for tid, rec in sdr.items():
        depth = sdr_depth(rec)
        if not depth:
            counts["no_depth_sdr"] += 1  # a head only; no line
        strata = [
            [num(s.get("TopDepth")), num(s.get("BottomDepth"))]
            for s in rec.get("WaterStrata", [])
        ]
        wells.append(
            {
                "uid": "S" + tid,
                "rec": rec,
                "lonlat": rec["_lonlat"],
                "depth": depth,
                "segs": segments(rec.get("Lithology"), depth),
                "level": first_level(rec, "Measurement"),
                "strata": [
                    s
                    for s in strata
                    if s[0] is not None and s[1] is not None and s[1] > s[0]
                ],
                "hickory": any(
                    g.get("Aquifer") == "Hickory" for g in rec.get("GWDB", [])
                ),
                "use": use_group(rec.get("ProposedUse")),
            }
        )
    for swn, rec in gw.items():
        if swn in linked:
            continue
        depth = num(rec.get("WellDepth"))
        if not depth:
            counts["no_depth_gwdb"] += 1
        wells.append(
            {
                "uid": "G" + swn,
                "rec": rec,
                "lonlat": rec["_lonlat"],
                "depth": depth,
                "segs": segments(rec.get("Lithology"), depth),
                "level": first_level(rec, "DepthFromLSD"),
                "strata": [],
                "hickory": rec.get("Aquifer") == "Hickory",
                "use": use_group(rec.get("WellUse")),
            }
        )
    for w in wells:
        w["water"] = water_source(w["segs"], w["strata"])
        w["yield"] = max_yield(w["rec"])
        w["tile"] = tile_of(*w["lonlat"], params.TILE_DEG)

    # The drawing is made from the reports as published (a log line keeps its
    # rock class); then every free text that may name someone is blanked.
    scrub.finish()
    for tid, rec in sdr.items():
        scrub.walk(rec, names["S" + tid])
    for swn, rec in gw.items():
        scrub.walk(rec, names["G" + swn])

    tiles = collections.defaultdict(list)
    details = collections.defaultdict(dict)
    for w in wells:
        tiles[w["tile"]].append(w)
        rec = dict(w["rec"])
        rec.pop("_lonlat", None)
        rec["GWDB"] = [
            {k: v for k, v in g.items() if k != "_lonlat"}
            for g in rec.get("GWDB", [])
        ]
        if not rec["GWDB"]:
            del rec["GWDB"]
        details[tile_of(*w["lonlat"], params.DETAIL_DEG)][w["uid"]] = compact(
            rec
        )
    index_tiles = {}
    for key, found in sorted(tiles.items()):
        tx, ty = (int(v) for v in key.split("_"))
        record.write_json(
            os.path.join(wells_dir, f"draw-{key}.json"),
            [draw_record(w) for w in found],
        )
        index_tiles[key] = {
            "bbox": [
                round(tx * params.TILE_DEG, 2),
                round(ty * params.TILE_DEG, 2),
                round((tx + 1) * params.TILE_DEG, 2),
                round((ty + 1) * params.TILE_DEG, 2),
            ],
            "count": len(found),
        }
    for key, found in sorted(details.items()):
        record.write_json(os.path.join(wells_dir, f"detail-{key}.json"), found)

    cells = {}
    for w in wells:
        key = (
            math.floor(w["lonlat"][0] / params.OVERVIEW_DEG),
            math.floor(w["lonlat"][1] / params.OVERVIEW_DEG),
        )
        score = (bool(w["segs"]), w["depth"] or 0)
        if key not in cells or score > cells[key][0]:
            cells[key] = (score, w)
    overview = [draw_record(w) for _, w in cells.values()]
    figs = {
        "wells_sdr_inside": counts["sdr_inside"],
        "wells_gwdb_inside": counts["gwdb_inside"],
        "wells_gwdb_linked": len(linked),
        "wells_drawn": len(wells),
        "wells_drawn_sdr": sum(w["uid"][0] == "S" for w in wells),
        "wells_drawn_gwdb": sum(w["uid"][0] == "G" for w in wells),
        "wells_logged": sum(bool(w["segs"]) for w in wells),
        "wells_with_level": sum(w["level"] is not None for w in wells),
        "wells_with_strata": sum(bool(w["strata"]) for w in wells),
        "wells_with_yield": sum(w["yield"] is not None for w in wells),
        "wells_no_depth": counts["no_depth_sdr"] + counts["no_depth_gwdb"],
        "wells_hickory": sum(bool(w["hickory"]) for w in wells),
        "wells_overview": len(overview),
        "wells_plugging_reports": counts["sdr_plugging_reports"],
        "wells_tiles": len(index_tiles),
        "wells_detail_files": len(details),
        "wells_water_from_strata": sum(w["water"][3] == 0 for w in wells),
        "wells_water_from_deepest": sum(w["water"][3] == 1 for w in wells),
        "wells_unlogged": sum(w["water"][3] == 2 for w in wells),
    }
    for i in range(len(params.USE_GROUPS)):
        figs[f"wells_use_{i}"] = sum(w["use"] == i for w in wells)
    figs.update({f"blanked_{k}": v for k, v in sorted(scrub.blanked.items())})
    figs.update({f"redacted_{k}": v for k, v in sorted(scrub.redacted.items())})
    index = {
        "source": (
            "TWDB Submitted Driller's Reports and Groundwater Database, the "
            "reports inside the domain of TWDB's Llano Uplift groundwater "
            "model"
        ),
        "classes": list(params.CLASSES),
        "tile_degrees": params.TILE_DEG,
        "detail_degrees": params.DETAIL_DEG,
        "overview_cell_degrees": params.OVERVIEW_DEG,
        "fields": [
            "uid",
            "lon",
            "lat",
            "depth_ft",
            "log [[top, bottom, class]]",
            "water_level_ft",
            "water_strata [[top, bottom]]",
            "hickory (GWDB)",
            "detail_cell",
            "use_group",
            "water_class",
            "water_top_ft",
            "water_bottom_ft",
            "water_basis",
            "yield_gpm",
            "yield_test",
        ],
        "tiles": index_tiles,
        "overview": overview,
        "use_groups": list(params.USE_GROUPS),
        "use_map": {
            **{k: params.USE_GROUPS[v] for k, v in params.USE_MAP.items()},
            "(anything else)": params.USE_GROUPS[params.OTHER_USE],
        },
        # Every well drawn, as [use group, Hickory (GWDB), highest tested
        # yield or null, depth or null], for the page's filter counts.
        "filter_keys": [
            [
                w["use"],
                1 if w["hickory"] else 0,
                None if w["yield"] is None else round(w["yield"][0], 1),
                r1(w["depth"]) if w["depth"] else None,
            ]
            for w in wells
        ],
        "fields_removed": {
            "sdr_well_report": sorted(privacy.REMOVED_SDR),
            "sdr_plugging_report": sorted(privacy.REMOVED_PLUG),
            "gwdb": sorted(privacy.REMOVED_GWDB),
        },
    }
    # Every well's head, in a few files, for the page's every-well layer: a
    # quarter of the drawing tiles' bytes.
    heads = [head_record(w) for w in wells]
    size = params.HEADS_PER_FILE
    files = []
    for n, at in enumerate(range(0, len(heads), size)):
        files.append(f"heads-{n}.json")
        record.write_json(
            os.path.join(wells_dir, files[-1]), heads[at : at + size]
        )
    index["heads"] = {"files": files, "fields": list(HEAD_FIELDS)}
    figs["wells_heads_files"] = len(files)
    record.write_json(os.path.join(wells_dir, "index.json"), index)
    for w in wells:
        del w["rec"]
    return figs, wells, names, scrub
