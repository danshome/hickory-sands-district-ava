/* The land page's three wells (#three-wells): steps the drawings with the text (the buttons, a tap on a step, or
 * scrolling), picks the drawing on narrow screens, switches the granite well's two views, and shows the source a drawn
 * layer names in a small note. Nothing is fetched. The drawings are made by src/site/make_wells.py. */
(function () {
  "use strict";
  var body = document.querySelector(".w-body");
  var fig = body && body.querySelector(".w-fig");
  if (!fig) {
    return;
  }
  body.classList.add("w-js");
  var steps = Array.prototype.slice.call(body.querySelectorAll(".w-steps .lnd-step"));
  var marks = Array.prototype.slice.call(fig.querySelectorAll(".w-progress li"));
  var tabs = Array.prototype.slice.call(fig.querySelectorAll(".w-tabs [role=tab]"));
  var strip = body.querySelector(".w-strip");
  var now = document.getElementById("w-now");
  var count = fig.querySelector(".w-count");
  var note = fig.querySelector(".w-note");
  var noteText = note.querySelector("p");
  var back = fig.querySelector('.geo-step[data-go="-1"]');
  var next = fig.querySelector('.geo-step[data-go="1"]');
  // The land page's rule for the figure beside the text.
  var WIDE = "(min-width:1000px),(min-width:700px) and (min-height:520px) and (orientation:landscape)";
  var wide = window.matchMedia(WIDE);
  var all = window.matchMedia("(min-width:1000px)"); // room for the three drawings side by side
  var still = window.matchMedia("(prefers-reduced-motion: reduce)");
  var current = 1;
  var holding = false; // after a button, the scroll it starts does not move the step
  var holdEnd = 0;

  function hold() {
    holding = true;
    window.clearTimeout(holdEnd);
    holdEnd = window.setTimeout(function () {
      holding = false;
    }, 250);
  }

  function layout() {
    body.classList.toggle("w-wide", wide.matches);
    body.classList.toggle("w-all", all.matches);
  }

  function show(n) {
    current = Math.max(1, Math.min(steps.length, n));
    note.hidden = true;
    fig.dataset.step = String(current);
    fig.classList.toggle("show-water", current >= 2);
    fig.classList.toggle("show-recharge", current >= 3);
    fig.classList.toggle("show-levels", current >= 4);
    fig.classList.toggle("show-unsure", current >= 6);
    steps.forEach(function (s, i) {
      s.classList.toggle("lnd-current", i + 1 === current);
    });
    marks.forEach(function (m, i) {
      m.classList.toggle("on", i + 1 < current);
      m.classList.toggle("now", i + 1 === current);
    });
    now.textContent = steps[current - 1].querySelector("h3").textContent;
    count.textContent = (current < 10 ? "0" : "") + current;
    back.setAttribute("aria-disabled", String(current === 1));
    next.setAttribute("aria-disabled", String(current === steps.length));
  }

  // The reading line: below the stuck figure on a narrow screen, near the middle on a wide one.
  function line() {
    if (wide.matches) {
      return window.innerHeight * 0.45;
    }
    var b = fig.getBoundingClientRect().bottom;
    return b + (window.innerHeight - b) * 0.25;
  }

  function go(n) {
    n = Math.max(1, Math.min(steps.length, n));
    show(n);
    hold();
    // 40 px past the line, so a small change of layout (a tab, a font) does not move the step back
    var top = steps[n - 1].getBoundingClientRect().top + window.scrollY - line() + 40;
    window.scrollTo({ top: Math.max(0, top), behavior: still.matches ? "auto" : "smooth" });
  }

  var ticking = false;
  function onScroll() {
    if (ticking) {
      return;
    }
    ticking = true;
    window.requestAnimationFrame(function () {
      ticking = false;
      if (holding) {
        hold(); // the scroll a button started is still moving
        return;
      }
      var at = line();
      var first = steps[0].getBoundingClientRect().top;
      if (first > window.innerHeight) {
        return; // the section is not reached yet
      }
      var n = 1;
      steps.forEach(function (s, i) {
        if (s.getBoundingClientRect().top <= at) {
          n = i + 1;
        }
      });
      if (n !== current) {
        show(n);
      }
      followText();
    });
  }

  function choose(well, focus) {
    fig.dataset.well = well;
    if (strip) {
      strip.dataset.well = well;
    }
    tabs.forEach(function (t) {
      var on = t.dataset.well === well;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      if (on && focus) {
        t.focus();
      }
    });
  }

  tabs.forEach(function (t, i) {
    t.addEventListener("click", function () {
      choose(t.dataset.well, false);
    });
    t.addEventListener("keydown", function (e) {
      var to = null;
      if (e.key === "ArrowRight") {
        to = (i + 1) % tabs.length;
      } else if (e.key === "ArrowLeft") {
        to = (i - 1 + tabs.length) % tabs.length;
      } else if (e.key === "Home") {
        to = 0;
      } else if (e.key === "End") {
        to = tabs.length - 1;
      }
      if (to !== null) {
        e.preventDefault();
        choose(tabs[to].dataset.well, true);
      }
    });
  });
  back.addEventListener("click", function () {
    go(current - 1);
  });
  next.addEventListener("click", function () {
    go(current + 1);
  });
  steps.forEach(function (s, i) {
    s.addEventListener("click", function (e) {
      if (!e.target.closest("a, button, summary")) {
        show(i + 1);
      }
    });
  });

  // A drawn layer's source: each one names the number of its source in the page's list (data-src).
  fig.querySelectorAll("[data-src]").forEach(function (el) {
    el.setAttribute("tabindex", "0");
    el.setAttribute("role", "button");
    var src = (el.getAttribute("data-src") || "").trim();
    if (/^\d+$/.test(src)) {
      el.setAttribute("aria-label", "Show source " + src);
    }
  });
  function cite(el) {
    var n = (el.getAttribute("data-src") || "").trim();
    if (!/^\d+$/.test(n)) {
      return;
    }
    var li = document.getElementById("source-" + n);
    if (!li) {
      return;
    }
    note.hidden = false;
    noteText.textContent = "Source " + n + ": " + li.textContent.replace(/\s+/g, " ").trim() + " ";
    var a = document.createElement("a");
    a.href = "#source-" + n;
    a.textContent = "All sources";
    noteText.appendChild(a);
  }
  fig.addEventListener("click", function (e) {
    var el = e.target.closest("[data-src]");
    if (el) {
      cite(el);
    }
  });
  fig.addEventListener("keydown", function (e) {
    var el = e.target.closest && e.target.closest("[data-src]");
    if (el && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      cite(el);
    }
  });

  // The granite well's two views: the documented example (the default) or the screened gravel well.
  var gpanel = document.getElementById("panel-granite");
  var gbuttons = Array.prototype.slice.call(gpanel.querySelectorAll(".w-gview button"));
  var chosen = false; // the reader picked a view by hand: the text no longer switches it
  function view(v) {
    gpanel.dataset.gview = v;
    gpanel.querySelector(".w-gv-rock").hidden = v !== "rock";
    gpanel.querySelector(".w-gv-gravel").hidden = v !== "gravel";
    gbuttons.forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.gview === v));
    });
  }
  gbuttons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      chosen = true;
      view(btn.dataset.gview);
    });
  });
  // While the text about one granite well crosses the reading line, show that well; elsewhere the default.
  var gtexts = Array.prototype.slice.call(body.querySelectorAll(".w-steps [data-gview]"));
  function followText() {
    if (chosen) {
      return;
    }
    var at = line();
    var want = "rock";
    gtexts.forEach(function (p) {
      var r = p.getBoundingClientRect();
      if (r.top <= at && r.bottom >= at) {
        want = p.dataset.gview;
      }
    });
    if (gpanel.dataset.gview !== want) {
      view(want);
    }
  }
  note.querySelector(".w-note-x").addEventListener("click", function () {
    note.hidden = true;
  });
  layout();
  show(1);
  if (wide.addEventListener) {
    wide.addEventListener("change", layout);
    all.addEventListener("change", layout);
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
})();
