"""Build the HTML for the filing PDFs from markdown (page footer with docket number and page numbers,
real titles, Section VIII step indent, Exhibits A to C). Printed to PDF by scripts/build_all.sh.
usage: build_comment_html.py <kind: comment|fallback|attachment1> <md> <out_html>"""
import os, pathlib, re, sys
import markdown

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMGDIR = ROOT / "build" / "images"

kind, md_path, out_html = sys.argv[1], sys.argv[2], sys.argv[3]
IMG = IMGDIR.as_uri()
EXB = (ROOT / "public-comment" / "images" / "source" / "exhibit-b-parks-on-esri-world-imagery.jpg").as_uri()
title = {"comment": "Comment of Dan McLaughlin on Notice No. 243 (Docket No. TTB-2026-0005)",
         "fallback": "Comment of Dan McLaughlin on Notice No. 243 (Docket No. TTB-2026-0005)",
         "attachment1": "Attachment 1: Boundary Narrative Comparison (Docket No. TTB-2026-0005, Notice No. 243)"}[kind]
footer = "Attachment 1 to comment on Notice No. 243, Docket No. TTB-2026-0005" if kind == "attachment1" else "Comment on Notice No. 243, Docket No. TTB-2026-0005"
STYLE = f"""
@page {{ size: Letter; margin: 0.9in 0.9in 1in 0.9in;
  @bottom-left {{ content: "{footer}"; font: 8.5pt Georgia, serif; color: #444; }}
  @bottom-right {{ content: "Page " counter(page) " of " counter(pages); font: 8.5pt Georgia, serif; color: #444; }} }}
body {{ font-family: Georgia, 'Times New Roman', serif; font-size: 11pt; line-height: 1.4; color: #111; }}
h1 {{ font-size: 16pt; text-align: center; margin-bottom: 4pt; }}
h2 {{ font-size: 12.5pt; margin-top: 16pt; break-after: avoid; page-break-after: avoid; }}
p, li {{ orphans: 3; widows: 3; }}
table {{ border-collapse: collapse; margin: 8pt 0; width: 100%; break-inside: avoid; }}
td, th {{ border: 1px solid #888; padding: 4px 6px; font-size: 10pt; vertical-align: top; }}
th {{ background: #eee; }}
td:last-child {{ white-space: nowrap; }}
.step {{ margin-left: 0.4in; }}
.ex {{ page-break-before: always; }} .ex img {{ width: 100%; }}
.sig {{ break-inside: avoid; page-break-inside: avoid; margin-top: 14pt; }}
.sig .space {{ height: 0.6in; }}
.sig .line {{ width: 3.2in; border-bottom: 1px solid #111; margin-bottom: 4pt; }}
.sig p {{ margin: 0 0 8pt 0; }}
"""
src = open(md_path, encoding="utf-8").read()
body = markdown.markdown(src, extensions=["tables"])

# Signature block laid out like the author's earlier comment (TTB-2026-0005-0015): space to sign,
# a signature line, the name block, then the date. The date is the document's own date line.
dm = re.search(r"^(?:Date:|Prepared)\s+([A-Z][a-z]+ \d{1,2}, \d{4})", src, re.M)
if not dm: sys.exit("document date not found")
def sig(lead, name_html):
    return (f"<div class='sig'>{lead}<div class='space'></div><div class='line'></div>"
            f"<p>{name_html}</p><p>{dm.group(1)}</p></div>")
if kind == "attachment1":
    body += sig("<p>Prepared by:</p>", "Dan McLaughlin<br />Co-petitioner, Hickory Sands District AVA<br />Robert Clay Vineyards, Mason, Texas")
else:
    sm = re.search(r"<p>Respectfully submitted,</p>\s*<p>(Dan McLaughlin<br />.*?)</p>", body, re.S)
    if not sm: sys.exit("signature block not found")
    block = sig("<p>Respectfully submitted,</p>", sm.group(1))
    body = body[:sm.start()] + body[sm.end():]
    # As in TTB-2026-0005-0015, the signature follows the closing paragraph and the list of
    # attachments (Section IX) follows the signature.
    im = re.search(r"<h2>IX\. Attachments</h2>", body)
    if not im: sys.exit("Section IX heading not found")
    body = body[:im.start()] + block + body[im.start():]
