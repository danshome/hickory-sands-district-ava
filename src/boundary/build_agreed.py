"""The Hickory Sands District boundary as proposed to TTB after the Oct. 15, 2026 call.

Text: TTB's published regulatory text (Notice No. 243, 91 FR 52576) word for word, except the area near Grit, which uses
the petition's own wording (Feb. 2, 2023; petition steps 11-12 and 91-98, lane wording included), with two departures:
  - steps (93)-(96) are new: they replace petition step 94 (the straight line from the marked 1737 to the marked 1762)
    and go around a lobe of granite by a windmill and Topaz Lane;
  - step (90) (petition step 91) names the unnamed, intermittent tributary the petition's line follows from Honey Creek
    to the marked 1727 (flagged), and steps (90)-(91) name the roads as TTB's text names them (flagged).
Outside the area near Grit, two corrections to TTB's own wording, flagged (Dan, Oct. 17, 2026; issue #38), text only:
  - step (85) "to the marked 1,802-foot summit": the Turtle Creek map prints x1802 at the summit (TTB's text: 1,801);
  - step (49) "to the marked 1,586-foot elevation point": "-foot", as everywhere else in TTB's text (TTB's: 1,586-elevation).
Geometry: the option 2 ring (petition route, granite-lobe detour, tributary) with the highway passes drawn 30 m either
side of the road center line (westbound lane NE, eastbound lane SW), per TTB, so the line is visible beside the road;
the narrative is unchanged by the offset. Ring: resources/boundary/proposed/proposed-ring.json (built in QGIS from option 2, see README), with the
steps that follow a road, creek or contour replaced by traces onto the centre of the ink on the USGS sheets
(ink-centerline-steps.geojson, usgs-quad-trace skill; NO_SPLICE=1 to build without them).
Attributes: TTB's AVAs_Production fields filled as TTB fills them for an established AVA where the value is known.
"""

import json, math, os, re, sys

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)  # the repository root
HERE = os.environ.get("HSD_WORK") or os.path.join(
    ROOT, "target", "work"
)  # build work dir (build.sh stages resources/ here)
sys.path.insert(0, os.path.join(ROOT, "src", "boundary"))
from osgeo import ogr, osr

ogr.UseExceptions()
import ttb_record, ttb_schema_layers as tsl

B = os.path.join(
    ROOT, "resources", "boundary"
)  # the inputs (see resources/boundary/README.md)
LL = osr.SpatialReference()
LL.ImportFromEPSG(4269)
LL.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
d = lambda a, b: math.hypot((a[0] - b[0]) * 95700, (a[1] - b[1]) * 110900)


def geo(g):
    h = g.Clone()
    h.AssignSpatialReference(LL)
    return h


def glen(c):
    g = ogr.CreateGeometryFromJson(
        json.dumps({"type": "LineString", "coordinates": c})
    )
    g.AssignSpatialReference(LL)
    return g.GeodesicLength()


R = json.load(open(os.path.join(B, "proposed", "proposed-ring.json")))
ring = [list(p) for p in R["ring"]]
WB, EB = R["westbound_lane"], R["eastbound_lane"]
TP = {
    f["properties"]["point"]: f
    for f in json.load(
        open(
            os.path.join(
                B, "proposed", "step-points-2026-10-14-EPSG4269.geojson"
            )
        )
    )["features"]
}
TL = {
    int(f["properties"]["step"]): f["properties"]
    for f in json.load(
        open(
            os.path.join(
                B, "proposed", "step-lines-2026-10-14-EPSG4269.geojson"
            )
        )
    )["features"]
}
OP = {
    f["properties"]["petition_point"]: f["geometry"]["coordinates"][:2]
    for f in json.load(
        open(
            os.path.join(
                B, "proposed", "western-routing-points-EPSG4269.geojson"
            )
        )
    )["features"]
}
DT = json.load(open(os.path.join(B, "proposed", "grit-detour-pins.json")))

