"""Minimal HTML -> DOCX converter for the response document (stdlib only).

Why not `textutil -convert docx`: on this Mac, textutil's DOCX writer drops <table> structure (cells become
plain paragraphs) and drops <img> entirely, and the response depends on its summary table and exhibit maps.
This converter handles exactly the subset the response HTML uses: h1-h3, p, div.(note|sig|pagebreak|quote),
blockquote, ul/ol/li, table/tr/th/td (colspan), img (width in inches via data-w), b/strong, i/em, u, a, br, sup, span.
Usage: python3 html2docx.py in.html out.docx
"""

from html.parser import HTMLParser
import os
import re
import struct
import sys
from xml.sax.saxutils import escape
import zipfile

EMU = 914400


def png_size(p):
    with open(p, "rb") as f:
        d = f.read(24)
    w, h = struct.unpack(">II", d[16:24])
    return w, h


def jpeg_size(p):
    with open(p, "rb") as f:
        d = f.read()
    i = 2
    while i < len(d):
        m = d[i + 1]
        seg_len = struct.unpack(">H", d[i + 2 : i + 4])[0]
        if m in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", d[i + 5 : i + 9])
            return w, h
        i += 2 + seg_len
    raise ValueError("no SOF marker in " + p)


def img_size(p):
    return (
        jpeg_size(p) if p.lower().endswith((".jpg", ".jpeg")) else png_size(p)
    )


