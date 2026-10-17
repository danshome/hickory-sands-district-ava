"""Dashboard for the PROPOSED boundary, in Dan's folder, shared only to the private group: one page that organizes
everything in the group for TTB's reviewer.
- header: the docket, and a selector for which steps to show (petition wording near Grit, new around the granite lobe,
  the two corrections to Notice No. 243's wording, (49) and (85), unchanged from Notice No. 243's text);
- left: the AVA's area, the steps shown, how many differ from Notice No. 243, the big differences from the AVA Map
  Explorer polygon and the acres
  between the two boundaries from the same text drawn differently; tabs with every item in the group by number, the 13 USGS quadrangles (GeoPDF, GeoTIFF, the steps
  on each), and what changes and how the line is drawn (taken from the package README, so it matches the build);
- centre: the web map 4a (quadrangles, geology, the Map Explorer polygon, the proposed revision, the differences);
Wording (Dan, 2026-10-16): the official names, Notice No. 243, the AVA Map Explorer polygon, the proposed revision; never
"ours" against "TTB's".
- right: the 104 steps, the big differences and all the differences, as lists that zoom the map, and the selected
  step's record; a tab on the left sets out the change near Grit, acre by acre, with its granite.
On a phone (narrow screens; issue #49) ArcGIS Dashboards shows a second layout, the mobileView, with its own copies of
the elements (ids "mobile-" + the desktop name; elementMappings pairs each with its desktop twin):
- header: the title and one line; the step selector is in the drawer (a phone header holds text and images only);
- top: the AVA's area, the steps reworded and the big differences; then the same web map, half the screen;
- below it, tabs: the steps (tap one to zoom the map; the list item holds the step's whole record), what changes,
  the change near Grit (its table as stacked rows) and the documents (one large link each).
Both views are built from the same builders and data below, so they cannot drift; check_views() (in
agol_dryrun_checks.py) stops the publish if an element is not placed, or an action points outside its own view.
Items are found by title in the folder at run time (their ids change if they are republished). Re-running updates the
dashboard in place. Sign-in: GIS(profile="hsd"). Never write "agreed".
build() makes the dashboard without signing in (from the build, the items and the layers it is given), so the publish dry
run (agol_dryrun.py) writes and checks it; main() signs in, reads the live items and layers, and sends it.
Run by ./build.sh publish after agol_layer.py (or .venv/bin/python src/publish/agol_dashboard.py)"""
import html, json, os, re, uuid
from arcgis.gis import GIS, ItemProperties, ItemTypeEnum
from arcgis.features import FeatureLayerCollection
from agol_dryrun_checks import check_views   # src/publish/, next to this script

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))   # the repository root
HERE = os.environ.get("HSD_WORK") or os.path.join(ROOT, "target", "work")   # build work dir
SQMI = "%.2f" % json.load(open(os.path.join(HERE, "agreed-steps.json")))["sqmi"]   # the built AVA area, GRS80 square miles
STATS = json.load(open(os.path.join(HERE, "review", "ttb-diff-stats.json")))
same = STATS["areas"]["drawing"]   # acres between the two boundaries from the same text drawn differently
change = STATS["areas"]["proposed text change"]
GRIT = json.load(open(os.path.join(HERE, "review", "grit-change-stats.json")))   # src/review/grit_change.py
README = os.path.join(HERE, "README.txt")
FOLDER = "Hickory Sands District - Final Proposed Boundary and Narrative"
GROUP_ID = "65720ee9c5a743f88659ae39228704ec"
TITLE = "0 Dashboard - the proposed boundary and everything in this group"
MAP_TITLE = "4a Proposed boundary - map over the 13 USGS quadrangles"
LAYER_TITLE = "4b Proposed boundary - layer (AVA polygon, 104 steps, step endpoints)"
DIFF_TITLE = "4k Differences from the AVA Map Explorer polygon - layer (the big ones, and all of them)"
SAME_TEXT = "the same text, drawn differently"   # the cause agol_layer.py gives the pieces not from the text change
CREDIT = "Dan McLaughlin, Robert Clay Vineyards (petitioner)"
CC0 = ("CC0 1.0 Universal (public domain dedication): no rights reserved. TTB, its contractors and anyone else may copy, "
       "change and use this for any purpose without permission or attribution. https://creativecommons.org/publicdomain/zero/1.0/")
# the dashboard shows more than the petitioner's work, so its license and credits name each part (QA #30)
LIC = ("The dashboard and the petitioner's layers (the proposed revision, the differences, the change near Grit, the shift of the "
       "geology): " + CC0 + " The step text it shows is Notice No. 243's, a U.S. Government work (public domain), except the "
       "proposed changes near Grit (CC0, as above). The AVA Map Explorer polygon (TTB's AVAs_Production layer): U.S. Government "
       "work (public domain). USGS quadrangles and USGS SGMC geology: public domain. Basemaps: Esri, under Esri's terms of use.")
CREDITS = (CREDIT + "; TTB (Notice No. 243 step text, AVAs_Production layer); USGS (quadrangles, via Esri USA Historical Topo "
           "Maps; SGMC geology); basemaps: Esri")
TAGS = ["Hickory Sands District", "AVA", "TTB", "Notice No. 243", "TTB-2026-0005", "proposed boundary", "dashboard"]
CULTURE = "en-us"
TYPE_KEYWORDS = ["ArcGIS Dashboards", "Dashboard", "Operations Dashboard"]   # set when the item is added
ABOUT = ("<p>Hickory Sands District AVA (Docket No. TTB-2026-0005, Notice No. 243, 91 FR 52576): the boundary the petitioners "
         "propose, with the changes discussed with TTB on October 15, 2026. Prepared by Dan McLaughlin, Robert Clay Vineyards "
         "(petitioner).</p>")
