"""Boundary description documents for the proposed boundary: the regulatory text in TTB's style (HTML for PDF/DOCX,
plain text), a CSV of the steps, and the changes from TTB's published text. Paragraphs (a)-(c) and steps are TTB's words
(Notice No. 243, 91 FR 52576, 52585-86) except where agreed-steps.json says otherwise."""
import csv, html, json, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))   # the repository root
HERE = os.environ.get("HSD_WORK") or os.path.join(ROOT, "target", "work")   # build work dir (build.sh stages resources/ here)
S = json.load(open(os.path.join(HERE, "agreed-steps.json")))
L = {f["properties"]["step"]: f["properties"] for f in json.load(open(os.path.join(HERE, "gis/hickory-sands-district-boundary-proposed-2026-10-15-line-EPSG4269.geojson")))["features"]}
OUT = os.path.join(HERE, "documents"); os.makedirs(OUT, exist_ok=True)
STEM = "Hickory-Sands-District-boundary-description-as-proposed-2026-10-15"

A = ("(a) Name. The name of the viticultural area described in this section is “Hickory Sands District”. "
     "For purposes of part 4 of this chapter, “Hickory Sands District” is a term of viticultural significance.")
B = ("(b) Approved maps. The 13 United States Geological Survey (USGS) 1:24,000 scale topographic map used to determine "
     "the boundary of the viticultural area are as follows:")
MAPS = ["(1) Long Mountain, TX., 1970;", "(2) Grit, TX., 1970;", "(3) Purdy Hill, TX., 1962;", "(4) Spy Rock, TX., 1963;",
        "(5) Fredonia, TX., 1962;", "(6) Katemcy, TX., 1970;", "(7) Voca, TX., 1963;", "(8) Pecan Springs, TX., 1963;",
        "(9) Pontotoc, TX., 1955;", "(10) Fly Gap, TX., 1962, photorevised 1982;", "(11) Mason, TX., 1967, photoinspected 1979;",
        "(12) Turtle Creek, TX., 1968; and", "(13) Sheep Run Creek, TX., 1968."]
C = ("(c) Boundary. The Hickory Sands District viticultural area is located in portions of Llano, Mason, McCulloch, "
     "and San Saba Counties, in Texas. The boundary of the Hickory Sands District viticultural area is as described as follows:")
steps = [s["text"] for s in S["steps"]]

# ---------- plain text
txt = ["§ 9.___ Hickory Sands District.", "", A, B] + ["    " + m for m in MAPS] + [C] + ["    " + t for t in steps]
open(os.path.join(OUT, STEM + ".txt"), "w", encoding="utf-8").write("\n".join(txt) + "\n")

