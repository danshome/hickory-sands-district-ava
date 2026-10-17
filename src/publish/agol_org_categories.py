"""Organization content categories for every item in Dan's folder "Hickory Sands District - Final Proposed Boundary and
Narrative" (the group has its own categories, set by agol_publish.py / agol_layer.py). Matched by the item title's number.
Sets each item's full list, so re-running is safe. categories() needs no sign-in (the publish dry run, agol_dryrun.py,
checks them). Sign-in: GIS(profile="hsd"). Run by ./build.sh publish (or .venv/bin/python src/publish/agol_org_categories.py)
"""

import json

from arcgis.gis import GIS

FOLDER = "Hickory Sands District - Final Proposed Boundary and Narrative"
AVA = (
    "/Categories/American Viticultural Areas (AVAs)/Hickory Sands District AVA"
)
ADMIN, AGRI, HIST = (
    "/Categories/Boundaries/Administrative",
    "/Categories/Infrastructure/Agriculture",
    "/Categories/Basemaps/Historical maps",
)
DOC = "/Categories/Documents"
GEO = "/Categories/Environment/Soils and geology"
RULES = [
    ("0 Dashboard", [ADMIN, AGRI]),
    ("0 ", [DOC]),
    ("1", [DOC + "/Boundary descriptions"]),
    ("2a", [DOC + "/Federal Register notices"]),
    ("2b", [DOC + "/Federal Register notices"]),
    ("2c", [DOC + "/Comparisons"]),
    ("2d", [DOC + "/Comparisons"]),
    ("3", [DOC + "/Comparisons"]),
    ("4a", [ADMIN, AGRI]),
    ("4b", [ADMIN, AGRI]),
    ("4l", [GEO]),
    ("4m", [GEO]),
    ("4n", [ADMIN, GEO]),
    ("4o", [ADMIN, GEO]),
    ("4", [ADMIN]),
    ("5", [HIST, ADMIN]),
]


def categories(title):
    """an item's organization categories, by its title's number"""
    return [AVA] + next(c for prefix, c in RULES if title.startswith(prefix))


def main():
    gis = GIS(profile="hsd")
    items = list(gis.content.folders.get(FOLDER).list())
    payload = []
    for it in items:
        payload.append({it.id: {"categories": categories(it.title)}})
    r = gis._con.post(
        f"{gis._portal.resturl}content/updateItems",
        {"f": "json", "items": json.dumps(payload)},
    )
    ok = [x for x in r.get("results", []) if x.get("success")]
    bad = [x for x in r.get("results", []) if not x.get("success")]
    print(f"{len(ok)} of {len(items)} items categorized", bad[:3])


if __name__ == "__main__":
    main()
