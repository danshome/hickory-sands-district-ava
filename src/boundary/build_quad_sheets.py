"""The 13 USGS quads, original GeoPDF and GeoTIFF exactly as downloaded, with a filed boundary polyline added.

  target/quad-sheets/proposed-text/     line = boundary-per-proposed-text-line-EPSG4269.geojson               (Notice No. 243 as written)
  target/quad-sheets/petition-routing/  line = boundary-with-petition-western-routing-line-EPSG4269.geojson   (as the comment requests)

Inputs are read, never written: the step lines (resources/boundary/proposed/) and the
USGS originals (resources/quads/geopdf/*.pdf; resources/quads/geotiff/*.zip, read inside the zip). The TTB package build
uses only its functions, through src/boundary/build_agreed_quads.py.

GeoPDF: a PDF incremental update. The USGS file is copied byte for byte and the additions are appended after
  it: one optional-content layer holding the line (solid red, as TTB asks), drawn in page coordinates from
  the sheet's own TerraGo LGIDict transform, so it runs through the collar to the page edge; one structure
  element per filed feature carrying, as UserProperties, TTB's AVAs_Production fields (TTB's values for the Hickory
  Sands District record, with Area, Shape__Area and Shape__Length calculated from our polygon) followed by the
  filed line attributes (Acrobat's Model Tree / Object Data
  tool, GDAL and QGIS read the same records GDAL itself writes); and the catalog without /Perms, the USGS
  Reader-extensions signature, which would otherwise make Reader warn that the file changed after signing; and the
  filed line GeoJSON (NAD83, EPSG:4269, as TTB's AVA layer) as an embedded file beside the one USGS embeds. The
  original bytes, signature included, are unchanged at the head of the file.
GeoTIFF: the USGS file copied byte for byte, the AVA record (src/boundary/ttb_record.py) added as GDAL metadata, then only the 512x512 tiles the line crosses are rewritten (GDAL
  re-encodes them with the file's own JPEG tables; background pixels in those tiles measured unchanged) and the
  overviews refreshed over that area. Every other full-resolution tile is the USGS tile.

The quads keep their NAD27 polyconic grids. The filed NAD83 features are carried onto them with the NADCON 5.0
CONUS grid, pinned explicitly: PROJ's default for these unnamed quad CRSs tries Canadian NTv2 grids and then
the older NADCON. Same shift the QGIS projects pin for display. Every feature that reaches the sheet is kept whole.

Runs in the project's .venv (./build.sh makes it from requirements.txt).
"""
import codecs, glob, json, os, re, shutil, subprocess, sys, zipfile
import numpy as np
from osgeo import gdal, osr

import ttb_record
from PIL import Image, ImageDraw
from pypdf import PdfWriter
from pypdf.generic import (ArrayObject, BooleanObject, DecodedStreamObject, DictionaryObject, FloatObject, NameObject,
                           NumberObject, TextStringObject)

gdal.UseExceptions()
gdal.SetConfigOption("GDAL_PAM_ENABLED", "NO")  # no .aux.xml sidecars beside the deliverables

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the repository root (src/boundary/..)
GIS = os.path.join(ROOT, "resources", "boundary", "proposed")
OUT = os.path.join(ROOT, "target", "quad-sheets")
GRID = "us_noaa_nadcon5_nad27_nad83_1986_conus.tif"
RED = (1.0, 0.0, 0.0)  # TTB asks for a solid red line
LINE_PT = 0.5          # line width in PDF points (0.18 mm, about 4 m on the ground); the TIFF uses the same at 300 dpi

SETS = {
    "proposed-text": dict(src="boundary-per-proposed-text-line-EPSG4269.geojson", display="step",
                          layer="Hickory Sands District boundary - per proposed text (Notice No. 243)"),
    "petition-routing": dict(src="boundary-with-petition-western-routing-line-EPSG4269.geojson", display="line_name",
                             layer="Hickory Sands District boundary - with petition western routing"),
}


def pipeline(lon0):
    # NAD83 degrees (GDAL hands a custom pipeline EPSG:4269's lat,lon order, hence the swap) -> NAD27
    # (NADCON5 CONUS, inverse) -> the sheet's Clarke 1866 polyconic, metres.
    return ("+proj=pipeline +step +proj=axisswap +order=2,1 +step +proj=unitconvert +xy_in=deg +xy_out=rad "
            f"+step +inv +proj=hgridshift +grids={GRID} "
            f"+step +proj=poly +lat_0=0 +lon_0={lon0} +x_0=0 +y_0=0 +ellps=clrk66")


