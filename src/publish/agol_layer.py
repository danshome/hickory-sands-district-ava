"""Hosted feature layers and the web map for the PROPOSED boundary.

They go in Dan's folder, shared only to the private group and placed in
category 4 > Map and layer:
- publishes the GeoPackage item (4c) as a hosted feature layer (4b), with
  exports allowed (Query, Extract);
- attaches the key PDFs (read-me, description, TTB notice with the changes
  highlighted, side-by-side) to the AVA polygon;
- sets symbology and pop-ups on the layer item, and readable field aliases on
  every hosted layer;
- publishes the build's comparison with the AVA Map Explorer polygon
  (target/work/review) as a GeoPackage (4j) and hosted layer (4k): the big
  differences (the lines 100 m or more apart) and every piece of land between
  the two boundaries;
- builds a web map (4a) over the 13 USGS quadrangle scans cited in paragraph
  (b), from Esri's USA Historical Topo Maps service locked to those editions,
  with the AVA Map Explorer polygon (TTB's live AVAs_Production, blue) under
  the proposed revision, the land between them shaded, and the big
  differences ringed.

Re-running reuses the layer, overwrites the comparison layer and updates the
map. Never write "agreed".

What it sends is built without signing in (the item properties at module
level; boundary_plan(), diff_plan(), geo_plan(), grit_plan(), webmap_plan():
pop-ups, field aliases, the layers' visualizations and the web map, from the
layers given; plan() all of them at once), so the publish dry run
(agol_dryrun.py) writes and checks it; main() signs in, publishes the layers,
and sends each piece where it always has.

Sign-in: GIS(profile="hsd"). Run by ./build.sh publish (or .venv/bin/python
src/publish/agol_layer.py).
"""

import hashlib
import json
import math
import os
import sys
import time

from arcgis.features import FeatureLayerCollection
from arcgis.gis import GIS
from arcgis.gis import ItemProperties
from arcgis.gis import ItemTypeEnum
from osgeo import gdal

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)  # src/
import revision

gdal.UseExceptions()

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)  # the repository root
HERE = os.environ.get("HSD_WORK") or os.path.join(
    ROOT, "target", "work"
)  # build work dir (build.sh stages resources/ here)
with open(os.path.join(HERE, "proposed-steps.json")) as f:
    PROPOSED = json.load(f)
SQMI = f"{PROPOSED['sqmi']:.2f}"  # the AVA's area, GRS80 square miles
STEPS = len(PROPOSED["steps"])  # the boundary's steps, as the build made them
PKG = os.path.join(HERE, "pkg", revision.NAME)
FOLDER = "Hickory Sands District - Final Proposed Boundary and Narrative"
GROUP_ID = "65720ee9c5a743f88659ae39228704ec"
CAT = "/Categories/4 GIS data/Map and layer"
C4D = "/Categories/4 GIS data/Downloads (GeoPackage + shapefiles + GeoJSON)"
TTB_URL = "https://services7.arcgis.com/ykuAbKu9MbV93nAe/ArcGIS/rest/services/AVAs_Production/FeatureServer/0"
TTB_WHERE = "Name = 'Hickory Sands District'"
REVIEW = os.path.join(HERE, "review")
DIFF_GPKG = os.path.join(
    REVIEW, "hickory-sands-district-differences-from-ttb-EPSG4269.gpkg"
)
# The date GDAL stamps on the GeoPackages written here (last_change in
# gpkg_contents), fixed so the same features always give the same bytes: then
# hosted() sees an unchanged file and skips overwriting 4k and 4o (issue #74).
# The proposed boundary's date, as in the file names.
GPKG_DATE = f"{revision.ISO}T00:00:00.000Z"
DIFF_SRC_TITLE = (
    "4j Differences from the AVA Map Explorer polygon - GeoPackage (the big "
    "ones, and all of them)"
)
DIFF_TITLE = (
    "4k Differences from the AVA Map Explorer polygon - layer (the big ones, "
    "and all of them)"
)
# Earlier titles, so a re-run finds and retitles those items.
DIFF_WAS = (
    [
        (
            "4j Differences from TTB's published polygon - GeoPackage (the "
            "big ones, and all of them)"
        ),
        (
            "4j Differences from TTB's published polygon - GeoPackage (rings, "
            "short tips)"
        ),
    ],
    [
        (
            "4k Differences from TTB's published polygon - layer (the big "
            "ones, and all of them)"
        ),
        (
            "4k Differences from TTB's published polygon - layer (rings, "
            "short tips)"
        ),
    ],
)
# The names used everywhere a reader sees them (Dan, 2026-10-16: the official
# names, no "ours" and "TTB's").
REV, MAPX, N243 = (
    "the proposed revision",
    "the AVA Map Explorer polygon",
    "Notice No. 243",
)
SAME_TEXT, TEXT_CHANGE = (
    "the same text, drawn differently",
    "the proposed text change near Grit",
)
GEO_GPKG = os.path.join(
    ROOT,
    "resources",
    "geology",
    "usgs-sgmc-geology-shifted-to-naip-EPSG4269.gpkg",
)  # see its README.md
GEO_SRC_TITLE = (
    "4l Geology - USGS SGMC units shifted to the outcrops - GeoPackage"
)
GEO_TITLE = "4m Geology - USGS SGMC units shifted to the outcrops - layer"
GRIT_GPKG = os.path.join(
    REVIEW, "hickory-sands-district-change-near-grit-EPSG4269.gpkg"
)  # from src/review/grit_change.py
GRIT_SRC_TITLE = (
    "4n The change near Grit - GeoPackage (lines swapped, areas moved, "
    "granite acres)"
)
GRIT_TITLE = (
    "4o The change near Grit - layer (lines swapped, areas moved, granite "
    "acres)"
)
TOPO = "https://historical1.arcgis.com/arcgis/rest/services/USA_Historical_Topo_Maps/ImageServer"
# The four basemaps of TTB's AVA Map Explorer (https://www.ttb.gov/ava; its web
# map ae8e5830627f439c97b05ff285568c80).
ESRI = "https://services.arcgisonline.com/arcgis/rest/services/"
VTS = "https://cdn.arcgis.com/sharing/rest/content/items/{}/resources/styles/root.json"
# Esri public style item ids
TOPO_STYLE = "7dc6cea0b1764a1f9af2e679f642f0f5"  # pragma: allowlist secret
STREETS_STYLE = "de26a3cf4cc9451298ea173c4b324736"  # pragma: allowlist secret
TTB_BASEMAPS = [
    (
        "Topographic (TTB's default)",
        [
            (
                "World Hillshade",
                "ArcGISTiledMapServiceLayer",
                ESRI + "Elevation/World_Hillshade/MapServer",
            ),
            (
                "World Topographic Map",
                "VectorTileLayer",
                VTS.format(TOPO_STYLE),
            ),
        ],
    ),
    (
        "Streets",
        [
            (
                "World Street Map",
                "VectorTileLayer",
                VTS.format(STREETS_STYLE),
            )
        ],
    ),
    (
        "Imagery",
        [
            (
                "World Imagery",
                "ArcGISTiledMapServiceLayer",
                ESRI + "World_Imagery/MapServer",
            )
        ],
    ),
    (
        "USA Topo Maps",
        [
            (
                "USA Topo Maps (USGS topographic maps)",
                "ArcGISTiledMapServiceLayer",
                ESRI + "USA_Topo_Maps/MapServer",
            )
        ],
    ),
]
RASTERS = [
    145300,
    145405,
    145725,
    146412,
    147043,
    147287,
    148287,
    148500,
    148654,
    149400,
    149688,
    150198,
    150346,
]  # the 13 editions


def year(field, label):
    """Returns a pop-up field for a year of the quadrangle catalog.

    The year is printed 1970, not 1,970.

    Args:
        field: The catalog's field.
        label: The label the pop-up shows.

    Returns:
        The pop-up's fieldInfo.
    """
    return {
        "fieldName": field,
        "label": label,
        "visible": True,
        "format": {"places": 0, "digitSeparator": False},
    }