class Conv(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.body = []
        self.runs = None
        self.fmt = []
        self.pstyle = None
        self.list_stack = []
        self.table = None
        self.cell = None
        self.row = None
        self.media = []
        self.link = None
        self.skip = 0
        self.ppr_extra = ""
        self.in_title = False
        self.cell_shade = None

    # ---- paragraph handling
    def start_par(self, style=None, extra=""):
        self.flush()
        self.runs = []
        self.pstyle = style
        self.ppr_extra = extra

    def flush(self):
        if self.runs is None:
            return
        ppr = ""
        if self.pstyle:
            ppr += f'<w:pStyle w:val="{self.pstyle}"/>'
        ppr += self.ppr_extra
        xml = f"<w:p><w:pPr>{ppr}</w:pPr>{''.join(self.runs)}</w:p>"
        (self.cell if self.cell is not None else self.body).append(xml)
        self.runs = None
        self.pstyle = None
        self.ppr_extra = ""

    def run(self, text):
        if self.runs is None:
            self.start_par(self.default_style())
        rpr = ""
        if "b" in self.fmt:
            rpr += "<w:b/>"
        if "i" in self.fmt:
            rpr += "<w:i/>"
        if "u" in self.fmt or self.link:
            rpr += '<w:u w:val="single"/>'
        if self.link:
            rpr += '<w:color w:val="1F3A93"/>'
        if "sup" in self.fmt:
            rpr += '<w:vertAlign w:val="superscript"/>'
        if "small" in self.fmt:
            rpr += '<w:sz w:val="18"/>'
        if "del" in self.fmt:
            rpr += '<w:strike/><w:color w:val="C00000"/>'
        if "ins" in self.fmt:
            rpr += '<w:highlight w:val="yellow"/>'
        if "new" in self.fmt:
            rpr += '<w:b/><w:highlight w:val="green"/>'
        if "red" in self.fmt:
            rpr += '<w:b/><w:color w:val="C00000"/><w:sz w:val="24"/>'
        self.runs.append(
            f"<w:r><w:rPr>{rpr}</w:rPr>"
            f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'
        )

    def default_style(self):
        if self.cell is not None:
            return "TableText"
        return "BodyText"

    # ---- parser callbacks
    def handle_starttag(self, tag, a):
        a = dict(a)
        cls = a.get("class", "")
        if tag in ("style", "script", "head", "title"):
            self.skip += 1
            return
        if tag in ("h1", "h2", "h3"):
            self.start_par(
                {"h1": "Heading1", "h2": "Heading2", "h3": "Heading3"}[tag]
            )
        elif tag == "p":
            st = (
                "TableText"
                if self.cell is not None
                else (
                    "Note"
                    if "note" in cls
                    else ("Small" if "small" in cls else "BodyText")
                )
            )
            if "center" in cls:
                self.start_par(st, '<w:jc w:val="center"/>')
            else:
                self.start_par(st)
        elif tag == "blockquote":
            self.start_par("Quote")
        elif tag == "div" and "pagebreak" in cls:
            self.flush()
            self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        elif tag in ("ul", "ol"):
            self.flush()
            self.list_stack.append(tag)
        elif tag == "li":
            self.start_par(
                "ListBullet"
                if self.list_stack and self.list_stack[-1] == "ul"
                else "ListNumber"
            )
        elif tag in ("b", "strong"):
            self.fmt.append("b")
        elif tag in ("i", "em"):
            self.fmt.append("i")
        elif tag == "u":
            self.fmt.append("u")
        elif tag == "sup":
            self.fmt.append("sup")
        elif tag == "small":
            self.fmt.append("small")
        elif tag in ("del", "s"):
            self.fmt.append("del")
        elif tag == "ins":
            self.fmt.append("ins")
        elif tag == "mark":
            self.fmt.append("new")
        elif tag == "red":
            self.fmt.append("red")
        elif tag == "a":
            self.link = a.get("href")
        elif tag == "br":
            if self.runs is None:
                self.start_par(self.default_style())
            self.runs.append("<w:r><w:br/></w:r>")
        elif tag == "table":
            self.flush()
            self.table = {
                "rows": [],
                "widths": [
                    float(x) for x in a.get("data-cols", "").split(",") if x
                ],
            }
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
            self.cell_span = int(a.get("colspan", 1))
            self.cell_th = tag == "th"
            self.cell_shade = a.get("data-shade")
            if tag == "th":
                self.fmt.append("b")
        elif tag == "img":
            src = a.get("src")
            p = os.path.join(self.base, src)
            wpx, hpx = img_size(p)
            win = float(a.get("data-w", "6.5"))
            cx = int(win * EMU)
            cy = int(cx * hpx / wpx)
            ext = "jpeg" if p.lower().endswith((".jpg", ".jpeg")) else "png"
            rid = f"rIdImg{len(self.media) + 1}"
            name = f"image{len(self.media) + 1}.{ext}"
            self.media.append((rid, name, p))
            n = len(self.media)
            drawing = (
                "<w:r><w:drawing>"
                '<wp:inline distT="0" distB="0" distL="0" distR="0">'
                f'<wp:extent cx="{cx}" cy="{cy}"/>'
                f'<wp:docPr id="{n}" name="Picture {n}"/>'
                "<wp:cNvGraphicFramePr>"
                '<a:graphicFrameLocks noChangeAspect="1"/>'
                "</wp:cNvGraphicFramePr>"
                "<a:graphic><a:graphicData"
                ' uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
                "<pic:pic><pic:nvPicPr>"
                f'<pic:cNvPr id="{n}" name="{name}"/><pic:cNvPicPr/>'
                "</pic:nvPicPr>"
                f'<pic:blipFill><a:blip r:embed="{rid}"/>'
                "<a:stretch><a:fillRect/></a:stretch></pic:blipFill>"
                '<pic:spPr><a:xfrm><a:off x="0" y="0"/>'
                f'<a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
                '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
                "</pic:pic></a:graphicData></a:graphic></wp:inline>"
                "</w:drawing></w:r>"
            )
            if self.runs is None:
                self.start_par("Figure", '<w:jc w:val="center"/>')
            self.runs.append(drawing)

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head", "title"):
            self.skip -= 1
            return
        if tag in ("h1", "h2", "h3", "p", "li", "blockquote"):
            self.flush()
        elif tag in ("ul", "ol"):
            self.flush()
            self.list_stack.pop()
        elif tag in ("b", "strong"):
            self._pop("b")
        elif tag in ("i", "em"):
            self._pop("i")
        elif tag == "u":
            self._pop("u")
        elif tag == "sup":
            self._pop("sup")
        elif tag == "small":
            self._pop("small")
        elif tag in ("del", "s"):
            self._pop("del")
        elif tag == "ins":
            self._pop("ins")
        elif tag == "mark":
            self._pop("new")
        elif tag == "red":
            self._pop("red")
        elif tag == "a":
            self.link = None
        elif tag in ("td", "th"):
            self.flush()
            if not self.cell:
                self.cell.append(
                    '<w:p><w:pPr><w:pStyle w:val="TableText"/></w:pPr></w:p>'
                )
            self.row.append(
                (
                    self.cell,
                    self.cell_span,
                    self.cell_shade if not self.cell_th else "E8EDF3",
                )
            )
            self.cell = None
            if tag == "th":
                self._pop("b")
        elif tag == "tr":
            self.table["rows"].append(self.row)
            self.row = None
        elif tag == "table":
            self.body.append(self.table_xml(self.table))
            self.table = None

    def _pop(self, f):
        for i in range(len(self.fmt) - 1, -1, -1):
            if self.fmt[i] == f:
                del self.fmt[i]
                return

    def handle_data(self, d):
        if self.skip:
            return
        if self.runs is None and self.cell is None and not d.strip():
            return
        if self.cell is not None and self.runs is None and not d.strip():
            return
        d = re.sub(r"\s+", " ", d)
        if self.runs is None or not self.runs:
            d = d.lstrip()
        if d:
            self.run(d)

    def table_xml(self, t):
        ncols = max(sum(s for _, s, _ in r) for r in t["rows"])
        widths = t["widths"] or [6.5 / ncols] * ncols
        grid = "".join(f'<w:gridCol w:w="{int(w * 1440)}"/>' for w in widths)
        rows = []
        for ri, r in enumerate(t["rows"]):
            cells = []
            ci = 0
            for content, span, shade in r:
                w = sum(widths[ci : ci + span])
                ci += span
                tcpr = f'<w:tcW w:w="{int(w * 1440)}" w:type="dxa"/>'
                if span > 1:
                    tcpr += f'<w:gridSpan w:val="{span}"/>'
                if shade:
                    tcpr += (
                        '<w:shd w:val="clear" w:color="auto"'
                        f' w:fill="{shade}"/>'
                    )
                cells.append(
                    f"<w:tc><w:tcPr>{tcpr}</w:tcPr>{''.join(content)}</w:tc>"
                )
            trpr = (
                "<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>"
                if ri == 0
                else "<w:trPr><w:cantSplit/></w:trPr>"
            )
            rows.append(f"<w:tr>{trpr}{''.join(cells)}</w:tr>")
        b = '<w:{0} w:val="single" w:sz="4" w:space="0" w:color="808080"/>'
        borders = "".join(
            b.format(x)
            for x in ("top", "left", "bottom", "right", "insideH", "insideV")
        )
        return (
            "<w:tbl><w:tblPr>"
            f'<w:tblW w:w="{int(sum(widths) * 1440)}" w:type="dxa"/>'
            f"<w:tblBorders>{borders}</w:tblBorders>"
            '<w:tblLayout w:type="fixed"/><w:tblCellMar>'
            '<w:left w:w="72" w:type="dxa"/><w:right w:w="72" w:type="dxa"/>'
            "</w:tblCellMar></w:tblPr>"
            f"<w:tblGrid>{grid}</w:tblGrid>{''.join(rows)}</w:tbl>"
            '<w:p><w:pPr><w:spacing w:after="60"/></w:pPr></w:p>'
        )


STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    "<w:styles"
    ' xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
    "<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts"
    ' w:ascii="Times New Roman" w:hAnsi="Times New Roman"'
    ' w:cs="Times New Roman" w:eastAsia="Times New Roman"/>'
    '<w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="en-US"/></w:rPr>'
    "</w:rPrDefault>\n"
    "<w:pPrDefault><w:pPr>"
    '<w:spacing w:after="120" w:line="252" w:lineRule="auto"/></w:pPr>'
    "</w:pPrDefault></w:docDefaults>\n"
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
    '<w:name w:val="Normal"/></w:style>\n'
    '<w:style w:type="paragraph" w:styleId="BodyText">'
    '<w:name w:val="Body Text"/><w:basedOn w:val="Normal"/><w:pPr>'
    '<w:jc w:val="both"/></w:pPr></w:style>\n'
    '<w:style w:type="paragraph" w:styleId="Heading1">'
    '<w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
    '<w:next w:val="BodyText"/><w:pPr><w:keepNext/>'
    '<w:spacing w:before="120" w:after="120"/><w:jc w:val="center"/>'
    '<w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="30"/>'
    "</w:rPr></w:style>\n"
    '<w:style w:type="paragraph" w:styleId="Heading2">'
    '<w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>'
    '<w:next w:val="BodyText"/><w:pPr><w:keepNext/>'
    '<w:spacing w:before="240" w:after="100"/><w:outlineLvl w:val="1"/>'
    '</w:pPr><w:rPr><w:b/><w:sz w:val="25"/></w:rPr></w:style>\n'
    '<w:style w:type="paragraph" w:styleId="Heading3">'
    '<w:name w:val="heading 3"/><w:basedOn w:val="Normal"/>'
    '<w:next w:val="BodyText"/><w:pPr><w:keepNext/>'
    '<w:spacing w:before="180" w:after="80"/><w:outlineLvl w:val="2"/>'
    '</w:pPr><w:rPr><w:b/><w:sz w:val="22"/></w:rPr></w:style>\n'
    '<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/>'
    '<w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="567" w:right="567"/>'
    '<w:jc w:val="both"/></w:pPr><w:rPr><w:sz w:val="21"/></w:rPr>'
    "</w:style>\n"
    '<w:style w:type="paragraph" w:styleId="Note"><w:name w:val="Note"/>'
    '<w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="284"/>'
    '<w:jc w:val="both"/></w:pPr><w:rPr><w:sz w:val="20"/></w:rPr>'
    "</w:style>\n"
    '<w:style w:type="paragraph" w:styleId="Small"><w:name w:val="Small"/>'
    '<w:basedOn w:val="Normal"/><w:rPr><w:sz w:val="19"/></w:rPr></w:style>\n'
    '<w:style w:type="paragraph" w:styleId="TableText">'
    '<w:name w:val="Table Text"/><w:basedOn w:val="Normal"/><w:pPr>'
    '<w:spacing w:before="20" w:after="20" w:line="228" w:lineRule="auto"/>'
    '</w:pPr><w:rPr><w:sz w:val="18"/></w:rPr></w:style>\n'
    '<w:style w:type="paragraph" w:styleId="Figure">'
    '<w:name w:val="Figure"/><w:basedOn w:val="Normal"/><w:pPr>'
    '<w:keepNext/><w:jc w:val="center"/></w:pPr></w:style>\n'
    '<w:style w:type="paragraph" w:styleId="ListBullet">'
    '<w:name w:val="List Bullet"/><w:basedOn w:val="Normal"/><w:pPr>'
    '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
    '<w:ind w:left="567" w:hanging="283"/><w:jc w:val="both"/></w:pPr>'
    "</w:style>\n"
    '<w:style w:type="paragraph" w:styleId="ListNumber">'
    '<w:name w:val="List Number"/><w:basedOn w:val="Normal"/><w:pPr>'
    '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr>'
    '<w:ind w:left="567" w:hanging="340"/><w:jc w:val="both"/></w:pPr>'
    "</w:style>\n"
    "</w:styles>"
)

