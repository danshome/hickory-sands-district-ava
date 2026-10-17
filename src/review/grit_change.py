"""grit_change.py: the lines and acres the proposed change near Grit swaps.

Line by line and acre by acre, with the granite in each piece. Three versions
of the AVA, all from our own lines (none from TTB's polygon):
  TTB's published text: our final lines, with TTB's steps (10)-(11) and
      (90)-(92) as drawn from TTB's text on Oct. 14
      (resources/boundary/proposed/step-lines-2026-10-14), and TTB's (93)-(96)
      as our (101)-(104);
  the petition: our final lines, with the petition's straight line from the
      marked 1,737 to the marked 1,762 in place of the new steps (93)-(96);
  ours: the final boundary.
Both of the petition's routes start and end where TTB's do (Honey Creek at
point 89, the end of Lange Road), so the differences between the versions are
exactly the pieces the change moves. Each piece gets its acres, the acres of
granite (Town Mountain Granite and younger granitic intrusions) and of the
Hickory Sandstone Member formation in it, from the USGS SGMC units shifted to
the outcrops (resources/geology), and the steps along it.

Usage (the project .venv, -E -s):
  grit_change.py --line LINE.geojson --oct14 STEP-LINES.geojson --geology GPKG
                 --out-dir DIR
Outputs: grit-change-lines-EPSG4269.geojson,
grit-change-areas-EPSG4269.geojson, grit-change-stats.json (NAD83, EPSG:4269;
areas in NAD83 / Conus Albers, EPSG:5070, an equal-area projection; line
lengths geodesic on GRS 1980, as in the boundary layer).
"""

import argparse
import json
import os

from osgeo import ogr
from osgeo import osr

ogr.UseExceptions()
SQM_PER_ACRE = 4046.8564224
TTB_STEPS, NEW_STEPS = (10, 11, 90, 91, 92), (93, 94, 95, 96)
PETITION_STEPS = (10, 11, 90, 91, 92, 97, 98, 99, 100)


def tr(src, dst):
    """Returns the transformation between two EPSG codes, in lon/lat order."""
    a = osr.SpatialReference()
    a.ImportFromEPSG(src)
    b = osr.SpatialReference()
    b.ImportFromEPSG(dst)
    for s in (a, b):
        s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(a, b)


TO_M, TO_LL = tr(4269, 5070), tr(5070, 4269)


def flat(c):
    """Returns the points of a line's or a multiline's coordinates, in order."""
    return [p for part in c for p in part] if isinstance(c[0][0], list) else c


def glen(coords):
    """Returns the geodesic length of a lon/lat line on GRS 1980 (NAD83), in m.

    As the boundary layer's step lengths are measured (issue #35).
    """
    g = ogr.Geometry(ogr.wkbLineString)
    for x, y in coords:
        g.AddPoint_2D(x, y)
    ll = osr.SpatialReference()
    ll.ImportFromEPSG(4269)
    ll.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    g.AssignSpatialReference(ll)
    return g.GeodesicLength()


def line(coords):
    """Returns a lon/lat line as a line in EPSG:5070 metres."""
    g = ogr.Geometry(ogr.wkbLineString)
    for x, y in coords:
        g.AddPoint_2D(x, y)
    g.Transform(TO_M)
    return g


def polygon(steps):
    """Returns the polygon (EPSG:5070) whose ring runs through these steps.

    Args:
        steps: the step lines' lon/lat coordinates, in order round the ring.
    """
    pts = [p for c in steps for p in flat(c)]
    r = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in [*pts, pts[0]]:
        r.AddPoint_2D(x, y)
    g = ogr.Geometry(ogr.wkbPolygon)
    g.AddGeometry(r)
    g.Transform(TO_M)
    return g if g.IsValid() else g.MakeValid()


def pieces(g, min_acres):
    """Returns the polygons of a difference, largest first.

    Args:
        g: the difference between two versions (EPSG:5070).
        min_acres: smaller polygons, slivers from pin rounding, are dropped.
    """
    t = ogr.GT_Flatten(g.GetGeometryType())
    ps = (
        [g]
        if t == ogr.wkbPolygon
        else [g.GetGeometryRef(i) for i in range(g.GetGeometryCount())]
    )
    ps = [
        p
        for p in ps
        if ogr.GT_Flatten(p.GetGeometryType()) == ogr.wkbPolygon
        and p.GetArea() >= min_acres * SQM_PER_ACRE
    ]
    return sorted(ps, key=lambda p: -p.GetArea())


