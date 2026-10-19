// Add a vineyard (vineyards.html). An enhancement only: without this file the
// form is a plain mailto: form and the district's address is on the page.
// With it, the form is checked, the email is built (vineyard-email.js), the
// details can be copied, and a pin can be placed on the site's map. Nothing is
// stored and nothing is sent by this page: the visitor's own email app sends
// the message, after they press Send there. Every text is set with
// textContent, never parsed as HTML.
import {
  ADDRESS,
  SUBJECT,
  decimal,
  message,
  normalize,
  pair,
  plan,
  problems,
} from "./vineyard-email.js";

const SDK = "https://js.arcgis.com/5.1/";
const MAPS = "./maps.js";

const $ = (id) => document.getElementById(id);
const form = $("vineyard-form");
const details = $("add-form");
const ready = $("ready");
const status = $("status");
const summary = $("error-summary");
form.noValidate = true; // the script shows its own messages, beside each field

const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const CONSENT = $("v-consent-text").textContent;
let source = "typed"; // "pin" once the map's centre is used
let checked = false; // after the first press, fields are checked as they change
let shown = null; // the message the ready panel shows

function values() {
  const v = (id) => $(id).value;
  const chosen = form.querySelector('input[name="Status"]:checked');
  return normalize({
    name: v("v-name"),
    business: v("v-business"),
    status: chosen ? chosen.value : "",
    website: v("v-website"),
    lat: v("v-lat"),
    lon: v("v-lon"),
    source,
    road: v("v-road"),
    directions: v("v-directions"),
    county: v("v-county"),
    acres: v("v-acres"),
    year: v("v-year"),
    varieties: v("v-varieties"),
    sells: $("v-sells").checked,
    makes: $("v-makes").checked,
    contact: v("v-contact"),
    email: v("v-email"),
    consent: $("v-consent").checked,
    note: v("v-note"),
  });
}

const LABELS = {
  "v-name": "Vineyard name",
  "v-status": "Status",
  "v-website": "Website",
  "v-where": "Where it is",
  "v-lat": "Latitude",
  "v-lon": "Longitude",
  "v-county": "County",
  "v-acres": "Acres planted",
  "v-year": "Year first planted",
  "v-contact": "Your name",
  "v-email": "Your email",
  "v-consent": "Permission",
};
const WORDS = ["", "One thing", "Two things", "Three things", "Four things",
  "Five things", "Six things", "Seven things", "Eight things", "Nine things",
  "Ten things", "Eleven things", "Twelve things"];

// The fields a message marks: a group's every control, or the one field.
// The "Where it is" group marks its point and its road.
function marked(id) {
  if (id === "v-where") return [$("v-lat"), $("v-lon"), $("v-road")];
  const field = $(id);
  return field.matches("fieldset") ? [...field.querySelectorAll("input")] : [field];
}

// Follows a summary link: focuses the field and brings its message into view
// (a group's message sits at the group's top or foot, not at its first field).
function follow(id) {
  const [first] = marked(id);
  const group = $(id).matches("fieldset");
  first.focus({ preventScroll: true });
  (group ? $(`${id}-error`) : first).scrollIntoView({
    block: "center",
    behavior: reducedMotion() ? "auto" : "smooth",
  });
}

function show(found) {
  for (const error of form.querySelectorAll(".field-error")) {
    error.hidden = true;
    error.textContent = "";
  }
  for (const field of form.querySelectorAll("[aria-invalid]")) {
    field.removeAttribute("aria-invalid");
  }
  for (const [id, text] of found) {
    const error = $(`${id}-error`);
    error.textContent = text;
    error.hidden = false;
    for (const field of marked(id)) field.setAttribute("aria-invalid", "true");
  }
  const list = $("error-list");
  list.replaceChildren();
  summary.hidden = found.length === 0;
  if (!found.length) return;
  $("error-summary-title").textContent =
    `${WORDS[found.length] || `${found.length} things`} to check`;
  for (const [id, text] of found) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = `#${id}`;
    link.textContent = `${LABELS[id]}: ${text}`;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      follow(id);
    });
    item.append(link);
    list.append(item);
  }
}

