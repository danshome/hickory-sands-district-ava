"""Live smoke tests of the public ArcGIS Online site (issue #59).

What TTB sees without an ArcGIS account. Anonymous REST GETs only (no sign-in,
nothing written). One line per check, each failure naming the item and what is
wrong; exit 1 if any check fails.
- security: every hosted feature service in the group, and each of its layers
  and tables, has no Create, Update, Delete, Editing or Sync capability, and
  sync is off (#25);
- sharing: the group and every item in it are public, with one item for each
  number the publish scripts give (0 Read me first, 0 Dashboard, 1a-1d, 2a-2d,
  3a-3b, 4a-4o, a 5a GeoPDF and a 5b GeoTIFF for each of the 13 quadrangles),
  so a missing, private or duplicated item shows;
- links: every URL in the group's description, in each item's description,
  snippet, license and credits, and in the dashboard answers 200 (redirects
  followed, 3 tries, mailto: skipped); every link to home/item.html?id=...
  goes to a public item in the group whose title holds the link's text;
- web map: every layer and basemap URL answers ?f=json without an error, each
  layer's item is in the group (another's must at least be public), and a
  filtered layer (the AVA Map Explorer polygon) still returns its feature;
- dashboard: its JSON parses; desktopView's layout, data sources and actions
  name widgets and web map layers that exist, its map is the group's web map,
  and it links every other item in the group; mobileView is checked the same
  way once there is one (no phone layout yet is a note, #49), and every id in
  elementMappings must be in a view;
- figures, from the build's outputs in HSD_WORK or target/work (skipped when
  they are not there): the AVA polygon's Area and area_sqmi equal
  agreed-steps.json (0.01 sq mi); as many steps and points as the build's
  GeoJSON; the differences' pieces and acres by cause and side equal
  ttb-diff-stats.json, and each big difference's acres the build's rings (0.1
  acre); the Grit areas' acres, granite and sandstone equal
  grit-change-stats.json (0.01 acre);
- files: every file the build packages (and the read-me) is an item of the
  same size, downloaded and of the same SHA-256 up to 4 MB (the 26 quadrangles
  by size only); the GeoPackages agol_layer.py makes match their recorded
  SHA-256; the documents attached to the AVA polygon match the build's by name
  and size (skipped without a package).

Run last by ./build.sh publish, or by hand: ./build.sh check-live (or
.venv/bin/python -E -s -B src/publish/agol_check.py). Right after a publish
ArcGIS may take a minute to show a change to anonymous users: run it again
before chasing a failure.
"""

from concurrent.futures import ThreadPoolExecutor
import csv
import glob
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
)  # the repository root
HERE = os.environ.get("HSD_WORK") or os.path.join(
    ROOT, "target", "work"
)  # the build's work dir
PKG = os.path.join(
    HERE, "pkg", "Hickory-Sands-District-AVA_boundary-as-proposed-2026-10-15"
)
REVIEW = os.path.join(HERE, "review")
GROUP_ID = "65720ee9c5a743f88659ae39228704ec"
REST = "https://www.arcgis.com/sharing/rest/"
UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh) hickory-sands-district-ava "
    "agol_check.py"
}  # some CDNs refuse Python-urllib
EDIT = {
    "Create",
    "Update",
    "Delete",
    "Editing",
    "Sync",
}  # capabilities no public layer may have
# Files up to 4 MB are downloaded and hashed; the larger ones (the quadrangles)
# are compared by size.
HASH_MAX = 4 << 20
CODES = [
    "0 Read me first",
    "0 Dashboard",
    *["1a", "1b", "1c", "1d", "2a", "2b", "2c", "2d", "3a", "3b"],
    *(f"4{c}" for c in "abcdefghijklmno"),
]
with open(os.path.join(ROOT, "resources", "quads", "quads-manifest.csv")) as f:
    QUADS = [r["quad"].removesuffix(", TX") for r in csv.DictReader(f)]
SAME_TEXT, TEXT_CHANGE = (
    "the same text, drawn differently",
    "the proposed text change near Grit",
)  # causes, as agol_layer.py words them
CAUSES = {
    "drawing": SAME_TEXT,
    "proposed text change": TEXT_CHANGE,
}  # ttb-diff-stats.json's keys
SIDES = {
    "in the proposed revision only": "revision_only_acres",
    "in the Map Explorer polygon only": "map_explorer_only_acres",
}
ITEM_LINK = re.compile(r"/home/item\.html\?id=([0-9a-f]{32})")


