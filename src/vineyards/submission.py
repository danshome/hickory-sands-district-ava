"""A vineyard sent through the website's form: checks, issue, review, file.

The Python side of the vineyard form (docs/vineyards.html, "Add your
vineyard"). The page posts a submission (JSON) to one Supabase Edge Function
(src/vineyards/functions/vineyard-submit/), which checks it with the same
rules as here (docs/assets/vineyard-blocks.js, the JavaScript twin, which
the page and the function share; tests/test_vineyard_rules.py holds the two
to the same answers), keeps the contact details in one locked table and
opens a public GitHub issue that holds only the public fields, in the fixed
layout issue_body() writes. In this repository, the vineyard-check Action
reads that issue back (parse_issue()), checks it again with the current data
(review(): acres, the proposed district, vineyards already on the map, wells
nearby) and comments; when the petitioner adds the label `approved`, the
vineyard-approve Action adds the blocks to resources/vineyards/
(add_blocks()) and opens the pull request.

Submission (version 1), as the page posts it:

    {"form": "hsd-vineyard", "version": 1, "id": "<a UUID 4>",
     "vineyard": {"name", "county", "planted": "planted" | "planned",
                  "acres": number | null, "year": int | null,
                  "varieties": [str]},
     "blocks": [[[lon, lat], ...], ...],    # open rings, WGS 84
     "pin": [lon, lat] | null,
     "contact": {"name", "email", "phone"},  # never in the issue
     "agree": {"public": true, "permission": true},
     "website": ""}                          # a trap for bots: always empty

A change to a listed vineyard ("Suggest a change", version 2) is the same,
with "version": 2, "changes": <the vineyard's id, a key of
docs/assets/vineyards/known.json> and "note": <the sender's short public
note on what changed>; its blocks are required (no pin). Its issue shows the
listed vineyard beside the suggestion; approving it replaces that vineyard's
blocks and fields (add_blocks()) instead of adding a vineyard.

Standard library only, apart from the repository's own src/site/aquifer
(also standard library only); the Actions run it without installing
anything. Import it as src.vineyards.submission, with the repository's root
on sys.path.
"""

import datetime
import difflib
import itertools
import json
import math
import os
import re
import unicodedata

from src.site.aquifer import privacy
from src.site.aquifer import vineyards as places

ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # the repository (src/vineyards/../..)
FORM = "hsd-vineyard"
VERSION = 1
CHANGE_VERSION = 2  # a change to a listed vineyard
MARK = "<!-- hsd-vineyard-submission: v1 -->"
CHECK_MARK = "<!-- hsd-vineyard-check: v1 -->"
LABEL = "vineyard-submission"
CHANGE_LABEL = "vineyard-change"
APPROVED = "approved"
DATA_LABEL = "vineyard-data"
# The form's GitHub App ("HSD vineyard form") opens every submission's
# issue; no person can open one as it. The workflows' gates name the same.
BOT = "hsd-vineyard-form[bot]"
# Who edits the check comment: the Actions' own token.
ACTIONS_BOT = "github-actions[bot]"
VINEYARDS = "resources/vineyards/vineyards-EPSG4269.geojson"
LLANO = "docs/assets/aquifer/llano-uplift.geojson"
DISTRICT = "docs/data/boundary.geojson"
WELLS = "docs/assets/aquifer/wells"

COUNTIES = (*places.COUNTIES, "Not sure")
# The chips the form offers; anything else goes in "Others".
VARIETIES = (
    "Aglianico",
    "Albariño",
    "Barbera",
    "Blanc du Bois",
    "Cabernet Sauvignon",
    "Charbono",
    "Chardonnay",
    "Chenin Blanc",
    "Cinsault",
    "Graciano",
    "Grenache",
    "Grenache Blanc",
    "Malbec",
    "Malvasia Bianca",
    "Marsanne",
    "Merlot",
    "Montepulciano",
    "Mourvèdre",
    "Muscat Canelli",
    "Petit Verdot",
    "Petite Sirah",
    "Picpoul Blanc",
    "Pinot Grigio",
    "Roussanne",
    "Ruby Cabernet",
    "Sangiovese",
    "Semillon",
    "Syrah",
    "Tannat",
    "Tempranillo",
    "Touriga Nacional",
    "Vermentino",
    "Viognier",
)
LIMITS = {
    "name": 80,
    "variety": 40,
    "varieties": 20,
    "contact_name": 80,
    "email": 120,
    "phone": 30,
    "blocks": 20,
    "corners": 100,
    "block_min_acres": 0.02,
    "block_max_acres": 300.0,
    "total_max_acres": 2000.0,
    "acres_max": 2000.0,
    "year_min": 1900,
    "year_ahead": 5,
    "body_bytes": 65536,
    "note": 300,
}
TEXAS = (-107.0, 25.0, -93.0, 37.0)  # west, south, east, north
ACRE_M2 = 4046.8564224
# GRS 80 (NAD83's ellipsoid; WGS 84's differs by under a millimetre here)
A = 6378137.0
F = 1 / 298.257222101
E2 = F * (2 - F)
E = math.sqrt(E2)

# Free text in a public field: letters, digits, spaces and plain punctuation.
PUBLIC_TEXT = re.compile(r"^[\w .,'’&()/:-]*$")
WEBBY = re.compile(
    r"https?:|www\.|//|\b[a-z0-9-]+\.(com|net|org|io|co|us|info|biz|xyz|ru"
    r"|cn|top|site|online|shop|app|dev|link|me|ly|tk|gg)\b",
    re.IGNORECASE,
)
PERSON_TEXT = re.compile(r"^[^\W\d_]+(?:[ .'’-]+[^\W\d_]+)*\.?$")
EMAIL = re.compile(
    r"^[^\s@<>()\[\],;:\"]+@[^\s@<>()\[\],;:\"]+\.[a-z]{2,}$", re.IGNORECASE
)
# A telephone number however it is written: seven digits or more once spaces
# and ( ) . / - are taken out.
DIGIT_RUN = re.compile(r"\d{7,}")
SEPARATORS = re.compile(r"[\s()./-]")
UUID4 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
NAME_PROBLEMS = {
    "web": "Leave web addresses out of the name.",
    "characters": "Use only letters, numbers and simple punctuation.",
    "contact": (
        "Leave phone numbers and email addresses out of the name. "
        "There is a place for them in step 4."
    ),
    "title": "Leave out titles like Mr., Mrs. or Dr. (write Drive in full).",
    "personal": (
        "The register can't show this name as written. Change the "
        "wording, or email the petitioners."
    ),
}
NOTE_PROBLEMS = {
    "web": "Leave web addresses out of the note.",
    "characters": (
        "Use only letters, numbers and simple punctuation in the note."
    ),
    "contact": (
        "Leave phone numbers and email addresses out of the note. "
        "There is a place for them in step 4."
    ),
    "title": "Leave out titles like Mr., Mrs. or Dr. (write Drive in full).",
    "personal": (
        "The register can't show this note as written. Change the "
        "wording, or email the petitioners."
    ),
}
VINEYARD_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")  # fullmatch()
HEADER = (
    '{"type":"FeatureCollection","name":"vineyards","crs":{"type":"name",'
    '"properties":{"name":"urn:ogc:def:crs:EPSG::4269"}},"features":[\n'
)
FOOTER = "\n]}\n"