SECTIONS = {"0": "Start here", "1": "1 Boundary description as proposed", "2": "2 Notice No. 243 with the proposed changes highlighted",
            "3": "3 Changes side by side", "4": "4 GIS data: the map, the layers and the downloads", "5": "5 USGS quadrangles with the boundary"}
WINE, INK = "#5a1e2e", "#8a1c1c"

def wid(name):   # stable element ids, so a re-run changes only what changed
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "hickory-sands-district-dashboard/" + name))
MAP, LIST, DIFFS, ALLD, DETAILS, SELECT = wid("map"), wid("steps"), wid("differences"), wid("all-differences"), wid("details"), wid("selector")
IND = {k: wid("indicator-" + k) for k in ("area", "steps", "changed", "places", "acres")}
TXT = {k: wid("text-" + k) for k in ("documents", "quads", "about", "grit")}
def mwid(name):   # the phone layout's twin of the element wid(name)
    return wid("mobile-" + name)
M_MAP, M_LIST, M_SELECT = mwid("map"), mwid("steps"), mwid("selector")
M_IND = {k: mwid("indicator-" + k) for k in ("area", "changed", "places")}
M_TXT = {k: mwid("text-" + k) for k in ("about", "grit", "documents")}
TWINS = {MAP: M_MAP, LIST: M_LIST, SELECT: M_SELECT, **{IND[k]: M_IND[k] for k in M_IND}, **{TXT[k]: M_TXT[k] for k in M_TXT}}
PHONE = '<div style="font-size:15px;line-height:1.5">'   # the phone's text: 15 px, its small print 13 px (desktop 13 and 11)