# ---- anonymous HTTP
def get(url, params=None, limit=None, tries=3):
    """GETs a URL anonymously, with redirects followed and a few tries.

    A network error, a 429 or a 5xx is tried again (after 2 s, then 4 s); any
    other HTTP error is not.

    Args:
        url: The URL.
        params: Query parameters to add to it, if any.
        limit: The most bytes of the body to read (None: all of it).
        tries: How many times to try.

    Returns:
        (status, body, error): the HTTP status (None if there was no answer),
        the body (b"" after a failure), and None or what went wrong.
    """
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    for i in range(tries):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=60
            ) as r:
                return (
                    r.status,
                    r.read(limit),
                    (None if r.status == 200 else f"HTTP {r.status}"),
                )
        except urllib.error.HTTPError as e:
            code, err = e.code, f"HTTP {e.code}"
            if e.code < 500 and e.code != 429:
                break
        # No answer (DNS, TLS, a timeout, a dropped connection, a bad URL):
        # whatever the error, it is the link's result, not the check's.
        except Exception as e:  # noqa: BLE001
            code, err = None, f"{type(e).__name__}: {getattr(e, 'reason', e)}"
        if i < tries - 1:
            time.sleep(2 * (i + 1))
    return code, b"", err


def rest(url, **params):
    """Returns an ArcGIS REST resource as JSON, read anonymously.

    Args:
        url: The resource's URL.
        **params: Query parameters (f=json is added).

    Returns:
        The parsed JSON.

    Raises:
        RuntimeError: An HTTP error, or the error ArcGIS reports inside a 200
            reply.
    """
    _, body, err = get(url, {"f": "json", **params})
    if err:
        raise RuntimeError(f"{url}: {err}")
    d = json.loads(body)
    if isinstance(d, dict) and "error" in d:
        raise RuntimeError(
            f"{url}: ArcGIS error {d['error'].get('code')}: "
            f"{d['error'].get('message')}"
        )
    return d


def problem(url, **params):
    """Returns what is wrong with a REST resource, or None if it answers."""
    try:
        rest(url, **params)
    # Whatever goes wrong is the answer: it is reported, not raised.
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"


def query(url, **params):
    """Queries every feature of a layer, without geometry.

    Args:
        url: The layer's URL.
        **params: More query parameters (outFields, returnCountOnly, ...).

    Returns:
        The query's JSON.
    """
    return rest(url + "/query", where="1=1", returnGeometry="false", **params)


def parallel(fn, xs, n=8):
    """Returns {x: fn(x)} for every x, in n threads."""
    with ThreadPoolExecutor(n) as pool:
        return dict(zip(xs, pool.map(fn, xs), strict=True))


# ---- JSON and HTML helpers
def nodes(x):
    """Yields every dict in a JSON tree."""
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from nodes(v)
    elif isinstance(x, list):
        for v in x:
            yield from nodes(v)


def strings(x):
    """Yields every string in a JSON tree."""
    if isinstance(x, str):
        yield x
    for v in (
        x.values() if isinstance(x, dict) else x if isinstance(x, list) else ()
    ):
        yield from strings(v)


ANCHOR = re.compile(
    r"""<a\s[^>]*?href\s*=\s*(["'])(.*?)\1[^>]*>(.*?)</a>""", re.S | re.I
)


def links(text):
    """Returns every link in a piece of HTML or text.

    Args:
        text: The HTML or text.

    Returns:
        A list of (url, link text): one for every <a href>, with its text as a
        reader sees it, then one for every bare http(s) URL, with None.
    """
    out = [
        (
            html.unescape(u).strip(),
            " ".join(html.unescape(re.sub(r"<[^>]+>", " ", t)).split()),
        )
        for _, u, t in ANCHOR.findall(text)
    ]
    return out + [
        (html.unescape(u).rstrip(".,;:)"), None)
        for u in re.findall(r"""https?://[^\s"'<>]+""", ANCHOR.sub(" ", text))
    ]


def holds(title, text):
    """Tells whether a link's words appear in a title, in order.

    "Read me first what is ..." is held by "0 Read me first - what is ...".

    Args:
        title: The item's title.
        text: The link's text.

    Returns:
        True if every word of text is in title, in the same order.
    """

    def words(s):
        return re.findall(r"[\w']+", s.lower())

    rest = iter(words(title))
    return all(w in rest for w in words(text))


def layers(tree):
    """Yields every layer of a list of web map layers, group layers opened."""
    for lyr in tree or []:
        yield lyr
        yield from layers(lyr.get("layers"))


def code(title):
    """Returns an item's number in the group: "1a", "0 Dashboard", "5a Fly Gap".

    Args:
        title: The item's title.

    Returns:
        A quadrangle's number with its name, a 0 item's title up to " - ",
        else the title's first word.
    """
    m = re.match(r"(5[ab]) .*\) - (.+?), TX\b", title)
    return (
        f"{m[1]} {m[2]}"
        if m
        else title.split(" - ")[0]
        if title.startswith("0 ")
        else title.split(" ", 1)[0]
    )


