// The Hickory Aquifer in 3D (aquifer.html, #135): the whole aquifer as
// TWDB's Llano Uplift groundwater model draws it, under a see-through ground,
// with TWDB's well reports, the vineyards, the proposed district, TTB's
// proposed Llano Uplift AVA, the counties and towns.
//
// The data is assets/aquifer/ (made by src/site/make_aquifer_3d.py) and the
// district is data/boundary.geojson. The aquifer's body is built here from
// blocks of 2 x 2 (half a mile, large screens) or 4 x 4 (a mile, phones)
// model cells, each from its bottom to its top, with walls only where a
// neighbour is missing or steps up or down. Heights are metres above sea level
// times the vertical exaggeration, and the ground's elevation is multiplied by
// the same factor, so depths below the ground keep their proportions. When
// Esri's ground cannot be loaded, the ground is flat and every height is drawn
// from the model's own ground instead; when the basemap cannot be loaded, the
// layers are drawn on the page's background. Every figure the page shows is
// read from assets/aquifer/stats.json. Text from the data is only ever set as
// text, never parsed as HTML.
import { apiKey } from "./map-config.js";
import { setupWells, wellAttributes, CLASS_NAMES, FAR_HEADS_MAX } from "./aquifer-wells.js";

const DATA = "assets/aquifer/";
document.documentElement.classList.add("js");

const setText = (id, text) => {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = text;
  }
};
const status = document.getElementById("aq-status");
const notes = new Map();
// The status line under the view: what is loading, and what failed.
function say(key, text) {
  if (text) {
    notes.set(key, text);
  } else {
    notes.delete(key);
  }
  if (status) {
    status.textContent = [...notes.values()].join(" ");
  }
}

