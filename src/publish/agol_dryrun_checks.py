"""Checks on everything the publish would send to ArcGIS Online.

The publish dry run (agol_dryrun.py, issue #58) builds it without signing in
and writes it to target/publish/: items.json (each item's title, type, group
category and the properties update() sends), item-list.json (the group's item
list it was built against), services.json (each hosted layer's definition,
layer names, field aliases and visualization), webmap.json, dashboard.json,
group.json, facts.json. Python's standard library only, so the lint
workflow's unit tests run them too (tests/test_publish_dryrun.py).

One line per check; every failure names the item and what is wrong:
- items: the publish makes exactly the items in the group's item list (a new,
  retitled or dropped item shows);
- security (#25): every hosted feature layer is set read-only (capabilities
  Query,Extract; no Create, Update, Delete, Editing, Sync or Uploads);
- web map (#46): the quadrangles show no band legend (showLegend false) and a
  short pop-up naming the sheet, years without a thousands separator, no time
  filter; every operational layer and basemap has a URL, each petitioner's
  layer the URL of the hosted layer item it names, every other one a service
  from KNOWN;
- dashboard (#45, #47, #49): the desktop and the phone view both there and
  wired (check_views); every map and data source is the web map's; every link
  to an item names an item in the list and its text is in that item's title;
  every other item is linked; indicator captions within CAPTION_BUDGET
  characters per width; link cells in tables do not wrap;
- metadata (#31): culture en-us; tags with "Notice No. 243" and
  "TTB-2026-0005"; credits; a sane extent on every spatial item (numbers 4 and
  5); a group category under the item's own number;
- licences (#11, #30): each item's licence names the terms of everything it
  carries (LICENCES), credits name TTB, USGS and Esri where their content is
  (CREDITS);
- descriptions (#29, #34): each has its own text beyond the shared opening,
  each summary at least SNIPPET_MIN characters; Word files and the CSV say
  what they are; TTB's own notice is not "prepared by" the petitioner; a
  hosted layer that offers exports says they are Web Mercator and where the
  NAD83 data is;
- quadrangle titles (#44): one 5a and one 5b per quadrangle of paragraph (b),
  titled and summarized with its edition as paragraph (b) cites it;
- wording: no "agreed", "ours", "our boundary", "TTB's published polygon",
  "final text" or bare "Hickory Sandstone" in anything sent (check_outputs.py's
  rule);
- group: public, its tags, and its description links the dashboard and the
  read-me in the list.

Run by agol_dryrun.py, or on a dry run's files:
.venv/bin/python src/publish/agol_dryrun_checks.py [target/publish]
"""

import html
import json
import os
import re
import sys

