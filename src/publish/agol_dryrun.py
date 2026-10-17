"""The publish dry run (issue #58): what ./build.sh publish would send, checked.

Everything ./build.sh publish would send to ArcGIS Online is built from the
build's outputs WITHOUT signing in, written to target/publish/ as JSON and
checked (agol_dryrun_checks.py); exit 1 if a check fails. ./build.sh publish
runs it first and stops before uploading anything if a check fails;
./build.sh publish-dry-run runs only this.

It calls the publish scripts' own builders (agol_publish.ITEMS and
properties(), agol_layer's item properties and plan(), agol_dashboard.build(),
agol_share.description(), agol_org_categories.categories()), never their
main(): arcgis.gis.GIS is replaced before they are imported by a function that
raises, and nothing here touches the network.

What only ArcGIS knows (item ids, service URLs, the hosted layers' fields)
comes from stand-ins: the group's item list in
tests/fixtures/publish/agol-items.json, with fake ids and the public layers'
definitions, fetched anonymously from the public site by --fetch (read-only).
The dashboard's step records come from the build's line GeoJSON, which 4b is
published from. agol_layer's two GeoPackages are made in the output folder,
not in the build's review folder.

Written: items.json (each item: title, type, stand-in id, file, group and
organization categories, the properties update() sends; the dashboard's type
keywords), item-list.json, services.json (each hosted layer: its definition
update, layer names, changed field aliases, visualization), webmap.json,
dashboard.json, group.json, facts.json.

Run:
    .venv/bin/python src/publish/agol_dryrun.py [out dir, default
        target/publish] [--items FILE]
    .venv/bin/python src/publish/agol_dryrun.py --fetch FILE [--real-ids]
        (the item list, anonymously; --real-ids keeps the live ids, to
        compare a dry run with the live site)
"""

import argparse
import glob
import json
import os
import sys
import urllib.parse
import urllib.request

import agol_dryrun_checks  # src/publish/, next to this script

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)  # the repository root
HERE = os.environ.get("HSD_WORK") or os.path.join(
    ROOT, "target", "work"
)  # the build's work dir
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "publish", "agol-items.json")
GROUP_ID = "65720ee9c5a743f88659ae39228704ec"
PORTAL = "https://robertclayvines.maps.arcgis.com"
REST = "https://www.arcgis.com/sharing/rest/"
LAYER_KEYS = (
    "id",
    "name",
    "type",
    "geometryType",
    "objectIdField",
    "globalIdField",
    "geometryProperties",
    "hasAttachments",
    "fields",
)


# ---- stand-ins for ArcGIS's items and layers
class Props(dict):
    """A stand-in for ArcGIS's PropertyMap: a dict whose keys are attributes."""

    def __getattr__(self, k):
        """Returns the value of key k.

        Raises:
            AttributeError: There is no key k.
        """
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k) from None


class Layer:
    """A hosted feature layer: .properties (from the item list) and .url."""

    def __init__(self, d, service_url):
        """Makes the stand-in.

        Args:
            d: The layer's definition from the item list (id, name, fields...).
            service_url: Its feature service's URL.
        """
        self.properties, self.url = Props(d), f"{service_url}/{d['id']}"


class Item:
    """An item: .id, .title, .type, .url, and for a hosted layer .layers."""

    def __init__(self, d):
        """Makes the stand-in.

        Args:
            d: The item from the item list: id, title, type, and for a hosted
                feature layer its url and layers.
        """
        self.id, self.title, self.type, self.url = (
            d["id"],
            d["title"],
            d["type"],
            d.get("url"),
        )
        self.layers = [Layer(x, self.url) for x in d.get("layers", [])]


def no_sign_in(*a, **k):
    """Stands in for arcgis.gis.GIS during the dry run.

    Args:
        *a: Whatever GIS() was given.
        **k: Whatever GIS() was given.

    Raises:
        RuntimeError: Always: the dry run must not sign in.
    """
    raise RuntimeError("the publish dry run must not sign in to ArcGIS Online")