NUMBERING = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    "<w:numbering"
    ' xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
    '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0">'
    '<w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/>'
    '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="567" w:hanging="283"/>'
    "</w:pPr></w:lvl></w:abstractNum>\n"
    '<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0">'
    '<w:start w:val="1"/><w:numFmt w:val="decimal"/>'
    '<w:lvlText w:val="%1."/><w:lvlJc w:val="left"/><w:pPr>'
    '<w:ind w:left="567" w:hanging="340"/></w:pPr></w:lvl></w:abstractNum>\n'
    '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
    '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>\n'
    "</w:numbering>"
)


def footer_xml(text):
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        "<w:ftr"
        ' xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:p><w:pPr><w:tabs>"
        '<w:tab w:val="center" w:pos="4680"/>'
        '<w:tab w:val="right" w:pos="9360"/></w:tabs></w:pPr>'
        '<w:r><w:rPr><w:sz w:val="17"/></w:rPr>'
        '<w:t xml:space="preserve">Docket No. TTB-2026-0005</w:t></w:r>'
        '<w:r><w:rPr><w:sz w:val="17"/></w:rPr><w:tab/>'
        '<w:t xml:space="preserve">Page </w:t></w:r>'
        '<w:r><w:rPr><w:sz w:val="17"/></w:rPr>'
        '<w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:rPr><w:sz w:val="17"/></w:rPr>'
        '<w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        '<w:r><w:rPr><w:sz w:val="17"/></w:rPr>'
        '<w:fldChar w:fldCharType="end"/></w:r>'
        '<w:r><w:rPr><w:sz w:val="17"/></w:rPr>'
        '<w:t xml:space="preserve"> of </w:t></w:r>'
        '<w:r><w:rPr><w:sz w:val="17"/></w:rPr>'
        '<w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:rPr><w:sz w:val="17"/></w:rPr>'
        '<w:instrText xml:space="preserve"> NUMPAGES </w:instrText></w:r>'
        '<w:r><w:rPr><w:sz w:val="17"/></w:rPr>'
        '<w:fldChar w:fldCharType="end"/></w:r>'
        '<w:r><w:rPr><w:sz w:val="17"/></w:rPr><w:tab/>'
        f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p></w:ftr>'
    )