EDIT = {
    "Create",
    "Update",
    "Delete",
    "Editing",
    "Sync",
    "Uploads",
}  # capabilities no public layer may have
READ = {"Query", "Extract"}
TAGS = ("Notice No. 243", "TTB-2026-0005")
# The services a web map layer that is not one of the petitioner's hosted
# layers may come from (a new one is added here, on purpose).
KNOWN = (
    # the 13 USGS quads
    "https://historical1.arcgis.com/arcgis/rest/services/USA_Historical_Topo_Maps/ImageServer",
    # TTB's layer
    "https://services7.arcgis.com/ykuAbKu9MbV93nAe/ArcGIS/rest/services/AVAs_Production/FeatureServer/0",
    "https://services.arcgisonline.com/",  # Esri basemaps
    "https://cdn.arcgis.com/sharing/rest/content/items/",  # Esri vector styles
)
TTB_PD, CC0, USGS, ESRI = (
    "U.S. Government work (public domain)",
    "CC0 1.0 Universal",
    "USGS",
    "Esri",
)
# What each item's licence must name (#11, #30): TTB's text and data stay a
# U.S. Government work, the USGS maps and geology USGS's (public domain), Esri's
# basemaps under Esri's terms; the petitioner's work is CC0. Keys: an item's
# number, or its first digit for a whole category. An item without a rule
# fails: add it here.
LICENCES = {
    "0 Read me first": (CC0,),
    "0 Dashboard": (CC0, TTB_PD, USGS, ESRI),
    "1": (TTB_PD, CC0),
    "2a": (TTB_PD, CC0),
    "2b": (TTB_PD,),
    "2c": (TTB_PD,),
    "2d": (TTB_PD, CC0),
    "3": (TTB_PD, CC0),
    "4a": (CC0, TTB_PD, USGS, ESRI),
    **{f"4{c}": (TTB_PD, CC0) for c in "bcdefghi"},
    "4j": (CC0,),
    "4k": (CC0,),
    "4l": (USGS, CC0),
    "4m": (USGS, CC0),
    "4n": (CC0,),
    "4o": (CC0,),
    "5": (USGS, CC0),
}
NOT_CC0 = {
    "2b",
    "2c",
}  # TTB's own notice and its text: not the petitioner's to dedicate
# Whom each item's credits must name besides the petitioner (#30), where their
# content is in it.
CREDITS = {
    "0 Dashboard": ("TTB", USGS, ESRI),
    "2a": ("TTB",),
    "2b": ("TTB",),
    "2c": ("TTB",),
    "4a": ("TTB", USGS, ESRI),
    **{f"4{c}": ("TTB",) for c in "bcdefghijk"},
    "4l": (USGS,),
    "4m": (USGS,),
    "4n": (USGS,),
    "4o": (USGS,),
    "5": (USGS,),
}
NAMED = {
    "TTB": r"\bTTB\b|Tax and Trade Bureau",
    USGS: r"\bUSGS\b",
    ESRI: r"\bEsri\b",
}
# Characters per caption line, per whole width of the view (#45): a third of
# the desktop's left column (0.33 of the width) holds 22, half of it 33; a third
# of a phone 20. A regression guard: #45 is settled by looking at the dashboard
# at 1366x650 and 1536x750, not by this number.
CAPTION_BUDGET = {
    "desktop": 200,
    "mobile": 60,
}
SNIPPET_MIN = 45  # characters (#34: the stub summaries were 38 and 39)
# Characters of a description beyond its shared opening paragraph (#34: eight
# items had only that).
OWN_TEXT_MIN = 80
REGION = (
    -100.0,
    30.0,
    -98.0,
    32.0,
)  # lon/lat box an extent must fall in (the AVA is near -99.2, 30.9)
# check_outputs.py's wording rule, copied (that script reads the build outputs
# when imported).
BAD = re.compile(
    r"\bagreed\b|\bours\b|\bour boundary\b|\bTTB['’]s published polygon\b"
    r"|\bfinal text\b|\bHickory\s+Sandstone\b(?!\s+Member)",
    re.I,
)
ITEM_LINK = re.compile(r"/home/item\.html\?id=([0-9a-f]{32})")
ANCHOR = re.compile(
    r"""<a\s[^>]*?href\s*=\s*(["'])(.*?)\1[^>]*>(.*?)</a>""", re.S | re.I
)
FILES = (
    "items",
    "item-list",
    "services",
    "webmap",
    "dashboard",
    "group",
    "facts",
)


# ---- helpers
def code(title):
    """Returns an item's number in the group, as agol_check.py reads it.

    Args:
        title: The item's title.

    Returns:
        "1a", "0 Dashboard", "5a Fly Gap": a quadrangle's number with its
        name, a 0 item's title up to " - ", else the title's first word.
    """
    m = re.match(r"(5[ab]) .*\) - (.+?), TX\b", title)
    return (
        f"{m[1]} {m[2]}"
        if m
        else title.split(" - ")[0]
        if title.startswith("0 ")
        else title.split(" ", 1)[0]
    )


def rule(table, title):
    """Returns an item's rule: by its number, else its category's first digit.

    Args:
        table: The rules, keyed by item number or first digit (LICENCES,
            CREDITS).
        title: The item's title.

    Returns:
        The rule, or None if the table has none for the item.
    """
    c = code(title)
    return table.get(c.split(" ")[0] if c[:1] == "5" else c, table.get(c[:1]))