# ---------------------------------------------------------------- text
# TTB's steps word for word from the Federal Register's own text of Notice No. 243 (document 2026-16670, full-text XML,
# downloaded 2026-10-15; the PDF is byte-identical to our copy and its text identical to the regulations.gov copy)
NPRM = {
    int(k): v
    for k, v in json.load(
        open(
            os.path.join(B, "description", "ttb-notice-243-steps.json"),
            encoding="utf-8",
        )
    ).items()
}
# our stored copy lost two line-break hyphens; the notice (91 FR 52586) prints them
assert "light-duty" in NPRM[15] and "Mason-McCulloch" in NPRM[19]
PET = {  # petition (Feb. 2, 2023), written boundary description, word for word
    11: "Proceed southeasterly along the westbound lane of State Highway 29 to its intersection with U.S. Highway 377; then",
    12: "Proceed southeasterly along U.S. Highway 377 along the westbound lane to its intersection with U.S. Highway 87; then",
    91: "Proceed north-easterly, then north-westerly, then north-easterly along Honey Creek to the marked 1727-foot elevation point at its intersection with State Highway 29; then",
    92: "Proceed northwesterly along the eastbound lane of State Highway 29 to its intersection with U.S. Highway 377; then,",
    93: "Proceed northwesterly along the eastbound lane of State Highway 29 to the marked 1737-foot elevation point; then,",
    95: "Proceed southwest in a straight line to the unmarked, unnamed road to the point where the road ends; then",
    96: "Proceed southwesterly along the unmarked road to its intersection with US Highway 377; then",
    97: "Proceed southeast in a straight line to the marked 1765-foot summit; then",
    98: "Proceed southeast in a straight line to the end of the unmarked, unnamed road known locally as Lange Road; then",
}
pet_check = json.load(
    open(os.path.join(B, "description", "petition-steps.json"))
)
for k, v in PET.items():
    assert pet_check[str(k)].startswith(v), (k, pet_check[str(k)])
CORR90 = (
    "Proceed north-easterly, then north-westerly along Honey Creek to its confluence with an unnamed, intermittent "
    "tributary, then north-easterly along the tributary to the marked 1727-foot elevation point at its intersection "
    "with State Highway 29; then"
)
NEW = {
    93: "Proceed southwest in a straight line to a windmill; then",
    94: "Proceed west in a straight line to the intersection of a fence line and the unmarked, unnamed road known locally as Topaz Lane; then",
    95: "Proceed southerly, then southwesterly along Topaz Lane to its westernmost point, east of a stock pond; then",
    96: "Proceed south-southwest in a straight line to the marked 1,762-foot elevation point; then",
}


def ttb_body(n):
    return re.sub(r"^\(\d+\)\s*", "", NPRM[n])


# Two corrections to TTB's own wording, outside the change near Grit (Dan, Oct. 17, 2026; issue #38). Text only: the line,
# the points and the area do not change. The change notes start "text correction", which src/review/compare_ttb.py
# counts as unchanged (the line is TTB's step) and the dashboard's step filter looks for.
#  (85) substantive: the summit the step goes to (its end point, -99.25899, 30.72613 NAD83) is printed x1802 on the
#       Turtle Creek, TX (1968) map; TTB's 1,801 follows the petition's written step 86 ("the marked 1801-foot summit").
#  (49) editorial: everywhere else in TTB's 96 steps an elevation is "N-foot" (72 times), as in 27 CFR part 9 (about
#       500 times) and in the petition's step 50 ("the marked 1,586-foot elevation point").
TEXT_FIX = {
    49: (
        "the marked 1,586-elevation point",
        "the marked 1,586-foot elevation point",
        "text correction (editorial): 1,586-elevation point -> 1,586-foot elevation point, as TTB writes every other "
        "elevation (the line does not change)",
    ),
    85: (
        "the marked 1,801-foot summit",
        "the marked 1,802-foot summit",
        "text correction: 1,801-foot summit -> 1,802-foot summit, as the Turtle Creek map prints it (x1802) "
        "(the line does not change)",
    ),
}

