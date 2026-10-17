"""Publishes the proposed-boundary deliverable to ArcGIS Online, one item per file, in Dan's folder
"Hickory Sands District - Final Proposed Boundary and Narrative", shared only to the private group
"Hickory Sands District AVA - Final Proposed Boundary and Narrative" and placed in the group's categories.

Idempotent: an item with the same title in the folder has its file replaced, not duplicated. An item whose title has
changed is found by its earlier title (WAS) and retitled, and category 2's earlier name is renamed in the group's schema.
Sign-in: GIS(profile="hsd"), Dan's saved profile (the password stays in his macOS Keychain).
The boundary is PROPOSED (changes discussed with TTB on October 15, 2026); never write "agreed".
Run by ./build.sh publish (or .venv/bin/python src/publish/agol_publish.py) [text that titles must contain, to do only some items]"""
import json, math, os, re, sys
from arcgis.gis import GIS, ItemProperties, ItemTypeEnum
from osgeo import gdal, osr
gdal.UseExceptions()

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))   # the repository root
HERE = os.environ.get("HSD_WORK") or os.path.join(ROOT, "target", "work")   # build work dir (build.sh stages resources/ here)
SQMI = "%.2f" % json.load(open(os.path.join(HERE, "agreed-steps.json")))["sqmi"]   # the built AVA area, GRS80 square miles
PKG = os.path.join(HERE, "pkg", "Hickory-Sands-District-AVA_boundary-as-proposed-2026-10-15")
FOLDER = "Hickory Sands District - Final Proposed Boundary and Narrative"
GROUP_ID = "65720ee9c5a743f88659ae39228704ec"
C1, C2, C3 = "/Categories/1 Boundary description (proposed text)", "/Categories/2 Notice No. 243 - proposed changes highlighted", "/Categories/3 Changes side by side"
C2_WAS = "2 TTB Notice 243 - proposed changes highlighted"   # category 2's earlier name in the group's schema (QA #31)
C4D = "/Categories/4 GIS data/Downloads (GeoPackage + shapefiles + GeoJSON)"
C5P, C5T = "/Categories/5 USGS quadrangles with the boundary/GeoPDF", "/Categories/5 USGS quadrangles with the boundary/GeoTIFF"

CREDIT = "Dan McLaughlin, Robert Clay Vineyards (petitioner)"
CC0 = ("CC0 1.0 Universal (public domain dedication): no rights reserved. TTB, its contractors and anyone else may copy, "
       "change and use this for any purpose without permission or attribution. https://creativecommons.org/publicdomain/zero/1.0/")
TAGS = ["Hickory Sands District", "AVA", "TTB", "Notice No. 243", "TTB-2026-0005", "proposed boundary"]
CULTURE = "en-us"
ABOUT = ("<p>Hickory Sands District AVA (Docket No. TTB-2026-0005, Notice No. 243, 91 FR 52576): the boundary the petitioners "
         "propose, with the changes discussed with TTB on October 15, 2026. Prepared by Dan McLaughlin, Robert Clay Vineyards "
         "(petitioner).</p>")
PART = ("Part of the Hickory Sands District AVA package (Docket No. TTB-2026-0005, Notice No. 243, 91 FR 52576): the boundary "
        "the petitioners propose, with the changes discussed with TTB on October 15, 2026.")   # for TTB's own notice (2b, 2c)
T = ItemTypeEnum
WAS = {}   # title -> earlier titles, so a re-run finds an item that was retitled and gives it its new title

# ---------------------------------------------------------------- extents (an item's extent puts it in location search)
def outward(xs, ys):   # [[xmin, ymin], [xmax, ymax]], rounded outward to 4 decimals
    return [[math.floor(min(xs) * 1e4) / 1e4, math.floor(min(ys) * 1e4) / 1e4], [math.ceil(max(xs) * 1e4) / 1e4, math.ceil(max(ys) * 1e4) / 1e4]]