// The message, never nothing: if building it fails, the form's own values,
// one "Name: value" line each, with the bare subject.
function build() {
  try {
    const built = message(values(), CONSENT);
    return { ...built, ...plan(built), body: built.body };
  } catch (error) {
    console.error("the email could not be built", error);
    const body = [...new FormData(form)].map(([k, v]) => `${k}: ${v}`).join("\n");
    return { subject: SUBJECT, body, url: `mailto:${ADDRESS}`, long: true };
  }
}

// The panel under the form, in one of its states: "opened" (the email app was
// given the whole message), "long" (it was given the subject, and the details
// were copied), "long-failed" (the same, but the copy failed), "copied" (Copy
// was pressed) and "selected" (Copy failed: the text is selected to copy).
const STATES = {
  opened: ["Your email is ready.", "ready-opened"],
  long: ["The details are copied.", "ready-long"],
  "long-failed": ["The details are below.", "ready-long-failed"],
  copied: ["The details are copied.", "ready-copied"],
  selected: ["The details are below.", "ready-copied"],
};
function fill(mail, state) {
  const [title, text] = STATES[state];
  $("ready-title").textContent = title;
  for (const p of ready.querySelectorAll(".ready-text")) p.hidden = p.id !== text;
  $("ready-subject").textContent = mail.subject;
  $("ready-body").textContent = mail.body;
  $("ready-open").href = mail.url; // the very URL the button opened
  $("ready-open").textContent = state === "opened" || state.startsWith("long")
    ? "Open the email again"
    : "Open in your email app";
  ready.hidden = false;
  shown = mail;
}

function selectBody() {
  const range = document.createRange();
  range.selectNodeContents($("ready-body"));
  getSelection().removeAllRanges();
  getSelection().addRange(range);
}

// Starts copying the text, in the same turn as the press (iOS allows it only
// then), and returns the promise, which never throws where it starts.
function copying(text) {
  try {
    return navigator.clipboard.writeText(text);
  } catch (error) {
    return Promise.reject(error);
  }
}

const COPY_FAILED = "Your browser would not copy it. The details are selected " +
  "below: copy them with the keyboard, or press and hold.";

// The button: the checks, then the email app. A long message goes by the
// clipboard: the copy starts first, without waiting for it, so the press still
// allows the email app to open.
function send() {
  const mail = build();
  if (mail.long) {
    const copy = copying(mail.body);
    fill(mail, "long");
    status.textContent = "";
    ready.focus();
    location.href = mail.url;
    copy.catch(() => {
      if (shown !== mail) return;
      fill(mail, "long-failed");
      selectBody();
      status.textContent = COPY_FAILED;
    });
    return;
  }
  fill(mail, "opened");
  status.textContent = "";
  ready.focus();
  location.href = mail.url;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  checked = true;
  const found = problems(values(), new Date().getFullYear());
  show(found);
  if (found.length) {
    hideReady();
    summary.focus();
    return;
  }
  send();
});

// The panel is never stale: any change to the form hides it until the button
// is pressed again.
function hideReady() {
  if (ready.hidden) return;
  ready.hidden = true;
  shown = null;
  status.textContent = "";
}
form.addEventListener("input", hideReady);
form.addEventListener("change", () => {
  hideReady();
  if (checked) show(problems(values(), new Date().getFullYear()));
});

// Enter (a phone keyboard's Next or Go) in a one-line field moves to the next
// field, as Tab does; only the button sends the form.
function nextField(field) {
  const order = [];
  const groups = new Set();
  for (const control of form.querySelectorAll("input, select, textarea")) {
    if (control.disabled || control.type === "hidden") continue;
    if (control.closest("[hidden]")) continue;
    if (control.type === "radio") {
      if (groups.has(control.name)) continue;
      groups.add(control.name);
      const group = [...form.querySelectorAll("input[type=radio]")]
        .filter((radio) => radio.name === control.name);
      order.push(group.find((radio) => radio.checked) || control);
      continue;
    }
    order.push(control);
  }
  const at = order.findIndex((control) => control === field ||
    (field.type === "radio" && control.type === "radio" && control.name === field.name));
  return order[at + 1] || null;
}
form.addEventListener("keydown", (event) => {
  const field = event.target;
  if (event.key !== "Enter" || event.isComposing) return;
  if (!(field instanceof HTMLInputElement)) return;
  if (["submit", "button", "reset", "image"].includes(field.type)) return;
  event.preventDefault();
  nextField(field)?.focus();
});

