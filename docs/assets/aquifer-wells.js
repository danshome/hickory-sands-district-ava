// The wells of the 3D aquifer page (aquifer.html): TWDB's Submitted
// Driller's Reports and Groundwater Database, from assets/aquifer/wells/
// (made by src/site/make_aquifer_3d.py, without people's names).
//
// Each well has a head at the ground, coloured by the rock its water comes
// from, and a line from the ground down to the depth its report gives, at the
// same vertical exaggeration as the ground and the aquifer, coloured interval
// by interval by its own log. Only the wells that pass the filters are
// drawn. By the view's map scale (the scales are in
// assets/aquifer/stats.json):
// - zoomed far out, while no more than FAR_HEADS_MAX wells pass, the head of
//   every one of them, with the overview's lines (below); when more pass, a
//   thinned overview, one well per overview cell, with its head and its
//   line, each drawn if it passes;
// - from the District view's scale in (wells_all_scale), the head of every
//   well that passes, with the overview's lines;
// - closer in (wells_lines_scale), those heads and every line in the tiles
//   around the middle of the view, up to a cap; the page says how many wells
//   that pass, in view, have only their heads drawn.
// The heads come from the compact heads files (wells/heads-<n>.json): a
// small layer of just the wells that pass while no more than FAR_HEADS_MAX
// do, else one layer of every well's head, made once, drawn filtered.
// A well's raw report is fetched only when it is clicked. Text from the data
// is only ever set as text.

const DATA = "assets/aquifer/wells/";
const FT = 0.304800609601219; // metres per US survey foot
const REPORT =
  "https://www3.twdb.texas.gov/apps/waterdatainteractive/GetReports.aspx";

export const CLASS_NAMES = [
  "granite",
  "gneiss, schist or marble",
  "sandstone, or “Hickory” in the log",
  "limestone",
  "other rock",
  "not logged",
];
export const CLASS_COLORS = {
  0: [232, 96, 120], // granite: pink-red
  1: [168, 120, 232], // gneiss, schist, marble: violet
  2: [240, 214, 72], // sandstone, "Hickory": yellow
  3: [110, 196, 110], // limestone: green
  4: [196, 168, 128], // other: tan
  5: [128, 128, 128], // not logged: grey
};
const WATER = [120, 222, 244];
const BASIS = ["its logged water-bearing zone", "its deepest logged interval", ""];

// Zoomed far out, the head of every well that passes the filters is drawn
// while no more than this many pass; beyond it, the thinned overview. It is
// about three times the overview's heads: at the "Whole aquifer" view on a
// phone an overview cell is under 20 px across and a head 6 px, so about
// three heads to a cell still read as wells, and more run together. It is
// also about as many features as the overview draws (its heads and their
// lines), so a phone makes and draws no more at first than before.
export const FAR_HEADS_MAX = 3000;

// A well's head's values (wells/heads-<n>.json, index.heads.fields), by
// name, as wellAttributes() gives them; its report's cell is found from its
// place, as the generator files it.
export function headAttributes(h, detailDegrees) {
  const [uid, lon, lat, depth, hickory, use, wcls, wtop, wbot, wbasis, gpm, ytype] = h;
  const cell = `${Math.floor(lon / detailDegrees)}_${Math.floor(lat / detailDegrees)}`;
  return wellAttributes([uid, lon, lat, depth, null, null, null, hickory, cell, use, wcls, wtop, wbot, wbasis, gpm, ytype]);
}

// A drawing record's values (wells/index.json's fields), by name.
export function wellAttributes(r) {
  const [uid, lon, lat, depth, , , , hickory, cell, use, wcls, wtop, wbot, wbasis, gpm, ytype] = r;
  const title = uid[0] === "S"
    ? `TWDB driller's report ${uid.slice(1)}`
    : `TWDB state well ${uid.slice(1)}`;
  return { uid, lon, lat, depth, hickory, cell, use, wcls, wtop, wbot, wbasis, yield: gpm, ytype, title };
}

