// Google Analytics (GA4) for hickorysandsdistrictava.org: it counts visits.
// Every page loads this file in its <head>, deferred; no page names Google's
// script itself (tests/test_analytics.py). It loads gtag.js only on the live
// site, and never for an automated browser (so the site's tests never count),
// a visitor whose browser asks not to be tracked (Do Not Track or Global
// Privacy Control), or with the measurement ID below empty. Google signals and
// ad personalization are off. It adds no events of its own: gtag.js sends the
// page view, and whatever the stream's enhanced measurement turns on.
(function () {
  "use strict";

  // The site's GA4 web stream. Public by nature (every request to Google
  // carries it); empty, nothing loads.
  const MEASUREMENT_ID = "G-5PDG3Z75PY";
  const HOST = "hickorysandsdistrictava.org";

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

  const script = document.createElement("script");
  script.async = true;
  script.src =
    "https://www.googletagmanager.com/gtag/js?id=" +
    encodeURIComponent(MEASUREMENT_ID);
  document.head.appendChild(script);
})();
