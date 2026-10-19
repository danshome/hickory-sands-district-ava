"""The vineyards' data for the website, and the wells near each block.

From the committed resources/vineyards/vineyards-EPSG4269.geojson (see its
README.md): every block with its vineyard's name, its category (CATEGORIES:
the Hickory Sands District's vineyards, the Llano Uplift's outside the
district, vineyards under development, historical vineyards), the acres of
its outline and a short note of its source; a block sent through the
website's form also keeps the year its vineyard was first planted and its
varieties. src/site/make_vineyards.py writes, into docs/assets/vineyards/:

    vineyards.geojson
        The blocks, each with a vid, its name, category, the category's
        label, block (its number or a planned block's name, as text),
        acres and source; the 3D aquifer page draws one layer per
        category, the vineyards page lists them.
    vineyard-wells.json
        For each block (by its vid), every well within WELLS_M of its
        outline, nearest first: the distance in metres (0 inside it) and the
        well's drawing record, from the 3D page's committed well tiles
        (docs/assets/aquifer/wells/draw-*.json).
    register.json
        One entry per vineyard, for the vineyards page's list: its name,
        category, the vids of its blocks, the year first planted and the
        varieties (when given).
    counties.geojson
        The seven Llano Uplift counties as polygons, closed from the 3D
        page's county lines (docs/assets/aquifer/context.geojson), for the
        form's county guess only.

A block in no known category, or whose fields name a person (named()) or
give an e-mail address or a telephone number, stops the run. Standard
library only: the vineyard data is made on any machine, GitHub's runners
among them, without the 3D page's downloads.
"""

import hashlib
import itertools
import json
import math
import os
import re

from . import privacy
from . import record

VERSION = 1  # raise with any change to the output no parameter shows
# The fields of the resources file the site's GeoJSON keeps, in order.
FIELDS = ("name", "category", "block", "acres", "source")
# A vineyard's popup lists the wells within this many metres of it.
WELLS_M = 1000.0
# The vineyards' categories (resources/vineyards/), each a layer of its own
# on the 3D page and a group in the vineyards page's list, and how each is
# named.
CATEGORIES = (
    ("hsd", "Hickory Sands District vineyard"),
    ("llano-uplift", "Llano Uplift vineyard"),
    ("under-development", "Under development"),
    ("historical", "Historical vineyard"),
)
# The counties the register covers: TTB's proposed Llano Uplift AVA lies in
# these (the form offers them, and "Not sure").
COUNTIES = (
    "Blanco",
    "Burnet",
    "Gillespie",
    "Llano",
    "Mason",
    "McCulloch",
    "San Saba",
)
# The vineyards are named, but never a person: not the petitioner's name, an
# owner, a proprietor or a titled name (the gitignored .private-words, which
# the generator passes in, holds the other names never to publish).
PERSONAL = re.compile(
    r"\b(Dan|Daniel|McLaughlin)\b|\b(owner|owners|proprietor)\b",
    re.IGNORECASE,
)
M_LON = 111_320.0  # metres per degree of longitude at the equator
M_LAT = 110_574.0  # metres per degree of latitude, near enough here
# A county ring whose ends are further apart than this, in degrees, is not a
# county line that was only left open.
CLOSE_DEG = 0.2


def rings(geometry):
    """A Polygon's or MultiPolygon's rings, as lists of (lon, lat)."""
    if geometry["type"] == "Polygon":
        return [list(map(tuple, r)) for r in geometry["coordinates"]]
    return [list(map(tuple, r)) for p in geometry["coordinates"] for r in p]


def distance_m(lonlat, outline):
    """How far a point lies from an outline, in metres; 0 inside it.

    Measured on a plane tangent at the outline's first vertex, which is
    good to well under a metre over a kilometre.

    Args:
        lonlat: The point's (longitude, latitude).
        outline: rings()'s rings.

    Returns:
        The distance to the nearest edge, or 0 when the point is inside.
    """
    lon0, lat0 = outline[0][0]
    kx = M_LON * math.cos(math.radians(lat0))

    def xy(p):
        return ((p[0] - lon0) * kx, (p[1] - lat0) * M_LAT)

    px, py = xy(lonlat)
    inside = False
    best = math.inf
    for ring in outline:
        pts = [xy(p) for p in ring]
        for (ax, ay), (bx, by) in itertools.pairwise(pts):
            if (ay > py) != (by > py) and px < ax + (py - ay) * (bx - ax) / (
                by - ay
            ):
                inside = not inside
            dx, dy = bx - ax, by - ay
            length = dx * dx + dy * dy
            t = (
                0.0
                if not length
                else ((px - ax) * dx + (py - ay) * dy) / length
            )
            t = max(0.0, min(1.0, t))
            best = min(best, math.hypot(px - ax - t * dx, py - ay - t * dy))
    return 0.0 if inside else best