QUADS = {
    "id": "usgs-quads",
    "title": "USGS 1:24,000 quadrangles cited in paragraph (b) (Esri USA "
    "Historical Topo Maps)",
    "url": TOPO,
    "layerType": "ArcGISImageServiceLayer",
    "visibility": True,
    "opacity": 1,
    # The service is time-enabled; without this Map Viewer filters to
    # 1878-1891 and hides the 1955-1970 sheets.
    "timeAnimation": False,
    "mosaicRule": {
        "mosaicMethod": "esriMosaicLockRaster",
        "lockRasterIds": RASTERS,
        "ascending": True,
        "mosaicOperation": "MT_FIRST",
    },
    # Scanned maps: no "Red: Band_1, Green: Band_2, Blue: Band_3" legend (QA
    # #46).
    "showLegend": False,
    "popupInfo": {
        # the sheet, not the catalog's 20 raw fields (QA #46)
        "title": "{Map_Name}, {Primary_State} ({Date_On_Map})",
        "fieldInfos": [
            {"fieldName": "Map_Name", "label": "Map name", "visible": True},
            {"fieldName": "Primary_State", "label": "State", "visible": True},
            year("Date_On_Map", "Date on map"),
            year("Photo_Revision", "Photorevised"),
            year("Photo_Inspection", "Photoinspected"),
        ],
        "popupElements": [
            {
                "type": "text",
                "text": "USGS 1:24,000 quadrangle cited in paragraph (b), "
                "from Esri's USA Historical Topo Maps.",
            },
            {"type": "fields"},
        ],
    },
}
CREDIT = "Dan McLaughlin, Robert Clay Vineyards (petitioner)"
CC0 = (
    "CC0 1.0 Universal (public domain dedication): no rights reserved. TTB, "
    "its contractors and anyone else may copy, change and use this for any "
    "purpose without permission or attribution. "
    "https://creativecommons.org/publicdomain/zero/1.0/"
)
# The web map shows more than the petitioner's work, so its license and credits
# name each part (QA #30).
LIC_MAP = (
    "The map and the petitioner's layers (the proposed revision, the "
    "differences, the change near Grit, the shift of the geology): "
    + CC0
    + " The AVA Map Explorer polygon (TTB's AVAs_Production layer) and the "
    "step text from Notice No. 243: U.S. Government work (public domain). "
    "USGS quadrangles and USGS SGMC geology: public domain. Basemaps: Esri, "
    "under Esri's terms of use."
)
# The boundary layer (4b) holds TTB's text and data too (the step text, the
# AVAs_Production values): the same split as the downloads 4c-4i
# (agol_publish.py).
LIC_GIS = (
    "TTB's text and data, the step text from Notice No. 243 (boundary line "
    "layer) and the values copied from TTB's AVAs_Production record (Name, "
    "Status, Counties and the like): U.S. Government work (public domain). "
    "The petitioner's work, the boundary as drawn, its other attributes and "
    "the proposed changes to the text: " + CC0
)
CREDIT_GIS = (
    CREDIT + "; TTB (Notice No. 243 step text, AVAs_Production record values)"
)
CREDIT_MAP = (
    CREDIT
    + "; TTB (AVAs_Production layer, Notice No. 243); USGS (quadrangles, via "
    "Esri USA Historical Topo Maps; SGMC geology); basemaps: Esri"
)
TAGS = [
    "Hickory Sands District",
    "AVA",
    "TTB",
    "Notice No. 243",
    "TTB-2026-0005",
    "proposed boundary",
]
CULTURE = "en-us"
# TTB's own aliases for its AVAs_Production fields (Level_ is "Level",
# Contains_ is "Contains"), from the layer's definition.
with open(
    os.path.join(
        ROOT,
        "resources",
        "ttb",
        "AVAs_Production-layer0-definition-2026-10-14.json",
    )
) as f:
    TTB_ALIAS = {
        field["name"]: field["alias"] for field in json.load(f)["fields"]
    }


def bbox(path):
    """Returns an item's extent: that of every layer in a vector file.

    Args:
        path: The vector file (NAD83 longitude and latitude).

    Returns:
        [[xmin, ymin], [xmax, ymax]], rounded outward to 4 decimals.
    """
    ds = gdal.OpenEx(path, gdal.OF_VECTOR)
    e = [
        ds.GetLayer(i).GetExtent() for i in range(ds.GetLayerCount())
    ]  # (xmin, xmax, ymin, ymax)
    return [
        [
            math.floor(min(x[0] for x in e) * 1e4) / 1e4,
            math.floor(min(x[2] for x in e) * 1e4) / 1e4,
        ],
        [
            math.ceil(max(x[1] for x in e) * 1e4) / 1e4,
            math.ceil(max(x[3] for x in e) * 1e4) / 1e4,
        ],
    ]


EXTENT = bbox(
    os.path.join(
        PKG,
        "4_GIS",
        f"{revision.STEM}-area-EPSG4269.geojson",
    )
)  # the AVA
ABOUT = (
    "<p>Hickory Sands District AVA (Docket No. TTB-2026-0005, Notice No. "
    "243, 91 FR 52576): the boundary the petitioners propose, with the "
    "changes discussed with TTB on October 15, 2026. Prepared by Dan "
    "McLaughlin, Robert Clay Vineyards (petitioner).</p>"
)
# An item's title is how ./build.sh publish finds it again: a fixed identifier
# (like the services' names), not a figure the build derives.
LAYER_TITLE = (
    "4b Proposed boundary - layer (AVA polygon, 104 steps, step endpoints)"
)
MAP_TITLE = "4a Proposed boundary - map over the 13 USGS quadrangles"
NAMES = {
    "esriGeometryPolygon": "AVA (proposed, " + SQMI + " sq mi)",
    "esriGeometryPolyline": f"Boundary steps ({STEPS})",
    "esriGeometryPoint": "Step endpoints",
}
ATTACH = [
    os.path.join(
        HERE,
        "documents",
        f"Hickory-Sands-District-read-me-first-{revision.ISO}.pdf",
    ),
    os.path.join(
        PKG,
        "1_boundary-description",
        "Hickory-Sands-District-boundary-description-as-proposed-2026-10-"
        "15.pdf",
    ),
    os.path.join(
        PKG,
        "2_TTB-notice-243-with-changes-highlighted",
        "TTB-Notice-243-with-proposed-Hickory-Sands-District-changes-"
        f"highlighted-{revision.ISO}-UNOFFICIAL.pdf",
    ),
    os.path.join(
        PKG,
        "3_changes-side-by-side",
        f"Hickory-Sands-District-boundary-changes-side-by-side-{revision.ISO}.pdf",
    ),
]

gis = folder = typed = (
    None  # signed in and listed by main(); hosted() uses them
)

READ_ONLY = {
    "capabilities": "Query,Extract"
}  # public layers: no editing by anyone (issue #25: publish leaves editing on)


def lock(lyr):
    """Makes a hosted layer read-only.

    Viewers may query and export it, never add, change or delete features.

    Args:
        lyr: The hosted feature layer item.

    Returns:
        The same item.
    """
    FeatureLayerCollection.fromitem(lyr).manager.update_definition(READ_ONLY)
    return lyr


props = {
    "snippet": "The proposed boundary as a hosted feature layer: the AVA "
    f"polygon, the {STEPS} boundary steps with their text, and the step "
    "endpoints. Exports allowed.",
    "description": ABOUT
    + "<p>Add it to ArcGIS Pro from the portal, or open it in Map Viewer. "
    "Click the AVA polygon for the documents (attached): read-me, boundary "
    "description, TTB's notice with the proposed changes highlighted, and "
    "the side-by-side. Click a step for its text and what changed. Export to "
    "shapefile, file geodatabase, GeoPackage, GeoJSON and others from the "
    "item page.</p><p>ArcGIS Online stores this hosted layer in Web Mercator "
    "(EPSG:3857), and exports from the item page are made from that copy. "
    "For the data in NAD83 (EPSG:4269), the datum of TTB's AVAs_Production "
    "layer, download items 4c-4i: the GeoPackage this layer is published "
    "from (4c), the shapefiles (4d-4f) and the GeoJSON (4g-4i), all with "
    "TTB's AVAs_Production fields.</p>",
    "tags": ",".join(TAGS),
    "licenseInfo": LIC_GIS,
    "accessInformation": CREDIT_GIS,
    "culture": CULTURE,
    "extent": EXTENT,
}


def boundary_layers(layers):
    """Returns the hosted layer 4b's three layers by geometry type.

    Args:
        layers: The layers of 4b.

    Returns:
        {geometry type: layer}: polygon (the AVA), polyline (the steps), point
        (the endpoints).
    """
    return {lyr.properties.geometryType: lyr for lyr in layers}


# ---- the layer's features, as built (issue #71)
# The layer is published from the GeoPackage once; a republish used to leave its
# features as first published (the live steps kept old wording and attributes).
# Each feature is updated in place from the package's GeoJSON, matched by step
# (lines), point (points) or as the one AVA polygon, so the object ids and the
# documents attached to the polygon stay. Only when the build's files changed
# (their SHA-256 is kept in the item's properties). Editing is on for the
# update only, and the layer is locked again whatever happens (main()).
BUILT = {
    g: os.path.join(
        PKG,
        "4_GIS",
        f"{revision.STEM}-{k}-EPSG4269.geojson",
    )
    for g, k in (
        ("esriGeometryPolygon", "area"),
        ("esriGeometryPolyline", "line"),
        ("esriGeometryPoint", "points"),
    )
}
KEY = {
    "esriGeometryPolygon": None,
    "esriGeometryPolyline": "step",
    "esriGeometryPoint": "point",
}


def esri(g):
    """Returns a GeoJSON geometry (NAD83 lon/lat) as Esri JSON (wkid 4269)."""
    sr, c = {"wkid": 4269}, g["coordinates"]
    return {
        "Point": lambda: {"x": c[0], "y": c[1]},
        "LineString": lambda: {"paths": [c]},
        "MultiLineString": lambda: {"paths": c},
        "Polygon": lambda: {"rings": c},
        "MultiPolygon": lambda: {"rings": [r for p in c for r in p]},
    }[g["type"]]() | {"spatialReference": sr}


