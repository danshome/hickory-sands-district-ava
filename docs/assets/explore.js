// Explore the map (#113): the proposed revision, its steps and points, with a
// popup for each and, when the site has a basemap key, Esri's basemaps.
import { boundaryMap, hasBasemap, mapFailed, setBasemap } from "./maps.js";

document.documentElement.classList.add("js");
try {
  const element = document.querySelector(".explore-map arcgis-map");
  const { layers } = await boundaryMap(element);
  layers.points.minScale = 400000;

  const switcher = document.querySelector(".map-basemaps");
  if (hasBasemap && switcher) {
    switcher.hidden = false;
    for (const button of switcher.querySelectorAll("button")) {
      button.addEventListener("click", () => {
        for (const other of switcher.querySelectorAll("button")) {
          other.setAttribute("aria-pressed", String(other === button));
        }
        setBasemap(element, button.dataset.basemap);
      });
    }
  }
} catch (error) {
  mapFailed(error);
}