def project(fc, srs):
    """Filed features -> (properties, [line parts in sheet metres]); attributes are not touched."""
    opts = osr.CoordinateTransformationOptions()
    opts.SetOperation(pipeline(srs.GetProjParm(osr.SRS_PP_CENTRAL_MERIDIAN)))
    nad83 = osr.SpatialReference()
    nad83.ImportFromEPSG(4269)
    nad83.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(nad83, srs, opts)
    feats = []
    for f in fc["features"]:
        g = f["geometry"]
        parts = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        feats.append((f["properties"], [[ct.TransformPoint(x, y)[:2] for x, y, *_ in p] for p in parts]))
    return feats


def touching(feats, x0, y0, x1, y1):
    """Whole features with any vertex or segment near the sheet rectangle (generous 1 km pad)."""
    pad = 1000
    keep = []
    for props, parts in feats:
        xs = [x for p in parts for x, _ in p]
        ys = [y for p in parts for _, y in p]
        if max(xs) >= x0 - pad and min(xs) <= x1 + pad and max(ys) >= y0 - pad and min(ys) <= y1 + pad:
            keep.append((props, parts))
    return keep


# ---------------------------------------------------------------- GeoPDF (incremental update of the USGS file)

class RealObject(FloatObject):
    """A PDF real that always keeps its decimal point, so 2485.0 reads back as a real, not an integer
    (a column mixing integers and reals is read as text)."""
    def write_to_stream(self, stream, encryption_key=None):
        txt = repr(float(self))
        if "e" in txt or "E" in txt:  # PDF has no exponent notation
            txt = f"{float(self):.17f}".rstrip("0")
        stream.write((txt if "." in txt and not txt.endswith(".") else txt.rstrip(".") + ".0").encode())


def pdf_value(v):
    if isinstance(v, bool):
        return TextStringObject(str(v).lower())
    if isinstance(v, int):
        return NumberObject(v)
    if isinstance(v, float):
        return RealObject(v)
    return text("" if v is None else str(v))


def text(v):
    """A PDF text string; anything beyond ASCII goes out as UTF-16BE with a BOM. PDFDocEncoding would be valid
    too, but GDAL decodes it as Latin-1, turning the narratives' curly quotes into control characters."""
    t = TextStringObject(v)
    if not v.isascii():
        t.autodetect_utf16 = True
        t.utf16_bom = codecs.BOM_UTF16_BE
    return t


