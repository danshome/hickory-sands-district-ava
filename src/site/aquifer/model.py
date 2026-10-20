"""The aquifer, its drill grid and the context layers of the 3D page.

From TWDB's Llano Uplift groundwater model (GAM v1.01, layer 7 the Hickory
Aquifer, layer 8 the Precambrian) and TWDB's 2017 official Hickory outline,
shifted onto the geology, write() writes into the page's data folder:

    hickory-k2.json, hickory-k4.json
        The aquifer as blocks of 2 x 2 and 4 x 4 model cells (half a mile
        and a mile square). A block is drawn where at least half its cells
        have layer 7 active; it belongs to the official outline or to "model
        only", whichever holds more of its cells (ties go to the outline),
        and sits at the mean top and bottom of that side's cells. Each block
        is [row, col, top_m, bottom_m, mostly model outcrop, outside the
        outline, the model's ground (m)]; the page makes the corners from a
        polynomial (grid.corner_polynomial()).
    drill-grid.bin, drill-grid.json
        For "My location": per model cell, the model's ground, layer 7's
        top and bottom (int16 feet, -32768 where none) and flags (uint8: 1
        layer 7 active; 2 inside the official outline; 4 layer 7 at the
        surface; 8 Precambrian at the surface; 16 inside the model), and the
        lookup polynomial from longitude and latitude to the cell.
    precambrian.geojson, precambrian-buried.geojson
        Precambrian rock at the surface (layer 8 outcrop), and under younger
        rock where the model has no Hickory.
    context.geojson
        TWDB's 2017 Hickory outcrop (shifted), the towns (Census 2023
        Gazetteer internal points) and the county lines in the model's area
        (Census 2023, 1:500,000).
    llano-uplift.geojson
        TTB's proposed Llano Uplift AVA (AVAs_Production snapshot).
    hickory-member.geojson
        The Hickory Sandstone Member of the Riley Formation (the shifted
        USGS geology).

It returns the figures the page shows and the drill grid's lookup, which
the wells use to keep the reports inside the model.
"""

import csv
import json
import math
import os
import shutil
import subprocess
import warnings

import numpy as np
from osgeo import ogr
from osgeo import osr

from . import grid as gridlib
from . import params
from . import record

ogr.UseExceptions()
osr.UseExceptions()

NULL = -32768  # the drill grid's "no value"
SQMI_FT2 = 5280.0**2
GEOLOGY_LAYER = "Hickory_Sandstone_Member_formation"