def geojson_ll(g):
    """Returns an EPSG:5070 geometry as NAD83 lon/lat GeoJSON, 8 decimals."""
    g = g.Clone()
    g.Transform(TO_LL)

    def round_coords(c):
        if isinstance(c[0], float):
            return [round(c[0], 8), round(c[1], 8)]
        return [round_coords(x) for x in c]

    j = json.loads(g.ExportToJson())
    j["coordinates"] = round_coords(j["coordinates"])
    return j


def tally(stats, what, exact):
    """Adds a piece's exact acres to its kind's totals.

    The totals are summed unrounded; rounded() rounds them once (issue #33: no
    double rounding).

    Args:
        stats: the totals by kind, updated in place.
        what: the piece's kind.
        exact: the piece's acres, granite acres and sandstone acres.
    """
    s = stats.setdefault(
        what,
        {
            "pieces": 0,
            "acres": 0.0,
            "granite_acres": 0.0,
            "sandstone_acres": 0.0,
        },
    )
    s["pieces"] += 1
    for k, v in exact.items():
        s[k] += v


def rounded(stats):
    """Rounds the totals once, from the unrounded sums, and returns them."""
    for s in stats.values():
        for k in ("acres", "granite_acres", "sandstone_acres"):
            s[k] = round(s[k], 2)
    return stats


