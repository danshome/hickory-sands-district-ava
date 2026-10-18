r"""Hard checks on what reaches TTB, run at the end of ./build.sh (issue #57).

Exit 1 on any failure; warnings do not fail.

- pdf: every font embedded in every PDF the build makes (documents/*.pdf,
  except TTB's docket PDF, byte-identical to resources/ttb/; the 13 USGS
  GeoPDFs are USGS's), and no Mac-only font (Helvetica Neue, Menlo, ...); the
  notice copy (2a) has no AcroForm, /Perms, document XMP, signature or
  annotation other than links (#39). pdffonts and pdfsig (poppler) are asked
  too when installed;
- compare text: the two compare-text files differ in exactly the steps whose
  change in proposed-steps.json is not "unchanged", each changed line reads as
  the proposed step, and the steps README.txt names as the differences are
  those;
- figures: the area (proposed-steps.json) in README.txt and the description
  (1a), every "x.xx square miles" in them and the read me; README.md's
  figures from the build's statistics (grit-change-stats.json,
  ttb-diff-stats.json), each rounded once, half up (#26, #33);
- wording: no "agreed", "ours", "our boundary", "TTB's published polygon",
  "final text" or bare "Hickory Sandstone" in a generated document
  (documents/ HTML, TXT, CSV, DOCX; README.txt; the GIS attributes). The
  compare-text files are the text of TTB's notice, not ours, and are not read;
- gis: every point's quad is the quadrangle whose neatline holds it (#32), and
  every line's quad that of its end: the neatline is the quad's 7.5-minute
  cell of the NAD27 graticule, found from the centre of its neatline VRT
  template (resources/quads/cropped/, committed, no raster needed), the point
  carried NAD83 -> NAD27 with the NADCON 5.0 CONUS grid; every length_m
  geodesic on GRS 1980 (within 0.5 m); every layer NAD83 (EPSG:4269):
  GeoJSON, GeoPackage and the shapefiles' .prj (read from the zips that
  ship); the steps CSV agrees with the line layer;
- package: a WARNING when a path in the zip, extracted by Windows Explorer
  under C:\Users\<20 characters>\Downloads\<zip name>\, passes Windows'
  MAX_PATH (260 with the terminating null: 259 characters). Dan, Oct. 17
  2026: leave the names.

Usage: check_outputs.py [<work dir> [<dist dir>]]
    (defaults: $HSD_WORK or target/work; dist/)
"""

import csv
from decimal import Decimal
from decimal import ROUND_HALF_UP
import difflib
import filecmp
import glob
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import zipfile

from osgeo import gdal
from osgeo import ogr
from osgeo import osr
import pymupdf
import pypdf

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # src/
import revision

gdal.UseExceptions()
ogr.UseExceptions()
ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)
W = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.environ.get("HSD_WORK") or os.path.join(ROOT, "target", "work")
)
DIST = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "dist")


def work_json(*parts):
    """Reads a JSON file of the build, given its path under the work dir."""
    with open(os.path.join(W, *parts), encoding="utf-8") as fh:
        return json.load(fh)


def read(path):
    """Returns the text of a UTF-8 file."""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def flat(s):
    """Returns s with each run of whitespace made one space."""
    return re.sub(r"\s+", " ", s)


def round_half_up(v):
    """Rounds a stored value to whole units, half up, from its stored digits."""
    return int(Decimal(repr(v)).quantize(Decimal(1), ROUND_HALF_UP))


def as_int(s):
    """Returns the whole number a figure such as "1,050" stands for."""
    return int(s.replace(",", ""))


base = os.path.basename
steps = work_json("proposed-steps.json")
S = {s["step"]: s for s in steps["steps"]}
CHANGED = sorted(n for n, s in S.items() if s["change"] != "unchanged")
failed, warned = [], []


