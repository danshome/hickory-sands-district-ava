"""The one attribute record every published file carries.

TTB can take any of the files (GeoJSON, GeoPDF, GeoTIFF) without adding fields
or calculating values.

Fields, in TTB's AVAs_Production order, then ours:
  OBJECTID           the feature number in its layer
  Name ... Counties  TTB's own values for the Hickory Sands District record
                     (OBJECTID 306), from resources/ttb/
                     hickory-sands-district-AVAs_Production-2026-10-14.json
  Area               square miles on the GRS 1980 ellipsoid, calculated from
                     this version's boundary polygon
  Shape__Area        planar area in square degrees (NAD83, EPSG:4269), as
                     TTB's layer stores it
  Shape__Length      planar perimeter in degrees
  area_sqmi, source  from the filed area layer (area_sqmi checked against the
                     calculated area)
  version_note       the filed area layer's Note, which says which version of
                     the boundary this is (TTB's Note for the record is empty,
                     so it takes TTB's value and ours moves here)
Area, Shape__Area and Shape__Length describe the AVA polygon, the same on every
feature of every layer of a version.

Field names that equal one of these ignoring case (GDAL, QGIS and ArcGIS match
field names case-insensitively) are renamed in the layers that carry them:
name -> point_name / line_name, note -> point_note, description ->
point_description / line_description.
"""

import json
import os

from osgeo import ogr
from osgeo import osr

ogr.UseExceptions()
ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # the repository root (src/boundary/..)
GIS = os.path.join(
    ROOT, "resources", "boundary", "proposed"
)  # (the filed Attachment 2 layers are no longer read)
CORRECTED = os.path.join(ROOT, "resources", "boundary", "proposed")


def source(name):
    """Returns the path of a filed Attachment 2 layer.

    The corrected copy (in CORRECTED) where one exists (made Oct. 14 by a
    script now in tobedeleted/), otherwise the layer as filed (in GIS).
    """
    c = os.path.join(CORRECTED, name)
    return c if os.path.exists(c) else os.path.join(GIS, name)


TTB_RECORD = os.path.join(
    ROOT,
    "resources",
    "ttb",
    "hickory-sands-district-AVAs_Production-2026-10-14.json",
)
TTB_FIELDS = [
    "OBJECTID",
    "Name",
    "Id",
    "Area",
    "States",
    "Phase",
    "Level_",
    "Contains_",
    "Within",
    "Established",
    "Status",
    "CFR_Section",
    "Partially_Overlaps",
    "Note",
    "Counties",
    "Shape__Area",
    "Shape__Length",
]
SQ_MILE = 1609.344**2

VERSIONS = {
    "proposed-text": "boundary-per-proposed-text",
    "petition-routing": "boundary-with-petition-western-routing",
}
RENAME = {  # per layer kind
    "area": {},
    "line": {"name": "line_name", "description": "line_description"},
    "points": {
        "name": "point_name",
        "note": "point_note",
        "description": "point_description",
    },
}


def ava_record(version):
    """Returns the AVA record of one version (OBJECTID None: set per feature).

    TTB's fields with TTB's values (Area, Shape__Area and Shape__Length
    calculated from the version's area layer), then ours (area_sqmi, source,
    version_note) from that layer.
    """
    with open(TTB_RECORD) as fh:
        ttb = json.load(fh)["features"][0]["attributes"]
    with open(source(f"{VERSIONS[version]}-area-EPSG4269.geojson")) as fh:
        area_fc = json.load(fh)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4269)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    f = area_fc["features"][0]
    g = ogr.CreateGeometryFromJson(json.dumps(f["geometry"]))
    g.AssignSpatialReference(srs)
    sqmi = g.GeodesicArea() / SQ_MILE
    filed = f["properties"]
    assert abs(sqmi - filed["area_sqmi"]) < 0.005, (sqmi, filed["area_sqmi"])
    rec = {k: ttb.get(k) for k in TTB_FIELDS}
    rec.update(
        OBJECTID=None,
        Area=sqmi,
        Shape__Area=g.Area(),
        Shape__Length=g.Boundary().Length(),
    )
    rec.update(
        area_sqmi=filed["area_sqmi"],
        source=filed["source"],
        version_note=filed["Note"],
    )
    return rec


def feature_record(ava, kind, props, oid):
    """Returns the record for one feature.

    The AVA record (OBJECTID = oid), then the layer's own fields, renamed where
    they would collide with a TTB field. For the area layer the AVA record is
    the whole record.
    """
    rec = dict(ava, OBJECTID=oid)
    if kind != "area":
        ren = RENAME[kind]
        for k, v in props.items():
            k2 = ren.get(k, k)
            assert k2.lower() not in {x.lower() for x in rec}, (kind, k2)
            rec[k2] = v
    return rec
