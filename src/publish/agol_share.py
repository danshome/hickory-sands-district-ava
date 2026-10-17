"""Makes everything in Dan's folder "Hickory Sands District - Final Proposed Boundary and Narrative" public, and the group
"Hickory Sands District AVA - Final Proposed Boundary and Narrative" public too, so TTB can open the dashboard, the map
and every item without an ArcGIS account (Dan, 2026-10-16). Items stay shared to the group as well. Re-running is safe.
Sign-in: GIS(profile="hsd"). Run last by ./build.sh publish (or .venv/bin/python src/publish/agol_share.py)"""
from arcgis.gis import GIS

FOLDER = "Hickory Sands District - Final Proposed Boundary and Narrative"
GROUP_ID = "65720ee9c5a743f88659ae39228704ec"

gis = GIS(profile="hsd")
group = gis.groups.get(GROUP_ID)
if group.access != "public":
    group.update(access="public")
items = list(gis.content.folders.get(FOLDER).list())
# the group's description: start with the two 0 items, then the numbered categories (QA, 2026-10-16)
first = {it.title.split(" - ")[0]: it for it in items if it.title.startswith("0 ")}
link = lambda it, text: f'<a href="{gis.url}/home/item.html?id={it.id}">{text}</a>'
desc = ("<p>The boundary the petitioners propose for the Hickory Sands District AVA (Docket No. TTB-2026-0005, Notice No. 243, "
        "91 FR 52576), with the changes discussed with TTB on October 15, 2026. Prepared by Dan McLaughlin, Robert Clay Vineyards "
        "(petitioner).</p>"
        f"<p><b>Start here:</b> {link(first['0 Dashboard'], '0 Dashboard')} (the map, every step, every difference and a link to every file) "
        f"and {link(first['0 Read me first'], '0 Read me first')} (what each item is, and the license).</p>"
        "<p>Browse the content by category (like folders):</p><ol><li>Boundary description (proposed text)</li><li>TTB Notice 243 - "
        "proposed changes highlighted</li><li>Changes side by side</li><li>GIS data: map and layers; downloads (GeoPackage, shapefiles, "
        "GeoJSON)</li><li>USGS quadrangles with the boundary: GeoPDF and GeoTIFF</li></ol>")
if group.description != desc:
    group.update(description=desc)
for it in items:
    if str(it.sharing.sharing_level).split(".")[-1].upper() != "EVERYONE":
        it.sharing.sharing_level = "EVERYONE"
not_public = [it.title for it in gis.content.folders.get(FOLDER).list() if it.access != "public"]
print(f"group {gis.groups.get(GROUP_ID).access}; {len(items) - len(not_public)} of {len(items)} items public", not_public[:5])