def check(name):
    """Makes a decorator that runs one check at once and prints its result.

    The decorated function returns (problems, the line that says it passed);
    each problem is a failure. A check that raises fails with its error.

    Args:
        name: the check's name, as printed.

    Returns:
        The decorator.
    """

    def run(f):
        try:
            problems, ok = f()
        except Exception as e:  # noqa: BLE001  an error fails the check
            problems, ok = [f"{type(e).__name__}: {e}"], ""
        for p in problems:
            print(f"{name.upper()} CHECK FAILED: {p}")
        if problems:
            failed.append(name)
        else:
            print(f"{name} check: {ok}")

    return run


# ---------------------------------------------------------------- PDFs
MAC = re.compile(
    r"Helvetica ?Neue|Menlo|Monaco|Lucida ?Grande|Geneva|Avenir|"
    r"SF ?(Pro|Mono|Compact|NS)|\.SF|AppleSystemUI|"
    r"Apple ?(Color ?Emoji|SD ?Gothic|Chancery|Braille|Symbols)|Hiragino|"
    r"PingFang|Chalkboard|Marker ?Felt|Noteworthy|Optima",
    re.I,
)
TTB_FILES = glob.glob(os.path.join(ROOT, "resources", "ttb", "*.pdf"))


@check("pdf")
def _():
    pdfs = [
        p
        for p in sorted(glob.glob(os.path.join(W, "documents", "*.pdf")))
        if not any(filecmp.cmp(p, t, shallow=False) for t in TTB_FILES)
    ]
    notice = [p for p in pdfs if base(p).startswith("TTB-Notice-243-with-")]
    bad = (
        []
        if len(pdfs) >= 4 and len(notice) == 1
        else [
            (
                "expected the description, side-by-side, read me and one "
                f"notice copy in documents/, found {[base(p) for p in pdfs]}"
            )
        ]
    )
    for p in pdfs:
        d = pymupdf.open(p)
        fonts = set()
        for i in range(len(d)):
            fonts |= {
                (
                    re.sub(r"^[A-Z]{6}\+", "", f[3]),
                    f[1] != "n/a" or f[2] == "Type3",
                )
                for f in d.get_page_fonts(i, full=True)
            }
        # poppler: every font object, in pages, forms and annotations alike
        if shutil.which("pdffonts"):
            for row in subprocess.run(
                ["pdffonts", p], capture_output=True, text=True, check=True
            ).stdout.splitlines()[2:]:
                t = row.split()
                if len(t) >= 7:  # name ... emb sub uni object ID
                    fonts.add(
                        (re.sub(r"^[A-Z]{6}\+", "", t[0]), t[-5] == "yes")
                    )
        bad += [
            f"{base(p)}: font {f} is not embedded"
            for f, emb in sorted(fonts)
            if not emb
        ]
        bad += [
            f"{base(p)}: font {f} is a Mac-only font (TTB's PCs do not have it)"
            for f in sorted({f for f, _ in fonts if MAC.search(f)})
        ]
    xmp = 0
    # the notice copy: no form, permissions, document XMP, signature; only link
    # annotations (#39)
    for p in notice:
        r = pypdf.PdfReader(p)
        root = r.trailer["/Root"]
        bad += [
            f"{base(p)}: the catalog has {k}"
            for k in ("/AcroForm", "/Perms", "/Metadata")
            if k in root
        ]
        for i, pg in enumerate(r.pages):
            bad += (
                [f"{base(p)}: page {i + 1:d} has an XMP /Metadata"]
                if "/Metadata" in pg
                else []
            )
            annots = pg["/Annots"].get_object() if "/Annots" in pg else []
            bad += [
                f"{base(p)}: page {i + 1:d} has a "
                f"{a.get_object().get('/Subtype')} annotation"
                for a in annots
                if a.get_object().get("/Subtype") != "/Link"
            ]
        d = pymupdf.open(p)
        images = set()
        for pg in d:
            images |= {im[0] for im in pg.get_images(full=True)}
        for x in range(1, d.xref_length()):
            if x == d.pdf_catalog():
                continue  # the catalog, read above
            try:
                o = d.xref_object(x, compressed=True).replace(" ", "")
            except Exception:  # noqa: BLE001, S112
                continue  # an object pymupdf cannot read has no key to find
            for k in (
                "/SigFlags",
                "/ByteRange",
                "/FT/Sig",
                "/Type/Sig",
                "/DocTimeStamp",
                "/Perms",
                "/AcroForm",
            ):
                if k in o:
                    bad.append(f"{base(p)}: object {x:d} has {k}")
            # who carries XMP: only TTB's figure images may (their Photoshop
            # records)
            if "/Metadata" in o and "/Subtype/XML" not in o:
                if x in images:
                    xmp += 1
                elif "/Type/XObject" not in o or "/Subtype/Image" not in o:
                    bad.append(f"{base(p)}: object {x:d} carries XMP metadata")
        if shutil.which("pdfsig"):
            # pdfsig exits 2 on a PDF without signatures: read its text, not its
            # status
            out = subprocess.run(
                ["pdfsig", p], capture_output=True, text=True, check=False
            ).stdout
            bad += (
                [f"{base(p)}: pdfsig finds a signature"]
                if "Signature #" in out
                else []
            )
    names = ", ".join(
        re.sub(rf"^Hickory-Sands-District-|-{revision.ISO}.*$", "", base(p))
        for p in pdfs
    )
    return (
        bad,
        (
            f"{len(pdfs):d} PDFs ({names}): every font embedded, no Mac-only "
            "font; the notice copy has no AcroForm, /Perms, document XMP or "
            f"signature, only link annotations ({xmp:d} XMP records left on "
            "TTB's figure images, as in the docket PDF)"
        ),
    )