// A pair copied from a map app, pasted into either box, is split between them.
for (const id of ["v-lat", "v-lon"]) {
  $(id).addEventListener("input", () => {
    const both = pair($(id).value);
    if (both) [$("v-lat").value, $("v-lon").value] = both;
    source = "typed";
  });
}

// Copy never blocks: it copies whatever is filled in, for the visitor to send
// as they like; only the button checks the form first.
function copyDetails(event) {
  const mail = build();
  const fromForm = event.currentTarget === $("copy");
  copying(mail.body).then(
    () => {
      fill(mail, "copied");
      status.textContent = `Copied. Paste the details into a new email to ${ADDRESS}.`;
    },
    () => {
      fill(mail, "selected");
      selectBody();
      status.textContent = COPY_FAILED;
    },
  ).finally(() => {
    if (fromForm) ready.focus();
  });
}
$("copy").hidden = false;
$("copy").addEventListener("click", copyDetails);
$("ready-copy").addEventListener("click", copyDetails);
// Opening a long message again copies its details again.
$("ready-open").addEventListener("click", () => {
  if (shown?.long) copying(shown.body).catch(() => {});
});
$("ready-edit").addEventListener("click", () => {
  hideReady();
  $("v-name").focus();
});

// A link to vineyards.html#add opens the form.
function openFromLink() {
  if (location.hash === "#add") details.open = true;
}
openFromLink();
addEventListener("hashchange", openFromLink);

// The pin: the site's map, loaded only when asked for (it fetches Esri's SDK
// and basemap; nothing typed in the form goes to Esri).
$("pin").hidden = false;
function loadSdk() {
  return new Promise((resolve, reject) => {
    if (window.$arcgis) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.type = "module";
    script.src = SDK;
    script.onload = resolve;
    script.onerror = () => reject(new Error("the map SDK did not load"));
    document.head.append(script);
  });
}
let opening = false;
async function openMap() {
  if (opening) return;
  opening = true;
  const button = $("pin-open");
  button.setAttribute("aria-expanded", "true");
  button.hidden = true;
  $("pin-map").hidden = false;
  try {
    await loadSdk();
    const maps = await import(MAPS);
    const element = document.querySelector("#pin-map arcgis-map");
    const { layers } = await maps.boundaryMap(element, { popups: false });
    layers.points.visible = false; // the line is enough to find one's way
    if (maps.hasBasemap) {
      maps.setBasemap(element, "imagery");
      const switcher = $("pin-basemaps");
      switcher.hidden = false;
      for (const b of switcher.querySelectorAll("button")) {
        b.addEventListener("click", () => {
          for (const o of switcher.querySelectorAll("button")) {
            o.setAttribute("aria-pressed", String(o === b));
          }
          maps.setBasemap(element, b.dataset.basemap);
        });
      }
    }
    // A tap or a click moves that spot under the cross.
    element.addEventListener("arcgisViewClick", (event) => {
      element.goTo({ target: event.detail.mapPoint }).catch((error) => {
        if (!maps.interrupted(error)) console.error(error);
      });
    });
    $("pin-use").addEventListener("click", () => {
      const centre = element.view.center;
      $("v-lat").value = decimal(centre.latitude, 5);
      $("v-lon").value = decimal(centre.longitude, 5);
      source = "pin";
      hideReady(); // set here, not typed: no input event says so
      maps.markStep(layers.marked, null, centre.clone());
      status.textContent = `The pin is at ${$("v-lat").value}, ${$("v-lon").value}.`;
      if (checked) show(problems(values(), new Date().getFullYear()));
    });
    $("pin-loading").hidden = true;
    $("pin-tools").hidden = false;
    $("pin-note").hidden = false;
  } catch (error) {
    console.error("the pin map could not be drawn", error);
    $("pin-map").hidden = true;
    $("pin-failed").hidden = false;
  }
}
$("pin-open").addEventListener("click", openMap);