# What code() puts for the three characters that could end a code span or a
# table's cell, or escape something (public text never holds them).
LOOKALIKES = str.maketrans({"\\": "∖", "`": "ˋ", "|": "｜"})


class SubmissionError(Exception):
    """The submission cannot be read at all (not JSON, wrong shape)."""


# --- text --------------------------------------------------------------------


def clean(value, limit=None):
    """One line of text: NFC, no control or format characters, one space.

    Args:
        value: Anything; non-strings become "".
        limit: Cut to this many characters when given (after cleaning).

    Returns:
        The text.
    """
    if not isinstance(value, str):
        return ""
    out = []
    for ch in unicodedata.normalize("NFC", value):
        kind = unicodedata.category(ch)
        if ch in "\t\r\n" or kind in {"Zs", "Zl", "Zp"}:
            out.append(" ")
        elif kind not in {"Cc", "Cf", "Cs", "Co", "Cn"}:
            out.append(ch)
    text = " ".join("".join(out).split())
    return text[:limit] if limit else text


def public_text_problem(text):
    """Why a public free-text value is refused, or None.

    Public text is posted at once, so it holds only letters, digits and
    plain punctuation: no web address ("web"), nothing else ("characters"),
    no email address or telephone number however written ("contact"), no
    title ("title"), nothing else the vineyard data's privacy rule refuses
    ("personal").

    Args:
        text: clean()'s text.

    Returns:
        The reason's key in NAME_PROBLEMS, or None.
    """
    if WEBBY.search(text):
        return "web"
    if not PUBLIC_TEXT.match(text):
        return "characters"
    if (
        DIGIT_RUN.search(SEPARATORS.sub("", text))
        or privacy.EMAIL.search(text)
        or privacy.PHONE.search(text)
    ):
        return "contact"
    if privacy.TITLE.search(text):
        return "title"
    if places.named(text):
        return "personal"
    return None


def phone_format(text):
    """A US telephone number as (325) 555-0100, or None when it is not one."""
    d = re.sub(r"\D", "", text)
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    if len(d) != 10 or not re.fullmatch(r"[\d\s().+-]*", text):
        return None
    return f"({d[:3]}) {d[3:6]}-{d[6:]}"


# --- geometry ----------------------------------------------------------------


def _q(phi):
    s = math.sin(phi)
    return (1 - E2) * (
        s / (1 - E2 * s * s)
        - (1 / (2 * E)) * math.log((1 - E * s) / (1 + E * s))
    )


QP = _q(math.pi / 2)
RQ = A * math.sqrt(QP / 2)  # the authalic radius


def authalic(lat):
    """The authalic latitude (radians) of a geodetic latitude in degrees."""
    return math.asin(max(-1.0, min(1.0, _q(math.radians(lat)) / QP)))


def plane(ring):
    """A ring on an equal-area plane, in metres.

    The sinusoidal projection of the authalic sphere, centred on the ring's
    mean longitude and its first vertex's latitude: areas on it are areas on
    the ellipsoid.

    Args:
        ring: [(lon, lat)].

    Returns:
        [(x, y)].
    """
    lon0 = sum(p[0] for p in ring) / len(ring)
    b0 = authalic(ring[0][1])
    out = []
    for lon, lat in ring:
        b = authalic(lat)
        out.append((RQ * math.radians(lon - lon0) * math.cos(b), RQ * (b - b0)))
    return out


def area_acres(ring):
    """The area of an open ring of (lon, lat), in acres."""
    if len(ring) < 3:
        return 0.0
    pts = plane(ring)
    s = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1], strict=True):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2 / ACRE_M2


def _orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on(a, b, c):
    return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[
        1
    ] <= max(a[1], b[1])


def segments_meet(a, b, c, d):
    """Whether segments ab and cd touch or cross (planar)."""
    o1 = _orient(a, b, c)
    o2 = _orient(a, b, d)
    o3 = _orient(c, d, a)
    o4 = _orient(c, d, b)
    if ((o1 > 0 > o2) or (o1 < 0 < o2)) and ((o3 > 0 > o4) or (o3 < 0 < o4)):
        return True
    return (
        (o1 == 0 and _on(a, b, c))
        or (o2 == 0 and _on(a, b, d))
        or (o3 == 0 and _on(c, d, a))
        or (o4 == 0 and _on(c, d, b))
    )


def crosses_itself(ring):
    """Whether an open ring's edges cross or touch, or a corner folds back."""
    pts = plane(ring)
    n = len(pts)
    edges = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                # neighbours share a corner: a fold back is a spike
                a, b = edges[i]
                c, d = edges[j]
                shared, p, q = (b, a, d) if j == i + 1 else (a, b, c)
                v1 = (p[0] - shared[0], p[1] - shared[1])
                v2 = (q[0] - shared[0], q[1] - shared[1])
                cross = v1[0] * v2[1] - v1[1] * v2[0]
                dot = v1[0] * v2[0] + v1[1] * v2[1]
                n1 = math.hypot(*v1)
                n2 = math.hypot(*v2)
                if n1 and n2 and abs(cross) <= 1e-9 * n1 * n2 and dot > 0:
                    return True
                continue
            if segments_meet(*edges[i], *edges[j]):
                return True
    return False


def point_in_ring(pt, ring):
    """Even-odd test of a (lon, lat) against an open or closed ring."""
    x, y = pt
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


class Area:
    """A polygon (GeoJSON Polygon or MultiPolygon) to test blocks against."""

    def __init__(self, path):
        """Reads the polygon.

        Args:
            path: A GeoJSON file: a FeatureCollection (its first feature), a
                Feature or a geometry.
        """
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if "features" in data:
            data = data["features"][0]
        geom = data.get("geometry", data)
        polys = (
            [geom["coordinates"]]
            if geom["type"] == "Polygon"
            else geom["coordinates"]
        )
        self.rings = [[tuple(p[:2]) for p in r] for poly in polys for r in poly]
        self.edges = []
        for r in self.rings:
            for a, b in itertools.pairwise(r):
                self.edges.append(
                    (
                        a,
                        b,
                        min(a[0], b[0]),
                        min(a[1], b[1]),
                        max(a[0], b[0]),
                        max(a[1], b[1]),
                    )
                )

    def contains(self, pt):
        """Whether a (lon, lat) is inside (even-odd over every ring)."""
        inside = False
        for r in self.rings:
            if point_in_ring(pt, r):
                inside = not inside
        return inside

    def crossed(self, a, b):
        """Whether the segment ab touches or crosses the area's line."""
        w, s = min(a[0], b[0]), min(a[1], b[1])
        e, n = max(a[0], b[0]), max(a[1], b[1])
        return any(
            ew <= e
            and ee >= w
            and es <= n
            and en >= s
            and segments_meet(a, b, p, q)
            for p, q, ew, es, ee, en in self.edges
        )

    def relation(self, ring):
        """Where an open ring lies against the area: "in", "out" or "both"."""
        flags = {self.contains(p) for p in ring}
        n = len(ring)
        if len(flags) == 2 or any(
            self.crossed(ring[i], ring[(i + 1) % n]) for i in range(n)
        ):
            return "both"
        return "in" if flags == {True} else "out"