# ---------------------------------------------------------------- compare text
STEPLINE = re.compile(r"^\((\d+)\) ")


def plain(s):
    """Returns s with straight quotes, one space between words, stripped."""
    return flat(
        s.replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    ).strip()


def ranges(s):
    """Returns the step numbers a list of step ranges names.

    Args:
        s: steps and ranges of steps, such as "(10)-(11) and (90)-(104)".

    Returns:
        The set of the step numbers, such as {10, 11, 90, ..., 104}.
    """
    return {
        n
        for a, b in re.findall(r"\((\d+)\)(?:-\((\d+)\))?", s)
        for n in range(int(a), int(b or a) + 1)
    }


@check("compare text")
def _():
    a, b = (
        read(
            glob.glob(os.path.join(W, "documents", f"compare-text_*{k}.txt"))[0]
        ).splitlines()
        for k in ("docket", "with-proposed-changes")
    )
    old, new = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, a, b, autojunk=False
    ).get_opcodes():
        if op != "equal":
            old += a[i1:i2]
            new += b[j1:j2]
    bad = [
        f"a line other than a boundary step differs: {line[:120]!r}"
        for line in old + new
        if not STEPLINE.match(line)
    ]
    got_new = sorted(
        {
            int(STEPLINE.match(line).group(1))
            for line in new
            if STEPLINE.match(line)
        }
    )
    got_old = sorted(
        {
            int(STEPLINE.match(line).group(1))
            for line in old
            if STEPLINE.match(line)
        }
    )
    ttb_n = max(
        int(x)
        for s in S.values()
        for t in re.findall(
            r"TTB's (?:published text, )?step \((\d+)\)"
            r"|renumbered from \((\d+)\)",
            s["source"] + " " + s["change"],
        )
        for x in t
        if x
    )  # Notice No. 243's last step
    if got_new != CHANGED:
        bad.append(
            f"the notice copy's text differs in steps {got_new}; "
            f"proposed-steps.json changes {CHANGED}"
        )
    if got_old != [n for n in CHANGED if n <= ttb_n]:
        bad.append(
            f"Notice No. 243's text differs in steps {got_old}; "
            f"expected {[n for n in CHANGED if n <= ttb_n]}"
        )
    bad += [
        f"step ({STEPLINE.match(line).group(1)}) in the notice copy is not the "
        f"proposed text: {line[:100]!r}"
        for line in new
        if STEPLINE.match(line)
        and int(STEPLINE.match(line).group(1)) in S
        and plain(line) != plain(S[int(STEPLINE.match(line).group(1))]["text"])
    ]
    m = re.search(
        r"the only differences are the changed steps, (.+?)\.(?:\s|$)",
        flat(read(os.path.join(W, "README.txt"))),
    )
    if m and ranges(m.group(1)) != set(CHANGED):
        bad.append(
            f"README.txt says the only differences are {m.group(1)}; "
            f"they are {CHANGED}"
        )
    return (
        bad,
        (
            "the two compare-text files differ in exactly the "
            f"{len(CHANGED):d} changed steps {CHANGED}, each the proposed text"
            f"{'; README.txt names them' if m else ''}"
        ),
    )