STEPS = []  # (number, text without the number, source, change)
for n in range(1, 105):
    if n in TEXT_FIX:
        old, new, note = TEXT_FIX[n]
        assert ttb_body(n).count(old) == 1, (n, ttb_body(n))
        STEPS.append(
            (
                n,
                ttb_body(n).replace(old, new),
                f"TTB's published text, step ({n}), corrected",
                note,
            )
        )
    elif n <= 9 or 12 <= n <= 89:
        STEPS.append(
            (n, ttb_body(n), f"TTB's published text, step ({n})", "unchanged")
        )
    elif n in (10, 11):
        STEPS.append(
            (
                n,
                PET[n + 1],
                f"Petition step {n + 1}",
                "petition wording (replaces TTB's step (%d))" % n,
            )
        )
    elif n == 90:
        STEPS.append(
            (
                n,
                CORR90,
                "Petition step 91, corrected",
                "petition wording, CORRECTED: names the tributary",
            )
        )
    elif n in (91, 92):
        STEPS.append(
            (n, PET[n + 1], f"Petition step {n + 1}", "petition wording")
        )
    elif 93 <= n <= 96:
        STEPS.append(
            (
                n,
                NEW[n],
                "New (proposed; discussed with TTB Oct. 15, 2026)",
                "NEW: granite lobe",
            )
        )
    elif 97 <= n <= 100:
        STEPS.append(
            (n, PET[n - 2], f"Petition step {n - 2}", "petition wording")
        )
    else:
        STEPS.append(
            (
                n,
                ttb_body(n - 8),
                f"TTB's published text, step ({n - 8})",
                "unchanged, renumbered from (%d)" % (n - 8),
            )
        )

# The petition-worded steps are written in TTB's style, as its published text writes them (style only; each step's
# change field lists what was rewritten): "US Highway" (the petition writes "U.S. Highway"), "northeasterly" and
# "northwesterly" (the petition hyphenates them), elevations with a comma ("1,727-foot"), and "then" without a comma.
STYLE = [
    (r"U\.S\. Highway", "US Highway"),
    (r"\b(north|south)-(east|west)erly\b", r"\1\2erly"),
    (r"\b(\d)(\d{3})-foot\b", r"\1,\2-foot"),
    (r"; then,$", "; then"),
]
for i, (n, body, src, change) in enumerate(STEPS):
    if not src.startswith("Petition"):
        continue
    notes = []
    for pat, rep in STYLE:
        for m in dict.fromkeys(
            re.findall(f"(?:{pat})", body)
            and [x.group(0) for x in re.finditer(pat, body)]
        ):
            notes.append(
                f"{m.lstrip('; ')} -> {re.sub(pat, rep, m).lstrip('; ')}"
            )
        body = re.sub(pat, rep, body)
    if notes:
        STEPS[i] = (n, body, src, change + "; TTB's style: " + ", ".join(notes))
assert not any(
    re.search(
        r"U\.S\.|\b(north|south)-(east|west)erly\b|\b\d{4}-foot\b|then,$", b
    )
    for _, b, _, _ in STEPS
)
print(
    "TTB style applied:",
    {n: c.split("; ", 1)[1] for n, _, _, c in STEPS if "TTB's style:" in c},
)
# Road names as TTB's published text names them: State Highway 29 northwest of the junction near Grit (TTB step (10)),
# US Highway 377 on the shared road from the junction to Mason (TTB step (11)). The marked 1,727 is 1.5 km southeast
# of the junction, on the shared road, so steps (90)-(91) name it US Highway 377 where the petition said State Highway 29.
NAMES = {
    90: [
        (
            "at its intersection with State Highway 29; then",
            "at its intersection with US Highway 377; then",
        )
    ],
    91: [
        (
            "along the eastbound lane of State Highway 29 to its intersection with US Highway 377; then",
            "along the eastbound lane of US Highway 377 to its intersection with State Highway 29; then",
        )
    ],
}
NAME_NOTE = (
    "road named as TTB names it (US Highway 377, Grit junction to Mason)"
)
for i, (n, body, src, change) in enumerate(STEPS):
    for old, new in NAMES.get(n, []):
        assert body.count(old) == 1, (n, body)
        body = body.replace(old, new)
        STEPS[i] = (n, body, src, change + "; " + NAME_NOTE)