export async function setupWells(opts) {
  const { map, view, small, FeatureLayer, Graphic, Polyline, Point, SpatialReference, reactiveUtils } = opts;
  const response = await fetch(`${DATA}index.json`);
  if (!response.ok) {
    throw new Error(`wells/index.json: HTTP ${response.status}`);
  }
  const index = await response.json();
  let k = opts.exaggeration;
  // Dan, 2026-10-19: by default only irrigation wells that tested at 25 gpm
  // or more (a well with no reported yield is left out); the panel's filters
  // widen it.
  const IRRIGATION = index.use_groups.indexOf("Irrigation");
  const DEFAULTS = {
    on: true,
    water: false,
    hickoryOnly: false,
    uses: new Set(IRRIGATION >= 0 ? [IRRIGATION] : index.use_groups.map((_, i) => i)),
    yieldLo: 25,
    yieldHi: Infinity,
    noYield: false,
    depthLo: 0,
    depthHi: Infinity,
    noDepth: true,
  };
  const state = { ...DEFAULTS, uses: new Set(DEFAULTS.uses) };
  const detailCache = new Map();

  // Whether a well passes the filters, by its use group, Hickory Aquifer
  // flag, highest tested yield and depth (null where none is reported): the
  // same test as the layers' filter (baseWhere), for the counts.
  function inRange(v, lo, hi, includeNull) {
    if (v === null || v === undefined) return includeNull;
    return v >= lo && v <= hi;
  }
  const passesBesidesUse = (hick, gpm, depth) =>
    (!state.hickoryOnly || Boolean(hick)) &&
    inRange(gpm, state.yieldLo, state.yieldHi, state.noYield) &&
    inRange(depth, state.depthLo, state.depthHi, state.noDepth);
  const passes = (use, hick, gpm, depth) => state.uses.has(use) && passesBesidesUse(hick, gpm, depth);

  const line = (color, size) => ({
    type: "line-3d",
    symbolLayers: [{ type: "line", material: { color }, size }],
  });
  const lineRenderer = (size) => ({
    type: "unique-value",
    field: "cls",
    defaultSymbol: line([...CLASS_COLORS[4], 1], size),
    uniqueValueInfos: [
      ...Object.entries(CLASS_COLORS).map(([cls, color]) => ({ value: Number(cls), symbol: line([...color, 1], size) })),
      { value: 6, symbol: line([...WATER, 0.45], size * 2.2) },
    ],
  });
  // A well head; a white ring marks a well the Groundwater Database assigns
  // to the Hickory Aquifer.
  const icon = (color, size, outline, ring) => ({
    type: "point-3d",
    symbolLayers: [
      {
        type: "icon",
        resource: { primitive: "circle" },
        material: { color },
        // The ring is lighter on the small heads drawn zoomed out.
        ...(ring
          ? { outline: { color: [255, 255, 255, 1], size: size >= 8 ? 2 : 1.25 } }
          : outline
            ? { outline: { color: [20, 21, 18, 1], size: 1 } }
            : {}),
        size: ring ? size + (size >= 8 ? 4 : 2.5) : size,
      },
    ],
  });
  const pointRenderer = (size) => ({
    type: "unique-value",
    field: "sym",
    defaultSymbol: icon([...CLASS_COLORS[5], 1], size, true),
    uniqueValueInfos: [
      ...Object.entries(CLASS_COLORS).map(([cls, color]) => ({ value: `h${cls}`, symbol: icon([...color, 1], size, true) })),
      ...Object.entries(CLASS_COLORS).map(([cls, color]) => ({
        value: `h${cls}k`,
        symbol: icon([...color, 1], size, true, true),
      })),
      // Water levels: small dots, off by default.
      { value: "lv", symbol: icon([...WATER, 0.9], 3, false) },
    ],
  });

  function popupContent({ graphic }) {
    const a = graphic.attributes;
    let pending = detailCache.get(a.cell);
    if (!pending) {
      pending = fetch(`${DATA}detail-${a.cell}.json`).then((r) => {
        if (!r.ok) throw new Error(`wells/detail-${a.cell}.json: HTTP ${r.status}`);
        return r.json();
      });
      detailCache.set(a.cell, pending);
    }
    return pending
      .then((records) => reportElement(a, records[a.uid], index.use_groups))
      .catch((error) => {
        console.error("the well report could not be loaded", error);
        detailCache.delete(a.cell);
        const p = document.createElement("p");
        p.textContent = "Sorry, this well's report could not be loaded.";
        return p;
      });
  }
  const popupTemplate = { title: "{title}", outFields: ["*"], content: popupContent };

  const SCHEMA = [
    { name: "ObjectID", type: "oid" },
    { name: "uid", type: "string" },
    { name: "cell", type: "string" },
    { name: "title", type: "string" },
    { name: "cls", type: "integer" },
    { name: "sym", type: "string" },
    { name: "hickory", type: "integer" },
    { name: "use", type: "integer" },
    { name: "yield", type: "double" },
    { name: "ytype", type: "string" },
    { name: "depth", type: "double" },
    { name: "wcls", type: "integer" },
    { name: "wtop", type: "double" },
    { name: "wbot", type: "double" },
    { name: "wbasis", type: "integer" },
  ];

  // The features of some wells: their heads at the ground, their lines down
  // the hole (one per rock class, and the water-bearing strata) and their
  // water levels. With down false, only the heads.
  function features(records, down = true) {
    const lines = [];
    const heads = [];
    const levels = [];
    let id = 1;
    for (const r of records) {
      const a = wellAttributes(r);
      const [, lon, lat, depth, segs, level, strata] = r;
      const at = (ft) => [lon, lat, -ft * FT * k];
      const attrs = (cls, sym) => ({
        ObjectID: id++, uid: a.uid, cell: a.cell, title: a.title, cls, sym, hickory: a.hickory, use: a.use,
        yield: a.yield, ytype: a.ytype, depth: a.depth, wcls: a.wcls, wtop: a.wtop, wbot: a.wbot, wbasis: a.wbasis,
      });
      heads.push(new Graphic({
        geometry: new Point({ longitude: lon, latitude: lat, z: 0, spatialReference: SpatialReference.WGS84 }),
        attributes: attrs(-1, `h${a.wcls}${a.hickory ? "k" : ""}`),
      }));
      if (!down) continue;
      const byClass = new Map();
      let covered = 0;
      for (const [top, bot, cls] of segs) {
        if (!byClass.has(cls)) byClass.set(cls, []);
        byClass.get(cls).push([at(top), at(bot)]);
        covered = Math.max(covered, bot);
      }
      if (depth) {
        if (!segs.length) {
          byClass.set(5, [[at(0), at(depth)]]);
        } else if (covered < depth) {
          if (!byClass.has(5)) byClass.set(5, []);
          byClass.get(5).push([at(covered), at(depth)]);
        }
      }
      for (const [cls, paths] of byClass) {
        lines.push(new Graphic({
          geometry: new Polyline({ hasZ: true, paths, spatialReference: SpatialReference.WGS84 }),
          attributes: attrs(cls, ""),
        }));
      }
      for (const [top, bot] of strata) {
        lines.push(new Graphic({
          geometry: new Polyline({ hasZ: true, paths: [[at(top), at(bot)]], spatialReference: SpatialReference.WGS84 }),
          attributes: attrs(6, ""),
        }));
      }
      if (level !== null) {
        levels.push(new Graphic({
          geometry: new Point({ longitude: lon, latitude: lat, z: -level * FT * k, spatialReference: SpatialReference.WGS84 }),
          attributes: attrs(-1, "lv"),
        }));
      }
    }
    return { lines, heads, levels };
  }

  // The filter shared by every well layer.
  function rangeWhere(field, lo, hi, includeNull) {
    const range = [`${field} IS NOT NULL`];
    if (lo > 0) range.push(`${field} >= ${lo}`);
    if (Number.isFinite(hi)) range.push(`${field} <= ${hi}`);
    const known = `(${range.join(" AND ")})`;
    return includeNull ? `(${known} OR ${field} IS NULL)` : known;
  }
  function baseWhere() {
    const parts = [`use IN (${[...state.uses].join(",") || "-1"})`];
    if (state.hickoryOnly) parts.push("hickory = 1");
    parts.push(rangeWhere("yield", state.yieldLo, state.yieldHi, state.noYield));
    parts.push(rangeWhere("depth", state.depthLo, state.depthHi, state.noDepth));
    return parts.join(" AND ");
  }
  const lineWhere = () => baseWhere() + (state.water ? "" : " AND cls < 6");
  const pointWhere = () => baseWhere() + (state.water ? "" : " AND sym <> 'lv'");

  const common = {
    fields: SCHEMA,
    objectIdField: "ObjectID",
    hasZ: true,
    spatialReference: SpatialReference.WGS84,
    elevationInfo: { mode: "relative-to-ground" },
    popupTemplate,
  };
  const lineLayer = (source, size) =>
    new FeatureLayer({
      ...common,
      title: "Wells (TWDB reports)",
      source,
      geometryType: "polyline",
      renderer: lineRenderer(size),
      definitionExpression: lineWhere(),
    });
  const pointLayer = (source, size, title) =>
    new FeatureLayer({
      ...common,
      title,
      source,
      geometryType: "point",
      screenSizePerspectiveEnabled: false,
      renderer: pointRenderer(size),
      definitionExpression: pointWhere(),
    });

  const ALL_SCALE = opts.allScale;
  const LINES_SCALE = opts.linesScale;
  // The cap on the tiles whose lines are drawn keeps a phone or a wide tilted
  // view smooth.
  const MAX_TILES = small ? 6 : 16;
  // Heads: zoomed far out as big as the overview's, smaller from the
  // district's scale in where every well that passes may be drawn, bigger
  // again with the lines.
  const HEAD_OVERVIEW = 6;
  const HEAD_FAR = 4;
  const HEAD_NEAR = 8;
  const headSizeFor = (scale) => (scale <= LINES_SCALE ? HEAD_NEAR : scale <= ALL_SCALE ? HEAD_FAR : HEAD_OVERVIEW);
  const insertAt = () => (opts.insertAt ? opts.insertAt() : undefined);
  const onNote = opts.onNote || (() => {});
  // "overview" (the thinned overview), "heads" (the head of every well that
  // passes, with the overview's lines) or "lines" (and the lines near the
  // middle of the view).
  let mode = "";
  // How many wells pass the filters, of every well in the data.
  let shown = counts().shown;
  // Zoomed far out with more wells passing than FAR_HEADS_MAX: the thinned
  // overview, not every head.
  const thinned = () => !(view.scale <= ALL_SCALE) && shown > FAR_HEADS_MAX;
  // The overview's wells that pass the filters, which it draws.
  const overviewShown = () => index.overview.filter((r) => passes(r[9], r[7], r[14], r[3])).length;
  // The note: the mode, as above; loading or failed (the heads files; the
  // overview is drawn meanwhile); left (lines mode: the wells that pass, in
  // view, with only their heads drawn); shown; drawn (the wells whose heads
  // are drawn).
  let note = { mode: "", left: 0, shown, drawn: 0 };
  const tell = (next) => {
    note = { left: 0, ...next, shown, drawn: next.mode === "overview" ? overviewShown() : shown };
    onNote(note);
  };

  // The thinned overview: its lines (also drawn under every well's head
  // until the lines near the middle of the view take over) and its heads.
  let overview = null;
  function makeOverview() {
    const f = features(index.overview);
    overview = {
      lines: lineLayer(f.lines, 2.5),
      points: pointLayer([...f.heads, ...f.levels], 6, "Well heads (TWDB reports, one per cell)"),
    };
    map.addMany([overview.lines, overview.points], insertAt());
  }
  function dropOverview() {
    map.removeMany([overview.lines, overview.points]);
    overview = null;
  }

  // The tiles, each fetched once.
  const tileData = new Map();
  function loadTile(key) {
    let p = tileData.get(key);
    if (!p) {
      p = fetch(`${DATA}draw-${key}.json`).then((r) => {
        if (!r.ok) throw new Error(`wells/draw-${key}.json: HTTP ${r.status}`);
        return r.json();
      });
      tileData.set(key, p);
      p.catch(() => tileData.delete(key));
    }
    return p;
  }

  // A file of the wells' data, tried twice.
  const fetchJson = (name) => {
    const once = () =>
      fetch(`${DATA}${name}`).then((r) => {
        if (!r.ok) throw new Error(`wells/${name}: HTTP ${r.status}`);
        return r.json();
      });
    return once().catch(once);
  };

  // Every well's head record, read once from the heads files (a quarter of
  // the tiles' bytes, without the logs), as drawing records without lines.
  let headRecords = null;
  // Every well's [tile, use group, Hickory, yield, depth], for the filters.
  let headKeys = [];
  let recordsLoading = null;
  function loadHeadRecords() {
    if (!recordsLoading) {
      recordsLoading = Promise.all(index.heads.files.map(fetchJson)).then((files) => {
        const td = index.tile_degrees;
        const records = files.flat().map((h) => {
          const a = headAttributes(h, index.detail_degrees);
          return [a.uid, a.lon, a.lat, a.depth, [], null, [], a.hickory, a.cell, a.use, a.wcls, a.wtop, a.wbot, a.wbasis, a.yield, a.ytype];
        });
        headKeys = records.map((r) => [`${Math.floor(r[1] / td)}_${Math.floor(r[2] / td)}`, r[9], r[7], r[14], r[3]]);
        headRecords = records;
        return records;
      });
      recordsLoading.catch(() => {
        recordsLoading = null;
      });
    }
    return recordsLoading;
  }

  // A layer of wells' heads, drawn filtered. A scene draws only so many
  // features of a layer; these draw all of theirs.
  let headSize = HEAD_FAR;
  function headLayer(records) {
    const f = features(records, false);
    const layer = pointLayer(f.heads, headSize, "Well heads (TWDB reports)");
    layer.visible = false;
    map.add(layer, insertAt());
    view
      .whenLayerView(layer)
      .then((layerView) => {
        if ("maximumNumberOfFeatures" in layerView) {
          layerView.maximumNumberOfFeatures = Math.max(layerView.maximumNumberOfFeatures, f.heads.length);
        }
      })
      .catch((error) => console.error("the wells' heads could not be drawn", error));
    return layer;
  }
  // The heads drawn: every well's, in one layer made once when more than
  // FAR_HEADS_MAX pass; until then only those that pass, in a small layer
  // made again only when the filters let in a well it lacks (a phone makes
  // a few hundred features at once, not every well's). Once every well's
  // layer is made, it alone is used.
  let heads = null;
  let few = null; // { layer, ids: the indices of its wells in headRecords }
  let active = null;
  function chooseHeads() {
    if (!heads && shown <= FAR_HEADS_MAX) {
      const ids = [];
      headKeys.forEach(([, use, hick, gpm, depth], i) => {
        if (passes(use, hick, gpm, depth)) ids.push(i);
      });
      if (!few || !ids.every((i) => few.ids.has(i))) {
        const old = few;
        few = { layer: headLayer(ids.map((i) => headRecords[i])), ids: new Set(ids) };
        // The old layer goes once the new one is drawn: no gap between.
        if (old) {
          view
            .whenLayerView(few.layer)
            .then((layerView) => reactiveUtils.whenOnce(() => !layerView.updating))
            .catch(() => {})
            .finally(() => map.remove(old.layer));
        }
      }
      active = few.layer;
    } else {
      if (!heads) {
        heads = headLayer(headRecords);
        if (few) map.remove(few.layer);
        few = null;
      }
      active = heads;
    }
    return active;
  }

  // The lines of the wells in the tiles near the middle of the view, by tile:
  // [lines, water levels].
  const loaded = new Map();
  function dropLines(keep = []) {
    for (const [key, layers] of loaded) {
      if (!keep.includes(key)) {
        map.removeMany(layers);
        loaded.delete(key);
      }
    }
  }

  // The tiles in view, nearest the middle of the view first.
  function tilesInView() {
    const center = view.center;
    const extent = view.extent;
    if (!center || !extent) return [];
    const lon = center.longitude;
    const lat = center.latitude;
    const box = extent.spatialReference.isWGS84
      ? extent
      : { xmin: -180, ymin: -90, xmax: 180, ymax: 90 };
    const geo = extent.spatialReference.isWebMercator
      ? {
        xmin: (extent.xmin / 6378137) * (180 / Math.PI),
        xmax: (extent.xmax / 6378137) * (180 / Math.PI),
        ymin: (Math.atan(Math.sinh(extent.ymin / 6378137)) * 180) / Math.PI,
        ymax: (Math.atan(Math.sinh(extent.ymax / 6378137)) * 180) / Math.PI,
      }
      : box;
    return Object.entries(index.tiles)
      .filter(([, t]) => t.bbox[2] >= geo.xmin && t.bbox[0] <= geo.xmax && t.bbox[3] >= geo.ymin && t.bbox[1] <= geo.ymax)
      .map(([key, t]) => {
        const cx = Math.max(t.bbox[0], Math.min(lon, t.bbox[2]));
        const cy = Math.max(t.bbox[1], Math.min(lat, t.bbox[3]));
        return [key, Math.hypot((cx - lon) * Math.cos((lat * Math.PI) / 180), cy - lat), t.count];
      })
      .sort((a, b) => a[1] - b[1]);
  }

  // What each layer shows, by the mode and the switches.
  function show() {
    if (overview) {
      overview.lines.visible = state.on && mode !== "lines";
      overview.points.visible = state.on && mode === "overview";
    }
    for (const layer of [heads, few?.layer]) {
      if (layer) layer.visible = state.on && mode !== "overview" && layer === active;
    }
    for (const [lines, levels] of loaded.values()) {
      lines.visible = state.on;
      levels.visible = state.on && state.water;
    }
  }

  // The thinned overview alone (extra: loading or failed, for the note).
  function overviewOnly(extra = {}) {
    dropLines();
    if (!overview) makeOverview();
    mode = "overview";
    show();
    tell({ mode, ...extra });
  }

  // One step: the layers for the view's scale and middle, and the filters.
  async function step() {
    const scale = view.scale;
    if (!view.center || !Number.isFinite(scale)) return;
    if (thinned()) {
      overviewOnly();
      return;
    }
    // The overview, while the wells' heads load.
    if (!headRecords) overviewOnly({ loading: true });
    try {
      await loadHeadRecords();
    } catch (error) {
      // The overview stays: it is better than nothing.
      console.error("every well's head could not be loaded", error);
      overviewOnly({ failed: true });
      return;
    }
    // The view or the filters may have changed while the heads loaded.
    if (thinned()) {
      overviewOnly();
      return;
    }
    const size = headSizeFor(view.scale);
    if (size !== headSize) {
      headSize = size;
      for (const layer of [heads, few?.layer]) {
        if (layer) layer.renderer = pointRenderer(size);
      }
    }
    chooseHeads();
    if (!(view.scale <= LINES_SCALE)) {
      dropLines();
      if (!overview) makeOverview();
      mode = "heads";
      show();
      tell({ mode });
      return;
    }
    if (overview) dropOverview();
    mode = "lines";
    const inView = tilesInView();
    const wanted = inView.slice(0, MAX_TILES).map(([key]) => key);
    // The wells that pass, in the tiles in view past the cap.
    const rest = new Set(inView.slice(MAX_TILES).map(([key]) => key));
    let left = 0;
    if (rest.size) {
      for (const [tile, use, hick, gpm, depth] of headKeys) {
        if (rest.has(tile) && passes(use, hick, gpm, depth)) left += 1;
      }
    }
    dropLines(wanted);
    for (const key of wanted) {
      if (loaded.has(key)) continue;
      try {
        const f = features(await loadTile(key));
        const layers = [lineLayer(f.lines, 3.5), pointLayer(f.levels, 3, "Water levels (TWDB reports)")];
        loaded.set(key, layers);
        map.addMany(layers, insertAt());
      } catch (error) {
        console.error("a well tile could not be loaded", error);
      }
    }
    show();
    tell({ mode, left });
  }

  // Steps run one at a time; a move while one runs runs one more after it.
  let running = null;
  let again = false;
  function update() {
    if (running) {
      again = true;
      return running;
    }
    running = (async () => {
      do {
        again = false;
        await step();
      } while (again);
    })()
      .catch((error) => console.error("the wells could not be drawn", error))
      .finally(() => {
        running = null;
      });
    return running;
  }

  function refilter() {
    const layers = [overview?.lines, overview?.points, heads, few?.layer].filter(Boolean);
    for (const layer of layers) {
      layer.definitionExpression = layer.geometryType === "point" ? pointWhere() : lineWhere();
    }
    for (const [lines, levels] of loaded.values()) {
      lines.definitionExpression = lineWhere();
      levels.definitionExpression = baseWhere();
    }
    show();
    // Zoomed far out, how many pass picks every head or the thinned
    // overview; and the note gives the counts.
    update();
  }
  // The lines and water levels depend on the exaggeration; the heads do not.
  function rebuild() {
    if (overview) {
      dropOverview();
      makeOverview();
    }
    dropLines();
    show();
    update();
  }

  // Counts over every well in the data, not only the tiles on screen.
  function counts() {
    const out = { shown: 0, byUse: index.use_groups.map(() => 0) };
    for (const [use, hick, gpm, depth] of index.filter_keys) {
      if (!passesBesidesUse(hick, gpm, depth)) continue;
      out.byUse[use] += 1;
      if (state.uses.has(use)) out.shown += 1;
    }
    return out;
  }

  // Opens a well's report from its drawing record (a vineyard's list of the
  // wells near it), whether or not its tile is loaded.
  function openWell(record) {
    const a = wellAttributes(record);
    const point = new Point({ longitude: a.lon, latitude: a.lat, z: 0, spatialReference: SpatialReference.WGS84 });
    const graphic = new Graphic({ geometry: point, attributes: a, popupTemplate });
    return view
      .goTo({ target: point, scale: Math.min(view.scale, 20000) }, { animate: !opts.reducedMotion, duration: 1500 })
      .catch((error) => {
        if (error.name !== "AbortError") console.error("the camera could not move", error);
      })
      .then(() => view.openPopup({ features: [graphic], location: point }));
  }

  reactiveUtils.watch(
    () => view.stationary,
    (stationary) => {
      if (stationary) update();
    },
  );
  // The first step draws the overview at once; the heads files, when the
  // filters and the scale want them, load after it without holding up the
  // page (its note says so).
  update();

  return {
    index,
    counts,
    defaults: DEFAULTS,
    openWell,
    note: () => note,
    // The layer of the wells' heads in use, once loaded (for the tests).
    heads: () => active,
    update,
    setExaggeration(value) {
      k = value;
      rebuild();
    },
    setVisible(on) {
      state.on = on;
      show();
    },
    setWater(on) {
      state.water = on;
      refilter();
    },
    setFilter(patch) {
      Object.assign(state, patch);
      const out = counts();
      shown = out.shown;
      refilter();
      return out;
    },
  };
}