# ---- symbology, pop-ups and field aliases
def fields(lyr, wanted):
    """Returns a pop-up's fieldInfos: the wanted fields the layer has.

    Args:
        lyr: The layer.
        wanted: (field, label) pairs, in order; a field is matched whatever
            its case.

    Returns:
        A visible fieldInfo for each wanted field the layer has, named as the
        layer names it.
    """
    have = {f["name"].lower(): f["name"] for f in lyr.properties.fields}
    return [
        {"fieldName": have[k.lower()], "label": label, "visible": True}
        for k, label in wanted
        if k.lower() in have
    ]


WORDS = {
    "n": "Number",
    "label": "Label",
    "what": "Which area",
    "why": "Why",
    "side": "Side",
    "area_sqmi": "Area (sq mi, GRS 1980)",
    "source": "Source",
    "version_note": "Version",
    "point": "Point number",
    "kind": "Kind",
    "step": "Step",
}  # fields no pop-up shows


def alias_fields(lyr, wanted=(), ttb=False):
    """Returns readable field aliases for a layer (QA #31).

    The aliases show in the attribute table, the dashboard and exports. For
    TTB's AVAs_Production fields (ttb=True) TTB's own alias, else the name in
    words (CFR_Section: CFR Section); for the others the pop-up's label, else
    a plain name. The service's own fields (object id, global id, shape area
    and length) keep theirs.

    Args:
        lyr: The layer.
        wanted: The pop-up's (field, label) pairs.
        ttb: Whether the layer has TTB's AVAs_Production fields.

    Returns:
        The fields whose alias changes, each whole (as update_definition
        takes them); set_aliases() sends them.
    """
    labels = {k.lower(): v for k, v in wanted}
    geom = lyr.properties.get("geometryProperties") or {}
    own = {
        lyr.properties.get("objectIdField"),
        lyr.properties.get("globalIdField"),
        geom.get("shapeAreaFieldName"),
        geom.get("shapeLengthFieldName"),
    }

    def words(n):
        return " ".join(n.replace("_", " ").split())

    out = []
    for f in lyr.properties.fields:
        n = f["name"]
        if n in own:
            continue
        if ttb and n in TTB_ALIAS:
            a = TTB_ALIAS[n] if TTB_ALIAS[n] != n else words(n)
        else:
            a = labels.get(n.lower()) or WORDS.get(n.lower()) or words(n)
        if f.get("alias") != a:
            out.append(
                {**json.loads(json.dumps(f, default=dict)), "alias": a}
            )  # the whole field, as a plain dict
    return out


def set_aliases(lyr, out):
    """Sends a layer's changed fields (alias_fields()), if any.

    A failure is printed, not raised.

    Args:
        lyr: The layer.
        out: The fields to send.
    """
    if out:
        try:
            lyr.manager.update_definition({"fields": out})
        # The ArcGIS API raises bare Exception: a failure is reported, and
        # the publish goes on.
        except Exception as e:  # noqa: BLE001
            print(
                "could not set the field aliases of",
                lyr.properties.name,
                type(e).__name__,
            )


NOTE = (
    "The boundary as proposed to TTB; the changes near Grit were discussed "
    "with TTB on October 15, 2026."
)


def popup(title, lyr, wanted, attachments=False, text=None):
    """Returns a layer's pop-up.

    Args:
        title: The pop-up's title ({field} placeholders allowed).
        lyr: The layer.
        wanted: The (field, label) pairs to show, in order.
        attachments: Whether to list the feature's attachments.
        text: A text to show above the fields, if any.

    Returns:
        The popupInfo: the text, the fields, then the attachments.
    """
    p = {
        "title": title,
        "fieldInfos": fields(lyr, wanted),
        "showAttachments": attachments,
        "popupElements": [],
    }
    if text:
        p["popupElements"].append({"type": "text", "text": text})
    p["popupElements"].append({"type": "fields"})
    if attachments:
        p["popupElements"].append(
            {"type": "attachments", "displayType": "list"}
        )
    return p


RED = [220, 0, 0, 255]
area_def = {
    "drawingInfo": {
        "renderer": {
            "type": "simple",
            "symbol": {
                "type": "esriSFS",
                "style": "esriSFSSolid",
                "color": [255, 0, 0, 18],
                "outline": {
                    "type": "esriSLS",
                    "style": "esriSLSSolid",
                    "color": RED,
                    "width": 1.2,
                },
            },
        }
    }
}
line_def = {
    "drawingInfo": {
        "renderer": {
            "type": "simple",
            "symbol": {
                "type": "esriSLS",
                "style": "esriSLSSolid",
                "color": RED,
                "width": 2.4,
            },
        }
    }
}
pts_def = {
    "drawingInfo": {
        "renderer": {
            "type": "simple",
            "symbol": {
                "type": "esriSMS",
                "style": "esriSMSCircle",
                "color": [255, 255, 255, 255],
                "size": 5,
                "outline": {
                    "type": "esriSLS",
                    "color": [0, 0, 0, 255],
                    "width": 1,
                },
            },
        },
        "labelingInfo": [
            {
                "labelExpressionInfo": {
                    "expression": "IIf(IsEmpty($feature.step), '', '(' + "
                    "$feature.step + ')')"
                },
                "labelPlacement": "esriServerPointLabelPlacementAboveRight",
                "symbol": {
                    "type": "esriTS",
                    "color": [0, 0, 0, 255],
                    "haloColor": [255, 255, 255, 255],
                    "haloSize": 1.5,
                    "font": {"family": "Arial", "size": 9, "weight": "bold"},
                },
                "minScale": 150000,
            }
        ],
    },
    "showLabels": True,
}
AREA_F = [
    ("Name", "Name"),
    ("Status", "Status"),
    ("Area", "Area (sq mi)"),
    ("Counties", "Counties"),
    ("Within", "Within"),
    ("CFR_Section", "CFR section"),
    ("version_note", "Version"),
]
LINE_F = [
    ("narrative", "Text"),
    ("change", "Change from Notice No. 243's text"),
    ("txt_source", "Text source"),
    ("endpoint", "Ends at"),
    ("quad", "USGS quadrangle"),
    ("length_m", "Length (m)"),
]
PTS_F = [
    ("step", "Step"),
    ("point_name", "Point"),
    ("kind", "Kind"),
    ("quad", "USGS quadrangle"),
]


# ---- GeoPackage items and the hosted layers made from them
def hosted_props(gpkg, props):
    """Returns a GeoPackage item's and its hosted layer's properties.

    They get the GeoPackage's extent, for location search (QA #31).

    Args:
        gpkg: The GeoPackage.
        props: The item's properties (snippet, description, tags, ...).

    Returns:
        The properties with the culture and the extent.
    """
    return {**props, "culture": CULTURE, "extent": bbox(gpkg)}