# ---------------------------------------------------------------- figures
@check("figures")
def _():
    grit, diff = (
        work_json("review", "grit-change-stats.json"),
        work_json("review", "ttb-diff-stats.json"),
    )
    area, bad = f"{steps['sqmi']:.2f}", []
    desc = glob.glob(
        os.path.join(
            W, "documents", "*-boundary-description-as-proposed-*.html"
        )
    )[0]
    for p in [
        os.path.join(W, "README.txt"),
        desc,
        *glob.glob(os.path.join(W, "documents", "*-read-me-first-*.html")),
    ]:
        t = flat(html.unescape(re.sub(r"<[^>]+>", "", read(p))))
        figs = re.findall(r"(\d+\.\d\d) square miles", t)
        if not figs and p != desc and not p.endswith("README.txt"):
            continue
        bad += (
            [
                (
                    f"{base(p)} gives no area (x.xx square miles); "
                    f"the build's is {area}"
                )
            ]
            if not figs
            else []
        )
        bad += [
            f"{base(p)} says {f} square miles; the build's area is {area}"
            for f in figs
            if f != area
        ]
    md = flat(read(os.path.join(ROOT, "README.md")))
    tab = re.search(
        r"\| piece \| acres \| granite \(acres\) \| \|[-:| ]+\| "
        r"((?:\|[^|]+\|[^|]+\|[^|]+\| ?)+)",
        md,
    )
    if not tab:
        bad.append(
            "README.md: no Grit table (| piece | acres | granite (acres) |)"
        )
    else:
        rows = sorted(
            (as_int(r[1]), as_int(r[2]))
            for r in re.findall(
                r"\|([^|]+)\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|", tab.group(1)
            )
        )
        want = sorted(
            (round_half_up(v["acres"]), round_half_up(v["granite_acres"]))
            for v in grit["areas"].values()
        )
        if rows != want:
            bad.append(
                f"README.md Grit table (acres, granite) {rows}; "
                f"grit-change-stats.json rounded once, half up: {want}"
            )
    with open(
        glob.glob(os.path.join(W, "gis", "*-points-EPSG4269.geojson"))[0]
    ) as fh:
        pts = len(json.load(fh)["features"])
    dr = diff["areas"]["drawing"]
    for what, rx, want in [
        (
            "steps, points and area",
            r"(\d+) steps, (\d+) points, ([\d.]+) square miles",
            [str(len(S)), str(pts), area],
        ),
        (
            "areas by text",
            (
                r"measures ([\d.]+) square miles by Notice No\. 243's text, "
                r"([\d.]+) by the petition, and ([\d.]+) as proposed"
            ),
            [
                f"{grit['sqmi'][k]:.2f}"
                for k in ("notice_243", "petition", "revision")
            ],
        ),
        (
            "big differences",
            (
                r"(\d+) big differences\*\*, where the lines are (\d+) m "
                r"or more apart"
            ),
            [str(diff["big"]), f"{diff['big_m']:g}"],
        ),
        (
            "pieces",
            (
                r"every piece of land between the two lines\*\* "
                r"\(([\d,]+) pieces\)"
            ),
            ["{:,}".format(sum(v["pieces"] for v in diff["areas"].values()))],
        ),
        (
            "drawing acres",
            (
                r"([\d,]+) acres are in the proposed revision only and "
                r"([\d,]+) acres in the Map Explorer polygon only"
            ),
            [
                "{:,}".format(round_half_up(dr["revision_only_acres"])),
                "{:,}".format(round_half_up(dr["map_explorer_only_acres"])),
            ],
        ),
        (
            "median",
            r"the median distance to the other line is (\d+) m",
            [str(round_half_up(diff["median_m"]))],
        ),
    ]:
        m = re.search(rx, md)
        if not m:
            bad.append(f"README.md: cannot find the {what} ({rx})")
        elif list(m.groups()) != want:
            bad.append(
                f"README.md {what}: {list(m.groups())}; the build's: {want}"
            )
    return (
        bad,
        (
            f"area {area} sq mi in README.txt, the description and the read "
            "me; README.md's Grit table, area, step, point, difference and "
            "median figures equal the build's statistics, rounded once"
        ),
    )