def strings(x):
    """Yields every string in a JSON tree."""
    if isinstance(x, str):
        yield x
    for v in (
        x.values() if isinstance(x, dict) else x if isinstance(x, list) else ()
    ):
        yield from strings(v)


def nodes(x):
    """Yields every dict in a JSON tree."""
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from nodes(v)
    elif isinstance(x, list):
        for v in x:
            yield from nodes(v)


def text(s):
    """Returns what a reader sees of a piece of HTML: its text, spaced once."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def runs(s):
    """Returns the separate pieces of text in a piece of HTML.

    A link's title and its note, say, are two pieces, not run together.

    Args:
        s: The HTML.

    Returns:
        A list of the non-empty pieces between the tags, unescaped and
        spaced once.
    """
    return [
        t
        for t in (
            " ".join(html.unescape(x).split()) for x in re.split(r"<[^>]+>", s)
        )
        if t
    ]


def layers(tree):
    """Yields every layer of a list of web map layers, group layers opened."""
    for lyr in tree or []:
        yield lyr
        yield from layers(lyr.get("layers"))


# ---- the dashboard's two views (moved from agol_dashboard.py)
def check_views(d, ops):
    """Hard checks on the dashboard's two layouts, before anything is sent.

    In each view every element is placed once and every action, filter and map
    link points at an element of that same view (a phone action aimed at a
    desktop element would silently do nothing); the two views share no id;
    elementMappings pairs every phone element with a desktop element of the
    same type, one to one. agol_dashboard.py runs it before sending the
    dashboard; the dry run's dashboard check too.

    Args:
        d: The dashboard's JSON.
        ops: The ids of the web map's operational layers.

    Raises:
        AssertionError: A check fails.
    """

    def walk(e, name, placed, boxes):
        if e["type"] == "itemLayoutElement":
            placed.append(e["id"])
            return
        boxes.append(e["id"])
        if e["type"] == "stackLayoutElement":  # a stack's shares add up to 1
            assert (
                abs(
                    sum(
                        c["width" if e["orientation"] == "col" else "height"]
                        for c in e["elements"]
                    )
                    - 1
                )
                < 1e-9
            ), (name, e["id"])
        for c in e["elements"]:
            walk(c, name, placed, boxes)

    seen = {}
    for name in ("desktopView", "mobileView"):
        v = d[name]
        widgets_ = {w["id"]: w for w in v["widgets"]}
        selectors = {
            s["id"]: s
            for p in ("header", "sidebar", "drawer")
            for s in v.get(p, {}).get("selectors", [])
        }
        placed, boxes = [], []
        walk(v["layout"]["rootElement"], name, placed, boxes)
        assert sorted(placed) == sorted(widgets_), (
            name,
            set(placed) ^ set(widgets_),
        )
        ids = [*widgets_, *selectors, *boxes]
        assert len(ids) == len(set(ids)), (name, "an id is used twice")
        for el in [*widgets_.values(), *selectors.values()]:
            for t in re.findall(r'"targetId": "([^"]*)"', json.dumps(el)):
                base, _, part = t.partition("#")
                assert base in widgets_, (
                    name,
                    el["name"],
                    "targets an element not in this view",
                    t,
                )
                if part == "main":
                    assert any(
                        x["name"] == "main"
                        for x in widgets_[base].get("datasets", [])
                    ), (name, t)
                elif part:
                    assert (
                        widgets_[base]["type"] == "mapWidget" and part in ops
                    ), (name, t)
            if "mapWidgetId" in el:
                assert el["mapWidgetId"] in widgets_, (
                    name,
                    el["name"],
                    "a map not in this view",
                )
        seen[name] = ({**widgets_, **selectors}, set(ids))
    (desk, desk_ids), (phone, phone_ids) = (
        seen["desktopView"],
        seen["mobileView"],
    )
    assert not desk_ids & phone_ids, "the desktop and phone views share an id"
    m = d["elementMappings"]
    assert len(set(m.values())) == len(m) and set(m.values()) == set(phone), (
        "every phone element is the twin of one desktop element"
    )
    assert all(desk[a]["type"] == phone[b]["type"] for a, b in m.items()), (
        "a twin of another type"
    )
    assert "selectors" not in d["mobileView"]["header"], (
        "on a phone the header holds text and images only"
    )


# ---- the checks: each check(bundle, bad) calls bad(problem) for every problem
# it finds, and returns its summary line
def check_items(b, bad):
    """Items: the publish makes exactly the items of the group's item list."""
    made = [it["title"] for it in b["items"]]
    listed = [it["title"] for it in b["item-list"]["items"]]
    for t in sorted({t for t in made if made.count(t) > 1}):
        bad(f"{t}: made {made.count(t)} times")
    for t in sorted(set(made) - set(listed)):
        bad(
            f"{t}: not in the group's item list ({b['item-list'].get('source', 'item-list.json')}): a new or retitled item? add it there"
        )
    for t in sorted(set(listed) - set(made)):
        bad(
            f"{t}: in the group's item list, but the publish no longer makes it (it would be left in the group)"
        )
    return f"the publish makes the {len(set(made))} items of the group's item list, each once"


