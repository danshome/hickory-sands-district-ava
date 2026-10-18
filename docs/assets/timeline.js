/* The land: the geologic timeline's figure (issue #117).
 *
 * An enhancement only. The eight stages, their ages and their sources are the
 * page's own HTML (docs/land.html) and read the same without this file. With
 * it, a schematic cross-section of the uplift, not to scale, is drawn for one
 * stage at a time, with a time scale and a key. The reader steps through the
 * stages with the Earlier and Later buttons (or the arrow keys, Home and End
 * on them); on wide screens, where the figure stays beside the list,
 * scrolling the list moves the figure too. Every text is set with textContent
 * and every element made with createElement or createElementNS: nothing is
 * parsed as HTML. Smooth scrolling and the fade follow prefers-reduced-motion.
 */
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var W = 600; // the drawing's width and height, in its own units
  var H = 280;
  var DX = 4; // the step along x at which the layers' outlines are sampled
  var OLDEST = 1400; // the time scale's left end, millions of years ago

  var body = document.querySelector(".geo-body");
  var list = body ? body.querySelector(".geo-stages") : null;
  if (!list || !window.matchMedia || !document.createElementNS) {
    return;
  }
  var items = Array.prototype.slice.call(list.querySelectorAll(".geo-stage"));
  if (items.length !== 8) {
    return; // the drawings below are made for these eight stages
  }
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  var wide = window.matchMedia("(min-width: 1000px)");

  /* The section as functions of x; y grows downward. */

  function bell(x, centre, width) {
    var t = (x - centre) / width;
    return Math.exp(-t * t);
  }

  function ramp(x, a, b) {
    var t = Math.min(1, Math.max(0, (x - a) / (b - a)));
    return t * t * (3 - 2 * t);
  }

  // Stage 1: the mountains of the collision.
  function peaks(x) {
    return 92 + 24 * Math.sin(x / 47 + 1) + 12 * Math.sin(x / 19) +
      5 * Math.sin(x / 7.3);
  }

  // From stage 2: the worn basement, granite knobs and hollows.
  function knobs(x) {
    return 196 - 30 * bell(x, 118, 26) - 26 * bell(x, 262, 30) -
      30 * bell(x, 352, 24) - 24 * bell(x, 478, 28) + 3 * Math.sin(x / 21);
  }

  // The tops of the later layers as they were laid down, flat.
  var HICKORY = 170;
  var RILEY = 156;
  var WILBERNS = 142;
  var ELLENBURGER = 124;
  var CUT = 104; // the worn surface the Cretaceous sea flooded
  var CRETACEOUS = 74; // the top of the Cretaceous cover
  var FAULTS = [190, 420];
  var PLUTONS = [[118, 46], [262, 40], [352, 44], [478, 40]];
  var SEA = { 3: 132, 4: 98, 6: 52 };

  // From stage 5: the dome, and two faults with their outer blocks down.
  function lift(stage, x) {
    if (stage < 5) {
      return 0;
    }
    return -72 * bell(x, 300, 170) + (x < FAULTS[0] ? 8 : 0) +
      (x > FAULTS[1] ? 6 : 0);
  }

  // From stage 7: the land now, a lowland inside a rim of Cretaceous rock.
  function landNow(x) {
    var low = ramp(x, 40, 92) * (1 - ramp(x, 508, 560));
    return CRETACEOUS + (62 + 3 * Math.sin(x / 29)) * low;
  }

  function surface(stage, x) {
    if (stage === 1) {
      return peaks(x);
    }
    if (stage === 2) {
      return knobs(x);
    }
    if (stage === 3) {
      return Math.min(HICKORY, knobs(x));
    }
    if (stage === 4) {
      return ELLENBURGER;
    }
    if (stage === 5) {
      return ELLENBURGER + lift(5, x);
    }
    if (stage === 6) {
      return CRETACEOUS;
    }
    return landNow(x);
  }

  /* Drawing. */

  function sample(f, from, to) {
    var points = [];
    for (var x = from || 0; x <= (to === undefined ? W : to); x += DX) {
      points.push([x, f(x)]);
    }
    return points;
  }

  function coords(points) {
    return points.map(function (p) {
      return p[0].toFixed(1) + "," + p[1].toFixed(1);
    }).join(" ");
  }

  function band(top, bottom) {
    return coords(sample(top).concat(sample(bottom).reverse()));
  }

  function svg(name, attrs, parent) {
    var node = document.createElementNS(SVG_NS, name);
    Object.keys(attrs).forEach(function (key) {
      node.setAttribute(key, attrs[key]);
    });
    if (parent) {
      parent.appendChild(node);
    }
    return node;
  }

  function shape(parent, cls, fill, points) {
    var attrs = { points: points };
    if (cls) {
      attrs["class"] = cls;
    }
    if (fill) {
      attrs.fill = fill;
    }
    return svg("polygon", attrs, parent);
  }

  function line(parent, cls, points) {
    return svg("polyline", { "class": cls, points: coords(points) }, parent);
  }

  function flat(y) {
    return function () {
      return y;
    };
  }

  function defs(root) {
    var d = svg("defs", {}, root);
    function pattern(id, w, h) {
      var p = svg("pattern", {
        id: "geo-p-" + id, width: w, height: h, patternUnits: "userSpaceOnUse"
      }, d);
      svg("rect", { "class": "geo-f-" + id, width: w, height: h }, p);
      return p;
    }
    svg("path", { "class": "geo-m-gneiss", d: "M0 6Q10 2 20 6T40 6" },
      pattern("gneiss", 40, 12));
    svg("path", {
      "class": "geo-m-granite", d: "M2 5h5M4.5 2.5v5M11 14h5M13.5 11.5v5"
    }, pattern("granite", 18, 18));
    var sand = pattern("hickory", 11, 9);
    svg("circle", { "class": "geo-m-hickory", cx: 2.5, cy: 2.5, r: 0.9 }, sand);
    svg("circle", { "class": "geo-m-hickory", cx: 8, cy: 6.5, r: 0.7 }, sand);
    ["riley", "wilberns", "ellen"].forEach(function (id) {
      svg("path", {
        "class": "geo-m-lime", d: "M0 .5H24M0 6.5H24M8 .5V6.5M20 6.5V12"
      }, pattern(id, 24, 12));
    });
    svg("path", {
      "class": "geo-m-cret", d: "M0 .5H28M0 7.5H28M10 .5V7.5M24 7.5V14"
    }, pattern("cret", 28, 14));
    svg("path", { "class": "geo-m-water", d: "M0 3H10" }, pattern("water", 10, 6));
  }

  function draw(stage) {
    var g = svg("g", { "class": "geo-art" });
    var base = stage === 1 ? peaks : knobs;
    function at(f) {
      return function (x) {
        return f(x) + lift(stage, x);
      };
    }

    // The later layers first: the basement is drawn over them, so a granite
    // knob that stood above the sand shows through it.
    if (stage >= 3) {
      shape(g, "geo-layer", "url(#geo-p-hickory)", band(at(flat(HICKORY)),
        at(function (x) {
          return Math.max(knobs(x), HICKORY);
        })));
    }
    if (stage >= 4) {
      [[RILEY, HICKORY, "riley"], [WILBERNS, RILEY, "wilberns"],
        [ELLENBURGER, WILBERNS, "ellen"]].forEach(function (layer) {
        shape(g, "geo-layer", "url(#geo-p-" + layer[2] + ")",
          band(at(flat(layer[0])), at(flat(layer[1]))));
      });
    }
    shape(g, "geo-layer", "url(#geo-p-gneiss)", band(at(base), flat(H + 10)));
    PLUTONS.forEach(function (pluton) {
      var points = [];
      for (var x = pluton[0] - pluton[1]; x <= pluton[0] + pluton[1]; x += 2) {
        var t = (x - pluton[0]) / pluton[1];
        points.push([x, Math.max(150 + 70 * t * t, base(x)) + lift(stage, x)]);
      }
      points.push([pluton[0] + pluton[1], H + 10], [pluton[0] - pluton[1], H + 10]);
      shape(g, "geo-layer", "url(#geo-p-granite)", coords(points));
    });
    if (stage >= 3) {
      line(g, "geo-unconformity", sample(at(knobs)));
    }
    if (stage >= 5) {
      FAULTS.forEach(function (x) {
        svg("line", { "class": "geo-fault", x1: x, y1: 0, x2: x, y2: H }, g);
      });
    }
    if (stage >= 6) {
      shape(g, "geo-layer", "url(#geo-p-cret)", band(flat(CRETACEOUS),
        function (x) {
          return Math.max(CUT, ELLENBURGER + lift(stage, x));
        }));
    }

    // Everything above the land surface of the stage is air or sea.
    var ground = sample(function (x) {
      return surface(stage, x);
    });
    shape(g, "geo-sky", null, coords([[0, -10]].concat(ground, [[W, -10]])));
    if (SEA[stage]) {
      shape(g, null, "url(#geo-p-water)",
        coords([[0, SEA[stage]], [W, SEA[stage]]].concat(ground.slice().reverse())));
      line(g, "geo-sea", [[0, SEA[stage]], [W, SEA[stage]]]);
    }
    line(g, stage === 2 ? "geo-unconformity" : "geo-ground", ground);

    if (stage === 8) {
      today(g);
    }
    return g;
  }

  // Stage 8: sandy soil on the outcrop of the Hickory Sandstone Member, rain
  // into it, and water held in it where it dips under younger rock.
  function today(g) {
    var runs = [[], []];
    function top(x) {
      return HICKORY + lift(8, x);
    }
    function bottom(x) {
      return Math.max(knobs(x), HICKORY) + lift(8, x);
    }
    for (var x = 2; x < W; x += 6) {
      var s = landNow(x);
      if (s >= top(x) && s <= bottom(x)) {
        svg("circle", { "class": "geo-soil", cx: x, cy: (s + 2.5).toFixed(1), r: 1.5 }, g);
        svg("circle", { "class": "geo-soil", cx: x + 3, cy: (s + 5.5).toFixed(1), r: 1.1 }, g);
        runs[x < 300 ? 0 : 1].push(x);
      }
    }
    runs.forEach(function (run, side) {
      if (!run.length) {
        return;
      }
      var x = run[Math.floor(run.length / 2)];
      var s = landNow(x);
      svg("line", { "class": "geo-arrow", x1: x, y1: s - 32, x2: x, y2: s - 12 }, g);
      shape(g, "geo-arrow", null, coords([[x - 4, s - 14], [x + 4, s - 14], [x, s - 6]]));
      var from = side === 0 ? 16 : run[run.length - 1] + 14;
      var to = side === 0 ? run[0] - 14 : W - 16;
      line(g, "geo-aquifer", sample(function (u) {
        return (top(u) + bottom(u)) / 2;
      }, from, to));
    });
  }

  /* The figure. */

  var KEY = {
    water: "Sea",
    soil: "Sandy soil",
    aquifer: "Water in the Hickory Aquifer",
    cret: "Cretaceous rock",
    later: "Later Cambrian and Ordovician rock",
    hickory: "Hickory Sandstone Member",
    unconformity: "Great Unconformity",
    fault: "Faults",
    granite: "Granite",
    gneiss: "Gneiss and schist"
  };
  var KEYS = [
    [],
    ["granite", "gneiss"],
    ["unconformity", "granite", "gneiss"],
    ["water", "hickory", "unconformity", "granite", "gneiss"],
    ["water", "later", "hickory", "unconformity", "granite", "gneiss"],
    ["later", "hickory", "unconformity", "fault", "granite", "gneiss"],
    ["water", "cret", "later", "hickory", "unconformity", "fault", "granite",
      "gneiss"],
    ["cret", "later", "hickory", "unconformity", "fault", "granite", "gneiss"],
    ["soil", "aquifer", "cret", "later", "hickory", "unconformity", "fault",
      "granite", "gneiss"]
  ];

  function el(tag, cls, words) {
    var node = document.createElement(tag);
    if (cls) {
      node.className = cls;
    }
    if (words) {
      node.textContent = words;
    }
    return node;
  }

  var stages = items.map(function (li, i) {
    var title = li.querySelector("h3");
    var age = li.querySelector(".geo-age");
    return {
      li: li,
      index: (i < 9 ? "0" : "") + (i + 1),
      title: title ? title.textContent.trim() : "",
      age: age ? age.textContent.trim() : "",
      from: parseFloat(li.getAttribute("data-from")) || 0,
      to: parseFloat(li.getAttribute("data-to")) || 0
    };
  });

  var figure = el("figure", "geo-figure");
  var art = svg("svg", {
    "class": "geo-svg", viewBox: "0 0 " + W + " " + H, "aria-hidden": "true",
    focusable: "false"
  });
  defs(art);
  figure.appendChild(art);

  var scale = el("div", "geo-scale");
  scale.setAttribute("aria-hidden", "true");
  var bar = el("div", "geo-scale-bar");
  var spans = stages.map(function (s) {
    var span = el("span", "geo-scale-span");
    var width = Math.max(0.8, (s.from - s.to) / OLDEST * 100);
    span.style.left = Math.min((OLDEST - s.from) / OLDEST * 100, 100 - width) + "%";
    span.style.width = width + "%";
    bar.appendChild(span);
    return span;
  });
  scale.appendChild(bar);
  var ticks = el("div", "geo-scale-ticks");
  [[1400, "1,400"], [1000, "1,000"], [500, "500"], [0, "Today"]].forEach(function (t) {
    var tick = el("span", null, t[1]);
    tick.style.left = (OLDEST - t[0]) / OLDEST * 100 + "%";
    ticks.appendChild(tick);
  });
  scale.appendChild(ticks);
  scale.appendChild(el("p", "geo-scale-unit", "Millions of years ago"));
  figure.appendChild(scale);

  var caption = el("figcaption");
  var now = el("p", "geo-now");
  var nowTitle = el("span", "geo-now-title");
  var nowAge = el("span", "geo-now-age");
  now.appendChild(nowTitle);
  now.appendChild(document.createTextNode(" "));
  now.appendChild(nowAge);
  var key = el("ul", "geo-key");
  caption.appendChild(now);
  caption.appendChild(key);
  caption.appendChild(el("p", "geo-note",
    "A schematic section across the uplift, not to scale."));
  figure.appendChild(caption);

  var current = 0;
  var hold = 0; // until then, scrolling the list does not move the figure

  function stepper(label, arrow, by) {
    var button = el("button", "geo-step");
    button.type = "button";
    button.setAttribute("aria-label", label + " stage");
    var mark = el("span", null, arrow);
    mark.setAttribute("aria-hidden", "true");
    if (by < 0) {
      button.appendChild(mark);
    }
    button.appendChild(document.createTextNode(label));
    if (by > 0) {
      button.appendChild(mark);
    }
    button.addEventListener("click", function () {
      if (button.getAttribute("aria-disabled") !== "true") {
        go(current + by);
      }
    });
    return button;
  }

  var controls = el("div", "geo-controls");
  controls.setAttribute("role", "group");
  controls.setAttribute("aria-label", "Step through the stages");
  var earlier = stepper("Earlier", "←", -1);
  var count = el("span", "geo-count");
  count.setAttribute("aria-hidden", "true");
  var later = stepper("Later", "→", 1);
  controls.appendChild(earlier);
  controls.appendChild(count);
  controls.appendChild(later);
  controls.addEventListener("keydown", function (event) {
    var keys = { ArrowLeft: current - 1, ArrowRight: current + 1, Home: 1, End: 8 };
    if (!Object.prototype.hasOwnProperty.call(keys, event.key)) {
      return;
    }
    event.preventDefault();
    go(keys[event.key]);
  });
  caption.appendChild(controls); // the figcaption stays the figure's last child

  var live = el("p", "geo-live");
  live.setAttribute("aria-live", "polite");
  caption.appendChild(live);

  function show(n, announce) {
    if (n < 1 || n > 8 || n === current) {
      return false;
    }
    current = n;
    var s = stages[n - 1];
    var old = art.querySelector(".geo-art");
    if (old) {
      art.removeChild(old);
    }
    art.appendChild(draw(n));
    nowTitle.textContent = s.title;
    nowAge.textContent = s.age;
    count.textContent = s.index + " / 08";
    while (key.firstChild) {
      key.removeChild(key.firstChild);
    }
    KEYS[n].forEach(function (k) {
      var item = el("li");
      var swatch = el("span", "geo-swatch geo-sw-" + k);
      swatch.setAttribute("aria-hidden", "true");
      item.appendChild(swatch);
      item.appendChild(document.createTextNode(KEY[k]));
      key.appendChild(item);
    });
    spans.forEach(function (span, i) {
      span.classList.toggle("geo-on", i === n - 1);
    });
    items.forEach(function (li, i) {
      li.classList.toggle("geo-current", i === n - 1);
    });
    earlier.setAttribute("aria-disabled", String(n === 1));
    later.setAttribute("aria-disabled", String(n === 8));
    if (announce) {
      live.textContent = "Stage " + n + " of 8: " + s.title + ". " + s.age + ".";
    }
    return true;
  }

  function go(n) {
    if (!show(n, true) || !wide.matches) {
      return;
    }
    hold = Date.now() + 1200;
    stages[n - 1].li.scrollIntoView({
      block: "center", behavior: reduce.matches ? "auto" : "smooth"
    });
  }

  // Drawn before it goes in, so a failure leaves the list as it was.
  show(1, false);
  body.insertBefore(figure, list);
  body.classList.add("geo-has-figure");

  // Beside the list, the figure follows the stage at the middle of the screen.
  if ("IntersectionObserver" in window) {
    var watch = new IntersectionObserver(function (entries) {
      if (!wide.matches || Date.now() < hold) {
        return;
      }
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          show(items.indexOf(entry.target) + 1, false);
        }
      });
    }, { rootMargin: "-45% 0px -54% 0px" });
    items.forEach(function (li) {
      watch.observe(li);
    });
  }
})();
