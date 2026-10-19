// The map's address (map.html): which groups are on, where the view opens,
// how it is seen, the basemap, and a step or point to open. Read once when the
// page loads, before anything else; the layers and the basemap are written
// back as the reader changes them, so a copied address opens the same map.
// A word the page does not know is left out, never shown. No Esri code here,
// so node can test it on its own.

// The panel's groups, in its order (the order they are drawn, sky to rock).
export const GROUPS = [
  "district",
  "places",
  "wells",
  "vineyards",
  "boundaries",
  "geology",
  "aquifer",
];
// The groups drawn below the ground: with one of them on, the ground is
// see-through, the view tilts and the heights are exaggerated.
export const UNDERGROUND = ["aquifer", "wells"];
export const BASEMAPS = ["imagery", "topo", "dark"];
// The water: the menu's "The water", The land's link and the old
// aquifer.html all open this.
export const WATER = "map.html?layers=aquifer,vineyards,places";

const word = (value) => String(value || "").trim().toLowerCase();

/**
 * Reads the map's state from a query string (location.search).
 *
 * layers: a comma-separated list of groups to turn on, besides the district
 *   (always on when the page opens); "all" turns on every group.
 * view: "district" or "whole" (the whole aquifer); by default the whole
 *   aquifer when the aquifer is on, else the district.
 * look: "2d" (straight down, as a map reads) or "3d" (tilted); by default 3d
 *   when a group below the ground is on, else 2d.
 * basemap: "imagery", "topo" or "dark"; by default dark when a group below
 *   the ground is on, else imagery.
 * step, point: a step's number, or a point's number or "beginning", whose
 *   popup opens.
 */
export function readState(search) {
  const query = new URLSearchParams(search);
  const layers = new Set(["district"]);
  for (const w of word(query.get("layers")).split(",").map((v) => v.trim())) {
    if (w === "all") {
      GROUPS.forEach((g) => layers.add(g));
    } else if (GROUPS.includes(w)) {
      layers.add(w);
    }
  }
  const under = UNDERGROUND.some((g) => layers.has(g));
  const pick = (name, allowed, fallback) => {
    const v = word(query.get(name));
    return allowed.includes(v) ? v : fallback;
  };
  const number = (v) => (/^\d{1,3}$/.test(v) ? Number(v) : null);
  const point = word(query.get("point"));
  return {
    layers,
    // Opened as the water: the menu marks "The water" and the panel is
    // headed "The Hickory Aquifer".
    water: layers.has("aquifer"),
    place: pick("view", ["district", "whole"], layers.has("aquifer") ? "whole" : "district"),
    look: pick("look", ["2d", "3d"], under ? "3d" : "2d"),
    basemap: pick("basemap", BASEMAPS, under ? "dark" : "imagery"),
    step: number(word(query.get("step"))),
    point: point === "beginning" ? "Beginning" : number(point),
  };
}

/**
 * Returns the query string for the groups on and the basemap, keeping the
 * address's other words (view, look, step, point).
 */
export function writeState(search, { layers, basemap }) {
  const query = new URLSearchParams(search);
  const on = GROUPS.filter((g) => g !== "district" && layers.has(g));
  if (on.length) {
    query.set("layers", on.join(","));
  } else {
    query.delete("layers");
  }
  const under = UNDERGROUND.some((g) => layers.has(g));
  if (basemap === (under ? "dark" : "imagery")) {
    query.delete("basemap");
  } else {
    query.set("basemap", basemap);
  }
  const text = query.toString().replaceAll("%2C", ",");
  return text ? `?${text}` : "";
}