def build(items, wm, ops, line, area, rings_oid, steps, url):
    """The dashboard's JSON and its item properties, built without signing in or sending anything, from the build's outputs
    and: the items in the folder (title -> item, with .id and .title), the web map 4a (.id) and the ids of its operational
    layers (ops), the boundary layer 4b's line and area layers (.properties.id, .objectIdField), the big differences
    layer's object id field, the steps' records (step, quad, change) and the portal's URL. main() passes the live ones;
    the publish dry run (agol_dryrun.py) passes stand-ins. Returns (dashboard, props)."""
    LINE_OP, AREA_OP, RINGS_OP, ALL_OP = f"hsd-{line.properties.id}", f"hsd-{area.properties.id}", "hsd-rings", "hsd-all-differences"   # ids set by agol_layer.py
    assert {LINE_OP, AREA_OP, RINGS_OP, ALL_OP} <= ops, ops
    OID = line.properties.objectIdField
    RINGS_OID = rings_oid

    def ds(op):
        return {"type": "layerDataSource", "itemId": wm.id, "layerId": op}
    def dataset(op, **kw):
        return {"type": "serviceDataset", "name": "main", "dataSource": ds(op), "groupByFields": [], "orderByFields": [],
                "statisticDefinitions": [], "outFields": ["*"], "returnDistinctValues": False, "allowSourceDownload": False,
                "allowSummaryDownload": False, **kw}
    def target(element, by="whereClause", selection=False, **kw):
        return {"targetId": element, "by": by, "requiresSelection": selection, **kw}
    def widget(id_, name, type_, **kw):
        return {"id": id_, "dashboardItemType": "widget", "name": name, "type": type_, "noDataState": {}, "noFilterState": {},
                "focusModeEnabled": False, **kw}
    def page(it):   # the item's page: its description, license and download (an item's /data link would only download)
        return f"{url}/home/item.html?id={it.id}"
    def link(it, text=None):
        return (f'<a href="{page(it)}" target="_blank" rel="noopener noreferrer">'
                f'{html.escape(text or it.title.split(" ", 1)[1])}</a>')
    def button(url, title, note=""):   # a link the size of a finger, for the phone: "Title - note" -> title, note below it
        return (f'<a href="{url}" target="_blank" rel="noopener noreferrer" style="display:block;padding:12px 14px;margin:0 0 10px;'
                f'border:1px solid #d9c3c8;border-radius:8px;background:#faf6f7;color:{WINE};text-decoration:none;font-size:16px;'
                f'line-height:1.35"><strong>{html.escape(title)}</strong>'
                + (f'<br><span style="font-size:14px;color:#555">{html.escape(note)}</span>' if note else "") + "</a>")
    def item_button(it):
        return button(page(it), *it.title.split(" ", 1)[1].split(" - ", 1))
    def spans(nums):   # 1,2,3,7,9,10 -> (1)-(3), (7), (9)-(10)
        out, nums = [], sorted(nums)
        for n in nums:
            if out and n == out[-1][1] + 1:
                out[-1][1] = n
            else:
                out.append([n, n])
        return ", ".join(f"({a})" if a == b else f"({a})-({b})" for a, b in out)

    # ---------------------------------------------------------------- the three text tabs
    docs = sorted((t, it) for t, it in items.items() if t != TITLE and re.match(r"\d[a-z]? ", t))
    parts = ['<div style="font-size:13px;line-height:1.45">']
    for key, head in SECTIONS.items():
        group_items = [it for t, it in docs if t[0] == key]
        if not group_items:
            continue
        parts.append(f'<p style="margin:10px 0 2px"><strong>{html.escape(head)}</strong></p>')
        if key == "5":
            parts.append(f"<p>The {sum(1 for it in group_items if 'GeoPDF' in it.title)} quadrangles as GeoPDF and GeoTIFF, "
                         "with the boundary added as a solid red line: see the <em>USGS quadrangles</em> tab.</p>")
            continue
        parts.append("<ul style=\"margin:0;padding-left:18px\">" + "".join(
            f"<li><span style=\"color:#666\">{html.escape(it.title.split(' ', 1)[0])}</span> {link(it)}</li>" for it in group_items) + "</ul>")
    parts.append("</div>")
    documents_html = "".join(parts)
    numbered = {t.split(" ", 1)[0]: it for t, it in docs}
    for n in ("0", "1a", "2a", "3a"):
        assert n in numbered, f"no item {n} in the folder for the phone's Documents tab"
    group_button = button(f"{url}/home/group.html?id={GROUP_ID}", "Everything in the group",
                          "the Word files, the GIS data and the 13 USGS quadrangles")
    documents_phone = (PHONE + '<p style="margin:0 0 10px">Each opens the item\'s page, where it can be read or downloaded.</p>'
                       + "".join(item_button(numbered[n]) for n in ("0", "1a", "2a", "3a")) + group_button + "</div>")

    quads = {}
    for t, it in docs:
        m = re.match(r"5[ab] .*\((GeoPDF|GeoTIFF)\) - (.+), TX \((\d{4}[^)]*)\)$", t)   # "(1962, photorevised 1982)", as paragraph (b)
        if m:
            sheet = quads.setdefault(m.group(2), {"edition": m.group(3)})
            sheet[m.group(1)] = it
            sheet["edition"] = max(sheet["edition"], m.group(3), key=len)   # one row even if only one of the pair is retitled yet
    rows = "".join(f'<tr><td style="padding:3px 6px">{html.escape(q)}, TX ({f["edition"]})</td>'
                   f'<td style="padding:3px 6px;white-space:nowrap">{link(f["GeoPDF"], "GeoPDF")}</td>'   # never "GeoPD / F" (QA #47)
                   f'<td style="padding:3px 6px;white-space:nowrap">{link(f["GeoTIFF"], "GeoTIFF")}</td>'
                   f'<td style="padding:3px 6px">{spans(s["step"] for s in steps if s["quad"] == q) or "-"}</td></tr>'
                   for q, f in sorted(quads.items()))
    quads_html = ('<div style="font-size:13px"><p>The 13 USGS 1:24,000 quadrangles cited in paragraph (b), each with the boundary '
                  "added as a solid red line. The GeoPDF is the USGS file with the line as an optional-content layer; in the GeoTIFF "
                  "only the image tiles the line crosses are rewritten. The quads keep their NAD27 grids; the NAD83 line is carried "
                  "onto them with the NADCON 5.0 CONUS grid.</p>"
                  '<table style="border-collapse:collapse;width:100%"><tr style="text-align:left;border-bottom:1px solid #ccc">'
                  "<th style=\"padding:3px 6px\">Quadrangle</th><th style=\"padding:3px 6px\" colspan=\"2\">Files</th>"
                  f"<th style=\"padding:3px 6px\">Steps</th></tr>{rows}</table>"
                  '<p style="color:#666">Each step is listed under the one quadrangle named in its record; a step that crosses '
                  "onto another map is listed once.</p></div>")

    def readme_section(start):
        """a section of the package README as HTML: paragraphs, and '- ' bullets with their indented continuation lines"""
        lines = open(README, encoding="utf-8").read().splitlines()
        i = next(k for k, s in enumerate(lines) if s.startswith(start))
        out, para, bullets = [], [], []
        def flush():
            if para:
                out.append("<p>" + html.escape(" ".join(para)) + "</p>"); para.clear()
            if bullets:
                out.append("<ul style=\"margin:0 0 6px;padding-left:18px\">" + "".join(f"<li>{html.escape(b)}</li>" for b in bullets) + "</ul>"); bullets.clear()
        for s in lines[i + 1:]:
            if s and not s.startswith(" "):
                break
            t = s.strip()
            if not t:
                flush()
            elif t.startswith("- "):
                if para:
                    out.append("<p>" + html.escape(" ".join(para)) + "</p>"); para.clear()
                bullets.append(t[2:])
            elif bullets and s.startswith("     "):
                bullets[-1] += " " + t
            else:
                if bullets:
                    flush()
                para.append(t)
        flush()
        return "".join(out)
    head = open(README, encoding="utf-8").read().splitlines()[:3]
    CHANGES = readme_section("WHAT WE PROPOSE TO CHANGE")
    MAP_RED = f"Red: the proposed revision, {SQMI} square miles."   # the map's key, in both views
    MAP_BLUE = "Blue: the AVA Map Explorer polygon for Notice No. 243, from TTB's live AVAs_Production layer."
    MAP_SHADED = ("Shaded: every piece of land between them (red: in the proposed revision only; blue: in the Map Explorer polygon "
                  "only; grey: the proposed text change near Grit)")
    MAP_RINGED = (f"Ringed: the {STATS['big']} big differences, where the lines are {STATS['big_m']:.0f} m or more apart (orange: the "
                  "two lines take different paths; grey dashed: the proposed text change near Grit)")
    MAP_BASEMAPS = ("In the map's layer list, <em>TTB's AVA Map Explorer basemaps</em> holds the Map Explorer's four basemaps "
                    "(Topographic, Streets, Imagery, USA Topo Maps): turn it on and pick one.")
    about_html = ('<div style="font-size:13px;line-height:1.45">'
                  f"<p>{html.escape(head[1])}<br>{html.escape(head[2].replace('(see LICENSE.txt)', '(full text in item 0, the read me)'))}</p>"
                  "<p style=\"margin:10px 0 2px\"><strong>What the proposed revision changes in Notice No. 243</strong></p>"
                  + CHANGES +
                  "<p style=\"margin:10px 0 2px\"><strong>How the line is drawn</strong></p>" + readme_section("HOW THE LINE IS DRAWN") +
                  "<p style=\"margin:10px 0 2px\"><strong>The map</strong></p>"
                  f"<p>{MAP_RED} {MAP_BLUE} The Map Explorer polygon was digitized by hand and the proposed revision follows the printed "
                  f"linework, so the two differ a little almost everywhere (median {STATS['median_m']:.0f} m apart, measured every 2 m along "
                  f"each line). {MAP_SHADED}; from the same text drawn differently they add up to {same['revision_only_acres']:,.0f} acres "
                  f"in the proposed revision only and {same['map_explorer_only_acres']:,.0f} in the Map Explorer polygon only. {MAP_RINGED}. "
                  "Under them: the USGS geologic units "
                  "(Town Mountain Granite, younger granitic intrusions, Hickory Sandstone Member formation), shifted about 400 m to "
                  f"sit on the outcrops, and the 13 USGS quadrangles. {MAP_BASEMAPS}</p></div>")
    about_phone = (PHONE + '<p style="margin:0 0 4px"><strong>What the proposed revision changes in Notice No. 243</strong></p>' + CHANGES
                   + f'<p style="margin:12px 0 4px"><strong>On the map</strong></p><p>{MAP_RED} {MAP_BLUE} {MAP_SHADED}. {MAP_RINGED}.</p>'
                   f"<p>{MAP_BASEMAPS}</p>"
                   '<p style="margin:12px 0 4px"><strong>Every change, step by step</strong></p>'
                   + item_button(numbered["3a"]) + item_button(numbered["2a"]) + "</div>")

    A = GRIT["areas"]
    def ac(x): return f"{int(x + 0.5):,}"   # whole acres, rounded once, half up, from the build's unrounded stats (issue #33)
    def grow(key, label):
        r = A[key]
        return (f'<tr><td style="padding:3px 6px">{label}</td><td style="padding:3px 6px;text-align:right;white-space:nowrap">{ac(r["acres"])}</td>'
                f'<td style="padding:3px 6px;text-align:right;white-space:nowrap">{ac(r["granite_acres"])}</td>'
                f'<td style="padding:3px 6px;text-align:right;white-space:nowrap">{ac(r["sandstone_acres"])}</td></tr>')
    def gblock(key, label):   # a row of the table as a paragraph, for the phone (no wide tables)
        r = A[key]
        return (f'<p style="margin:8px 0 0"><strong>{label}</strong><br>{ac(r["acres"])} acres &middot; granite {ac(r["granite_acres"])} '
                f'&middot; sandstone* {ac(r["sandstone_acres"])}</p>')
    def key(color, dash, label):
        return (f'<li><span style="display:inline-block;width:26px;border-top:4px {"dashed" if dash else "solid"} {color};vertical-align:middle;'
                f'margin-right:6px"></span>{label}</li>')
    GRIT_LINES = (("#005aff", True, "Replaced: Notice No. 243 steps (10)-(11), (90)-(92), as drawn by the petitioner on the USGS maps"),
                  ("#008c3c", False, "Put back: the petition's wording, (10)-(11), (90)-(92), (97)-(100)"),
                  ("#be0082", False, "New: (93)-(96), around the granite lobe"),
                  ("#008c3c", True, "Replaced: the petition's straight line from the marked 1,737 to the marked 1,762"))
    GRIT_AREAS = (("Notice No. 243, not the petition", "In Notice No. 243's text, left out by the petition"),
                  ("granite lobe", "Granite lobe, also left out now by (93)-(96)"),
                  ("put back", "Put back, between the marked 1,737 and the windmill"),
                  ("lane wording", "Added by the petition's lane wording, (10)-(11)"),
                  ("petition, not Notice No. 243", "In the petition, not Notice No. 243's text, (99)-(100)"))
    reworded = [s["step"] for s in steps if "unchanged" not in (s["change"] or "")]   # as the indicator counts them
    FIX = "text correction"   # how build_agreed.py's change notes for (49) and (85) start: Notice No. 243's wording corrected
    fixes = [s["step"] for s in steps if FIX in (s["change"] or "")]
    near_grit = [n for n in reworded if n not in fixes]
    def and_list(nums):   # 49, 85 -> (49) and (85)
        s = [f"({n})" for n in sorted(nums)]
        return s[0] if len(s) == 1 else ", ".join(s[:-1]) + " and " + s[-1]
    REWORDED = (f"All {len(reworded)} steps worded differently from Notice No. 243 (<em>Steps reworded</em>, at the top) are here, "
                f"near Grit: {spans(reworded)}." if not fixes else
                f"Of the {len(reworded)} steps worded differently from Notice No. 243 (<em>Steps reworded</em>, at the top), "
                f"{len(near_grit)} are here, near Grit: {spans(near_grit)}. "
                + (f"The other one, {and_list(fixes)}, corrects Notice No. 243's own wording elsewhere, one word; " if len(fixes) == 1 else
                   f"The other {({2: 'two', 3: 'three', 4: 'four'}).get(len(fixes), len(fixes))}, {and_list(fixes)}, correct Notice "
                   "No. 243's own wording elsewhere, one word each; ")
                + "the line does not change.")
    def grit_tab(phone=False):   # the same text in both views; on the phone larger, and the table as stacked rows
        head = '<p style="margin:12px 0 4px">' if phone else '<p style="margin:10px 0 2px">'
        areas = ("".join(gblock(*a) for a in GRIT_AREAS) if phone else
                 '<table style="border-collapse:collapse;width:100%"><tr style="text-align:left;border-bottom:1px solid #ccc">'
                 '<th style="padding:3px 6px"></th><th style="padding:3px 6px;text-align:right">acres</th><th style="padding:3px 6px;text-align:right;white-space:nowrap">granite</th>'
                 '<th style="padding:3px 6px;text-align:right;white-space:nowrap">sandstone*</th></tr>' + "".join(grow(*a) for a in GRIT_AREAS) + "</table>")
        return ((PHONE if phone else '<div style="font-size:13px;line-height:1.45">')
                + "<p>Near Grit the proposed text puts back the petition's wording in place of "
                "Notice No. 243's steps (10)-(11) and (90)-(92), and adds steps (93)-(96) around a lobe of granite. Turn on <em>The change near Grit</em> in "
                "the map's layer list (on by default) to see each line and area.</p>"
                f"<p>{REWORDED} Every other step is Notice No. 243's text word for word.</p>"
                + head + '<strong>The lines</strong></p><ul style="list-style:none;padding-left:4px;margin:0">'
                + "".join(key(*k) for k in GRIT_LINES) + "</ul>"
                + head + "<strong>The areas</strong> (granite: Town Mountain Granite and younger granitic intrusions; "
                "USGS SGMC shifted to the outcrops)</p>" + areas
                + ('<p style="font-size:13px;color:#555;margin-top:4px">' if phone else '<p style="font-size:11px;color:#666;margin-top:2px">')
                + "* the Hickory Sandstone Member formation</p>"
                f'<p style="margin-top:8px">The AVA drawn three ways: Notice No. 243\'s text {GRIT["sqmi"]["notice_243"]:.2f} square miles; the petition '
                f'{GRIT["sqmi"]["petition"]:.2f}; the proposed revision {GRIT["sqmi"]["revision"]:.2f}. All three are drawn the same way, on the '
                "printed linework of the USGS maps; none is taken from the AVA Map Explorer polygon.</p></div>")
    grit_html, grit_phone = grit_tab(), grit_tab(phone=True)

    # ---------------------------------------------------------------- elements
    def indicator(id_, k, captions):   # the same number in both views (IND_DATA), with each view's captions
        name, op, stat, digits, flt = IND_DATA[k]
        top, bottom = captions[k]
        return widget(id_, name, "indicatorWidget",
                      datasets=[dataset(op, statisticDefinitions=[stat], **({"filter": flt} if flt else {}))],
                      defaultSettings={"topSection": {"maxHeight": 30, "textInfo": {"text": top, "weight": "normal"}},
                                       "middleSection": {"maxHeight": 45, "textInfo": {"text": "{calculated/value}", "weight": "bold", "fillColor": WINE}},
                                       "bottomSection": {"maxHeight": 25, "textInfo": {"text": bottom, "weight": "normal"}}},
                      verticalAlignment="middle", comparison="none", valueType="statistic", noValueState={}, showFeatureMenu=False,
                      valueFormat={"name": "value", "prefix": False, "style": "decimal", "useGrouping": True,
                                   "minimumFractionDigits": digits, "maximumFractionDigits": digits},
                      percentageFormat={"name": "percentage", "prefix": False, "style": "percent", "useGrouping": True},
                      ratioFormat={"name": "ratio", "prefix": False, "style": "decimal", "useGrouping": True, "maximumFractionDigits": 2})
    count = {"onStatisticField": OID, "statisticType": "count", "outStatisticFieldName": "value"}
    changed = {"type": "filterGroup", "condition": "AND", "rules": [{"type": "filterRule", "field": {"name": "change", "type": "string"},
                                                                      "operator": "not_contains", "constraint": {"type": "value", "value": "unchanged"}}]}
    IND_DATA = {   # key: name, layer, statistic, decimals, filter
        "area": ("AVA area", AREA_OP, {"onStatisticField": "area_sqmi", "statisticType": "max", "outStatisticFieldName": "value"}, 2, None),
        "steps": ("Steps shown", LINE_OP, count, 0, None),
        "changed": ("Steps worded differently from Notice No. 243", LINE_OP, count, 0, changed),
        "places": ("Big differences", RINGS_OP, {"onStatisticField": RINGS_OID, "statisticType": "count", "outStatisticFieldName": "value"}, 0, None),
        "acres": ("Land between the boundaries", ALL_OP, {"onStatisticField": "acres", "statisticType": "sum", "outStatisticFieldName": "value"}, 0,
                  {"type": "filterGroup", "condition": "AND", "rules": [{"type": "filterRule", "field": {"name": "cause", "type": "string"},
                                                                        "operator": "equal", "constraint": {"type": "value", "value": SAME_TEXT}}]})}
    CAPTIONS = {"area": ("AVA as proposed", "sq mi (GRS 1980)"), "steps": ("Steps shown", f"of {len(steps)}"),
                "changed": ("Steps reworded", "from Notice No. 243"),
                "places": (f"Big differences ({STATS['big_m']:.0f} m+)", "from the Map Explorer polygon"),
                "acres": ("Acres between the boundaries", "same text, drawn differently")}
    PHONE_CAPTIONS = {"area": ("AVA area", "sq mi"), "changed": ("Steps reworded", "from Notice No. 243"),
                      "places": ("Big differences", f"{STATS['big_m']:.0f} m+ apart")}   # a third of a phone's width each: short
    indicators = [indicator(IND[k], k, CAPTIONS) for k in IND]

    def zoom_and_flash(map_id):
        return [{"type": "flashGeometry", "targets": [target(map_id, "geometry")]}, {"type": "zoom", "targets": [target(map_id, "geometry")]}]
    def map_widget(id_, phone=False, layers=()):
        """the web map 4a. The phone's: no measure tool, a locate button (is this place in the AVA?), and no selection by
        tapping (nothing on the phone listens to it); pop-ups stay on, to tell what a tapped line or area is."""
        return widget(id_, "Map", "mapWidget", itemId=wm.id, flashRepeats=3, linkedMapWidgetIds=[], pointZoomScale=10000,
                      mapTools=[{"type": "mapContentsTool"}, {"type": "legendTool"}], showMeasureTool=not phone, showNavigation=True,
                      showPanRotate=False, showLocate=phone, showCompass=False, showPopup=True, scalebarStyle="line", editingEnabled=False,
                      selectionColor="#00b4ff", highlightColor="#00b4ff", trackedFeatureColor="#0000ff", trackedFeatureRadius=100,
                      **({"layers": list(layers)} if layers else {}),
                      selectTool={"type": "selectTool", "clickToSelect": not phone, "advanceSketchTools": []})
    STEP_ITEM = (f'<p><span style="font-size:13px">{{field/narrative}}</span></p>'
                 f'<p><span style="font-size:11px;color:{INK}">{{field/change}}</span><span style="font-size:11px;color:#777"> &middot; '
                 "{field/quad} quad &middot; {field/length_m} m</span></p>")
    STEP_PHONE = ('<p><span style="font-size:15px">{field/narrative}</span></p>'   # the phone has no details panel: the whole record
                  f'<p><span style="font-size:13px;color:{INK}">{{field/change}}</span></p>'
                  '<p><span style="font-size:13px;color:#555">Ends at {field/endpoint} &middot; {field/quad} quad &middot; '
                  "{field/length_m} m &middot; {field/txt_source}</span></p>")
    def steps_list(id_, map_id, details=None, phone=False):
        filter_details = [{"type": "filter", "targets": [target(details + "#main", selection=True)]}] if details else []
        return widget(id_, "Steps", "listWidget", datasets=[dataset(LINE_OP, orderByFields=["step ASC"], maxFeatures=200)],
                      events=[{"type": "selectionChanged", "actions": filter_details + zoom_and_flash(map_id)}],
                      selectionMode="single", iconType="none", showFilter=True, separatorColor="#dddddd", selectionColor="#f3e3e6",
                      text=STEP_PHONE if phone else STEP_ITEM,
                      **({"topCaption": '<p style="font-size:14px;margin:4px 6px">Tap a step to show it on the map.</p>'} if phone else {}))
    def text_widget(id_, name, text):
        return widget(id_, name, "richTextWidget", datasets=[], valueType="none", showFeatureMenu=False, text=text)
    widgets = [
        map_widget(MAP, layers=[{"type": "layer", "dataSource": ds(LINE_OP), "events": [{"type": "selectionChanged", "actions": [   # the list's selection gates the details
            {"type": "filter", "targets": [target(DETAILS + "#main")]}]}]}]),
        steps_list(LIST, MAP, details=DETAILS),
        widget(DIFFS, "Big differences from the Map Explorer polygon", "listWidget", datasets=[dataset(RINGS_OP, orderByFields=["n ASC"], maxFeatures=100)],
               events=[{"type": "selectionChanged", "actions": zoom_and_flash(MAP)}], selectionMode="single", iconType="none", showFilter=False,
               separatorColor="#dddddd", selectionColor="#fdebd9",
               text=('<p><span style="font-size:13px"><strong>#{field/n}</strong> &middot; step(s) {field/steps}: up to {field/max_apart_m} m apart '
                     "over {field/length_m} m</span></p>"
                     f'<p><span style="font-size:11px;color:{INK}">{{field/why}}</span><span style="font-size:11px;color:#777"> &middot; '
                     "in the proposed revision only: {field/revision_only_acres} ac &middot; in the Map Explorer polygon only: "
                     "{field/map_explorer_only_acres} ac</span></p>")),
        widget(ALLD, "All differences between the two lines", "listWidget", datasets=[dataset(ALL_OP, orderByFields=["acres DESC"], maxFeatures=2000)],
               events=[{"type": "selectionChanged", "actions": zoom_and_flash(MAP)}], selectionMode="single", iconType="none", showFilter=False,
               separatorColor="#dddddd", selectionColor="#e8eef9",
               topCaption=(f'<p style="font-size:12px;margin:4px 6px">Every piece of land in one line and not the other, largest first. '
                           f"Same text drawn differently: <strong>{same['revision_only_acres']:,.0f} acres</strong> in the proposed revision only and "
                           f"<strong>{same['map_explorer_only_acres']:,.0f} acres</strong> in the AVA Map Explorer polygon only, in {same['pieces']} pieces. "
                           f"The proposed text change near Grit: {change['revision_only_acres']:,.0f} and {change['map_explorer_only_acres']:,.0f} acres, "
                           f"in {change['pieces']} pieces.</p>"),
               text=('<p><span style="font-size:13px"><strong>{field/acres} ac</strong> &middot; {field/side}</span></p>'
                     '<p><span style="font-size:11px;color:#777">{field/cause} &middot; steps {field/steps} &middot; {field/length_m} m long '
                     "&middot; up to {field/widest_m} m apart</span></p>")),
        widget(DETAILS, "Selected step", "detailsWidget", datasets=[dataset(LINE_OP, maxFeatures=1)], mapWidgetId=MAP, showTitle=True,
               showContents=True, showMedia=True, showAttachments=False, showFeatureMenu=False),
        text_widget(TXT["documents"], "Documents", documents_html),
        text_widget(TXT["quads"], "USGS quadrangles", quads_html),
        text_widget(TXT["about"], "About", about_html),
        text_widget(TXT["grit"], "The change near Grit", grit_html),
        *indicators]
    phone_widgets = [map_widget(M_MAP, phone=True), *(indicator(M_IND[k], k, PHONE_CAPTIONS) for k in M_IND),
                     steps_list(M_LIST, M_MAP, phone=True), text_widget(M_TXT["about"], "What changes", about_phone),
                     text_widget(M_TXT["grit"], "The change near Grit", grit_phone), text_widget(M_TXT["documents"], "Documents", documents_phone)]

    CHOICES = (("1", "Petition wording near Grit", "petition wording"), ("2", "New: around the granite lobe", "NEW"),
               ("4", "Corrections to Notice No. 243's wording", FIX), ("3", "Unchanged from Notice No. 243", "unchanged"))
    for s in steps:   # the filter is "contains": every step in exactly one choice, matched with or without case
        for fold in (str, str.lower):
            hits = [value for _, _, value in CHOICES if fold(value) in fold(s["change"] or "")]
            assert len(hits) == 1, ("step selector", s["step"], s["change"], hits)
    def step_selector(id_, targets, phone=False):   # which steps to show, by the `change` field; on the phone in the drawer
        return {"id": id_, "dashboardItemType": "selector", "name": "Steps to show", "noDataState": {}, "noFilterState": {},
                "focusModeEnabled": False, "label": "Steps", "placeholderText": f"All {len(steps)} steps", "showActionButtons": True,
                "type": "categorySelectorWidget", "category": {"type": "static"}, "selection": {"operator": "contains", "type": "multiple"},
                "showFilter": False, "displayType": "list", "maxSize": "none" if phone else "compact",
                "presentationMode": "drilldown" if phone else "dropdown",
                "datasets": [{"type": "staticDataset", "name": "main", "data": {"type": "staticValues", "dataType": "string", "values": [
                    {"type": "labelledValue", "id": i, "label": label, "value": value} for i, label, value in CHOICES]}}],
                "events": [{"type": "selectionChanged", "actions": [{"type": "filter", "targets": [
                    target(t, fieldMap=[{"sourceName": "filterField", "targetName": "change"}]) for t in targets]}]}]}
    selector = step_selector(SELECT, (LIST + "#main", f"{MAP}#{LINE_OP}", IND["steps"] + "#main", IND["changed"] + "#main"))
    phone_selector = step_selector(M_SELECT, (M_LIST + "#main", f"{M_MAP}#{LINE_OP}", M_IND["changed"] + "#main"), phone=True)

    COLS = (0.33, 0.41, 0.26)   # left, map, right: shares of the width (QA #45: 0.27/0.45/0.28, then 0.3/0.42/0.28)
    ROWS = (0.25, 0.23, 0.52)   # left column: indicators, indicators, tabs: shares of the height (QA #45: room for two-line captions at 1280x720)
    PHONE_ROWS = (0.12, 0.52, 0.36)   # the phone, top to bottom: indicators, map, tabs: shares of the screen below the header
    assert abs(sum(COLS) - 1) < 1e-9 and abs(sum(ROWS) - 1) < 1e-9 and abs(sum(PHONE_ROWS) - 1) < 1e-9
    def item(id_, w=1, h=1, **kw):
        return {"type": "itemLayoutElement", "id": id_, "width": w, "height": h, **kw}
    def stack(orientation, elements, name, w=1, h=1, ids=wid):
        return {"type": "stackLayoutElement", "orientation": orientation, "id": ids("layout-" + name), "width": w, "height": h, "elements": elements}
    phone_layout = {"type": "dockingLayout", "rootElement": stack("row", [   # one column: rows top to bottom
        stack("col", [item(M_IND[k], 1 / 3) for k in M_IND], "indicators", h=PHONE_ROWS[0], ids=mwid),
        item(M_MAP, h=PHONE_ROWS[1]),
        {"type": "tabsLayoutElement", "id": mwid("layout-tabs"), "width": 1, "height": PHONE_ROWS[2], "elements": [
            item(M_LIST, tabName="Steps"), item(M_TXT["about"], tabName="What changes"), item(M_TXT["grit"], tabName="Grit"),
            item(M_TXT["documents"], tabName="Documents")]}], "root", ids=mwid)}
    layout = {"type": "dockingLayout", "rootElement": stack("col", [
        stack("row", [
            stack("col", [item(IND[k], 1 / 3) for k in ("area", "steps", "changed")], "indicators", h=ROWS[0]),
            stack("col", [item(IND[k], 0.5) for k in ("places", "acres")], "indicators-2", h=ROWS[1]),
            {"type": "tabsLayoutElement", "id": wid("layout-tabs-left"), "width": 1, "height": ROWS[2], "elements": [
                item(TXT["documents"], tabName="Documents"), item(TXT["grit"], tabName="The change near Grit"),
                item(TXT["about"], tabName="What changes"), item(TXT["quads"], tabName="USGS quadrangles")]}],
            "left", w=COLS[0]),
        item(MAP, COLS[1]),
        stack("row", [
            {"type": "tabsLayoutElement", "id": wid("layout-tabs-right"), "width": 1, "height": 0.6, "elements": [
                item(LIST, tabName="Steps"), item(DIFFS, tabName="Big differences"), item(ALLD, tabName="All differences")]},
            item(DETAILS, h=0.4)], "right", w=COLS[2])], "root")}

    def header(title, subtitle, phone=False):   # a phone header holds text and images only: its selector is in the drawer
        return {"type": "header", "dashboardItemType": "panel", "title": title, "subtitle": subtitle,
                "textColor": "#ffffff", "titleTextColor": "#ffffff", "backgroundColor": WINE, "logoSize": "small",
                "backgroundImageSizing": "fit-height", "normalBackgroundImagePlacement": "left", "horizontalBackgroundImagePlacement": "top",
                "showSignOutMenu": False, "subtitlePlacement": "below", "showMargin": not phone, "menuContents": [],
                **({} if phone else {"selectors": [selector]})}
    desktop_view = {"type": "desktop", "layout": layout, "widgets": widgets,
                    "header": header("Hickory Sands District AVA: the boundary as proposed to TTB",
                                     "Docket No. TTB-2026-0005, Notice No. 243 (91 FR 52576) - changes discussed with TTB on October 15, 2026 - "
                                     "prepared by Dan McLaughlin, Robert Clay Vineyards (petitioner)"),
                    "settings": {"allowElementResizing": True, "allowElementExpansion": True, "allowReset": True}}
    phone_view = {"type": "mobile", "layout": phone_layout, "widgets": phone_widgets,
                  "header": header("Hickory Sands District AVA: proposed boundary", "Notice No. 243, changes discussed with TTB Oct. 15, 2026",
                                   phone=True),
                  "drawer": {"type": "drawer", "dashboardItemType": "panel", "selectors": [phone_selector]},
                  "settings": {"allowElementResizing": False, "allowElementExpansion": True, "allowReset": False}}

    dashboard = {"version": "5.1.0", "authoringApp": "ArcGIS Dashboards", "authoringAppVersion": "5.1.0", "maxPaginationRecords": 50000,
                 "maxChartRecords": 10000, "timeZone": "system", "theme": {"id": "light", "type": "defined"},
                 "numberPrefixOverrides": [{"key": k, "symbol": s, "enabled": e} for k, s, e in (
                     ("yotta", "Y", True), ("zeta", "Z", True), ("exa", "E", True), ("peta", "P", True), ("tera", "T", True),
                     ("giga", "G", True), ("mega", "M", True), ("kilo", "k", True), ("base", "", True), ("deci", "d", False),
                     ("centi", "c", False), ("milli", "m", False), ("micro", "µ", False), ("nano", "n", False))],
                 "desktopView": desktop_view, "mobileView": phone_view, "elementMappings": TWINS}

    props = {"snippet": "Start here: the proposed revision on the 13 USGS quadrangles with the AVA Map Explorer polygon, the 104 steps, and every "
                        "document, map and download in this group.",
             "description": ABOUT + "<p>One page for the whole group: pick a step to see it on the map and read it; the differences from "
                            "the AVA Map Explorer polygon are listed and ringed on the map; the tabs link every document, the GIS data and the "
                            "13 USGS quadrangles.</p>",
             "tags": ",".join(TAGS), "licenseInfo": LIC, "accessInformation": CREDITS, "culture": CULTURE}
    return dashboard, props