def build_pdf(orig_pdf, feats, s, pdf_out):
    shutil.copyfile(orig_pdf, pdf_out)
    w = PdfWriter(pdf_out, incremental=True)
    page = w.pages[0]
    root = w.root_object
    lgi = page["/LGIDict"]
    lgi = lgi[0] if isinstance(lgi, list) else lgi
    a, b, c, d, e, f = (float(v) for v in lgi.get_object()["/CTM"])  # page point -> map metre
    det = a * d - b * c
    to_page = lambda X, Y: ((d * (X - e) - c * (Y - f)) / det, (-b * (X - e) + a * (Y - f)) / det)
    W, H = float(page.mediabox.width), float(page.mediabox.height)
    X0, Y0 = e, f
    X1, Y1 = a * W + c * H + e, b * W + d * H + f
    feats = touching(feats, min(X0, X1), min(Y0, Y1), max(X0, X1), max(Y0, Y1))

    def path(parts):
        ops = []
        for p in parts:
            pts = [to_page(x, y) for x, y in p]
            ops.append(f"{pts[0][0]:.3f} {pts[0][1]:.3f} m")
            ops += [f"{x:.3f} {y:.3f} l" for x, y in pts[1:]]
        return "\n".join(ops) + "\nS"

    # Structure: a layer element under the root, one feature element per marked-content id on this page.
    st = root["/StructTreeRoot"].get_object()
    nums = st["/ParentTree"].get_object()["/Nums"]
    sp = page["/StructParents"]
    page_arr = nums[list(nums).index(sp) + 1].get_object()
    mcid0 = len(page_arr)
    layer_el = DictionaryObject({NameObject("/Type"): NameObject("/StructElem"), NameObject("/S"): NameObject("/Feature"),
                                 NameObject("/T"): TextStringObject(s["layer"]), NameObject("/P"): root.raw_get("/StructTreeRoot"),
                                 NameObject("/A"): DictionaryObject({NameObject("/O"): NameObject("/UserProperties")})})
    layer_ref = w._add_object(layer_el)
    kids = ArrayObject()
    ocg = w._add_object(DictionaryObject({NameObject("/Type"): NameObject("/OCG"), NameObject("/Name"): TextStringObject(s["layer"])}))
    # Each feature is a Form XObject drawn inside its marked-content id, the layout GDAL itself writes and reads.
    xobjs = {}

    def form(ops):
        x = DecodedStreamObject()
        x.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Form"),
                  NameObject("/BBox"): ArrayObject([FloatObject(0), FloatObject(0), FloatObject(W), FloatObject(H)])})
        x.set_data(ops.encode("latin-1"))
        name = f"/HSD{len(xobjs)}"
        xobjs[name] = w._add_object(x.flate_encode())
        return name

    body = ["q\n/OC /HSDLine BDC"]
    line_style = f"{RED[0]:g} {RED[1]:g} {RED[2]:g} RG {LINE_PT} w 1 J 1 j [] 0 d\n"
    for i, (props, parts) in enumerate(feats):
        mcid = mcid0 + i
        body.append(f"/feature <</MCID {mcid}>> BDC\n{form(line_style + path(parts))} Do\nEMC")
        ups = ArrayObject(DictionaryObject({NameObject("/N"): text(k), NameObject("/V"): pdf_value(v)})
                          for k, v in props.items())
        el = w._add_object(DictionaryObject({
            NameObject("/Type"): NameObject("/StructElem"), NameObject("/S"): NameObject("/feature"),
            NameObject("/T"): text(str(props.get(s["display"], i + 1))), NameObject("/P"): layer_ref,
            NameObject("/Pg"): page.indirect_reference, NameObject("/K"): NumberObject(mcid),
            NameObject("/A"): DictionaryObject({NameObject("/O"): NameObject("/UserProperties"), NameObject("/P"): ups})}))
        kids.append(el)
        page_arr.append(el)
    body.append("EMC\nQ\n")
    layer_el[NameObject("/K")] = kids
    old_k = st["/K"]
    st[NameObject("/K")] = ArrayObject(list(old_k) if isinstance(old_k, list) else [old_k]) + [layer_ref]

    stream = DecodedStreamObject()
    stream.set_data("\n".join(body).encode("latin-1"))
    stream = stream.flate_encode()
    contents = page.raw_get("/Contents")
    page[NameObject("/Contents")] = ArrayObject((list(contents.get_object()) if isinstance(contents.get_object(), list)
                                                  else [contents]) + [w._add_object(stream)])
    res = page["/Resources"].get_object()
    props_d = res.get("/Properties", DictionaryObject()).get_object() if "/Properties" in res else DictionaryObject()
    props_d[NameObject("/HSDLine")] = ocg
    res[NameObject("/Properties")] = props_d
    xo = res["/XObject"].get_object() if "/XObject" in res else DictionaryObject()
    for name, ref in xobjs.items():
        xo[NameObject(name)] = ref
    res[NameObject("/XObject")] = xo
    if "/Resources" in page and page.raw_get("/Resources") is not res:
        page[NameObject("/Resources")] = res
    # Add our layer to the document's optional content, keeping any layers the USGS file already has (the current
    # USGS GeoPDFs have none, but a merged list is correct either way).
    if "/OCProperties" in root:
        ocp = root["/OCProperties"].get_object()
        ocp[NameObject("/OCGs")] = ArrayObject(list(ocp.get("/OCGs", [])) + [ocg])
        d = ocp["/D"].get_object() if "/D" in ocp else DictionaryObject()
        for key in ("/Order", "/ON"):
            d[NameObject(key)] = ArrayObject(list(d.get(key, [])) + [ocg])
        ocp[NameObject("/D")] = d
        root[NameObject("/OCProperties")] = ocp
    else:
        root[NameObject("/OCProperties")] = DictionaryObject({
            NameObject("/OCGs"): ArrayObject([ocg]),
            NameObject("/D"): DictionaryObject({NameObject("/Order"): ArrayObject([ocg]), NameObject("/ON"): ArrayObject([ocg])})})
    mark = root["/MarkInfo"].get_object() if "/MarkInfo" in root else DictionaryObject()
    mark[NameObject("/Marked")] = BooleanObject(True)
    mark[NameObject("/UserProperties")] = BooleanObject(True)  # tells readers the structure carries attributes
    root[NameObject("/MarkInfo")] = mark
    # The filed line layer itself, byte for byte (NAD83, EPSG:4269, the CRS of TTB's AVA layer), as an attachment
    # beside the one USGS already embeds.
    with open(ttb_record.source(s["src"]), "rb") as fh:
        w.add_attachment(s["src"], fh.read())
    if "/Perms" in root:
        del root["/Perms"]
    with open(pdf_out, "wb") as fh:
        w.write(fh)
    return feats


# ---------------------------------------------------------------- GeoTIFF (only the crossed tiles rewritten)