def rings_overlap(r1, r2):
    """Whether two open rings of (lon, lat) overlap or touch."""
    n1, n2 = len(r1), len(r2)
    if (
        max(p[0] for p in r1) < min(p[0] for p in r2)
        or max(p[0] for p in r2) < min(p[0] for p in r1)
        or max(p[1] for p in r1) < min(p[1] for p in r2)
        or max(p[1] for p in r2) < min(p[1] for p in r1)
    ):
        return False
    for i in range(n1):
        for j in range(n2):
            if segments_meet(r1[i], r1[(i + 1) % n1], r2[j], r2[(j + 1) % n2]):
                return True
    return point_in_ring(r1[0], r2) or point_in_ring(r2[0], r1)


_AREAS = {}


def area(name, root=ROOT):
    """The Llano Uplift ("llano") or the proposed district ("district").

    Args:
        name: "llano": TTB's proposed Llano Uplift AVA as the site publishes
            it (the copy the function bundles); "district": the proposed
            Hickory Sands District (docs/data/boundary.geojson).
        root: The repository.

    Returns:
        An Area.
    """
    key = (name, root)
    if key not in _AREAS:
        rel = {"llano": LLANO, "district": DISTRICT}[name]
        _AREAS[key] = Area(os.path.join(root, rel))
    return _AREAS[key]


# --- the submission ----------------------------------------------------------