def extract_gam(archive, cache):
    """The GAM Properties GeoPackage, extracted from the model's archive.

    Args:
        archive: lnup_v101.7z in the cache.
        cache: The cache folder; the GeoPackage is extracted under it once.

    Returns:
        The GeoPackage's path.

    Raises:
        SystemExit: bsdtar (libarchive), which reads 7z, is missing.
    """
    path = os.path.join(cache, params.GAM_MEMBER)
    if os.path.isfile(path):
        return path
    tool = shutil.which("bsdtar")
    if not tool:
        raise SystemExit(
            "bsdtar is needed to read the model's 7z archive: it comes with "
            "macOS; on Linux, brew install libarchive"
        )
    work = os.path.join(cache, "extract.part")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    print(f"extracting {params.GAM_MEMBER}")
    command = [tool, "-xf", archive, "-C", work, params.GAM_MEMBER]
    subprocess.run(command, check=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    os.replace(os.path.join(work, params.GAM_MEMBER), path)
    shutil.rmtree(work)
    return path


def geojson(geom):
    """A geometry as GeoJSON, longitude and latitude to params.DECIMALS."""
    return json.loads(
        geom.ExportToJson(options=[f"COORDINATE_PRECISION={params.DECIMALS}"])
    )


def collection(features):
    """A GeoJSON FeatureCollection."""
    return {"type": "FeatureCollection", "features": features}


def feature(props, geometry):
    """A GeoJSON Feature."""
    return {"type": "Feature", "properties": props, "geometry": geometry}


def wall_count(keep, top, bot):
    """The number of wall quads the page builds (the same rule as its code).

    Args:
        keep: The blocks drawn, a boolean array.
        top: Their tops.
        bot: Their bottoms.

    Returns:
        Walls where a neighbour is missing, or steps down from the top or up
        from the bottom.
    """
    n = 0
    padded = np.pad(keep, 1)
    t = np.pad(np.where(keep, top, np.nan), 1, constant_values=np.nan)
    b = np.pad(np.where(keep, bot, np.nan), 1, constant_values=np.nan)
    core = (slice(1, -1), slice(1, -1))
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        sl = (
            slice(1 + dr, padded.shape[0] - 1 + dr),
            slice(1 + dc, padded.shape[1] - 1 + dc),
        )
        other = padded[sl]
        n += int((keep & ~other).sum())
        both = keep & other
        with np.errstate(invalid="ignore"):
            n += int((both & (t[core] > t[sl])).sum())
            n += int((both & (b[core] < b[sl])).sum())
    return n


def blocks(grid, keep, outside, k):
    """Groups the cells into k x k blocks.

    Args:
        grid: The ModelGrid.
        keep: Cells with layer 7 active inside the official outline.
        outside: Cells with layer 7 active outside it.
        k: The block's size in cells.

    Returns:
        Arrays over the blocks: drawn, top, bottom, mostly outcrop, outside
        the outline, and the model's ground (all in feet).
    """
    nr = math.ceil(params.ROWS / k)
    nc = math.ceil(params.COLS / k)
    pad_r, pad_c = nr * k - params.ROWS, nc * k - params.COLS

    def shaped(a, fill):
        a = np.pad(a, ((0, pad_r), (0, pad_c)), constant_values=fill)
        return a.reshape(nr, k, nc, k).swapaxes(1, 2).reshape(nr, nc, k * k)

    n_in = shaped(keep, False).sum(axis=2)
    n_out = shaped(outside, False).sum(axis=2)
    drawn = (n_in + n_out) >= math.ceil(k * k / 2)
    side = n_out > n_in
    use = np.where(
        side[:, :, None], shaped(outside, False), shaped(keep, False)
    )
    outcrop = use & shaped(grid.ib7 == params.IBOUND_OUTCROP, False)
    count = use.sum(axis=2)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # empty blocks
        top = np.nanmean(np.where(use, shaped(grid.top7, np.nan), np.nan), 2)
        bot = np.nanmean(np.where(use, shaped(grid.bot7, np.nan), np.nan), 2)
        ground = np.nanmean(
            np.where(use, shaped(grid.ground, np.nan), np.nan), 2
        )
    mostly_outcrop = outcrop.sum(axis=2) * 2 >= np.maximum(count, 1)
    return drawn, top, bot, mostly_outcrop, drawn & side, ground


def write_blocks(grid, keep, outside, out_dir):
    """Writes hickory-k2.json and hickory-k4.json.

    Args:
        grid: The ModelGrid.
        keep: Cells with layer 7 active inside the official outline.
        outside: Cells with layer 7 active outside it.
        out_dir: The page's data folder.

    Returns:
        The figures, by name: each size's block count and vertices.
    """
    ft = params.M_PER_US_FT
    corners = gridlib.corner_polynomial(grid)
    figs = {}
    for k in params.FACTORS:
        drawn, top, bot, outcrop, side, ground = blocks(grid, keep, outside, k)
        rows = [
            [
                int(r),
                int(c),
                round(float(top[r, c]) * ft, 1),
                round(float(bot[r, c]) * ft, 1),
                int(outcrop[r, c]),
                int(side[r, c]),
                round(float(ground[r, c]) * ft, 1),
            ]
            for r, c in zip(*np.nonzero(drawn), strict=True)
        ]
        walls = wall_count(drawn, top, bot)
        data = {
            "source": (
                "TWDB Llano Uplift GAM v1.01, model layer 7 (the Hickory "
                f"Aquifer), in blocks of {k} x {k} model cells"
            ),
            "block_cells": k,
            "units": "metres above sea level (from US survey feet)",
            "corners": (
                "block (row, col)'s corners are the model grid positions "
                "(row * block_cells - 0.5, col * block_cells - 0.5) to "
                "((row + 1) * block_cells - 0.5, (col + 1) * block_cells - "
                "0.5), placed by the polynomial"
            ),
            "polynomial": corners,
            "fields": [
                "row",
                "col",
                "top_m",
                "bottom_m",
                "mostly_model_outcrop",
                "outside_official",
                "ground_m",
            ],
            "cells": rows,
        }
        record.write_json(os.path.join(out_dir, f"hickory-k{k}.json"), data)
        figs[f"k{k}_blocks"] = len(rows)
        figs[f"k{k}_blocks_outside_official"] = int(side.sum())
        figs[f"k{k}_vertices"] = 8 * len(rows) + 4 * walls
    return figs


def step_figures(grid, keep, faults_path):
    """How the aquifer's top steps across the model's faults.

    Args:
        grid: The ModelGrid.
        keep: Cells with layer 7 active inside the official outline.
        faults_path: TWDB's fault lines, NAD83 GeoJSON
            (resources/aquifer/twdb-gam-faults-EPSG4269.geojson).

    Returns:
        The figures: the cells beside a step of more than params.STEP_FT,
        the share of them within params.FAULT_NEAR_CELLS cells of a fault
        line, the neighbouring pairs across such a step, and the share of
        those whose two sides no longer overlap.
    """
    top = grid.top7
    step = np.zeros_like(top)
    for axis in (0, 1):
        d = np.nan_to_num(np.abs(np.diff(top, axis=axis)))
        lo = [slice(None)] * 2
        hi = [slice(None)] * 2
        lo[axis] = slice(None, -1)
        hi[axis] = slice(1, None)
        step[tuple(lo)] = np.fmax(step[tuple(lo)], d)
        step[tuple(hi)] = np.fmax(step[tuple(hi)], d)
    big = (step > params.STEP_FT) & keep
    lines = ogr.Geometry(ogr.wkbMultiLineString)
    ds = ogr.Open(faults_path)
    to_gam = osr.CoordinateTransformation(gridlib.nad83(), grid.srs)
    for f in ds.GetLayer(0):
        g = f.GetGeometryRef().Clone()
        g.Transform(to_gam)
        for part in ogr.ForceToMultiLineString(g):
            lines.AddGeometry(part)
    near = grid.mask_of(lines.Buffer(params.FAULT_NEAR_CELLS * params.CELL_FT))
    n_big = n_gap = 0
    for axis in (0, 1):
        if axis == 0:
            a, b = (slice(None, -1), slice(None)), (slice(1, None), slice(None))
        else:
            a, b = (slice(None), slice(None, -1)), (slice(None), slice(1, None))
        t1, t2 = grid.top7[a], grid.top7[b]
        b1, b2 = grid.bot7[a], grid.bot7[b]
        with np.errstate(invalid="ignore"):
            pair = keep[a] & keep[b] & (np.abs(t1 - t2) > params.STEP_FT)
            n_big += int(pair.sum())
            n_gap += int((pair & ((b1 > t2) | (b2 > t1))).sum())
    return {
        "step_cells": int(big.sum()),
        "step_cells_near_fault_share": float((big & near).sum() / big.sum()),
        "step_pairs": n_big,
        "step_pairs_apart_share": n_gap / n_big,
    }


def write_drill_grid(grid, inside, out_dir):
    """Writes drill-grid.bin and drill-grid.json for "My location".

    Args:
        grid: The ModelGrid.
        inside: Cells whose centre lies inside the official outline.
        out_dir: The page's data folder.

    Returns:
        The lookup: its polynomial and the flags, for the wells.
    """

    def as_int(a):
        return np.where(np.isnan(a), NULL, np.round(a)).astype("<i2")

    flags = (
        (grid.ib7 > 0) * 1
        + inside * 2
        + (grid.ib7 == params.IBOUND_OUTCROP) * 4
        + (grid.ib8 == params.IBOUND_PRECAMBRIAN_OUTCROP) * 8
        + (~np.isnan(grid.ground)) * 16
    ).astype(np.uint8)
    blob = (
        as_int(grid.ground).tobytes()
        + as_int(grid.top7).tobytes()
        + as_int(grid.bot7).tobytes()
        + flags.tobytes()
    )
    record.write_bytes(os.path.join(out_dir, "drill-grid.bin"), blob)
    poly = gridlib.lookup_polynomial(grid)
    meta = {
        "source": (
            "TWDB Llano Uplift GAM v1.01 (the top of every layer, layer 7's "
            "top and bottom, ibound); TWDB 2017 Minor Aquifers (the Hickory "
            "outline, shifted)"
        ),
        "rows": params.ROWS,
        "cols": params.COLS,
        "null": NULL,
        "units": "US survey feet above sea level",
        "layout": [
            "ground_ft int16",
            "top7_ft int16",
            "bot7_ft int16",
            "flags uint8",
        ],
        "order": "four arrays, each row-major from row 1, little-endian",
        "flags": {
            "layer7": 1,
            "inside_official": 2,
            "outcrop71": 4,
            "precambrian81": 8,
            "in_model": 16,
        },
        "lonlat_to_rowcol": poly,
    }
    record.write_json(os.path.join(out_dir, "drill-grid.json"), meta, indent=1)
    return {"polynomial": poly, "flags": flags}


def towns(gazetteer):
    """The towns, from the Census Gazetteer's Texas places.

    Args:
        gazetteer: 2023_gaz_place_48.txt.

    Returns:
        GeoJSON point features, in params.TOWNS's order.

    Raises:
        SystemExit: A town is not found.
    """
    with open(gazetteer, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh, delimiter="\t"))
    head = [h.strip() for h in rows[0]]
    found = {}
    for row in rows[1:]:
        rec = dict(zip(head, (v.strip() for v in row), strict=True))
        for town in params.TOWNS:
            if rec["NAME"] in (f"{town} city", f"{town} town"):
                found[town] = rec
    missing = set(params.TOWNS) - set(found)
    if missing:
        raise SystemExit(f"towns not in the Gazetteer: {sorted(missing)}")
    return [
        feature(
            {"kind": "town", "name": town, "geoid": found[town]["GEOID"]},
            {
                "type": "Point",
                "coordinates": [
                    float(found[town]["INTPTLONG"]),
                    float(found[town]["INTPTLAT"]),
                ],
            },
        )
        for town in params.TOWNS
    ]