# ---------------------------------------------------------------- wording
BAD = re.compile(
    r"\bagreed\b|\bours\b|\bour boundary\b|"
    r"\bTTB['\u2019]s published polygon\b|\bfinal text\b|"
    r"\bHickory\s+Sandstone\b(?!\s+Member)",
    re.I,
)


def texts():
    """Yields (path, text) for every generated document and GIS layer.

    The HTML without its styles and tags, the TXT and CSV files and README.txt
    (not the compare-text files: TTB's notice, word for word), the text of the
    DOCX files, and the string attributes of the GeoJSON layers.
    """
    docs = os.path.join(W, "documents")
    for p in sorted(glob.glob(docs + "/*.html")):
        yield (
            p,
            html.unescape(
                re.sub(
                    r"<[^>]+>",
                    " ",
                    re.sub(r"<style.*?</style>", " ", read(p), flags=re.S),
                )
            ),
        )
    for p in sorted(
        glob.glob(docs + "/*.txt")
        + glob.glob(docs + "/*.csv")
        + [os.path.join(W, "README.txt")]
    ):
        if not base(p).startswith("compare-text_"):
            yield p, read(p)  # compare-text: TTB's notice, word for word
    for p in sorted(glob.glob(docs + "/*.docx")):
        z = zipfile.ZipFile(p)
        yield (
            p,
            " ".join(
                html.unescape(
                    re.sub(
                        r"<[^>]+>",
                        "",
                        re.sub(r"</w:p>", "\n", z.read(n).decode("utf-8")),
                    )
                )
                for n in z.namelist()
                if n.startswith(("word/", "docProps/")) and n.endswith(".xml")
            ),
        )
    for p in sorted(glob.glob(os.path.join(W, "gis", "*.geojson"))):
        with open(p) as fh:
            features = json.load(fh)["features"]
        yield (
            p,
            "\n".join(
                sorted(
                    {
                        v
                        for f in features
                        for v in f["properties"].values()
                        if isinstance(v, str)
                    }
                )
            ),
        )


@check("wording")
def _():
    n, bad = 0, []
    for p, t in texts():
        n += 1
        bad += [
            f"{base(p)}: {m.group(0)!r} in "
            f"\u2026{flat(t[max(0, m.start() - 60) : m.end() + 40])}\u2026"
            for m in BAD.finditer(t)
        ]
    return (
        bad,
        (
            f"{n:d} generated documents and layers: no agreed, ours, our "
            "boundary, TTB's published polygon, final text or bare Hickory "
            "Sandstone"
        ),
    )


# ---------------------------------------------------------------- GIS
NAD83 = osr.SpatialReference()
NAD83.ImportFromEPSG(4269)
NAD83.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
NAD27 = osr.SpatialReference()
NAD27.ImportFromEPSG(4267)
NAD27.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
_o = osr.CoordinateTransformationOptions()
_o.SetOperation(
    "+proj=pipeline +step +proj=axisswap +order=2,1 +step +proj=unitconvert "
    "+xy_in=deg +xy_out=rad +step +inv +proj=hgridshift "
    "+grids=us_noaa_nadcon5_nad27_nad83_1986_conus.tif +step "
    "+proj=unitconvert +xy_in=rad +xy_out=deg +step +proj=axisswap +order=2,1"
)
# NAD83 -> NAD27 by the NADCON 5.0 CONUS grid (CLAUDE.md: Datum)
TO27 = osr.CoordinateTransformation(NAD83, NAD27, _o)
# a 1:24,000 quad is a 7.5-minute cell; within 1 m of its neatline counts
CELL, EDGE_M = 0.125, 1.0


