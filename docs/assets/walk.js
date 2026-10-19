// Walk the line (#112): the page lists every step; as each one reaches the
// reading line, the map marks it and moves to it. Without JavaScript, or when
// the map cannot load, the list reads on its own.
import {
  boundaryMap,
  interrupted,
  mapFailed,
  markStep,
  reducedMotion,
  walkedTo,
} from "./maps.js?v=722b7c5";

document.documentElement.classList.add("js");
try {
  await follow(document.querySelector(".walk-map arcgis-map"));
} catch (error) {
  mapFailed(error);
}

async function follow(element) {
  const { layers, extent } = await boundaryMap(element, { quiet: true });
  // Never closer than about the scale of the 1:24,000 survey maps.
  element.constraints = {
    minScale: 1500000,
    maxScale: 20000,
    snapToZoom: false,
  };
  const items = [...document.querySelectorAll(".walk-step")];

  // Each step's line and end point, looked up once.
  const query = { where: "1=1", outFields: ["step"], returnGeometry: true };
  const [lines, ends] = await Promise.all([
    layers.steps.queryFeatures(query),
    layers.points.queryFeatures(query),
  ]);
  const lineOf = new Map(lines.features.map((f) => [f.attributes.step, f.geometry]));
  const endOf = new Map(ends.features.map((f) => [f.attributes.step, f.geometry]));

  let current = null;
  let moving = null;

  // Analytics (analytics.js's window.hsdTrack, absent or off on most visits):
  // a step counts once it has stayed on the reading line for a second, once
  // per step, so scrolling past many sends nothing for them; the last step
  // reached is the walk complete.
  const total = items.length;
  const last = Math.max(...items.map((item) => Number(item.dataset.step)));
  const counted = new Set();
  let dwell = 0;
  function reached(step) {
    clearTimeout(dwell);
    dwell = setTimeout(() => {
      if (step !== current || counted.has(step)) {
        return;
      }
      counted.add(step);
      window.hsdTrack?.("walk_step", { step, total });
      if (step === last) {
        window.hsdTrack?.("walk_complete", { total });
      }
    }, 1000);
  }

  function show(step) {
    if (step === current) {
      return;
    }
    current = step;
    reached(step);
    for (const item of items) {
      item.classList.toggle("is-current", Number(item.dataset.step) === step);
    }
    const line = lineOf.get(step);
    walkedTo(layers.steps, step);
    markStep(layers.marked, line, endOf.get(step));
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
      .catch((error) => {
        if (!interrupted(error)) {
          console.error("the map could not move to the step", error);
        }
      });
  }

  // The reading line: below the map on a phone, mid-screen beside it on a
  // wide screen.
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
}