def bbox(geojson):
    """the extent of a GeoJSON file's features (NAD83; WGS84 agrees to about a metre here)"""
    xs, ys = [], []
    def walk(c):
        if c and isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c: walk(x)
    for f in json.load(open(geojson))["features"]:
        walk(f["geometry"]["coordinates"])
    return outward(xs, ys)

NADCON = "us_noaa_nadcon5_nad27_nad83_1986_conus.tif"
def neatline(tif, cell=0.125):
    """a 1:24,000 quadrangle's 7.5-minute neatline as an extent: the NAD27 cell that holds the sheet's centre, its corners
    carried to NAD83 with the NADCON 5.0 CONUS grid"""
    ds = gdal.Open(tif); g = ds.GetGeoTransform()
    sheet = osr.SpatialReference(wkt=ds.GetProjection()); sheet.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    geo = sheet.CloneGeogCS(); geo.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    lon, lat = osr.CoordinateTransformation(sheet, geo).TransformPoint(g[0] + g[1] * ds.RasterXSize / 2, g[3] + g[5] * ds.RasterYSize / 2)[:2]
    w, s = math.floor(lon / cell) * cell, math.floor(lat / cell) * cell
    nad83 = osr.SpatialReference(); nad83.ImportFromEPSG(4269); nad83.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    o = osr.CoordinateTransformationOptions()
    o.SetOperation("+proj=pipeline +step +proj=axisswap +order=2,1 +step +proj=unitconvert +xy_in=deg +xy_out=rad "
                   f"+step +proj=hgridshift +grids={NADCON} +step +proj=unitconvert +xy_in=rad +xy_out=deg +step +proj=axisswap +order=2,1")
    ct = osr.CoordinateTransformation(geo, nad83, o)
    corners = [ct.TransformPoint(x, y)[:2] for x in (w, w + cell) for y in (s, s + cell)]
    return outward([c[0] for c in corners], [c[1] for c in corners])

# ---------------------------------------------------------------- the 13 quadrangles, titled as paragraph (b) cites them
D1 = "1_boundary-description/Hickory-Sands-District-boundary-description-as-proposed-2026-10-15"
B = {name: year + note for name, year, note in   # paragraph (b) of the proposed text: "(10) Fly Gap, TX., 1962, photorevised 1982;"
     re.findall(r"\(\d+\) ([A-Z][\w ]+?), TX\., (\d{4})((?:, [a-z]+ \d{4})?)[;.]", open(os.path.join(PKG, D1 + ".txt"), encoding="utf-8").read())}
QUAD_EXTENT = {}   # title -> the quadrangle's neatline
def quad_items():
    out = []
    for kind, ext, cat, typ in (("GeoPDF", "pdf", C5P, T.PDF), ("GeoTIFF", "tif", C5T, T.IMAGE)):
        for f in sorted(os.listdir(os.path.join(PKG, "5_USGS-quadrangles-with-boundary"))):
            m = re.match(r"TX_(.+?)_\d+_(\d{4})_24000_geo\." + ext + "$", f)
            if not m: continue
            name, year = m.groups()
            edition = B[name]   # "1962, photorevised 1982" (QA #44); every quad is in paragraph (b), with the file's year
            assert edition.startswith(year), (name, year, edition)
            title = f"5{'a' if kind == 'GeoPDF' else 'b'} USGS quadrangle with the boundary ({kind}) - {name}, TX ({edition})"
            if edition != year:
                WAS[title] = [title.replace(f"({edition})", f"({year})")]
            QUAD_EXTENT[title] = neatline(os.path.join(PKG, "5_USGS-quadrangles-with-boundary", f[:-len(ext)] + "tif"))
            out.append((f"5_USGS-quadrangles-with-boundary/{f}", title,
                        typ, cat, f"The USGS 1:24,000 {name}, TX ({edition}) quadrangle ({kind}) with the proposed boundary added as a solid red line.",
                        ABOUT + f"<p>The USGS {kind} from topoView, unaltered except for the added boundary line"
                        + (" (an optional-content layer, with each step's record and the line GeoJSON attached)." if kind == "GeoPDF"
                           else " (only the image tiles the line crosses are rewritten).") + " The quadrangle keeps its NAD27 grid; the NAD83 line is "
                        "carried onto it with the NADCON 5.0 CONUS grid.</p>",
                        "USGS topographic map (public domain); boundary line " + CC0, "USGS; boundary line: " + CREDIT))
    return out