# ---- the dry run
def dry_run(out, items_file=FIXTURE):
    """Builds everything the publish would send, writes it as JSON, returns it.

    Args:
        out: The folder to write the JSON files (and the two GeoPackages) in.
        items_file: The group's item list to use as stand-ins.

    Returns:
        The bundle: {name: JSON} for items, item-list, services, webmap,
        dashboard, group and facts, as written to out/<name>.json.
    """
    # These imports stay here, in this order: GIS is replaced before the
    # publish scripts import it, and their folder is put on sys.path first.
    import arcgis.gis  # noqa: PLC0415, RUF100

    # Before the scripts import it: a GIS() anywhere in them now fails the dry
    # run.
    arcgis.gis.GIS = no_sign_in
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    # Their module level needs no sign-in.
    import agol_dashboard  # noqa: PLC0415, RUF100
    import agol_layer  # noqa: PLC0415, RUF100
    import agol_org_categories  # noqa: PLC0415, RUF100
    import agol_publish  # noqa: PLC0415, RUF100
    import agol_share  # noqa: PLC0415, RUF100

    with open(items_file, encoding="utf-8") as f:
        listed = json.load(f)
    stand = {d["title"]: Item(d) for d in listed["items"]}
    os.makedirs(out, exist_ok=True)

    def rel(p):
        return os.path.relpath(p, HERE)

    made = []  # (title, type, script, file, group category, properties, extra)
    # agol_publish.py: the files of the package
    for r, title, typ, cat, snippet, desc, lic, credit in agol_publish.ITEMS:
        made.append(
            (
                title,
                typ.value,
                "agol_publish.py",
                rel(os.path.normpath(os.path.join(agol_publish.PKG, r))),
                cat,
                agol_publish.properties(title, snippet, desc, lic, credit),
                {"was": agol_publish.WAS.get(title, [])},
            )
        )
    # agol_layer.py: the map, the hosted layers and their GeoPackages (made
    # here, not in the build's review folder)
    diff = agol_layer.make_diff_gpkg(
        os.path.join(out, os.path.basename(agol_layer.DIFF_GPKG))
    )
    grit = agol_layer.make_grit_gpkg(
        os.path.join(out, os.path.basename(agol_layer.GRIT_GPKG))
    )
    hp = {
        agol_layer.DIFF_TITLE: agol_layer.hosted_props(diff, agol_layer.dprops),
        agol_layer.GEO_TITLE: agol_layer.hosted_props(
            agol_layer.GEO_GPKG, agol_layer.gprops
        ),
        agol_layer.GRIT_TITLE: agol_layer.hosted_props(grit, agol_layer.rprops),
    }
    src = {
        agol_layer.DIFF_TITLE: (agol_layer.DIFF_SRC_TITLE, diff),
        agol_layer.GEO_TITLE: (agol_layer.GEO_SRC_TITLE, agol_layer.GEO_GPKG),
        agol_layer.GRIT_TITLE: (agol_layer.GRIT_SRC_TITLE, grit),
    }
    was = {
        agol_layer.DIFF_SRC_TITLE: list(agol_layer.DIFF_WAS[0]),
        agol_layer.DIFF_TITLE: list(agol_layer.DIFF_WAS[1]),
    }
    made += [
        (
            agol_layer.MAP_TITLE,
            "Web Map",
            "agol_layer.py",
            None,
            agol_layer.CAT,
            {**agol_layer.mprops, "extent": agol_layer.EXTENT},
            {},
        ),
        (
            agol_layer.LAYER_TITLE,
            "Feature Service",
            "agol_layer.py",
            None,
            agol_layer.CAT,
            agol_layer.props,
            {"published from": "4c"},
        ),
    ]
    made += [
        (
            t,
            "Feature Service",
            "agol_layer.py",
            None,
            agol_layer.CAT,
            hp[t],
            {"published from": src[t][0], "was": was.get(t, [])},
        )
        for t in hp
    ]

    # A GeoPackage's file: in the repository, or made in the output folder.
    def where(p):
        return (
            os.path.relpath(p, ROOT)
            if p.startswith(ROOT + os.sep)
            else os.path.basename(p)
        )

    made += [
        (
            src[t][0],
            "GeoPackage",
            "agol_layer.py",
            where(src[t][1]),
            agol_layer.C4D,
            hp[t],
            {"was": was.get(src[t][0], [])},
        )
        for t in hp
    ]
    fl, dl, gl, grl = (
        stand[t]
        for t in (
            agol_layer.LAYER_TITLE,
            agol_layer.DIFF_TITLE,
            agol_layer.GEO_TITLE,
            agol_layer.GRIT_TITLE,
        )
    )
    b = agol_layer.boundary_layers(fl.layers)
    area, line, pts = (
        b["esriGeometryPolygon"],
        b["esriGeometryPolyline"],
        b["esriGeometryPoint"],
    )
    bigl, every_l = agol_layer.diff_layers(dl.layers)
    geo = agol_layer.geo_layers(gl.layers)
    grit_lines, grit_areas = agol_layer.grit_layers(grl.layers)
    plan = agol_layer.plan(
        fl,
        area,
        line,
        pts,
        dl,
        bigl,
        every_l,
        gl,
        geo,
        grl,
        grit_lines,
        grit_areas,
    )
    names = {
        agol_layer.LAYER_TITLE: [
            (x, agol_layer.NAMES[x.properties.geometryType])
            for x in (area, line, pts)
        ],
        agol_layer.DIFF_TITLE: [
            (bigl, agol_layer.DNAMES["big"]),
            (every_l, agol_layer.DNAMES["all"]),
        ],
        agol_layer.GEO_TITLE: [(x, nm) for x, nm, _ in geo],
        agol_layer.GRIT_TITLE: list(
            zip((grit_lines, grit_areas), agol_layer.GRIT_NAMES, strict=True)
        ),
    }
    services = {}
    for t, it in (
        (agol_layer.LAYER_TITLE, fl),
        (agol_layer.DIFF_TITLE, dl),
        (agol_layer.GEO_TITLE, gl),
        (agol_layer.GRIT_TITLE, grl),
    ):
        alias = {id(x): out_ for x, out_ in plan["aliases"][t]}
        services[t] = {
            "url": it.url,
            "definition": agol_layer.READ_ONLY,
            "layers": [
                {
                    "id": x.properties.id,
                    "name": nm,
                    "fields with a new alias": alias.get(id(x), []),
                }
                for x, nm in names[t]
            ],
            "data": plan["data"][t],
        }
    services[agol_layer.LAYER_TITLE]["attachments on the AVA polygon"] = [
        {"name": os.path.basename(p), "size": os.path.getsize(p)}
        for p in agol_layer.ATTACH
    ]
    webmap = plan["webmap"]
    # agol_dashboard.py: built against the items the two scripts above make
    # (the folder it reads), stand-in ids
    titles = [m[0] for m in made] + [agol_dashboard.TITLE]
    ids = {
        t: stand[t].id if t in stand else f"{90000 + i:032d}"
        for i, t in enumerate(titles)
    }  # a new item: a new stand-in id
    folder = {
        t: Item(
            {
                "id": ids[t],
                "title": t,
                "type": "",
                "url": stand[t].url if t in stand else None,
            }
        )
        for t in titles
    }
    ops = {
        o["id"] for o in webmap["operationalLayers"]
    }  # as agol_dashboard.main() reads them from the web map
    rings_oid = bigl.properties.objectIdField
    with open(
        glob.glob(os.path.join(HERE, "gis", "*-line-EPSG4269.geojson"))[0],
        encoding="utf-8",
    ) as f:
        steps = [
            {
                k: feature["properties"].get(k)
                for k in ("step", "quad", "change")
            }
            for feature in json.load(f)["features"]
        ]
    dashboard, dprops = agol_dashboard.build(
        folder,
        folder[agol_dashboard.MAP_TITLE],
        ops,
        line,
        area,
        rings_oid,
        steps,
        PORTAL,
    )
    made.append(
        (
            agol_dashboard.TITLE,
            "Dashboard",
            "agol_dashboard.py",
            None,
            None,
            dprops,
            {"typeKeywords (when added)": agol_dashboard.TYPE_KEYWORDS},
        )
    )
    # agol_share.py and agol_org_categories.py
    group = {
        "access": agol_share.ACCESS,
        "tags": agol_share.TAGS,
        "description": agol_share.description(list(folder.values()), PORTAL),
    }
    items = [
        {
            "title": t,
            "type": typ,
            "id": ids[t],
            "script": s,
            "file": f,
            "group_category": c,
            "org_categories": agol_org_categories.categories(t),
            "properties": p,
            **x,
        }
        for t, typ, s, f, c, p, x in made
    ]
    facts = {
        "sqmi": agol_publish.SQMI,
        "paragraph_b": agol_publish.B,
        "about": [agol_publish.ABOUT, agol_publish.PART],
    }  # for the checks: the area, paragraph (b), the shared openings
    bundle = {
        "items": items,
        "item-list": {
            "source": os.path.relpath(items_file, ROOT)
            if items_file.startswith(ROOT)
            else items_file,
            **listed,
        },
        "services": services,
        "webmap": webmap,
        "dashboard": dashboard,
        "group": group,
        "facts": facts,
    }
    for k, v in bundle.items():
        with open(os.path.join(out, k + ".json"), "w", encoding="utf-8") as f:
            json.dump(v, f, indent=1, ensure_ascii=False)
            f.write("\n")
    return bundle