# ---------- CSV
with open(os.path.join(OUT, STEM + "-steps.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["step", "text", "text_source", "change_from_TTB_published_text", "quad", "endpoint", "length_m"])
    for s in S["steps"]:
        p = L[s["step"]]
        w.writerow([s["step"], s["text"], s["source"], s["change"], p["quad"], p["endpoint"], p["length_m"]])

# ---------- HTML (PDF + DOCX)
e = html.escape
P = lambda t, cls="": f'<p{" class=%s" % cls if cls else ""}>{e(t)}</p>'
pet91 = ("Proceed north-easterly, then north-westerly, then north-easterly along Honey Creek to the marked 1727-foot "
         "elevation point at its intersection with State Highway 29; then")
corr = ("Proceed northeasterly, then northwesterly along Honey Creek <b>to its confluence with an unnamed, intermittent "
        "tributary, then northeasterly along the tributary</b> to the marked 1,727-foot elevation point at its intersection "
        "with US Highway 377; then")
import re as _re
assert pet91 == json.load(open(os.path.join(ROOT, "resources", "boundary", "description", "petition-steps.json")))["91"], "petition step 91 changed"
assert _re.sub("<[^>]+>", "", corr) == _re.sub(r"^\(90\)\s*", "", S["steps"][89]["text"]), "correction box out of step with step (90)"
rows = [("(1)–(9)", "TTB’s published text, unchanged", "Notice No. 243, steps (1)–(9)"),
        ("(10)–(11)", "Petition wording (out along the westbound lane of State Highway 29 and US Highway 377); replaces TTB’s steps (10)–(11)", "Petition steps 11–12"),
        ("(12)–(89)", "TTB’s published text, unchanged", "Notice No. 243, steps (12)–(89)"),
        ("(90)", "Petition wording, with one correction (below): names the unnamed, intermittent tributary the petition’s line follows from Honey Creek to the marked 1727", "Petition step 91"),
        ("(91)–(92)", "Petition wording (back along the eastbound lane of State Highway 29)", "Petition steps 92–93"),
        ("(93)–(96)", "New: around a lobe of granite northwest of the area near Grit, by a windmill, a fence line and Topaz Lane; replaces petition step 94 (a straight line from the marked 1737 to the marked 1762)", "Proposed; discussed with TTB, Oct. 15, 2026"),
        ("(97)–(100)", "Petition wording", "Petition steps 95–98"),
        ("(101)–(104)", "TTB’s published text, unchanged, renumbered from (93)–(96)", "Notice No. 243, steps (93)–(96)"),
        ("(10), (11), (90)–(92), (99)", "Style only, written the way TTB’s published text writes them: “US Highway” (the petition wrote “U.S. Highway”), “northeasterly” and “northwesterly” (petition “north-easterly”, “north-westerly”), elevations with a comma, such as “1,727-foot” (petition “1727-foot”), and “then” without a comma (petition “then,”). Nothing else in these steps changes.", "Notice No. 243"),
        ("(90), (91)", "Road names as TTB’s published text gives them: US Highway 377 on the road US Highway 377 and State Highway 29 share from the junction near Grit to Mason (TTB’s step (11)), State Highway 29 northwest of the junction (TTB’s step (10)). The marked 1,727 is on the shared road, so the petition’s “State Highway 29” there is written “US Highway 377”. The line does not change.", "Notice No. 243")]
CSS = ("body{font-family:'Times New Roman',Times,serif;font-size:11.5pt;line-height:1.35;margin:0.9in}"
       "h1{font-size:15pt;margin:0 0 4pt} h2{font-size:12.5pt;margin:18pt 0 6pt} .sub{color:#333;margin:0 0 12pt}"
       "p{margin:0 0 6pt} .ind{margin-left:22pt} .sec{font-weight:bold;margin-top:10pt}"
       "table{border-collapse:collapse;width:100%;font-size:10.5pt} td,th{border:1px solid #888;padding:4pt;vertical-align:top;text-align:left}"
       ".box{border:1px solid #888;padding:6pt 8pt;margin:6pt 0} .small{font-size:9.5pt;color:#333}"
       "@page{size:letter;margin:0}")
h = [f"<html><head><meta charset='utf-8'><title>Hickory Sands District AVA: boundary description as proposed to TTB</title><style>{CSS}</style></head><body>",
     "<h1>Hickory Sands District AVA: regulatory text as proposed to TTB</h1>",
     f"<p class=sub>Docket No. TTB-2026-0005, Notice No. 243 (91 FR 52576). Proposed § 9.___, with the changes the petitioners propose, as discussed with TTB on October 15, 2026. "
     f"The AVA is {S['sqmi']:.2f} square miles. Prepared by Dan McLaughlin, Robert Clay Vineyards, petitioner.</p>",
     "<p class=small>Every word below is TTB’s published text (Notice No. 243), except steps (10)–(11) and (90)–(100) near Grit, which use the "
     "petition’s own wording (February 2, 2023), with four new steps around a granite lobe and one flagged correction, with “US Highway” written as TTB writes it. The changes are listed after the text.</p>",
     "<h2>Regulatory text</h2>", P("§ 9.___ Hickory Sands District.", "sec"), P(A), P(B)] + \
    [P(m, "ind") for m in MAPS] + [P(C)] + [P(t, "ind") for t in steps] + \
    ["<h2>Changes from TTB’s published text (Notice No. 243)</h2>",
     "<table><tr><th>Steps</th><th>Text</th><th>Source</th></tr>" + "".join(f"<tr><td>{e(a)}</td><td>{e(b)}</td><td>{e(c)}</td></tr>" for a, b, c in rows) + "</table>",
     "<h2>The one correction to the petition’s wording</h2>",
     "<p>The petition said the line follows Honey Creek all the way to the marked 1727. On the Grit map, the creek labelled Honey Creek reaches the highway at the marked 1668. "
     "The petition’s line leaves Honey Creek at its confluence with an unnamed, intermittent tributary and follows the tributary, past Bench Mark 1680, to the marked 1727. "
     "The line is unchanged; only the description now names the tributary.</p>",
     "<div class=box><p><b>Petition step 91, as filed:</b> " + e(pet91) + "</p><p><b>Step (90), corrected:</b> " + corr + "</p></div>",
     "<h2>Notes</h2>",
     "<p>Lane wording. Steps (10)–(11) and (91)–(92) keep the petition’s lane wording. In the GIS layers and on the quadrangles, the westbound-lane line is drawn 30 meters northeast of the highway’s center line and the eastbound-lane line 30 meters southwest of it, along the whole highway stretch, so the boundary is visible beside the road; this is a drawing convention discussed with TTB and does not change the text.</p>",
     "<p>Highway names. On the Grit map, State Highway 29 and US Highway 377 share the road from their junction at Roadside Park to Mason. The roads are named as TTB’s published text names them: State Highway 29 northwest of the junction (TTB’s step (10)) and US Highway 377 on the shared road (TTB’s step (11)). The marked 1,727 is on the shared road, 1.5 km southeast of the junction.</p>",
     "<p>Source of TTB’s words: the Federal Register’s text of Notice No. 243 (document 2026-16670), checked on October 15, 2026 against the official PDF on govinfo.gov and the notice in docket TTB-2026-0005 (same wording). The petition’s words are from the petition as filed in the docket (TTB-2026-0005-0012).</p>",
     "<p class=small>License: CC0 1.0 Universal (public domain dedication). To the extent possible under law, Dan McLaughlin has waived all copyright and related rights in this document and the accompanying files. "
     "TTB, its contractors and anyone else may copy, change and use them for any purpose without permission and without attribution. https://creativecommons.org/publicdomain/zero/1.0/</p>",
     "</body></html>"]
open(os.path.join(OUT, STEM + ".html"), "w", encoding="utf-8").write("\n".join(h))
print("ok", len(steps), "steps;", OUT)
