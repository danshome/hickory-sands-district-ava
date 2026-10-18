// The site's maps (#112, #113): the proposed revision from data/ (made by the
// build), drawn with Esri's ArcGIS Maps SDK for JavaScript, which the page loads
// from js.arcgis.com. Text from the data is only ever set as text, never parsed
// as HTML.
import { apiKey } from "./map-config.js";

const load = (name) => $arcgis.import(`@arcgis/core/${name}.js`);
const [config, Map, Basemap, GeoJSONLayer, GraphicsLayer, Graphic] =
  await Promise.all(
    ["config", "Map", "Basemap", "layers/GeoJSONLayer", "layers/GraphicsLayer",
      "Graphic"].map(load),
  );

export const reducedMotion =
  matchMedia("(prefers-reduced-motion: reduce)").matches;
export const hasBasemap = apiKey !== "";

const SAND = [199, 151, 111];
const BONE = [238, 232, 219];
const INK = [20, 21, 18];
const CREDIT = "Hickory Sands District petitioners (CC0)";

if (hasBasemap) {
  config.apiKey = apiKey;
}

// Esri's basemaps in the site's black and white: the dark grey map, or the
// imagery in greyscale.
const BASEMAPS = {
  map: { style: { id: "arcgis/dark-gray" } },
  imagery: { style: { id: "arcgis/imagery" } },
};

function basemap(name) {
  const chosen = new Basemap(BASEMAPS[name]);
  if (name === "imagery") {
    chosen
      .when(() => {
        chosen.baseLayers.forEach((layer) => {
          layer.effect = "grayscale(100%) brightness(80%)";
        });
      })
      .catch((error) => console.error("the imagery basemap failed", error));
  }
  return chosen;
}

// A popup's content: rows of a label and a value, then the step's text. The
// popup draws inside its own shadow DOM, where the site's stylesheet does not
// reach, so the few styles are set here.
const LABEL = "font-size:.625rem;letter-spacing:.12em;text-transform:uppercase;" +
  "opacity:.7;margin-right:.4rem";
const ROW = "margin:.15rem 0;font-size:.8125rem;line-height:1.45";
const TEXT = "margin:.8rem 0 0;font-family:'Cormorant Garamond',Georgia,serif;" +
  "font-size:1.125rem;line-height:1.4";

function described(rows, text) {
  const box = document.createElement("div");
  for (const [label, value] of rows) {
    const row = document.createElement("p");
    row.style.cssText = ROW;
    const name = document.createElement("span");
    name.style.cssText = LABEL;
    name.textContent = label;
    row.append(name, document.createTextNode(value));
    box.append(row);
  }
  if (text) {
    const body = document.createElement("p");
    body.style.cssText = TEXT;
    body.textContent = text;
    box.append(body);
  }
  return box;
}

const miles = (metres) => `${(metres / 1609.344).toFixed(1)} mi`;

function stepPopup({ graphic }) {
  const a = graphic.attributes;
  return described(
    [["Quadrangle", a.quad], ["Length", miles(a.length_m)], ["Ends", a.endpoint]],
    a.narrative,
  );
}

function pointPopup({ graphic }) {
  const a = graphic.attributes;
  return described([["Quadrangle", a.quad]], a.point_name);
}