print("TTB road names applied:", [n for n, _, _, c in STEPS if NAME_NOTE in c])
assert all(len(c.encode()) <= 254 for _, _, _, c in STEPS), (
    "a change note is longer than a shapefile text field"
)


# ---------------------------------------------------------------- endpoints on the ring
def proj(p, line):
    best = None
    for i, (a, b) in enumerate(zip(line, line[1:])):
        ax, ay, bx, by, px, py = (
            a[0] * 95700,
            a[1] * 110900,
            b[0] * 95700,
            b[1] * 110900,
            p[0] * 95700,
            p[1] * 110900,
        )
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = (
            0
            if L == 0
            else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
        )
        q = [(ax + t * dx) / 95700, (ay + t * dy) / 110900]
        dd = d(p, q)
        if best is None or dd < best[0]:
            best = (dd, i, t, q)
    return best


junction = TP["10"]["geometry"]["coordinates"][:2]
END = {}
for n in range(1, 105):
    if n == 9:
        END[n] = WB[0]  # Honey Creek now ends where it meets the westbound lane
    elif n <= 9 or 12 <= n <= 89:
        END[n] = TP[str(n)]["geometry"]["coordinates"][:2]
    elif n == 10:
        END[n] = proj(junction, WB)[3]
    elif n == 11:
        END[n] = WB[-1]
    elif n == 90:
        END[n] = EB[0]
    elif n == 91:
        END[n] = proj(junction, EB)[3]
    elif n == 92:
        END[n] = EB[-1]
    elif n == 93:
        END[n] = DT["windmill"]
    elif n == 94:
        END[n] = DT["C"]
    elif n == 95:
        END[n] = DT["D"]
    elif n == 96:
        END[n] = OP[97]
    elif 97 <= n <= 99:
        END[n] = OP[n + 1]
    elif n == 100:
        END[n] = TP["92"]["geometry"]["coordinates"][:2]
    else:
        END[n] = TP[str(n - 8)]["geometry"]["coordinates"][:2]
BEGIN = TP["Beginning"]["geometry"]["coordinates"][:2]
assert d(ring[0], BEGIN) < 0.01 and ring[0] == ring[-1]
# Pins moved onto the centre of the printed feature (fix_pins.py, Oct. 16, 2026: the pins have to be perfect). Each
# move replaces the step's endpoint AND the ring vertex that sits on the old pin, so the chords either side follow.
MOVES = os.path.join(B, "tracing", "pin-moves.json")
if os.path.exists(MOVES) and not os.environ.get("NO_PIN_MOVES"):
    PM = json.load(open(MOVES))
    for k, mv in PM.items():
        n = int(k)
        assert d(END[n], mv["old"]) < 0.05, (
            n,
            "pin-moves.json 'old' is not the step's endpoint",
        )
        j = min(range(len(ring)), key=lambda i: d(ring[i], mv["old"]))
        assert d(ring[j], mv["old"]) < 0.05, (n, "old pin not a ring vertex")
        END[n] = list(mv["new"])
        ring[j] = list(mv["new"])
        if j == 0:
            ring[-1] = ring[0]
        if mv.get(
            "trim_step"
        ):  # the pin moved BACK along its own step's line (e.g. pin 92 along the lane): drop that
            lo = max(
                0, j - 400
            )  # line's vertices beyond the new pin, so the step ends at the pin without a spur
            dd, i, t, q = proj(mv["new"], ring[lo:j])
            assert dd < 0.5, (
                n,
                "trim_step: new pin is not on the step's line",
                dd,
            )
            ring = ring[: lo + i + 1] + ring[j:]
    print(
        "pins moved onto the ink centre:",
        {k: v["moved_m"] for k, v in PM.items()},
    )