def _number(value):
    """A finite JSON number (never a bool), or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _point(value):
    if not isinstance(value, list) or len(value) != 2:
        return None
    lon, lat = _number(value[0]), _number(value[1])
    if lon is None or lat is None:
        return None
    if not (TEXAS[0] <= lon <= TEXAS[2] and TEXAS[1] <= lat <= TEXAS[3]):
        return None
    return (round(lon, 6), round(lat, 6))


def _ring(value):
    """An open ring of rounded (lon, lat): no repeats, no closing corner."""
    if not isinstance(value, list) or len(value) > LIMITS["corners"] + 1:
        return None
    out = []
    for v in value:
        p = _point(v)
        if p is None:
            return None
        if not out or out[-1] != p:
            out.append(p)
    if len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def loads(text):
    """Strict JSON: at most LIMITS["body_bytes"], no NaN or Infinity.

    Args:
        text: The JSON text.

    Returns:
        The value.

    Raises:
        SubmissionError: Too large, or not strict JSON.
    """
    if len(text.encode("utf-8")) > LIMITS["body_bytes"]:
        raise SubmissionError("too large")

    def refuse(name):
        raise SubmissionError(f"not JSON: {name}")

    try:
        return json.loads(text, parse_constant=refuse)
    except (ValueError, RecursionError) as error:
        raise SubmissionError("not JSON") from error


def _where(raw, errors, root, change=False, listed_rings=()):
    """Step 1-2: the blocks, or a pin (not for a change).

    A change may keep two listed blocks that touch as they are listed
    (listed_rings: the listed vineyard's blocks).

    Returns:
        (blocks, facts, pin, whether any block was sent).
    """

    def as_listed(ring):
        return any(same_ring(ring, r) for r in listed_rings)

    def err(field, message):
        errors.append([field, message])

    blocks = []
    facts = []
    raw_blocks = raw.get("blocks")
    if raw_blocks is None:
        raw_blocks = []
    if not isinstance(raw_blocks, list):
        raise SubmissionError("blocks")
    if len(raw_blocks) > LIMITS["blocks"]:
        err("blocks", f"Send up to {LIMITS['blocks']} blocks at a time.")
        raw_blocks = raw_blocks[: LIMITS["blocks"]]
    llano = area("llano", root)
    for i, rb in enumerate(raw_blocks, 1):
        ring = _ring(rb)
        if ring is None:
            err(f"block-{i}", f"Block {i} could not be read. Start it again.")
            continue
        if len(ring) < 3:
            err(f"block-{i}", f"Block {i} needs at least 3 corners.")
            continue
        if len(ring) > LIMITS["corners"]:
            err(
                f"block-{i}",
                f"Block {i} has more than {LIMITS['corners']} corners. "
                "Use fewer: one at each turn of the edge is enough.",
            )
            continue
        acres = area_acres(ring)
        fact = {"block": i, "corners": len(ring), "acres": round(acres, 2)}
        if crosses_itself(ring):
            err(
                f"block-{i}",
                f"Block {i}'s edges cross. Drag a corner so they don't, "
                "or start the block again.",
            )
        elif acres < LIMITS["block_min_acres"]:
            err(f"block-{i}", f"Block {i} is very small. Check its corners.")
        elif acres > LIMITS["block_max_acres"]:
            err(
                f"block-{i}",
                f"Block {i} is very large. Draw just the vines, "
                "not the whole property.",
            )
        if llano.relation(ring) != "in":
            err(
                f"block-{i}",
                f"Block {i} is outside the area this register covers "
                "(the proposed Llano Uplift AVA). Check that the map is "
                "on your vineyard.",
            )
        fact["district"] = area("district", root).relation(ring)
        blocks.append(ring)
        facts.append(fact)
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            kept = (
                as_listed(blocks[i])
                and as_listed(blocks[j])
                and not same_ring(blocks[i], blocks[j])
            )
            if rings_overlap(blocks[i], blocks[j]) and not kept:
                err(
                    f"block-{j + 1}",
                    f"Blocks {i + 1} and {j + 1} overlap. "
                    "Move a corner so they don't.",
                )
    if sum(f["acres"] for f in facts) > LIMITS["total_max_acres"]:
        err(
            "blocks",
            "The blocks add up to too many acres. Draw just the vines.",
        )
    pin = None
    if raw.get("pin") is not None:
        pin = _point(raw.get("pin"))
        if pin is None or not llano.contains(pin):
            err(
                "pin",
                "The pin is outside the area this register covers (the "
                "proposed Llano Uplift AVA). Move it onto your vineyard.",
            )
            pin = None
    if change and not raw_blocks:
        err(
            "where",
            "A change needs the vineyard's blocks drawn, not a pin: keep "
            "one block or more.",
        )
    elif not raw_blocks and raw.get("pin") is None:
        err("where", "Draw your blocks, or drop a pin on the vineyard.")
    return blocks, facts, pin, bool(raw_blocks)


def _vineyard(raw, v, has_blocks, errors, year):
    """Step 3: about the vineyard. Returns the cleaned vineyard."""

    def err(field, message):
        errors.append([field, message])

    name = clean(v.get("name"))
    if not name:
        err("name", "Type the vineyard's name.")
    elif len(name) > LIMITS["name"]:
        err("name", f"Shorten the name to {LIMITS['name']} letters or fewer.")
    else:
        problem = public_text_problem(name)
        if problem:
            err("name", NAME_PROBLEMS[problem])
    county = clean(v.get("county"))
    if county not in COUNTIES:
        err("county", "Pick the county.")
    planted = v.get("planted")
    if planted not in ("planted", "planned"):
        err("planted", "Choose planted or planned.")
    acres = None
    if v.get("acres") is not None and v.get("acres") != "":
        acres = _number(v.get("acres"))
        if acres is None or not 0 < acres <= LIMITS["acres_max"]:
            err("acres", "Type the acres as a number, like 12 or 4.5.")
            acres = None
        else:
            acres = round(acres, 2)
    if (
        not has_blocks
        and raw.get("pin") is not None
        and acres is None
        and not any(e[0] == "acres" for e in errors)
    ):
        err(
            "acres",
            "Type about how many acres are planted, so the petitioners can "
            "draw the vineyard.",
        )
    plant_year = v.get("year")
    if isinstance(plant_year, float) and plant_year.is_integer():
        plant_year = int(plant_year)  # JSON has one kind of number
    if plant_year is not None and (
        isinstance(plant_year, bool)
        or not isinstance(plant_year, int)
        or not LIMITS["year_min"] <= plant_year <= year + LIMITS["year_ahead"]
    ):
        err("year", "Pick a year from the list.")
        plant_year = None
    varieties = []
    raw_v = v.get("varieties")
    if raw_v is None:
        raw_v = []
    if not isinstance(raw_v, list):
        raise SubmissionError("varieties")
    for item in raw_v[: LIMITS["varieties"] + 1]:
        text = clean(item, LIMITS["variety"] + 1)
        if not text or text in varieties:
            continue
        if text not in VARIETIES and (
            len(text) > LIMITS["variety"] or public_text_problem(text)
        ):
            err(
                "varieties",
                f"Check the other varieties: only names of grapes, each "
                f"under {LIMITS['variety']} letters, with no phone numbers "
                "or web addresses.",
            )
            continue
        varieties.append(text)
    if len(varieties) > LIMITS["varieties"]:
        err("varieties", f"Pick up to {LIMITS['varieties']} varieties.")
        varieties = varieties[: LIMITS["varieties"]]
    return {
        "name": name[: LIMITS["name"]],
        "county": county if county in COUNTIES else "",
        "planted": planted if planted in ("planted", "planned") else "",
        "acres": acres,
        "year": plant_year,
        "varieties": varieties,
    }


def _contact(c, errors):
    """Step 4: how to reach the sender (private). Returns the contact."""

    def err(field, message):
        errors.append([field, message])

    who = clean(c.get("name"))
    email = clean(c.get("email"))
    phone_raw = clean(c.get("phone"))
    if not who:
        err("contact-name", "Type your name, so we know who to reply to.")
    elif len(who) > LIMITS["contact_name"] or not PERSON_TEXT.match(who):
        err("contact-name", "Type just your name, in letters.")
    if email and (len(email) > LIMITS["email"] or not EMAIL.match(email)):
        err(
            "contact-email",
            "Check the email address. It looks like name@example.com.",
        )
    phone = None
    if phone_raw:
        phone = phone_format(phone_raw)
        if phone is None or len(phone_raw) > LIMITS["phone"]:
            err(
                "contact-phone",
                "Check the phone number: 10 digits, like 325 555 0100.",
            )
    if not email and not phone_raw:
        err(
            "contact-email",
            "Give an email address or a phone number, so we can reach you.",
        )
    return {"name": who, "email": email, "phone": phone or ""}


def _change(raw, known, errors):
    """Step 3 of a change: the vineyard it changes, and the note.

    Returns:
        (changes, note): the listed vineyard's id (None when it is not
        one), and the cleaned note.
    """

    def err(field, message):
        errors.append([field, message])

    vid = raw.get("changes") if isinstance(raw.get("changes"), str) else ""
    changes = vid if VINEYARD_ID.fullmatch(vid) and vid in known else None
    if changes is None:
        err(
            "changes",
            "This vineyard can't be changed from this page just now. Email "
            "the petitioners instead.",
        )
    note = clean(raw.get("note"))
    if not note:
        err("note", "Say in a few words what changed.")
    elif len(note) > LIMITS["note"]:
        err("note", f"Shorten the note to {LIMITS['note']} letters or fewer.")
    else:
        problem = public_text_problem(note)
        if problem:
            err("note", NOTE_PROBLEMS[problem])
    return changes, note[: LIMITS["note"]]


def listed_vineyards(root=ROOT):
    """The listed vineyards by id, as docs/assets/vineyards/known.json.

    Made from the vineyard file itself (places.known()), so the check
    always compares with the repository's current data.

    Args:
        root: The repository.

    Returns:
        {id: {"name", "category", "year", "varieties", "blocks"}}.
    """
    return places.known(existing_vineyards(root))


def check(raw, year=None, root=ROOT, known=None):
    """Checks a submission the way the page and the function do.

    Args:
        raw: The parsed JSON.
        year: This year (the default: now, UTC).
        root: The repository (where the areas are read from).
        known: The listed vineyards by id, which a change must name (the
            default: listed_vineyards(root), read only for a change).

    Returns:
        (submission, errors, facts): the cleaned submission (what the issue
        and the table get); errors as [field, plain-language message] in
        the order of the form; facts about the blocks for the page: each
        block's acres, corners and place against the proposed district.

    Raises:
        SubmissionError: Not an object of this form and version, or the trap was
            filled ("trap").
    """
    if not isinstance(raw, dict) or raw.get("form") != FORM:
        raise SubmissionError("not a vineyard submission")
    version = raw.get("version")
    if isinstance(version, bool) or version not in (VERSION, CHANGE_VERSION):
        raise SubmissionError("an unknown version")
    change = version == CHANGE_VERSION
    sid = raw.get("id")
    if not isinstance(sid, str) or not UUID4.match(sid):
        raise SubmissionError("no submission id")
    year = year or datetime.datetime.now(datetime.UTC).year
    errors = []
    v = raw.get("vineyard") if isinstance(raw.get("vineyard"), dict) else {}
    c = raw.get("contact") if isinstance(raw.get("contact"), dict) else {}
    agree = raw.get("agree") if isinstance(raw.get("agree"), dict) else {}
    listed_rings = ()
    if change:
        if known is None:
            known = listed_vineyards(root)
        target = raw.get("changes")
        if isinstance(target, str) and target in known:
            listed_rings = known[target].get("blocks") or ()
    blocks, facts, pin, has_blocks = _where(
        raw, errors, root, change, listed_rings
    )
    vineyard = _vineyard(raw, v, has_blocks, errors, year)
    if change:
        changes, note = _change(raw, known, errors)
    contact = _contact(c, errors)
    # 5. the two boxes, and the trap
    if agree.get("permission") is not True:
        errors.append(["agree-permission", "Tick this box to send."])
    if agree.get("public") is not True:
        errors.append(["agree-public", "Tick this box to send."])
    if raw.get("website") is not None and raw.get("website") != "":
        raise SubmissionError("trap")
    submission = {
        "form": FORM,
        "version": CHANGE_VERSION if change else VERSION,
        "id": sid,
        **({"changes": changes, "note": note} if change else {}),
        "vineyard": vineyard,
        "blocks": [[list(p) for p in r] for r in blocks],
        "pin": list(pin) if pin else None,
        "contact": contact,
    }
    return submission, errors, facts


# --- the issue (the function writes it; the contact is never in it) ---------


def code(text):
    """Text a stranger typed, safe in a Markdown table cell.

    A code span, so nothing in it is a link, a mention, HTML or formatting;
    a backslash, a backtick and a pipe become lookalikes, so nothing is
    escaped and nothing can end the span or the cell.

    Args:
        text: The text.

    Returns:
        The cell's Markdown.
    """
    text = clean(text).translate(LOOKALIKES)
    return f"`{text}`" if text else "_not given_"


def js_numbers(value):
    """Floats that are whole numbers as ints, so JSON matches JavaScript's."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [js_numbers(v) for v in value]
    if isinstance(value, dict):
        return {k: js_numbers(v) for k, v in value.items()}
    return value


