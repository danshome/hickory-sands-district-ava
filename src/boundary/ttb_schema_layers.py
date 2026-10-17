"""Attachment 2's six boundary layers with TTB's AVAs_Production fields added.

The fields come from src/boundary/ttb_record.py. The layers are read from
resources/boundary/proposed/ and written to target/ttb-schema-layers/ under the
same file names; every geometry is copied unchanged (checked). The TTB package
build uses only the shapefile writer and the field types.

  {version}-area     the AVA record (TTB fields + area_sqmi, source,
                     version_note)
  {version}-line     the AVA record, then the line's own fields
  {version}-points   the AVA record, then the point's own fields
"""

import json
import os
import shutil
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from osgeo import ogr
from osgeo import osr

import ttb_record

OUT = os.path.join(ttb_record.ROOT, "target", "ttb-schema-layers")


def main():
    """Writes the six layers, as GeoJSON and as shapefiles, with the record."""
    os.makedirs(OUT, exist_ok=True)
    for version, prefix in ttb_record.VERSIONS.items():
        ava = ttb_record.ava_record(version)
        for kind in ("area", "line", "points"):
            name = f"{prefix}-{kind}-EPSG4269.geojson"
            with open(ttb_record.source(name)) as fh:
                src = json.load(fh)
            out = {k: v for k, v in src.items() if k != "features"}
            out["features"] = [
                {
                    "type": "Feature",
                    "properties": ttb_record.feature_record(
                        ava, kind, f["properties"], i + 1
                    ),
                    "geometry": f["geometry"],
                }
                for i, f in enumerate(src["features"])
            ]
            text = json.dumps(out, ensure_ascii=False)
            back = json.loads(text)
            assert [f["geometry"] for f in back["features"]] == [
                f["geometry"] for f in src["features"]
            ], name
            with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
                fh.write(text)
            print(
                f"{name:62s} {len(out['features']):3d} features, "
                f"{len(out['features'][0]['properties'])} fields"
            )
            write_shapefile(out, name[: -len(".geojson")])


# Shapefile (.dbf) limits: field names of 10 characters, text of 254 bytes.
# TTB's fields keep the 10-character names ArcGIS gives them (Establishe,
# CFR_Sectio, Partially_, as in TTB's and the petition's shapefiles); text
# longer than 254 bytes continues in a second field so nothing is cut.
SHP_NAME = {
    "Established": "Establishe",
    "CFR_Section": "CFR_Sectio",
    "Partially_Overlaps": "Partially_",
    "Shape__Area": "Shape__Are",
    "Shape__Length": "Shape__Len",
    "version_note": "version_no",
    "petition_point": "petition_p",
    "line_description": "line_descr",
    "point_description": "point_desc",
}
SHP_CONT = {
    "version_note": "version_n2",
    "narrative": "narrativ2",
    "point_note": "point_not2",
    "point_description": "point_des2",
}
TTB_TYPE = {
    "OBJECTID": (ogr.OFTInteger, 0),
    "Id": (ogr.OFTInteger, 0),
    "Area": (ogr.OFTReal, 0),
    "Level_": (ogr.OFTInteger, 0),
    "Established": (ogr.OFTDate, 0),
    "Shape__Area": (ogr.OFTReal, 0),
    "Shape__Length": (ogr.OFTReal, 0),
    "Name": (ogr.OFTString, 50),
    "States": (ogr.OFTString, 50),
    "Phase": (ogr.OFTString, 50),
    "Status": (ogr.OFTString, 100),
    "CFR_Section": (ogr.OFTString, 50),
}
SHP_DIR = os.path.join(ttb_record.ROOT, "target", "shp-ttb-schema")
# The date written into the shapefiles (the .dbf header's last update) and
# their zips (every member's time), and build_proposed.py's GeoPackage:
# SOURCE_DATE_EPOCH, which build.sh sets to the package's date, not the time of
# writing, so the same features give the same bytes; the present time when it
# is not set.
DATE = time.gmtime(int(os.environ.get("SOURCE_DATE_EPOCH", time.time())))


def split254(text):
    """Splits a text for a .dbf text field of 254 bytes.

    Args:
        text: the text (or None).

    Returns:
        (text, None) if it fits in 254 bytes, else (its first 254 bytes or
        fewer, the rest), split inside a word.
    """
    b = (text or "").encode("utf-8")
    if len(b) <= 254:
        return text, None
    cut = 254
    # Break inside a word: not inside a UTF-8 character, and no space on either
    # side of the break, since .dbf readers trim the space padding at the end
    # of a field and would drop it.
    while cut and (
        (b[cut] & 0xC0) == 0x80
        or b[cut : cut + 1].isspace()
        or b[cut - 1 : cut].isspace()
    ):
        cut -= 1
    return b[:cut].decode("utf-8"), b[cut:].decode("utf-8")


