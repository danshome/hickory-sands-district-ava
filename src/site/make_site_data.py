"""make_site_data.py: the website's map data, from the boundary build.

Writes the files the website's maps will read (docs/data/; the maps are #112
and #113): the boundary, its steps and its points as GeoJSON, with only what
a reader needs, and the AVA's status as the boundary's own record gives it
(Status, Established, CFR_Section: "Proposed" until TTB's final rule). The
coordinates are the build's NAD83 values rounded to 6 decimal places and used
as WGS 84 for display; the two differ by about a metre here. The record is the
boundary package for TTB, not these files. Standard library only, so the lint
workflow can test it.

Usage (the project .venv, -E -s):
  make_site_data.py --gis DIR --out DIR [--check]
--gis is the build's GIS folder (target/work/gis). With --check nothing is
written. It exits 3 when --out is stale: when it differs from the build in
what every platform's build gives alike (the points, each step's number,
kind, endpoint, quad and text, the boundary's name, counties and area, and
the status), or in a line by more than MAX_DRIFT_M. Two machines (even two of
GitHub's Linux runners) can place a traced line's vertices differently along
the same ink (#116), so lines that close are reported in metres, not failed.
Other errors exit 1.
"""

import argparse
import glob
import itertools
import json
import math
import os
import sys

DECIMALS = 6
STALE = 3  # --check's exit status when docs/data/ is stale
STATUSES = ("proposed", "established")
STEP_KEYS = ("step", "kind", "endpoint", "quad", "length_m", "narrative")
POINT_KEYS = ("point", "step", "kind", "point_name", "quad")
# What may differ between platforms' builds (#116): every feature's geometry,
# and these properties.
DRIFTS = {"boundary.geojson": (), "steps.geojson": ("length_m",)}
# How far apart a feature's lines may be in two builds before the check calls
# the site stale: in #116 a vertex slid 53 m along a straight road and the
# lines stayed 0.34 m apart; a rerouted step moves much further.
MAX_DRIFT_M = 5.0
M_PER_DEGREE = 111320.0  # metres per degree of latitude, near enough here
CELL_M = 200.0  # the grid that finds a position's nearby segments
NOTE = (
    "Display copy of the Hickory Sands District boundary for the website "
    "(NAD83 coordinates, rounded to 6 decimal places, shown as WGS 84). The "
    "record is the boundary package for TTB."
)


def rounded(coords):
    """Returns coordinates rounded for display, without any z values.

    Args:
        coords: A GeoJSON coordinate array of any depth.

    Returns:
        The same structure, each position [x, y] rounded to DECIMALS places.
    """
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], DECIMALS), round(coords[1], DECIMALS)]
    return [rounded(c) for c in coords]


def feature(source, properties):
    """Returns a GeoJSON feature with the given properties and rounded shape.

    Args:
        source: A feature from the build's GIS files.
        properties: The properties to keep, already cleaned.

    Returns:
        A new feature.
    """
    geometry = source["geometry"]
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": geometry["type"],
            "coordinates": rounded(geometry["coordinates"]),
        },
    }


def collection(name, features):
    """Returns a GeoJSON feature collection with the display note.

    Args:
        name: The collection's name.
        features: Its features.

    Returns:
        The collection.
    """
    return {
        "type": "FeatureCollection",
        "name": name,
        "description": NOTE,
        "features": features,
    }


def one(gis_dir, suffix):
    """Returns the one GeoJSON file in gis_dir whose name ends in suffix.

    Args:
        gis_dir: The build's GIS folder.
        suffix: The end of the file name, such as "-line-EPSG4269.geojson".

    Returns:
        The file's parsed contents.

    Raises:
        SystemExit: When there is not exactly one such file.
    """
    found = glob.glob(os.path.join(gis_dir, "*" + suffix))
    if len(found) != 1:
        sys.exit(f"expected one *{suffix} in {gis_dir}, found {len(found)}")
    with open(found[0], encoding="utf-8") as fh:
        return json.load(fh)