# ---- the item list, anonymously from the public site
def fetch(path, real_ids=False):
    """Writes the public group's item list, read anonymously, to a file.

    Each item has its title, type and id, and a hosted feature layer its
    service URL and its layers' definitions (LAYER_KEYS). The items are sorted
    by title.

    Args:
        path: The JSON file to write.
        real_ids: Keep the live ids; otherwise each id is replaced by a fake
            one (00000000000000000000000000000001, ...).

    Raises:
        RuntimeError: ArcGIS answers a request with an error.
    """

    def rest(url, **q):
        req = urllib.request.Request(
            url + "?" + urllib.parse.urlencode({"f": "json", **q}),
            headers={
                "User-Agent": "Mozilla/5.0 hickory-sands-district-ava agol_dryrun.py"
            },
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
        if isinstance(d, dict) and "error" in d:
            raise RuntimeError(f"{url}: {d['error']}")
        return d

    found, start = [], 1
    while start > 0:
        page = rest(REST + f"content/groups/{GROUP_ID}", num=100, start=start)
        found += page["items"]
        start = page.get("nextStart", -1)
    out = []
    for n, it in enumerate(sorted(found, key=lambda x: x["title"]), 1):
        d = {
            "title": it["title"],
            "id": it["id"] if real_ids else f"{n:032d}",
            "type": it["type"],
        }
        if it["type"] == "Feature Service":
            d["url"] = it["url"]
            d["layers"] = [
                {k: lyr.get(k) for k in LAYER_KEYS}
                for lyr in (
                    rest(f"{it['url']}/{x['id']}")
                    for x in rest(it["url"]).get("layers", [])
                )
            ]
        out.append(d)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "about": "The group's item list as the publish dry run's stand-ins (src/publish/agol_dryrun.py --fetch): titles, "
                "types, "
                + ("the live ids" if real_ids else "fake ids")
                + ", and each hosted layer's service URL and layer "
                "definitions (id, name, geometry, fields), read anonymously from the public site.",
                "portal": PORTAL,
                "items": out,
            },
            f,
            indent=1,
            ensure_ascii=False,
        )
        f.write("\n")
    print(f"{len(out)} items written to {path}")


def main():
    """Runs the dry run and its checks (exit 1 if one fails), or --fetch."""
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument(
        "out", nargs="?", default=os.path.join(ROOT, "target", "publish")
    )
    a.add_argument(
        "--items",
        default=FIXTURE,
        help="the item list to use as stand-ins (default: the committed fixture)",
    )
    a.add_argument(
        "--fetch",
        metavar="FILE",
        help="write the public group's item list to FILE, anonymously, and stop",
    )
    a.add_argument(
        "--real-ids",
        action="store_true",
        help="with --fetch: keep the live ids",
    )
    o = a.parse_args()
    if o.fetch:
        return fetch(o.fetch, o.real_ids)
    print(
        f"Publish dry run: built from {HERE}, against the item list {os.path.relpath(o.items, ROOT)}, without signing in; written to {o.out}",
        flush=True,
    )
    bundle = dry_run(o.out, o.items)
    sys.exit(1 if agol_dryrun_checks.run(bundle) else 0)


if __name__ == "__main__":
    main()