def named(text, extra_words=()):
    """Whether a vineyard's text names a person or gives a contact.

    Args:
        text: The text.
        extra_words: More words never to publish (.private-words).

    Returns:
        True when it holds PERSONAL, a title, one of extra_words, an e-mail
        address or a telephone number.
    """
    low = text.lower()
    return bool(
        PERSONAL.search(text)
        or privacy.TITLE.search(text)
        or privacy.EMAIL.search(text)
        or privacy.PHONE.search(text)
        or any(w.lower() in low for w in extra_words if w.strip())
    )


def checked(props, where, extra_words=()):
    """A block's fields, refused if they name someone or give a contact.

    Args:
        props: The fields.
        where: The block, for the error.
        extra_words: More words never to publish (.private-words).

    Returns:
        The fields.

    Raises:
        SystemExit: named() finds a name or a contact.
    """
    if named(json.dumps(props, ensure_ascii=False), extra_words):
        raise SystemExit(f"a name or contact in the vineyard block {where}")
    return props


def rules_digest():
    """A digest of the privacy rules the vineyards are held to."""
    patterns = [
        p.pattern
        for p in (PERSONAL, privacy.TITLE, privacy.EMAIL, privacy.PHONE)
    ]
    text = json.dumps(patterns, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def tile_wells(wells_dir):
    """Every well drawn on the 3D page, from its committed drawing tiles.

    Args:
        wells_dir: docs/assets/aquifer/wells.

    Returns:
        (wells, draw): the wells as [{"uid", "lonlat"}], in the tiles'
        order, and their drawing records by uid.
    """
    draw = {}
    for path in tile_paths(wells_dir):
        with open(path, encoding="utf-8") as fh:
            for rec in json.load(fh):
                draw[rec[0]] = rec
    wells = [{"uid": uid, "lonlat": (r[1], r[2])} for uid, r in draw.items()]
    return wells, draw


def tile_paths(wells_dir):
    """The drawing tiles of wells/index.json, sorted, that exist."""
    with open(os.path.join(wells_dir, "index.json"), encoding="utf-8") as fh:
        keys = sorted(json.load(fh)["tiles"])
    paths = [os.path.join(wells_dir, f"draw-{k}.json") for k in keys]
    return [p for p in paths if os.path.exists(p)]


def tiles_digest(wells_dir):
    """One digest over wells/index.json and every drawing tile's SHA-256."""
    names = ["index.json"] + [
        os.path.basename(p) for p in tile_paths(wells_dir)
    ]
    digest = hashlib.sha256()
    for name in names:
        sha = record.sha256_file(os.path.join(wells_dir, name))
        digest.update(f"{name} {sha}\n".encode())
    return "sha256:" + digest.hexdigest()


def near_wells(outline, wells, draw):
    """The wells within WELLS_M of an outline, nearest first.

    Args:
        outline: rings()'s rings.
        wells: The wells drawn (tile_wells()'s).
        draw: The wells' drawing records, by uid.

    Returns:
        A list of [distance in metres, then the drawing record's values].
    """
    radius = WELLS_M
    lons = [p[0] for r in outline for p in r]
    lats = [p[1] for r in outline for p in r]
    pad_lat = radius / M_LAT
    pad_lon = radius / (M_LON * math.cos(math.radians(max(map(abs, lats)))))
    west, east = min(lons) - pad_lon, max(lons) + pad_lon
    south, north = min(lats) - pad_lat, max(lats) + pad_lat
    found = []
    for w in wells:
        lon, lat = w["lonlat"]
        if west <= lon <= east and south <= lat <= north:
            d = distance_m((lon, lat), outline)
            if d <= radius:
                found.append((round(d), w["uid"]))
    found.sort()
    return [[d, *draw[uid]] for d, uid in found]


def counties(context_path):
    """The Llano Uplift's counties as polygons, from the 3D page's lines.

    Args:
        context_path: docs/assets/aquifer/context.geojson.

    Returns:
        A GeoJSON FeatureCollection, one Polygon per county of COUNTIES,
        named without "County".

    Raises:
        SystemExit: A county is missing, or its line is not one ring left
            open at most by its closing point.
    """
    with open(context_path, encoding="utf-8") as fh:
        found = {
            f["properties"]["name"]: f["geometry"]
            for f in json.load(fh)["features"]
            if f["properties"].get("kind") == "county"
        }
    feats = []
    for name in COUNTIES:
        geom = found.get(f"{name} County")
        if not geom or geom["type"] != "LineString":
            raise SystemExit(f"context.geojson: no line for {name} County")
        ring = [list(p) for p in geom["coordinates"]]
        gap = math.dist(ring[0], ring[-1])
        if len(ring) < 4 or gap > CLOSE_DEG:
            raise SystemExit(f"{name} County's line is not a ring")
        if gap:
            ring.append(list(ring[0]))
        feats.append(
            {
                "type": "Feature",
                "properties": {"name": name},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )
    return {"type": "FeatureCollection", "features": feats}


def register(source, labels, extra_words=()):
    """One entry per vineyard, for the vineyards page's list.

    Args:
        source: The resources file's features.
        labels: CATEGORIES as a dict.
        extra_words: More words never to publish (.private-words).

    Returns:
        A list of {"name", "category", "category_label", "vids", "year",
        "varieties"}, in CATEGORIES' order and then by name.
    """
    order = [c for c, _ in CATEGORIES]
    out = {}
    for i, f in enumerate(source, 1):
        p = f["properties"]
        key = (p["category"], p["name"])
        entry = out.setdefault(
            key,
            {
                "name": p["name"],
                "category": p["category"],
                "category_label": labels[p["category"]],
                "vids": [],
                "year": None,
                "varieties": [],
            },
        )
        entry["vids"].append(f"v-{i}")
        if entry["year"] is None and isinstance(p.get("year"), int):
            entry["year"] = p["year"]
        for v in p.get("varieties") or ():
            if isinstance(v, str) and v not in entry["varieties"]:
                entry["varieties"].append(v)
    entries = sorted(
        out.values(),
        key=lambda e: (order.index(e["category"]), e["name"].casefold()),
    )
    for e in entries:
        checked(e, e["name"], extra_words)
    return entries


def write(paths, out_dir, extra_words=()):
    """Writes the vineyard data the site shows.

    Args:
        paths: The inputs: "vineyards" (the resources file), "wells" (the
            3D page's well folder) and "context" (its context.geojson).
        out_dir: The new data folder.
        extra_words: More words never to publish (.private-words).

    Returns:
        The figures the pages show, by name: blocks and vineyards in each
        category, the wells near them and the radius.

    Raises:
        SystemExit: A block has no known category, or names someone.
    """
    labels = dict(CATEGORIES)
    with open(paths["vineyards"], encoding="utf-8") as fh:
        source = json.load(fh)["features"]
    wells, draw = tile_wells(paths["wells"])
    feats = []
    near = {}
    for i, f in enumerate(source, 1):
        p = f["properties"]
        if p.get("category") not in labels:
            raise SystemExit(f"vineyard block {i}: no known category")
        checked(p, i, extra_words)
        props = checked(
            {
                "vid": f"v-{i}",
                **{k: p.get(k) for k in FIELDS},
                "category_label": labels[p["category"]],
            },
            i,
            extra_words,
        )
        feats.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": f["geometry"],
            }
        )
        near[props["vid"]] = near_wells(rings(f["geometry"]), wells, draw)
    record.write_json(
        os.path.join(out_dir, "vineyards.geojson"),
        {"type": "FeatureCollection", "features": feats},
    )
    record.write_json(
        os.path.join(out_dir, "vineyard-wells.json"),
        {
            "radius_m": WELLS_M,
            "fields": (
                "distance_m, then the drawing record (wells/index.json fields)"
            ),
            "vineyards": near,
        },
    )
    record.write_json(
        os.path.join(out_dir, "register.json"),
        {
            "about": (
                "One entry per vineyard of vineyards.geojson, for the "
                "vineyards page's list (src/site/make_vineyards.py)"
            ),
            "vineyards": register(source, labels, extra_words),
        },
        indent=1,
    )
    record.write_json(
        os.path.join(out_dir, "counties.geojson"), counties(paths["context"])
    )
    figs = {
        "vineyard_wells_radius_m": WELLS_M,
        "vineyard_wells_near": len({r[1] for v in near.values() for r in v}),
        "vineyard_blocks": len(feats),
    }
    for key in labels:
        found = [f for f in feats if f["properties"]["category"] == key]
        name = key.replace("-", "_")
        figs[f"vineyards_{name}_blocks"] = len(found)
        figs[f"vineyards_{name}_names"] = len(
            {f["properties"]["name"] for f in found}
        )
    return figs