def check_security(b, bad):
    """Security (#25): every hosted feature layer is set read-only."""
    services = [
        it["title"] for it in b["items"] if it["type"] == "Feature Service"
    ]
    if not services:
        bad("no hosted feature layer in the items")
    for t in services:
        s = b["services"].get(t)
        if not s:
            bad(
                f"{t}: a hosted feature layer the publish does not set read-only (no definition for it)"
            )
            continue
        caps = {
            c.strip()
            for c in str(
                (s.get("definition") or {}).get("capabilities", "")
            ).split(",")
            if c.strip()
        }
        if caps & EDIT or not caps <= READ or "Query" not in caps:
            bad(
                f"{t}: capabilities {s['definition'].get('capabilities')!r}, not read-only (Query,Extract; #25)"
            )
        if (s.get("definition") or {}).get("syncEnabled"):
            bad(f"{t}: sync enabled")
    return (
        f"{len(services)} hosted feature layers set read-only (Query,Extract)"
    )


def check_webmap(b, bad):
    """Web map (#46): the quadrangles' layer, and every layer's URL."""
    wm, ids = b["webmap"], {it["id"]: it for it in b["item-list"]["items"]}
    ops = list(layers(wm.get("operationalLayers")))
    quads = [lyr for lyr in ops if lyr.get("id") == "usgs-quads"]
    if len(quads) != 1:
        bad(f"{len(quads)} USGS quadrangle layers (id usgs-quads), not 1")
    for q in quads:
        if q.get("showLegend") is not False:
            bad(
                "the quadrangles show a legend (Red: Band_1 ...): showLegend must be false (#46)"
            )
        if q.get("timeAnimation") is not False:
            bad(
                "the quadrangles' time filter is on: Map Viewer would hide the 1955-1970 sheets"
            )
        pop = q.get("popupInfo") or {}
        if not pop:
            bad(
                "the quadrangles have no pop-up of their own: Map Viewer shows the catalog's 20 raw fields (#46)"
            )
        if len(pop.get("fieldInfos") or []) > 6:
            bad(
                f"the quadrangles' pop-up shows {len(pop['fieldInfos'])} fields, not a short one (#46)"
            )
        if pop and "{Map_Name}" not in pop.get("title", ""):
            bad(
                f"the quadrangles' pop-up title {pop.get('title')!r} does not name the sheet"
            )
        for f in pop.get("fieldInfos") or []:
            if (
                re.search(r"Date|Year|Photo", f.get("fieldName", ""))
                and (f.get("format") or {}).get("digitSeparator") is not False
            ):
                bad(
                    f"the quadrangles' pop-up prints {f.get('fieldName')} with a thousands separator (1,969; #46)"
                )
    seen, n = set(), 0
    for lyr in ops + list(
        layers((wm.get("baseMap") or {}).get("baseMapLayers"))
    ):
        name = lyr.get("title") or lyr.get("id")
        if lyr.get("id") in seen:
            bad(f"two layers have the id {lyr.get('id')!r}")
        seen.add(lyr.get("id"))
        if lyr.get("layerType") == "GroupLayer":
            continue
        n += 1
        url = lyr.get("url") or lyr.get("styleUrl")
        if not url:
            bad(f"layer {name!r} has no URL")
            continue
        if lyr.get("itemId"):
            it = ids.get(lyr["itemId"])
            if it is None:
                bad(
                    f"layer {name!r}: its item {lyr['itemId']} is not in the group's item list"
                )
            elif not (it.get("url") and url.startswith(it["url"] + "/")):
                bad(
                    f"layer {name!r}: {url} is not a layer of its item {it['title']!r}"
                )
        elif not url.startswith(KNOWN):
            bad(
                f"layer {name!r}: {url} is neither a hosted layer in the group nor a known service (KNOWN)"
            )
    return f"{n} layers, each with a known URL or a layer of the group; the quadrangles with no band legend and a short pop-up"