idx = [0]
cur = 0
split_log = []
for n in range(1, 105):
    p = END[n]
    if n == 104:
        idx.append(len(ring) - 1)
        continue
    # nearest vertex at or after the previous endpoint (search the next 20,000 vertices)
    hi = min(len(ring), cur + 20000)
    j = min(range(cur + 1, hi), key=lambda k: d(ring[k], p))
    if (
        d(ring[j], p) > 0.01
    ):  # a point on a lane (steps 10 and 91): insert it on its segment
        best = proj(p, ring[cur:hi])
        assert best[0] < 0.01, (n, best[0])
        k = cur + best[1] + 1
        ring.insert(k, list(best[3]))
        j = k
        split_log.append((n, round(best[0], 4)))
    assert j > cur, (n, j, cur)
    idx.append(j)
    cur = j
print("inserted split points:", split_log)

# ---------------------------------------------------------------- ink centrelines (usgs-quad-trace skill)
# The steps that follow a mapped feature are replaced by their traces onto the centre of the ink
# (ink-centerline-steps.geojson, made by ink_centerline.py; GOAL-ink-centerlines.md). The pins stay where they are.
TRACED = os.path.join(HERE, "ink-centerline-steps.geojson")
PIN_TIE = 12.0
# hand patches by Dan on the ink overlay (apply_patches.py, provenance in each step's hand_edits), Oct. 16, 2026
if os.path.exists(
    os.path.join(HERE, "ink-centerline-steps-patched.geojson")
) and not os.environ.get("NO_PATCHES"):
    TRACED = os.path.join(HERE, "ink-centerline-steps-patched.geojson")
    print("traced lines: hand-patched file")
if os.path.exists(TRACED) and not os.environ.get("NO_SPLICE"):
    T = {
        int(f["properties"]["id"]): f
        for f in json.load(open(TRACED))["features"]
    }
    segs = [ring[a : b + 1] for a, b in zip(idx, idx[1:])]
    spliced = []
    for n in sorted(T):
        c = [list(p) for p in T[n]["geometry"]["coordinates"]]
        old = segs[n - 1]
        assert d(c[0], old[0]) < 0.5 and d(c[-1], old[-1]) < 0.5, (
            n,
            "traced line does not end at the step's pins",
        )
        # tie each end to its pin with a straight segment (vertices within PIN_TIE m of the pin dropped): where a pin
        # sits a few metres off a road's centre, the trace's hook to it would cross the next step's hook
        # ... except at an end where a hand patch runs to the pin (apply_patches.py marks it pin_patched): keep the patch
        pp = T[n]["properties"].get("pin_patched") or []
        c = (
            [old[0]]
            + [
                q
                for q in c[1:-1]
                if ("start" in pp or d(q, old[0]) > PIN_TIE)
                and ("end" in pp or d(q, old[-1]) > PIN_TIE)
            ]
            + [old[-1]]
        )
        c = [
            q for k, q in enumerate(c) if k == 0 or d(q, c[k - 1]) > 1e-3
        ]  # a patch run to the pin repeats the pin
        segs[n - 1] = c
        spliced.append(n)
    ring = [segs[0][0]]
    idx = [0]
    for seg in segs:
        ring += seg[1:]
        idx.append(len(ring) - 1)
    assert ring[0] == ring[-1] and len(idx) == 105
    print("ink centrelines spliced into steps:", spliced)