def safe_json(value):
    """Compact JSON that cannot end a Markdown code fence or hold HTML."""
    text = json.dumps(
        js_numbers(value), ensure_ascii=False, separators=(",", ":")
    )
    for c, e in (
        ("&", "\\u0026"),
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("`", "\\u0060"),
    ):
        text = text.replace(c, e)
    return text


def public(submission, sent):
    """The submission without the contact or its id: what the issue holds."""
    keys = ("form", "version", "vineyard", "blocks", "pin")
    if submission["version"] == CHANGE_VERSION:
        keys = ("form", "version", "changes", "note", *keys[2:])
    out = {k: submission[k] for k in keys}
    out["sent"] = sent
    if submission.get("outline"):
        out["outline"] = submission["outline"]  # drawn by the petitioners
    return out


def issue_title(submission, listed=None):
    """A neutral title: nothing a stranger typed.

    Args:
        submission: check()'s submission.
        listed: For a change, the listed vineyard (listed_vineyards()'s
            entry): its name as the site lists it.

    Returns:
        "Vineyard change: <listed name>", or "Vineyard submission" and the
        county when it is one of the list.
    """
    if listed:
        return f"Vineyard change: {clean(listed['name'])}"
    county = submission["vineyard"]["county"]
    if county in places.COUNTIES:
        return f"Vineyard submission, {county} County"
    return "Vineyard submission"


def _blocks_text(n, drawn):
    return f"{n} block{_s(n)}" + (" drawn" if drawn else "")


def _ring_feature(ring, props):
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Polygon", "coordinates": [[*ring, ring[0]]]},
    }


def change_body(submission, sent, listed):
    """A change's public issue: the listing beside the suggestion.

    Both outlines are on the issue's map: the blocks listed now grey, the
    suggested ones gold (GitHub draws the simplestyle colours).

    Args:
        submission: check()'s cleaned change.
        sent: When it was sent (as issue_body()).
        listed: The listed vineyard (listed_vineyards()'s entry).

    Returns:
        Markdown.
    """
    v = submission["vineyard"]
    planted = {"planted": "Planted", "planned": "Planned"}
    old_year = "" if listed.get("year") is None else str(listed["year"])
    old_planted = (
        "Planned" if listed["category"] == "under-development" else "Planted"
    )
    acres = "" if v["acres"] is None else f"{js_numbers(v['acres'])}"
    year = "" if v["year"] is None else str(v["year"])
    not_listed = "_not listed_"
    rows = [
        ("Vineyard", code(listed["name"]), code(v["name"])),
        ("County", not_listed, code(v["county"])),
        (
            "Planted or planned",
            code(old_planted),
            code(planted.get(v["planted"], "")),
        ),
        ("Acres planted (as given)", not_listed, code(acres)),
        ("Year first planted", code(old_year), code(year)),
        (
            "Varieties",
            code(", ".join(listed.get("varieties") or [])),
            code(", ".join(v["varieties"])),
        ),
        (
            "Where",
            code(_blocks_text(len(listed["blocks"]), False)),
            code(_blocks_text(len(submission["blocks"]), True)),
        ),
    ]

    def look(listing, colour):
        return {"listing": listing, "stroke": colour, "fill": colour}

    feats = [
        _ring_feature(r, {"block": i, **look("listed now", "#6e7781")})
        for i, r in enumerate(listed["blocks"], 1)
    ] + [
        _ring_feature(r, {"block": i, **look("suggested", "#bf8700")})
        for i, r in enumerate(submission["blocks"], 1)
    ]
    lines = [
        MARK,
        (
            "A change to a vineyard listed on hickorysandsdistrictava.org,"
            " sent through its form, as the sender typed it. Nothing on the"
            " site changes until the petitioners have checked it. The"
            " sender's contact details are kept privately, not here."
        ),
        "",
        f"| | Listed now (`{submission['changes']}`) | Suggested |",
        "|---|---|---|",
        *[f"| {k} | {a} | {b} |" for k, a, b in rows],
        f"| What changed (the sender's note) | | {code(submission['note'])} |",
        f"| Sent | | {code(sent[:16].replace('T', ' ') + ' UTC')} |",
        "",
        "The map: the blocks listed now in grey, the suggested blocks in gold.",
        "",
        "```geojson",
        safe_json({"type": "FeatureCollection", "features": feats}),
        "```",
        "",
        "<details><summary>The submission's data, read by the check</summary>",
        "",
        "```json",
        safe_json(public(submission, sent)),
        "```",
        "",
        "</details>",
    ]
    return "\n".join(lines) + "\n"