def main():
    """Writes the change's lines, pieces and totals (see the module's text)."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", required=True)
    ap.add_argument("--oct14", required=True)
    ap.add_argument("--geology", required=True)
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--min-acres", type=float, default=0.5)
    a = ap.parse_args()
    with open(a.line) as fh:
        feats = {
            int(f["properties"]["step"]): f for f in json.load(fh)["features"]
        }
    fin = {s: f["geometry"]["coordinates"] for s, f in feats.items()}
    with open(a.oct14) as fh:
        o14 = {
            int(f["properties"]["step"]): f for f in json.load(fh)["features"]
        }

    def last(s):
        return flat(fin[s])[-1]

    # the petition's straight line from the marked 1,737 to the marked 1,762
    straight = [last(92), last(96)]
    ours = polygon([fin[s] for s in sorted(fin)])
    petition = polygon(
        [fin[s] for s in range(1, 93)]
        + [straight]
        + [fin[s] for s in range(97, max(fin) + 1)]
    )
    ttb = polygon(
        [fin[s] for s in range(1, 10)]
        + [
            o14[10]["geometry"]["coordinates"],
            o14[11]["geometry"]["coordinates"],
        ]
        + [fin[s] for s in range(12, 90)]
        + [o14[s]["geometry"]["coordinates"] for s in (90, 91, 92)]
        + [fin[s] for s in range(101, max(fin) + 1)]
    )
    geo = ogr.Open(a.geology)

    def union(names):
        u = None
        for n in names:
            for f in geo.GetLayerByName(n):
                g = f.GetGeometryRef().Clone()
                g.Transform(TO_M)
                g = g.Buffer(0)
                u = g if u is None else u.Union(g)
        return u

    granite, sandstone = (
        union(["Town_Mountain_Granite", "Younger_granitic_intrusions"]),
        union(["Hickory_Sandstone_Member_formation"]),
    )
    ours_lines = {s: line(flat(fin[s])) for s in fin}
    petition_lines = {
        **{s: g for s, g in ours_lines.items() if s not in NEW_STEPS},
        "1737-1762": line(straight),
    }
    ttb_lines = {
        s: line(flat(o14[s]["geometry"]["coordinates"])) for s in TTB_STEPS
    }

    def along(p, lines):
        # the steps that run along a piece (at least 100 m of the step within
        # 2 m of it)
        edge = p.Buffer(2.0)
        return [
            s
            for s, g in sorted(
                lines.items(), key=lambda kv: str(kv[0]).zfill(9)
            )
            if g.Intersection(edge).Length() >= 100.0
        ]

    # ---- areas
    areas, stats = [], {}

    def add(what, why, g, side, our_set):
        for p in pieces(g, a.min_acres):
            ours_along, ttb_along = along(p, our_set), along(p, ttb_lines)
            exact = {
                "acres": p.GetArea() / SQM_PER_ACRE,
                "granite_acres": p.Intersection(granite).GetArea()
                / SQM_PER_ACRE,
                "sandstone_acres": p.Intersection(sandstone).GetArea()
                / SQM_PER_ACRE,
            }
            props = {
                "what": what,
                "why": why,
                "side": side,
                **{k: round(v, 2) for k, v in exact.items()},
                "revision_steps": ",".join(map(str, ours_along)),
                "notice_steps": ",".join(map(str, ttb_along)),
            }
            if what == "petition, not Notice No. 243" and ttb_along == [10, 11]:
                props["what"] = "lane wording"
                props["why"] = (
                    "the petition's westbound lane of the highway, 30 m from "
                    "the center line Notice No. 243 follows"
                )
            areas.append(
                {
                    "type": "Feature",
                    "geometry": geojson_ll(p),
                    "properties": props,
                }
            )
            tally(stats, props["what"], exact)

    add(
        "Notice No. 243, not the petition",
        "in Notice No. 243's text; the petition leaves it out",
        ttb.Difference(petition),
        "left out",
        petition_lines,
    )
    add(
        "petition, not Notice No. 243",
        "in the petition; Notice No. 243's text leaves it out",
        petition.Difference(ttb),
        "put in",
        petition_lines,
    )
    add(
        "granite lobe",
        "also left out now: new steps (93)-(96) go around it instead of the "
        "petition's straight line",
        petition.Difference(ours),
        "left out",
        ours_lines,
    )
    add(
        "put back",
        "put back: between the marked 1,737 and the windmill, inside the "
        "petition's straight line",
        ours.Difference(petition),
        "put in",
        ours_lines,
    )
    rounded(stats)

    # ---- lines
    lines = []

    def add_line(role, label, steps, coords, src):
        g = line(flat(coords))
        lines.append(
            {
                "type": "Feature",
                "geometry": geojson_ll(g),
                "properties": {
                    "role": role,
                    "label": label,
                    "steps": steps,
                    "length_m": round(glen(flat(coords))),
                    "source": src,
                },
            }
        )

    for s in TTB_STEPS:
        add_line(
            "replaced: a Notice No. 243 step",
            f"Notice ({s})",
            str(s),
            o14[s]["geometry"]["coordinates"],
            "Notice No. 243's text, as drawn by the petitioner on the USGS "
            "maps",
        )
    for s in PETITION_STEPS:
        add_line(
            "put back: the petition's wording",
            f"({s})",
            str(s),
            fin[s],
            "the proposed text (the petition's wording)",
        )
    for s in NEW_STEPS:
        add_line(
            "new: around the granite lobe",
            f"({s})",
            str(s),
            fin[s],
            "the proposed text (new steps)",
        )
    add_line(
        "replaced: the petition's straight line",
        "petition: marked 1,737 to marked 1,762",
        "93-96",
        straight,
        "the petition (February 2, 2023), replaced by new steps (93)-(96)",
    )

    crs = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4269"}}
    os.makedirs(a.out_dir, exist_ok=True)
    with open(
        os.path.join(a.out_dir, "grit-change-lines-EPSG4269.geojson"), "w"
    ) as fh:
        json.dump(
            {"type": "FeatureCollection", "crs": crs, "features": lines}, fh
        )
    with open(
        os.path.join(a.out_dir, "grit-change-areas-EPSG4269.geojson"), "w"
    ) as fh:
        json.dump(
            {"type": "FeatureCollection", "crs": crs, "features": areas}, fh
        )

    def sqmi(g):
        return round(g.GetArea() / (SQM_PER_ACRE * 640), 2)

    with open(os.path.join(a.out_dir, "grit-change-stats.json"), "w") as fh:
        json.dump(
            {
                "areas": stats,
                "sqmi": {
                    "notice_243": sqmi(ttb),
                    "petition": sqmi(petition),
                    "revision": sqmi(ours),
                },
            },
            fh,
            indent=1,
        )
    print(
        "the change near Grit:",
        ", ".join(
            f"{k} {v['acres']:.0f} ac ({v['granite_acres']:.0f} granite)"
            for k, v in stats.items()
        ),
    )


if __name__ == "__main__":
    main()