# ---------------------------------------------------------------- AVA record (TTB fields, filled)
poly = ogr.CreateGeometryFromJson(
    json.dumps({"type": "Polygon", "coordinates": [ring]})
)
assert poly.IsValid()
sqmi = geo(poly).GeodesicArea() / ttb_record.SQ_MILE
ttb = json.load(open(ttb_record.TTB_RECORD))["features"][0]["attributes"]
AVA = {k: ttb.get(k) for k in ttb_record.TTB_FIELDS}
AVA.update(
    OBJECTID=None,
    Id=0,
    Area=sqmi,
    Contains_="None",
    Partially_Overlaps="None",
    Shape__Area=poly.Area(),
    Shape__Length=poly.Boundary().Length(),
)
AVA.update(
    area_sqmi=round(sqmi, 2),
    source="Dan McLaughlin, Robert Clay Vineyards (petitioner); drawn on the 13 USGS 1:24,000 maps cited in paragraph (b)",
    version_note="Boundary as proposed to TTB after the Oct. 15, 2026 call: TTB's published text, with the petition's wording near Grit, four new steps around a granite lobe, and flagged changes to the wording of steps 49, 85, 90 and 91.",
)
print(
    "AVA %.3f sq mi; fields:" % sqmi,
    {
        k: AVA[k]
        for k in (
            "Name",
            "Id",
            "States",
            "Level_",
            "Contains_",
            "Within",
            "Status",
            "CFR_Section",
            "Partially_Overlaps",
            "Counties",
        )
    },
)


# ---------------------------------------------------------------- features
def kind_of(n, src):
    if n <= 9 or 12 <= n <= 89:
        return TL[n]["kind"]
    if n >= 101:
        return TL[n - 8]["kind"]
    return "straight line" if "straight line" in src else "followed feature"


QUAD = lambda n: (
    TP[str(n)]["properties"]["quad"]
    if (n <= 9 or 12 <= n <= 89)
    else TP[str(n - 8)]["properties"]["quad"]
    if n >= 101
    else "Purdy Hill"
    if n == 11
    else "Turtle Creek"
    if n == 100
    else "Grit"
)
NAME = {
    9: "Honey Creek at the westbound lane of SH 29 (by the marked 1737)",
    10: "SH 29 / US 377 junction (westbound lane)",
    11: "US 377 (shared with SH 29) and US 87 (westbound lane)",
    90: "the marked 1727, where the tributary reaches the eastbound lane",
    91: "SH 29 / US 377 junction (eastbound lane)",
    92: "the marked 1737 (eastbound lane)",
    93: "windmill (center of the vanes)",
    94: "Topaz Lane at a fence line",
    95: "the westernmost point of Topaz Lane",
    96: "the marked 1762",
    97: "terminus of the unmarked, unnamed road",
    98: "the unmarked road and US 377",
    99: "the marked 1765 summit",
    100: "end of Lange Road",
}


def endname(n):
    if n in NAME:
        return NAME[n]
    return (
        TP[str(n)]["properties"]["name"]
        if n <= 89
        else TP[str(n - 8)]["properties"]["name"]
    )


lines, points = [], []
for (n, body, src, change), a, b in zip(STEPS, idx, idx[1:]):
    c = ring[a : b + 1]
    lines.append(
        {
            "step": n,
            "kind": kind_of(n, body),
            "endpoint": endname(n),
            "quad": QUAD(n),
            "length_m": round(glen(c), 1),
            "narrative": f"({n}) {body}",
            "txt_source": src,
            "change": change,
            "_c": c,
        }
    )
points.append(
    {
        "point": "Beginning",
        "step": 0,
        "kind": "Beginning point",
        "name": TP["Beginning"]["properties"]["name"],
        "quad": "Long Mountain",
        "_c": ring[0],
    }
)
for (n, body, src, change), b in zip(STEPS, idx[1:]):
    points.append(
        {
            "point": str(n),
            "step": n,
            "kind": "End of step",
            "name": endname(n),
            "quad": QUAD(n),
            "_c": ring[b],
        }
    )
assert len(lines) == 104 and len(points) == 105
print("perimeter %.1f km" % (sum(l["length_m"] for l in lines) / 1000))

