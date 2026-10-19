"""The boundary drawing on Home and The boundary, made from the site's data.

Both pages draw the proposed revision as an inline SVG over the survey map,
docs/assets/survey-map.webp (#107, #126). The drawing is
docs/data/boundary.geojson carried from NAD83 to UTM zone 14N (EPSG:26914),
each ring simplified by Douglas-Peucker at 12 m (as GEOS simplifies, so GDAL's
Simplify(12) keeps the same vertices), and fitted to the drawing's viewBox:
the boundary's box centred, at the scale that leaves a margin of 11% of its
width (or of its height, where that fits tighter) on each side. The 5 km scale
bar is drawn at the same scale. src/site/make_site_data.py writes both into
the pages, where they are marked data-figure-path, and its --check stops the
build when one is stale; src/site/make_survey_map.py then fits the survey map
to the drawn line.

Standard library only, so the lint workflow tests it. The projection is the
Krüger series to the sixth order in the third flattening (Karney, 2011,
"Transverse Mercator with an accuracy of a few nanometers", Journal of
Geodesy 85, eq. 35), which agrees with PROJ's within a micrometre over the
boundary (tests/test_boundary_drawing.py).
"""

import json
import math

# The drawing's coordinate system, as The boundary's caption names it and
# docs/assets/survey-map.json records it (tests/test_boundary_drawing.py).
EPSG = 26914
CRS_NAME = "NAD83 / UTM zone 14N"
# GRS 1980, NAD83's ellipsoid, and UTM zone 14N.
SEMI_MAJOR_M = 6378137.0
FLATTENING = 1 / 298.257222101
SCALE_FACTOR = 0.9996
CENTRAL_MERIDIAN = -99.0
FALSE_EASTING_M = 500000.0
SIMPLIFY_M = 12.0  # the Douglas-Peucker tolerance, in metres on the ground
# The drawing's layout, a design value (not a boundary figure): the
# boundary's box takes 1 / (1 + 2 * MARGIN) of the viewBox on the tighter
# axis, centred.
MARGIN = 0.11
SCALE_BAR_M = 5000.0  # the scale bar's length on the ground ("5 km")
DECIMALS = 2  # viewBox units; at 1200 units across, 0.01 is about 0.5 m
# The series' coefficients alpha_1..alpha_6 (Karney, 2011, eq. 35), each a
# list of (numerator, denominator, power of the third flattening n).
KRUEGER = (
    (
        (1, 2, 1),
        (-2, 3, 2),
        (5, 16, 3),
        (41, 180, 4),
        (-127, 288, 5),
        (7891, 37800, 6),
    ),
    (
        (13, 48, 2),
        (-3, 5, 3),
        (557, 1440, 4),
        (281, 630, 5),
        (-1983433, 1935360, 6),
    ),
    ((61, 240, 3), (-103, 140, 4), (15061, 26880, 5), (167603, 181440, 6)),
    ((49561, 161280, 4), (-179, 168, 5), (6601661, 7257600, 6)),
    ((34729, 80640, 5), (-3418889, 1995840, 6)),
    ((212378941, 319334400, 6),),
)

_N = FLATTENING / (2 - FLATTENING)  # the third flattening
_E = math.sqrt(FLATTENING * (2 - FLATTENING))  # the eccentricity
_RECTIFYING_M = (  # the rectifying radius, A
    SEMI_MAJOR_M / (1 + _N) * (1 + _N**2 / 4 + _N**4 / 64 + _N**6 / 256)
)
_ALPHAS = tuple(sum(a / b * _N**k for a, b, k in terms) for terms in KRUEGER)


def utm14(lon, lat):
    """Returns NAD83 longitude and latitude in UTM zone 14N.

    Args:
        lon: Longitude, degrees east (negative here).
        lat: Latitude, degrees north.

    Returns:
        (easting, northing) in metres, as EPSG:26914.
    """
    phi = math.radians(lat)
    lam = math.radians(lon - CENTRAL_MERIDIAN)
    s = math.sin(phi)
    # The tangent of the conformal latitude, then the spherical transverse
    # Mercator coordinates (xi', eta'), which the series carries to the
    # ellipsoid's.
    t = math.sinh(math.atanh(s) - _E * math.atanh(_E * s))
    xi = math.atan2(t, math.cos(lam))
    eta = math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    east, north = eta, xi
    for j, a in enumerate(_ALPHAS, start=1):
        east += a * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
        north += a * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
    k = SCALE_FACTOR * _RECTIFYING_M
    return FALSE_EASTING_M + k * east, k * north