N2 = "2_TTB-notice-243-with-changes-highlighted/"
S3 = "3_changes-side-by-side/Hickory-Sands-District-boundary-changes-side-by-side-2026-10-15"
G4 = "4_GIS/hickory-sands-district-boundary-proposed-2026-10-15-"
AVA = bbox(os.path.join(PKG, G4 + "area-EPSG4269.geojson"))   # the extent of the 4 GIS downloads
DESC1 = ABOUT + "<p>Proposed &sect; 9.___ Hickory Sands District: paragraphs (a)&ndash;(c) and all 104 boundary steps, TTB's published text with the proposed changes near Grit, followed by the list of changes.</p>"
DESC1C = (ABOUT + "<p>Proposed &sect; 9.___ Hickory Sands District as plain text (UTF-8): paragraphs (a)&ndash;(c) and all 104 "
          "boundary steps, one step to a line, Notice No. 243's text with the proposed changes near Grit. The regulatory text only: "
          "the list of changes is in items 1a and 1b, and each changed step is set beside Notice No. 243's text, with why, in 3a and 3b.</p>")
DESC1D = (ABOUT + "<p>The 104 boundary steps of the proposed text, one row each (CSV, UTF-8), with the columns <i>step</i> (its "
          "number), <i>text</i> (the step as proposed), <i>text_source</i> (where the wording comes from: Notice No. 243 or the "
          "petition, and the step number there), <i>change_from_TTB_published_text</i> (unchanged, or how it differs from "
          "Notice No. 243), <i>quad</i> (its USGS quadrangle), <i>endpoint</i> (the mark or junction it ends at) and "
          "<i>length_m</i> (its length in metres, as drawn). The same steps as the boundary_line layer of the GIS data "
          "(4b-4i); the full document is item 1a.</p>")
