// Google Analytics (GA4) for hickorysandsdistrictava.org: it counts visits,
// and which parts of the maps, the walk, The land, the logo vote and the
// vineyard form are used. Every page loads this file in its <head>, deferred;
// no page names Google's script itself (tests/test_analytics.py). It loads
// gtag.js only on the live site, and never for an automated browser (so the
// site's tests never count), a visitor whose browser asks not to be tracked
// (Do Not Track or Global Privacy Control), or with the measurement ID below
// empty. Google signals and ad personalization are off.
//
// The site's own events go through window.hsdTrack(name, params), the one way
// a page's script reaches Analytics. It sends only the events in EVENTS below,
// each with only its own params, and a param only when its value is one of
// that param's fixed words or a small whole number: never free text, a place,
// an id or anything typed. Anything else is dropped, and so is the whole call
// when Analytics is off. It never throws. BUILD.md (Analytics) lists them.
(function () {
  "use strict";

  // The site's GA4 web stream. Public by nature (every request to Google
  // carries it); empty, nothing loads.
  const MEASUREMENT_ID = "G-5PDG3Z75PY";
  const HOST = "hickorysandsdistrictava.org";

  // A param whose value is a whole number from 0 to MAX_INT.
  const INT = "int";
  const MAX_INT = 999;
  // The most events one page view sends: a runaway loop stops here.
  const MAX_EVENTS = 300;
  // The pages, from their address: "/" is home; any other is "other".
  const PAGES = [
    "home",
    "about",
    "boundary",
    "colophon",
    "journal",
    "land",
    "logo-vote",
    "map",
    "status",
    "vineyards",
    "walk",
    "other",
  ];
  // The map's groups (map-url.js's GROUPS) and its layers' switches (each
  // data-switch in map.html), and "all" for a group's own switch.
  const MAP_GROUPS = [
    "district",
    "places",
    "wells",
    "vineyards",
    "boundaries",
    "geology",
    "aquifer",
  ];
  const MAP_LAYERS = [
    "all",
    "ava",
    "counties",
    "district",
    "location",
    "member",
    "official-outcrop",
    "outside-official",
    "precambrian",
    "precambrian-buried",
    "sides",
    "steps",
    "top-buried",
    "top-surface",
    "towns",
    "vineyards-developing",
    "vineyards-historical",
    "vineyards-hsd",
    "vineyards-llano",
    "wells",
    "wells-water",
  ];
  const STEPS = (prefix, n) =>
    Array.from({ length: n }, (_, i) => prefix + "-" + (i + 1));
  // Each event and its params: a list of the words it may take, or INT.
  const EVENTS = {
    map_layer: {
      group: MAP_GROUPS,
      layer: MAP_LAYERS,
      state: ["on", "off"],
    },
    map_open_item: {
      kind: ["step", "point", "well", "vineyard", "aquifer", "other"],
    },
    map_view: {
      action: [
        "3d",
        "2d",
        "home",
        "basemap",
        "wells_filter",
        "wells_reset",
        "panel_min",
        "panel_restore",
        "about",
      ],
      choice: [
        "button",
        "imagery",
        "topo",
        "dark",
        "use",
        "yield",
        "depth",
        "unreported",
        "hickory_only",
        "about-district",
        "about-sources",
        "sheet",
      ],
    },
    map_mode: { mode: ["map", "aquifer"] },
    walk_step: { step: INT, total: INT },
    walk_complete: { total: INT },
    land_section: { section: [...STEPS("slice", 6), ...STEPS("timeline", 8)] },
    vote_cast: { dir: ["like", "pass"] },
    vote_undo: {},
    vote_upload: { result: ["ok", "refused", "error"] },
    vineyard_form: {
      step: [
        "start",
        "blocks",
        "details",
        "review",
        "sent",
        "email_fallback",
        "error",
      ],
    },
  };
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);

  // The page this is, as one of PAGES.
  function pageName() {
    const path = String(location.pathname || "/");
    const name = path.slice(path.lastIndexOf("/") + 1).replace(/\.html$/, "");
    const page = name === "" || name === "index" ? "home" : name;
    return PAGES.includes(page) ? page : "other";
  }

  // The params to send, or null when the call breaks a rule.
  function clean(name, params) {
    if (typeof name !== "string" || !own(EVENTS, name)) return null;
    const allowed = EVENTS[name];
    const out = {};
    for (const key of Object.keys(params || {})) {
      if (!own(allowed, key)) return null;
      const value = params[key];
      if (allowed[key] === INT) {
        if (!Number.isInteger(value) || value < 0 || value > MAX_INT) {
          return null;
        }
      } else if (typeof value !== "string" || !allowed[key].includes(value)) {
        return null;
      }
      out[key] = value;
    }
    out.page = pageName();
    return out;
  }

  let send = null; // set once Analytics is on
  let sent = 0;
  function track(name, params) {
    try {
      if (!send || sent >= MAX_EVENTS) return;
      const out = clean(name, params);
      if (!out) return;
      sent += 1;
      send(name, out);
    } catch {
      // Analytics never breaks a page.
    }
  }
  window.hsdTrack = track;

  // Why this visit is not counted, or "" when it is.
  function skip() {
    if (!MEASUREMENT_ID) return "no measurement ID";
    if (navigator.webdriver) return "an automated browser";
    if (location.hostname !== HOST) return "not the live site";
    if (navigator.doNotTrack === "1" || window.doNotTrack === "1") {
      return "Do Not Track";
    }
    if (navigator.globalPrivacyControl) return "Global Privacy Control";
    return "";
  }
  if (skip()) return;

  window.dataLayer = window.dataLayer || [];
  // gtag.js reads each call's arguments object, as Google's own snippet pushes.
  function gtag() {
    window.dataLayer.push(arguments);
  }
  gtag("js", new Date());
  gtag("config", MEASUREMENT_ID, {
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
    send_page_view: true,
  });
  send = (name, out) => gtag("event", name, out);

  const script = document.createElement("script");
  script.async = true;
  script.src =
    "https://www.googletagmanager.com/gtag/js?id=" +
    encodeURIComponent(MEASUREMENT_ID);
  document.head.appendChild(script);
})();
