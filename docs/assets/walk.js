// Walk the line (#112): the page lists every step; as each one reaches the
// reading line, the map marks it and moves to it. Without JavaScript the list
// reads on its own.
import { boundaryMap, markStep, reducedMotion, walkedTo } from "./maps.js";

document.documentElement.classList.add("js");
const element = document.querySelector(".walk-map arcgis-map");
const { layers, extent } = await boundaryMap(element, {
  popups: false,
  quiet: true,
});
// Never closer than about the scale of the 1:24,000 survey maps.
element.constraints = { minScale: 1500000, maxScale: 20000, snapToZoom: false };
const items = [...document.querySelectorAll(".walk-step")];

// Each step's line and end point, looked up once.
const [lines, ends] = await Promise.all([
  layers.steps.queryFeatures({ where: "1=1", outFields: ["step"], returnGeometry: true }),
  layers.points.queryFeatures({ where: "1=1", outFields: ["step"], returnGeometry: true }),
]);
const lineOf = new Map(lines.features.map((f) => [f.attributes.step, f.geometry]));
const endOf = new Map(ends.features.map((f) => [f.attributes.step, f.geometry]));

let current = null;
let moving = null;

function show(step) {
  if (step === current) {
    return;
  }
  current = step;
  for (const item of items) {
    item.classList.toggle("is-current", Number(item.dataset.step) === step);
  }
  const line = lineOf.get(step);
  const end = endOf.get(step);
  walkedTo(layers.steps, step);
  markStep(layers.marked, line, end);
  // The whole line for the beginning point; otherwise the step.
  const target = line ? line.extent.clone().expand(1.8) : extent;
  moving?.abort();
  moving = new AbortController();
  element
    .goTo(target, {
      animate: !reducedMotion,
      duration: 900,
      signal: moving.signal,
    })
    .catch(() => {}); // a newer step took over the move
}

// The reading line: below the map on a phone, mid-screen beside it on a wide
// screen.
const wide = matchMedia("(min-width: 1000px)");
let observer = null;
function observe() {
  observer?.disconnect();
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          show(Number(entry.target.dataset.step));
        }
      }
    },
    { rootMargin: wide.matches ? "-50% 0px -50% 0px" : "-68% 0px -31% 0px" },
  );
  items.forEach((item) => observer.observe(item));
}
observe();
wide.addEventListener("change", observe);