def sha256(path):
    """Returns a file's SHA-256, in hex."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def num(v):
    """Returns a figure as people write it: 112.32, not 112.32000000000001.

    Args:
        v: The figure (anything else is shown as its repr).

    Returns:
        The figure with thousands separators and at most 3 decimals, trailing
        zeros dropped.
    """
    return (
        f"{v:,.3f}".rstrip("0").rstrip(".")
        if isinstance(v, (int, float))
        else repr(v)
    )


def excerpt(s, i):
    """Returns where two texts part: s from 25 characters before index i.

    Args:
        s: One of the texts.
        i: The index of their first difference.

    Returns:
        Up to 60 characters of s around i, with "..." if it starts later.
    """
    return ("..." if i > 25 else "") + s[max(0, i - 25) : i + 35]


def rel(p):
    """Returns a build file's path, short.

    Args:
        p: The file's path.

    Returns:
        The path relative to the package, the work dir or the repository,
        whichever holds it first.
    """
    return os.path.relpath(
        p, next(d for d in (PKG, HERE, ROOT, "/") if p.startswith(d))
    )


# ---- what the site holds (read in main(), so the module imports without
# touching the network: the unit tests use its helpers)
def load():
    """Reads the public group, its items, dashboard and web map, anonymously.

    Sets the module's globals the checks use (group, items, by_id, dash, wm,
    OPS, ...). The dashboard's or web map's error is kept for its check; if the
    group cannot be read, nothing else can be checked: it prints FAIL and
    exits 1.
    """
    global \
        group, \
        items, \
        by_id, \
        dashboards, \
        dash, \
        dash_err, \
        maps, \
        web_maps, \
        wm_item, \
        wm, \
        wm_err, \
        OPS
    built = os.path.exists(os.path.join(HERE, "agreed-steps.json"))
    print(
        "Live checks of the public ArcGIS Online site, anonymously (group "
        f"{GROUP_ID}; build outputs: {HERE if built else 'none'})",
        flush=True,
    )
    try:
        group = rest(REST + f"community/groups/{GROUP_ID}")
        items, start = [], 1
        while start > 0:
            page = rest(
                REST + f"content/groups/{GROUP_ID}", num=100, start=start
            )
            items += page["items"]
            start = page.get("nextStart", -1)
    # Whatever the error, nothing else can be checked: report it and stop.
    except Exception as e:  # noqa: BLE001
        print(
            "FAIL  group      the group cannot be read without signing in "
            f"(is it public?): {e}"
        )
        sys.exit(1)
    by_id = {it["id"]: it for it in items}
    dashboards = [it for it in items if it["type"] == "Dashboard"]
    dash, dash_err = None, "no dashboard in the group"
    if dashboards:
        try:
            dash, dash_err = (
                rest(REST + f"content/items/{dashboards[0]['id']}/data"),
                None,
            )
        # Whatever the error, the dashboard check reports it.
        except Exception as e:  # noqa: BLE001
            dash_err = f"its JSON cannot be read: {type(e).__name__}: {e}"
    # the web map: the one the dashboard's map shows, else the group's only web
    # map
    maps = [
        d.get("itemId")
        for d in nodes((dash or {}).get("desktopView"))
        if d.get("type") == "mapWidget"
    ]
    web_maps = [it for it in items if it["type"] == "Web Map"]
    wm_item = (
        by_id.get(maps[0])
        if maps
        else web_maps[0]
        if len(web_maps) == 1
        else None
    )
    wm, wm_err = (
        None,
        "no web map in the group"
        if not web_maps
        else f"the dashboard's map {maps[:1]} is not a web map in the group",
    )
    if wm_item:
        try:
            wm, wm_err = (
                rest(REST + f"content/items/{wm_item['id']}/data"),
                None,
            )
        # Whatever the error, the web map check reports it.
        except Exception as e:  # noqa: BLE001
            wm_err = (
                f"{wm_item['title']}: its JSON cannot be read: "
                f"{type(e).__name__}: {e}"
            )
    OPS = {
        lyr["id"]: lyr
        for lyr in layers((wm or {}).get("operationalLayers"))
        if "id" in lyr
    }


_kinds = {}


def op_url(op_id, geometry=None):
    """Returns the URL of a layer of the web map.

    Args:
        op_id: The layer's id in the web map (set by agol_layer.py).
        geometry: Instead, a geometry type: the URL of the boundary layer
            (hsd-<n>) of that type.

    Returns:
        The layer's URL.

    Raises:
        RuntimeError: The web map has no such layer.
    """
    if geometry:
        for i, lyr in OPS.items():
            if re.fullmatch(r"hsd-\d+", i) and lyr.get("url"):
                _kinds.setdefault(i, rest(lyr["url"]).get("geometryType"))
                if _kinds[i] == geometry:
                    return lyr["url"]
        raise RuntimeError(
            f"the web map has no boundary layer (hsd-<n>) of type {geometry}"
        )
    if not (OPS.get(op_id) or {}).get("url"):
        raise RuntimeError(f"the web map has no layer {op_id!r}")
    return OPS[op_id]["url"]


# ---- the checks: each check(bad, note) calls bad(problem) for every problem,
# note(text) for what is only worth a note, and returns its summary line
def security(bad, note):
    """Security (#25): no layer allows editing or sync."""
    services, n = [it for it in items if it["type"] == "Feature Service"], 0
    if not services:
        bad("no hosted feature service in the group")
    for it in services:
        svc = rest(it["url"])
        parts = [("the service", svc)] + [
            (
                f"layer {x['id']} ({x.get('name')})",
                rest(f"{it['url']}/{x['id']}"),
            )
            for x in svc.get("layers", []) + svc.get("tables", [])
        ]
        for where, d in parts:
            caps = {
                c.strip()
                for c in (d.get("capabilities") or "").split(",")
                if c.strip()
            }
            if caps & EDIT:
                bad(
                    f"{it['title']}: {where} allows "
                    f"{', '.join(sorted(caps & EDIT))} (capabilities "
                    f"{d.get('capabilities')})"
                )
            if d.get("syncEnabled"):
                bad(f"{it['title']}: {where} has sync enabled")
        n += len(parts) - 1
    return (
        f"{len(services)} hosted feature services, {n} layers: none allows "
        "Create, Update, Delete, Editing or Sync; sync off"
    )


def sharing(bad, note):
    """Sharing: everything public, one item for each number the scripts give."""
    if group.get("access") != "public":
        bad(f"the group is {group.get('access')!r}, not public")
    for it in items:
        if it.get("access") != "public":
            bad(f"{it['title']}: shared {it.get('access')!r}, not public")
    have, want = {}, CODES + [f"5{k} {q}" for k in "ab" for q in QUADS]
    for it in items:
        have.setdefault(code(it["title"]), []).append(it["title"])
    for c in want:
        if c not in have:
            bad(
                f"no public item {c} in the group (missing, or not shared "
                "publicly)"
            )
    for c, titles in have.items():
        if len(titles) > 1:
            bad(f"{len(titles)} items numbered {c}: {' | '.join(titles)}")
        if c not in want:
            bad(
                f"{titles[0]}: a number the publish scripts do not give (add "
                "it to CODES in agol_check.py if it is meant to be there)"
            )
    return (
        f"the group and its {len(items)} items are public: one for each of "
        f"the {len(want)} numbers"
    )


def dashboard_links():
    """Returns every link in the dashboard's JSON, as links() gives them."""
    return [(u, t) for s in strings(dash) for u, t in links(s)] if dash else []


def linkcheck(bad, note):
    """Links: every URL answers; every item link goes where its text says."""
    found = [
        ("the group's description", u, t)
        for u, t in links(group.get("description") or "")
    ]
    for it in items:
        for k in ("description", "snippet", "licenseInfo", "accessInformation"):
            found += [
                (f"{it['title']} ({k})", u, t)
                for u, t in links(it.get(k) or "")
            ]
    found += [("the dashboard", u, t) for u, t in dashboard_links()]
    found = [
        (w, u, t)
        for w, u, t in found
        if not u.lower().startswith("mailto:") and "{" not in u
    ]  # {field/...}: a list's template
    for w, u, _ in found:
        if not u.lower().startswith(("http://", "https://")):
            bad(f"{w}: {u!r} is not a web link")
    where = {}
    for w, u, _ in found:
        if u.lower().startswith(("http://", "https://")):
            where.setdefault(u, []).append(w)
    answers = parallel(lambda u: get(u, limit=1 << 16), list(where))
    for u, (_, _, err) in answers.items():
        if err:
            bad(
                f"{u} -> {err} (in {where[u][0]}"
                + (
                    f" and {len(where[u]) - 1} more places)"
                    if len(where[u]) > 1
                    else ")"
                )
            )
    named = [
        (w, ITEM_LINK.search(u)[1], t)
        for w, u, t in found
        if ITEM_LINK.search(u)
    ]
    # The group's and the dashboard's item links must stay in the group; an
    # item's may go to any public item.
    for w, i, t in named:
        if i in by_id:
            if t and not holds(by_id[i]["title"], t):
                bad(f"{w}: the link {t!r} goes to {by_id[i]['title']!r}")
        elif problem(REST + f"content/items/{i}"):
            bad(
                f"{w}: the link {t!r} goes to item {i}, which is not public "
                "or does not exist"
            )
        elif w in ("the group's description", "the dashboard"):
            bad(
                f"{w}: the link {t!r} goes to item {i}, which is not in the "
                "group"
            )
    return (
        f"{len(where)} URLs answer 200 ({sum(map(len, where.values()))} "
        f"links); {len(named)} item links go to public items in the group, "
        "each titled as the link says"
    )


def webmap(bad, note):
    """Web map: every layer's URL answers, and its item is in the group.

    Another's item must at least be public; a filtered layer (the AVA Map
    Explorer polygon) must still return its feature.
    """
    if wm is None:
        bad(wm_err)
        return "not checked"
    ops, base = (
        list(layers(wm.get("operationalLayers"))),
        list(layers((wm.get("baseMap") or {}).get("baseMapLayers"))),
    )
    urls = {}
    for lyr in ops + base:
        u = lyr.get("url") or lyr.get("styleUrl")
        if u:
            urls.setdefault(u, lyr.get("title") or lyr.get("id"))
        elif lyr.get("layerType") != "GroupLayer":
            bad(f"layer {lyr.get('title')!r} has no URL")
        # The petitioner's layers are all in the group; another must at least
        # be public.
        if lyr.get("itemId") and lyr["itemId"] not in by_id:
            p = problem(REST + f"content/items/{lyr['itemId']}")
            (bad if p else note)(
                f"layer {lyr.get('title')!r}: its item {lyr['itemId']} is not "
                "in the group"
                + (f" and cannot be opened: {p}" if p else ", but public")
            )
    for u, p in parallel(problem, list(urls)).items():
        if p:
            bad(f"{urls[u]}: {p}")
    filtered = [
        lyr
        for lyr in ops
        if (lyr.get("layerDefinition") or {}).get("definitionExpression")
        and lyr.get("url")
    ]
    for lyr in filtered:
        q = lyr["layerDefinition"]["definitionExpression"]
        if (
            rest(lyr["url"] + "/query", where=q, returnCountOnly="true").get(
                "count", 0
            )
            < 1
        ):
            bad(f"{lyr.get('title')}: no feature where {q}")
    return (
        f"{wm_item['title'].split(' - ')[0]}: {len(urls)} layer and basemap "
        "URLs answer ?f=json; their items are in the group; the filtered "
        f"layers ({len(filtered)}) return their features"
    )


def dashboard(bad, note):
    """Dashboard: both views wired to what exists, and every item linked."""
    if len(dashboards) != 1:
        bad(f"{len(dashboards)} dashboards in the group, not 1")
    if dash is None:
        bad(dash_err)
        return "not checked"
    views = {
        k: dash[k]
        for k in ("desktopView", "mobileView")
        if isinstance(dash.get(k), dict)
    }
    if "desktopView" not in views:
        bad("no desktopView")
    if "mobileView" not in views:
        note("no mobileView: no phone layout yet (#49)")
    every, said = set(), []
    for name, v in views.items():
        widgets = {w["id"]: w for w in v.get("widgets", [])}
        ids = set(widgets) | {
            s["id"]
            for part in ("header", "sidePanel", "sidebar", "drawer")
            for s in ((v.get(part) or {}).get("selectors") or [])
        }
        every |= ids | {d["id"] for d in nodes(v.get("layout")) if "id" in d}
        placed = [
            d["id"]
            for d in nodes(v.get("layout"))
            if d.get("type") == "itemLayoutElement"
        ]
        for i in placed:
            if i not in widgets:
                bad(
                    f"{name}: the layout places {i}, which is not one of its "
                    "widgets"
                )
        mapw = {i for i, w in widgets.items() if w.get("type") == "mapWidget"}
        for i in mapw:
            if not wm_item or widgets[i].get("itemId") != wm_item["id"]:
                bad(
                    f"{name}: the map shows item {widgets[i].get('itemId')}, "
                    "not the group's web map"
                )
        for d in nodes(v):
            src = (
                d.get("dataSource")
                if isinstance(d.get("dataSource"), dict)
                else {}
            )
            if src.get("type") == "layerDataSource" and (
                not wm_item
                or src.get("itemId") != wm_item["id"]
                or src.get("layerId") not in OPS
            ):
                bad(
                    f"{name}: a data source names layer "
                    f"{src.get('layerId')!r} of item {src.get('itemId')}, not "
                    "a layer of the group's web map"
                )
            t = d.get("targetId")
            if isinstance(t, str):
                w, _, sub = t.partition("#")
                if w not in ids:
                    bad(
                        f"{name}: an action targets {t}, which is not one of "
                        "its elements"
                    )
                elif w in mapw and sub and sub not in OPS:
                    bad(
                        f"{name}: an action targets the map's layer {sub!r}, "
                        "which the web map does not have"
                    )
        said.append(f"{name} {len(widgets)} widgets ({len(placed)} placed)")
    mapped = dash.get("elementMappings") or {}
    for k, val in mapped.items():
        for x in [k] + (
            val
            if isinstance(val, list)
            else [val]
            if isinstance(val, str)
            else []
        ):
            if x not in every:
                bad(f"elementMappings names {x}, which is in no view")
    linked = {
        ITEM_LINK.search(u)[1]
        for u, _ in dashboard_links()
        if ITEM_LINK.search(u)
    }
    for it in items:
        if it["id"] not in linked and it["type"] != "Dashboard":
            bad(f"the dashboard does not link {it['title']}")
    return (
        f"{dashboards[0]['title'].split(' - ')[0]}: the JSON parses; "
        f"{'; '.join(said)}, all wired to what exists; links all "
        f"{len(linked)} other items"
    )


def figures(bad, note):
    """Figures: the live layers' area, counts, attributes and acres as built."""
    if not os.path.exists(os.path.join(HERE, "agreed-steps.json")):
        return (
            f"skipped: no build outputs in {HERE} (run ./build.sh first, or "
            "point HSD_WORK at them)"
        )
    if wm is None:
        bad(f"the layers cannot be found: {wm_err}")
        return "not checked"

    def load(path):
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        note(f"{rel(path)} is not in the build outputs: not compared")
        return None

    said = []
    with open(os.path.join(HERE, "agreed-steps.json")) as f:
        sqmi = json.load(f)["sqmi"]
    ava = query(op_url(None, "esriGeometryPolygon"), outFields="*")["features"]
    if len(ava) != 1:
        bad(f"the AVA layer holds {len(ava)} polygons, not 1")
    for f in ava:
        for k in ("Area", "area_sqmi"):
            v = f["attributes"].get(k)
            if not isinstance(v, (int, float)) or abs(v - sqmi) > 0.01:
                bad(
                    f"the AVA polygon's {k} is {num(v)}, the build's area "
                    f"{num(sqmi)} sq mi"
                )
    said.append(f"AVA {sqmi:.2f} sq mi")
    for what, geometry, pat in (
        ("steps", "esriGeometryPolyline", "line"),
        ("points", "esriGeometryPoint", "points"),
    ):
        files = glob.glob(
            os.path.join(HERE, "gis", f"*-{pat}-EPSG4269.geojson")
        )
        if not files:
            note(
                f"no gis/*-{pat}-EPSG4269.geojson in the build outputs: "
                f"{what} not counted"
            )
            continue
        with open(files[0]) as f:
            built = json.load(f)["features"]
        want, got = (
            len(built),
            query(op_url(None, geometry), returnCountOnly="true")["count"],
        )
        if want != got:
            bad(f"{what}: {got} live, {want} in the build's {rel(files[0])}")
        # every attribute as built (#71: a republish once left the live steps
        # with their first-published text and quads)
        key = "step" if pat == "line" else "point"
        live = {
            str(r["attributes"][key]): r["attributes"]
            for r in query(op_url(None, geometry), outFields="*")["features"]
        }
        off = 0
        for f in built:
            have = live.get(str(f["properties"][key]))
            if have is None:
                continue  # counted above
            for a, v in f["properties"].items():
                # a field the layer doesn't hold is not compared
                w = have.get(a, v)
                same = (
                    abs(w - v) <= 1e-6 * max(1.0, abs(v))
                    if isinstance(v, float) and isinstance(w, (int, float))
                    else w == v
                )
                if not same:
                    off += 1
                    if off <= 5:
                        # show where they part: 25 characters before the
                        # first difference
                        sw, sv = str(w), str(v)
                        i = next(
                            (
                                j
                                for j, (x, y) in enumerate(
                                    zip(sw, sv, strict=False)
                                )
                                if x != y
                            ),
                            min(len(sw), len(sv)),
                        )
                        bad(
                            f"{what} {f['properties'][key]}: {a} is "
                            f"{excerpt(sw, i)!r} live, {excerpt(sv, i)!r} in "
                            "the build"
                        )
        if off > 5:
            bad(f"{what}: {off - 5} more attributes differ from the build")
        said.append(f"{got} {what} (every attribute as built)")
    stats = load(os.path.join(REVIEW, "ttb-diff-stats.json"))
    if stats:
        out = json.dumps(
            [
                {
                    "statisticType": "sum",
                    "onStatisticField": "acres",
                    "outStatisticFieldName": "acres",
                },
                {
                    "statisticType": "count",
                    "onStatisticField": "acres",
                    "outStatisticFieldName": "n",
                },
            ]
        )
        rows = query(
            op_url("hsd-all-differences"),
            groupByFieldsForStatistics="cause,side",
            outStatistics=out,
        )["features"]
        live = {
            (r["attributes"]["cause"], r["attributes"]["side"]): r["attributes"]
            for r in rows
        }
        for x in set(live) - {(c, s) for c in CAUSES.values() for s in SIDES}:
            bad(f"differences: an unexpected cause and side {x}")
        for key, cause in CAUSES.items():
            s = stats["areas"][key]
            n = sum(live.get((cause, side), {}).get("n") or 0 for side in SIDES)
            if n != s["pieces"]:
                bad(
                    f"differences, {cause}: {n} pieces live, {s['pieces']} in "
                    "the build"
                )
            for side, k in SIDES.items():
                a = live.get((cause, side), {}).get("acres") or 0
                if abs(a - s[k]) > 0.1:
                    bad(
                        f"differences, {cause}, {side}: {a:,.1f} acres live, "
                        f"{s[k]:,.1f} in the build"
                    )
        rings = query(
            op_url("hsd-rings"),
            outFields="n,revision_only_acres,map_explorer_only_acres",
            orderByFields="n",
        )["features"]
        if len(rings) != stats["big"]:
            bad(
                f"big differences: {len(rings)} live, {stats['big']} in the "
                "build"
            )
        built = load(os.path.join(REVIEW, "ttb-diff-rings-EPSG4269.geojson"))
        for n, (b, r) in enumerate(
            zip(
                [
                    f["properties"]
                    for f in (built or {}).get("features", [])
                    if f["properties"].get("big")
                ],
                rings,
                strict=False,  # a count that differs is reported above
            ),
            1,
        ):
            for bk, lk in (
                ("ours_adds_acres", "revision_only_acres"),
                ("ours_drops_acres", "map_explorer_only_acres"),
            ):
                if abs((r["attributes"].get(lk) or 0) - b[bk]) > 0.1:
                    bad(
                        f"big difference #{n}: {lk} "
                        f"{num(r['attributes'].get(lk))} live, {num(b[bk])} "
                        "in the build's rings"
                    )
        said.append(
            f"{sum(s['pieces'] for s in stats['areas'].values())} pieces of "
            f"land between the lines and {stats['big']} big differences"
        )
    grit = load(os.path.join(REVIEW, "grit-change-stats.json"))
    if grit:
        live = {
            r["attributes"]["what"]: r["attributes"]
            for r in query(
                op_url("hsd-grit-areas"),
                outFields="what,acres,granite_acres,sandstone_acres",
            )["features"]
        }
        for what in set(live) ^ set(grit["areas"]):
            bad(
                f"Grit areas: {what!r} is "
                f"{'live only' if what in live else 'in the build only'}"
            )
        for what, s in grit["areas"].items():
            for k in ("acres", "granite_acres", "sandstone_acres"):
                v = (live.get(what) or {}).get(k)
                if what in live and (
                    not isinstance(v, (int, float)) or abs(v - s[k]) > 0.01
                ):
                    bad(
                        f"Grit, {what}: {k} {num(v)} live, {num(s[k])} in the "
                        "build"
                    )
        lines = load(os.path.join(REVIEW, "grit-change-lines-EPSG4269.geojson"))
        n = (
            query(op_url("hsd-grit-lines"), returnCountOnly="true")["count"]
            if lines
            else 0
        )
        if lines and n != len(lines["features"]):
            bad(f"Grit lines: {n} live, {len(lines['features'])} in the build")
        said.append(f"the Grit acres of {len(grit['areas'])} areas")
    return ", ".join(said) + ": as built"


def files(bad, note):
    """Files: each file the build makes is an item of the same size and hash."""
    if not os.path.isdir(PKG):
        return (
            f"skipped: no package in {PKG} (run ./build.sh first, or point "
            "HSD_WORK at the build outputs)"
        )

    # ArcGIS keeps an uploaded file's name with its spaces made underscores.
    def norm(name):
        return name.replace(" ", "_")

    built = {
        norm(os.path.basename(p)): p
        for p in sorted(
            glob.glob(os.path.join(PKG, "*", "**", "*"), recursive=True)
        )
        if os.path.isfile(p)
    }
    built.update(
        {
            norm(os.path.basename(p)): p
            for p in glob.glob(
                os.path.join(HERE, "documents", "*read-me-first*.pdf")
            )
        }
    )
    made = {
        norm(os.path.basename(p)): p
        for p in glob.glob(os.path.join(REVIEW, "*.gpkg"))
        + glob.glob(os.path.join(ROOT, "resources", "geology", "*.gpkg"))
    }
    named, local = (
        {it["name"]: it for it in items if it.get("name")},
        {**made, **built},
    )  # made: the GeoPackages agol_layer.py uploads
    for name, p in built.items():
        if name not in named:
            bad(f"{rel(p)}: no public item in the group holds this file")
    small, sized = [], 0
    for name, it in named.items():
        p, sha = local.get(name), (it.get("properties") or {}).get("sha256")
        if p is None:
            if sha:
                note(
                    f"{it['title']}: its GeoPackage is made by agol_layer.py "
                    "when publishing; not in these build outputs, not compared"
                )
            else:
                bad(
                    f"{it['title']}: its file {name} is not one the build makes"
                )
            continue
        if it.get("size") != os.path.getsize(p):
            bad(
                f"{it['title']}: {it.get('size'):,} bytes live, the build's "
                f"{rel(p)} {os.path.getsize(p):,}"
            )
            continue
        sized += 1
        if sha and sha != sha256(p):
            bad(f"{it['title']}: the recorded SHA-256 is not that of {rel(p)}")
        elif not sha and it["size"] <= HASH_MAX:
            small.append(name)
    for name, (_, body, err) in parallel(
        lambda nm: get(REST + f"content/items/{named[nm]['id']}/data"), small, 6
    ).items():
        if err or len(body) != named[name]["size"]:
            bad(
                f"{named[name]['title']}: the download fails: "
                f"{err or f'{len(body):,} bytes, not {named[name]["size"]:,}'}"
            )
        elif hashlib.sha256(body).hexdigest() != sha256(local[name]):
            bad(
                f"{named[name]['title']}: the same size as "
                f"{rel(local[name])}, but a different file (not the one this "
                "build made)"
            )
    att, url = 0, op_url(None, "esriGeometryPolygon") if wm else None
    for oid in (
        (query(url, returnIdsOnly="true").get("objectIds") or []) if url else []
    ):
        for a in rest(f"{url}/{oid}/attachments").get("attachmentInfos", []):
            p, att = built.get(norm(a["name"])), att + 1
            if p is None:
                bad(
                    f"the AVA polygon's attachment {a['name']} is not a file "
                    "the build makes"
                )
            elif a.get("size") != os.path.getsize(p):
                bad(
                    f"the AVA polygon's attachment {a['name']}: "
                    f"{a.get('size'):,} bytes live, the build's "
                    f"{os.path.getsize(p):,}"
                )
    return (
        f"{sized} file items the same size as the build's files, the "
        f"{len(small)} up to 4 MB downloaded with the same SHA-256; the {att} "
        "documents attached to the AVA polygon as built"
    )


def main():
    """Reads the site and runs every check, one line each; exit 1 if one fails.

    Importable for the tests (tests/test_agol_check.py).
    """
    load()
    results = []
    for name, fn in (
        ("security", security),
        ("sharing", sharing),
        ("links", linkcheck),
        ("web map", webmap),
        ("dashboard", dashboard),
        ("figures", figures),
        ("files", files),
    ):
        bad, notes = [], []
        try:
            summary = fn(bad.append, notes.append)
        # Any error is that check's failure, reported with the others.
        except Exception as e:  # noqa: BLE001
            summary = "could not finish"
            bad.append(f"{type(e).__name__}: {e}")
        status, once = (
            "FAIL"
            if bad
            else "skip"
            if summary.startswith("skipped")
            else "ok  ",
            {b: bad.count(b) for b in bad},
        )
        print(
            f"{status}  {name:10s} "
            + (
                f"{len(once)} problem{'s' * (len(once) != 1)}:"
                if bad
                else summary
            ),
            flush=True,
        )
        for b, k in once.items():
            print(f"      - {b}" + (f" ({k} times)" if k > 1 else ""))
        for n in notes:
            print(f"      note: {n}")
        results.append(status)
    print(
        f"live checks: {results.count('ok  ')} of {len(results)} passed"
        + (f", {results.count('skip')} skipped" if "skip" in results else "")
        + (f", {results.count('FAIL')} FAILED" if "FAIL" in results else "")
    )
    sys.exit(1 if "FAIL" in results else 0)


if __name__ == "__main__":
    main()
