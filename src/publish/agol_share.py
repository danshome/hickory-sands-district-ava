"""Makes the group and everything in Dan's folder public (Dan, 2026-10-16).

Everything in Dan's folder "Hickory Sands District - Final Proposed Boundary
and Narrative" is made public, and the group "Hickory Sands District AVA -
Final Proposed Boundary and Narrative" too, so TTB can open the dashboard, the
map and every item without an ArcGIS account. Items stay shared to the group as
well. The group gets the items' tags and a description that lists its
categories. Re-running is safe.

description() builds the group's description without signing in (the publish
dry run, agol_dryrun.py, checks it).

Sign-in: GIS(profile="hsd"). Run last by ./build.sh publish (or
.venv/bin/python src/publish/agol_share.py).
"""

from arcgis.gis import GIS

FOLDER = "Hickory Sands District - Final Proposed Boundary and Narrative"
GROUP_ID = "65720ee9c5a743f88659ae39228704ec"
TAGS = [
    "Hickory Sands District",
    "AVA",
    "TTB",
    "Notice No. 243",
    "TTB-2026-0005",
    "proposed boundary",
]  # as on every item (QA #31)
ACCESS = "public"  # the group, and every item in the folder ("EVERYONE")


def description(items, url):
    """Builds the group's description, without signing in.

    It starts with links to the two 0 items (the dashboard and the read-me),
    then lists the numbered categories (QA, 2026-10-16).

    Args:
        items: The folder's items, each with .title and .id.
        url: The portal's URL.

    Returns:
        The description, as HTML.
    """
    first = {
        it.title.split(" - ")[0]: it
        for it in items
        if it.title.startswith("0 ")
    }

    def link(it, text):
        return f'<a href="{url}/home/item.html?id={it.id}">{text}</a>'

    return (
        "<p>The boundary the petitioners propose for the Hickory Sands "
        "District AVA (Docket No. TTB-2026-0005, Notice No. 243, 91 FR "
        "52576), with the changes discussed with TTB on October 15, 2026. "
        "Prepared by Dan McLaughlin, Robert Clay Vineyards (petitioner).</p>"
        f"<p><b>Start here:</b> {link(first['0 Dashboard'], '0 Dashboard')} "
        "(the map, every step, every difference and a link to every file) "
        f"and {link(first['0 Read me first'], '0 Read me first')} (what each "
        "item is, and the license).</p><p>Browse the content by category "
        "(like folders):</p><ol><li>Boundary description (proposed text)</li>"
        "<li>Notice No. 243 - proposed changes highlighted</li><li>Changes "
        "side by side</li><li>GIS data: map and layers; downloads "
        "(GeoPackage, shapefiles, GeoJSON)</li><li>USGS quadrangles with the "
        "boundary: GeoPDF and GeoTIFF</li></ol>"
    )


def main():
    """Signs in and makes the group and every item in the folder public.

    The group's access, tags and description are sent only where they differ
    from these; each item not yet shared with everyone is shared so. Prints
    how many items are public, and the first few that are not.
    """
    gis = GIS(profile="hsd")
    group = gis.groups.get(GROUP_ID)
    if group.access != ACCESS:
        group.update(access=ACCESS)
    if list(group.tags or []) != TAGS:
        group.update(tags=",".join(TAGS))
    items = list(gis.content.folders.get(FOLDER).list())
    desc = description(items, gis.url)
    if group.description != desc:
        group.update(description=desc)
    for it in items:
        if str(it.sharing.sharing_level).split(".")[-1].upper() != "EVERYONE":
            it.sharing.sharing_level = "EVERYONE"
    not_public = [
        it.title
        for it in gis.content.folders.get(FOLDER).list()
        if it.access != "public"
    ]
    print(
        f"group {gis.groups.get(GROUP_ID).access}; "
        f"{len(items) - len(not_public)} of {len(items)} items public",
        not_public[:5],
    )


if __name__ == "__main__":
    main()
