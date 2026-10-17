"""Publishes the proposed-boundary deliverable to ArcGIS Online, one item per file, in Dan's folder
"Hickory Sands District - Final Proposed Boundary and Narrative", shared only to the private group
"Hickory Sands District AVA - Final Proposed Boundary and Narrative" and placed in the group's categories.

Idempotent: an item with the same title in the folder has its file replaced, not duplicated.
Sign-in: GIS(profile="hsd"), Dan's saved profile (the password stays in his macOS Keychain).
The boundary is PROPOSED (changes discussed with TTB on October 15, 2026); never write "agreed".
Run by ./build.sh publish (or .venv/bin/python src/publish/agol_publish.py) [text that titles must contain, to do only some items]"""
import json, os, re, sys
from arcgis.gis import GIS, ItemProperties, ItemTypeEnum

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))   # the repository root
HERE = os.environ.get("HSD_WORK") or os.path.join(ROOT, "target", "work")   # build work dir (build.sh stages resources/ here)
SQMI = "%.2f" % json.load(open(os.path.join(HERE, "agreed-steps.json")))["sqmi"]   # the built AVA area, GRS80 square miles
PKG = os.path.join(HERE, "pkg", "Hickory-Sands-District-AVA_boundary-as-proposed-2026-10-15")
FOLDER = "Hickory Sands District - Final Proposed Boundary and Narrative"
GROUP_ID = "65720ee9c5a743f88659ae39228704ec"
C1, C2, C3 = "/Categories/1 Boundary description (proposed text)", "/Categories/2 TTB Notice 243 - proposed changes highlighted", "/Categories/3 Changes side by side"
C4D = "/Categories/4 GIS data/Downloads (GeoPackage + shapefiles + GeoJSON)"
C5P, C5T = "/Categories/5 USGS quadrangles with the boundary/GeoPDF", "/Categories/5 USGS quadrangles with the boundary/GeoTIFF"

CREDIT = "Dan McLaughlin, Robert Clay Vineyards (petitioner)"
CC0 = ("CC0 1.0 Universal (public domain dedication): no rights reserved. TTB, its contractors and anyone else may copy, "
       "change and use this for any purpose without permission or attribution. https://creativecommons.org/publicdomain/zero/1.0/")
TAGS = ["Hickory Sands District", "AVA", "TTB", "Notice No. 243", "TTB-2026-0005", "proposed boundary"]
ABOUT = ("<p>Hickory Sands District AVA (Docket No. TTB-2026-0005, Notice No. 243, 91 FR 52576): the boundary the petitioners "
         "propose, with the changes discussed with TTB on October 15, 2026. Prepared by Dan McLaughlin, Robert Clay Vineyards "
         "(petitioner).</p>")
T = ItemTypeEnum

def quad_items():
    out = []
    for kind, ext, cat, typ in (("GeoPDF", "pdf", C5P, T.PDF), ("GeoTIFF", "tif", C5T, T.IMAGE)):
        for f in sorted(os.listdir(os.path.join(PKG, "5_USGS-quadrangles-with-boundary"))):
            m = re.match(r"TX_(.+?)_\d+_(\d{4})_24000_geo\." + ext + "$", f)
            if not m: continue
            name, year = m.groups()
            out.append((f"5_USGS-quadrangles-with-boundary/{f}", f"5{'a' if kind == 'GeoPDF' else 'b'} USGS quadrangle with the boundary ({kind}) - {name}, TX ({year})",
                        typ, cat, f"The USGS 1:24,000 {name}, TX ({year}) quadrangle ({kind}) with the proposed boundary added as a solid red line.",
                        ABOUT + f"<p>The USGS {kind} from topoView, unaltered except for the added boundary line"
                        + (" (an optional-content layer, with each step's record and the line GeoJSON attached)." if kind == "GeoPDF"
                           else " (only the image tiles the line crosses are rewritten).") + " The quadrangle keeps its NAD27 grid; the NAD83 line is "
                        "carried onto it with the NADCON 5.0 CONUS grid.</p>",
                        "USGS topographic map (public domain); boundary line " + CC0, "USGS; boundary line: " + CREDIT))
    return out