def convert(src, dst, footer, title="", author=""):
    c = Conv(os.path.dirname(os.path.abspath(src)))
    with open(src, encoding="utf-8") as f:
        text = f.read()
    landscape = 'name="orientation" content="landscape"' in text
    c.feed(text)
    c.flush()
    ns = (
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        ' xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
        ' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        ' xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"'
    )
    sect = (
        '<w:sectPr><w:footerReference w:type="default" r:id="rIdFtr"/>'
        + (
            '<w:pgSz w:w="15840" w:h="12240" w:orient="landscape"/>'
            if landscape
            else '<w:pgSz w:w="12240" w:h="15840"/>'
        )
        + '<w:pgMar w:top="1296" w:right="1296" w:bottom="1296" w:left="1296"'
        ' w:header="720" w:footer="576" w:gutter="0"/></w:sectPr>'
    )
    doc = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {ns}><w:body>{''.join(c.body)}{sect}</w:body>"
        "</w:document>"
    )
    rels = [
        (
            '<Relationship Id="rIdStyles"'
            ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"'
            ' Target="styles.xml"/>'
        ),
        (
            '<Relationship Id="rIdNum"'
            ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering"'
            ' Target="numbering.xml"/>'
        ),
        (
            '<Relationship Id="rIdFtr"'
            ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer"'
            ' Target="footer1.xml"/>'
        ),
    ]
    rels += [
        (
            f'<Relationship Id="{rid}"'
            ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"'
            f' Target="media/{name}"/>'
        )
        for rid, name, _ in c.media
    ]
    ct = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        "<Types"
        ' xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '<Default Extension="jpeg" ContentType="image/jpeg"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/word/numbering.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
        '<Override PartName="/word/footer1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        "</Types>"
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        "<cp:coreProperties"
        ' xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:dcterms="http://purl.org/dc/terms/"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{escape(title)}</dc:title>"
        f"<dc:creator>{escape(author)}</dc:creator></cp:coreProperties>"
    )
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            "<Relationships"
            ' xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1"'
            ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
            ' Target="word/document.xml"/>'
            '<Relationship Id="rId2"'
            ' Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"'
            ' Target="docProps/core.xml"/></Relationships>',
        )
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/numbering.xml", NUMBERING)
        z.writestr("word/footer1.xml", footer_xml(footer))
        z.writestr(
            "word/_rels/document.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            "<Relationships"
            ' xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(rels)
            + "</Relationships>",
        )
        z.writestr("docProps/core.xml", core)
        for _rid, name, p in c.media:
            z.write(p, f"word/media/{name}")


if __name__ == "__main__":
    convert(
        sys.argv[1],
        sys.argv[2],
        title=sys.argv[3] if len(sys.argv) > 3 else "",
        author=sys.argv[4] if len(sys.argv) > 4 else "",
        footer=sys.argv[5]
        if len(sys.argv) > 5
        else sys.exit(
            "usage: html2docx.py in.html out.docx title author footer"
        ),
    )