def neatlines():
    """Returns each quad's 7.5-minute cell, by the quad's name.

    The cell, given by its south-west corner (NAD27 lon, lat), is the one that
    holds the centre of the quad's neatline VRT template
    (resources/quads/cropped/*.vrt.in).
    """
    cells = {}
    for p in glob.glob(
        os.path.join(ROOT, "resources", "quads", "cropped", "*.vrt.in")
    ):
        x = read(p)
        srs = osr.SpatialReference(
            html.unescape(re.search(r"<SRS[^>]*>(.*?)</SRS>", x, re.S).group(1))
        )
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        geo = srs.CloneGeogCS()
        geo.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        g = [
            float(v)
            for v in re.search(r"<GeoTransform>(.*?)</GeoTransform>", x)
            .group(1)
            .split(",")
        ]
        nx, ny = (
            int(re.search(rf'raster{k}Size="(\d+)"', x).group(1)) for k in "XY"
        )
        lon, lat = osr.CoordinateTransformation(srs, geo).TransformPoint(
            g[0] + g[1] * nx / 2, g[3] + g[5] * ny / 2
        )[:2]
        cells[re.match(r"[A-Z]{2}_(.+?)_\d+_\d{4}_", base(p)).group(1)] = (
            math.floor(lon / CELL) * CELL,
            math.floor(lat / CELL) * CELL,
        )
    return cells


def off_m(c, lon, lat):
    """Returns the metres from a NAD27 point to a quad's cell (0 inside)."""
    dx = (
        max(c[0] - lon, 0, lon - c[0] - CELL)
        * 111320
        * math.cos(math.radians(lat))
    )
    dy = max(c[1] - lat, 0, lat - c[1] - CELL) * 110574
    return math.hypot(dx, dy)