ITEMS = [
    ("../../documents/Hickory-Sands-District-read-me-first-2026-10-15.pdf", "0 Read me first - what is in this group, and the license", T.PDF, None,
     "What each item is, what the proposed changes are, how the line is drawn, the attributes, and the CC0 license.",
     ABOUT + "<p>A short PDF to read first. It lists every numbered item in this group, in the group's categories: 1 the boundary "
     "description as proposed; 2 Notice No. 243 with the proposed changes highlighted, and the text of both for comparing; 3 the "
     "changes side by side; 4 the GIS data (the map, the hosted layers and the downloads); 5 the 13 USGS quadrangles with the "
     "boundary. It then sets out what the proposed text changes near Grit, how the line is drawn on the printed linework of the "
     "USGS maps, the attributes of the GIS layers, and the license: CC0 for the petitioner's work, while Notice No. 243 is a "
     "U.S. Government work. The same PDF is attached to the AVA polygon in layer 4b; the dashboard (0 Dashboard) shows the "
     "boundary on the quadrangles and links every item.</p>", CC0, CREDIT),
    (D1 + ".pdf", "1a Boundary description as proposed (PDF)", T.PDF, C1, "The proposed regulatory text, all 104 steps, and the changes from TTB's published text.", DESC1, CC0, CREDIT),
    (D1 + ".docx", "1b Boundary description as proposed (Word)", T.MICROSOFT_WORD, C1,
     "The proposed regulatory text, all 104 steps, and the changes from Notice No. 243's text, as an editable Word document.",
     DESC1 + "<p>The same document as item 1a, as an editable Word file.</p>", CC0, CREDIT),
    (D1 + ".txt", "1c Boundary description as proposed (plain text)", T.CODE_SAMPLE, C1, "The proposed regulatory text as plain text (UTF-8).", DESC1C, CC0, CREDIT),
    (D1 + "-steps.csv", "1d Boundary steps, one row per step (CSV)", T.CSV, C1,
     "The 104 steps: text, source, change from TTB's published text, quadrangle, endpoint and length.", DESC1D, CC0, CREDIT),
    (N2 + "TTB-Notice-243-with-proposed-Hickory-Sands-District-changes-highlighted-2026-10-15-UNOFFICIAL.pdf",
     "2a Notice No. 243 with the proposed changes highlighted (unofficial copy, PDF)", T.PDF, C2,
     "TTB's own Notice No. 243 with only the proposed steps set into pages 52586 and 52588, highlighted in yellow. Unofficial.",
     ABOUT + "<p>TTB's docket copy of Notice No. 243 with only the changed steps set into its pages 52586 and 52588, in the notice's own typeface, the changed wording highlighted in yellow. Every other page and line is TTB's. The start of the next document in that issue (Kaw Valley) is moved, unchanged, to an added last page. Prepared by the petitioner for TTB's convenience; not the official Federal Register text.</p>",
     "TTB's notice: U.S. Government work (public domain). The petitioner's changes: " + CC0, "TTB (Notice No. 243); proposed changes: " + CREDIT),
    (N2 + "TTB-Notice-243-as-published-docket-TTB-2026-0005-0001.pdf", "2b Notice No. 243 as published, docket TTB-2026-0005-0001 (PDF)", T.PDF, C2,
     "TTB's notice exactly as it is in the docket (downloaded October 15, 2026), for comparison.",
     "<p>TTB's Notice No. 243 (91 FR 52576), exactly as it is in the docket: an unchanged copy of the docket file "
     "TTB-2026-0005-0001, downloaded October 15, 2026, and uploaded by Dan McLaughlin, Robert Clay Vineyards (petitioner), "
     "for comparison with item 2a, which sets the proposed steps into the same pages.</p><p>" + PART + "</p>",
     "U.S. Government work (public domain).", "Alcohol and Tobacco Tax and Trade Bureau; Federal Register (GPO)"),
    (N2 + "text-for-comparing-1_TTB-Notice-243-as-published.txt", "2c Text for comparing - 1 Notice No. 243 as published (plain text)", T.CODE_SAMPLE, C2,
     "The text of item 2b, one paragraph per line, for a text compare (for example Beyond Compare) against 2d.",
     "<p>The text of TTB's Notice No. 243 as published (item 2b), extracted by Dan McLaughlin, Robert Clay Vineyards "
     "(petitioner), with poppler's pdftotext in reading order, one paragraph per line, with GPO's page notes at the page "
     "breaks. Compared with 2d, the only differences are the proposed steps, (10)-(11) and (90)-(104).</p><p>" + PART + "</p>",
     "U.S. Government work (public domain).", "Text of TTB's notice; extracted by " + CREDIT),
    (N2 + "text-for-comparing-2_TTB-Notice-243-with-proposed-changes.txt", "2d Text for comparing - 2 Notice No. 243 with the proposed changes (plain text)", T.CODE_SAMPLE, C2,
     "The text of item 2a, one paragraph per line, for a text compare against 2c.",
     ABOUT + "<p>Extracted with poppler's pdftotext in reading order, one paragraph per line, with GPO's page notes at the page breaks. Compared with 2c, the only differences are the proposed steps, (10)-(11) and (90)-(104).</p>",
     "TTB's text: U.S. Government work (public domain). The petitioner's changes: " + CC0, CREDIT),
    (S3 + ".pdf", "3a Changes side by side - TTB's text, the petition, the proposed text and why (PDF)", T.PDF, C3,
     "Every step that changes: TTB's published text, the original petition (for reference), the proposed text, and why.",
     ABOUT + "<p>Marking compares the proposed text with TTB's published text only: red strikethrough for TTB's words dropped, yellow for words added. The petition column is for reference and is not marked.</p>", CC0, CREDIT),
    (S3 + ".docx", "3b Changes side by side (Word)", T.MICROSOFT_WORD, C3,
     "Every step that changes, as an editable Word document: Notice No. 243's text, the original petition (for reference), the proposed text, and why.",
     ABOUT + "<p>The side-by-side comparison of item 3a as an editable Word document. For every step that changes, four columns: "
     "Notice No. 243's text, the original petition (February 2, 2023, for reference), the proposed text, and why. Every other "
     "step is Notice No. 243's text word for word. Marking compares the proposed text with Notice No. 243's text only: red "
     "strikethrough for its words that the proposed text drops, yellow for words added. The petition column is for reference "
     "and is not marked.</p>", CC0, CREDIT),
    (G4 + "EPSG4269.gpkg", "4c Proposed boundary - GeoPackage (AVA polygon, 104 steps, step endpoints)", T.GEOPACKAGE, C4D,
     "All three layers in one OGC GeoPackage, NAD83 (EPSG:4269), with TTB's AVAs_Production fields.",
     ABOUT + "<p>Layers: boundary_area (the AVA, " + SQMI + " square miles), boundary_line (one feature per step, 104, each with its text), "
     "boundary_points (the beginning point and the step endpoints). The hosted layer 4b is published from this file; the same "
     "layers are also downloads as shapefiles (4d-4f) and GeoJSON (4g-4i).</p>", CC0, CREDIT),
]
GIS_LAYERS = {   # the three layers of the GIS downloads: what each holds, and its fields beyond TTB's AVAs_Production fields
    "area": ("AVA polygon", "the AVA polygon (" + SQMI + " square miles)", "boundary_area",
             "<i>area_sqmi</i> (the area in square miles, GRS 1980), <i>source</i> and <i>version_note</i>"),
    "line": ("104 boundary steps", "the boundary, one feature per step (104), each with its text", "boundary_line",
             "each step's number, kind, endpoint, USGS quadrangle, length in metres, text as proposed (<i>narrative</i>), the source "
             "of its wording and its change from Notice No. 243"),
    "points": ("step endpoints", "the beginning point and the 104 step endpoints", "boundary_points",
               "each point's number, step, kind, name and USGS quadrangle")}
