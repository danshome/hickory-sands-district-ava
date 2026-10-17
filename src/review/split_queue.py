"""Split featurecheck.py queues into review batches for triage agents.
Usage: split_queue.py --out-dir DIR [--per 60] QUEUE.geojson [QUEUE.geojson ...]
Writes DIR/batch-<K>.json (items with item, step, kind, lon, lat, types, why, crop as an ABSOLUTE path) and prints the
batches. Contours, creeks and roads go to separate batches (each kind has its own rubric)."""
import argparse, json, os, string
ap = argparse.ArgumentParser(); ap.add_argument("queues", nargs="+"); ap.add_argument("--out-dir", required=True); ap.add_argument("--per", type=int, default=60)
a = ap.parse_args(); os.makedirs(a.out_dir, exist_ok=True)
items = []
for q in a.queues:
    base = os.path.dirname(os.path.abspath(q))
    for f in json.load(open(q))["features"]:
        p = dict(f["properties"]); p["crop"] = os.path.join(base, p["crop"]) if p.get("crop") else None
        p["lon"], p["lat"] = f["geometry"]["coordinates"][:2]; items.append(p)
letters = iter(string.ascii_uppercase)
for kind in ("contour", "creek", "road"):
    k = sorted([i for i in items if i.get("kind") == kind], key=lambda i: (i.get("priority", 9), int(i["step"])))
    for j in range(0, len(k), a.per):
        b = next(letters); json.dump(k[j:j + a.per], open(os.path.join(a.out_dir, f"batch-{b}.json"), "w"), indent=1)
        print(f"batch-{b}.json  {kind:8s} {len(k[j:j + a.per])} items")