def width_shares(v):
    """Returns each placed element's share of its view's width, by its id."""
    out = {}

    def walk(e, w):
        if e["type"] == "itemLayoutElement":
            out[e["id"]] = w
            return
        for c in e.get("elements", []):
            walk(
                c, w * c.get("width", 1) if e.get("orientation") == "col" else w
            )

    walk(v["layout"]["rootElement"], 1.0)
    return out


def check_dashboard(b, bad):
    """Dashboard (#45, #47, #49): views, links, captions and table cells."""
    d, ids = b["dashboard"], {it["id"]: it for it in b["item-list"]["items"]}
    views = {k: d.get(k) for k in ("desktopView", "mobileView")}
    for k, v in views.items():
        if not isinstance(v, dict) or not v.get("widgets"):
            bad(
                f"no {k}"
                + (" (the phone layout, #49)" if k == "mobileView" else "")
            )
    if not all(isinstance(v, dict) for v in views.values()):
        return "not checked further"
    ops = {
        lyr["id"]
        for lyr in b["webmap"].get("operationalLayers") or []
        if "id" in lyr
    }  # as agol_dashboard.main() reads them
    try:
        check_views(d, ops)
    except (AssertionError, KeyError, TypeError) as e:
        bad(f"check_views: {type(e).__name__}: {e}")
    wm_id = next(
        (it["id"] for it in b["items"] if it["type"] == "Web Map"), None
    )
    for name, v in views.items():
        for w in v["widgets"]:
            if w.get("type") == "mapWidget" and w.get("itemId") != wm_id:
                bad(
                    f"{name}: the map shows item {w.get('itemId')}, not the web map"
                )
        for x in nodes(v):
            src = (
                x.get("dataSource")
                if isinstance(x.get("dataSource"), dict)
                else {}
            )
            if src.get("type") == "layerDataSource" and (
                src.get("itemId") != wm_id or src.get("layerId") not in ops
            ):
                bad(
                    f"{name}: a data source names layer {src.get('layerId')!r} of item {src.get('itemId')}, not a layer of the web map"
                )
    # links to items: to one in the list, each piece of the link's text in its
    # title
    linked, n = set(), 0
    for s in strings(d):
        for _, href, inner in ANCHOR.findall(s):
            url = html.unescape(href)
            m = ITEM_LINK.search(url)
            if not m:
                if not url.startswith("https://"):
                    bad(f"a link to {url!r}, not a web link")
                continue
            n += 1
            it = ids.get(m[1])
            if it is None:
                bad(
                    f"a link {text(inner)!r} goes to item {m[1]}, which is not in the group's item list"
                )
                continue
            linked.add(it["id"])
            for t in runs(inner):
                if t not in it["title"]:
                    bad(
                        f"a link's text {t!r} is not in the title of the item it opens, {it['title']!r}"
                    )
    for it in b["item-list"]["items"]:
        if it["type"] != "Dashboard" and it["id"] not in linked:
            bad(f"the dashboard does not link {it['title']}")
    # indicator captions fit their width (#45)
    worst = {}
    for name, v in views.items():
        kind, share = v.get("type", "desktop"), width_shares(v)
        for w in v["widgets"]:
            if w.get("type") != "indicatorWidget":
                continue
            room = int(
                CAPTION_BUDGET.get(kind, CAPTION_BUDGET["desktop"])
                * share.get(w["id"], 1)
                + 1e-9
            )
            for part in ("topSection", "bottomSection"):
                cap = text(
                    ((w.get("defaultSettings") or {}).get(part) or {})
                    .get("textInfo", {})
                    .get("text", "")
                )
                worst[kind] = max(worst.get(kind, 0), len(cap))
                if len(cap) > room:
                    bad(
                        f"{name}: the indicator {w.get('name')!r} caption {cap!r} is {len(cap)} characters; its width holds {room} (#45)"
                    )
    # link cells in tables stay on one line (#47)
    cells = 0
    for s in strings(d):
        for attrs, inner in re.findall(
            r"<td\b([^>]*)>(.*?)</td>", s, re.S | re.I
        ):
            if "<a " in inner:
                cells += 1
                if not re.search(r"white-space\s*:\s*nowrap", attrs):
                    bad(
                        f"a table cell with the link {text(inner)!r} may wrap mid-word (no white-space:nowrap; #47)"
                    )
    return (
        f"desktop and phone views wired to the web map's layers; {n} item links, each to an item in the list and titled as it "
        f"says, every item linked; captions within their width (longest {worst.get('desktop', 0)} desktop, "
        f"{worst.get('mobile', 0)} phone); {cells} link cells nowrap"
    )