if kind != "attachment1":
    m = re.search(r"<ol>(\s*<li>\s*(?:<p>)?\s*<strong>Published polygon)", body)
    if not m: sys.exit("Section VIII list not found")
    body = body[:m.start()] + '<ol start="2">' + m.group(1) + body[m.end():]
    n = 0
    def mark(mo):
        global n; n += 1; return '<p class="step">' + mo.group(1)
    body = re.sub(r"<p>(\(9[0-6]\) Proceed)", mark, body)
    body = re.sub(r"<p>(These steps follow the petition)", lambda mo: '<p class="step">' + mo.group(1), body)
    if n != 7: sys.exit(f"expected 7 replacement steps, found {n}")
    tail_c = ("The feature is available on request with the other GIS layers." if kind == "fallback"
              else "The feature is included in Attachment 2 as ttb-published-san-pasqual-valley.")
    body += (
        "<div class='ex'><h2>Exhibit A. Trail networks in the Grit section, as mapped in OpenStreetMap</h2>"
        f"<img src='{IMG}/exhibit-a-osm-trails.png'>"
        "<p>OpenStreetMap shows about 27 miles of dirt tracks and trails inside the Grit section, nearly all of them within the two rock-crawling parks. "
        "Trail and road data: OpenStreetMap contributors, Open Database License (ODbL), retrieved October 12, 2026. Boundaries and park outlines: drawn by the commenter; park outlines are approximate.</p></div>"
        f"<div class='ex'><h2>Exhibit B. Approximate park areas on aerial imagery (imagery: Esri World Imagery)</h2><img src='{EXB}'><p class='cap'>Imagery: Esri, Maxar, Earthstar Geographics, and the GIS User Community.</p>"
        "<p>Katemcy Rocks (K2), about 750 acres, and Wolf Caves, about 477 acres, inside the Grit section. Approximate, interpreted from imagery and the parks' trail maps.</p></div>"
        f"<div class='ex'><h2>Exhibit C. San Pasqual Valley AVA (27 CFR 9.25) as published in TTB's AVAs_Production layer</h2><img src='{IMG}/exhibit-c-san-pasqual-valley.png'>"
        "<p>TTB's San Pasqual Valley polygon, retrieved October 12, 2026, geometry unaltered (NAD83). The boundary goes out along a single line of about 380 meters "
        f"to leave a hillock of about 220 acres outside the AVA, then returns along the same line. {tail_c}</p></div>")
    exd = IMGDIR / "exhibit-d-beg-grit.png"
    if exd.exists():  # built only where the purchased BEG map is available (scripts/exhibits/exhibit_d_beg.py)
        body += (
            "<div class='ex'><h2>Exhibit D. The Grit section on the Bureau of Economic Geology's 1:24,000 geologic map</h2>"
            f"<img src='{exd.as_uri()}'>"
            "<p>Excerpt of Hunt, B.B., Johnson, B., and Helper, M., 2021, Geologic map of the Grit quadrangle, Mason County, Texas: "
            "Bureau of Economic Geology Open-File Map 252, scale 1:24,000, with the Grit section and both routings drawn by the commenter. "
            "The land inside the petition boundary lies to the west of the routings. Principal map units: "
            "p\u0404sg Streeter Granite, p\u0404tm Town Mountain Granite, p\u0404ps Packsaddle Schist, \u0404rh Hickory Sandstone Member, Qal alluvium, Qat terrace deposits. "
            "Copyright Bureau of Economic Geology, The University of Texas at Austin; excerpt reproduced with attribution.</p></div>")
open(out_html, "w", encoding="utf-8").write(
    f"<html><head><meta charset='utf-8'><title>{title}</title><meta name='author' content='Dan McLaughlin'><style>{STYLE}</style></head><body>{body}</body></html>")
print("wrote", out_html)