def to_segment(p, a, b):
    """Returns the distance from p to the segment from a to b.

    Args:
        p: An (x, y) position in metres.
        a: The segment's start.
        b: Its end (which may be a itself).

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


def simplify(line, tolerance):
    """Simplifies a line or a closed ring by Douglas-Peucker.

    A ring is simplified as a line from its first point back to the same
    point, as GEOS does, so its first point is kept.

    Args:
        line: The positions, (x, y) in metres; a ring repeats its first.
        tolerance: The largest distance a dropped point may lie from the
            simplified line, in metres.

    Returns:
        The kept positions, in order, first and last among them.
    """
    keep = [False] * len(line)
    keep[0] = keep[-1] = True
    sections = [(0, len(line) - 1)]
    while sections:
        first, last = sections.pop()
        far, at = -1.0, None
        for k in range(first + 1, last):
            d = to_segment(line[k], line[first], line[last])
            if d > far:
                far, at = d, k
        if at is not None and far > tolerance:
            keep[at] = True
            sections += [(first, at), (at, last)]
    return [p for p, kept in zip(line, keep, strict=True) if kept]


def rings_m(geojson_text):
    """Returns the boundary's rings in UTM zone 14N.

    Args:
        geojson_text: docs/data/boundary.geojson's text: NAD83 longitudes
            and latitudes, Polygon or MultiPolygon features.

    Returns:
        A list of rings, each a list of (easting, northing) in metres.
    """
    rings = []
    for feature in json.loads(geojson_text)["features"]:
        geometry = feature["geometry"]
        polygons = (
            [geometry["coordinates"]]
            if geometry["type"] == "Polygon"
            else geometry["coordinates"]
        )
        rings += [
            [utm14(p[0], p[1]) for p in ring]
            for polygon in polygons
            for ring in polygon
        ]
    return rings


def fit(rings, size):
    """Returns how the drawing places the ground in its viewBox.

    Args:
        rings: The boundary's rings, (easting, northing) in metres.
        size: The viewBox's (width, height).

    Returns:
        (scale, centre): viewBox units per metre, and the ground (easting,
        northing) drawn at the viewBox's centre, the middle of the
        boundary's box.
    """
    es = [p[0] for ring in rings for p in ring]
    ns = [p[1] for ring in rings for p in ring]
    room = 1 + 2 * MARGIN
    scale = min(
        size[0] / (room * (max(es) - min(es))),
        size[1] / (room * (max(ns) - min(ns))),
    )
    return scale, ((min(es) + max(es)) / 2, (min(ns) + max(ns)) / 2)


def number(value):
    """Returns a viewBox coordinate as the drawing writes it, 0.01 units."""
    return f"{value:.{DECIMALS}f}"


def paths(geojson_text, size):
    """Returns the drawing's paths, as their d attributes, by name.

    Args:
        geojson_text: docs/data/boundary.geojson's text.
        size: The viewBox's (width, height).

    Returns:
        A dict: "boundary", each ring simplified, in absolute moves and
        lines, closed ("M x,y L x,y ... Z"); "scale_bar", the 5 km bar with
        a tick at each end and in its middle, drawn from its left end.
    """
    rings = rings_m(geojson_text)
    scale, (east, north) = fit(rings, size)

    def drawn(p):
        x = size[0] / 2 + (p[0] - east) * scale
        y = size[1] / 2 - (p[1] - north) * scale
        return f"{number(x)},{number(y)}"

    boundary = " ".join(
        "M" + " L".join(drawn(p) for p in simplify(ring, SIMPLIFY_M)) + " Z"
        for ring in rings
    )
    bar = SCALE_BAR_M * scale
    return {
        "boundary": boundary,
        "scale_bar": f"M0 -8 V0 H{number(bar)} V-8 M{number(bar / 2)} 0 V-8",
    }
