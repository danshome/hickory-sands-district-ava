"""The parameters of the 3D aquifer page's data (docs/assets/aquifer/).

Every choice the generator (src/site/make_aquifer_3d.py) makes that changes
what it writes is here, and the committed record holds them all: change one
and the build's check calls the data stale until ./build.sh site-data makes
it again. VERSION counts changes to the code's output that no other
parameter shows; raise it with any such change. Standard library only.
"""

VERSION = 1

# TWDB's Llano Uplift groundwater availability model (GAM v1.01): the grid
# of its GAM Properties GeoPackage, inside the model archive.
GAM_MEMBER = "lnup_v101/lnup_v101_fp_grid/lnup_v101_flow_props.gpkg"
ROWS = 478
COLS = 556
CELL_FT = 1320.0  # a quarter mile
HICKORY_LAYER = 7  # the Hickory Aquifer
PRECAMBRIAN_LAYER = 8
IBOUND_OUTCROP = 71  # layer 7 at the surface
IBOUND_PRECAMBRIAN_OUTCROP = 81  # layer 8 at the surface
IBOUND_PRECAMBRIAN_BURIED = 82
M_PER_US_FT = 0.304800609601219

# TWDB's 2017 Hickory outline is moved by the geology's own shift
# (resources/geology/README.md), in NAD83 degrees, before anything else.
SHIFT_LON = -0.002356
SHIFT_LAT = 0.002993

# The aquifer is drawn in blocks of k x k model cells: 2 x 2 on large
# screens, 4 x 4 on phones.
FACTORS = (2, 4)
# The forward polynomial (model row and column to NAD83 longitude and
# latitude) the page builds the block corners from: its degree and the
# largest error allowed, in metres.
CORNER_DEGREE = 3
CORNER_MAX_ERROR_M = 0.5
# The lookup polynomial (longitude and latitude to model row and column)
# for "My location": its degree and largest error allowed, in cells.
LOOKUP_DEGREE = 3
LOOKUP_MAX_ERROR_CELLS = 0.02
# Steps in the aquifer's top: cells beside a step of more than this many
# feet, and how near a fault line (in cells) counts as on it.
STEP_FT = 200.0
FAULT_NEAR_CELLS = 1.5
# Model Hickory outside TWDB's outline counted near the granite core when
# within this many miles of the model's Precambrian outcrop.
CORE_MILES = 3.0

# When TTB's AVAs_Production layer was queried for the Llano Uplift AVA
# (resources/ttb/ttb-avas-production-llano-uplift-EPSG4269-NAD83.geojson).
TTB_LLANO_UPLIFT_QUERIED = "2026-10-18"

TOWNS = ("Mason", "Llano", "Brady", "Fredericksburg", "San Saba", "Burnet")
DECIMALS = 5  # longitude and latitude in the page's GeoJSON

# Wells: drawing tiles, the cells the raw reports are fetched by, and the
# thinned overview's cells, all in degrees.
TILE_DEG = 0.2
DETAIL_DEG = 0.05
OVERVIEW_DEG = 0.05
# The view's map scales the page draws the wells by: further out than
# WELLS_ALL_SCALE, the thinned overview; from it in, every well's head; and
# from WELLS_LINES_SCALE in, also the lines down the hole, for the tiles
# around the middle of the view. WELLS_ALL_SCALE lies between the page's two
# views, as measured in Chrome on 2026-10-18: "Whole aquifer" opens at about
# 1:647,000 at 1440 x 900 (1:471,000 at 1920 x 1080; 1:1,038,000 on a 390 x
# 844 phone), thinned; "District" is about 1:145,000 at 1440 x 900 and
# 1:368,000 on the phone (1:397,000 at 360 x 780), every well.
WELLS_ALL_SCALE = 430_000
WELLS_LINES_SCALE = 250_000
# Every well's head is written this many to a file (wells/heads-<n>.json),
# so each stays well under the hooks' 2 MB.
HEADS_PER_FILE = 20_000
# The vineyards it draws, and the wells near each, are made apart from the
# rest (src/site/make_vineyards.py; their parameters are in vineyards.py).

# The lithology classes: an interval takes the first that matches its
# description, case-insensitive (Comment 9's s04 rule plus limestone).
CLASS_RULES = (
    ("granite", r"granit"),
    ("metamorphic", r"gneiss|schist|metamorph|marble"),
    ("sandstone", r"sand ?stone|hickory"),
    ("limestone", r"lime ?stone|limerock|\blime\b"),
)
CLASSES = (
    "granite",
    "metamorphic",
    "sandstone",
    "limestone",
    "other",
    "unlogged",
)

# Well use: the report's own use (a driller's report's ProposedUse, the
# Groundwater Database's WellUse), grouped. Anything not listed is in the
# last group.
USE_GROUPS = (
    "Irrigation",
    "Domestic",
    "Livestock / stock",
    "Public supply",
    "Industrial / commercial / mining",
    "Recreation",
    "Monitoring / test / other / unknown",
)
USE_MAP = {
    "Irrigation": 0,
    "Domestic": 1,
    "Stock": 2,
    "Aquaculture": 2,
    "Public Supply": 3,
    "Institution": 3,
    "Industrial": 4,
    "Commercial": 4,
    "Mining": 4,
    "De-watering": 4,
    "Injection": 4,
    "Rig Supply": 4,
    "Fracking Supply": 4,
    "Recreation": 5,
}
OTHER_USE = 6

# The largest file the repository's hooks accept (check-added-large-files).
MAX_FILE_BYTES = 2 * 1024 * 1024