// Makes the map in an <arcgis-map> element: the boundary, its steps and its
// points, and a layer for whatever the page marks. A quiet map draws the
// boundary in bone, leaving the sand for the steps the page marks. Returns the
// element, the layers and the boundary's extent.
export async function boundaryMap(element, { popups = true, quiet = false } = {}) {
  const boundary = new GeoJSONLayer({
    url: "data/boundary.geojson",
    title: "Proposed revision",
    copyright: CREDIT,
    popupEnabled: false,
    renderer: {
      type: "simple",
      symbol: {
        type: "simple-fill",
        color: [...SAND, 0.07],
        outline: quiet
          ? { color: [...BONE, 0.35], width: 1.25 }
          : { color: [...SAND, 1], width: 2 },
      },
    },
  });
  const steps = new GeoJSONLayer({
    url: "data/steps.geojson",
    title: "Steps",
    copyright: CREDIT,
    outFields: ["*"],
    popupEnabled: popups,
    popupTemplate: {
      // Built by functions, so the popup must be told to fetch every field.
      outFields: ["*"],
      title: ({ graphic }) => `Step ${Number(graphic.attributes.step)}`,
      content: stepPopup,
    },
    renderer: {
      type: "simple",
      // Nearly clear and wide: the boundary draws the line; this makes it easy to select.
      symbol: { type: "simple-line", color: [...BONE, 0.01], width: 8 },
    },
  });
  const points = new GeoJSONLayer({
    url: "data/points.geojson",
    title: "Points",
    copyright: CREDIT,
    outFields: ["*"],
    popupEnabled: popups,
    popupTemplate: {
      outFields: ["*"],
      title: ({ graphic }) => graphic.attributes.point === "Beginning"
        ? "The beginning point"
        : `Point ${Number(graphic.attributes.point)}`,
      content: pointPopup,
    },
    renderer: {
      type: "simple",
      symbol: {
        type: "simple-marker",
        size: 5,
        color: [...BONE, 0.9],
        outline: { color: [...INK, 1], width: 1 },
      },
    },
  });
  const marked = new GraphicsLayer({ title: "Marked" });

  element.map = new Map({
    basemap: hasBasemap ? basemap("map") : null,
    layers: [boundary, steps, marked, points],
  });
  // Web Mercator, as Esri's basemaps are, on the site's ink: a basemap that is
  // missing or refused leaves the line on the page's own background.
  element.spatialReference = { wkid: 3857 };
  element.background = { color: [...INK, 1] };
  element.constraints = { minScale: 1500000, snapToZoom: false };
  // The map's own focusable container takes its name from this property, not
  // from the element's aria-label attribute.
  element.aria = { label: element.getAttribute("aria-label") };
  await element.viewOnReady();
  // A selected step or point is outlined in sand, not the SDK's cyan.
  const selected = element.view?.highlights?.find((h) => h.name === "default");
  if (selected) {
    selected.color = [...SAND, 1];
    selected.haloOpacity = 0.9;
    selected.fillOpacity = 0.2;
  }
  await boundary.load();
  const extent = boundary.fullExtent.clone().expand(1.08);
  await element.goTo(extent, { animate: false });
  return { element, layers: { boundary, steps, points, marked }, extent };
}

// When a map cannot be made (Esri's service or the data did not load), the page
// hides it and shows its note instead; the page's text is untouched.
export function mapFailed(error) {
  console.error("the map could not be drawn", error);
  document.documentElement.classList.remove("js");
}

// The error a goTo gives when a newer move takes over: nothing went wrong.
export const interrupted = (error) => error?.name === "AbortError";

export function setBasemap(element, name) {
  element.map.basemap = basemap(name);
}

// The steps already walked, in sand, up to the one before step.
export function walkedTo(layer, step) {
  layer.renderer = {
    type: "class-breaks",
    field: "step",
    defaultSymbol: { type: "simple-line", color: [...BONE, 0.01], width: 1 },
    classBreakInfos: step > 1
      ? [{
        minValue: 1,
        maxValue: step - 1,
        symbol: { type: "simple-line", color: [...SAND, 0.8], width: 2 },
      }]
      : [],
  };
}

// The marked step: a sand line over the boundary and its end point.
export function markStep(layer, line, end) {
  layer.removeAll();
  if (line) {
    layer.add(new Graphic({
      geometry: line,
      symbol: { type: "simple-line", color: [...SAND, 1], width: 4 },
    }));
  }
  if (end) {
    layer.add(new Graphic({
      geometry: end,
      symbol: {
        type: "simple-marker",
        size: 11,
        color: [...SAND, 1],
        outline: { color: [...INK, 1], width: 2 },
      },
    }));
  }
}