def record_status(record):
    """Returns the AVA's status as the website shows it, from its record.

    Args:
        record: The boundary's properties: Name, Status ("Proposed" or
            "Established"), Established (the date) and CFR_Section.

    Returns:
        A dict: name, status ("proposed" or "established"), established_on
        and cfr_section (both None while proposed).

    Raises:
        SystemExit: When the record's status is not one the site can show, or
            an established AVA lacks its date or its CFR section.
    """
    status = str(record.get("Status") or "").lower()
    if status not in STATUSES:
        sys.exit(f"Status must be one of {STATUSES}: {record.get('Status')!r}")
    if status == "proposed":
        return {
            "name": record["Name"],
            "status": status,
            "established_on": None,
            "cfr_section": None,
        }
    cfr = record.get("CFR_Section") or ""
    if not record.get("Established") or not cfr or "X" in cfr:
        sys.exit(
            "an established AVA needs its Established date and CFR_Section"
        )
    return {
        "name": record["Name"],
        "status": status,
        "established_on": record["Established"],
        "cfr_section": cfr,
    }


def kept(source, keys, label):
    """Returns the properties to keep, refusing any that are missing or empty.

    Args:
        source: A feature from the build's GIS files.
        keys: The property names to keep, in order.
        label: How to name the feature in an error, such as "step 6".

    Returns:
        A dict of the kept properties, in the order of keys.

    Raises:
        SystemExit: When a property is missing or empty.
    """
    p = source["properties"]
    for k in keys:
        if p.get(k) in (None, ""):
            sys.exit(f"{label}: {k} is missing or empty")
    return {k: p[k] for k in keys}


def numbered(features, key, first=None):
    """Returns features sorted by number, refusing gaps and repeats.

    Args:
        features: The step lines or the points.
        key: The property holding the number: "step" or "point".
        first: A name that comes before 1 ("Beginning"), or None.

    Returns:
        The features in order: first (if any), then 1, 2, 3 and so on.

    Raises:
        SystemExit: When the numbers are not first (if any) then 1 to N,
            each once.
    """
    ids = [str(f["properties"][key]) for f in features]
    named = [first] if first else []
    count = len(features) - len(named)
    want = [*named, *(str(n) for n in range(1, count + 1))]
    if sorted(ids) != sorted(want):
        sys.exit(f"the {key}s are not {want[0]}..{want[-1]}, each once")
    return sorted(features, key=lambda f: want.index(str(f["properties"][key])))


