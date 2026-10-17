"""Hard checks on what reaches TTB, run at the end of ./build.sh (issue #57). Exit 1 on any failure; warnings do not fail.
- pdf: every font embedded in every PDF the build makes (documents/*.pdf, except TTB's docket PDF, byte-identical to
  resources/ttb/; the 13 USGS GeoPDFs are USGS's), and no Mac-only font (Helvetica Neue, Menlo, ...); the notice copy (2a)
  has no AcroForm, /Perms, document XMP, signature or annotation other than links (#39). pdffonts and pdfsig (poppler)
  are asked too when installed;
- compare text: the two compare-text files differ in exactly the steps whose change in agreed-steps.json is not
  "unchanged", each changed line reads as the proposed step, and the steps README.txt names as the differences are those;
- figures: the area (agreed-steps.json) in README.txt and the description (1a), every "x.xx square miles" in them and the
  read me; README.md's figures from the build's statistics (grit-change-stats.json, ttb-diff-stats.json), each rounded
  once, half up (#26, #33);
- wording: no "agreed", "ours", "our boundary", "TTB's published polygon", "final text" or bare "Hickory Sandstone" in
  a generated document (documents/ HTML, TXT, CSV, DOCX; README.txt; the GIS attributes). The compare-text files are
  the text of TTB's notice, not ours, and are not read;
- gis: every point's quad is the quadrangle whose neatline holds it (#32), and every line's quad that of its end: the
  neatline is the quad's 7.5-minute cell of the NAD27 graticule, found from the centre of its neatline VRT template
  (resources/quads/cropped/, committed, no raster needed), the point carried NAD83 -> NAD27 with the NADCON 5.0 CONUS
  grid; every length_m geodesic on GRS 1980 (within 0.5 m); every layer NAD83 (EPSG:4269): GeoJSON, GeoPackage and the
  shapefiles' .prj (read from the zips that ship); the steps CSV agrees with the line layer;
- package: a WARNING when a path in the zip, extracted by Windows Explorer under C:\\Users\\<20 characters>\\Downloads\\
  <zip name>\\, passes Windows' MAX_PATH (260 with the terminating null: 259 characters). Dan, Oct. 17 2026: leave the names.
Usage: check_outputs.py [<work dir> [<dist dir>]]   (defaults: $HSD_WORK or target/work; dist/)"""
import csv, difflib, filecmp, glob, html, json, math, os, re, shutil, subprocess, sys, zipfile
from decimal import Decimal, ROUND_HALF_UP
import pymupdf, pypdf
from osgeo import gdal, ogr, osr
gdal.UseExceptions(); ogr.UseExceptions()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
W = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("HSD_WORK") or os.path.join(ROOT, "target", "work")
DIST = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "dist")
J = lambda *p: json.load(open(os.path.join(W, *p), encoding="utf-8"))
read = lambda p: open(p, encoding="utf-8").read()
flat = lambda s: re.sub(r"\s+", " ", s)
rh = lambda v: int(Decimal(repr(v)).quantize(Decimal(1), ROUND_HALF_UP))         # whole units, half up, from the stored value
num = lambda s: int(s.replace(",", ""))
base = os.path.basename
steps = J("agreed-steps.json")
S = {s["step"]: s for s in steps["steps"]}
CHANGED = sorted(n for n, s in S.items() if s["change"] != "unchanged")
failed, warned = [], []

def check(name):                      # one check: a list of problems (each a failure), or the line that says it passed
    def run(f):
        try: problems, ok = f()
        except Exception as e: problems, ok = ["%s: %s" % (type(e).__name__, e)], ""
        for p in problems: print("%s CHECK FAILED: %s" % (name.upper(), p))
        if problems: failed.append(name)
        else: print("%s check: %s" % (name, ok))
    return run