D1 = "1_boundary-description/Hickory-Sands-District-boundary-description-as-proposed-2026-10-15"
N2 = "2_TTB-notice-243-with-changes-highlighted/"
S3 = "3_changes-side-by-side/Hickory-Sands-District-boundary-changes-side-by-side-2026-10-15"
G4 = "4_GIS/hickory-sands-district-boundary-proposed-2026-10-15-"
DESC1 = ABOUT + "<p>Proposed &sect; 9.___ Hickory Sands District: paragraphs (a)&ndash;(c) and all 104 boundary steps, TTB's published text with the proposed changes near Grit, followed by the list of changes.</p>"
ITEMS = [
    ("../../documents/Hickory-Sands-District-read-me-first-2026-10-15.pdf", "0 Read me first - what is in this group, and the license", T.PDF, None,
     "What each item is, what the proposed changes are, how the line is drawn, the attributes, and the CC0 license.", ABOUT, CC0, CREDIT),
    (D1 + ".pdf", "1a Boundary description as proposed (PDF)", T.PDF, C1, "The proposed regulatory text, all 104 steps, and the changes from TTB's published text.", DESC1, CC0, CREDIT),
    (D1 + ".docx", "1b Boundary description as proposed (Word)", T.MICROSOFT_WORD, C1, "The proposed regulatory text, editable.", DESC1, CC0, CREDIT),
    (D1 + ".txt", "1c Boundary description as proposed (plain text)", T.CODE_SAMPLE, C1, "The proposed regulatory text as plain text (UTF-8).", DESC1, CC0, CREDIT),
    (D1 + "-steps.csv", "1d Boundary steps, one row per step (CSV)", T.CSV, C1,
     "The 104 steps: text, source, change from TTB's published text, quadrangle, endpoint and length.", DESC1, CC0, CREDIT),
    (N2 + "TTB-Notice-243-with-proposed-Hickory-Sands-District-changes-highlighted-2026-10-15-UNOFFICIAL.pdf",
     "2a TTB Notice 243 with the proposed changes highlighted (unofficial copy, PDF)", T.PDF, C2,
     "TTB's own Notice No. 243 with only the proposed steps set into pages 52586 and 52588, highlighted in yellow. Unofficial.",
     ABOUT + "<p>TTB's docket copy of Notice No. 243 with only the changed steps set into its pages 52586 and 52588, in the notice's own typeface, the changed wording highlighted in yellow. Every other page and line is TTB's. The start of the next document in that issue (Kaw Valley) is moved, unchanged, to an added last page. Prepared by the petitioner for TTB's convenience; not the official Federal Register text.</p>",
     "TTB's notice: U.S. Government work (public domain). The petitioner's changes: " + CC0, "TTB (Notice No. 243); proposed changes: " + CREDIT),
    (N2 + "TTB-Notice-243-as-published-docket-TTB-2026-0005-0001.pdf", "2b TTB Notice 243 as published, docket TTB-2026-0005-0001 (PDF)", T.PDF, C2,
     "TTB's notice exactly as it is in the docket (downloaded October 15, 2026), for comparison.",
     ABOUT + "<p>An unchanged copy of the docket file TTB-2026-0005-0001, for comparison with item 2a.</p>",
     "U.S. Government work (public domain).", "Alcohol and Tobacco Tax and Trade Bureau; Federal Register (GPO)"),
    (N2 + "text-for-comparing-1_TTB-Notice-243-as-published.txt", "2c Text for comparing - 1 TTB Notice 243 as published (plain text)", T.CODE_SAMPLE, C2,
     "The text of item 2b, one paragraph per line, for a text compare (for example Beyond Compare) against 2d.",
     ABOUT + "<p>Extracted with poppler's pdftotext in reading order, one paragraph per line, with GPO's page notes at the page breaks. Compared with 2d, the only differences are the proposed steps, (10)-(11) and (90)-(104).</p>",
     "U.S. Government work (public domain).", "Text of TTB's notice; extracted by " + CREDIT),
    (N2 + "text-for-comparing-2_TTB-Notice-243-with-proposed-changes.txt", "2d Text for comparing - 2 TTB Notice 243 with the proposed changes (plain text)", T.CODE_SAMPLE, C2,
     "The text of item 2a, one paragraph per line, for a text compare against 2c.",
     ABOUT + "<p>Extracted with poppler's pdftotext in reading order, one paragraph per line, with GPO's page notes at the page breaks. Compared with 2c, the only differences are the proposed steps, (10)-(11) and (90)-(104).</p>",
     "TTB's text: U.S. Government work (public domain). The petitioner's changes: " + CC0, CREDIT),
    (S3 + ".pdf", "3a Changes side by side - TTB's text, the petition, the proposed text and why (PDF)", T.PDF, C3,
     "Every step that changes: TTB's published text, the original petition (for reference), the proposed text, and why.",
     ABOUT + "<p>Marking compares the proposed text with TTB's published text only: red strikethrough for TTB's words dropped, yellow for words added. The petition column is for reference and is not marked.</p>", CC0, CREDIT),
    (S3 + ".docx", "3b Changes side by side (Word)", T.MICROSOFT_WORD, C3, "The side-by-side comparison, editable.", ABOUT, CC0, CREDIT),
    (G4 + "EPSG4269.gpkg", "4c Proposed boundary - GeoPackage (AVA polygon, 104 steps, step endpoints)", T.GEOPACKAGE, C4D,
     "All three layers in one OGC GeoPackage, NAD83 (EPSG:4269), with TTB's AVAs_Production fields.",
     ABOUT + "<p>Layers: boundary_area (the AVA, " + SQMI + " square miles), boundary_line (one feature per step, 104, each with its text), boundary_points (the beginning point and the step endpoints).</p>", CC0, CREDIT),
]
for key, what, n in (("area", "AVA polygon", "the AVA polygon (" + SQMI + " square miles)"), ("line", "104 boundary steps", "the boundary, one feature per step (104), each with its text"),
                     ("points", "step endpoints", "the beginning point and the 104 step endpoints")):
    ITEMS.append((f"4_GIS/shapefiles/hickory-sands-district-boundary-proposed-2026-10-15-{key}-EPSG4269-shp.zip", f"4{'def'['area line points'.split().index(key)]} Proposed boundary - {what} (shapefile)",
                  T.SHAPEFILE, C4D, f"Zipped shapefile of {n}, NAD83 (EPSG:4269); field names trimmed to 10 characters, with a field-name key.", ABOUT, CC0, CREDIT))
    ITEMS.append((G4 + f"{key}-EPSG4269.geojson", f"4{'ghi'['area line points'.split().index(key)]} Proposed boundary - {what} (GeoJSON)",
                  T.GEOJSON, C4D, f"GeoJSON of {n}, NAD83 (EPSG:4269).", ABOUT, CC0, CREDIT))