@check("gis")
def _():
    cells, bad = neatlines(), []
    with open(
        os.path.join(ROOT, "resources", "quads", "quads-manifest.csv"),
        newline="",
    ) as fh:
        man = sorted(r["quad"].rsplit(",", 1)[0] for r in csv.DictReader(fh))
    if sorted(cells) != man or len(set(cells.values())) != len(cells):
        bad.append(
            f"neatlines: {sorted(cells.items())} from the VRT templates, "
            f"{man} in the manifest"
        )

    def quad_of(lon, lat, said):
        # the quad a NAD83 point is on: the one it names, if within EDGE_M of
        # that neatline, else the one whose cell holds it
        lo, la = TO27.TransformPoint(lon, lat)[:2]
        if said in cells and off_m(cells[said], lo, la) <= EDGE_M:
            return said
        return next(
            (k for k, c in cells.items() if off_m(c, lo, la) == 0), None
        )

    srcs = sorted(
        glob.glob(os.path.join(W, "gis", "*.geojson"))
        + glob.glob(os.path.join(W, "gis", "*.gpkg"))
    )
    shz = sorted(glob.glob(os.path.join(W, "gis", "shapefiles", "*.zip")))
    for z in shz:
        prj = [n for n in zipfile.ZipFile(z).namelist() if n.endswith(".prj")]
        srcs += [f"/vsizip/{z}/{n[:-4]}.shp" for n in prj]
        bad += [f"{base(z)}: no .prj"] if not prj else []
    if len(shz) != 3:
        bad.append(
            "expected the area, line and points shapefile zips, found "
            f"{[base(z) for z in shz]}"
        )
    nl, pts, lines, endq = 0, 0, 0, {}
    for src in srcs:
        ds = ogr.Open(src)
        for lyr in ds:
            nl += 1
            name = base(src)
            if not src.endswith((".geojson", ".shp")):
                name += ":" + lyr.GetName()
            srs = lyr.GetSpatialRef()
            if srs is None:
                bad.append(f"{name}: no coordinate system")
                continue
            srs = srs.Clone()
            srs.AutoIdentifyEPSG()
            if not (
                srs.IsGeographic() and srs.GetAuthorityCode(None) == "4269"
            ):
                bad.append(f"{name}: not NAD83 (EPSG:4269): {srs.GetName()}")
            fields = [
                lyr.GetLayerDefn().GetFieldDefn(i).GetName()
                for i in range(lyr.GetLayerDefn().GetFieldCount())
            ]
            gt = ogr.GT_Flatten(lyr.GetGeomType())
            for f in lyr:
                g = f.GetGeometryRef()
                step = f.GetField("step") if "step" in fields else None
                if gt == ogr.wkbPoint and "quad" in fields:
                    pts += 1
                    got = quad_of(g.GetX(), g.GetY(), f.GetField("quad"))
                    if got != f.GetField("quad"):
                        bad.append(
                            f"{name}: point {step} is on the {got} map, "
                            f"not {f.GetField('quad')} (quad)"
                        )
                if gt == ogr.wkbLineString and "length_m" in fields:
                    lines += 1
                    h = g.Clone()
                    h.AssignSpatialReference(NAD83)
                    gl = h.GeodesicLength()
                    if abs(gl - f.GetField("length_m")) > 0.5:
                        bad.append(
                            f"{name}: step {step} length_m "
                            f"{f.GetField('length_m')}, geodesic {gl:.1f} m"
                        )
                    if "quad" in fields:
                        x, y = g.GetPoint_2D(g.GetPointCount() - 1)
                        got = quad_of(x, y, f.GetField("quad"))
                        endq[step] = (got, gl)
                        if got != f.GetField("quad"):
                            bad.append(
                                f"{name}: step {step} ends on the {got} map, "
                                f"not {f.GetField('quad')} (quad)"
                            )
        ds = None
    for p in glob.glob(os.path.join(W, "documents", "*-steps.csv")):
        with open(p, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                q_, gl = endq.get(int(r["step"]), (None, None))
                if (
                    r["quad"] != q_
                    or gl is None
                    or abs(float(r["length_m"]) - gl) > 0.5
                ):
                    bad.append(
                        f"{base(p)}: step {r['step']} quad {r['quad']}, "
                        f"length_m {r['length_m']}; the line ends on {q_}, "
                        f"geodesic {gl and round(gl, 1)} m"
                    )
    if not pts or not lines:
        bad.append(
            "no point or line layer with quad / length_m found in "
            f"{os.path.join(W, 'gis')}"
        )
    return (
        bad,
        (
            f"{nl:d} layers (GeoJSON, GeoPackage, shapefiles' .prj) NAD83 "
            f"(EPSG:4269); {pts:d} points and {lines:d} step ends on the quad "
            "they name (NAD27 7.5' neatlines, NADCON 5.0 CONUS); "
            f"{lines:d} lengths geodesic within 0.5 m; the steps CSV agrees"
        ),
    )


# ---------------------------------------------------------------- package
@check("package")
def _():
    zips = glob.glob(os.path.join(DIST, "*.zip"))
    if len(zips) != 1:
        return [
            f"expected one zip in {DIST}, found {[base(z) for z in zips]}"
        ], ""
    stem = base(zips[0])[:-4]
    pre = f"C:\\Users\\{'U' * 20}\\Downloads\\{stem}\\"
    names = [
        n for n in zipfile.ZipFile(zips[0]).namelist() if not n.endswith("/")
    ]
    over = sorted(
        (n for n in names if len(pre) + len(n) > 259), key=len, reverse=True
    )
    if over:
        warned.append("package")
        print(
            f"WARNING: {len(over):d} of {len(names):d} paths in "
            f"{base(zips[0])} pass Windows' 260-character MAX_PATH when "
            f"Explorer extracts it to {pre} "
            f"(longest {len(pre) + len(over[0]):d}: {over[0]}); "
            "Explorer may refuse them (Dan: leave the names for now)"
        )
    return (
        [],
        (
            f"{len(names):d} files in {base(zips[0])}; longest path extracted "
            f"under {pre}: {len(pre) + max(map(len, names)):d} characters"
        ),
    )


summary = "all passed" if not failed else "FAILED: " + ", ".join(failed)
if warned:
    summary += f" (warnings: {', '.join(warned)})"
print(f"output checks: {summary}")
sys.exit(1 if failed else 0)
