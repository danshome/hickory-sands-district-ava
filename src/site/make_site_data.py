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
  make_site_data.py --gis DIR --out DIR [--walk TEMPLATE PAGE] [--pages DIR]
                    [--check]
--gis is the build's GIS folder (target/work/gis). With --check nothing is
written. It exits 3 when --out is stale: when it differs from the build in
what every platform's build gives alike (the points, each step's number,
kind, endpoint, quad and text, the boundary's name, counties and area, and
the status), or in a line by more than MAX_DRIFT_M. Two machines (even two of
GitHub's Linux runners) can place a traced line's vertices differently along
the same ink (#116), so lines that close are reported in metres, not failed.
Other errors exit 1. With --walk it also makes (or checks) the walk page,
the story map's text, from its template; with --pages it writes (or checks)
every figure marked data-figure in the site's pages, so no page types the
area, the counts, the length or the revision date.
"""

import argparse
import datetime
import decimal
import glob
import html
import itertools
import json
import math
import os
import re
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # src/
import revision

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
SAMPLE_M = 1.0  # how often along a changed segment the distance is measured
M_PER_MILE = 1609.344
# The walk page's template holds this once, for the list of steps
# (src/site/walk.template.html); its figures are data-figure elements.
WALK_TOKENS = ("@STEPS@",)
# A figure in a page: an element marked data-figure="name" holding only text,
# such as <span data-figure="area_sqmi">193.83</span>; the build writes it.
FIGURE = re.compile(
    r'<(?P<tag>[a-z][a-z0-9]*)(?P<attrs>[^>]*\sdata-figure="(?P<name>[a-z_]+)"'
    r"[^>]*)>(?P<text>[^<]*)</(?P=tag)>",
    re.IGNORECASE,
)
# Any mark at all, however written, so one the build cannot fill stops it.
ANY_MARK = re.compile(r"data-figure\s*=", re.IGNORECASE)
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


def as_date(value):
    """Returns a date from TTB's record as YYYY-MM-DD.

    Args:
        value: The record's Established value: epoch milliseconds (an
            esriFieldTypeDate in an ArcGIS REST response, in UTC), an ISO
            date or date-time string, or None.

    Returns:
        The date, or None when value is not one.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        when = datetime.datetime.fromtimestamp(value / 1000, datetime.UTC)
        return when.date().isoformat()
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value[:10]).isoformat()
        except ValueError:
            return None
    return None


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
            an established AVA lacks its date or its CFR section (a
            placeholder such as "27 CFR 9.XXX" is not one).
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
    established_on = as_date(record.get("Established"))
    if established_on is None or not re.fullmatch(r"27 CFR 9\.\d+", cfr):
        sys.exit(
            "an established AVA needs its Established date and CFR_Section"
            f" (27 CFR 9.n): {record.get('Established')!r}, {cfr!r}"
        )
    return {
        "name": record["Name"],
        "status": status,
        "established_on": established_on,
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


def revision_of(gis_dir):
    """Returns the proposed revision's date, checked against the build.

    The date is typed once, in resources/boundary/revision-date.txt
    (src/revision.py); the build names its files after it, so the GIS area
    file's name must carry the same date.

    Args:
        gis_dir: The build's GIS folder, whose area file is named like
            hickory-sands-district-boundary-proposed-<date>-area-EPSG4269.

    Returns:
        The date, YYYY-MM-DD.

    Raises:
        SystemExit: When the area file's name carries no date, or another
            date than the revision's (a build older than the date's file).
    """
    found = glob.glob(os.path.join(gis_dir, "*-area-EPSG4269.geojson"))
    dated = re.search(
        r"-(\d{4}-\d{2}-\d{2})-area-EPSG4269\.geojson$",
        found[0] if found else "",
    )
    if len(found) != 1 or not dated:
        sys.exit(f"no dated area file in {gis_dir}")
    if dated.group(1) != revision.ISO:
        sys.exit(
            f"{gis_dir} was built for {dated.group(1)}, but the revision is"
            f" {revision.ISO} ({revision.FILE}): run ./build.sh"
        )
    return revision.ISO


def compared_areas(stats_path):
    """Returns the other boundaries' areas the build measured, in sq mi.

    Args:
        stats_path: The review stage's grit-change-stats.json, or None.

    Returns:
        A dict with petition_sqmi and notice_243_sqmi (empty without stats).

    Raises:
        SystemExit: When the file lacks either area.
    """
    if not stats_path:
        return {}
    with open(stats_path, encoding="utf-8") as fh:
        sqmi = json.load(fh).get("sqmi", {})
    if not {"petition", "notice_243"} <= set(sqmi):
        sys.exit(f"{stats_path}: no petition and notice_243 areas")
    return {
        "petition_sqmi": float(sqmi["petition"]),
        "notice_243_sqmi": float(sqmi["notice_243"]),
    }


def site_data(gis_dir, stats_path=None):
    """Returns the website's data files, by name, as the text to write.

    Args:
        gis_dir: The build's GIS folder.
        stats_path: The review stage's grit-change-stats.json, for the
            petition's and Notice No. 243's areas, or None.

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
    revised = revision_of(gis_dir)
    boundary = [
        feature(
            area[0],
            {
                "name": first["Name"],
                "area_sqmi": float(first["area_sqmi"]),
                "counties": first["Counties"],
                "revision": revised,
                **compared_areas(stats_path),
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


def samples(a, b):
    """Returns points every SAMPLE_M (or less) along a segment, ends included.

    Args:
        a: The segment's start, (x, y) in metres.
        b: Its end.

    Returns:
        A list of (x, y) points from a to b.
    """
    n = max(1, math.ceil(math.dist(a, b) / SAMPLE_M))
    return [
        (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
        for k in range(n + 1)
    ]


def farthest(lines, others, limit):
    """Returns how far the farthest point of lines lies from others.

    Each segment of lines that others do not share is measured every
    SAMPLE_M along its length, so the answer is within SAMPLE_M / 2 of the
    exact one.

    Args:
        lines: Lines of (x, y) positions in metres.
        others: The lines to measure from.
        limit: The distance beyond which the answer is only "too far".

    Returns:
        The largest distance from a point of lines to its nearest segment of
        others, in metres, or None when one is more than limit away.
    """
    grid = {}
    shared = set()
    for line in others:
        for a, b in itertools.pairwise(line):
            shared.update(((a, b), (b, a)))
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
    worst = 0.0
    for line in lines:
        for a, b in itertools.pairwise(line):
            if (a, b) in shared:
                continue
            for p in samples(a, b):
                cell = (math.floor(p[0] / CELL_M), math.floor(p[1] / CELL_M))
                d = min(
                    (to_segment(p, c, e) for c, e in grid.get(cell, ())),
                    default=math.inf,
                )
                if d > limit:
                    return None
                worst = max(worst, d)
    return worst


def apart_m(a, b, limit):
    """Returns how far apart two shapes' lines are at most, up to limit.

    The distance is the largest from a point of either shape's lines to the
    other's (their Hausdorff distance, measured every SAMPLE_M), so a vertex
    that only slides along a line does not count, and the shapes may have
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
    one = farthest(la, lb, limit)
    other = farthest(lb, la, limit)
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
        or None when that is more than MAX_DRIFT_M or a committed shape is
        malformed.
    """
    a, b = json.loads(have)["features"], json.loads(want)["features"]
    worst = 0.0
    for f, g in zip(a, b, strict=True):
        try:
            d = apart_m(
                f["geometry"]["coordinates"],
                g["geometry"]["coordinates"],
                MAX_DRIFT_M,
            )
        except IndexError, KeyError, TypeError:  # not a shape: stale
            return None
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
    have = set()
    if os.path.isdir(out_dir):  # leave dotfiles (.DS_Store) alone
        have = {n for n in os.listdir(out_dir) if not n.startswith(".")}
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


def same_text(path, text):
    """Returns whether the file at path holds exactly text.

    Args:
        path: A file, which may be missing.
        text: The text it should hold.

    Returns:
        True when it does.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read() == text
    except FileNotFoundError:
        return False


def write_one(path, text):
    """Writes text to path in one step (a temporary file, then a rename).

    Args:
        path: The file to write.
        text: Its text.
    """
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(path + ".tmp", path)


def write(files, out_dir):
    """Writes files to out_dir, each in one step, and removes any other file.

    Args:
        files: A dict from file name to the text it should hold.
        out_dir: The site's data folder, which only this script writes.
    """
    os.makedirs(out_dir, exist_ok=True)
    for name, text in files.items():
        write_one(os.path.join(out_dir, name), text)
    for name in compare(files, out_dir)[2]:
        os.remove(os.path.join(out_dir, name))


def figures(files):
    """Returns the figures the pages show, from the site's data files.

    Args:
        files: The data files, by name, as site_data() gives them or as
            committed in docs/data/.

    Returns:
        A dict from figure name to (text, ISO date or None): area_sqmi
        ("193.83"), area_whole ("194", rounded half up), step_count,
        point_count, miles (the line's length, to the mile),
        revision_date ("October 15, 2026", with its ISO date for a <time>),
        and, when the build measured them, petition_area_whole and
        notice_243_area_whole (the petition's and Notice No. 243's areas,
        whole square miles).
    """
    (boundary,) = json.loads(files["boundary.geojson"])["features"]
    steps = json.loads(files["steps.geojson"])["features"]
    points = json.loads(files["points.geojson"])["features"]
    area = boundary["properties"]["area_sqmi"]
    metres = sum(f["properties"]["length_m"] for f in steps)
    dated = datetime.date.fromisoformat(boundary["properties"]["revision"])

    def whole(sqmi):  # whole square miles, rounded half up
        return str(
            decimal.Decimal(str(sqmi)).quantize(
                decimal.Decimal(1), rounding=decimal.ROUND_HALF_UP
            )
        )

    compared = {
        f"{key.removesuffix('_sqmi')}_area_whole": (whole(value), None)
        for key, value in boundary["properties"].items()
        if key in ("petition_sqmi", "notice_243_sqmi")
    }
    return {
        **compared,
        "area_sqmi": (f"{area:.2f}", None),
        "area_whole": (whole(area), None),
        "step_count": (str(len(steps)), None),
        "point_count": (str(len(points)), None),
        "miles": (f"{metres / M_PER_MILE:.0f}", None),
        "revision_date": (
            " ".join(
                (
                    revision.LONG_MONTHS[dated.month - 1],
                    f"{dated.day},",
                    str(dated.year),
                )
            ),
            dated.isoformat(),
        ),
    }


def fill_figures(text, figs, where):
    """Returns a page with each marked figure written from figs.

    Args:
        text: The page's HTML.
        figs: The figures, from figures().
        where: The page's name, for errors.

    Returns:
        The HTML with every data-figure element's text replaced (escaped),
        and a <time>'s datetime set to the figure's ISO date.

    Raises:
        SystemExit: When a figure is unknown, or a marked element holds more
            than text.
    """
    if len(ANY_MARK.findall(text)) != len(FIGURE.findall(text)):
        sys.exit(
            f"{where}: write each figure as "
            '<tag data-figure="name">text</tag>, with only text inside'
        )

    def write_figure(m):
        if m["name"] not in figs:
            sys.exit(f"{where}: no figure called {m['name']}")
        value, iso = figs[m["name"]]
        attrs = m["attrs"]
        if iso and m["tag"].lower() == "time":
            dated = re.compile(r'(\sdatetime=")[^"]*(")', re.IGNORECASE)
            if dated.search(attrs):
                attrs = dated.sub(lambda d: f"{d[1]}{iso}{d[2]}", attrs)
            else:
                attrs += f' datetime="{iso}"'
        return f"<{m['tag']}{attrs}>{html.escape(value)}</{m['tag']}>"

    return FIGURE.sub(write_figure, text)


def stale_figures(text, filled):
    """Returns the names of the figures a page has wrong.

    Args:
        text: The page as committed.
        filled: The page with its figures written by fill_figures().

    Returns:
        The sorted names of the marked figures that differ.
    """
    pairs = zip(FIGURE.finditer(text), FIGURE.finditer(filled), strict=True)
    return sorted({a["name"] for a, b in pairs if a[0] != b[0]})


def committed(files, out_dir):
    """Returns the committed copies of the data files, by name.

    Args:
        files: The build's data files (for their names).
        out_dir: The site's data folder.

    Returns:
        A dict from file name to its committed text.
    """
    texts = {}
    for name in files:
        with open(os.path.join(out_dir, name), encoding="utf-8") as fh:
            texts[name] = fh.read()
    return texts


def site_pages(pages_dir, skip):
    """Returns the site's pages that may hold figures, by path.

    Args:
        pages_dir: The site's folder (docs).
        skip: A page the build makes itself (the walk page), or None.

    Returns:
        A dict from path to the page's text.
    """
    pages = {}
    for path in sorted(glob.glob(os.path.join(pages_dir, "*.html"))):
        if skip and os.path.abspath(path) == os.path.abspath(skip):
            continue
        with open(path, encoding="utf-8") as fh:
            pages[path] = fh.read()
    return pages


def walk_item(anchor, step, eyebrow, text, ends_at):
    """Returns one step of the walk page as an HTML list item.

    Args:
        anchor: The item's id, such as "step-13" or "beginning".
        step: The step number, or 0 for the beginning point.
        eyebrow: The line above the text, such as "Step 13 · Purdy Hill".
        text: The step's text from the boundary description.
        ends_at: The name of the point the step ends at.

    Returns:
        The item's HTML, every value escaped.
    """
    return (
        f'<li class="walk-step" id="{anchor}" data-step="{step}">'
        f'<p class="walk-eyebrow">{html.escape(eyebrow)}</p>'
        f'<p class="walk-text">{html.escape(text)}</p>'
        f'<p class="walk-point"><span>{"Begins" if step == 0 else "Ends"}'
        f"</span> {html.escape(ends_at)}</p></li>"
    )


def walk_page(files, template):
    """Returns the walk page (#112): every step of the line, in order.

    The page is the story map's text, so it reads in full without
    JavaScript; the map follows it when JavaScript runs. Lengths are shown
    to a tenth of a mile. The check makes the page from the committed data
    (check_page), so the small drift between machines (#116) cannot make it
    stale even where a length sits on a rounding edge.

    Args:
        files: The data files from site_data().
        template: The page's template, with @STEPS@ once and its figures
            marked data-figure.

    Returns:
        The page's HTML.

    Raises:
        SystemExit: When the template lacks a token or has one twice.
    """
    steps = json.loads(files["steps.geojson"])["features"]
    points = json.loads(files["points.geojson"])["features"]
    names = {p["properties"]["point"]: p["properties"] for p in points}
    start = names["Beginning"]
    items = [
        walk_item(
            "beginning",
            0,
            f"The beginning point · {start['quad']} quadrangle",
            "The line begins here and returns here at its last step.",
            start["point_name"],
        )
    ]
    for f in steps:
        p = f["properties"]
        miles = p["length_m"] / M_PER_MILE
        items.append(
            walk_item(
                f"step-{p['step']}",
                p["step"],
                f"Step {p['step']} · {p['quad']} · {miles:.1f} mi",
                p["narrative"],
                names[str(p["step"])]["point_name"],
            )
        )
    for token in WALK_TOKENS:
        if template.count(token) != 1:
            sys.exit(f"the walk template needs {token} once")
    page = template.replace("@STEPS@", "\n".join(items))
    return fill_figures(page, figures(files), "the walk page")


def check_page(files, out_dir, template, page_path):
    """Returns how the walk page differs from the one the data should give.

    The page is made from the committed data, once compare() has accepted it:
    the build's own data may differ from it within MAX_DRIFT_M (#116), and a
    length that drifts across a rounding edge must not make the page stale.

    Args:
        files: The build's data files, which out_dir matched.
        out_dir: The site's data folder.
        template: The walk page's template text.
        page_path: The committed walk page.

    Returns:
        "missing", "differs from the build", or None when it matches.
    """
    if not os.path.exists(page_path):
        return "missing"
    if not same_text(page_path, walk_page(committed(files, out_dir), template)):
        return "differs from the build"
    return None


def main():
    """Writes or checks the website's map data."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gis", required=True, help="the build's GIS folder")
    ap.add_argument("--out", required=True, help="the site's data folder")
    ap.add_argument(
        "--stats",
        help="the review stage's grit-change-stats.json (other areas)",
    )
    ap.add_argument(
        "--walk",
        nargs=2,
        metavar=("TEMPLATE", "PAGE"),
        help="also the walk page (docs/walk.html) from its template",
    )
    ap.add_argument(
        "--pages",
        help="also write (or check) the figures in the site's pages (docs)",
    )
    ap.add_argument("--check", action="store_true", help="compare only")
    args = ap.parse_args()
    skip = args.walk[1] if args.walk else None
    files = site_data(args.gis, args.stats)
    template = None
    if args.walk:
        with open(args.walk[0], encoding="utf-8") as fh:
            template = fh.read()
    if args.check:
        missing, differs, unexpected, notes = compare(files, args.out)
        for note in notes:
            print(f"note: {note} (#116; not a failure)")
        stale = bool(missing or differs or unexpected)
        for what, names in (
            ("missing", missing),
            ("differs from the build", differs),
            ("not made by the build", unexpected),
        ):
            if names:
                print(f"{args.out}: {what}: {', '.join(names)}")
        if template is not None and not stale:
            page = check_page(files, args.out, template, args.walk[1])
            if page:
                print(f"{args.walk[1]}: {page}")
                stale = True
        if args.pages and not stale:
            figs = figures(committed(files, args.out))
            for path, text in site_pages(args.pages, skip).items():
                wrong = stale_figures(text, fill_figures(text, figs, path))
                if wrong:
                    names = ", ".join(wrong)
                    print(f"{path}: figures differ from the build: {names}")
                    stale = True
        if stale:
            print(
                "run ./build.sh site-data and commit docs/data/ and the pages"
            )
            sys.exit(STALE)
        print(f"{args.out} matches the build ({len(files)} files)")
        return
    # Everything is made before anything is written, so an error in one page
    # leaves the site as it was.
    page = walk_page(files, template) if template is not None else None
    pages = {}
    if args.pages:
        figs = figures(files)
        for path, text in site_pages(args.pages, skip).items():
            filled = fill_figures(text, figs, path)
            if filled != text:
                pages[path] = filled
    write(files, args.out)
    print(f"wrote {len(files)} files to {args.out}")
    if page is not None:
        write_one(args.walk[1], page)
        print(f"wrote {args.walk[1]}")
    for path, filled in pages.items():
        write_one(path, filled)
        print(f"wrote the figures in {path}")


if __name__ == "__main__":
    main()