def check_metadata(b, bad):
    """Metadata (#31): culture, tags, credits, extents and group categories."""
    n = 0
    for it in b["items"]:
        t, p, c = it["title"], it["properties"], code(it["title"])
        if p.get("culture") != "en-us":
            bad(f"{t}: culture {p.get('culture')!r}, not 'en-us' (#31)")
        tags = [
            x.strip()
            for x in (
                p.get("tags")
                if isinstance(p.get("tags"), list)
                else str(p.get("tags", "")).split(",")
            )
        ]
        for want in TAGS:
            if want not in tags:
                bad(f"{t}: no tag {want!r} (#31)")
        for k in ("snippet", "description", "licenseInfo", "accessInformation"):
            if not (p.get(k) or "").strip():
                bad(f"{t}: no {k}")
        if c[:1] in "45":
            e = p.get("extent")
            ok = (
                isinstance(e, list)
                and len(e) == 2
                and all(
                    isinstance(x, list)
                    and len(x) == 2
                    and all(isinstance(v, (int, float)) for v in x)
                    for x in e
                )
                and e[0][0] < e[1][0]
                and e[0][1] < e[1][1]
                and REGION[0] <= e[0][0]
                and e[1][0] <= REGION[2]
                and REGION[1] <= e[0][1]
                and e[1][1] <= REGION[3]
            )
            if not ok:
                bad(
                    f"{t}: extent {e!r}, not a box around the AVA (a spatial item; #31)"
                )
            else:
                n += 1
        cat = it.get("group_category")
        if c[:1] in "12345" and not (
            cat and re.match(r"/Categories/" + c[0] + r"\b", cat)
        ):
            bad(f"{t}: group category {cat!r}, not one under {c[0]}")
    return f"{len(b['items'])} items: culture en-us, the docket's tags, credits; {n} spatial items with an extent around the AVA; categories by number"