for i, (key, (what, n, layer, extra)) in enumerate(GIS_LAYERS.items()):
    shp, gj = "4" + "def"[i], "4" + "ghi"[i]
    base = f"hickory-sands-district-boundary-proposed-2026-10-15-{key}-EPSG4269"
    ITEMS.append((f"4_GIS/shapefiles/{base}-shp.zip", f"{shp} Proposed boundary - {what} (shapefile)",
                  T.SHAPEFILE, C4D, f"Zipped shapefile of {n}, NAD83 (EPSG:4269); field names trimmed to 10 characters, with a field-name key.",
                  ABOUT + f"<p>{n[0].upper() + n[1:]}, as a zipped Esri shapefile in NAD83 (EPSG:4269), for GIS software that does "
                  f"not read GeoPackage. The same features and attributes as the {layer} layer of the GeoPackage (4c) and the "
                  f"GeoJSON ({gj}): TTB's AVAs_Production fields (Name, Status, CFR_Section, Counties and the rest), and {extra}. "
                  f"A shapefile's field names hold 10 characters at most, so the longer ones are trimmed; {base}-field-names.txt "
                  "in the zip gives the full name of each."
                  + (" Text longer than a shapefile field holds (254 bytes) continues in a second field, <i>narrativ2</i>." if key == "line" else "")
                  + "</p>", CC0, CREDIT))
    ITEMS.append((G4 + f"{key}-EPSG4269.geojson", f"{gj} Proposed boundary - {what} (GeoJSON)",
                  T.GEOJSON, C4D, f"GeoJSON of {n}, NAD83 (EPSG:4269).",
                  ABOUT + f"<p>{n[0].upper() + n[1:]}, as GeoJSON: coordinates in longitude and latitude, NAD83 (EPSG:4269, "
                  f"named in the file's crs member), with the full field names. The same features and attributes as the {layer} "
                  f"layer of the GeoPackage (4c) and the shapefile ({shp}): TTB's AVAs_Production fields (Name, Status, "
                  f"CFR_Section, Counties and the rest), and {extra}.</p>", CC0, CREDIT))
