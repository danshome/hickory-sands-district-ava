// The proposed revision on the map (map.html): the boundary, its steps and
// its points from data/ (made by the build), with a popup for every step and
// point, as the Explore page had them (#113), and a link from each to the
// same step in Walk the line. Text from the data is only ever set as text,
// never parsed as HTML.

const SAND = [199, 151, 111];
const BONE = [238, 232, 219];
const INK = [20, 21, 18];
const CREDIT = "Hickory Sands District petitioners (CC0)";

// A popup's content: rows of a label and a value, then the step's text and a
// link. The popup draws inside its own shadow DOM, where the site's
// stylesheet does not reach, so the few styles are set here.
const LABEL = "font-size:.75rem;letter-spacing:.12em;text-transform:uppercase;" +
  "opacity:.7;margin-right:.4rem";
const ROW = "margin:.15rem 0;font-size:.8125rem;line-height:1.45";
const TEXT = "margin:.8rem 0 0;font-family:'Cormorant Garamond',Georgia,serif;" +
  "font-size:1.125rem;line-height:1.4";
const LINK = "display:inline-flex;align-items:center;min-height:44px;" +
  "font-size:.8125rem;color:inherit";

function described(rows, text, walk) {
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
  if (walk) {
    const p = document.createElement("p");
    p.style.cssText = "margin:.4rem 0 0";
    const a = document.createElement("a");
    a.style.cssText = LINK;
    a.href = `walk.html#${walk.anchor}`;
    a.textContent = `${walk.text} →`;
    p.append(a);
    box.append(p);
  }
  return box;
}

const miles = (metres) => `${(metres / 1609.344).toFixed(1)} mi`;

function stepPopup({ graphic }) {
  const a = graphic.attributes;
  const n = Number(a.step);
  return described(
    [["Quadrangle", a.quad], ["Length", miles(a.length_m)], ["Ends", a.endpoint]],
    a.narrative,
    { anchor: `step-${n}`, text: "Walk the line from this step" },
  );
}

function pointPopup({ graphic }) {
  const a = graphic.attributes;
  const first = a.point === "Beginning";
  return described([["Quadrangle", a.quad]], a.point_name, first
    ? { anchor: "beginning", text: "Walk the line from the beginning" }
    : { anchor: `step-${Number(a.step)}`, text: `Read step ${Number(a.step)} in Walk the line` });
}

/**
 * Makes the district's three layers, on the ground: the boundary (its fill),
 * its steps (the line itself: sand with a dark casing, so it reads on the
 * imagery, the topographic map and the dark map alike, and a nearly clear
 * wide band that makes it easy to select) and its points (from about a
 * 1:400,000 scale in). A scene's polygons take no line symbols, so the steps
 * draw the line.
 */
export function districtLayers(GeoJSONLayer, { touch = false } = {}) {
  const boundary = new GeoJSONLayer({
    url: "data/boundary.geojson",
    title: "Proposed revision",
    copyright: CREDIT,
    geometryType: "polygon",
    elevationInfo: { mode: "on-the-ground" },
    popupEnabled: false,
    labelingInfo: [
      {
        labelExpressionInfo: { expression: JSON.stringify("Hickory Sands District (proposed)") },
        // Only zoomed far out, where the line alone is hard to find.
        maxScale: 700000,
        symbol: {
          type: "label-3d",
          symbolLayers: [{
            type: "text",
            material: { color: SAND },
            halo: { color: [...INK, 0.85], size: 1.2 },
            size: 11,
            font: { family: "Noto Sans", weight: "bold" },
          }],
        },
      },
    ],
    renderer: {
      type: "simple",
      symbol: {
        type: "polygon-3d",
        symbolLayers: [{ type: "fill", material: { color: [...SAND, 0.08] } }],
      },
    },
  });
  const steps = new GeoJSONLayer({
    url: "data/steps.geojson",
    title: "Steps",
    copyright: CREDIT,
    geometryType: "polyline",
    elevationInfo: { mode: "on-the-ground" },
    outFields: ["*"],
    popupTemplate: {
      // Built by functions, so the popup must be told to fetch every field.
      outFields: ["*"],
      title: ({ graphic }) => `Step ${Number(graphic.attributes.step)}`,
      content: stepPopup,
    },
    renderer: {
      type: "simple",
      symbol: {
        type: "line-3d",
        symbolLayers: [
          { type: "line", material: { color: [...BONE, 0.01] }, size: touch ? 14 : 9 },
          { type: "line", material: { color: [...INK, 0.6] }, size: 5, cap: "round", join: "round" },
          { type: "line", material: { color: [...SAND, 1] }, size: 2.5, cap: "round", join: "round" },
        ],
      },
    },
  });
  const points = new GeoJSONLayer({
    url: "data/points.geojson",
    title: "Points",
    copyright: CREDIT,
    geometryType: "point",
    elevationInfo: { mode: "on-the-ground" },
    outFields: ["*"],
    minScale: 400000,
    screenSizePerspectiveEnabled: false,
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
        type: "point-3d",
        symbolLayers: [{
          type: "icon",
          resource: { primitive: "circle" },
          material: { color: [...BONE, 0.95] },
          outline: { color: [...INK, 1], size: 1 },
          size: touch ? 9 : 6,
        }],
      },
    },
  });
  return { boundary, steps, points };
}

