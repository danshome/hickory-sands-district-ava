"""The vineyard outlines of the 3D aquifer page, and the wells near each.

From the committed resources/vineyards/vineyards-EPSG4269.geojson (see its
README.md): every block with its vineyard's name, its category
(params.VINEYARD_CATEGORIES: the Hickory Sands District's vineyards, the
Llano Uplift's outside the district, vineyards under development, historical
vineyards), the acres of its outline and a short note of its source. It
writes into the page's data folder:

    vineyards.geojson
        The blocks, each with a vid, its name, category, the category's
        label, block number, acres and source; the page draws one layer per
        category.
    vineyard-wells.json
        For each block (by its vid), every well within
        params.VINEYARD_WELLS_M of its outline, nearest first: the distance
        in metres (0 inside it) and the well's drawing record.

A block in no known category, or whose fields name a person (named()) or
give an e-mail address or a telephone number, stops the run. Standard
library only.
"""

import itertools
import json
import math
import os
import re

from . import params
from . import privacy
from . import record

FIELDS = ("name", "category", "block", "acres", "source")
# The vineyards are named, but never a person: not the petitioner's name, an
# owner, a proprietor or a titled name (the gitignored .private-words, which
# the generator passes in, holds the other names never to publish).
PERSONAL = re.compile(
    r"\b(Dan|Daniel|McLaughlin)\b|\b(owner|owners|proprietor)\b",
    re.IGNORECASE,
)
M_LON = 111_320.0  # metres per degree of longitude at the equator
M_LAT = 110_574.0  # metres per degree of latitude, near enough here


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


def near_wells(outline, wells, draw):
    """The wells within params.VINEYARD_WELLS_M of an outline, nearest first.

    Args:
        outline: rings()'s rings.
        wells: The wells drawn (wells.write()'s).
        draw: The wells' drawing records, by uid.

    Returns:
        A list of [distance in metres, then the drawing record's values].
    """
    radius = params.VINEYARD_WELLS_M
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


def write(paths, wells, draw, out_dir, extra_words=()):
    """Writes the vineyard blocks and the wells near each.

    Args:
        paths: The inputs, by name (record.LOCAL's, as paths).
        wells: The wells drawn (wells.write()'s).
        draw: The wells' drawing records, by uid.
        out_dir: The page's new data folder.
        extra_words: More words never to publish (.private-words).

    Returns:
        The figures the page shows, by name: blocks and vineyards in each
        category.
    """
    labels = dict(params.VINEYARD_CATEGORIES)
    with open(paths["vineyards"], encoding="utf-8") as fh:
        source = json.load(fh)["features"]
    feats = []
    near = {}
    for i, f in enumerate(source, 1):
        p = f["properties"]
        if p.get("category") not in labels:
            raise SystemExit(f"vineyard block {i}: no known category")
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
            "radius_m": params.VINEYARD_WELLS_M,
            "fields": (
                "distance_m, then the drawing record (wells/index.json fields)"
            ),
            "vineyards": near,
        },
    )
    figs = {
        "vineyard_wells_radius_m": params.VINEYARD_WELLS_M,
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