// ---- The raw report, as an element.

const SECTIONS = [
  ["Lithology", "Lithology (as logged)", ["TopDepth", "BottomDepth", "LithologyDescription"]],
  ["BoreHole", "Bore hole", ["Diameter", "TopDepth", "BottomDepth"]],
  ["Casing", "Casing", null],
  ["WaterStrata", "Water-bearing strata", ["TopDepth", "BottomDepth", "WaterType"]],
  ["WaterLevels", "Water levels", null],
  ["WellTests", "Well tests", null],
];

function el(tag, text) {
  const e = document.createElement(tag);
  if (text !== undefined && text !== null) e.textContent = String(text);
  return e;
}

function table(rows, columns) {
  const cols = columns || [...new Set(rows.flatMap((r) => Object.keys(r)))];
  const t = el("table");
  t.style.cssText = "border-collapse:collapse;font-size:12px;margin:.3rem 0 .8rem;width:100%";
  const head = el("tr");
  for (const c of cols) {
    const th = el("th", c);
    th.style.cssText = "text-align:left;padding:2px 6px;border-bottom:1px solid #666;font-weight:600";
    head.append(th);
  }
  t.append(head);
  for (const r of rows) {
    const tr = el("tr");
    for (const c of cols) {
      const td = el("td", r[c] ?? "");
      td.style.cssText = "padding:2px 6px;vertical-align:top;border-bottom:1px solid #3334";
      tr.append(td);
    }
    t.append(tr);
  }
  return t;
}