def site_data(gis_dir):
    """Returns the website's data files, by name, as the text to write.

    Args:
        gis_dir: The build's GIS folder.

    Returns:
        A dict from file name to file text.

    Raises:
        SystemExit: When the build's files are not what the site needs: not
            one area, steps or points out of order, an empty property, or a
            status the site cannot show.
    """
    area = one(gis_dir, "-area-EPSG4269.geojson")["features"]
    lines = one(gis_dir, "-line-EPSG4269.geojson")["features"]
    points = one(gis_dir, "-points-EPSG4269.geojson")["features"]
    if len(area) != 1:
        sys.exit(f"expected one boundary polygon, found {len(area)}")
    if len(points) != len(lines) + 1:
        sys.exit(f"{len(lines)} steps need {len(lines) + 1} points")

    first = kept(area[0], ("Name", "area_sqmi", "Counties"), "boundary")
    status = record_status(area[0]["properties"])
    boundary = [
        feature(
            area[0],
            {
                "name": first["Name"],
                "area_sqmi": float(first["area_sqmi"]),
                "counties": first["Counties"],
            },
        )
    ]
    steps = []
    for f in numbered(lines, "step"):
        p = kept(f, STEP_KEYS, f"step {f['properties']['step']}")
        p["step"] = int(p["step"])
        p["length_m"] = round(float(p["length_m"]), 1)
        steps.append(feature(f, p))
    marks = []
    for f in numbered(points, "point", first="Beginning"):
        p = kept(f, POINT_KEYS, f"point {f['properties']['point']}")
        p["point"] = str(p["point"])
        p["step"] = int(p["step"])
        marks.append(feature(f, p))

    def text(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"

    return {
        "boundary.geojson": text(collection("boundary", boundary)),
        "steps.geojson": text(collection("steps", steps)),
        "points.geojson": text(collection("points", marks)),
        "status.json": json.dumps(status, ensure_ascii=False, indent=2) + "\n",
    }


def parts(coords):
    """Returns the lines in a GeoJSON coordinate array.

    Args:
        coords: A LineString's or a ring's positions, or a Polygon's or a
            Multi- geometry's coordinates.

    Returns:
        A list of lines (rings count as lines), each a list of positions.
    """
    if isinstance(coords[0][0], (int, float)):
        return [coords]
    return [line for c in coords for line in parts(c)]


def in_metres(coords, lat):
    """Returns the lines in coords as (east, north) metres, flattened at lat.

    Args:
        coords: A GeoJSON coordinate array of a line or a polygon.
        lat: The latitude whose scale is used (an equirectangular
            approximation, right to a few centimetres over a few km here).

    Returns:
        A list of lines, each a list of (x, y) tuples in metres.
    """
    kx = math.cos(math.radians(lat)) * M_PER_DEGREE
    return [
        [(p[0] * kx, p[1] * M_PER_DEGREE) for p in line]
        for line in parts(coords)
    ]


def to_segment(p, a, b):
    """Returns the distance from position p to the segment from a to b.

    Args:
        p: An (x, y) position in metres.
        a: The segment's start.
        b: Its end.

    Returns:
        The distance, in metres.
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = 0.0
    if length2:
        t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2
        t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def farthest(points, lines, limit):
    """Returns how far the farthest of points lies from lines, up to limit.

    Args:
        points: (x, y) positions in metres.
        lines: Lines of (x, y) positions in metres.
        limit: The distance beyond which the answer is only "too far".

    Returns:
        The largest distance from a point to its nearest segment, in metres,
        or None when a point is more than limit from every segment.
    """
    grid = {}
    for line in lines:
        for a, b in itertools.pairwise(line):
            cells = [
                range(
                    math.floor((min(a[i], b[i]) - limit) / CELL_M),
                    math.floor((max(a[i], b[i]) + limit) / CELL_M) + 1,
                )
                for i in (0, 1)
            ]
            for cx in cells[0]:
                for cy in cells[1]:
                    grid.setdefault((cx, cy), []).append((a, b))
    vertices = {p for line in lines for p in line}
    worst = 0.0
    for p in points:
        if p in vertices:
            continue
        cell = (math.floor(p[0] / CELL_M), math.floor(p[1] / CELL_M))
        near = grid.get(cell, ())
        d = min((to_segment(p, a, b) for a, b in near), default=math.inf)
        if d > limit:
            return None
        worst = max(worst, d)
    return worst


def apart_m(a, b, limit):
    """Returns how far apart two shapes' lines are at most, up to limit.

    The distance is the largest from a vertex of either shape to the other
    shape's lines (the Hausdorff distance between them), so a vertex that
    only slides along a line does not count, and the shapes may have
    different numbers of vertices.

    Args:
        a: A GeoJSON coordinate array of a line or a polygon.
        b: Another.
        limit: The distance beyond which the answer is only "too far".

    Returns:
        The distance in metres, or None when it is more than limit.
    """
    lat = parts(a)[0][0][1]
    la, lb = in_metres(a, lat), in_metres(b, lat)
    one = farthest([p for line in la for p in line], lb, limit)
    other = farthest([p for line in lb for p in line], la, limit)
    return None if one is None or other is None else max(one, other)


def firm(name, text):
    """Returns what of a file every platform's build gives alike.

    Args:
        name: The file's name.
        text: The file's text.

    Returns:
        The text itself, or for a file listed in DRIFTS, its features with
        only the type of their geometry and without the drifting properties,
        as canonical JSON; None when the text does not parse.
    """
    if name not in DRIFTS:
        return text
    try:
        data = json.loads(text)
        for f in data["features"]:
            f["geometry"] = f["geometry"]["type"]
            for k in DRIFTS[name]:
                f["properties"].pop(k, None)
    except ValueError, KeyError, TypeError, AttributeError:
        return None
    return json.dumps(data, sort_keys=True)


def drift(have, want):
    """Returns how far a file's shapes are from the build's.

    Args:
        have: The committed text of a file listed in DRIFTS.
        want: The text the build gives, whose features firm() found to match
            have's one for one.

    Returns:
        How far apart the two versions of any feature are at most, in metres,
        or None when that is more than MAX_DRIFT_M.
    """
    a, b = json.loads(have)["features"], json.loads(want)["features"]
    worst = 0.0
    for f, g in zip(a, b, strict=True):
        d = apart_m(
            f["geometry"]["coordinates"],
            g["geometry"]["coordinates"],
            MAX_DRIFT_M,
        )
        if d is None:
            return None
        worst = max(worst, d)
    return worst


def compare(files, out_dir):
    """Returns how the files in out_dir differ from files.

    Args:
        files: A dict from file name to the text it should hold.
        out_dir: The folder holding the committed copies.

    Returns:
        Four lists: the names missing from out_dir; those that differ from
        the build (in what every platform's build gives alike, or in a line
        by more than MAX_DRIFT_M); those in out_dir but not made by the
        build; and notes on lines that drift within MAX_DRIFT_M (#116).
    """
    have = set(os.listdir(out_dir)) if os.path.isdir(out_dir) else set()
    missing = sorted(set(files) - have)
    unexpected = sorted(have - set(files))
    differs, notes = [], []
    for name in sorted(set(files) & have):
        with open(os.path.join(out_dir, name), encoding="utf-8") as fh:
            text = fh.read()
        if firm(name, text) != firm(name, files[name]):
            differs.append(name)
        elif name in DRIFTS and text != files[name]:
            apart = drift(text, files[name])
            if apart is None:
                differs.append(name)
            else:
                notes.append(f"{name}: lines up to {apart:.2f} m apart")
    return missing, differs, unexpected, notes


def write(files, out_dir):
    """Writes files to out_dir, each in one step, and removes any other file.

    Args:
        files: A dict from file name to the text it should hold.
        out_dir: The site's data folder, which only this script writes.
    """
    os.makedirs(out_dir, exist_ok=True)
    for name, text in files.items():
        path = os.path.join(out_dir, name)
        with open(path + ".tmp", "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(path + ".tmp", path)
    for name in compare(files, out_dir)[2]:
        os.remove(os.path.join(out_dir, name))


def main():
    """Writes or checks the website's map data."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gis", required=True, help="the build's GIS folder")
    ap.add_argument("--out", required=True, help="the site's data folder")
    ap.add_argument("--check", action="store_true", help="compare only")
    args = ap.parse_args()
    files = site_data(args.gis)
    if args.check:
        missing, differs, unexpected, notes = compare(files, args.out)
        for note in notes:
            print(f"note: {note} (#116; not a failure)")
        if missing or differs or unexpected:
            for what, names in (
                ("missing", missing),
                ("differs from the build", differs),
                ("not made by the build", unexpected),
            ):
                if names:
                    print(f"{args.out}: {what}: {', '.join(names)}")
            print("run ./build.sh site-data and commit docs/data/")
            sys.exit(STALE)
        print(f"{args.out} matches the build ({len(files)} files)")
        return
    write(files, args.out)
    print(f"wrote {len(files)} files to {args.out}")


if __name__ == "__main__":
    main()