def build_tif(zip_path, member, feats, tif_out, record=None, layer_src=None):
    with zipfile.ZipFile(zip_path) as z, z.open(member) as src, open(tif_out, "wb") as dst:
        shutil.copyfileobj(src, dst)
    gdal.SetConfigOption("IGNORE_COG_LAYOUT_BREAK", "YES")
    ds = gdal.Open(tif_out, gdal.GA_Update)
    X0, dx, _, Y0, _, dy = ds.GetGeoTransform()
    w, h = ds.RasterXSize, ds.RasterYSize
    feats = touching(feats, X0, Y0 + h * dy, X0 + w * dx, Y0)
    orig = np.dstack([ds.GetRasterBand(i).ReadAsArray() for i in (1, 2, 3)])
    im = Image.fromarray(orig)
    dr = ImageDraw.Draw(im)
    k = 300 / 72  # PDF points -> pixels at the sheet's 300 dpi
    rgb = tuple(round(v * 255) for v in RED)
    width = round(LINE_PT * k)
    for _, parts in feats:
        for p in parts:
            pts = [((x - X0) / dx, (y - Y0) / dy) for x, y in p]
            dr.line(pts, fill=rgb, width=width, joint="curve")
            for x, y in (pts[0], pts[-1]):  # round ends, like the PDF's round caps
                dr.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=rgb)
    new = np.asarray(im)
    bx, by = ds.GetRasterBand(1).GetBlockSize()
    tiles = 0
    for ty in range(0, h, by):
        for tx in range(0, w, bx):
            a, b_ = orig[ty:ty + by, tx:tx + bx], new[ty:ty + by, tx:tx + bx]
            if np.array_equal(a, b_):
                continue
            tiles += 1
            for i in range(3):
                ds.GetRasterBand(i + 1).WriteArray(np.ascontiguousarray(b_[:, :, i]), tx, ty)
            ds.FlushCache()
    if record:  # the AVA record as GDAL metadata (GDAL_METADATA tag), beside the USGS TIFF tags
        for k, v in record.items():
            ds.SetMetadataItem(k, "<Null>" if v is None else repr(v) if isinstance(v, float) else str(v))  # GDAL drops empty items
        ds.SetMetadataItem("boundary_layer", f"{layer_src} (NAD83, EPSG:4269), as filed in Attachment 2")
    ds = None
    # Refresh the overviews only where the base changed.
    ys, xs = np.nonzero(np.any(orig != new, axis=2))
    if len(xs):
        win = [X0 + xs.min() * dx, Y0 + ys.min() * dy, X0 + (xs.max() + 1) * dx, Y0 + (ys.max() + 1) * dy]
        subprocess.run(["gdaladdo", "-q", "-r", "average", "--partial-refresh-from-projwin",
                        *(f"{float(v):.3f}" for v in win), tif_out], check=True)
    return feats, tiles


def main():
    only = sys.argv[1:]  # optional quad-name filter, e.g. "Long Mountain"
    for setkey in SETS:
        os.makedirs(os.path.join(OUT, setkey), exist_ok=True)
    filed = {k: json.load(open(ttb_record.source(s["src"]))) for k, s in SETS.items()}
    ava = {k: ttb_record.ava_record(k) for k in SETS}
    oid = {k: {json.dumps(f["properties"], sort_keys=True): i + 1 for i, f in enumerate(filed[k]["features"])}
           for k in SETS}
    for orig_pdf in sorted(glob.glob(os.path.join(ROOT, "resources", "quads", "geopdf", "*_geo.pdf"))):
        stem = os.path.basename(orig_pdf)[:-4]                 # e.g. TX_Grit_110460_1970_24000_geo
        quadname = re.match(r"TX_(.+?)_\d+_", stem).group(1)
        if only and quadname not in only:
            continue
        zip_path = os.path.join(ROOT, "resources", "quads", "geotiff", stem + ".tif.zip")
        srs = osr.SpatialReference(gdal.Open(f"/vsizip/{zip_path}/{stem}.tif").GetProjection())
        for setkey, s in SETS.items():
            feats = project(filed[setkey], srs)
            base = os.path.join(OUT, setkey, stem)
            fp = build_pdf(orig_pdf, [(ttb_record.feature_record(ava[setkey], "line", p,
                                                                 oid[setkey][json.dumps(p, sort_keys=True)]), parts)
                                       for p, parts in feats],
                           s, base + ".pdf")
            ft, tiles = build_tif(zip_path, stem + ".tif", feats, base + ".tif",
                                  dict(ava[setkey], OBJECTID=1), s["src"])
            print(f"{quadname:18s} {setkey:17s} pdf features={len(fp):3d}  tif features={len(ft):3d}  tiles rewritten={tiles}")


if __name__ == "__main__":
    main()
