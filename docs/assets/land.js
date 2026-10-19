/* The land: the slice through the district (part of TWDB's section line A–A′, model row 239).
 *
 * An enhancement only. The six steps, their keys and their sources are the
 * page's own HTML (docs/land.html), and the build's static drawing
 * (assets/land/section.svg, every layer shown) stands in the figure, so the
 * page reads the same without this file. With it, the slice is drawn from
 * the build's data (assets/land/section.json, src/site/make_land.py) at the
 * figure's own width, so its text is true CSS pixels, and drawn again when
 * the width changes. Each step reveals one layer: the ground, the sandstone,
 * the aquifer, the core and the younger rock, the wells, the district.
 * Where the figure stays in view (beside the steps on a wide screen, stuck
 * to the top as a short panel on a phone held upright) scrolling the steps
 * moves it, as the timeline does (timeline.js); elsewhere the Back and Next
 * buttons (or the arrow keys, Home and End on them) do. Every element is
 * made with createElement or createElementNS and every text set with
 * textContent: nothing is parsed as HTML. Smooth scrolling and the fades
 * follow prefers-reduced-motion.
 */
(function () {
  "use strict";

  var NS = "http://www.w3.org/2000/svg";
  var body = document.querySelector(".lnd-sec-body");
  if (!body || !window.matchMedia || !window.fetch ||
      !document.createElementNS) {
    return;
  }
  var fig = body.querySelector(".lnd-fig");
  var art = fig.querySelector(".lnd-art");
  var nowTitle = fig.querySelector(".lnd-now");
  var items = Array.prototype.slice.call(body.querySelectorAll(".lnd-step"));
  var STEPS = items.length;
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  var wide = window.matchMedia("(min-width: 1000px)");
  // A phone held upright, as timeline.js has it; land.css has the same query.
  var tall = window.matchMedia(
    "screen and (max-width: 999px) and (min-height: 520px) and " +
    "(orientation: portrait)");
  function follows() {
    return wide.matches || tall.matches;
  }

  // The wells' colours by the data's classes: granite, metamorphic,
  // sandstone, limestone (or dolomite), other, unlogged, sand.
  var COLOURS = ["#b5485e", "#7b5ea7", "#a8820f", "#5b8a57", "#a3906f",
    "#9a958c", "#d8bd55"];

  function svg(name, attrs, parent) {
    var node = document.createElementNS(NS, name);
    Object.keys(attrs).forEach(function (k) {
      node.setAttribute(k, attrs[k]);
    });
    if (parent) {
      parent.appendChild(node);
    }
    return node;
  }

  function text(parent, x, y, words, cls, anchor) {
    var t = svg("text", { x: x, y: y, "text-anchor": anchor || "start" },
      parent);
    if (cls) {
      t.setAttribute("class", cls);
    }
    t.textContent = words;
    return t;
  }

  function fmt(n) {
    return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ",")
      .replace("-", "−");
  }

  function start(S) {
    var gs = S.ground.map(function (g) { return g[0]; });
    var gz = S.ground.map(function (g) { return g[1]; });

    function ground(s) {
      if (s <= gs[0]) {
        return gz[0];
      }
      if (s >= gs[gs.length - 1]) {
        return gz[gz.length - 1];
      }
      var lo = 0;
      var hi = gs.length - 1;
      while (hi - lo > 1) {
        var mid = (lo + hi) >> 1;
        if (gs[mid] <= s) {
          lo = mid;
        } else {
          hi = mid;
        }
      }
      return gz[lo] + (gz[hi] - gz[lo]) * (s - gs[lo]) / (gs[hi] - gs[lo]);
    }

    function samples(a, b) {
      var out = [a];
      gs.forEach(function (s) {
        if (s > a && s < b) {
          out.push(s);
        }
      });
      out.push(b);
      return out;
    }

    // A column: [s0, s1, hickory top, hickory bottom, base top, top layer].
    // The topmost unit of a column runs to the 3DEP ground, so no gap is
    // left between the model's top and the ground.
    var units = {
      younger: {
        has: function (c) { return c[5] < 7; },
        top: function (c, s) { return ground(s); },
        bot: function (c, s) {
          return Math.min(c[2] !== null ? c[2] : c[4], ground(s));
        }
      },
      hickory: {
        has: function (c) { return c[2] !== null; },
        top: function (c, s) {
          return c[5] === 7 ? ground(s) : Math.min(c[2], ground(s));
        },
        bot: function (c, s) { return Math.min(c[3], ground(s)); }
      },
      core: {
        has: function () { return true; },
        top: function (c, s) {
          return c[5] === 8 ? ground(s) : Math.min(c[4], ground(s));
        },
        bot: function () { return S.z_base; }
      }
    };

    var current = 1;
    var layers = []; // [group, the step it appears at]

    function apply(animate) {
      layers.forEach(function (l) {
        l[0].classList.toggle("lnd-wait", current < l[1]);
        if (!animate) {
          l[0].style.transition = "none";
          l[0].getBoundingClientRect();
          l[0].style.transition = "";
        }
      });
    }

    function draw() {
      var w = Math.round(art.clientWidth);
      if (w < 120) {
        return;
      }
      var narrow = w < 560;
      var ML = narrow ? 36 : 54;
      var MR = narrow ? 8 : 14;
      var MT = narrow ? 34 : 46;
      var MB = narrow ? 26 : 38;
      var pw = w - ML - MR;
      var kx = pw / S.length_ft;
      var ky = kx * S.ve;
      var h = Math.round(MT + (S.z_top - S.z_base) * ky + MB);
      function X(s) { return ML + s * kx; }
      function Y(z) { return MT + (S.z_top - z) * ky; }
      function pt(s, z) { return X(s).toFixed(1) + "," + Y(z).toFixed(1); }

      var root = svg("svg", {
        viewBox: "0 0 " + w + " " + h, width: w, height: h,
        "aria-hidden": "true", focusable: "false"
      });
      var defs = svg("defs", {}, root);
      var p = svg("pattern", { id: "lnd-p-sand", width: 7, height: 6,
        patternUnits: "userSpaceOnUse" }, defs);
      svg("rect", { width: 7, height: 6, fill: "#c7976f" }, p);
      svg("circle", { cx: 1.5, cy: 1.5, r: 0.7, fill: "#8f6646" }, p);
      svg("circle", { cx: 5, cy: 4.5, r: 0.55, fill: "#8f6646" }, p);
      p = svg("pattern", { id: "lnd-p-water", width: 7, height: 6,
        patternUnits: "userSpaceOnUse" }, defs);
      svg("rect", { width: 7, height: 6, fill: "#6d8c86" }, p);
      svg("circle", { cx: 1.5, cy: 1.5, r: 0.7, fill: "#93aca6" }, p);
      svg("circle", { cx: 5, cy: 4.5, r: 0.55, fill: "#93aca6" }, p);
      p = svg("pattern", { id: "lnd-p-core", width: 14, height: 14,
        patternUnits: "userSpaceOnUse" }, defs);
      svg("rect", { width: 14, height: 14, fill: "#e7e1d4" }, p);
      svg("path", { d: "M2 4.5h5M4.5 2v5M9 11h4M11 9v4", stroke: "#a59a88",
        "stroke-width": 0.8 }, p);
      p = svg("pattern", { id: "lnd-p-younger", width: 18, height: 9,
        patternUnits: "userSpaceOnUse" }, defs);
      svg("rect", { width: 18, height: 9, fill: "#d3ccbd" }, p);
      svg("path", { d: "M0 .5H18M0 5H18M6 .5V5M15 5V9", stroke: "#ada491",
        "stroke-width": 0.5, fill: "none" }, p);
      var clip = svg("clipPath", { id: "lnd-clip" }, defs);
      svg("rect", { x: ML, y: 0, width: pw, height: Y(S.z_base) }, clip);

      layers = [];
      function layer(cls, step) {
        var g = svg("g", { "class": "lnd-l " + cls });
        layers.push([g, step]);
        return g;
      }
      function band(u, parent, fill, stroke) {
        var runs = [];
        var cur = null;
        S.cols.forEach(function (c) {
          if (!u.has(c)) {
            cur = null;
            return;
          }
          if (!cur) {
            cur = { top: [], bot: [] };
            runs.push(cur);
          }
          samples(c[0], c[1]).forEach(function (s) {
            cur.top.push(pt(s, u.top(c, s)));
            cur.bot.push(pt(s, u.bot(c, s)));
          });
        });
        var d = runs.map(function (r) {
          return "M" + r.top.concat(r.bot.reverse()).join("L") + "Z";
        }).join("");
        return svg("path", { d: d, fill: fill, stroke: stroke || "none",
          "stroke-width": 0.6, "stroke-linejoin": "round" }, parent);
      }

      // The scales, always shown.
      var axes = svg("g", {}, root);
      var every = narrow ? 1000 : 500;
      for (var z = Math.ceil(S.z_base / every) * every; z <= S.z_top;
        z += every) {
        svg("line", { x1: ML, x2: ML + pw, y1: Y(z), y2: Y(z),
          stroke: "#b1a797", "stroke-width": 0.5,
          "stroke-dasharray": "1 3" }, axes);
        text(axes, ML - 5, Y(z) + 3.5, fmt(z), null, "end");
      }
      text(axes, 2, MT - 14, narrow ? "ft" : "feet above sea level");
      var miles = narrow ? 10 : 5;
      for (var mi = 0; mi * 5280 <= S.length_ft; mi += miles) {
        var x = X(mi * 5280);
        svg("line", { x1: x, x2: x, y1: Y(S.z_base), y2: Y(S.z_base) + 4,
          stroke: "#6c6259" }, axes);
        text(axes, x, Y(S.z_base) + 15, mi === 0 ? "0 mi" : String(mi), null,
          mi === 0 ? "start" : "middle");
      }

      var below = svg("g", { "clip-path": "url(#lnd-clip)" }, root);
      // 1: everything below the ground, quiet, until its step colours it.
      var quiet = layer("lnd-l-quiet", 1);
      svg("path", {
        d: "M" + S.ground.map(function (q) { return pt(q[0], q[1]); })
          .join("L") + "L" + pt(S.length_ft, S.z_base) + "L" +
          pt(0, S.z_base) + "Z",
        fill: "#ddd6c8"
      }, quiet);
      below.appendChild(quiet);
      // 4: the younger rock and the core.
      var rock = layer("lnd-l-rock", 4);
      band(units.younger, rock, "url(#lnd-p-younger)");
      band(units.core, rock, "url(#lnd-p-core)");
      below.appendChild(rock);
      // 2: the sandstone; 3: its water.
      var sand = layer("lnd-l-sand", 2);
      band(units.hickory, sand, "url(#lnd-p-sand)", "#8f6646");
      below.appendChild(sand);
      var water = layer("lnd-l-water", 3);
      band(units.hickory, water, "url(#lnd-p-water)", "#47625c");
      below.appendChild(water);
      // 2: the formation at the surface on the geologic map, a strip on the
      // ground.
      var strip = layer("lnd-l-strip", 2);
      S.surface_hickory.forEach(function (iv) {
        var top = samples(iv[0], iv[1]).map(function (s) {
          return [X(s), Y(ground(s))];
        });
        var d = "M" + top.map(function (q) {
          return q[0].toFixed(1) + "," + (q[1] - 1).toFixed(1);
        }).join("L") + "L" + top.slice().reverse().map(function (q) {
          return q[0].toFixed(1) + "," + (q[1] + 4).toFixed(1);
        }).join("L") + "Z";
        svg("path", { d: d, fill: "#c7976f", stroke: "#8f6646",
          "stroke-width": 0.5 }, strip);
      });
      below.appendChild(strip);
      // 4: the faults, from the ground down.
      var faults = layer("lnd-l-faults", 4);
      S.faults.forEach(function (s) {
        svg("line", { x1: X(s), x2: X(s), y1: Y(ground(s)), y2: Y(S.z_base),
          stroke: "#282b24", "stroke-width": 0.9, "stroke-dasharray": "4 3",
          opacity: 0.7 }, faults);
      });
      below.appendChild(faults);
      // 6: the district, a wash through the slice and a bar above it.
      var district = layer("lnd-l-district", 6);
      S.district.forEach(function (iv) {
        svg("rect", { x: X(iv[0]), y: MT - 18, width: X(iv[1]) - X(iv[0]),
          height: Y(S.z_base) - MT + 18, fill: "#5a1e2e",
          "fill-opacity": 0.07 }, district);
        svg("rect", { x: X(iv[0]), y: MT - 18, width: X(iv[1]) - X(iv[0]),
          height: 4, fill: "#5a1e2e" }, district);
      });
      var first = S.district[0];
      var last = S.district[S.district.length - 1];
      text(district, (X(first[0]) + X(last[1])) / 2, MT - 24,
        narrow ? "District" : "Hickory Sands District (proposed)",
        "lnd-t-district", "middle");
      root.appendChild(district);
      // 1: the ground line, the rule's height and the slice's ends.
      var top = layer("lnd-l-ground", 1);
      svg("path", {
        d: "M" + S.ground.map(function (q) { return pt(q[0], q[1]); })
          .join("L"),
        fill: "none", stroke: "#282b24", "stroke-width": 1.4,
        "stroke-linejoin": "round"
      }, top);
      svg("line", { x1: ML, x2: ML + pw, y1: Y(S.rule_ft), y2: Y(S.rule_ft),
        stroke: "#5a1e2e", "stroke-width": 0.9, "stroke-dasharray": "5 4" },
        top);
      // Above the dashed line at the south-east end, where the ground is
      // lower: clear of the wells.
      text(top, ML + pw - 2, Y(S.rule_ft) - 5, fmt(S.rule_ft) + " ft",
        "lnd-t-rule", "end");
      // Part of TWDB's line A–A′, so its ends are not called A and A′.
      text(top, ML, 11, narrow ? "NW" : "North-west end", "lnd-t-end");
      text(top, ML + pw, 11, narrow ? "SE" : "South-east end", "lnd-t-end",
        "end");
      root.appendChild(top);
      // 5: the wells, from the slice's ground to their reported depths,
      // each with its report number and its driller's own words.
      var wells = layer("lnd-l-wells", 5);
      S.wells.forEach(function (wl) {
        var x = X(wl.s);
        var z0 = wl.ground;
        var one = svg("g", {}, wells);
        var title = svg("title", {}, one);
        title.textContent = (wl.uid.charAt(0) === "S" ?
          "Driller’s report " : "State well ") + wl.uid.slice(1) + ", " +
          fmt(wl.depth) + " ft. " + wl.log.map(function (seg) {
            return fmt(seg[0]) + "–" + fmt(seg[1]) + " ft " + seg[3];
          }).join("; ");
        svg("line", { x1: x, x2: x, y1: Y(z0), y2: Y(z0 - wl.depth),
          stroke: "transparent", "stroke-width": 10 }, one);
        wl.log.forEach(function (seg) {
          svg("line", { x1: x, x2: x, y1: Y(z0 - seg[0]),
            y2: Y(z0 - Math.min(seg[1], wl.depth)),
            stroke: COLOURS[seg[2]], "stroke-width": narrow ? 2.2 : 3 }, one);
        });
        svg("circle", { cx: x, cy: Y(z0), r: narrow ? 1.6 : 2,
          fill: "#282b24" }, one);
      });
      root.appendChild(wells);

      while (art.firstChild) {
        art.removeChild(art.firstChild);
      }
      art.appendChild(root);
      apply(false);
    }

    /* The panel: the progress marks, the step's name, Back and Next. */
    var progress = fig.querySelector(".lnd-progress");
    var marks = items.map(function () {
      return progress.appendChild(document.createElement("li"));
    });
    var controls = document.createElement("div");
    controls.className = "lnd-controls";
    controls.setAttribute("role", "group");
    controls.setAttribute("aria-label", "Step through the layers");
    var hold = 0; // until then, scrolling the steps does not move the figure
    var holdEnds = 0; // the timer that ends the hold
    var onLine = null; // the step on the reading line, kept during a hold too

    function stepper(label, word, arrow, by) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "geo-step";
      b.setAttribute("aria-label", label + " layer");
      var m = document.createElement("span");
      m.setAttribute("aria-hidden", "true");
      m.textContent = arrow;
      if (by < 0) {
        b.appendChild(m);
      }
      b.appendChild(document.createTextNode(word));
      if (by > 0) {
        b.appendChild(m);
      }
      b.addEventListener("click", function () {
        if (b.getAttribute("aria-disabled") !== "true") {
          go(current + by);
        }
      });
      return b;
    }
    var back = stepper("Previous", "Back", "←", -1);
    var count = document.createElement("span");
    count.className = "geo-count";
    count.setAttribute("aria-hidden", "true");
    var next = stepper("Next", "Next", "→", 1);
    controls.appendChild(back);
    controls.appendChild(count);
    controls.appendChild(next);
    controls.addEventListener("keydown", function (event) {
      var keys = { ArrowLeft: current - 1, ArrowRight: current + 1, Home: 1,
        End: STEPS };
      if (!Object.prototype.hasOwnProperty.call(keys, event.key)) {
        return;
      }
      event.preventDefault();
      go(keys[event.key]);
    });
    fig.querySelector("figcaption").appendChild(controls);
    var live = document.createElement("p");
    live.className = "geo-live";
    live.setAttribute("aria-live", "polite");
    fig.appendChild(live);

    function pad(n) {
      return (n < 10 ? "0" : "") + n;
    }

    function show(n, announce) {
      if (n < 1 || n > STEPS) {
        return false;
      }
      var changed = n !== current;
      current = n;
      var title = items[n - 1].querySelector("h3").textContent;
      nowTitle.textContent = title;
      count.textContent = pad(n) + " / " + pad(STEPS);
      marks.forEach(function (m, i) {
        m.classList.toggle("geo-on", i === n - 1);
        m.classList.toggle("geo-past", i < n - 1);
      });
      items.forEach(function (li, i) {
        li.classList.toggle("lnd-current", i === n - 1);
      });
      back.setAttribute("aria-disabled", String(n === 1));
      next.setAttribute("aria-disabled", String(n === STEPS));
      apply(!reduce.matches);
      if (announce && changed) {
        live.textContent = "Layer " + n + " of " + STEPS + ": " + title + ".";
      }
      return changed;
    }

    // The hold is over: the drawing shows the step on the reading line,
    // which the reader may have scrolled to while the hold lasted.
    function release() {
      hold = 0;
      clearTimeout(holdEnds);
      if (onLine && follows()) {
        show(items.indexOf(onLine) + 1, false);
      }
    }

    function go(n) {
      if (!show(n, true) || !follows()) {
        return;
      }
      hold = Date.now() + 1200;
      clearTimeout(holdEnds);
      holdEnds = setTimeout(release, 1200);
      var li = items[n - 1];
      var behavior = reduce.matches ? "auto" : "smooth";
      if (n === 1 && !wide.matches) {
        // On a phone the first step follows the figure directly, so the
        // buttons stay where they are.
        window.scrollTo({
          top: li.getBoundingClientRect().top + window.pageYOffset -
            fig.getBoundingClientRect().height,
          behavior: behavior
        });
        return;
      }
      li.scrollIntoView({
        // On a phone the step's top lands just under the stuck figure (its
        // scroll-margin-top is the figure's height).
        block: wide.matches ? "center" : "start",
        behavior: behavior
      });
    }

    // One quiet line that says how the drawing moves; made here, so the
    // page without JavaScript never mentions it.
    var hint = document.createElement("p");
    hint.className = "geo-hint";
    body.parentNode.insertBefore(hint, body);
    body.classList.add("lnd-has-figure");
    draw();
    show(1, false);

    // Beside the steps (wide) or above them (a phone held upright), the
    // figure follows the step that crosses a reading line: the middle of a
    // wide screen; on a phone, a third of the way down the space left under
    // the stuck figure, measured again when the window changes.
    var watch = null;
    function observe() {
      var panel = Math.ceil(fig.getBoundingClientRect().height);
      body.style.setProperty("--lnd-panel", panel + "px");
      var scrolls = "IntersectionObserver" in window;
      hint.textContent = follows() && scrolls ?
        "The drawing changes as you scroll" : "Press Next to add a layer";
      if (!scrolls) {
        return;
      }
      if (watch) {
        watch.disconnect();
      }
      var margin = "-45% 0px -54% 0px";
      if (!wide.matches && tall.matches) {
        var vh = window.innerHeight;
        var at = Math.round(panel + (vh - panel) / 3);
        margin = -at + "px 0px " + -(vh - at - 1) + "px 0px";
      }
      watch = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            onLine = entry.target;
          } else if (entry.target === onLine) {
            onLine = null;
          }
        });
        if (!follows() || Date.now() < hold || !onLine) {
          return;
        }
        show(items.indexOf(onLine) + 1, false);
      }, { rootMargin: margin });
      items.forEach(function (li) {
        watch.observe(li);
      });
    }
    observe();
    // The reader's own touch or wheel ends a hold at once (a tap on the
    // buttons is theirs to hold), so the drawing follows the scroll it
    // starts.
    function reader(event) {
      if (hold && !controls.contains(event.target)) {
        release();
      }
    }
    window.addEventListener("touchstart", reader, { passive: true });
    window.addEventListener("wheel", reader, { passive: true });
    var again = 0;
    var lastW = art.clientWidth;
    window.addEventListener("resize", function () {
      clearTimeout(again);
      again = setTimeout(function () {
        if (Math.abs(art.clientWidth - lastW) > 2) {
          lastW = art.clientWidth;
          draw();
        }
        observe();
      }, 150);
    });
    // Printing shows every layer.
    window.addEventListener("beforeprint", function () {
      layers.forEach(function (l) {
        l[0].classList.remove("lnd-wait");
      });
    });
    window.addEventListener("afterprint", function () {
      apply(false);
    });
  }

  // The build's data; without it the static drawing and the steps stay as
  // they are.
  fetch("assets/land/section.json").then(function (response) {
    if (!response.ok) {
      throw new Error("assets/land/section.json: HTTP " + response.status);
    }
    return response.json();
  }).then(start).catch(function (error) {
    if (window.console) {
      window.console.warn("The slice keeps its static drawing:", error);
    }
  });
})();