OUT = os.path.join(HERE, "gis")
os.makedirs(OUT, exist_ok=True)
tsl.SHP_DIR = os.path.join(OUT, "shapefiles")
os.makedirs(tsl.SHP_DIR, exist_ok=True)
STEM = "hickory-sands-district-boundary-proposed-2026-10-15-%s-EPSG4269"


def write(kind, feats):
    fc = {
        "type": "FeatureCollection",
        "name": STEM % kind,
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::4269"},
        },
        "features": feats,
    }
    p = os.path.join(OUT, STEM % kind + ".geojson")
    open(p, "w", encoding="utf-8").write(json.dumps(fc, ensure_ascii=False))
    tsl.write_shapefile(fc, STEM % kind)
    return p


write(
    "area",
    [
        {
            "type": "Feature",
            "properties": ttb_record.feature_record(dict(AVA), "area", {}, 1),
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        }
    ],
)
write(
    "line",
    [
        {
            "type": "Feature",
            "properties": ttb_record.feature_record(
                dict(AVA),
                "line",
                {k: v for k, v in l.items() if k != "_c"},
                i + 1,
            ),
            "geometry": {"type": "LineString", "coordinates": l["_c"]},
        }
        for i, l in enumerate(lines)
    ],
)
write(
    "points",
    [
        {
            "type": "Feature",
            "properties": ttb_record.feature_record(
                dict(AVA),
                "points",
                {k: v for k, v in p.items() if k != "_c"},
                i + 1,
            ),
            "geometry": {"type": "Point", "coordinates": p["_c"]},
        }
        for i, p in enumerate(points)
    ],
)
gp = os.path.join(
    OUT, "hickory-sands-district-boundary-proposed-2026-10-15-EPSG4269.gpkg"
)
if os.path.exists(gp):
    os.remove(gp)
# GeoPackage written with explicit field types (TTB's AVAs_Production types, as the shapefiles), not inferred from
# the GeoJSON: an all-null field such as Established would otherwise come out as String instead of Date.
gds = ogr.GetDriverByName("GPKG").CreateDataSource(gp)
for kind in ("area", "line", "points"):
    fc = json.load(open(os.path.join(OUT, STEM % kind + ".geojson")))
    gt = {
        "Polygon": ogr.wkbPolygon,
        "LineString": ogr.wkbLineString,
        "Point": ogr.wkbPoint,
    }[fc["features"][0]["geometry"]["type"]]
    lyr = gds.CreateLayer(f"boundary_{kind}", LL, gt, options=["FID=fid"])
    keys = list(fc["features"][0]["properties"])
    for k in keys:
        vals = [
            f["properties"][k]
            for f in fc["features"]
            if f["properties"][k] is not None
        ]
        if k in tsl.TTB_TYPE:
            t = tsl.TTB_TYPE[k][0]
        elif vals and all(
            isinstance(v, int) and not isinstance(v, bool) for v in vals
        ):
            t = ogr.OFTInteger
        elif vals and all(isinstance(v, (int, float)) for v in vals):
            t = ogr.OFTReal
        else:
            t = ogr.OFTString
        lyr.CreateField(ogr.FieldDefn(k, t))
    for f in fc["features"]:
        of = ogr.Feature(lyr.GetLayerDefn())
        for k in keys:
            if f["properties"][k] is not None:
                of.SetField(k, f["properties"][k])
        of.SetGeometry(ogr.CreateGeometryFromJson(json.dumps(f["geometry"])))
        lyr.CreateFeature(of)
gds = None
json.dump(
    {
        "steps": [
            {"step": n, "text": f"({n}) {b}", "source": s, "change": c}
            for n, b, s, c in STEPS
        ],
        "sqmi": sqmi,
    },
    open(os.path.join(HERE, "agreed-steps.json"), "w"),
    ensure_ascii=False,
    indent=1,
)
print("written", OUT)
