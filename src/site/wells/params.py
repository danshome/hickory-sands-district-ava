"""The parameters of The land page's three wells (src/site/make_wells.py).

The cited constants (lift energy, the cost tables and indexes, the granite
example's report number and the illustrative values of the screened granite
view), each with its source, are in resources/wells/constants.json; these
are the generator's own rules. Both go into the record, so a change makes
the data stale.
"""

VERSION = 1

# The seven counties the page's figures describe (2023 Census names).
STATEFP = "48"
COUNTIES = (
    "Gillespie",
    "Kimble",
    "Llano",
    "Mason",
    "McCulloch",
    "Menard",
    "San Saba",
)

# The groups, by the mapped rock at the well (SGMC ORIG_LABEL): the Hickory
# Sandstone Member; Town Mountain Granite and the younger granites; and,
# downdip, younger cover (not Quaternary, not Precambrian) where the well is
# coded Hickory by TWDB or reaches the model's Hickory top under cover.
OUTCROP_UNITS = ("Ch",)
GRANITE_UNITS = ("pCt", "pCy")
PRECAMBRIAN_PREFIX = "pC"
QUATERNARY_PREFIXES = ("Q", "Water")
IRRIGATION_USE = 0  # src/site/aquifer/params.py USE_MAP["Irrigation"]
# The drawn downdip well: where the model's Hickory top is this far down.
DEEP_TOP_FT = (1500, 3000)
# The drill grid's flags (docs/assets/aquifer/drill-grid.json).
FLAG_LAYER7 = 1
FLAG_OUTCROP = 4

# The water-bearing stratum a driller logged (the drawing record's water
# class, src/site/aquifer/params.py CLASSES), counted where its basis is the
# log itself (basis 0).
LOGGED_BASIS = 0

# A tested yield this large or larger is counted ("none of the granite
# wells at 200 gpm or more").
BIG_YIELD_GPM = 200
# The deep well's cost depth: its median depth to the nearest 500 ft; the
# model's Hickory top to the nearest 50 ft ("about 2,150 feet").
COST_DEPTH_STEP_FT = 500
TOP_STEP_FT = 50

# The deep drawing's broken axis: the feet left out between the two parts.
DEEP_BREAK_FT = (600, 1950)
# The largest file written (the repository's hooks' limit is 2 MB).
MAX_FILE_BYTES = 200_000

# The drawings' slots in docs/land.html (src/site/wells/record.py BLOCK).
SLOTS = ("deep", "granite-gravel", "granite-rock", "outcrop", "scale")
# Labels in the wide drawings a phone shows: at least this many pixels on a
# phone this wide (a Galaxy Fold's cover screen, the narrowest the site
# is tested on), whose page has this gutter (7vw) on each side.
PHONE_PX = 344
GUTTER = 0.07
MIN_LABEL_PX = 11

# The page's source list (docs/land.html, <li id="source-n">): the number of
# the source each drawn layer names.
SOURCES = {
    "sgmc": 4,
    "cm16": 5,
    "twdb": 7,
    "mason": 9,
    "recharge_outcrop": 27,
    "usgs_rock": 29,
    "ctgcd": 30,
    "construction": 32,
    "example": 31,
    "heath84": 33,
    "hunt": 34,
    "costs": 36,
}