def check_licences(b, bad):
    """Licences (#11, #30): each names the terms of what its item carries."""
    for it in b["items"]:
        t, p, c = it["title"], it["properties"], code(it["title"])
        lic, credit = (
            p.get("licenseInfo") or "",
            p.get("accessInformation") or "",
        )
        need = rule(LICENCES, t)
        if need is None:
            bad(f"{t}: no licence rule for item {c} (add it to LICENCES)")
            continue
        for x in need:
            if x not in lic:
                bad(
                    f"{t}: the licence does not name {x!r} (#11, #30): {lic[:90]!r}..."
                )
        if c in NOT_CC0 and CC0 in lic:
            bad(f"{t}: TTB's own work licensed CC0")
        for x in rule(CREDITS, t) or ():
            if not re.search(NAMED[x], credit):
                bad(f"{t}: the credits do not name {x} (#30): {credit!r}")
    return f"{len(b['items'])} licences name the terms of what each item carries (TTB, USGS, Esri, CC0); credits name them"


def check_descriptions(b, bad):
    """Descriptions (#29, #34): each has its own text and says what it is."""
    about = b["facts"].get("about") or []  # the shared opening paragraphs
    for it in b["items"]:
        t, p, typ = it["title"], it["properties"], it["type"]
        desc, snip = p.get("description") or "", p.get("snippet") or ""
        own = text(desc)
        for a in about:
            own = own.replace(text(a), "")
        if len(own.strip()) < OWN_TEXT_MIN:
            bad(
                f"{t}: the description has {len(own.strip())} characters beyond the shared opening (#34)"
            )
        if len(snip) < SNIPPET_MIN:
            bad(f"{t}: a stub summary, {len(snip)} characters (#34): {snip!r}")
        if typ == "Microsoft Word" and "Word" not in snip + desc:
            bad(
                f"{t}: a Word file whose summary and description do not say so (#34)"
            )
        if typ == "CSV" and ("CSV" not in desc or "paragraphs (a)" in desc):
            bad(f"{t}: a CSV file described as something else (#29)")
        if code(t) in NOT_CC0 and "Prepared by" in desc:
            bad(
                f"{t}: TTB's own notice described as prepared by the petitioner (#29)"
            )
        if (
            typ == "Feature Service"
            and re.search(r"\bExport", desc)
            and not ("Web Mercator" in desc and "NAD83" in desc)
        ):
            bad(
                f"{t}: offers exports without saying they are Web Mercator and where the NAD83 data is (#29)"
            )
    return "every description has its own text and every summary its substance; each says what its item is"


def check_quads(b, bad):
    """Quadrangle titles (#44): a 5a and a 5b per quadrangle, with edition."""
    pb = b["facts"].get("paragraph_b") or {}
    if len(pb) != 13:
        bad(f"paragraph (b) names {len(pb)} quadrangles, not 13")
    quads = [it for it in b["items"] if code(it["title"])[:1] == "5"]
    for name, edition in pb.items():
        for k, kind in (("5a", "GeoPDF"), ("5b", "GeoTIFF")):
            hits = [
                it
                for it in quads
                if it["title"].startswith(k + " ")
                and code(it["title"]) == f"{k} {name}"
            ]
            if len(hits) != 1:
                bad(f"{len(hits)} {k} items for {name}, not 1")
                continue
            it = hits[0]
            if not it["title"].endswith(f"({kind}) - {name}, TX ({edition})"):
                bad(
                    f"{it['title']}: not titled {name}, TX ({edition}), as paragraph (b) cites it (#44)"
                )
            if f"{name}, TX ({edition})" not in it["properties"].get(
                "snippet", ""
            ):
                bad(
                    f"{it['title']}: the summary does not cite {name}, TX ({edition}) (#44)"
                )
    for it in quads:
        if code(it["title"]).split(" ", 1)[1] not in pb:
            bad(f"{it['title']}: a quadrangle paragraph (b) does not cite")
    return f"{len(quads)} quadrangle items: a GeoPDF and a GeoTIFF for each of the {len(pb)} in paragraph (b), titled with its edition"