# ---------------------------------------------------------------- PDFs
MAC = re.compile(r"Helvetica ?Neue|Menlo|Monaco|Lucida ?Grande|Geneva|Avenir|SF ?(Pro|Mono|Compact|NS)|\.SF|AppleSystemUI|"
                 r"Apple ?(Color ?Emoji|SD ?Gothic|Chancery|Braille|Symbols)|Hiragino|PingFang|Chalkboard|Marker ?Felt|Noteworthy|Optima", re.I)
TTB_FILES = glob.glob(os.path.join(ROOT, "resources", "ttb", "*.pdf"))
@check("pdf")
def _():
    pdfs = [p for p in sorted(glob.glob(os.path.join(W, "documents", "*.pdf"))) if not any(filecmp.cmp(p, t, shallow=False) for t in TTB_FILES)]
    notice = [p for p in pdfs if base(p).startswith("TTB-Notice-243-with-")]
    bad = [] if len(pdfs) >= 4 and len(notice) == 1 else ["expected the description, side-by-side, read me and one notice copy in documents/, found %s" % [base(p) for p in pdfs]]
    for p in pdfs:
        d = pymupdf.open(p); fonts = set()
        for i in range(len(d)): fonts |= {(re.sub(r"^[A-Z]{6}\+", "", f[3]), f[1] != "n/a" or f[2] == "Type3") for f in d.get_page_fonts(i, full=True)}
        if shutil.which("pdffonts"):  # poppler: every font object, in pages, forms and annotations alike
            for l in subprocess.run(["pdffonts", p], capture_output=True, text=True, check=True).stdout.splitlines()[2:]:
                t = l.split()
                if len(t) >= 7: fonts.add((re.sub(r"^[A-Z]{6}\+", "", t[0]), t[-5] == "yes"))   # name ... emb sub uni object ID
        bad += ["%s: font %s is not embedded" % (base(p), f) for f, emb in sorted(fonts) if not emb]
        bad += ["%s: font %s is a Mac-only font (TTB's PCs do not have it)" % (base(p), f) for f in sorted({f for f, _ in fonts if MAC.search(f)})]
    xmp = 0
    for p in notice:                  # the notice copy: no form, permissions, document XMP, signature; only link annotations (#39)
        r = pypdf.PdfReader(p); root = r.trailer["/Root"]
        bad += ["%s: the catalog has %s" % (base(p), k) for k in ("/AcroForm", "/Perms", "/Metadata") if k in root]
        for i, pg in enumerate(r.pages):
            bad += ["%s: page %d has an XMP /Metadata" % (base(p), i + 1)] if "/Metadata" in pg else []
            annots = pg["/Annots"].get_object() if "/Annots" in pg else []
            bad += ["%s: page %d has a %s annotation" % (base(p), i + 1, a.get_object().get("/Subtype")) for a in annots if a.get_object().get("/Subtype") != "/Link"]
        d = pymupdf.open(p); images = set()
        for pg in d: images |= {im[0] for im in pg.get_images(full=True)}
        for x in range(1, d.xref_length()):
            if x == d.pdf_catalog(): continue          # the catalog, read above
            try: o = d.xref_object(x, compressed=True).replace(" ", "")
            except Exception: continue
            for k in ("/SigFlags", "/ByteRange", "/FT/Sig", "/Type/Sig", "/DocTimeStamp", "/Perms", "/AcroForm"):
                if k in o: bad.append("%s: object %d has %s" % (base(p), x, k))
            if "/Metadata" in o and "/Subtype/XML" not in o:   # who carries XMP: only TTB's figure images may (their Photoshop records)
                if x in images: xmp += 1
                elif "/Type/XObject" not in o or "/Subtype/Image" not in o: bad.append("%s: object %d carries XMP metadata" % (base(p), x))
        if shutil.which("pdfsig"):
            out = subprocess.run(["pdfsig", p], capture_output=True, text=True).stdout
            bad += ["%s: pdfsig finds a signature" % base(p)] if "Signature #" in out else []
    return bad, "%d PDFs (%s): every font embedded, no Mac-only font; the notice copy has no AcroForm, /Perms, document XMP or signature, " \
                "only link annotations (%d XMP records left on TTB's figure images, as in the docket PDF)" % (len(pdfs), ", ".join(re.sub(r"^Hickory-Sands-District-|-2026-10-15.*$", "", base(p)) for p in pdfs), xmp)