async function json(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${path}: HTTP ${response.status}`);
  }
  return response.json();
}

// ---- The figures: every element marked data-stat gets its text from
// stats.json, in the format its data-format names.
const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];
const FORMATS = {
  int: (v) => Math.round(v).toLocaleString("en-US"),
  pct: (v) => `${Math.round(v * 100)}%`,
  num: (v) => v.toLocaleString("en-US"),
  deg: (v) => `${v < 0 ? "−" : "+"}${Math.abs(v)}°`,
  scale: (v) => `1:${Math.round(v).toLocaleString("en-US")}`,
  date: (v) => {
    const [y, m, d] = v.split("-").map(Number);
    return `${MONTHS[m - 1]} ${d}, ${y}`;
  },
};
export function formatStat(value, format) {
  const f = FORMATS[format || "int"];
  if (!f || value === undefined || value === null) {
    throw new Error(`no figure ${value} in format ${format}`);
  }
  return f(value);
}
let stats = {};
try {
  stats = (await json(`${DATA}stats.json`)).figures;
  for (const element of document.querySelectorAll("[data-stat]")) {
    element.textContent = formatStat(stats[element.dataset.stat], element.dataset.format);
  }
} catch (error) {
  console.error("the page's figures could not be loaded", error);
}

let EsriModules;
try {
  EsriModules = await $arcgis.import([
    "@arcgis/core/config.js",
    "@arcgis/core/Map.js",
    "@arcgis/core/Basemap.js",
    "@arcgis/core/Ground.js",
    "@arcgis/core/layers/ElevationLayer.js",
    "@arcgis/core/layers/BaseElevationLayer.js",
    "@arcgis/core/layers/GeoJSONLayer.js",
    "@arcgis/core/layers/FeatureLayer.js",
    "@arcgis/core/layers/GraphicsLayer.js",
    "@arcgis/core/Graphic.js",
    "@arcgis/core/geometry/Polyline.js",
    "@arcgis/core/geometry/Mesh.js",
    "@arcgis/core/geometry/support/MeshComponent.js",
    "@arcgis/core/geometry/support/MeshMaterial.js",
    "@arcgis/core/geometry/SpatialReference.js",
    "@arcgis/core/geometry/Point.js",
    "@arcgis/core/Camera.js",
    "@arcgis/core/core/reactiveUtils.js",
    "@arcgis/core/popup/content/CustomContent.js",
  ]);
} catch (error) {
  // No SDK (blocked, or offline): the page keeps its text and its note.
  console.error("Esri's map library could not be loaded", error);
  document.documentElement.classList.remove("js");
  throw error;
}
const [
  config,
  EsriMap,
  Basemap,
  Ground,
  ElevationLayer,
  BaseElevationLayer,
  GeoJSONLayer,
  FeatureLayer,
  GraphicsLayer,
  Graphic,
  Polyline,
  Mesh,
  MeshComponent,
  MeshMaterial,
  SpatialReference,
  Point,
  Camera,
  reactiveUtils,
  CustomContent,
] = EsriModules;

const SAND = [199, 151, 111];
const BONE = [238, 232, 219];
const MUTED = [185, 175, 161];
const INK = [20, 21, 18];
const GRANITE = [150, 116, 112];
const WATER_SIDE = [96, 138, 160, 1];
const WATER_TOP = [52, 98, 124, 1];
// See-through, so vineyards and well heads at the surface are never hidden
// where the model's ground sits a little above the real one.
const WATER_OUTCROP = [134, 184, 206, 0.5];
const WATER_OUTSIDE = [150, 178, 190, 0.45];
const WINE = [176, 82, 104];
const MEMBER = [122, 88, 58];
const FT = 0.304800609601219; // metres per US survey foot
const TERRAIN =
  "https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer";
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
// Phones and small screens get the 4 x 4 blocks (a quarter of the faces).
const small = matchMedia("(max-width: 900px), (pointer: coarse)").matches;

if (apiKey) {
  config.apiKey = apiKey;
}

say("load", "Loading the model…");

// Esri's ground, if it loads: its elevation times the vertical exaggeration.
const ExaggeratedElevation = BaseElevationLayer.createSubclass({
  properties: { exaggeration: 1, source: null },
  load() {
    this.addResolvingPromise(
      this.source.load().then(() => {
        this.tileInfo = this.source.tileInfo;
        this.spatialReference = this.source.spatialReference;
        this.fullExtent = this.source.fullExtent;
      }),
    );
    return this;
  },
  fetchTile(level, row, col, options) {
    return this.source.fetchTile(level, row, col, options).then((data) => {
      const k = this.exaggeration;
      for (let i = 0; i < data.values.length; i++) {
        if (data.values[i] !== data.noDataValue) {
          data.values[i] *= k;
        }
      }
      return data;
    });
  },
});

async function loadTerrain() {
  const terrain = new ElevationLayer({ url: TERRAIN });
  try {
    await terrain.load();
    return terrain;
  } catch (error) {
    console.warn("Esri's ground elevation could not be loaded", error);
    return null;
  }
}

let model;
let terrain;
try {
  [model, terrain] = await Promise.all([
    json(`${DATA}${small ? "hickory-k4.json" : "hickory-k2.json"}`),
    loadTerrain(),
  ]);
} catch (error) {
  // Without the model there is no aquifer to draw: say so, not "Loading".
  console.error("the model could not be loaded", error);
  say("load", "Sorry, the model could not be loaded, so the 3D view cannot be drawn. Please reload the page.");
  throw error;
}
// Without Esri's ground, the ground is flat at 0 and every height is drawn
// from the model's own ground, so wells and the aquifer still meet.
const flat = terrain === null;
if (flat) {
  say("ground", "Esri’s ground elevation could not be loaded, so the ground is drawn flat and the aquifer at its depth below the model’s own ground.");
}

// ---- The aquifer: a block's corners come from the polynomial in the data
// (model row and column to longitude and latitude).
const poly = model.polynomial;
function terms(u, v, degree) {
  const t = [];
  for (let n = 0; n <= degree; n++) {
    for (let j = 0; j <= n; j++) {
      t.push(u ** (n - j) * v ** j);
    }
  }
  return t;
}
const corners = new Map();
function corner(i, j) {
  const key = i * 100000 + j;
  let at = corners.get(key);
  if (!at) {
    const kc = model.block_cells;
    const t = terms((j * kc - 0.5 - poly.col_c) / poly.col_s, (i * kc - 0.5 - poly.row_c) / poly.row_s, poly.degree);
    const dot = (c) => c.reduce((s, x, n) => s + x * t[n], 0);
    at = [dot(poly.lon), dot(poly.lat)];
    corners.set(key, at);
  }
  return at;
}

// The aquifer as four meshes, so each can be switched on and off: its top
// where it lies under younger rock, its top where most of the block is model
// outcrop, its sides and base, and the blocks outside TWDB's outline.
function aquiferMesh(k) {
  const byKey = new Map();
  for (const cell of model.cells) {
    byKey.set(cell[0] * 100000 + cell[1], cell);
  }
  const parts = {
    top: { position: [], faces: [], n: 0 },
    outcrop: { position: [], faces: [], n: 0 },
    side: { position: [], faces: [], n: 0 },
    outside: { position: [], faces: [], n: 0 },
  };
  const quad = (part, a, b, c, d, za, zb, zc, zd) => {
    const n = part.n;
    part.position.push(a[0], a[1], za, b[0], b[1], zb, c[0], c[1], zc, d[0], d[1], zd);
    part.faces.push(n, n + 1, n + 2, n, n + 2, n + 3);
    part.n += 4;
  };
  for (const [r, c, top, bot, atSurface, outside, ground] of model.cells) {
    const base = flat ? ground : 0;
    const z = (m) => (m - base) * k;
    const sides = outside ? parts.outside : parts.side;
    const wall = (a, b, z0, z1) => {
      if (z1 > z0) {
        quad(sides, b, a, a, b, z(z0), z(z0), z(z1), z(z1));
      }
    };
    const p00 = corner(r, c);
    const p01 = corner(r, c + 1);
    const p11 = corner(r + 1, c + 1);
    const p10 = corner(r + 1, c);
    const topPart = outside ? parts.outside : atSurface ? parts.outcrop : parts.top;
    // Faces wind so their normals point out of the block (rows run
    // south-west, columns south-east), which the lighting needs.
    quad(topPart, p00, p10, p11, p01, z(top), z(top), z(top), z(top));
    quad(sides, p00, p01, p11, p10, z(bot), z(bot), z(bot), z(bot));
    const around = [
      [r - 1, c, p00, p01],
      [r, c + 1, p01, p11],
      [r + 1, c, p11, p10],
      [r, c - 1, p10, p00],
    ];
    for (const [nr, ncol, a, b] of around) {
      const other = byKey.get(nr * 100000 + ncol);
      if (!other) {
        wall(a, b, bot, top);
        continue;
      }
      if (top > other[2]) {
        wall(a, b, Math.max(other[2], bot), top);
      }
      if (bot < other[3]) {
        wall(a, b, bot, Math.min(other[3], top));
      }
    }
  }
  const mesh = (part, color) =>
    new Mesh({
      vertexAttributes: { position: new Float64Array(part.position) },
      components: [
        new MeshComponent({
          faces: new Uint32Array(part.faces),
          material: new MeshMaterial({ color, doubleSided: true }),
          shading: "flat",
        }),
      ],
      spatialReference: SpatialReference.WGS84,
    });
  return {
    top: mesh(parts.top, WATER_TOP),
    outcrop: mesh(parts.outcrop, WATER_OUTCROP),
    side: mesh(parts.side, WATER_SIDE),
    outside: mesh(parts.outside, WATER_OUTSIDE),
  };
}

const meshSymbol = { type: "mesh-3d", symbolLayers: [{ type: "fill" }] };
const aquifer = {
  top: new Graphic({ symbol: meshSymbol }),
  outcrop: new Graphic({ symbol: meshSymbol }),
  side: new Graphic({ symbol: meshSymbol }),
  outside: new Graphic({ symbol: meshSymbol }),
};

// ---- The layers on the ground.
const textSymbol = (size, color) => ({
  type: "label-3d",
  symbolLayers: [
    {
      type: "text",
      material: { color },
      halo: { color: [...INK, 0.85], size: 1.2 },
      size,
      font: { family: "Noto Sans", weight: "bold" },
    },
  ],
});
// A label with fixed text, for an outline.
const fixedLabel = (text, color) => [
  {
    labelExpressionInfo: { expression: JSON.stringify(text) },
    labelPlacement: "always-horizontal",
    symbol: textSymbol(11, color),
  },
];

const fillLayer = (url, title, color, options = {}) =>
  new GeoJSONLayer({
    url,
    title,
    geometryType: "polygon",
    elevationInfo: { mode: "on-the-ground" },
    popupEnabled: false,
    renderer: {
      type: "simple",
      symbol: { type: "polygon-3d", symbolLayers: [{ type: "fill", material: { color }, ...options }] },
    },
  });

const lineLayer = (title, kind, color, size) =>
  new GeoJSONLayer({
    url: `${DATA}context.geojson`,
    title,
    definitionExpression: `kind = '${kind}'`,
    geometryType: "polyline",
    elevationInfo: { mode: "on-the-ground" },
    popupEnabled: false,
    renderer: {
      type: "simple",
      symbol: { type: "line-3d", symbolLayers: [{ type: "line", material: { color }, size }] },
    },
  });

const precambrianBuried = fillLayer(
  `${DATA}precambrian-buried.geojson`,
  "Precambrian rock under younger rock; no Hickory Aquifer in the model",
  [104, 76, 72, 0.85],
);
const precambrian = fillLayer(
  `${DATA}precambrian.geojson`,
  "Precambrian rock at the surface (TWDB model layer 8)",
  [...GRANITE, 0.75],
);
precambrian.labelingInfo = fixedLabel("Precambrian rock at the surface: no Hickory Aquifer in the model", BONE);
const outcrop = new GeoJSONLayer({
  url: `${DATA}context.geojson`,
  definitionExpression: "kind = 'outcrop'",
  geometryType: "polygon",
  title: "TWDB 2017 Hickory outcrop (shifted)",
  elevationInfo: { mode: "on-the-ground" },
  popupEnabled: false,
  renderer: {
    type: "simple",
    symbol: { type: "polygon-3d", symbolLayers: [{ type: "fill", material: { color: [141, 180, 199, 0.6] } }] },
  },
});
const counties = lineLayer("County lines (Census 2023)", "county", [...MUTED, 0.55], 1);
const llanoUplift = new GeoJSONLayer({
  url: `${DATA}llano-uplift.geojson`,
  title: "Llano Uplift AVA (proposed, TTB)",
  geometryType: "polygon",
  elevationInfo: { mode: "on-the-ground" },
  popupEnabled: false,
  labelingInfo: fixedLabel("Llano Uplift AVA (proposed, TTB)", BONE),
  renderer: {
    type: "simple",
    symbol: {
      type: "polygon-3d",
      symbolLayers: [
        {
          type: "fill",
          material: { color: [0, 0, 0, 0] },
          outline: { color: BONE, size: 2, pattern: { type: "style", style: "long-dash" } },
        },
      ],
    },
  },
});
const district = new GeoJSONLayer({
  url: "data/boundary.geojson",
  title: "Hickory Sands District (proposed revision)",
  geometryType: "polygon",
  elevationInfo: { mode: "on-the-ground" },
  popupEnabled: false,
  labelingInfo: fixedLabel("Hickory Sands District (proposed)", SAND),
  renderer: {
    type: "simple",
    symbol: {
      type: "polygon-3d",
      symbolLayers: [{ type: "fill", material: { color: [...SAND, 0.08] }, outline: { color: SAND, size: 2.5 } }],
    },
  },
});
const towns = new GeoJSONLayer({
  url: `${DATA}context.geojson`,
  title: "Towns (Census 2023)",
  definitionExpression: "kind = 'town'",
  geometryType: "point",
  outFields: ["name"],
  popupEnabled: false,
  elevationInfo: { mode: "relative-to-ground" },
  screenSizePerspectiveEnabled: false,
  renderer: {
    type: "simple",
    symbol: {
      type: "point-3d",
      symbolLayers: [
        {
          type: "icon",
          resource: { primitive: "circle" },
          material: { color: BONE },
          outline: { color: [...INK, 1], size: 1 },
          size: 7,
        },
      ],
    },
  },
  labelingInfo: [
    {
      labelExpressionInfo: { expression: "$feature.name" },
      labelPlacement: "above-center",
      symbol: textSymbol(12, BONE),
    },
  ],
});
// The Hickory Sandstone Member formation at the surface: the USGS geologic
// map, shifted onto the outcrops (the repository's resources/geology).
const member = fillLayer(
  `${DATA}hickory-member.geojson`,
  "Hickory Sandstone Member formation (USGS geologic map, shifted)",
  [...MEMBER, 0.85],
);

// ---- The vineyards, each with the wells near it.
let wells = null;
let nearWells = null;
function loadNear() {
  if (!nearWells) {
    nearWells = json(`${DATA}vineyard-wells.json`).catch((error) => {
      nearWells = null;
      throw error;
    });
  }
  return nearWells;
}
function nearList(vid) {
  const box = document.createElement("div");
  box.style.cssText = "font-size:12px;line-height:1.45;margin-top:.5rem";
  const busy = document.createElement("p");
  busy.textContent = "Finding the wells near this block…";
  box.append(busy);
  loadNear()
    .then((data) => {
      const found = data.vineyards[vid] || [];
      const metres = Number(data.radius_m).toLocaleString("en-US");
      const head = document.createElement("p");
      head.style.cssText = "font-weight:600;margin:.4rem 0 .3rem";
      head.textContent = found.length
        ? `${found.length.toLocaleString("en-US")} TWDB well reports within ${metres} m of this block, nearest first:`
        : `No TWDB well report within ${metres} m of this block.`;
      busy.replaceWith(head);
      if (!found.length) return;
      const list = document.createElement("ol");
      list.style.cssText = "margin:0;padding-left:1.2rem;max-height:16rem;overflow:auto";
      const groups = wells ? wells.index.use_groups : [];
      for (const [distance, ...record] of found) {
        const a = wellAttributes(record);
        const item = document.createElement("li");
        item.style.cssText = "margin:.15rem 0";
        const button = document.createElement("button");
        button.type = "button";
        button.style.cssText = "font:inherit;color:inherit;background:none;border:0;padding:0;text-decoration:underline;cursor:pointer;text-align:left";
        button.textContent = `${a.uid[0] === "S" ? "Driller's report" : "State well"} ${a.uid.slice(1)}`;
        button.addEventListener("click", () => {
          if (wells) wells.openWell(record);
        });
        const facts = [
          distance ? `${Number(distance).toLocaleString("en-US")} m away` : "inside the block",
          a.depth ? `${Number(a.depth).toLocaleString("en-US")} ft deep` : "no depth reported",
          a.wbasis === 2 ? "no log" : CLASS_NAMES[a.wcls],
          a.yield === null || a.yield === undefined ? "no yield reported" : `${Number(a.yield).toLocaleString("en-US")} gpm`,
          groups[a.use] || "",
        ].filter(Boolean);
        item.append(button, document.createTextNode(` · ${facts.join(" · ")}`));
        list.append(item);
      }
      box.append(list);
    })
    .catch((error) => {
      console.error("the wells near this block could not be loaded", error);
      busy.textContent = "Sorry, the wells near this block could not be loaded.";
    });
  return box;
}

// The vineyards in four layers, one per category (resources/vineyards/):
// the Hickory Sands District's, the Llano Uplift's outside the district,
// those under development and the historical ones.
const VINEYARD_STYLES = {
  hsd: { fill: [...WINE, 0.65], outline: [255, 214, 224] },
  "llano-uplift": { fill: [200, 132, 152, 0.4], outline: [255, 236, 240] },
  // A light fill, so small planned blocks show under the see-through aquifer.
  "under-development": { fill: [255, 214, 224, 0.3], outline: [255, 214, 224], style: "dash" },
  historical: { fill: [0, 0, 0, 0], outline: [...MUTED, 1], style: "dot" },
};
const vineyardLayer = (category, title) => {
  const look = VINEYARD_STYLES[category];
  return new GeoJSONLayer({
    url: `${DATA}vineyards.geojson`,
    title,
    definitionExpression: `category = '${category}'`,
    geometryType: "polygon",
    outFields: ["*"],
    elevationInfo: { mode: "relative-to-ground", offset: 3 },
    renderer: {
      type: "simple",
      symbol: {
        type: "polygon-3d",
        symbolLayers: [
          {
            type: "fill",
            material: { color: look.fill },
            outline: { color: look.outline, size: 1.5, ...(look.style ? { pattern: { type: "style", style: look.style } } : {}) },
          },
        ],
      },
    },
    labelingInfo: [
      {
        labelExpressionInfo: { expression: "$feature.name" },
        labelPlacement: "above-center",
        minScale: 400000,
        symbol: textSymbol(10, [232, 196, 204]),
      },
    ],
    // The vineyard's name, its category, this block and its acres (one block,
    // not the vineyard's whole acreage) and its source; then the wells near it.
    popupTemplate: {
      title: "{name}",
      outFields: ["*"],
      content: [
        {
          type: "fields",
          fieldInfos: [
            { fieldName: "category_label", label: "Category" },
            { fieldName: "block", label: "Block" },
            { fieldName: "acres", label: "Acres of this block (as outlined)" },
            { fieldName: "source", label: "Source" },
          ],
        },
        new CustomContent({ outFields: ["*"], creator: ({ graphic }) => nearList(graphic.attributes.vid) }),
      ],
    },
  });
};
const vineyardsDistrict = vineyardLayer("hsd", "Hickory Sands District vineyards");
const vineyardsLlano = vineyardLayer("llano-uplift", "Llano Uplift vineyards");
const vineyardsDeveloping = vineyardLayer("under-development", "Vineyards under development");
const vineyardsHistorical = vineyardLayer("historical", "Historical vineyards");

let exaggeration = 5;
const groundLayers = (k) => (flat ? [] : [new ExaggeratedElevation({ exaggeration: k, source: terrain })]);
const ground = new Ground({
  layers: groundLayers(exaggeration),
  opacity: 0.4,
  navigationConstraint: { type: "none" },
});
const map = new EsriMap({
  basemap: apiKey ? new Basemap({ style: { id: "arcgis/dark-gray" } }) : null,
  ground,
  // Bottom to top, the reverse of the panel's list (the rock, the ground,
  // the sky): the geology, the boundaries, the vineyards, then (added later,
  // right above the vineyards) the wells and your location, and the towns on
  // top. The aquifer's meshes are view graphics, under the ground.
  layers: [
    precambrianBuried,
    precambrian,
    outcrop,
    member,
    counties,
    llanoUplift,
    district,
    vineyardsHistorical,
    vineyardsDeveloping,
    vineyardsLlano,
    vineyardsDistrict,
    towns,
  ],
});

// The places and angles the view can start from. "From above" looks across
// the place from the south-west; "from below" looks up at the aquifer's base
// from under the ground. Depths below the ground follow the exaggeration.
const PLACES = {
  whole: {
    above: () => ({ lon: -99.35, lat: 29.02, z: 150000, heading: 20, tilt: 48 }),
    below: (k) => ({ lon: -98.75, lat: 29.6, z: -9000 * k, heading: 0, tilt: 118 }),
  },
  district: {
    above: () => ({ lon: -99.62, lat: 30.55, z: 26000, heading: 42, tilt: 66 }),
    below: (k) => ({ lon: -99.3, lat: 30.55, z: -1200 * k, heading: 8, tilt: 106 }),
  },
};
let place = "whole";
let angle = "above";
const cameraFor = (k) => {
  const v = PLACES[place][angle](k);
  return new Camera({
    position: new Point({ longitude: v.lon, latitude: v.lat, z: v.z, spatialReference: SpatialReference.WGS84 }),
    heading: v.heading,
    tilt: v.tilt,
  });
};

const scene = document.querySelector(".aq-stage arcgis-scene");
scene.map = map;
scene.qualityProfile = small ? "medium" : "high";
scene.camera = cameraFor(exaggeration);
scene.aria = { label: scene.getAttribute("aria-label") };
let view;
try {
  await scene.viewOnReady();
  view = scene.view;
} catch (error) {
  // No WebGL 2, or the view could not start: the page keeps its text.
  console.error("the 3D view could not be drawn", error);
  document.documentElement.classList.remove("js");
  throw error;
}
view.environment = {
  background: { type: "color", color: [...INK, 1] },
  starsEnabled: false,
  atmosphereEnabled: false,
  lighting: { type: "virtual" },
};
window.aquiferView = view; // for the browser tests and anyone curious

// A layer that cannot be drawn: the basemap's are only a note; the rest are
// logged, but for one taken off the map before it was drawn (the wells'
// heads, replaced as the filters change), which is no failure.
view.on("layerview-create-error", ({ layer, error }) => {
  if (map.basemap && map.basemap.baseLayers.includes(layer)) {
    say("basemap", "Esri’s basemap could not be loaded, so the layers are drawn on a plain background.");
    console.warn("the basemap could not be loaded", error);
  } else if (map.allLayers.includes(layer)) {
    console.error(`the layer “${layer.title}” could not be drawn`, error);
  }
});
if (map.basemap) {
  map.basemap.load().catch((error) => {
    say("basemap", "Esri’s basemap could not be loaded, so the layers are drawn on a plain background.");
    console.warn("the basemap could not be loaded", error);
  });
}

function draw(k) {
  const meshes = aquiferMesh(k);
  for (const key of Object.keys(aquifer)) {
    aquifer[key].geometry = meshes[key];
    if (!view.graphics.includes(aquifer[key])) {
      view.graphics.add(aquifer[key]);
    }
  }
}
draw(exaggeration);
// The block's size, from the data: its cells and the model's cell size.
{
  const kc = model.block_cells;
  const miles = (kc * stats.cell_ft) / 5280;
  const side = { 0.5: "half a mile", 1: "a mile" }[miles] || (Number.isFinite(miles) ? `${miles} miles` : "");
  setText("aq-block-size", `${kc} × ${kc} model cells${side ? ` (${side} square)` : ""}`);
}

// ---- "My location": the position is never sent anywhere or stored. It is
// used only to place a point, to look up its model cell in drill-grid.bin (a
// static file fetched whole, so no request names the position) and to move
// the view there, which loads Esri's basemap and elevation tiles for that
// area, as any web map does: Esri's servers see which area is shown.
const drillLayer = new GraphicsLayer({ title: "Your location", elevationInfo: { mode: "relative-to-ground" } });
map.add(drillLayer, map.layers.indexOf(vineyardsDistrict) + 1);
let fix = null; // [lon, lat, result] while the page is open; never stored
let drillGrid = null;

async function loadDrillGrid() {
  if (drillGrid) {
    return drillGrid;
  }
  const [meta, blob] = await Promise.all([
    json(`${DATA}drill-grid.json`),
    fetch(`${DATA}drill-grid.bin`).then((r) => {
      if (!r.ok) throw new Error(`drill-grid.bin: HTTP ${r.status}`);
      return r.arrayBuffer();
    }),
  ]);
  const n = meta.rows * meta.cols;
  drillGrid = {
    meta,
    ground: new Int16Array(blob, 0, n),
    top: new Int16Array(blob, 2 * n, n),
    bot: new Int16Array(blob, 4 * n, n),
    flags: new Uint8Array(blob, 6 * n, n),
  };
  return drillGrid;
}

function cellAt(grid, lon, lat) {
  const p = grid.meta.lonlat_to_rowcol;
  const t = terms(lon - p.lon_c, lat - p.lat_c, p.degree);
  const dot = (c) => c.reduce((s, x, i) => s + x * t[i], 0);
  const r = Math.round(dot(p.row));
  const c = Math.round(dot(p.col));
  if (r < 0 || c < 0 || r >= grid.meta.rows || c >= grid.meta.cols) {
    return null;
  }
  const i = r * grid.meta.cols + c;
  return { row: r + 1, col: c + 1, ground: grid.ground[i], top: grid.top[i], bot: grid.bot[i], flags: grid.flags[i] };
}

const about = (ft) => (Math.round(ft / 10) * 10).toLocaleString("en-US");

function describe(cell) {
  const tail = stats.cell_ft
    ? `Estimate from TWDB’s regional model, whose cells are ${formatStat(stats.cell_ft, "num")} ft square.`
    : "Estimate from TWDB’s regional model.";
  if (!cell || !(cell.flags & 16)) {
    return {
      lines: ["This spot is outside TWDB’s Llano Uplift groundwater model, so the model says nothing about what lies beneath it."],
      hickory: null,
    };
  }
  if (!(cell.flags & 1)) {
    const first = cell.flags & 8
      ? "The model has Precambrian rock at the surface here and no Hickory Aquifer beneath this spot."
      : "The model has no Hickory Aquifer layer beneath this spot.";
    return { lines: [first, tail], hickory: null };
  }
  const thick = cell.top - cell.bot;
  const depth = Math.max(0, cell.ground - cell.top);
  const lines = [];
  if (cell.flags & 4 || depth < 1) {
    lines.push(`The model has the Hickory Aquifer at the surface here, about ${about(thick)} ft thick.`);
  } else {
    lines.push(`The model puts the top of the Hickory Aquifer about ${about(depth)} ft below the ground here, and it is about ${about(thick)} ft thick.`);
  }
  if (!(cell.flags & 2)) {
    lines.push("This spot is outside TWDB’s official Hickory Aquifer outline, which TWDB draws partly on water quality.");
  }
  lines.push(tail);
  return { lines, hickory: { depth, thick } };
}

function drawDrill(k) {
  drillLayer.removeAll();
  if (!fix) {
    return;
  }
  const [lon, lat, result] = fix;
  const at = (z) => [lon, lat, z];
  const line = (z0, z1, color, size, style) =>
    new Graphic({
      geometry: new Polyline({ hasZ: true, paths: [[at(z0), at(z1)]], spatialReference: SpatialReference.WGS84 }),
      symbol: {
        type: "line-3d",
        symbolLayers: [{ type: "line", material: { color }, size, ...(style ? { pattern: { type: "style", style } } : {}) }],
      },
    });
  const h = result.hickory;
  if (h) {
    if (h.depth > 0) {
      drillLayer.add(line(0, -h.depth * FT * k, BONE, 2, "dash"));
    }
    drillLayer.add(line(-h.depth * FT * k, -(h.depth + h.thick) * FT * k, [236, 248, 252, 1], 6));
    drillLayer.add(line(-(h.depth + h.thick) * FT * k, -(h.depth + h.thick + 200) * FT * k, BONE, 2, "dash"));
  } else {
    drillLayer.add(line(0, -1000 * FT * k, MUTED, 2, "dash"));
  }
  const here = new Point({ longitude: lon, latitude: lat, z: 0, spatialReference: SpatialReference.WGS84 });
  drillLayer.add(
    new Graphic({
      geometry: here,
      symbol: {
        type: "point-3d",
        symbolLayers: [
          { type: "icon", resource: { primitive: "circle" }, material: { color: BONE }, outline: { color: [...INK, 1], size: 2 }, size: 14 },
        ],
      },
    }),
  );
  drillLayer.add(
    new Graphic({
      geometry: here,
      symbol: {
        type: "point-3d",
        verticalOffset: { screenLength: 34 },
        callout: { type: "line", color: BONE, size: 1 },
        symbolLayers: [
          {
            type: "text",
            text: "Your location",
            material: { color: BONE },
            halo: { color: [...INK, 0.9], size: 1.2 },
            size: 12,
            font: { family: "Noto Sans", weight: "bold" },
          },
        ],
      },
    }),
  );
}

const drillBox = document.getElementById("aq-drill");
function showDrill(lines) {
  if (!drillBox) {
    return;
  }
  drillBox.replaceChildren(
    ...lines.map((text) => {
      const p = document.createElement("p");
      p.textContent = text;
      return p;
    }),
  );
  drillBox.hidden = false;
}

const locateButton = document.getElementById("aq-locate");
if (locateButton) {
  locateButton.addEventListener("click", () => {
    if (!("geolocation" in navigator)) {
      showDrill(["This browser cannot share a location, so nothing was placed."]);
      return;
    }
    showDrill(["Finding your location…"]);
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const lon = position.coords.longitude;
        const lat = position.coords.latitude;
        try {
          const grid = await loadDrillGrid();
          const cell = cellAt(grid, lon, lat);
          const result = describe(cell);
          // The model's ground at the point (metres), to aim the camera at.
          result.groundM = !flat && cell && cell.flags & 16 ? cell.ground * FT : 0;
          fix = [lon, lat, result];
          // The "Your location" row appears, checked; it shows while Places is on.
          const row = document.getElementById("aq-row-location");
          if (row) row.hidden = false;
          const box = document.querySelector('input[data-switch="location"]');
          if (box) box.checked = true;
          const places = document.querySelector('[data-group-switch="places"]');
          drillLayer.visible = !places || places.checked;
          drawDrill(exaggeration);
          showDrill(result.lines);
          view
            .goTo(
              {
                target: new Point({ longitude: lon, latitude: lat, z: result.groundM * exaggeration, spatialReference: SpatialReference.WGS84 }),
                zoom: 15,
                tilt: 62,
                heading: 20,
              },
              { animate: !reducedMotion, duration: 2000 },
            )
            .catch((error) => {
              if (error.name !== "AbortError") {
                console.error("the camera could not move", error);
              }
            });
        } catch (error) {
          console.error("the model lookup failed", error);
          showDrill(["Sorry, the model data could not be loaded. Please try again."]);
        }
      },
      (error) => {
        showDrill([
          error.code === error.PERMISSION_DENIED
            ? "Location is turned off for this page, so nothing was placed. You can allow it in your browser’s settings and try again."
            : "Your location could not be found just now. Please try again in a moment.",
        ]);
      },
      { enableHighAccuracy: false, timeout: 20000, maximumAge: 60000 },
    );
  });
}

// ---- The panel (its design: research/design-3d-panel-2026-10-18). Groups
// collapse and remember it; each group's switch gates its layers, as QGIS's
// groups do; an "i" opens a one-line note; on a phone the panel is a bottom
// sheet; "About this map" is a dialog.
const panel = document.getElementById("aq-panel");
const panelBody = document.getElementById("aq-panel-body");
const phone = matchMedia("(max-width: 640px)");
const STORE = "hsd-aquifer-3d-panel";
const stored = (() => {
  try {
    return JSON.parse(localStorage.getItem(STORE)) || {};
  } catch {
    return {}; // no storage (a private window): the defaults apply
  }
})();
stored.open = stored.open || {};
const remember = () => {
  try {
    localStorage.setItem(STORE, JSON.stringify(stored));
  } catch {
    // no storage: the panel just forgets
  }
};
// Open on a first visit; on a wide screen the well filters are open, so they
// are in sight without scrolling (#135).
const DEFAULT_OPEN = phone.matches
  ? { view: true }
  : { view: true, wells: true, filters: true, vineyards: true, aquifer: true };
for (const button of document.querySelectorAll(".lp-gt, .lp-subh")) {
  const key = button.dataset.sub || button.closest("[data-group]").dataset.group;
  const body = document.getElementById(button.getAttribute("aria-controls"));
  const set = (open) => {
    button.setAttribute("aria-expanded", String(open));
    body.hidden = !open;
  };
  set(stored.open[key] ?? DEFAULT_OPEN[key] ?? false);
  button.addEventListener("click", () => {
    const open = button.getAttribute("aria-expanded") !== "true";
    set(open);
    stored.open[key] = open;
    remember();
  });
}
for (const button of document.querySelectorAll(".lp-i")) {
  const note = document.getElementById(button.getAttribute("aria-controls"));
  button.addEventListener("click", () => {
    const open = button.getAttribute("aria-expanded") !== "true";
    button.setAttribute("aria-expanded", String(open));
    note.hidden = !open;
  });
}

// Keeps the panel from covering the middle of the view.
const pad = () => {
  if (!panel) return;
  view.padding = phone.matches
    ? { bottom: panel.classList.contains("is-open") ? Math.max(0, panel.offsetHeight - 64) : 0 }
    : { left: panel.offsetLeft + panel.offsetWidth };
};
const toggle = document.getElementById("aq-sheet-toggle");
function sheet(open, focus = true) {
  if (!panel || !toggle) return;
  panel.classList.toggle("is-open", open);
  toggle.setAttribute("aria-expanded", String(open));
  toggle.lastElementChild.textContent = open ? "Done" : "Layers";
  panelBody.inert = phone.matches && !open;
  if (focus && open) panelBody.querySelector("button, input, a")?.focus({ preventScroll: true });
  if (focus && !open) toggle.focus();
  pad();
}
if (toggle) {
  toggle.addEventListener("click", () => sheet(!panel.classList.contains("is-open")));
  panel.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && phone.matches && panel.classList.contains("is-open")) sheet(false);
  });
}
const fit = () => {
  if (phone.matches) {
    sheet(false, false);
  } else {
    panel.classList.remove("is-open");
    panelBody.inert = false;
    pad();
  }
};
phone.addEventListener("change", fit);
addEventListener("resize", pad);
fit();

const aboutDialog = document.getElementById("aq-about");
let opener = null;
for (const link of document.querySelectorAll("[data-about]")) {
  link.addEventListener("click", (event) => {
    if (!aboutDialog || typeof aboutDialog.showModal !== "function") return; // the link scrolls there
    event.preventDefault();
    opener = link;
    aboutDialog.showModal();
    aboutDialog.scrollTop = 0;
    if (link.dataset.about !== "about-reading") {
      document.getElementById(link.dataset.about)?.scrollIntoView({ block: "start" });
    }
    document.getElementById("aq-about-close")?.focus({ preventScroll: true });
  });
}
if (aboutDialog) {
  document.getElementById("aq-about-close")?.addEventListener("click", () => aboutDialog.close());
  aboutDialog.addEventListener("click", (event) => {
    if (event.target === aboutDialog) aboutDialog.close();
  });
  aboutDialog.addEventListener("close", () => opener?.focus());
}

// ---- The well filters: use groups, water volume (yield) and depth ranges
// (stepped), the Hickory-only switch and the water dots. A well shows only if
// it passes all.
const YIELD_STOPS = [0, 5, 10, 25, 50, 100, 200, 500, 1000, Infinity];
const DEPTH_STOPS = [0, 50, 100, 200, 300, 500, 800, 1200, 2000, Infinity];
// The use groups' names in the panel; the report's groups are in the data.
const SHORT_USES = {
  "Livestock / stock": "Livestock",
  "Industrial / commercial / mining": "Industrial",
  "Monitoring / test / other / unknown": "Monitoring, other",
};
const n = (v) => Number(v).toLocaleString("en-US");
const filters = { uses: true, yield: true, depth: true, hickory: true }; // true: not narrowed
let showCounts = () => {};

function wireWellFilters(w) {
  const groups = w.index.use_groups;
  const total = w.index.filter_keys.length;
  setText("aq-wells-total", n(total));
  // The page says the wells start as irrigation wells; without that use
  // group in the data every use is shown at first (aquifer-wells.js logs
  // it), and the page says that instead.
  if (!groups.includes("Irrigation")) {
    for (const said of document.querySelectorAll("[data-wells-default]")) {
      said.textContent = `Shown at first: wells of every use that tested at ${n(w.defaults.yieldLo)} gpm or more; widen the filters to see the rest.`;
    }
  }
  const box = document.getElementById("aq-uses");
  const useBoxes = [];
  const useCounts = [];
  const applyUses = () => {
    const uses = new Set(useBoxes.filter((b) => b.checked).map((b) => Number(b.dataset.use)));
    filters.uses = uses.size === groups.length;
    showCounts(w.setFilter({ uses }));
  };
  filters.uses = w.defaults.uses.size === groups.length;
  if (box) {
    groups.forEach((name, i) => {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = w.defaults.uses.has(i);
      input.dataset.use = String(i);
      const text = document.createElement("span");
      text.textContent = SHORT_USES[name] || name;
      const count = document.createElement("b");
      label.append(input, text, count);
      box.append(label);
      useBoxes.push(input);
      useCounts.push(count);
      input.addEventListener("change", applyUses);
    });
  }
  for (const [id, on] of [["aq-uses-all", true], ["aq-uses-none", false]]) {
    document.getElementById(id)?.addEventListener("click", () => {
      for (const b of useBoxes) b.checked = on;
      applyUses();
    });
  }
  showCounts = (counts) => {
    if (!counts) return;
    setText("aq-wells-shown", n(counts.shown));
    const meta = document.querySelector("[data-wells-meta]");
    if (meta) meta.textContent = counts.shown === total ? n(total) : `${n(counts.shown)} of ${n(total)}`;
    counts.byUse.forEach((v, i) => {
      if (useCounts[i]) useCounts[i].textContent = n(v);
    });
    const narrowed = Object.values(filters).filter((v) => !v).length;
    setText("aq-filters-state", narrowed ? `${narrowed} on` : "none");
  };
  const label = (stops, i) => (Number.isFinite(stops[i]) ? n(stops[i]) : `${n(stops[stops.length - 2])}+`);
  const ranges = [];
  for (const [prefix, key, stops, unit, loKey, hiKey, noneKey] of [
    ["aq-yield", "yield", YIELD_STOPS, "gpm", "yieldLo", "yieldHi", "noYield"],
    ["aq-depth", "depth", DEPTH_STOPS, "ft", "depthLo", "depthHi", "noDepth"],
  ]) {
    const lo = document.getElementById(`${prefix}-lo`);
    const hi = document.getElementById(`${prefix}-hi`);
    const none = document.getElementById(`${prefix}-none`);
    const dual = document.getElementById(`${prefix}-dual`);
    if (!lo || !hi) continue;
    const last = stops.length - 1;
    for (const input of [lo, hi]) {
      input.min = "0";
      input.max = String(last);
      input.step = "1";
    }
    // Start at the defaults (the highest stop at or below the default's
    // lower limit, the top stop for no upper limit).
    const startLo = Math.max(0, stops.findLastIndex((s) => s <= w.defaults[loKey]));
    const startHi = Number.isFinite(w.defaults[hiKey]) ? Math.max(startLo, stops.findIndex((s) => s >= w.defaults[hiKey])) : last;
    const startNone = w.defaults[noneKey];
    lo.value = String(startLo);
    hi.value = String(startHi);
    if (none) none.checked = startNone;
    const apply = (moved) => {
      let a = Number(lo.value);
      let b = Number(hi.value);
      if (a > b) {
        if (moved === lo) b = a;
        else a = b;
        lo.value = String(a);
        hi.value = String(b);
      }
      dual?.style.setProperty("--lo", `${(a / last) * 100}%`);
      dual?.style.setProperty("--hi", `${(b / last) * 100}%`);
      lo.setAttribute("aria-valuetext", `${label(stops, a)} ${unit}`);
      hi.setAttribute("aria-valuetext", `${label(stops, b)} ${unit}`);
      const all = a === 0 && b === last;
      filters[key] = all && (!none || none.checked);
      setText(`${prefix}-out`, all ? "all" : `${label(stops, a)}–${label(stops, b)} ${unit}`);
      // The top stop means "and above": no upper limit.
      const top = b === last ? Infinity : stops[b];
      const bottom = a === last ? stops[last - 1] : stops[a];
      showCounts(w.setFilter({ [loKey]: bottom, [hiKey]: top, [noneKey]: none ? none.checked : true }));
    };
    lo.addEventListener("input", () => apply(lo));
    hi.addEventListener("input", () => apply(hi));
    none?.addEventListener("change", () => apply(null));
    ranges.push({ lo, hi, none, startLo, startHi, startNone, apply });
    apply(null);
  }
  // Reset: the filters only (use, water volume, depth, "include unreported",
  // Hickory Aquifer only) back to their defaults; not the Wells switch or the
  // water levels.
  document.getElementById("aq-wells-reset")?.addEventListener("click", () => {
    useBoxes.forEach((b, i) => {
      b.checked = w.defaults.uses.has(i);
    });
    const only = document.querySelector('input[data-switch="wells-hickory-only"]');
    if (only) only.checked = false;
    w.setFilter({ uses: new Set(w.defaults.uses), hickoryOnly: false });
    filters.uses = w.defaults.uses.size === groups.length;
    filters.hickory = true;
    for (const r of ranges) {
      r.lo.value = String(r.startLo);
      r.hi.value = String(r.startHi);
      if (r.none) r.none.checked = r.startNone;
      r.apply(null);
    }
  });
  showCounts(w.counts());
}

// Only the wells that pass the filters are drawn. Zoomed far out, every one's
// head while few enough pass, else they are thinned; from about the
// district's scale in, every one's head; closer in, the lines down the hole
// near the middle of the view. The note under the Wells heading says which.
const scaleOf = (key) => (stats[key] ? formatStat(stats[key], "scale") : "the district’s scale");
function wellNote({ mode, left, failed, loading, shown, drawn }) {
  const note = document.getElementById("aq-wells-note");
  if (!note || !wells) return;
  const cell = `one well per ${wells.index.overview_cell_degrees}° cell`;
  const all = shown === 1 ? "The one well that passes the filters is drawn" : `The ${n(shown)} wells that pass the filters are drawn`;
  const of = shown === 1 ? "the one that passes" : `the ${n(shown)} that pass`;
  if (loading) {
    note.textContent = `Loading the wells that pass the filters; meanwhile ${cell} is drawn where it passes.`;
  } else if (!shown) {
    note.textContent = "No well passes the filters; widen them to see wells.";
  } else if (mode === "overview") {
    note.textContent = failed
      ? `Not every well could be loaded or drawn, so ${cell} is drawn where it passes the filters (${n(drawn)} of ${of}).`
      : `Zoomed out, the wells are thinned: ${cell}, where it passes the filters (${n(drawn)} of ${of}). Zoom in to about ${scaleOf("wells_all_scale")}, or go to District, to see them all.`;
  } else if (failed) {
    note.textContent = "Not every well that passes the filters could be drawn. Move the view or change a filter to try again.";
  } else if (mode === "heads") {
    note.textContent = `${all}, with only some of their lines down the hole. Zoom in to about ${scaleOf("wells_lines_scale")} for every line.`;
  } else if (left > 0) {
    note.textContent = `${all}, and every line near the middle of the view; ${n(left)} more in view have only their heads drawn. Zoom in or move to see their lines.`;
  } else {
    note.textContent = "";
  }
}

// Wells: TWDB's driller's reports and Groundwater Database.
setText("aq-wells-far-max", n(FAR_HEADS_MAX));
try {
  wells = await setupWells({
    map,
    view,
    small,
    exaggeration,
    reducedMotion,
    // The head of every well that passes the filters from about the
    // district's scale in (further out too while few enough pass), and the
    // lines down the hole closer in; else the thinned overview.
    allScale: stats.wells_all_scale,
    linesScale: stats.wells_lines_scale,
    FeatureLayer,
    Graphic,
    Polyline,
    Point,
    SpatialReference,
    reactiveUtils,
    onNote: (note) => wellNote(note),
    // Wells go right above the vineyards, under your location and the towns.
    insertAt: () => map.layers.indexOf(vineyardsDistrict) + 1,
  });
  window.aquiferWells = wells; // for the browser tests
  wireWellFilters(wells);
  wellNote(wells.note());
} catch (error) {
  console.error("the wells could not be loaded", error);
  say("wells", "The wells could not be loaded.");
}

// ---- The layer switches: each checkbox names what it turns on and off; a
// layer shows when its group's switch is on and its own box is checked.
const SWITCHES = {
  towns: (on) => (towns.visible = on),
  location: (on) => (drillLayer.visible = on),
  "vineyards-hsd": (on) => (vineyardsDistrict.visible = on),
  "vineyards-llano": (on) => (vineyardsLlano.visible = on),
  "vineyards-developing": (on) => (vineyardsDeveloping.visible = on),
  "vineyards-historical": (on) => (vineyardsHistorical.visible = on),
  district: (on) => (district.visible = on),
  ava: (on) => (llanoUplift.visible = on),
  counties: (on) => (counties.visible = on),
  member: (on) => (member.visible = on),
  "official-outcrop": (on) => (outcrop.visible = on),
  precambrian: (on) => (precambrian.visible = on),
  "precambrian-buried": (on) => (precambrianBuried.visible = on),
  "top-surface": (on) => (aquifer.outcrop.visible = on),
  "top-buried": (on) => (aquifer.top.visible = on),
  sides: (on) => (aquifer.side.visible = on),
  "outside-official": (on) => (aquifer.outside.visible = on),
};
const groupOn = (box) => {
  const toggleOf = box.closest(".lp-group")?.querySelector("[data-group-switch]");
  return !toggleOf || toggleOf.checked;
};
const layerBox = (box) => {
  const apply = SWITCHES[box.dataset.switch];
  if (apply) apply(groupOn(box) && box.checked);
};
for (const box of document.querySelectorAll("input[data-switch]")) {
  if (SWITCHES[box.dataset.switch]) {
    box.addEventListener("change", () => layerBox(box));
    layerBox(box);
  }
}
for (const toggleBox of document.querySelectorAll("[data-group-switch]")) {
  const group = toggleBox.closest(".lp-group");
  toggleBox.addEventListener("change", () => {
    group.classList.toggle("is-off", !toggleBox.checked);
    for (const box of group.querySelectorAll("input[data-switch]")) {
      if (box !== toggleBox) layerBox(box);
    }
  });
}
// "Show wells", at the top of the Wells group, and the group's own switch are
// one switch: every well on or off (heads, lines, rings and water dots).
const wellsSwitches = [...document.querySelectorAll('input[data-switch="wells"], #aq-wells-show')];
const setWellsOn = (on) => {
  for (const box of wellsSwitches) box.checked = on;
  document.getElementById("aq-wells")?.classList.toggle("is-off", !on);
  if (wells) wells.setVisible(on);
};
for (const box of wellsSwitches) {
  box.addEventListener("change", () => setWellsOn(box.checked));
}
document.querySelector('input[data-switch="wells-water"]')?.addEventListener("change", (event) => {
  if (wells) wells.setWater(event.target.checked);
});
document.querySelector('input[data-switch="wells-hickory-only"]')?.addEventListener("change", (event) => {
  filters.hickory = !event.target.checked;
  if (wells) showCounts(wells.setFilter({ hickoryOnly: event.target.checked }));
});

const move = () =>
  view.goTo(cameraFor(exaggeration), { animate: !reducedMotion, duration: 2000 }).catch((error) => {
    if (error.name !== "AbortError") {
      console.error("the camera could not move", error);
    }
  });
const press = (selector, chosen) => {
  for (const other of document.querySelectorAll(selector)) {
    other.setAttribute("aria-pressed", String(other === chosen));
  }
};
for (const button of document.querySelectorAll("button[data-place]")) {
  button.addEventListener("click", () => {
    place = button.dataset.place;
    press("button[data-place]", button);
    move();
  });
}
for (const button of document.querySelectorAll("button[data-angle]")) {
  button.addEventListener("click", () => {
    angle = button.dataset.angle;
    press("button[data-angle]", button);
    move();
  });
}
for (const button of document.querySelectorAll("button[data-ve]")) {
  button.addEventListener("click", () => {
    const k = Number(button.dataset.ve);
    if (k === exaggeration) {
      return;
    }
    exaggeration = k;
    press("button[data-ve]", button);
    setText("aq-ve", `${k}×`);
    map.ground.layers = groundLayers(k);
    draw(k);
    if (wells) {
      wells.setExaggeration(k);
    }
    drawDrill(k);
  });
}

await reactiveUtils.whenOnce(() => !view.updating);
say("load", "");
document.documentElement.dataset.aquifer = "ready";