def write(paths, out_dir):
    """Writes the aquifer, the drill grid and the context layers.

    Args:
        paths: The inputs, by name: the downloads (inputs.ensure()) and
            record.LOCAL's committed files, as paths.
        out_dir: The page's new data folder.

    Returns:
        (figures, lookup): the figures the page shows, by name, and the drill
        grid's lookup (write_drill_grid()).
    """
    gpkg = extract_gam(paths["twdb-gam"], os.path.dirname(paths["twdb-gam"]))
    grid = gridlib.ModelGrid(gpkg)
    gam = grid.srs
    ll = gridlib.nad83()
    to_ll = osr.CoordinateTransformation(gam, ll)
    print(f"model grid fitted, residual {grid.fit_residual_ft:.4f} ft")
    zip_path = paths["twdb-minor-aquifers"]
    official = gridlib.hickory(zip_path, "all", gam)
    inside = grid.mask_of(official)
    active7 = grid.ib7 > 0
    keep = active7 & inside
    outside7 = active7 & ~inside
    buried_pre = (grid.ib7 == 0) & (
        grid.ib8 == params.IBOUND_PRECAMBRIAN_BURIED
    )
    pre_cells = grid.ib8 == params.IBOUND_PRECAMBRIAN_OUTCROP
    cell_sqmi = params.CELL_FT**2 / SQMI_FT2
    pre = grid.polygons_of(pre_cells)
    near_core = grid.mask_of(pre.Buffer(params.CORE_MILES * 5280.0))
    figs = {
        "model_cells": params.ROWS * params.COLS,
        "layer7_cells": int(active7.sum()),
        "official_sqmi": official.GetArea() / SQMI_FT2,
        "official_layer7_sqmi": float(keep.sum()) * cell_sqmi,
        "official_no_layer7_sqmi": float((inside & ~active7).sum()) * cell_sqmi,
        "layer7_sqmi": float(active7.sum()) * cell_sqmi,
        # TWDB's model has no active cell thinner than this.
        "layer7_min_thickness_ft": float(
            np.nanmin((grid.top7 - grid.bot7)[active7])
        ),
        "outside_official_sqmi": float(outside7.sum()) * cell_sqmi,
        "outside_official_near_core_sqmi": (
            float((outside7 & near_core).sum()) * cell_sqmi
        ),
        "precambrian_outcrop_sqmi": pre.GetArea() / SQMI_FT2,
        "precambrian_buried_sqmi": float(buried_pre.sum()) * cell_sqmi,
    }
    figs.update(write_blocks(grid, keep, outside7, out_dir))
    figs.update(step_figures(grid, keep, paths["twdb-gam-faults"]))
    lookup = write_drill_grid(grid, inside, out_dir)

    for name, mask, label in (
        (
            "precambrian.geojson",
            pre_cells,
            "Precambrian rock at the surface (TWDB model layer 8 outcrop)",
        ),
        (
            "precambrian-buried.geojson",
            buried_pre,
            "Precambrian rock under younger rock; no Hickory in the model",
        ),
    ):
        polys = grid.polygons_of(mask)
        polys.Transform(to_ll)
        record.write_json(
            os.path.join(out_dir, name),
            collection([feature({"name": label}, geojson(polys))]),
        )

    # The model's area in longitude and latitude, for the county lines.
    corners = [
        grid.xy(r, c)
        for r, c in (
            (-0.5, -0.5),
            (-0.5, params.COLS - 0.5),
            (params.ROWS - 0.5, params.COLS - 0.5),
            (params.ROWS - 0.5, -0.5),
        )
    ]
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in [*corners, corners[0]]:
        ring.AddPoint_2D(float(x), float(y))
    area = ogr.Geometry(ogr.wkbPolygon)
    area.AddGeometry(ring)
    area.AssignSpatialReference(gam)
    area.Transform(to_ll)
    outcrop = gridlib.hickory(zip_path, "outcrop")
    outcrop = outcrop.SimplifyPreserveTopology(0.0001)
    feats = [
        feature(
            {"kind": "outcrop", "name": "TWDB 2017 Hickory outcrop (shifted)"},
            geojson(outcrop),
        )
    ]
    feats += towns(paths["census-places"])
    counties = ogr.Open(f"/vsizip/{paths['census-counties']}")
    layer = counties.GetLayer(0)
    layer.SetAttributeFilter("STATEFP = '48'")
    layer.SetSpatialFilter(area)
    names = []
    for f in sorted(layer, key=lambda f: f.GetField("NAMELSAD")):
        line = f.GetGeometryRef().Boundary().Intersection(area)
        if line is None or line.IsEmpty():
            continue
        names.append(f.GetField("NAMELSAD"))
        feats.append(
            feature(
                {"kind": "county", "name": f.GetField("NAMELSAD")},
                geojson(line),
            )
        )
    record.write_json(
        os.path.join(out_dir, "context.geojson"), collection(feats)
    )
    figs["counties"] = len(names)
    figs["towns"] = len(params.TOWNS)

    with open(paths["ttb-llano-uplift"], encoding="utf-8") as fh:
        llano = json.load(fh)
    for f in llano["features"]:
        p = f["properties"]
        if p.get("Name") != "Llano Uplift" or p.get("Status") != "Proposed":
            raise SystemExit("not TTB's proposed Llano Uplift AVA")
        f["properties"] = {
            k: p[k] for k in ("Name", "Status", "Counties") if k in p
        }
    llano.pop("crs", None)
    record.write_json(os.path.join(out_dir, "llano-uplift.geojson"), llano)

    geology = ogr.Open(paths["usgs-sgmc-shifted"])
    member = [
        feature(
            {"name": "Hickory Sandstone Member"},
            geojson(f.GetGeometryRef()),
        )
        for f in geology.GetLayerByName(GEOLOGY_LAYER)
    ]
    record.write_json(
        os.path.join(out_dir, "hickory-member.geojson"), collection(member)
    )
    figs["member_polygons"] = len(member)
    west, north = gridlib.shift_metres()
    figs["shift_west_m"] = west
    figs["shift_north_m"] = north
    return figs, lookup