# ---------------------------------------------------------------- compare text
STEPLINE = re.compile(r"^\((\d+)\) ")
q = lambda s: flat(s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')).strip()
def ranges(s):                        # "(10)-(11) and (90)-(104)" -> {10, 11, 90, ..., 104}
    return {n for a, b in re.findall(r"\((\d+)\)(?:-\((\d+)\))?", s) for n in range(int(a), int(b or a) + 1)}
@check("compare text")
def _():
    a, b = (read(glob.glob(os.path.join(W, "documents", "compare-text_*%s.txt" % k))[0]).splitlines() for k in ("docket", "with-proposed-changes"))
    old, new = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op != "equal": old += a[i1:i2]; new += b[j1:j2]
    bad = ["a line other than a boundary step differs: %r" % l[:120] for l in old + new if not STEPLINE.match(l)]
    got_new = sorted({int(STEPLINE.match(l).group(1)) for l in new if STEPLINE.match(l)})
    got_old = sorted({int(STEPLINE.match(l).group(1)) for l in old if STEPLINE.match(l)})
    ttb_n = max(int(x) for s in S.values() for t in re.findall(r"TTB's (?:published text, )?step \((\d+)\)|renumbered from \((\d+)\)", s["source"] + " " + s["change"]) for x in t if x)   # Notice No. 243's last step
    if got_new != CHANGED: bad.append("the notice copy's text differs in steps %s; agreed-steps.json changes %s" % (got_new, CHANGED))
    if got_old != [n for n in CHANGED if n <= ttb_n]: bad.append("Notice No. 243's text differs in steps %s; expected %s" % (got_old, [n for n in CHANGED if n <= ttb_n]))
    bad += ["step (%s) in the notice copy is not the proposed text: %r" % (STEPLINE.match(l).group(1), l[:100]) for l in new
            if STEPLINE.match(l) and int(STEPLINE.match(l).group(1)) in S and q(l) != q(S[int(STEPLINE.match(l).group(1))]["text"])]
    m = re.search(r"the only differences are the changed steps, (.+?)\.(?:\s|$)", flat(read(os.path.join(W, "README.txt"))))
    if m and ranges(m.group(1)) != set(CHANGED): bad.append("README.txt says the only differences are %s; they are %s" % (m.group(1), CHANGED))
    return bad, "the two compare-text files differ in exactly the %d changed steps %s, each the proposed text%s" % (
        len(CHANGED), CHANGED, "; README.txt names them" if m else "")

# ---------------------------------------------------------------- figures
@check("figures")
def _():
    G, T = J("review", "grit-change-stats.json"), J("review", "ttb-diff-stats.json")
    area, bad = "%.2f" % steps["sqmi"], []
    desc = glob.glob(os.path.join(W, "documents", "*-boundary-description-as-proposed-*.html"))[0]
    for p in [os.path.join(W, "README.txt"), desc] + glob.glob(os.path.join(W, "documents", "*-read-me-first-*.html")):
        t = flat(html.unescape(re.sub(r"<[^>]+>", "", read(p))))
        figs = re.findall(r"(\d+\.\d\d) square miles", t)
        if not figs and p != desc and not p.endswith("README.txt"): continue
        bad += ["%s gives no area (x.xx square miles); the build's is %s" % (base(p), area)] if not figs else []
        bad += ["%s says %s square miles; the build's area is %s" % (base(p), f, area) for f in figs if f != area]
    md = flat(read(os.path.join(ROOT, "README.md")))
    tab = re.search(r"\| piece \| acres \| granite \(acres\) \| \|[-:| ]+\| ((?:\|[^|]+\|[^|]+\|[^|]+\| ?)+)", md)
    if not tab: bad.append("README.md: no Grit table (| piece | acres | granite (acres) |)")
    else:
        rows = sorted((num(r[1]), num(r[2])) for r in re.findall(r"\|([^|]+)\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|", tab.group(1)))
        want = sorted((rh(v["acres"]), rh(v["granite_acres"])) for v in G["areas"].values())
        if rows != want: bad.append("README.md Grit table (acres, granite) %s; grit-change-stats.json rounded once, half up: %s" % (rows, want))
    pts = len(json.load(open(glob.glob(os.path.join(W, "gis", "*-points-EPSG4269.geojson"))[0]))["features"])
    dr = T["areas"]["drawing"]
    for what, rx, want in [
            ("steps, points and area", r"(\d+) steps, (\d+) points, ([\d.]+) square miles", [str(len(S)), str(pts), area]),
            ("areas by text", r"measures ([\d.]+) square miles by Notice No\. 243's text, ([\d.]+) by the petition, and ([\d.]+) as proposed",
             ["%.2f" % G["sqmi"][k] for k in ("notice_243", "petition", "revision")]),
            ("big differences", r"(\d+) big differences\*\*, where the lines are (\d+) m or more apart", [str(T["big"]), "%g" % T["big_m"]]),
            ("pieces", r"every piece of land between the two lines\*\* \(([\d,]+) pieces\)", ["{:,}".format(sum(v["pieces"] for v in T["areas"].values()))]),
            ("drawing acres", r"([\d,]+) acres are in the proposed revision only and ([\d,]+) acres in the Map Explorer polygon only",
             ["{:,}".format(rh(dr["revision_only_acres"])), "{:,}".format(rh(dr["map_explorer_only_acres"]))]),
            ("median", r"the median distance to the other line is (\d+) m", [str(rh(T["median_m"]))])]:
        m = re.search(rx, md)
        if not m: bad.append("README.md: cannot find the %s (%s)" % (what, rx))
        elif list(m.groups()) != want: bad.append("README.md %s: %s; the build's: %s" % (what, list(m.groups()), want))
    return bad, "area %s sq mi in README.txt, the description and the read me; README.md's Grit table, area, step, point, " \
                "difference and median figures equal the build's statistics, rounded once" % area

# ---------------------------------------------------------------- wording
BAD = re.compile(r"\bagreed\b|\bours\b|\bour boundary\b|\bTTB['\u2019]s published polygon\b|\bfinal text\b|\bHickory\s+Sandstone\b(?!\s+Member)", re.I)
def texts():
    D = os.path.join(W, "documents")
    for p in sorted(glob.glob(D + "/*.html")):
        yield p, html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<style.*?</style>", " ", read(p), flags=re.S)))
    for p in sorted(glob.glob(D + "/*.txt") + glob.glob(D + "/*.csv") + [os.path.join(W, "README.txt")]):
        if not base(p).startswith("compare-text_"): yield p, read(p)   # compare-text: TTB's notice, word for word
    for p in sorted(glob.glob(D + "/*.docx")):
        z = zipfile.ZipFile(p)
        yield p, " ".join(html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", z.read(n).decode("utf-8")))) for n in z.namelist() if n.startswith(("word/", "docProps/")) and n.endswith(".xml"))
    for p in sorted(glob.glob(os.path.join(W, "gis", "*.geojson"))):
        yield p, "\n".join(sorted({v for f in json.load(open(p))["features"] for v in f["properties"].values() if isinstance(v, str)}))
@check("wording")
def _():
    n, bad = 0, []
    for p, t in texts():
        n += 1
        bad += ["%s: %r in \u2026%s\u2026" % (base(p), m.group(0), flat(t[max(0, m.start() - 60):m.end() + 40])) for m in BAD.finditer(t)]
    return bad, "%d generated documents and layers: no agreed, ours, our boundary, TTB's published polygon, final text or bare Hickory Sandstone" % n

# ---------------------------------------------------------------- GIS
NAD83 = osr.SpatialReference(); NAD83.ImportFromEPSG(4269); NAD83.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
NAD27 = osr.SpatialReference(); NAD27.ImportFromEPSG(4267); NAD27.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
_o = osr.CoordinateTransformationOptions()
_o.SetOperation("+proj=pipeline +step +proj=axisswap +order=2,1 +step +proj=unitconvert +xy_in=deg +xy_out=rad "
                "+step +inv +proj=hgridshift +grids=us_noaa_nadcon5_nad27_nad83_1986_conus.tif +step +proj=unitconvert +xy_in=rad +xy_out=deg +step +proj=axisswap +order=2,1")
TO27 = osr.CoordinateTransformation(NAD83, NAD27, _o)   # NAD83 -> NAD27 by the NADCON 5.0 CONUS grid (CLAUDE.md: Datum)
CELL, EDGE_M = 0.125, 1.0                               # a 1:24,000 quad is a 7.5-minute cell; within 1 m of its neatline counts
def neatlines():
    cells = {}
    for p in glob.glob(os.path.join(ROOT, "resources", "quads", "cropped", "*.vrt.in")):
        x = read(p); srs = osr.SpatialReference(html.unescape(re.search(r"<SRS[^>]*>(.*?)</SRS>", x, re.S).group(1)))
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER); geo = srs.CloneGeogCS(); geo.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        g = [float(v) for v in re.search(r"<GeoTransform>(.*?)</GeoTransform>", x).group(1).split(",")]
        nx, ny = (int(re.search(r'raster%sSize="(\d+)"' % k, x).group(1)) for k in "XY")
        lon, lat = osr.CoordinateTransformation(srs, geo).TransformPoint(g[0] + g[1] * nx / 2, g[3] + g[5] * ny / 2)[:2]
        cells[re.match(r"[A-Z]{2}_(.+?)_\d+_\d{4}_", base(p)).group(1)] = (math.floor(lon / CELL) * CELL, math.floor(lat / CELL) * CELL)
    return cells
def off_m(c, lon, lat):               # metres from a NAD27 point to a cell (0 inside)
    dx = max(c[0] - lon, 0, lon - c[0] - CELL) * 111320 * math.cos(math.radians(lat)); dy = max(c[1] - lat, 0, lat - c[1] - CELL) * 110574
    return math.hypot(dx, dy)
@check("gis")
def _():
    Q, bad = neatlines(), []
    with open(os.path.join(ROOT, "resources", "quads", "quads-manifest.csv"), newline="") as fh:
        man = sorted(r["quad"].rsplit(",", 1)[0] for r in csv.DictReader(fh))
    if sorted(Q) != man or len(set(Q.values())) != len(Q): bad.append("neatlines: %s from the VRT templates, %s in the manifest" % (sorted(Q.items()), man))
    def quad_of(lon, lat, said):
        lo, la = TO27.TransformPoint(lon, lat)[:2]
        if said in Q and off_m(Q[said], lo, la) <= EDGE_M: return said
        return next((k for k, c in Q.items() if off_m(c, lo, la) == 0), None)
    srcs = sorted(glob.glob(os.path.join(W, "gis", "*.geojson")) + glob.glob(os.path.join(W, "gis", "*.gpkg")))
    shz = sorted(glob.glob(os.path.join(W, "gis", "shapefiles", "*.zip")))
    for z in shz:
        prj = [n for n in zipfile.ZipFile(z).namelist() if n.endswith(".prj")]
        srcs += ["/vsizip/%s/%s" % (z, n[:-4] + ".shp") for n in prj]
        bad += ["%s: no .prj" % base(z)] if not prj else []
    if len(shz) != 3: bad.append("expected the area, line and points shapefile zips, found %s" % [base(z) for z in shz])
    nl, pts, lines, endq = 0, 0, 0, {}
    for src in srcs:
        ds = ogr.Open(src)
        for lyr in ds:
            nl += 1; name = "%s%s" % (base(src), "" if src.endswith((".geojson", ".shp")) else ":" + lyr.GetName())
            srs = lyr.GetSpatialRef()
            if srs is None: bad.append("%s: no coordinate system" % name); continue
            srs = srs.Clone(); srs.AutoIdentifyEPSG()
            if not (srs.IsGeographic() and srs.GetAuthorityCode(None) == "4269"):
                bad.append("%s: not NAD83 (EPSG:4269): %s" % (name, srs.GetName()))
            fields = [lyr.GetLayerDefn().GetFieldDefn(i).GetName() for i in range(lyr.GetLayerDefn().GetFieldCount())]
            gt = ogr.GT_Flatten(lyr.GetGeomType())
            for f in lyr:
                g = f.GetGeometryRef(); step = f.GetField("step") if "step" in fields else None
                if gt == ogr.wkbPoint and "quad" in fields:
                    pts += 1; got = quad_of(g.GetX(), g.GetY(), f.GetField("quad"))
                    if got != f.GetField("quad"): bad.append("%s: point %s is on the %s map, not %s (quad)" % (name, step, got, f.GetField("quad")))
                if gt == ogr.wkbLineString and "length_m" in fields:
                    lines += 1; h = g.Clone(); h.AssignSpatialReference(NAD83); gl = h.GeodesicLength()
                    if abs(gl - f.GetField("length_m")) > 0.5: bad.append("%s: step %s length_m %s, geodesic %.1f m" % (name, step, f.GetField("length_m"), gl))
                    if "quad" in fields:
                        x, y = g.GetPoint_2D(g.GetPointCount() - 1); got = quad_of(x, y, f.GetField("quad")); endq[step] = (got, gl)
                        if got != f.GetField("quad"): bad.append("%s: step %s ends on the %s map, not %s (quad)" % (name, step, got, f.GetField("quad")))
        ds = None
    for p in glob.glob(os.path.join(W, "documents", "*-steps.csv")):
        with open(p, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                q_, gl = endq.get(int(r["step"]), (None, None))
                if r["quad"] != q_ or gl is None or abs(float(r["length_m"]) - gl) > 0.5:
                    bad.append("%s: step %s quad %s, length_m %s; the line ends on %s, geodesic %s m" % (base(p), r["step"], r["quad"], r["length_m"], q_, gl and round(gl, 1)))
    if not pts or not lines: bad.append("no point or line layer with quad / length_m found in %s" % os.path.join(W, "gis"))
    return bad, "%d layers (GeoJSON, GeoPackage, shapefiles' .prj) NAD83 (EPSG:4269); %d points and %d step ends on the quad they name " \
                "(NAD27 7.5' neatlines, NADCON 5.0 CONUS); %d lengths geodesic within 0.5 m; the steps CSV agrees" % (nl, pts, lines, lines)

# ---------------------------------------------------------------- package
@check("package")
def _():
    zips = glob.glob(os.path.join(DIST, "*.zip"))
    if len(zips) != 1: return ["expected one zip in %s, found %s" % (DIST, [base(z) for z in zips])], ""
    stem = base(zips[0])[:-4]; pre = "C:\\Users\\%s\\Downloads\\%s\\" % ("U" * 20, stem)
    names = [n for n in zipfile.ZipFile(zips[0]).namelist() if not n.endswith("/")]
    over = sorted((n for n in names if len(pre) + len(n) > 259), key=len, reverse=True)
    if over:
        warned.append("package")
        print("WARNING: %d of %d paths in %s pass Windows' 260-character MAX_PATH when Explorer extracts it to %s (longest %d: %s); "
              "Explorer may refuse them (Dan: leave the names for now)" % (len(over), len(names), base(zips[0]), pre, len(pre) + len(over[0]), over[0]))
    return [], "%d files in %s; longest path extracted under %s: %d characters" % (len(names), base(zips[0]), pre, len(pre) + max(map(len, names)))

print("output checks: %s" % ("all passed" if not failed else "FAILED: " + ", ".join(failed)) + (" (warnings: %s)" % ", ".join(warned) if warned else ""))
sys.exit(1 if failed else 0)
