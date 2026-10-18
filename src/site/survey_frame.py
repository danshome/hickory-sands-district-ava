"""The ground under the boundary drawing on Home and The boundary.

Both pages draw the proposed revision as an inline SVG over a survey map,
docs/assets/survey-map.webp. These read the drawing from a page, find the ground
its viewBox covers by fitting the drawn line to the boundary in UTM zone 14N,
and compare the record docs/data/survey-map.json keeps of that frame and of the
quads the image was made from. src/site/make_survey_map.py makes the image.
Standard library only, so the lint workflow tests it.
"""

import re

VIEWBOX = re.compile(
    r'<svg class="boundary-map" viewBox="0 0 (?P<w>[\d.]+) (?P<h>[\d.]+)"'
)
IMAGE = re.compile(
    r'<image class="survey-layer" href="(?P<href>[^"]+)" '
    r'width="(?P<w>[\d.]+)" height="(?P<h>[\d.]+)"\s*/>'
)
LINE = re.compile(r'<path class="boundary-line"[^>]*\sd="(?P<d>[^"]+)"')
POINT = re.compile(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")
# The drawing is north-up at one scale: its axes' scales may differ by no more
# than this share.
MAX_SKEW = 0.001
# How far (m) a frame edge may move before the record is stale: the fit's
# inputs are committed, so two machines differ only in PROJ's last digits.
MAX_SHIFT_M = 2.0


def drawing(text):
    """Reads the boundary drawing from a page.

    Args:
        text: The page's HTML.

    Returns:
        (size, href, points): the viewBox's (width, height); the survey
        image's href; the drawn boundary line's points in viewBox units.

    Raises:
        ValueError: The page has no drawing, or its image does not fill the
            viewBox from its origin.
    """
    box, image, line = (r.search(text) for r in (VIEWBOX, IMAGE, LINE))
    if not (box and image and line):
        raise ValueError("no boundary drawing (viewBox, survey image, line)")
    size = (float(box["w"]), float(box["h"]))
    if (float(image["w"]), float(image["h"])) != size:
        raise ValueError(f"the survey image does not fill the viewBox {size}")
    points = [(float(x), float(y)) for x, y in POINT.findall(line["d"])]
    return size, image["href"], points


def fit(points, ground, size):
    """Finds the ground a north-up drawing's viewBox covers.

    The drawn line and the boundary are matched by their bounding boxes: the
    drawing's scale is the ratio of their widths (and of their heights, which
    must agree), and its origin follows from their north-west corners. The
    drawn line is the boundary simplified, so the fit is good to about the
    simplification's tolerance.

    Args:
        points: The drawn line's points, (x, y) in viewBox units, y down.
        ground: The boundary's points, (easting, northing) in metres.
        size: The viewBox's (width, height).

    Returns:
        (west, south, east, north) of the viewBox on the ground, in metres.

    Raises:
        ValueError: The two axes' scales disagree (not one north-up scale).
    """
    xs, ys = zip(*points, strict=True)
    es, ns = zip(*ground, strict=True)
    sx = (max(xs) - min(xs)) / (max(es) - min(es))  # units per metre
    sy = (max(ys) - min(ys)) / (max(ns) - min(ns))
    if abs(sx / sy - 1) > MAX_SKEW:
        raise ValueError(f"the drawing's scales differ: {sx:.6f} vs {sy:.6f}")
    west = min(es) - min(xs) / sx
    north = max(ns) + min(ys) / sy
    return (west, north - size[1] / sy, west + size[0] / sx, north)


def record(frame, size, href, quads):
    """The record of what the survey image shows and was made from.

    Args:
        frame: (west, south, east, north) in metres, UTM zone 14N (NAD83).
        size: The image's (width, height) in pixels.
        href: The image's path, relative to the pages.
        quads: Manifest rows (quad, edition, geotiff), any order; the
            GeoTIFF's file name holds USGS's scan number, so it names the
            print.

    Returns:
        A dict for docs/data/survey-map.json.
    """
    return {
        "image": href,
        "crs": "EPSG:26914",
        "frame_m": dict(
            zip(
                ("west", "south", "east", "north"),
                (round(v) for v in frame),
                strict=True,
            )
        ),
        "pixels": [round(v) for v in size],
        "quads": sorted(
            ({k: q[k] for k in ("quad", "edition", "geotiff")} for q in quads),
            key=lambda q: q["quad"],
        ),
    }


def differences(old, new):
    """What differs between two records, beyond the frame's tolerance.

    Args:
        old: The committed record, or None.
        new: The record this build gives.

    Returns:
        A list of what differs; empty when the image is up to date.
    """
    if not old:
        return ["no record"]
    out = [
        key
        for key in ("image", "crs", "pixels", "quads")
        if old.get(key) != new[key]
    ]
    edges = old.get("frame_m") or {}
    out += [
        f"frame {edge} {edges.get(edge)} -> {value}"
        for edge, value in new["frame_m"].items()
        if edges.get(edge) is None or abs(edges[edge] - value) > MAX_SHIFT_M
    ]
    return out
