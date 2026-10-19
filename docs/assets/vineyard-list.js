// The vineyards on this site (vineyards.html): the list and the map, from the
// site's vineyard data (assets/vineyards/, made by src/site/make_vineyards.py
// from resources/vineyards/). The list is grouped as The water groups the
// blocks; each vineyard shows how many blocks it has, the year it was first
// planted and its varieties when given, and a button that shows it on the map.
// No acres: an outline's acres are not planted acres. The map loads Esri's SDK
// only when it comes near the screen, or when a vineyard is asked for. Text
// from the data is only ever set as text, never parsed as HTML.
import { apiKey } from "./map-config.js";

const SDK = "https://js.arcgis.com/5.1/";
const DATA = "assets/vineyards/";
const GROUPS = [
  ["hsd", "In the proposed Hickory Sands District"],
  ["llano-uplift", "Elsewhere in the proposed Llano Uplift AVA"],
  ["under-development", "Under development"],
  ["historical", "Historical"],
];
const STYLE = {
  hsd: { fill: [90, 30, 46, 0.55], line: [255, 214, 224, 1] },
  "llano-uplift": { fill: [200, 132, 152, 0.45], line: [255, 236, 240, 1] },
  "under-development": { fill: [255, 214, 224, 0.3], line: [255, 214, 224, 1], style: "dash" },
  historical: { fill: [0, 0, 0, 0], line: [238, 232, 219, 1], style: "dot" },
};
const YELLOW = [255, 214, 0];

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};

async function json(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

// --- the map ------------------------------------------------------------------

let mapReady = null;
function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.type = "module";
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error(`${src} did not load`));
    document.head.append(s);
  });
}
function openMap() {
  mapReady ||= (async () => {
    $("vy-map-note").textContent = "Loading the map…";
    if (!window.$arcgis) await loadScript(SDK);
    await customElements.whenDefined("arcgis-map");
    const [config, Map, Basemap, GeoJSONLayer] = await Promise.all(
      ["config", "Map", "Basemap", "layers/GeoJSONLayer"].map((n) => $arcgis.import(`@arcgis/core/${n}.js`)),
    );
    if (apiKey) config.apiKey = apiKey;
    const district = new GeoJSONLayer({
      url: "data/boundary.geojson",
      title: "The proposed Hickory Sands District",
      renderer: { type: "simple", symbol: { type: "simple-fill", color: [0, 0, 0, 0], outline: { color: [...YELLOW, 0.95], width: 2, style: "dash" } } },
    });
    const blocks = new GeoJSONLayer({
      url: `${DATA}vineyards.geojson`,
      title: "The vineyards",
      outFields: ["*"],
      renderer: {
        type: "unique-value",
        field: "category",
        uniqueValueInfos: Object.entries(STYLE).map(([value, s]) => ({
          value,
          symbol: { type: "simple-fill", color: s.fill, outline: { color: s.line, width: 1.5, style: s.style || "solid" } },
        })),
      },
      popupTemplate: { title: "{name}", content: "{category_label}" },
    });
    const view = $("vy-arcgis");
    view.map = new Map({ basemap: new Basemap({ style: { id: "arcgis/imagery" } }), layers: [district, blocks] });
    view.center = [-99.1, 30.85];
    view.zoom = 8;
    view.constraints = { rotationEnabled: false, minZoom: 6, maxZoom: 19 };
    await view.viewOnReady();
    $("vy-map-note").textContent = "Tap a block for its vineyard's name. Drag to move the map.";
    return { view: view.view, blocks };
  })().catch((error) => {
    console.error("the vineyards' map could not load", error);
    $("vy-map-note").textContent = "The map could not load. The list below has every vineyard; The water shows them too.";
    mapReady = null; // asked again (Show on the map), it tries again
    throw error;
  });
  return mapReady;
}

async function showOnMap(entry, button) {
  $("vy-map").scrollIntoView({ block: "start", behavior: "smooth" });
  try {
    const { view, blocks } = await openMap();
    const where = `vid IN (${entry.vids.map((v) => `'${v.replace(/[^a-z0-9-]/g, "")}'`).join(",")})`;
    const found = await blocks.queryFeatures({ where, returnGeometry: true, outFields: ["*"] });
    if (!found.features.length) throw new Error(`no blocks for ${entry.name}`);
    await view.goTo(found.features, { duration: 600 });
    view.openPopup({ features: found.features });
  } catch (error) {
    console.error("the vineyard could not be shown", error);
    button.textContent = "Not on the map just now";
  }
}

// --- the list -----------------------------------------------------------------

function row(entry) {
  const li = el("li", "vy-row");
  const text = el("div", "vy-text");
  text.append(el("h4", "vy-name", entry.name));
  const n = entry.vids.length;
  const facts = [`${n} block${n === 1 ? "" : "s"}`];
  if (entry.year) facts.push(`first planted ${entry.year}`);
  text.append(el("p", "vy-facts", facts.join(" · ")));
  if (entry.varieties?.length) text.append(el("p", "vy-varieties", entry.varieties.join(", ")));
  const show = el("button", "vy-show", "Show on the map");
  show.type = "button";
  show.setAttribute("aria-label", `Show ${entry.name} on the map`);
  show.addEventListener("click", () => showOnMap(entry, show));
  li.append(text, show);
  return li;
}

async function list() {
  const box = $("vy-list");
  try {
    const { vineyards } = await json(`${DATA}register.json`);
    box.replaceChildren();
    for (const [category, heading] of GROUPS) {
      const found = vineyards.filter((v) => v.category === category);
      if (!found.length) continue;
      const group = el("section", "vy-group");
      const id = `vy-${category}`;
      const h = el("h3", "vy-heading", heading);
      h.id = id;
      group.setAttribute("aria-labelledby", id);
      const ul = el("ul", "vy-rows");
      for (const entry of found) ul.append(row(entry));
      group.append(h, ul);
      box.append(group);
    }
  } catch (error) {
    console.error("the list of vineyards could not be loaded", error);
    $("vy-empty").textContent = "The list of vineyards could not be loaded just now. The water shows them on its map.";
  }
}

list();
// The map loads when it comes near the screen. A failure is logged and said
// in openMap(); null here.
const mapQuietly = () => openMap().catch(() => null);
if ("IntersectionObserver" in window) {
  const watch = new IntersectionObserver((seen) => {
    if (seen.some((s) => s.isIntersecting)) {
      watch.disconnect();
      mapQuietly();
    }
  }, { rootMargin: "200px" });
  watch.observe($("vy-map"));
} else {
  mapQuietly();
}