def issue_body(submission, sent, listed=None):
    """The public issue: the fixed layout, with no contact details.

    Args:
        submission: check()'s cleaned submission (its contact and id are
            never written).
        sent: When it was sent, ISO 8601 UTC with milliseconds, as
            JavaScript's toISOString() writes it.
        listed: For a change, the listed vineyard it changes
            (listed_vineyards()'s entry): change_body().

    Returns:
        Markdown.
    """
    if submission["version"] == CHANGE_VERSION and listed:
        return change_body(submission, sent, listed)
    v = submission["vineyard"]
    n = len(submission["blocks"])
    if not n:
        where = "a pin (no outline drawn)"
    elif submission.get("outline") == "petitioner":
        where = f"{n} block{'s' if n != 1 else ''} drawn by the petitioners"
    else:
        where = f"{n} block{'s' if n != 1 else ''} drawn"
    acres = "" if v["acres"] is None else f"{js_numbers(v['acres'])}"
    planted = {"planted": "Planted", "planned": "Planned"}.get(v["planted"], "")
    year = "" if v["year"] is None else str(v["year"])
    rows = [
        ("Vineyard", code(v["name"])),
        ("County", code(v["county"])),
        ("Planted or planned", code(planted)),
        ("Acres planted (as given)", code(acres)),
        ("Year first planted", code(year)),
        ("Varieties", code(", ".join(v["varieties"]))),
        ("Where", code(where)),
        ("Sent", code(sent[:16].replace("T", " ") + " UTC")),
    ]
    feats = [
        {
            "type": "Feature",
            "properties": {"block": i},
            "geometry": {"type": "Polygon", "coordinates": [[*r, r[0]]]},
        }
        for i, r in enumerate(submission["blocks"], 1)
    ]
    if submission["pin"]:
        feats.append(
            {
                "type": "Feature",
                "properties": {"pin": True},
                "geometry": {"type": "Point", "coordinates": submission["pin"]},
            }
        )
    lines = [
        MARK,
        (
            "A vineyard sent through the form on hickorysandsdistrictava.org,"
            " as the sender typed it. Nothing is shown on the site until the"
            " petitioners have checked it. The sender's contact details are"
            " kept privately, not here."
        ),
        "",
        "| | |",
        "|---|---|",
        *[f"| {k} | {val} |" for k, val in rows],
        "",
        "```geojson",
        safe_json({"type": "FeatureCollection", "features": feats}),
        "```",
        "",
        "<details><summary>The submission's data, read by the check</summary>",
        "",
        "```json",
        safe_json(public(submission, sent)),
        "```",
        "",
        "</details>",
    ]
    return "\n".join(lines) + "\n"


# --- the check, in the repository's Actions -----------------------------------


def parse_issue(body):
    """The submission's public data, read back from an issue body.

    Args:
        body: The issue's body.

    Returns:
        The data block's dict (the submission without its contact and id,
        with "sent").

    Raises:
        SubmissionError: The body is not the form's layout.
    """
    if not isinstance(body, str) or MARK not in body:
        raise SubmissionError("not a vineyard submission")
    # GitHub's editor saves an edited body with CRLF line ends
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    found = re.findall(r"```json\n(.*?)\n```", body, re.DOTALL)
    if len(found) != 1:
        raise SubmissionError("not one data block")
    data = loads(found[0])
    if not isinstance(data, dict):
        raise SubmissionError("data")
    return data


def existing_vineyards(root=ROOT):
    """The features of the vineyard file."""
    with open(os.path.join(root, VINEYARDS), encoding="utf-8") as fh:
        return json.load(fh)["features"]


def wells_near(rings, root=ROOT):
    """How many TWDB wells lie within the 3D page's radius of the blocks.

    Counted from the committed well tiles, as src/site/make_vineyards.py
    counts them for the blocks' popups.

    Args:
        rings: Open rings of (lon, lat).
        root: The repository.

    Returns:
        The number of wells near any of the blocks.
    """
    wells, draw = places.tile_wells(os.path.join(root, WELLS))
    found = set()
    for ring in rings:
        closed = [[list(p) for p in ring] + [list(ring[0])]]
        for row in places.near_wells(closed, wells, draw):
            found.add(row[1])
    return len(found)


def category(submission, facts):
    """The vineyard's category, and whether a block straddles the line.

    Args:
        submission: check()'s submission.
        facts: check()'s facts.

    Returns:
        (category, straddles): planned is "under-development"; planted
        with every block in the proposed district is "hsd", outside it
        "llano-uplift"; across the line, the category of most of the acres,
        with straddles True. "historical" is never chosen here.
    """
    if submission["vineyard"]["planted"] == "planned":
        return "under-development", False
    where = {f["district"] for f in facts}
    if where == {"in"}:
        return "hsd", False
    if where == {"out"} or not where:
        return "llano-uplift", False
    inside = sum(f["acres"] for f in facts if f["district"] == "in")
    outside = sum(f["acres"] for f in facts if f["district"] == "out")
    return ("hsd" if inside >= outside else "llano-uplift"), True


def source_text(number, date, outline=None):
    """The source note of a block added from issue #number."""
    drawn = (
        "drawn by the petitioners on Esri World Imagery from the sender's pin"
        if outline == "petitioner"
        else "drawn by the sender on Esri World Imagery"
    )
    return (
        f"Sent through the website's vineyard form (GitHub issue #{number}) "
        f"and checked by the petitioner, {date}; {drawn}."
    )


def _s(n):
    return "" if n == 1 else "s"


def change_source_text(number, date):
    """The source note of a block a change from issue #number drew anew."""
    return (
        "Changed through the website's vineyard form (GitHub issue "
        f"#{number}) and checked by the petitioner, {date}; drawn by the "
        "sender on Esri World Imagery."
    )


def kept_source_text(source, number, date):
    """The source of a block a change kept, with the change noted once."""
    base = re.sub(
        r" Updated through the website's vineyard form \(GitHub issue #\d+\)"
        r"[^.]*\.$",
        "",
        source or "",
    )
    return (
        f"{base} Updated through the website's vineyard form (GitHub issue "
        f"#{number}) and checked by the petitioner, {date}."
    ).strip()


def _key(ring):
    return [f"{p[0]:.6f},{p[1]:.6f}" for p in ring]


def same_ring(a, b):
    """Whether two open rings are the same block: any start, either way.

    Compared to the 6 decimal places a submission keeps, as the rules'
    sameRing() compares them.
    """
    a, b = _key(a), _key(b)
    if len(a) != len(b) or not a:
        return False
    for ring in (a, a[::-1]):
        for k in range(len(ring)):
            if ring[k:] + ring[:k] == b:
                return True
    return False