def write_shapefile(fc, stem):
    """Writes a FeatureCollection as a shapefile, and zips it, in SHP_DIR.

    Field names longer than 10 characters are shortened (SHP_NAME), text
    longer than 254 bytes continues in a second field (SHP_CONT), TTB's fields
    get TTB's types (TTB_TYPE); <stem>-field-names.txt beside the shapefile
    lists the full names. The .dbf header and the zip's members are dated
    DATE.

    Args:
        fc: the GeoJSON FeatureCollection (one geometry type).
        stem: the shapefile's name, without .shp; also its folder's.
    """
    feats = fc["features"]
    keys = list(feats[0]["properties"])
    need2 = {
        k
        for k in keys
        if any(
            isinstance(f["properties"][k], str)
            and split254(f["properties"][k])[1]
            for f in feats
        )
    }
    d = os.path.join(SHP_DIR, stem)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    gtype = {
        "Polygon": ogr.wkbMultiPolygon,
        "MultiPolygon": ogr.wkbMultiPolygon,
        "LineString": ogr.wkbMultiLineString,
        "MultiLineString": ogr.wkbMultiLineString,
        "Point": ogr.wkbPoint,
    }[feats[0]["geometry"]["type"]]
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4269)
    ds = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(
        os.path.join(d, stem + ".shp")
    )
    lyr = ds.CreateLayer(
        stem,
        srs,
        gtype,
        options=[
            "ENCODING=UTF-8",
            "DBF_DATE_LAST_UPDATE=" + time.strftime("%Y-%m-%d", DATE),
        ],
    )
    cols, mapping = [], []
    for k in keys:
        vals = [
            f["properties"][k] for f in feats if f["properties"][k] is not None
        ]
        if k in TTB_TYPE:
            t, width = TTB_TYPE[k]
        elif vals and all(
            isinstance(v, int) and not isinstance(v, bool) for v in vals
        ):
            t, width = ogr.OFTInteger, 0
        elif vals and all(isinstance(v, (int, float)) for v in vals):
            t, width = ogr.OFTReal, 0
        else:
            t, width = ogr.OFTString, 254
        short = SHP_NAME.get(k, k)
        assert len(short) <= 10, short
        fd = ogr.FieldDefn(short, t)
        if width:
            fd.SetWidth(width)
        lyr.CreateField(fd)
        cols.append((k, short, None))
        mapping.append(f"{short:12s}{k}")
        if k in need2:
            fd2 = ogr.FieldDefn(SHP_CONT[k], ogr.OFTString)
            fd2.SetWidth(254)
            lyr.CreateField(fd2)
            cols[-1] = (k, short, SHP_CONT[k])
            mapping.append(
                f"{SHP_CONT[k]:12s}{k}, continued "
                "(characters after the first 254 bytes)"
            )
    for f in feats:
        of = ogr.Feature(lyr.GetLayerDefn())
        for k, short, cont in cols:
            v = f["properties"][k]
            if v is None:
                continue
            if cont:
                v, rest = split254(v)
                if rest:
                    of.SetField(cont, rest)
            of.SetField(short, v)
        g = ogr.CreateGeometryFromJson(json.dumps(f["geometry"]))
        of.SetGeometry(
            ogr.ForceToMultiPolygon(g)
            if gtype == ogr.wkbMultiPolygon
            else ogr.ForceToMultiLineString(g)
            if gtype == ogr.wkbMultiLineString
            else g
        )
        lyr.CreateFeature(of)
    ds = None
    with open(os.path.join(d, stem + "-field-names.txt"), "w") as fh:
        fh.write(
            "Shapefile field names (10 characters at most) and the full field "
            "names they stand for.\n"
            "TTB's fields keep the names ArcGIS gives them in a shapefile; the "
            "full names are those of TTB's\n"
            "AVAs_Production layer, as in the GeoJSON and GeoPDF versions of "
            "this layer.\n\n" + "\n".join(mapping) + "\n"
        )
    zp = os.path.join(SHP_DIR, f"{stem}-shp.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for n in sorted(os.listdir(d)):
            # the entry z.write would make, but dated DATE, not the file's time
            info = zipfile.ZipInfo.from_file(os.path.join(d, n), n)
            info.date_time = DATE[:6]
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(os.path.join(d, n), "rb") as fh:
                z.writestr(info, fh.read())
    print(
        f"    shapefile {os.path.basename(zp)}: {len(cols)} fields "
        f"(+{len(need2)} continuation)"
    )


if __name__ == "__main__":
    main()
