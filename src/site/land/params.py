"""The parameters of The land page's data (docs/assets/land/).

Every choice the generator (src/site/make_land.py) makes that changes what
it writes is here, and the committed record holds them all: change one and
the build's check calls the data stale until ./build.sh site-data makes it
again. VERSION counts changes to the code's output that no other parameter
shows; raise it with any such change. Standard library only.
"""

VERSION = 2

# The rule the line is drawn on: Notice No. 243 (91 FR 52579), "at 1,500 feet
# or higher". A parameter of the rule, not a measurement.
RULE_FT = 1500
M_PER_FT = 0.3048  # 3DEP's metres to (international) feet
M_PER_US_FT = 0.304800609601219  # the model's units, US survey feet
FT_PER_MI = 5280

# The slice: part of TWDB's section line A-A' (Shi and others, 2016, Fig.
# 2.2.2), model row 239, from column COL_NW (north-west, where the Hickory is
# deep under younger rock) to COL_SE (on the Precambrian rock of the uplift).
# The line itself is resources/aquifer/twdb-gam-row239-EPSG4269.geojson.
ROW = 239
COL_NW = 150
COL_SE = 290
CELL_FT = 1320  # each model cell spans a quarter mile along the line
HICKORY_LAYER = 7
PRECAMBRIAN_LAYER = 8

# The ground along the slice: USGS 3DEP 1 arc-second, bilinear, sampled every
# GROUND_STEP_FT and written every GROUND_KEEP-th sample.
LINE_TILES = ("usgs-3dep-1-n31w100", "usgs-3dep-1-n32w100")
GROUND_STEP_FT = 100
GROUND_KEEP = 2
# The drawing's frame: this much above the highest ground, and below the
# deepest base of the Hickory, each rounded out to Z_ROUND_FT.
Z_ABOVE_FT = 150
Z_BELOW_FT = 250
Z_ROUND_FT = 100
# The depth of the sandstone's top at the slice's north-west end, shown
# rounded to this many feet ("about 2,240 feet").
DEPTH_ROUND_FT = 10
# The last of the slice's one-mile stretches is shorter (step 5: "the last
# a quarter-mile"): how the page says it, by its whole model cells.
LAST_STRETCH_WORDS = {
    1: "a quarter-mile",
    2: "half a mile",
    3: "three quarters of a mile",
}
# Two intervals along the line closer than this (feet) are one.
JOIN_FT = 2

# Wells on the slice: logged, with a reported depth, within WELL_BUFFER_M of
# the line; then the deepest in each mile of it that has one (on a tie, the
# first in the 3D page's heads files, TWDB's own order), so the sticks stay
# apart.
WELL_BUFFER_M = 800
WELL_EVERY_MI = 1

# The vertical exaggeration of the drawn slice.
VE = 40

# The four maps' frame, NAD83 longitude and latitude (west, south, east,
# north): the district and the core to its east, the same on every map.
FRAME = (-99.47, 30.67, -98.84, 31.17)
MAP_W = 540  # the maps' width in their own units; north up
SCALE_KM = 10  # the scale bar
KM_PER_DEG_LAT = 111.32
# Map 01: 3DEP 1 arc-second, averaged onto a grid of DEM_STEP degrees,
# thresholded at RULE_FT and outlined.
DEM_TILES = (
    "usgs-3dep-1-n31w100",
    "usgs-3dep-1-n32w100",
    "usgs-3dep-1-n31w099",
    "usgs-3dep-1-n32w099",
)
DEM_STEP = 0.0005
# How much each outline is simplified, in degrees.
SIMPLIFY = {
    "district": 0.0003,
    "hickory": 0.0004,
    "precambrian": 0.0004,
    "high": 0.0006,
    "together": 0.0004,
}
# The sandstone at the surface: the shifted USGS geology's layer.
GEOLOGY_LAYER = "Hickory_Sandstone_Member_formation"
# The wells' detail files the maps read, by cell (as the 3D page writes
# them; src/site/aquifer/params.py's DETAIL_DEG).
DETAIL_DEG = 0.05

# The page's well classes. An interval takes the class of the FIRST rock its
# driller names (drillers name the main material first): "shale w/ lime
# stks" is shale, "lime w/ shale stks" is limestone, "Whitelime" is
# limestone. A bare "sand" (not "sandy", not "sandstone") is its own class,
# kept apart from sandstone; "sandy", "shaley", "silty", "clayey" and
# "gravelly" are only modifiers (the word boundaries). Words that name no
# rock ("Elenburger", "Grey") are other. The indices 0-5 are the 3D page's
# (src/site/aquifer/params.py's CLASSES), with sand added as 6; dolomite is
# in the limestone class, named "Limestone or dolomite".
CLASSES = (
    "granite",
    "metamorphic",
    "sandstone",
    "limestone",
    "other",
    "unlogged",
    "sand",
)
CLASS_RULES = (
    ("granite", r"granit"),
    ("metamorphic", r"gneiss|schist|metamorph|marble"),
    ("sandstone", r"sand\s?stone|hickory"),
    ("sand", r"\bsands?\b"),
    ("limestone", r"lime\s?stone|limerock|lime\b|dolomit"),
    (
        "other",
        (
            r"\bshale\b|\bclay\b|caliche|\bgravel\b|soil|dirt|\bsilt\b|"
            r"conglomerate|chert|overburden|surface|\brock\b"
        ),
    ),
)
# The drawing's colours by class (unlogged is never drawn), and the order
# map 03 draws its dots in: sandstone and sand last, on top.
CLASS_COLOURS = (
    "#b5485e",
    "#7b5ea7",
    "#a8820f",
    "#5b8a57",
    "#a3906f",
    "#9a958c",
    "#d8bd55",
)
MAP_DRAW_ORDER = (
    "other",
    "limestone",
    "metamorphic",
    "granite",
    "sand",
    "sandstone",
)
MAP_DOT_R = 2.6
# The static drawing of the slice (section.svg, for readers without
# JavaScript and for print): its width in CSS pixels.
SECTION_SVG_W = 960

# The largest file each kind may be (bytes): the maps are on the page, so
# they stay small; nothing reaches the hooks' 2 MB.
MAX_MAP_BYTES = 200_000
MAX_FILE_BYTES = 2 * 1024 * 1024