# the description (1a-1d) and the side-by-side (3a, 3b) are mostly TTB's text, so they carry the same split license as 2a, 2d
LIC_MIX = "TTB's text: U.S. Government work (public domain). The petitioner's changes: " + CC0
ITEMS = [(r, ti, ty, c, s, d, LIC_MIX if ti[:1] in "13" else lic, cr) for r, ti, ty, c, s, d, lic, cr in ITEMS]
ITEMS += quad_items()

only = sys.argv[1] if len(sys.argv) > 1 else None
gis = GIS(profile="hsd")
folder = gis.content.folders.create(FOLDER, exist_ok=True)   # made again if it was deleted
group = gis.groups.get(GROUP_ID)
existing = {it.title: it for it in folder.list()}
done = []
for rel, title, typ, cat, snippet, desc, lic, credit in ITEMS:
    if only and only not in title: continue
    path = os.path.normpath(os.path.join(PKG, rel))
    assert os.path.exists(path), path
    assert "agree" not in (title + snippet + desc + lic + credit).lower(), title
    props = ItemProperties(title=title, item_type=typ, tags=TAGS, snippet=snippet, description=desc,
                           license_info=lic, access_information=credit)
    if title in existing:
        it = existing[title]
        it.update(item_properties={"snippet": snippet, "description": desc, "licenseInfo": lic, "accessInformation": credit, "tags": ",".join(TAGS)}, data=path)
        how = "updated"
    else:
        it = folder.add(props, file=path).result()
        how = "added"
    try:
        it.sharing.groups.add(group)
    except AttributeError:
        it.share(groups=[GROUP_ID])
    if cat:
        r = gis._con.post(f"{gis._portal.resturl}content/groups/{GROUP_ID}/updateCategories",
                          {"f": "json", "items": json.dumps([{it.id: [cat]}])})     # for a group: {itemId: [paths]}
        assert all(x.get("success") for x in r.get("results", [{}])), r
    done.append((how, it.id, title))
    print(f"{how:8s} {it.id}  {it.type:18s} {title}", flush=True)
print(f"{len(done)} items")
