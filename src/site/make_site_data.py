"""make_site_data.py: the website's map data, from the boundary build.

Writes the files the website's maps read (docs/data/): the boundary, its
steps and its points as GeoJSON, with only what a reader needs, and the AVA's
status from resources/site/status.json ("proposed" until TTB's final rule).
The coordinates are the build's NAD83 values rounded to 6 decimal places and
used as WGS 84 for display; the two differ by about a metre here. The record
is the boundary package for TTB, not these files. Standard library only, so
the lint workflow can test it.

Usage (the project .venv, -E -s):
  make_site_data.py --gis DIR --status FILE --out DIR [--check]
--gis is the build's GIS folder (target/work/gis). With --check nothing is
written: it exits 1 if a file in --out differs from what the build gives, and
names it.
"""

import argparse
import glob
import json
import os
import sys

DECIMALS = 6
STATUSES = ("proposed", "established")
STEP_KEYS = ("step", "kind", "endpoint", "quad", "length_m", "narrative")
POINT_KEYS = ("point", "step", "kind", "point_name", "quad")
NOTE = (
    "Display copy of the Hickory Sands District boundary for the website "
    "(NAD83 coordinates, rounded to 6 decimal places, shown as WGS 84). The "
    "record is the boundary package for TTB."
)


def rounded(coords):
    """Returns coordinates rounded for display, without any z values.

    Args:
        coords: A GeoJSON coordinate array of any depth.

    Returns:
        The same structure, each position [x, y] rounded to DECIMALS places.
    """
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], DECIMALS), round(coords[1], DECIMALS)]
    return [rounded(c) for c in coords]


def feature(source, properties):
    """Returns a GeoJSON feature with the given properties and rounded shape.

    Args:
        source: A feature from the build's GIS files.
        properties: The properties to keep, already cleaned.

    Returns:
        A new feature.
    """
    geometry = source["geometry"]
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": geometry["type"],
            "coordinates": rounded(geometry["coordinates"]),
        },
    }


def collection(name, features):
    """Returns a GeoJSON feature collection with the display note.

    Args:
        name: The collection's name.
        features: Its features.

    Returns:
        The collection.
    """
    return {
        "type": "FeatureCollection",
        "name": name,
        "description": NOTE,
        "features": features,
    }


def one(gis_dir, suffix):
    """Returns the one GeoJSON file in gis_dir whose name ends in suffix.

    Args:
        gis_dir: The build's GIS folder.
        suffix: The end of the file name, such as "-line-EPSG4269.geojson".

    Returns:
        The file's parsed contents.

    Raises:
        SystemExit: When there is not exactly one such file.
    """
    found = glob.glob(os.path.join(gis_dir, "*" + suffix))
    if len(found) != 1:
        sys.exit(f"expected one *{suffix} in {gis_dir}, found {len(found)}")
    with open(found[0], encoding="utf-8") as fh:
        return json.load(fh)


def point_order(point):
    """Returns the sort key that puts the Beginning point first.

    Args:
        point: A point's "point" property: "Beginning" or a number.

    Returns:
        A sortable key.
    """
    return -1 if point == "Beginning" else int(point)


def check_status(status):
    """Returns the status after checking it can be published.

    Args:
        status: The parsed resources/site/status.json.

    Returns:
        The status, unchanged.

    Raises:
        SystemExit: When the status is not one the site can show.
    """
    if status.get("status") not in STATUSES:
        sys.exit(f"status must be one of {STATUSES}: {status.get('status')!r}")
    if status["status"] == "established" and not (
        status.get("established_on") and status.get("cfr_section")
    ):
        sys.exit("an established AVA needs its established_on and cfr_section")
    return status


def site_data(gis_dir, status_path):
    """Returns the website's data files, by name, as the text to write.

    Args:
        gis_dir: The build's GIS folder.
        status_path: resources/site/status.json.

    Returns:
        A dict from file name to file text.
    """
    area = one(gis_dir, "-area-EPSG4269.geojson")["features"]
    lines = one(gis_dir, "-line-EPSG4269.geojson")["features"]
    points = one(gis_dir, "-points-EPSG4269.geojson")["features"]
    with open(status_path, encoding="utf-8") as fh:
        status = check_status(json.load(fh))

    first = area[0]["properties"]
    boundary = [
        feature(
            area[0],
            {
                "name": first["Name"],
                "area_sqmi": float(first["area_sqmi"]),
                "counties": first["Counties"],
            },
        )
    ]
    steps = []
    for f in sorted(lines, key=lambda f: int(f["properties"]["step"])):
        p = f["properties"]
        kept = {k: p[k] for k in STEP_KEYS}
        kept["step"] = int(p["step"])
        kept["length_m"] = round(float(p["length_m"]), 1)
        steps.append(feature(f, kept))
    marks = []
    for f in sorted(
        points, key=lambda f: point_order(f["properties"]["point"])
    ):
        p = f["properties"]
        kept = {k: p[k] for k in POINT_KEYS}
        kept["point"] = str(p["point"])
        kept["step"] = int(p["step"])
        marks.append(feature(f, kept))

    def text(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"

    return {
        "boundary.geojson": text(collection("boundary", boundary)),
        "steps.geojson": text(collection("steps", steps)),
        "points.geojson": text(collection("points", marks)),
        "status.json": json.dumps(status, ensure_ascii=False, indent=2) + "\n",
    }


def stale(files, out_dir):
    """Returns the names of the files in out_dir that differ from files.

    Args:
        files: A dict from file name to the text it should hold.
        out_dir: The folder holding the committed copies.

    Returns:
        The sorted names that are missing or different.
    """
    names = []
    for name, want in files.items():
        path = os.path.join(out_dir, name)
        try:
            with open(path, encoding="utf-8") as fh:
                have = fh.read()
        except FileNotFoundError:
            have = None
        if have != want:
            names.append(name)
    return sorted(names)


def main():
    """Writes or checks the website's map data."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gis", required=True, help="the build's GIS folder")
    ap.add_argument(
        "--status", required=True, help="resources/site/status.json"
    )
    ap.add_argument("--out", required=True, help="the site's data folder")
    ap.add_argument("--check", action="store_true", help="compare only")
    args = ap.parse_args()
    files = site_data(args.gis, args.status)
    if args.check:
        names = stale(files, args.out)
        if names:
            print(f"{args.out} is stale: {', '.join(names)}")
            sys.exit(1)
        print(f"{args.out} matches the build ({len(files)} files)")
        return
    os.makedirs(args.out, exist_ok=True)
    for name, text in files.items():
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    print(f"wrote {len(files)} files to {args.out}")


if __name__ == "__main__":
    main()