# the description (1a-1d) and the side-by-side (3a, 3b) are mostly TTB's text, so they carry the same split license as 2a, 2d;
# the GIS downloads (4c-4i) hold TTB's text and data too (the step text, the AVAs_Production values), so they get the same split
LIC_MIX = "TTB's text: U.S. Government work (public domain). The petitioner's changes: " + CC0
LIC_GIS = ("TTB's text and data, the step text from Notice No. 243 (boundary line layer) and the values copied from TTB's "
           "AVAs_Production record (Name, Status, Counties and the like): U.S. Government work (public domain). The petitioner's "
           "work, the boundary as drawn, its other attributes and the proposed changes to the text: " + CC0)
CREDIT_GIS = CREDIT + "; TTB (Notice No. 243 step text, AVAs_Production record values)"
ITEMS = [(r, ti, ty, c, s, d, LIC_MIX if ti[:1] in "13" else LIC_GIS if ti[:1] == "4" else lic, CREDIT_GIS if ti[:1] == "4" else cr)
         for r, ti, ty, c, s, d, lic, cr in ITEMS]
ITEMS += quad_items()
WAS.update({   # 2a-2d: "Notice No. 243", the official name, in place of "TTB Notice 243" (QA #31)
    "2a Notice No. 243 with the proposed changes highlighted (unofficial copy, PDF)": ["2a TTB Notice 243 with the proposed changes highlighted (unofficial copy, PDF)"],
    "2b Notice No. 243 as published, docket TTB-2026-0005-0001 (PDF)": ["2b TTB Notice 243 as published, docket TTB-2026-0005-0001 (PDF)"],
    "2c Text for comparing - 1 Notice No. 243 as published (plain text)": ["2c Text for comparing - 1 TTB Notice 243 as published (plain text)"],
    "2d Text for comparing - 2 Notice No. 243 with the proposed changes (plain text)": ["2d Text for comparing - 2 TTB Notice 243 with the proposed changes (plain text)"]})
assert set(WAS) <= {ti for _, ti, *_ in ITEMS}, set(WAS) - {ti for _, ti, *_ in ITEMS}

def rename_category(nodes, old, new):
    """renames a category, at any depth, in a group's category schema; True if it was there"""
    hit = False
    for n in nodes:
        if n.get("title") == old:
            n["title"] = new; hit = True
        hit = rename_category(n.get("categories") or [], old, new) or hit
    return hit

only = sys.argv[1] if len(sys.argv) > 1 else None
gis = GIS(profile="hsd")
folder = gis.content.folders.create(FOLDER, exist_ok=True)   # made again if it was deleted
group = gis.groups.get(GROUP_ID)
schema = group.categories.schema
if isinstance(schema, list) and rename_category(schema, C2_WAS, C2.rsplit("/", 1)[1]):   # its items are put back in it below
    group.categories.schema = schema
    print("renamed category", C2_WAS, "->", C2)
existing = {it.title: it for it in folder.list()}
done = []
for rel, title, typ, cat, snippet, desc, lic, credit in ITEMS:
    if only and only not in title: continue
    path = os.path.normpath(os.path.join(PKG, rel))
    assert os.path.exists(path), path
    assert "agree" not in (title + snippet + desc + lic + credit).lower(), title
    extent = QUAD_EXTENT.get(title) or (AVA if title.startswith("4") else None)
    meta = {"snippet": snippet, "description": desc, "licenseInfo": lic, "accessInformation": credit, "tags": ",".join(TAGS),
            "culture": CULTURE, **({"extent": extent} if extent else {})}
    it = existing.get(title) or next((existing[t] for t in WAS.get(title, ()) if t in existing), None)
    if it is not None:
        how = "updated" if it.title == title else "retitled"
        it.update(item_properties={"title": title, **meta}, data=path)
    else:
        props = ItemProperties(title=title, item_type=typ, tags=TAGS, snippet=snippet, description=desc,
                               license_info=lic, access_information=credit, culture=CULTURE, extent=extent)
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
