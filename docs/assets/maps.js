// The site's 2D maps: Walk the line (#112) and the vineyard form's pin map.
// The proposed revision from data/ (made by the build), drawn with Esri's
// ArcGIS Maps SDK for JavaScript, which the page loads from js.arcgis.com. The
// map with a popup for every step and point is map.html (map3d-district.js).
// Text from the data is only ever set as text, never parsed as HTML.
import { apiKey } from "./map-config.js?v=999720b";

const load = (name) => $arcgis.import(`@arcgis/core/${name}.js`);
const [config, Map, Basemap, GeoJSONLayer, GraphicsLayer, Graphic, Viewpoint] =
  await Promise.all(
    ["config", "Map", "Basemap", "layers/GeoJSONLayer", "layers/GraphicsLayer",
      "Graphic", "Viewpoint"].map(load),
  );

export const reducedMotion =
  matchMedia("(prefers-reduced-motion: reduce)").matches;
export const hasBasemap = apiKey !== "";
// A phone, or any touch screen: the map's buttons at the SDK's large size.
const touchSized = matchMedia("(max-width: 699px), (pointer: coarse)");

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

// Makes the map in an <arcgis-map> element: the boundary, its steps and its
// points, and a layer for whatever the page marks. A quiet map draws the
// boundary in bone, leaving the sand for the steps the page marks. Returns the
// element, the layers and the boundary's extent. Its steps and points have no
// popups: the pages that use it follow the line or place a pin.
export async function boundaryMap(element, { quiet = false } = {}) {
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
    popupEnabled: false,
    renderer: {
      type: "simple",
      // Nearly clear: the boundary draws the line; a page marks steps on it.
      symbol: { type: "simple-line", color: [...BONE, 0.01], width: 8 },
    },
  });
  const points = new GeoJSONLayer({
    url: "data/points.geojson",
    title: "Points",
    copyright: CREDIT,
    outFields: ["*"],
    popupEnabled: false,
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
  // Home goes back to the whole line, whatever the map's size by then.
  const home = element.querySelector("arcgis-home");
  if (home) {
    home.viewpoint = new Viewpoint({ targetGeometry: extent });
  }
  sizeControls(element);
  touchSized.addEventListener("change", () => sizeControls(element));
  return { element, layers: { boundary, steps, points, marked }, extent };
}

// On a phone or a touch screen the map's buttons are the SDK's large ones.
function sizeControls(element) {
  const large = touchSized.matches;
  for (const control of element.querySelectorAll("arcgis-zoom, arcgis-home")) {
    control.visualScale = large ? "l" : "m";
  }
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