def compare(target, sub, cat):
    """The listed vineyard beside a change, for the check's comment.

    Args:
        target: The listed vineyard (listed_vineyards()'s entry).
        sub: check()'s change.
        cat: The category it would take.

    Returns:
        (Markdown table lines, whether anything would change).
    """
    v = sub["vineyard"]
    labels = dict(places.CATEGORIES)
    kept = sum(
        any(same_ring(r, old) for old in target["blocks"])
        for r in sub["blocks"]
    )

    def acres(rings):
        return sum(area_acres([tuple(p) for p in r]) for r in rings)

    def year(value):
        return "" if value is None else str(value)

    rows = [
        ("Name", code(target["name"]), code(v["name"])),
        (
            "Category",
            f"{labels[target['category']]} (`{target['category']}`)",
            f"{labels[cat]} (`{cat}`)",
        ),
        (
            "Year first planted",
            code(year(target["year"])),
            code(year(v["year"])),
        ),
        (
            "Varieties",
            code(", ".join(target["varieties"])),
            code(", ".join(v["varieties"])),
        ),
        (
            "Blocks",
            (
                f"{len(target['blocks'])}, {acres(target['blocks']):.2f} acres "
                "of outline"
            ),
            (
                f"{len(sub['blocks'])}, {acres(sub['blocks']):.2f} acres of "
                f"outline; {kept} drawn as listed"
            ),
        ),
    ]
    changed = (
        target["name"] != v["name"]
        or target["category"] != cat
        or target["year"] != v["year"]
        or target["varieties"] != v["varieties"]
        or kept != len(sub["blocks"])
        or kept != len(target["blocks"])
    )
    lines = [
        "| | Listed now | Suggested |",
        "|---|---|---|",
        *[f"| {k} | {a} | {b} |" for k, a, b in rows],
        f"| What changed (the sender's note) | | {code(sub['note'])} |",
    ]
    return lines, changed


def not_layout(reason):
    """The check's comment on an issue that is not in the form's layout."""
    return (
        "\n".join(
            [
                CHECK_MARK,
                "### The check: this is not the form's layout",
                "",
                f"It could not be read ({reason}). Close it as not planned.",
            ]
        )
        + "\n"
    )


def review(data, number, others=(), private_words=(), today=None, root=ROOT):
    """The check the Action posts on a submission's issue.

    Args:
        data: parse_issue()'s data.
        number: The issue's number.
        others: The other open submissions' vineyard names, as (number,
            name) pairs.
        private_words: The private-words list, when the Action has it (an
            Actions secret); a match is never shown.
        today: The date for the source text (YYYY-MM-DD; default today).
        root: The repository.

    Returns:
        (markdown, ok, result): the comment; whether it can be approved as
        it is; and what add_blocks() needs, or None when it cannot be read.
    """
    today = today or datetime.datetime.now(datetime.UTC).date().isoformat()
    raw = {k: data.get(k) for k in ("form", "version", "vineyard", "blocks")}
    raw.update(
        pin=data.get("pin"),
        id="00000000-0000-4000-8000-000000000000",  # never in the issue
        contact={"name": "Checked", "email": "check@example.com"},
        agree={"public": True, "permission": True},
    )
    for key in ("changes", "note"):
        if key in data:
            raw[key] = data[key]
    listed = listed_vineyards(root)
    try:
        sub, errors, facts = check(raw, root=root, known=listed)
    except SubmissionError as error:
        return not_layout(error), False, None
    outline = (
        data.get("outline") if data.get("outline") == "petitioner" else None
    )
    sub["outline"] = outline
    errors = [e for e in errors if not e[0].startswith(("contact", "agree"))]
    v = sub["vineyard"]
    change = sub["version"] == CHANGE_VERSION
    target_id = sub.get("changes")
    target = listed.get(target_id) if change and target_id else None
    if change and not target_id:
        errors = [e for e in errors if e[0] != "changes"]
        errors.append(
            [
                "changes",
                (
                    "The vineyard this changes is not in the vineyard file (it "
                    "may have been renamed or removed since): decline this, or "
                    "make the change by hand."
                ),
            ]
        )
    cat, straddles = category(sub, facts)
    if target and target["category"] == "historical":
        cat, straddles = "historical", False  # the form never chooses it
    notes = []
    known = [
        f
        for f in existing_vineyards(root)
        if not (change and f["properties"].get("vineyard_id") == target_id)
    ]
    same = [
        f
        for f in known
        if f["properties"]["name"].casefold() == v["name"].casefold()
    ]
    if same:
        notes.append(
            f"A vineyard of this name is already on the map ({len(same)} "
            f"block{_s(len(same))}): an update, to be made by hand, not an "
            "addition."
        )
    twins = sorted(
        n
        for n, name in others
        if n != number and name.casefold() == v["name"].casefold()
    )
    if twins:
        notes.append(
            "Another open submission has this name: "
            + ", ".join(f"#{n}" for n in twins)
            + ". Close the extra one, or say why both are wanted, before "
            "approving either."
        )
    overlaps = []
    for i, ring in enumerate(sub["blocks"], 1):
        for f in known:
            other = [tuple(p) for p in f["geometry"]["coordinates"][0][:-1]]
            if rings_overlap([tuple(p) for p in ring], other):
                b = f["properties"].get("block")
                overlaps.append(
                    f"block {i} overlaps {f['properties']['name']}"
                    + (f", block {b}" if b else "")
                )
    if overlaps:
        notes.append("Already on the map: " + "; ".join(overlaps) + ".")
    if straddles:
        notes.append(
            "A block crosses the proposed district's line: the category "
            "follows most of the acres "
            f"({dict(places.CATEGORIES)[cat]}). Change it in the pull "
            "request if that is wrong."
        )
    words = [w for w in private_words if w.strip()]
    public_words = [v["name"], *v["varieties"], sub.get("note") or ""]
    if words and places.named(" ".join(public_words), words):
        errors.append(
            ["name", "A public field holds a word on the private list."]
        )
    if not sub["blocks"] and not change:
        notes.append(
            "No outline: only a pin. The petitioners draw the blocks from "
            "imagery and put them into the data block above before approving "
            "(src/vineyards/SETUP.md, A pin with no outline)."
        )
    compared = []
    if target:
        compared, changed = compare(target, sub, cat)
        if not changed:
            notes.append(
                "Nothing would change: the suggestion is what is listed now."
            )
    ok = (
        not errors
        and not same
        and not twins
        and not overlaps
        and bool(sub["blocks"])
        and (not change or (target is not None and changed))
    )
    head = (
        "### The check: ready for review"
        if ok
        else "### The check: something to look at"
    )
    lines = [CHECK_MARK, head, ""]
    if target:
        lines += [
            (
                f"A change to **{code(target['name'])}** (`{target_id}`), "
                "compared with the vineyard file as it is now:"
            ),
            "",
            *compared,
            "",
        ]
    if facts:
        word = {"in": "yes", "out": "no", "both": "partly: it crosses the line"}
        lines += [
            (
                "| Block | Corners | Acres of outline | "
                "In the proposed Hickory Sands District |"
            ),
            "|---|---|---|---|",
            *[
                f"| {f['block']} | {f['corners']} | {f['acres']:.2f} | "
                f"{word[f['district']]} |"
                for f in facts
            ],
            "",
        ]
        total = sum(f["acres"] for f in facts)
        given = (
            ""
            if v["acres"] is None
            else f"; the sender gave {js_numbers(v['acres'])} acres planted"
        )
        lines.append(f"- The outlines add up to {total:.2f} acres{given}.")
    outside = any("Llano Uplift" in e[1] for e in errors)
    lines.append(
        "- Inside TTB's proposed Llano Uplift AVA: "
        + ("no (see below)." if outside else "yes.")
    )
    if sub["blocks"] and target:
        n = len(sub["blocks"])
        lines.append(
            f"- If approved, the {len(target['blocks'])} listed "
            f"block{_s(len(target['blocks']))} and the fields of "
            f"`{target_id}` are replaced by these {n} block{_s(n)}, as "
            f"**{dict(places.CATEGORIES)[cat]}** (`{cat}`); a block drawn "
            "as it is listed keeps its source, with a note of this change "
            "added; a new block gets the source "
            f"“{change_source_text(number, today)}”"
        )
    elif sub["blocks"]:
        n = len(sub["blocks"])
        lines.append(
            f"- If approved, it is added as **{dict(places.CATEGORIES)[cat]}** "
            f"(`{cat}`), {n} block{_s(n)}, with the source "
            f"“{source_text(number, today, outline)}”"
        )
        lines.append(
            f"- TWDB wells within {places.WELLS_M / 1000:g} km of the blocks: "
            f"{wells_near(sub['blocks'], root)} (listed in the blocks' "
            "popups on The water)."
        )
    lines.append(
        "- Public fields: no web address, email address, telephone number "
        "or title"
        + (
            "; the private list was checked."
            if words
            else "; the private list was not available."
        )
    )
    if errors or notes:
        lines += ["", "#### To look at", ""]
        lines += [f"- {m}" for _, m in errors] + [f"- {m}" for m in notes]
    what = (
        f"replaces the vineyard's blocks and fields in `{VINEYARDS}` and"
        " makes the site's vineyard data again"
        if change
        else f"adds the blocks to `{VINEYARDS}` and the site's vineyard data"
    )
    lines += [
        "",
        (
            f"To approve, add the label `approved`: a pull request then {what}."
            " To decline, close this as not planned. The sender's contact"
            " details are kept privately, not here."
        ),
    ]
    result = {
        "submission": sub,
        "facts": facts,
        "category": cat,
        "outline": outline,
        "changes": target_id if change else None,
    }
    return "\n".join(lines) + "\n", ok, result