/**
 * Opens a step's or a point's popup, from the address (map.html?step=12 or
 * ?point=beginning): the view moves to it, keeping its angle. The popup is
 * the scene's slotted <arcgis-popup>, which the scene element's openPopup
 * opens (the view's own openPopup would open a second, unstyled one).
 */
export async function openFeature(scene, { steps, points }, { step, point }, reducedMotion) {
  const view = scene.view;
  const layer = step !== null ? steps : points;
  const where = step !== null
    ? `step = ${Number(step)}`
    : point === "Beginning" ? "point = 'Beginning'" : `point = '${Number(point)}'`;
  const found = await layer.queryFeatures({ where, outFields: ["*"], returnGeometry: true });
  const feature = found.features[0];
  if (!feature) {
    return false;
  }
  const g = feature.geometry;
  let location = g;
  let target = g;
  if (g.type === "polyline") {
    const path = g.paths[0];
    const k = Math.floor((path.length - 1) / 2);
    location = g.getPoint(0, k);
    location.x = (path[k][0] + path[k + 1][0]) / 2;
    location.y = (path[k][1] + path[k + 1][1]) / 2;
    target = g.extent.clone().expand(2.5);
  } else {
    target = { target: g, scale: 60000 };
  }
  await view.goTo(target, { animate: !reducedMotion, duration: 1200 }).catch(() => {});
  await scene.openPopup({ features: [feature], location });
  return true;
}

/**
 * On a narrow view the popup docks along the bottom, over the step just
 * tapped. While it is docked there the view's bottom is padded by its
 * height (through setBottom, which adds the panel's own padding), so the
 * view's centre is the part left above it and the place tapped moves to its
 * middle. Closed, the padding goes again. Ported from maps.js (Explore).
 */
export function keepSelectedInView(view, popup, { setBottom, reducedMotion }) {
  let box = null; // the popup's visible part, in its shadow DOM
  let shown = null; // the place last moved to, and the padding then
  let moving = null;
  let current = 0;
  const resized = new ResizeObserver(() => fit());

  function dockedHeight() {
    const found = popup.shadowRoot?.querySelector(".main-container") ?? null;
    if (found !== box) {
      resized.disconnect();
      box = found;
      if (box) {
        resized.observe(box);
      }
    }
    const docked = popup.open && popup.dockEnabled &&
      String(popup.currentDockPosition ?? "").startsWith("bottom");
    return docked && box ? Math.ceil(box.getBoundingClientRect().height) : 0;
  }

  // The point drawn at the middle of the part left becomes the centre, so
  // the picture stays put when the padding changes.
  function pad(bottom) {
    const still = view.toMap({ x: view.width / 2, y: (view.height - bottom) / 2 });
    current = bottom;
    setBottom(bottom);
    if (still) {
      view.center = still;
    }
  }

  async function fit() {
    await new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
    const bottom = dockedHeight();
    if (current !== bottom) {
      pad(bottom);
    }
    const place = bottom ? popup.location : null;
    if (!place) {
      shown = null;
      return;
    }
    if (shown?.place === place && shown.bottom === bottom) {
      return;
    }
    shown = { place, bottom };
    moving?.abort();
    moving = new AbortController();
    view
      .goTo({ center: place }, { animate: !reducedMotion, duration: 450, signal: moving.signal })
      .catch((error) => {
        if (error?.name !== "AbortError") {
          console.error("the map could not show the selected step", error);
        }
      });
  }

  popup.addEventListener("arcgisPropertyChange", (event) => {
    if (["open", "selectedFeature", "collapsed"].includes(event.detail?.name)) {
      fit();
    }
  });
}