def main():
    gis = GIS(profile="hsd")
    folder = gis.content.folders.get(FOLDER)
    group = gis.groups.get(GROUP_ID)
    items = {it.title: it for it in folder.list()}
    wm, fl, dl = items[MAP_TITLE], items[LAYER_TITLE], items[DIFF_TITLE]
    ops = {o["id"] for o in wm.get_data()["operationalLayers"]}
    layers = {lyr.properties.geometryType: lyr for lyr in FeatureLayerCollection.fromitem(fl).layers}
    line, area = layers["esriGeometryPolyline"], layers["esriGeometryPolygon"]
    rings_oid = next(x for x in FeatureLayerCollection.fromitem(dl).layers if "big" in x.properties.name.lower()).properties.objectIdField
    steps = [f.attributes for f in line.query(where="1=1", out_fields="step,quad,change", return_geometry=False).features]
    dashboard, props = build(items, wm, ops, line, area, rings_oid, steps, gis.url)
    check_views(dashboard, ops)
    text = json.dumps(dashboard)
    assert "agree" not in text.lower()
    assert "agree" not in json.dumps(props).lower()
    db = items.get(TITLE)
    if db is None:
        db = folder.add(ItemProperties(title=TITLE, item_type=ItemTypeEnum.DASHBOARD, tags=TAGS, snippet=props["snippet"],
                                       description=props["description"], license_info=LIC, access_information=CREDITS, culture=CULTURE,
                                       type_keywords=TYPE_KEYWORDS), text=text).result()
        how = "added"
    else:
        db.update(item_properties=props, data=text)
        how = "updated"
    try:
        db.sharing.groups.add(group)
    except AttributeError:
        db.share(groups=[GROUP_ID])
    print(how, db.id, db.type, db.title)
    print("open:", f"{gis.url}/apps/dashboards/{db.id}")

if __name__ == "__main__":
    main()