# --- the vineyard file (the pull request) -------------------------------------


def sort_key(feature):
    """The vineyard file's order: by category, then name."""
    p = feature["properties"]
    order = [c for c, _ in places.CATEGORIES]
    return (order.index(p["category"]), p["name"].casefold())


def feature_line(feature):
    """One feature as the file writes it (Python's JSON, one per line)."""
    return json.dumps(feature, ensure_ascii=False, separators=(",", ":"))


def _signed(closed):
    pairs = itertools.pairwise(closed)
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in pairs) / 2


def add_blocks(result, number, today=None, root=ROOT, extra_words=()):
    """The vineyard file with the approved blocks added, and its diff.

    The file keeps its own layout: its header, one feature per line in
    Python's compact JSON, sorted by category then name (stable, so blocks
    keep their order), rings clockwise. A block's number is written the way
    the file writes them (text when any block is text). The new features
    also keep the year first planted and the varieties, as given. A new
    vineyard gets a new vineyard_id, a slug of its name not yet taken.

    A change (result["changes"], a vineyard_id) replaces that vineyard's
    blocks instead, never adding a second entry: every block it had goes,
    and the change's blocks come in with its fields and the same id. A
    block drawn as it was listed keeps its outline, label, acres and
    source, with the change noted in the source (kept_source_text()); a
    new one gets the next free label and change_source_text().

    Args:
        result: review()'s result.
        number: The issue's number.
        today: The date for the source text (default today, UTC).
        root: The repository.
        extra_words: More words never to publish (the private lists).

    Returns:
        (new text, unified diff).

    Raises:
        SystemExit: A new block's fields name someone or give a contact, or
            the vineyard a change names is not in the file.
    """
    today = today or datetime.datetime.now(datetime.UTC).date().isoformat()
    path = os.path.join(root, VINEYARDS)
    with open(path, encoding="utf-8") as fh:
        old = fh.read()
    features = json.loads(old)["features"]
    as_text = any(
        isinstance(f["properties"].get("block"), str) for f in features
    )
    sub = result["submission"]
    v = sub["vineyard"]
    changes = result.get("changes")
    if changes:
        olds = [
            f for f in features if f["properties"].get("vineyard_id") == changes
        ]
        if not olds:
            raise SystemExit(f"no vineyard {changes} in the vineyard file")
        features = [f for f in features if f not in olds]
        vid = changes
    else:
        olds = []
        taken = {f["properties"].get("vineyard_id") for f in features}
        base = places.slug(v["name"])
        vid, k = base, 1
        while vid in taken:
            k += 1
            vid = f"{base[: places.ID_MAX - 1 - len(str(k))]}-{k}"
    labels = []  # the blocks' labels, kept or new
    blocks = []
    for ring in sub["blocks"]:
        was = next(
            (
                f
                for f in olds
                if same_ring(ring, f["geometry"]["coordinates"][0][:-1])
            ),
            None,
        )
        blocks.append((ring, was))
        if was is not None:
            labels.append(was["properties"].get("block"))
    for i, (ring, was) in enumerate(blocks, 1):
        if was is not None:
            closed = was["geometry"]["coordinates"][0]
            label = was["properties"].get("block")
            acres = was["properties"].get("acres")
            source = kept_source_text(
                was["properties"].get("source"), number, today
            )
        else:
            closed = [list(p) for p in ring] + [list(ring[0])]
            if _signed(closed) > 0:  # the file's rings run clockwise
                closed.reverse()
            n = i if not changes else 1
            while changes and (str(n) in map(str, labels)):
                n += 1
            labels.append(str(n) if as_text else n)
            label = labels[-1]
            acres = round(area_acres([tuple(p) for p in ring]), 2)
            source = (
                change_source_text(number, today)
                if changes
                else source_text(number, today, result.get("outline"))
            )
        props = {
            "name": v["name"],
            "vineyard_id": vid,
            "category": result["category"],
            "block": label,
            "acres": acres,
            "year": v["year"],
            "varieties": list(v["varieties"]),
            "source": source,
        }
        places.checked(props, f"issue #{number} block {i}", extra_words)
        features.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": {"type": "Polygon", "coordinates": [closed]},
            }
        )
    features.sort(key=sort_key)
    new = HEADER + ",\n".join(feature_line(f) for f in features) + FOOTER
    diff = "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            f"a/{VINEYARDS}",
            f"b/{VINEYARDS}",
            n=1,
        )
    )
    return new, diff