def check_wording(b, bad):
    """Wording: no forbidden phrase sent (check_outputs.py's rule)."""
    sent = [("items", it["title"]) for it in b["items"]]
    sent += [
        (it["title"], s) for it in b["items"] for s in strings(it["properties"])
    ]
    sent += [
        (f"{t} (layers)", s)
        for t, s_ in b["services"].items()
        for s in strings(s_)
    ]
    sent += [("the web map", s) for s in strings(b["webmap"])] + [
        ("the dashboard", s) for s in strings(b["dashboard"])
    ]
    sent += [("the group", s) for s in strings(b["group"])]
    for where, s in sent:
        for m in BAD.finditer(text(s)):
            bad(
                f"{where}: {m.group(0)!r} in ...{text(s)[max(0, m.start() - 50) : m.end() + 30]}..."
            )
    return f"{len(sent)} texts sent: no agreed, ours, our boundary, TTB's published polygon, final text or bare Hickory Sandstone"


def check_group(b, bad):
    """Group: public, tagged, linking the dashboard and the read-me."""
    g, ids = b["group"], {it["id"]: it for it in b["item-list"]["items"]}
    if g.get("access") != "public":
        bad(f"the group's access is {g.get('access')!r}, not public")
    for want in TAGS:
        if want not in (g.get("tags") or []):
            bad(f"the group has no tag {want!r}")
    linked = {
        ids[m].get("title", "").split(" - ")[0]
        for m in ITEM_LINK.findall(g.get("description") or "")
        if m in ids
    }
    for want in ("0 Dashboard", "0 Read me first"):
        if want not in linked:
            bad(f"the group's description does not link {want}")
    for it in b["items"]:
        cats = it.get("org_categories") or []
        if not cats or not cats[0].startswith(
            "/Categories/American Viticultural Areas (AVAs)/"
        ):
            bad(f"{it['title']}: organization categories {cats!r}")
    return "the group public, tagged, its description linking the dashboard and the read-me; every item in the AVA's organization category"


CHECKS = (
    ("items", check_items),
    ("security", check_security),
    ("web map", check_webmap),
    ("dashboard", check_dashboard),
    ("metadata", check_metadata),
    ("licences", check_licences),
    ("descriptions", check_descriptions),
    ("quad titles", check_quads),
    ("wording", check_wording),
    ("group", check_group),
)


def run(b, out=print):
    """Runs every check on a dry run's bundle, one line each.

    A check that raises fails, with the error as its problem. Each failing
    check's problems are listed under it, once each with a count.

    Args:
        b: The bundle, {name: JSON} as load() reads it.
        out: Called with each line of the report.

    Returns:
        The names of the checks that failed.
    """
    failed = []
    for name, fn in CHECKS:
        bad = []
        try:
            summary = fn(b, bad.append)
        # Any error is that check's failure, reported with the others.
        except Exception as e:  # noqa: BLE001, RUF100
            summary = "could not finish"
            bad.append(f"{type(e).__name__}: {e}")
        once = {x: bad.count(x) for x in bad}
        out(
            f"{'FAIL' if bad else 'ok  '}  {name:12s} "
            + (
                f"{len(once)} problem{'s' * (len(once) != 1)}:"
                if bad
                else summary
            )
        )
        for x, k in once.items():
            out(f"      - {x}" + (f" ({k} times)" if k > 1 else ""))
        if bad:
            failed.append(name)
    out(
        f"dry-run checks: {len(CHECKS) - len(failed)} of {len(CHECKS)} passed"
        + (f", {len(failed)} FAILED: {', '.join(failed)}" if failed else "")
    )
    return failed


def load(folder):
    """Returns a dry run's bundle, {name: JSON}, read from its files."""
    bundle = {}
    for k in FILES:
        with open(os.path.join(folder, k + ".json"), encoding="utf-8") as f:
            bundle[k] = json.load(f)
    return bundle


if __name__ == "__main__":
    folder = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            "..",
            "target",
            "publish",
        )
    )
    sys.exit(1 if run(load(folder)) else 0)