def hosted(gpkg, src_title, title, service, props, was=((), ())):
    """Publishes a GeoPackage item and a read-only hosted layer from it.

    Both are in the folder. A re-run replaces the file and overwrites the
    layer, or, if the file is the same, only updates their properties.

    Args:
        gpkg: The GeoPackage.
        src_title: The GeoPackage item's title.
        title: The hosted layer's title.
        service: The feature service's name.
        props: The items' properties (snippet, description, tags, ...).
        was: (the GeoPackage item's earlier titles, the layer's), so a re-run
            finds an item that was retitled.

    Returns:
        (the GeoPackage item, the hosted layer item).
    """

    def find(kind, *titles):
        return next(
            (typed[(x, kind)] for x in titles if (x, kind) in typed), None
        )

    src = find("GeoPackage", src_title, *was[0], title)
    lyr = find("Feature Service", title, *was[1], src_title, *was[0])
    # The service published from this file, whatever its title (an overwrite
    # retitles it).
    if lyr is None and src is not None:
        lyr = next(iter(src.related_items("Service2Data", "reverse")), None)
    props = hosted_props(gpkg, props)
    with open(gpkg, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    if (
        src is not None
        and lyr is not None
        and (src.properties or {}).get("sha256", "") in (sha, "")
        and (
            (src.properties or {}).get("sha256")
            or src.size == os.path.getsize(gpkg)
        )
    ):  # the same file: no republish
        src.update(
            item_properties={
                "title": src_title,
                **props,
                "properties": {**(src.properties or {}), "sha256": sha},
            }
        )
        lyr.update(item_properties={"title": title, **props})
        print("unchanged", lyr.id, lyr.url)
        return src, lock(lyr)
    if src is None:
        src = folder.add(
            ItemProperties(
                title=src_title,
                item_type=ItemTypeEnum.GEOPACKAGE,
                tags=TAGS,
                snippet=props["snippet"],
                description=props["description"],
                license_info=props["licenseInfo"],
                access_information=props["accessInformation"],
                culture=CULTURE,
                extent=props["extent"],
                properties={"sha256": sha},
            ),
            file=gpkg,
        ).result()
    else:
        src.update(
            item_properties={
                "title": src_title,
                **props,
                "properties": {**(src.properties or {}), "sha256": sha},
            },
            data=gpkg,
        )
    pp = gis.content.analyze(item=src, file_type="geoPackage")[
        "publishParameters"
    ]
    pp["name"] = service
    if lyr is None:
        lyr = src.publish(publish_parameters=pp, file_type="geoPackage")
        if lyr.ownerFolder != folder.properties.get("id"):
            lyr.move(folder)
        print("published", lyr.id, lyr.url)
    else:
        # The item's file was replaced above; republish over the same service
        # (manager.overwrite names it from the title).
        src.publish(
            publish_parameters=pp, file_type="geoPackage", overwrite=True
        )
        status = (
            f"{gis._portal.resturl}content/users/{lyr.owner}/items/{lyr.id}"
            "/status"
        )
        # The job retitles the service when it finishes, so set the title after
        # that (2 min at most).
        for _ in range(60):
            if (
                gis._con.get(status, {"f": "json"}).get("status")
                != "processing"
            ):
                break
            time.sleep(2)
        print("overwrote", lyr.id, lyr.url)
    lyr.update(item_properties={"title": title, **props})
    return src, lock(lyr)


def rename(lyr, nm):
    """Renames a layer of a service, unless it has that name; prints a failure.

    Args:
        lyr: The layer.
        nm: Its name.
    """
    if lyr.properties.name != nm:
        try:
            lyr.manager.update_definition({"name": nm})
        # The ArcGIS API raises bare Exception: a failure is reported, and
        # the publish goes on.
        except Exception as e:  # noqa: BLE001
            print(
                "could not rename",
                lyr.properties.name,
                "->",
                nm,
                type(e).__name__,
            )


# ---- differences from the AVA Map Explorer polygon
# From the build's comparison (src/review/compare_ttb.py): the big differences
# (rings where the two lines are at least STATS["big_m"] apart, renumbered 1..
# in step order) and every piece of land between the two boundaries, in one
# GeoPackage and one hosted layer, overwritten on a re-run. The comparison's
# working fields (its CHECK status, labels) stay home.
with open(os.path.join(REVIEW, "ttb-diff-stats.json")) as f:
    STATS = json.load(f)
BIG_M, MED = STATS["big_m"], STATS["median_m"]
OTHER_PATH = "the two lines take different paths"
with open(os.path.join(REVIEW, "ttb-diff-rings-EPSG4269.geojson")) as f:
    big = [
        feature
        for feature in json.load(f)["features"]
        if feature["properties"]["big"]
    ]
for n, f in enumerate(big, 1):
    p = f["properties"]
    f["properties"] = {
        "n": n,
        "why": TEXT_CHANGE
        if p["status"].startswith("intended")
        else OTHER_PATH,
        "steps": p["steps"],
        "kind": p["kind"],
        "max_apart_m": p["max_apart_m"],
        "length_m": p["length_m"],
        "revision_only_acres": p["ours_adds_acres"],
        "map_explorer_only_acres": p["ours_drops_acres"],
        "endpoints": p["pins"],
    }
with open(os.path.join(REVIEW, "ttb-diff-areas-EPSG4269.geojson")) as f:
    pieces = json.load(f)
for f in pieces["features"]:
    f["properties"]["cause"] = (
        TEXT_CHANGE
        if f["properties"]["cause"] == "proposed text change"
        else SAME_TEXT
    )
NBIG, NPIECES = len(big), len(pieces["features"])
same, change = STATS["areas"]["drawing"], STATS["areas"]["proposed text change"]


def make_diff_gpkg(path=DIFF_GPKG):
    """Makes the GeoPackage 4j: the big differences and all the differences.

    Two layers, big_differences and all_differences, each first written as a
    GeoJSON file beside it. The dry run makes its own copy.

    Args:
        path: The GeoPackage to make (replaced if it is there).

    Returns:
        path.
    """
    if os.path.exists(path):
        os.remove(path)
    for name, feats in (
        ("big_differences", big),
        ("all_differences", pieces["features"]),
    ):
        tmp = os.path.join(
            os.path.dirname(path), f"publish-{name}-EPSG4269.geojson"
        )
        with open(tmp, "w") as f:
            json.dump(
                {
                    "type": "FeatureCollection",
                    "crs": pieces["crs"],
                    "features": feats,
                },
                f,
            )
        with gdal.config_option("OGR_CURRENT_DATE", GPKG_DATE):
            gdal.VectorTranslate(
                path,
                tmp,
                format="GPKG",
                layerName=name,
                accessMode="append" if os.path.exists(path) else None,
            )
    return path


DIFF_ABOUT = (
    ABOUT
    + f"<p>Two layers comparing {REV} (red, drawn from the proposed text) "
    f"with {MAPX} (blue, TTB's AVAs_Production layer for Notice No. 243). The "
    "Map Explorer polygon was digitized by hand; the proposed revision "
    "follows the centre of the printed linework of the USGS maps. So the two "
    "lines differ a little almost everywhere: measured every 2 m along each "
    f"line, the median distance to the other line is {MED:.0f} m. (The pieces "
    "of land between them are narrower on average, since each tapers to "
    f"nothing where the lines cross.)</p><p><b>Big differences</b> ({NBIG}): "
    f"the places where the two lines are {BIG_M:.0f} m or more apart, where "
    "they take different paths, or the proposed text change near Grit. Each "
    "gives the steps, how far apart the lines are, the length of the "
    "stretch, the acres in one and not the other, and how far each step's "
    "endpoint is from the Map Explorer polygon's nearest vertex.</p><p><b>"
    f"All differences</b> ({NPIECES} pieces): every piece of land in one and "
    f"not the other. From {SAME_TEXT}: {same['revision_only_acres']:,.0f} "
    f"acres in {REV} only and {same['map_explorer_only_acres']:,.0f} acres in "
    f"{MAPX} only ({same['pieces']} pieces). From {TEXT_CHANGE}: "
    f"{change['revision_only_acres']:,.0f} and "
    f"{change['map_explorer_only_acres']:,.0f} acres ({change['pieces']} "
    "pieces).</p>"
)
dprops = {
    "snippet": f"The {NBIG} big differences ({BIG_M:.0f} m or more apart) "
    f"between {REV} and {MAPX}, and all {NPIECES} pieces of land between the "
    "two lines.",
    "description": DIFF_ABOUT,
    "tags": ",".join(TAGS),
    "licenseInfo": CC0,
    "accessInformation": CREDIT
    + "; compared with TTB's AVAs_Production polygon (the AVA Map Explorer "
    "polygon, Notice No. 243)",
}
# The published services' names are their URLs: fixed identifiers, not the
# revision's date, so a new date never breaks the dashboard's or anyone's links.
DIFF_SERVICE = "Hickory_Sands_District_differences_from_TTB_2026_10_15"
DNAMES = {
    "big": f"Big differences from the Map Explorer polygon ({NBIG})",
    "all": f"All differences between the two lines ({NPIECES} pieces)",
}


def diff_layers(layers):
    """Returns the hosted layer 4k's two layers: (big differences, all)."""
    return (
        next(x for x in layers if "big" in x.properties.name.lower()),
        next(x for x in layers if "all" in x.properties.name.lower()),
    )


# ---- geology (USGS SGMC, shifted to the outcrops)
GEO_ABOUT = (
    ABOUT
    + "<p>Three USGS geologic units near the AVA: Town Mountain Granite, the "
    "younger granitic intrusions and the Hickory Sandstone Member formation, "
    "from the USGS State Geologic Map Compilation (Horton and others, 2017, "
    "USGS Data Series 1052; public domain). SGMC as published sits about 400 "
    "m south-east of the outcrops seen on USDA NAIP imagery, so every "
    "polygon is shifted -0.002356 deg longitude and +0.002993 deg latitude "
    "(about 225 m west, 331 m north, fitted to the granite outcrop trace); "
    "each feature records its source and the shift. Context only: no "
    "boundary line comes from these layers.</p>"
)
gprops = {
    "snippet": "USGS geologic units near the AVA (granite and the Hickory "
    "Sandstone Member formation), shifted about 400 m to sit on the outcrops.",
    "description": GEO_ABOUT,
    "tags": ",".join([*TAGS, "geology", "SGMC"]),
    "licenseInfo": "USGS data (public domain); shift " + CC0,
    "accessInformation": "USGS State Geologic Map Compilation; shift: "
    + CREDIT,
}
GEO_SERVICE = "Hickory_Sands_District_geology_SGMC_shifted"
GEO = [
    ("town", "Town Mountain Granite (USGS SGMC, shifted)", [232, 96, 140]),
    (
        "younger",
        "Younger granitic intrusions (USGS SGMC, shifted)",
        [150, 90, 200],
    ),
    (
        "hickory",
        "Hickory Sandstone Member formation (USGS SGMC, shifted)",
        [214, 168, 50],
    ),
]
GEO_F = [
    ("name", "SGMC unit"),
    ("unit_link", "Unit code"),
    ("generalize", "Rock type"),
    ("area_acres", "Area (acres)"),
    ("source", "Source"),
    ("alignment", "Shift"),
    ("unit_url", "USGS unit page"),
]


def geo_layers(layers):
    """Returns the hosted layer 4m's three layers, with their names and colours.

    Args:
        layers: The layers of 4m.

    Returns:
        [(layer, name, rgb)], in GEO's order.
    """
    return [
        (next(x for x in layers if key in x.properties.name.lower()), nm, rgb)
        for key, nm, rgb in GEO
    ]


def geo_def(rgb):
    """Returns a geology layer's definition: an rgb fill, solid outline."""
    return {
        "drawingInfo": {
            "renderer": {
                "type": "simple",
                "symbol": {
                    "type": "esriSFS",
                    "style": "esriSFSSolid",
                    "color": [*rgb, 60],
                    "outline": {
                        "type": "esriSLS",
                        "style": "esriSLSSolid",
                        "color": [*rgb, 255],
                        "width": 0.8,
                    },
                },
            }
        }
    }


# ---- the change near Grit, line by line and acre by acre
with open(os.path.join(REVIEW, "grit-change-stats.json")) as f:
    GSTATS = json.load(f)["areas"]


def make_grit_gpkg(path=GRIT_GPKG):
    """Makes the GeoPackage 4n: what the change near Grit swaps and moves.

    Two layers: lines_swapped (the lines the change swaps) and areas_moved
    (the areas it moves). The dry run makes its own copy.

    Args:
        path: The GeoPackage to make (replaced if it is there).

    Returns:
        path.
    """
    if os.path.exists(path):
        os.remove(path)
    for f, name in (
        ("grit-change-lines-EPSG4269.geojson", "lines_swapped"),
        ("grit-change-areas-EPSG4269.geojson", "areas_moved"),
    ):
        with gdal.config_option("OGR_CURRENT_DATE", GPKG_DATE):
            gdal.VectorTranslate(
                path,
                os.path.join(REVIEW, f),
                format="GPKG",
                layerName=name,
                accessMode="append" if os.path.exists(path) else None,
            )
    return path


def gs(k, f="acres"):
    """Returns whole acres of a Grit area, as the map's labels show them.

    Rounded once, half up, from the build's unrounded stats (issue #33).

    Args:
        k: The area (a key of grit-change-stats.json's areas).
        f: The figure: acres, granite_acres or sandstone_acres.

    Returns:
        The acres, with thousands separators.
    """
    return f"{math.floor(GSTATS[k][f] + 0.5):,}"


def ga(k):
    """Returns a Grit area's acres and its granite (QA #43).

    For every area, put in or left out: "12 acres (3 granite)", or "(no
    granite)".
    """
    g = gs(k, "granite_acres")
    return f"{gs(k)} acres ({'no' if g == '0' else g} granite)"


GRIT_ABOUT = (
    ABOUT
    + "<p>What the proposed text swaps near Grit, all drawn on the printed "
    "linework of the USGS maps (none taken from the AVA Map Explorer "
    "polygon). Lines: Notice No. 243's steps (10)-(11) and (90)-(92), as "
    "drawn by the petitioner, which the proposed text replaces; the "
    "petition's wording put back in their place, steps (10)-(11), (90)-(92) "
    "and (97)-(100); the new steps (93)-(96) around the granite lobe; and "
    "the petition's straight line from the marked 1,737 to the marked 1,762, "
    "which they replace.</p><p>Areas, with the granite (Town Mountain "
    "Granite and younger granitic intrusions, USGS SGMC shifted to the "
    "outcrops) in each: in Notice No. 243's text and left out by the "
    f"petition, {ga('Notice No. 243, not the petition')}; added by the "
    f"petition's lane wording along steps (10)-(11), {ga('lane wording')}; in "
    "the petition and not Notice No. 243's text along steps (99)-(100), "
    f"{ga('petition, not Notice No. 243')}; the granite lobe now also left "
    f"out by (93)-(96), {ga('granite lobe')}; put back between the marked "
    f"1,737 and the windmill, {ga('put back')}.</p>"
)
rprops = {
    "snippet": "The change near Grit: the lines the proposed text swaps, and "
    "the acres (and granite) it leaves out and puts in.",
    "description": GRIT_ABOUT,
    "tags": ",".join([*TAGS, "granite", "Grit"]),
    "licenseInfo": CC0,
    "accessInformation": CREDIT
    + "; granite: USGS State Geologic Map Compilation (SGMC), shifted to the "
    "outcrops",
}
GRIT_SERVICE = "Hickory_Sands_District_change_near_Grit_2026_10_15"  # a URL
GRIT_NAMES = (
    "Lines the change near Grit swaps",
    "Areas the change near Grit moves, with their granite",
)


def grit_layers(layers):
    """Returns the hosted layer 4o's two layers: (the lines, the areas)."""
    glayers = {x.properties.geometryType: x for x in layers}
    return glayers["esriGeometryPolyline"], glayers["esriGeometryPolygon"]


ORANGE, GREY, BLUE = [230, 110, 0, 255], [110, 110, 110, 255], [0, 90, 255, 255]
GREEN, MAGENTA, BROWN = (
    [0, 140, 60, 255],
    [190, 0, 130, 255],
    [150, 90, 40, 255],
)


def ring(color, style):
    """Returns a ring: no fill, an outline 3 wide of a color and style."""
    return {
        "type": "esriSFS",
        "style": "esriSFSNull",
        "outline": {
            "type": "esriSLS",
            "style": style,
            "color": color,
            "width": 3,
        },
    }


big_def = {
    "drawingInfo": {
        "renderer": {
            "type": "uniqueValue",
            "field1": "why",
            "valueExpressionTitle": "Why the lines differ",
            "uniqueValueInfos": [
                {
                    "value": OTHER_PATH,
                    "label": "The two lines take different paths",
                    "symbol": ring(ORANGE, "esriSLSSolid"),
                },
                {
                    "value": TEXT_CHANGE,
                    "label": "The proposed text change near Grit",
                    "symbol": ring(GREY, "esriSLSDash"),
                },
            ],
        },
        "labelingInfo": [
            {
                "labelExpressionInfo": {
                    "expression": "'#' + $feature.n + IIf(Find(',', "
                    "$feature.steps) > -1, ' steps ', ' step ') + "
                    "$feature.steps + ': ' + Round($feature.max_apart_m) + ' "
                    "m'"
                },
                "labelPlacement": "esriServerPolygonPlacementAlwaysHorizontal",
                "symbol": {
                    "type": "esriTS",
                    "color": [170, 70, 0, 255],
                    "haloColor": [255, 255, 255, 255],
                    "haloSize": 1.5,
                    "font": {"family": "Arial", "size": 10, "weight": "bold"},
                },
            }
        ],
    },
    "showLabels": True,
}


def fill(rgba):
    """Returns a fill symbol of an RGBA colour, with no outline."""
    return {
        "type": "esriSFS",
        "style": "esriSFSSolid",
        "color": rgba,
        "outline": {
            "type": "esriSLS",
            "style": "esriSLSNull",
            "color": [0, 0, 0, 0],
            "width": 0,
        },
    }


all_def = {
    "drawingInfo": {
        "renderer": {
            "type": "uniqueValue",
            "valueExpressionTitle": "Land between the two boundaries",
            "valueExpression": f"IIf($feature.cause == '{TEXT_CHANGE}', "
            "'text', IIf($feature.side == 'in the proposed revision only', "
            "'rev', 'mapx'))",
            "uniqueValueInfos": [
                {
                    "value": "rev",
                    "label": f"In the proposed revision only ({SAME_TEXT})",
                    "symbol": fill([220, 0, 0, 120]),
                },
                {
                    "value": "mapx",
                    "label": f"In the Map Explorer polygon only ({SAME_TEXT})",
                    "symbol": fill([0, 90, 255, 120]),
                },
                {
                    "value": "text",
                    "label": "Between the two near Grit (the proposed text "
                    "change)",
                    "symbol": fill([120, 120, 120, 70]),
                },
            ],
        }
    }
}
ttb_def = {
    "definitionExpression": TTB_WHERE,
    "drawingInfo": {
        "renderer": {
            "type": "simple",
            "symbol": {
                "type": "esriSFS",
                "style": "esriSFSNull",
                "outline": {
                    "type": "esriSLS",
                    "style": "esriSLSSolid",
                    "color": BLUE,
                    "width": 2.2,
                },
            },
        }
    },
}
DIFF_NOTE = (
    "Red: the proposed revision. Blue: the AVA Map Explorer polygon "
    f"(AVAs_Production, Notice No. 243). Ringed where they are {BIG_M:.0f} m "
    "or more apart; elsewhere they differ as a hand-digitized line and a "
    f"traced one do (median {MED:.0f} m, measured every 2 m along each line)."
)
BIG_F = [
    ("why", "Why"),
    ("steps", "Steps"),
    ("kind", "Kind of step"),
    ("max_apart_m", "Farthest apart (m)"),
    ("length_m", "Length of the stretch (m)"),
    ("revision_only_acres", "In the proposed revision only (acres)"),
    ("map_explorer_only_acres", "In the Map Explorer polygon only (acres)"),
    (
        "endpoints",
        "Step endpoints vs the Map Explorer polygon's nearest vertex",
    ),
]
ALL_F = [
    ("cause", "Cause"),
    ("side", "Side"),
    ("acres", "Acres"),
    ("length_m", "Length (m)"),
    ("mean_width_m", "Average width (m)"),
    ("widest_m", "Farthest apart (m)"),
    ("steps", "Proposed revision steps along it"),
]
ttb_pop = {
    "title": "AVA Map Explorer polygon: {Name}",
    "fieldInfos": [
        {"fieldName": f, "label": f, "visible": True}
        for f in ("Name", "Status", "Counties", "Within")
    ],
    "popupElements": [
        {
            "type": "text",
            "text": "TTB's AVAs_Production layer (live), shown on TTB's AVA "
            "Map Explorer for Notice No. 243.",
        },
        {"type": "fields"},
    ],
}


def sls(rgba, width, style="esriSLSSolid"):
    """Returns a line symbol (esriSLS) of a colour, width and style."""
    return {"type": "esriSLS", "style": style, "color": rgba, "width": width}


grit_lines_def = {
    "drawingInfo": {
        "renderer": {
            "type": "uniqueValue",
            "field1": "role",
            "uniqueValueInfos": [
                {
                    "value": "replaced: a Notice No. 243 step",
                    "label": "Replaced: Notice No. 243 steps (10)-(11), "
                    "(90)-(92), as drawn by the petitioner",
                    "symbol": sls(BLUE, 3, "esriSLSDash"),
                },
                {
                    "value": "put back: the petition's wording",
                    "label": "Put back: the petition's wording, (10)-(11), "
                    "(90)-(92), (97)-(100)",
                    "symbol": sls(GREEN, 3.5),
                },
                {
                    "value": "new: around the granite lobe",
                    "label": "New: (93)-(96), around the granite lobe",
                    "symbol": sls(MAGENTA, 3.5),
                },
                {
                    "value": "replaced: the petition's straight line",
                    "label": "Replaced: the petition's straight line from "
                    "the marked 1,737 to the marked 1,762",
                    "symbol": sls(GREEN, 2.5, "esriSLSDash"),
                },
            ],
        },
        "labelingInfo": [
            {
                "labelExpressionInfo": {"expression": "$feature.label"},
                "labelPlacement": "esriServerLinePlacementCenterAlong",
                "minScale": 60000,
                "symbol": {
                    "type": "esriTS",
                    "color": [40, 40, 40, 255],
                    "haloColor": [255, 255, 255, 255],
                    "haloSize": 1.5,
                    "font": {"family": "Arial", "size": 9, "weight": "bold"},
                },
            }
        ],
    },
    "showLabels": True,
}


def hatch(rgba, style):
    """Returns a fill symbol of a colour and style, outlined in that colour."""
    return {
        "type": "esriSFS",
        "style": style,
        "color": rgba,
        "outline": sls(rgba, 1.2),
    }


grit_areas_def = {
    "drawingInfo": {
        "renderer": {
            "type": "uniqueValue",
            "field1": "what",
            "uniqueValueInfos": [
                {
                    "value": "Notice No. 243, not the petition",
                    "label": "In Notice No. 243's text, left out by the "
                    "petition",
                    "symbol": hatch(BROWN, "esriSFSBackwardDiagonal"),
                },
                {
                    "value": "granite lobe",
                    "label": "Granite lobe, also left out now by (93)-(96)",
                    "symbol": hatch(MAGENTA, "esriSFSForwardDiagonal"),
                },
                {
                    "value": "lane wording",
                    "label": "Added by the petition's lane wording, (10)-(11)",
                    "symbol": fill([0, 140, 60, 90]),
                },
                {
                    "value": "petition, not Notice No. 243",
                    "label": "In the petition, not Notice No. 243's text, "
                    "(99)-(100)",
                    "symbol": fill([0, 140, 60, 90]),
                },
                {
                    "value": "put back",
                    "label": "Put back, between the marked 1,737 and the "
                    "windmill",
                    "symbol": fill([0, 140, 60, 90]),
                },
            ],
        },
        "labelingInfo": [
            {
                "labelExpressionInfo": {
                    "expression": "Text($feature.acres, '#,###') + ' ac, ' + "
                    "Text($feature.granite_acres, '#,###') + ' ac granite'"
                },
                "labelPlacement": "esriServerPolygonPlacementAlwaysHorizontal",
                "symbol": {
                    "type": "esriTS",
                    "color": [60, 40, 20, 255],
                    "haloColor": [255, 255, 255, 255],
                    "haloSize": 1.5,
                    "font": {"family": "Arial", "size": 10, "weight": "bold"},
                },
            }
        ],
    },
    "showLabels": True,
}
GRIT_LINES_F = [
    ("role", "What it is"),
    ("steps", "Steps"),
    ("length_m", "Length (m)"),
    ("source", "Drawn from"),
]
GRIT_AREAS_F = [
    ("acres", "Acres"),
    ("granite_acres", "Granite (acres)"),
    ("sandstone_acres", "Hickory Sandstone Member formation (acres)"),
    ("revision_steps", "Proposed revision (or petition) steps along it"),
    ("notice_steps", "Notice No. 243 steps along it"),
]
mprops = {
    "snippet": "The proposed boundary over the 13 USGS 1:24,000 quadrangles "
    "cited in paragraph (b). Click the AVA for the documents, a step for its "
    "text.",
    "description": ABOUT
    + "<p>The quadrangle layer is Esri's USA Historical Topo Maps service, "
    "locked to the 13 editions the proposed regulation cites. Over them: the "
    "USGS geologic units shifted to the outcrops (layer 4m), the AVA Map "
    "Explorer polygon from TTB's live AVAs_Production layer (blue), the "
    "proposed revision (red, layer 4b, with its numbered step endpoints), "
    "every piece of land between the two lines shaded (red: in the proposed "
    "revision only; blue: in the Map Explorer polygon only; grey: the "
    f"proposed text change near Grit), and the {NBIG} big differences, where "
    "the lines are "
    f'{BIG_M:.0f} m or more apart, ringed (layer 4k). The group "The change '
    'near Grit" shows the lines the proposed text swaps and the areas (with '
    "their granite) it leaves out and puts in (layer 4o). The group \"TTB's "
    'AVA Map Explorer basemaps" holds '
    "the four basemaps of TTB's AVA Map Explorer (Topographic, Streets, "
    "Imagery, USA Topo Maps); turn it on and pick one to see the lines over "
    "what the Map Explorer shows.</p>",
    "tags": ",".join(TAGS),
    "licenseInfo": LIC_MAP,
    "accessInformation": CREDIT_MAP,
    "culture": CULTURE,
}


# ---- what is sent once the layers exist: built, not sent
# Each takes the layers (live in main(); the publish dry run, agol_dryrun.py,
# passes stand-ins from tests/fixtures/publish/agol-items.json) and returns
# their pop-ups, their changed field aliases ([(layer, fields)], for
# set_aliases()) and the layer item's data (its visualization: symbols, labels,
# pop-ups), without sending anything.
def boundary_plan(area, line, pts):
    """Plans the hosted layer 4b: the AVA polygon, the steps and the endpoints.

    Args:
        area: The AVA polygon's layer.
        line: The steps' layer.
        pts: The endpoints' layer.

    Returns:
        {"pops": (the three pop-ups), "aliases": [(layer, fields)], "data":
        the layer item's data}.
    """
    area_pop = popup(
        "Hickory Sands District AVA (proposed)",
        area,
        AREA_F,
        True,
        NOTE
        + " The documents are attached below: read-me, boundary description, "
        "TTB's notice with the proposed changes highlighted, and the "
        "side-by-side.",
    )
    line_pop = popup("Step ({step})", line, LINE_F, text=NOTE)
    pts_pop = popup("{point_name}", pts, PTS_F)
    return {
        "pops": (area_pop, line_pop, pts_pop),
        "aliases": [
            (lyr, alias_fields(lyr, wanted, ttb=True))
            for lyr, wanted in ((area, AREA_F), (line, LINE_F), (pts, PTS_F))
        ],
        "data": {
            "layers": [
                {
                    "id": area.properties.id,
                    "layerDefinition": area_def,
                    "popupInfo": area_pop,
                },
                {
                    "id": line.properties.id,
                    "layerDefinition": line_def,
                    "popupInfo": line_pop,
                },
                {
                    "id": pts.properties.id,
                    "layerDefinition": pts_def,
                    "popupInfo": pts_pop,
                },
            ]
        },
    }


def geo_plan(geo):
    """Plans the hosted layer 4m: the three geology layers.

    Args:
        geo: [(layer, name, rgb)], as geo_layers() gives them.

    Returns:
        {"layers": [(layer, name, its definition, its pop-up)], "aliases":
        [(layer, fields)], "data": the layer item's data}.
    """
    geo = [
        (lyr, nm, geo_def(rgb), popup(nm.split(" (")[0], lyr, GEO_F))
        for lyr, nm, rgb in geo
    ]
    return {
        "layers": geo,
        "aliases": [(lyr, alias_fields(lyr, GEO_F)) for lyr, *_ in geo],
        "data": {
            "layers": [
                {
                    "id": lyr.properties.id,
                    "layerDefinition": gdef,
                    "popupInfo": gpop,
                }
                for lyr, _, gdef, gpop in geo
            ]
        },
    }


def diff_plan(bigl, every_l):
    """Plans the hosted layer 4k: the big differences and all of them.

    Args:
        bigl: The big differences' layer.
        every_l: The layer of all the differences.

    Returns:
        {"pops": (the two pop-ups), "aliases": [(layer, fields)], "data": the
        layer item's data}.
    """
    big_pop = popup(
        "Big difference #{n}: step(s) {steps}", bigl, BIG_F, text=DIFF_NOTE
    )
    all_pop = popup(
        "{acres} acres {side}",
        every_l,
        ALL_F,
        text="One piece of land in one line and not the other. Red: in the "
        "proposed revision only; blue: in the AVA Map Explorer polygon only; "
        "grey: the proposed text change near Grit.",
    )
    return {
        "pops": (big_pop, all_pop),
        "aliases": [
            (
                bigl,
                alias_fields(bigl, [*BIG_F, ("n", "Big difference number")]),
            ),
            (every_l, alias_fields(every_l, ALL_F)),
        ],
        "data": {
            "layers": [
                {
                    "id": bigl.properties.id,
                    "layerDefinition": big_def,
                    "popupInfo": big_pop,
                },
                {
                    "id": every_l.properties.id,
                    "layerDefinition": all_def,
                    "popupInfo": all_pop,
                },
            ]
        },
    }


def grit_plan(grit_lines, grit_areas):
    """Plans the hosted layer 4o: what the change near Grit swaps and moves.

    Args:
        grit_lines: The layer of the lines the change swaps.
        grit_areas: The layer of the areas it moves.

    Returns:
        {"pops": (the two pop-ups), "aliases": [(layer, fields)], "data": the
        layer item's data}.
    """
    grit_lines_pop = popup("{label}", grit_lines, GRIT_LINES_F)
    grit_areas_pop = popup(
        "{acres} acres: {why}",
        grit_areas,
        GRIT_AREAS_F,
        text="Granite: Town Mountain Granite and younger granitic "
        "intrusions, USGS SGMC shifted about 400 m to the outcrops.",
    )
    return {
        "pops": (grit_lines_pop, grit_areas_pop),
        "aliases": [
            (grit_lines, alias_fields(grit_lines, GRIT_LINES_F)),
            (
                grit_areas,
                alias_fields(
                    grit_areas, [*GRIT_AREAS_F, ("side", "Left out or put in")]
                ),
            ),
        ],
        "data": {
            "layers": [
                {
                    "id": grit_lines.properties.id,
                    "layerDefinition": grit_lines_def,
                    "popupInfo": grit_lines_pop,
                },
                {
                    "id": grit_areas.properties.id,
                    "layerDefinition": grit_areas_def,
                    "popupInfo": grit_areas_pop,
                },
            ]
        },
    }


def webmap_plan(
    fl,
    area,
    line,
    pts,
    boundary,
    dl,
    bigl,
    every_l,
    diffs,
    gl,
    geology,
    grl,
    grit_lines,
    grit_areas,
    grit,
):
    """Plans the web map 4a, over the layers and the plans above.

    Args:
        fl: The hosted layer item 4b.
        area: Its AVA polygon's layer.
        line: Its steps' layer.
        pts: Its endpoints' layer.
        boundary: boundary_plan()'s plan.
        dl: The hosted layer item 4k.
        bigl: Its big differences' layer.
        every_l: Its layer of all the differences.
        diffs: diff_plan()'s plan.
        gl: The hosted layer item 4m.
        geology: geo_plan()'s plan.
        grl: The hosted layer item 4o.
        grit_lines: Its lines' layer.
        grit_areas: Its areas' layer.
        grit: grit_plan()'s plan.

    Returns:
        The web map's JSON: the quadrangles, TTB's basemaps, the geology, the
        differences, the AVA Map Explorer polygon, the proposed revision, the
        change near Grit and the big differences, over Light Gray Canvas.
    """
    area_pop, line_pop, pts_pop = boundary["pops"]
    big_pop, all_pop = diffs["pops"]
    geo = geology["layers"]
    grit_lines_pop, grit_areas_pop = grit["pops"]

    def op(lyr, title, ldef, pop, visible=True, item=None, lid=None):
        item = item or fl
        return {
            "id": lid or f"hsd-{lyr.properties.id}",
            "title": title,
            "url": lyr.url,
            "itemId": item.id,
            "layerType": "ArcGISFeatureLayer",
            "visibility": visible,
            "opacity": 1,
            "layerDefinition": ldef,
            "popupInfo": pop,
            **({"showLabels": True} if "labelingInfo" in ldef else {}),
        }

    return {
        "operationalLayers": [
            QUADS,
            {
                "id": "ttb-basemaps",
                "title": "TTB's AVA Map Explorer basemaps (turn on, pick one)",
                "layerType": "GroupLayer",
                "visibility": False,
                "visibilityMode": "exclusive",
                "opacity": 1,
                "layers": [
                    {
                        "id": f"ttb-basemap-{i}",
                        "title": title,
                        "layerType": "GroupLayer",
                        "visibility": i == 0,
                        "opacity": 1,
                        "layers": [
                            {
                                "id": f"ttb-basemap-{i}-{j}",
                                "title": t,
                                "layerType": kind,
                                "visibility": True,
                                "opacity": 1,
                                **(
                                    {"styleUrl": url}
                                    if kind == "VectorTileLayer"
                                    else {"url": url}
                                ),
                            }
                            for j, (t, kind, url) in enumerate(parts)
                        ],
                    }
                    for i, (title, parts) in enumerate(TTB_BASEMAPS)
                ],
            },
            *[
                op(
                    lyr,
                    nm,
                    gdef,
                    gpop,
                    item=gl,
                    lid=f"hsd-geology-{lyr.properties.id}",
                )
                for lyr, nm, gdef, gpop in geo
            ],
            op(
                every_l,
                DNAMES["all"],
                all_def,
                all_pop,
                item=dl,
                lid="hsd-all-differences",
            ),
            {
                "id": "hsd-ttb",
                "title": "AVA Map Explorer polygon (TTB AVAs_Production, "
                "Notice No. 243, live)",
                "url": TTB_URL,
                "layerType": "ArcGISFeatureLayer",
                "visibility": True,
                "opacity": 1,
                "layerDefinition": ttb_def,
                "popupInfo": ttb_pop,
            },
            op(area, NAMES["esriGeometryPolygon"], area_def, area_pop),
            op(line, NAMES["esriGeometryPolyline"], line_def, line_pop),
            op(pts, NAMES["esriGeometryPoint"], pts_def, pts_pop),
            {
                "id": "hsd-grit",
                "title": "The change near Grit: what the proposed text swaps",
                "layerType": "GroupLayer",
                "visibility": True,
                "opacity": 1,
                "layers": [
                    op(
                        grit_areas,
                        "Areas the change moves, with their granite",
                        grit_areas_def,
                        grit_areas_pop,
                        item=grl,
                        lid="hsd-grit-areas",
                    ),
                    op(
                        grit_lines,
                        "Lines the change swaps",
                        grit_lines_def,
                        grit_lines_pop,
                        item=grl,
                        lid="hsd-grit-lines",
                    ),
                ],
            },
            op(bigl, DNAMES["big"], big_def, big_pop, item=dl, lid="hsd-rings"),
        ],
        "baseMap": {
            "title": "Light Gray Canvas",
            "baseMapLayers": [
                {
                    "id": "gray",
                    "title": "World Light Gray Base",
                    "layerType": "ArcGISTiledMapServiceLayer",
                    "url": "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer",
                    "visibility": True,
                    "opacity": 1,
                }
            ],
        },
        "spatialReference": {"wkid": 102100, "latestWkid": 3857},
        "authoringApp": "ArcGIS API for Python",
        "authoringAppVersion": "2.4.3",
        "version": "2.31",
    }


def plan(
    fl, area, line, pts, dl, bigl, every_l, gl, geo, grl, grit_lines, grit_areas
):
    """Plans all of the above at once, for the publish dry run.

    main() calls each plan where it sends it.

    Args:
        fl: The hosted layer item 4b.
        area: Its AVA polygon's layer.
        line: Its steps' layer.
        pts: Its endpoints' layer.
        dl: The hosted layer item 4k.
        bigl: Its big differences' layer.
        every_l: Its layer of all the differences.
        gl: The hosted layer item 4m.
        geo: Its layers, as geo_layers() gives them.
        grl: The hosted layer item 4o.
        grit_lines: Its lines' layer.
        grit_areas: Its areas' layer.

    Returns:
        {"aliases": {item title: [(layer, fields)]}, "data": {item title: its
        data}, "webmap": the web map}.
    """
    boundary, diffs, geology, grit = (
        boundary_plan(area, line, pts),
        diff_plan(bigl, every_l),
        geo_plan(geo),
        grit_plan(grit_lines, grit_areas),
    )
    return {
        "aliases": {
            LAYER_TITLE: boundary["aliases"],
            DIFF_TITLE: diffs["aliases"],
            GEO_TITLE: geology["aliases"],
            GRIT_TITLE: grit["aliases"],
        },
        "data": {
            LAYER_TITLE: boundary["data"],
            DIFF_TITLE: diffs["data"],
            GEO_TITLE: geology["data"],
            GRIT_TITLE: grit["data"],
        },
        "webmap": webmap_plan(
            fl,
            area,
            line,
            pts,
            boundary,
            dl,
            bigl,
            every_l,
            diffs,
            gl,
            geology,
            grl,
            grit_lines,
            grit_areas,
            grit,
        ),
    }


# ---- sign in and send
def main():
    """Signs in, publishes the hosted layers and sends the plans and the map.

    The hosted layer 4b is published from 4c once, then reused: its layers are
    renamed, its features updated to the build's (issue #71) when the build's
    files changed, the documents attached to the AVA polygon, and its field
    aliases and visualization sent. The GeoPackages 4j, 4l and 4n and their
    hosted layers 4k, 4m and 4o follow, with their layers' names, field
    aliases and visualizations, then the web map 4a. Each item is shared to
    the group and put in its category; none may say "agree".
    """
    global gis, folder, typed  # hosted() uses them
    gis = GIS(profile="hsd")
    folder = gis.content.folders.get(FOLDER)
    group = gis.groups.get(GROUP_ID)
    listing = list(folder.list())
    items = {it.title: it for it in listing}
    typed = {
        (it.title, it.type): it for it in listing
    }  # a title alone can be shared (a stuck overwrite retitles the layer)
    gp = next(it for t, it in items.items() if t.startswith("4c "))

    # ---- hosted feature layer
    fl = items.get(LAYER_TITLE)
    if fl is None:
        pp = gis.content.analyze(item=gp, file_type="geoPackage")[
            "publishParameters"
        ]
        # A URL: a fixed identifier (see DIFF_SERVICE).
        pp["name"] = "Hickory_Sands_District_proposed_boundary_2026_10_15"
        pp["maxRecordCount"] = 2000
        fl = gp.publish(publish_parameters=pp, file_type="geoPackage")
        if fl.ownerFolder != folder.properties.get("id"):
            fl.move(folder)
        print("published", fl.id, fl.url)
    fl.update(item_properties={"title": LAYER_TITLE, **props})
    flc = FeatureLayerCollection.fromitem(lock(fl))

    layers = boundary_layers(flc.layers)
    area, line, pts = (
        layers["esriGeometryPolygon"],
        layers["esriGeometryPolyline"],
        layers["esriGeometryPoint"],
    )
    for gtype, lyr in layers.items():
        if lyr.properties.name != NAMES[gtype]:
            try:
                lyr.manager.update_definition({"name": NAMES[gtype]})
            # The ArcGIS API raises bare Exception: a failure is reported,
            # and the publish goes on.
            except Exception as e:  # noqa: BLE001
                print(
                    "could not rename",
                    lyr.properties.name,
                    "->",
                    NAMES[gtype],
                    type(e).__name__,
                )

    # the layer's features, as built (issue #71; BUILT, KEY, esri() above)
    built_files = []
    for g in sorted(BUILT):
        with open(BUILT[g], "rb") as f:
            built_files.append(f.read())
    built_sha = hashlib.sha256(b"".join(built_files)).hexdigest()
    if (fl.properties or {}).get("features_sha256") != built_sha:
        edits = {}
        for gtype, lyr in layers.items():
            oidf, key = lyr.properties.objectIdField, KEY[gtype]
            geo = lyr.properties.get("geometryProperties") or {}
            system = {
                oidf,
                lyr.properties.get("globalIdField"),
                geo.get("shapeAreaFieldName"),
                geo.get("shapeLengthFieldName"),
            }
            names = {f["name"] for f in lyr.properties.fields} - system
            live = lyr.query(
                where="1=1",
                out_fields=",".join(f for f in (oidf, key) if f),
                return_geometry=False,
            ).features
            with open(BUILT[gtype]) as f:
                new = json.load(f)["features"]
            live_by = {
                str(f.attributes[key]) if key else "": f.attributes[oidf]
                for f in live
            }
            new_by = {str(f["properties"][key]) if key else "": f for f in new}
            assert set(live_by) == set(new_by) and len(live) == len(new), (
                gtype,
                sorted(set(live_by) ^ set(new_by)),
            )  # same features
            edits[gtype] = [
                {
                    "attributes": {
                        oidf: live_by[k],
                        **{
                            a: v
                            for a, v in f["properties"].items()
                            if a in names
                        },
                    },
                    "geometry": esri(f["geometry"]),
                }
                for k, f in new_by.items()
            ]
        flc.manager.update_definition({"capabilities": "Query,Extract,Update"})
        try:
            for gtype, ups in edits.items():
                for i in range(0, len(ups), 50):
                    res = layers[gtype].edit_features(updates=ups[i : i + 50])[
                        "updateResults"
                    ]
                    failed = [r for r in res if not r.get("success")]
                    assert not failed, (gtype, failed[:3])
                print(
                    f"updated {len(ups)} features of "
                    f"{layers[gtype].properties.name}"
                )
            fl.update(
                item_properties={
                    "properties": {
                        **(fl.properties or {}),
                        "features_sha256": built_sha,
                    }
                }
            )
        finally:
            lock(fl)
    else:
        print("the layer's features are as built")

    # documents attached to the AVA polygon
    if not area.properties.get("hasAttachments"):
        area.manager.add_to_definition({"hasAttachments": True})
        area = FeatureLayerCollection.fromitem(fl).layers[
            [
                lyr.properties.geometryType
                for lyr in FeatureLayerCollection.fromitem(fl).layers
            ].index("esriGeometryPolygon")
        ]
    oid = area.query(where="1=1", return_ids_only=True)["objectIds"][0]
    have = {a["name"]: a for a in area.attachments.get_list(oid)}
    for p in ATTACH:
        assert os.path.exists(p), p
        old = have.get(os.path.basename(p))
        if old and old.get("size") != os.path.getsize(
            p
        ):  # the file changed: replace the attachment
            area.attachments.delete(oid, old["id"])
            old = None
        if not old:
            area.attachments.add(oid, p)
    print(
        "attachments on the AVA polygon:",
        sorted(a["name"] for a in area.attachments.get_list(oid)),
    )

    boundary = boundary_plan(area, line, pts)
    for lyr, out in boundary["aliases"]:
        set_aliases(lyr, out)
    fl.update(data=json.dumps(boundary["data"]))

    # ---- the GeoPackages and the hosted layers made from them
    make_diff_gpkg()
    dsrc, dl = hosted(
        DIFF_GPKG, DIFF_SRC_TITLE, DIFF_TITLE, DIFF_SERVICE, dprops, DIFF_WAS
    )
    bigl, every_l = diff_layers(FeatureLayerCollection.fromitem(dl).layers)
    for lyr, nm in ((bigl, DNAMES["big"]), (every_l, DNAMES["all"])):
        rename(lyr, nm)
    gsrc, gl = hosted(GEO_GPKG, GEO_SRC_TITLE, GEO_TITLE, GEO_SERVICE, gprops)
    geo = geo_layers(FeatureLayerCollection.fromitem(gl).layers)
    geology = geo_plan(geo)
    for (lyr, nm, _), (_, out) in zip(geo, geology["aliases"], strict=True):
        rename(lyr, nm)
        set_aliases(lyr, out)
    make_grit_gpkg()
    grsrc, grl = hosted(
        GRIT_GPKG, GRIT_SRC_TITLE, GRIT_TITLE, GRIT_SERVICE, rprops
    )
    grit_lines, grit_areas = grit_layers(
        FeatureLayerCollection.fromitem(grl).layers
    )
    rename(grit_lines, GRIT_NAMES[0])
    rename(grit_areas, GRIT_NAMES[1])

    # ---- symbology, pop-ups, field aliases and the web map
    diffs = diff_plan(bigl, every_l)
    for lyr, out in diffs["aliases"]:
        set_aliases(lyr, out)
    dl.update(data=json.dumps(diffs["data"]))
    gl.update(data=json.dumps(geology["data"]))
    grit = grit_plan(grit_lines, grit_areas)
    for lyr, out in grit["aliases"]:
        set_aliases(lyr, out)
    grl.update(data=json.dumps(grit["data"]))
    webmap = webmap_plan(
        fl,
        area,
        line,
        pts,
        boundary,
        dl,
        bigl,
        every_l,
        diffs,
        gl,
        geology,
        grl,
        grit_lines,
        grit_areas,
        grit,
    )
    wm = items.get(MAP_TITLE)
    if wm is None:
        wm = folder.add(
            ItemProperties(
                title=MAP_TITLE,
                item_type=ItemTypeEnum.WEB_MAP,
                tags=TAGS,
                snippet=mprops["snippet"],
                description=mprops["description"],
                license_info=LIC_MAP,
                access_information=CREDIT_MAP,
                culture=CULTURE,
                extent=EXTENT,
            ),
            text=json.dumps(webmap),
        ).result()
    else:
        wm.update(
            item_properties={**mprops, "extent": EXTENT},
            data=json.dumps(webmap),
        )
    print("web map", wm.id)

    # ---- share to the group, category 4 > Map and layer (sources: Downloads)
    for it, cat in (
        (wm, CAT),
        (fl, CAT),
        (dl, CAT),
        (gl, CAT),
        (grl, CAT),
        (dsrc, C4D),
        (gsrc, C4D),
        (grsrc, C4D),
    ):
        for t in (
            it.title,
            it.snippet,
            it.description,
            it.licenseInfo or "",
            it.accessInformation or "",
        ):
            assert "agree" not in t.lower(), it.title
        try:
            it.sharing.groups.add(group)
        except AttributeError:
            it.share(groups=[GROUP_ID])
        r = gis._con.post(
            f"{gis._portal.resturl}content/groups/{GROUP_ID}/updateCategories",
            {"f": "json", "items": json.dumps([{it.id: [cat]}])},
        )
        assert all(x.get("success") for x in r.get("results", [{}])), r
        print("shared + categorized:", it.id, it.type, it.title)


if __name__ == "__main__":
    main()