function fields(record) {
  const t = el("table");
  t.style.cssText = "border-collapse:collapse;font-size:12px;margin:.2rem 0 .8rem;width:100%";
  for (const [key, value] of Object.entries(record)) {
    if (typeof value !== "string" || value === "") continue;
    const tr = el("tr");
    const th = el("th", key);
    th.style.cssText = "text-align:left;padding:2px 6px;font-weight:500;opacity:.75;vertical-align:top;width:45%";
    const td = el("td", value);
    td.style.cssText = "padding:2px 6px;vertical-align:top";
    tr.append(th, td);
    t.append(tr);
  }
  return t;
}

function link(href, text) {
  const a = el("a", text);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

const fmt = (v) => Number(v).toLocaleString("en-US");

// The few facts about a well a list or a popup starts with.
export function wellSummary(a, useGroups) {
  return [
    a.wbasis === 2
      ? "Water from: not known (no log)"
      : `Water from: ${CLASS_NAMES[a.wcls]} (interval ${fmt(a.wtop)}–${fmt(a.wbot)} ft, ${BASIS[a.wbasis]})`,
    a.depth ? `Depth: ${fmt(a.depth)} ft (from the report)` : "Depth: none reported",
    a.yield === null || a.yield === undefined
      ? "Highest tested yield: none reported"
      : `Highest tested yield: ${fmt(a.yield)} gpm${a.ytype ? ` (${a.ytype})` : ""}`,
    `Use group: ${useGroups[a.use]}`,
  ];
}

function reportElement(a, record, useGroups) {
  const box = el("div");
  box.style.cssText = "font-size:12px;line-height:1.45";
  const [water, ...rest] = wellSummary(a, useGroups);
  const first = el("p");
  const swatch = el("span");
  const c = CLASS_COLORS[a.wcls] || CLASS_COLORS[5];
  swatch.style.cssText = `display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;background:rgb(${c.join(",")})`;
  first.append(swatch, document.createTextNode(water));
  box.append(first);
  for (const text of rest) box.append(el("p", text));
  if (!record) {
    box.append(el("p", "No report found for this well."));
    return box;
  }
  const num = a.uid.slice(1);
  const links = el("p");
  if (a.uid[0] === "S") {
    links.append(link(`${REPORT}?Num=${encodeURIComponent(num)}&Type=SDR-Well`, "TWDB's well report"));
    for (const p of record.PluggingReports || []) {
      links.append(document.createTextNode(" · "));
      links.append(link(`${REPORT}?Num=${encodeURIComponent(p.PluggingReportTrackingNumber)}&Type=SDR-Plug`, "plugging report"));
    }
  } else {
    links.append(link(`${REPORT}?Num=${encodeURIComponent(num)}&Type=GWDB`, "TWDB's well record"));
  }
  links.append(el("span", " (TWDB's own pages show the names left out here.)"));
  box.append(links);
  box.append(el("p", "As reported to TWDB, every field that holds something. Owners', drillers', pluggers' and companies' names, addresses and licence numbers are left out; any note that could name someone is blank, and words in the log that could are marked [removed]."));
  box.append(el("h4", a.uid[0] === "S" ? "Driller's report (TWDB SDR)" : "Groundwater Database (TWDB GWDB)"));
  box.append(fields(record));
  for (const [key, label, cols] of SECTIONS) {
    const rows = record[key];
    if (rows && rows.length) {
      box.append(el("h4", label));
      box.append(table(rows, cols));
    }
  }
  for (const p of record.PluggingReports || []) {
    box.append(el("h4", `Plugging report ${p.PluggingReportTrackingNumber}`));
    box.append(fields(p));
    if (p.PlugRanges && p.PlugRanges.length) box.append(table(p.PlugRanges));
  }
  for (const g of record.GWDB || []) {
    box.append(el("h4", `Groundwater Database well ${g.StateWellNumber}`));
    box.append(fields(g));
    for (const [key, label, cols] of SECTIONS) {
      const rows = g[key];
      if (rows && rows.length) {
        box.append(el("h4", label));
        box.append(table(rows, cols));
      }
    }
  }
  for (const h of box.querySelectorAll("h4")) {
    h.style.cssText = "margin:.6rem 0 .1rem;font-size:12px;letter-spacing:.06em;text-transform:uppercase;opacity:.8";
  }
  return box;
}
