// Add your vineyard (vineyards.html): five short steps over the whole screen.
// 1 where, 2 the blocks (tap the corners), 3 about the vineyard, 4 how to reach
// you, 5 check and send. Everything entered is kept on the device (a draft),
// apart from the name, phone and email, until it is sent. Send posts JSON to one
// Supabase Edge Function (src/vineyards/functions/vineyard-submit/), which
// checks it with the same rules (vineyard-blocks.js), keeps the contact
// privately and posts the public part for the petitioners. When the function
// is not set up (vineyard-config.js) or does not answer, the grower is offered
// the email instead (vineyard-email.js). Text from the grower is only ever set
// as text.
//
// "Suggest a change" (a button beside each vineyard in the list,
// vineyard-list.js, or vineyards.html#change=<id> from the map's popup) opens
// the same form filled with that listed vineyard's public fields and blocks
// (assets/vineyards/known.json), at its blocks; the grower changes what is
// wrong, says in a short public note what has changed, and gives a contact as
// for a new vineyard. It is sent as a change (version 2 of the rules, naming
// the vineyard by its id), and its draft is kept apart from a new vineyard's.
import { apiKey } from "./map-config.js?v=999720b";
import { endpoint, turnstileSiteKey } from "./vineyard-config.js?v=b87e284";
import * as rules from "./vineyard-blocks.js?v=a5a4beb";
import { ADDRESS, message, plan } from "./vineyard-email.js?v=10df5f5";

// The form sends when the function's address is given (READY). The person
// check (Cloudflare Turnstile) is loaded and required only when its site key
// is given too (CHECK_ON); without one, Send posts without a token (Dan,
// 2026-10-19: Turnstile is added only if bots show up).
const READY = /^https:\/\/[a-z0-9-]+\.supabase\.co\/functions\/v1\/vineyard-submit$/.test(endpoint) ||
  /^http:\/\/(localhost|127\.0\.0\.1):\d+\/vineyard-submit$/.test(endpoint);
const CHECK_ON = READY && Boolean(turnstileSiteKey);
const SDK = "https://js.arcgis.com/5.1/";
const TURNSTILE = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
const GEOCODE = "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer";
const DATA = {
  llano: "assets/aquifer/llano-uplift.geojson",
  district: "data/boundary.geojson",
  counties: "assets/vineyards/counties.geojson",
  known: "assets/vineyards/known.json",
};
const DRAFT = "hsd-vineyard-draft-v1";
const CHANGE_DRAFT = "hsd-vineyard-change-draft-v1"; // a change's, kept apart
const VINEYARD_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const DRAFT_DAYS = 7; // an untouched draft is forgotten after a week
const PRIVATE = ["cname", "phone", "email"]; // never kept on the device
const HIT_PX = 30; // a finger's reach around a corner dot
const DRAW_ZOOM = 15; // closer than this, a tap zooms in instead of adding a corner
const YELLOW = [255, 214, 0];
const INK = [20, 21, 18];
const WINE = [90, 30, 46];
const TITLES = {
  1: "Where is your vineyard?",
  2: "Draw your blocks",
  3: "About the vineyard",
  4: "How can we reach you?",
  5: "Check and send",
  done: "Thank you.",
  failed: "Not sent yet",
};
const CHANGE_TITLES = { ...TITLES, 2: "Check the blocks" };

const $ = (id) => document.getElementById(id);
const wiz = $("wiz");
const html = document.documentElement;

// --- state, and the draft kept on the device ---------------------------------

// One id per vineyard sent: a retry after a lost answer gets the first answer
// back from the function, never a second issue.
const newId = () => crypto.randomUUID();
const fresh = () => ({
  id: newId(),
  step: 1, mode: "blocks", blocks: [], current: [], pin: null, view: null,
  name: "", county: "", countyPicked: false, planted: "", acres: "", year: "",
  varieties: [], other: "", cname: "", phone: "", email: "",
  permission: false, public: false,
  changes: null, listedName: "", note: "", // a change: the listed vineyard's id and name
});
let state = fresh();
let token = null;
let shot = null; // a picture of the blocks for the review, kept in memory only
let areas = null;
let counties = [];
let known = null; // the listed vineyards by id, once loaded

// Where this state's draft is kept: a change's apart from a new vineyard's.
const draftKey = () => (state.changes ? CHANGE_DRAFT : DRAFT);

function readDraft(where = DRAFT) {
  try {
    const saved = JSON.parse(localStorage.getItem(where) || "null");
    if (!saved || typeof saved !== "object") return null;
    if (!(Date.now() - (saved.savedAt || 0) < DRAFT_DAYS * 86400000)) {
      localStorage.removeItem(where);
      return null;
    }
    const kept = { ...fresh(), ...saved };
    for (const key of PRIVATE) kept[key] = state?.[key] || "";
    return kept;
  } catch {
    return null;
  }
}
let saving = 0;
// Whether this browser keeps the draft: false once a save failed (a private
// window, a full or blocked store). The page then says the answers are kept
// only while it is open, never that they are kept on the device.
let keeps = true;
function store(kept) {
  try {
    localStorage.setItem(kept.changes ? CHANGE_DRAFT : DRAFT, JSON.stringify(kept));
    keeps = true;
  } catch (error) {
    if (keeps) console.warn("this browser will not keep the draft", error);
    keeps = false;
  }
  keptNote();
}
function save() {
  if (state.step === "done") return; // sent: nothing is kept
  clearTimeout(saving);
  const kept = { ...state, savedAt: Date.now() };
  for (const key of PRIVATE) delete kept[key]; // a shared phone keeps no contact details
  saving = setTimeout(() => store(kept), 250);
}
// Saved now, not in a moment: before the form closes or says it is kept.
function saveNow() {
  if (state.step === "done") return;
  clearTimeout(saving);
  const kept = { ...state, savedAt: Date.now() };
  for (const key of PRIVATE) delete kept[key];
  store(kept);
}
function forget(key = draftKey()) {
  clearTimeout(saving);
  try {
    localStorage.removeItem(key);
  } catch (error) {
    console.warn("the draft could not be forgotten", error);
  }
}
// The page's own words about the draft, true to what this browser does.
const KEPT = "Your answers so far are kept on this device, apart from your name, phone and email.";
const NOT_KEPT = "This browser won't keep your answers, so they stay only while this page is open.";
function keptNote() {
  $("draft-text").textContent = keeps ? KEPT : NOT_KEPT;
}

// A message on the screen, above the foot bar, for what is not one field's
// fault (the form's data not loading, the map search failing); with the
// district's address when the grower may need another way.
function msg(text, { email = false } = {}) {
  const p = $("wiz-msg");
  p.replaceChildren();
  p.hidden = !text;
  if (!text) return;
  p.append(text);
  if (email) {
    const a = document.createElement("a");
    a.href = `mailto:${ADDRESS}`;
    a.textContent = ADDRESS;
    p.append(" ", a, ".");
  }
}
const say = (text) => {
  $("live").textContent = "";
  requestAnimationFrame(() => ($("live").textContent = text));
};
const acresText = (a) => (a < 10 ? a.toFixed(1) : String(Math.round(a)));

// --- the page's start button ------------------------------------------------------

const draft = readDraft();
if (draft) {
  $("start").textContent = "Continue adding your vineyard";
  $("draft-note").hidden = false;
}
$("draft-discard").addEventListener("click", () => {
  forget(DRAFT);
  state = fresh();
  shot = null;
  fillFields();
  render(); // the last vineyard's blocks leave the map too
  $("start").textContent = "Add my vineyard";
  $("draft-note").hidden = true;
  say("Started again. Nothing is kept.");
});
$("start").addEventListener("click", () => open());
$("wiz-close").addEventListener("click", close);
wiz.addEventListener("keydown", (e) => {
  if (e.key === "Escape") close();
});

// The phone's Back goes back one step, as people expect: each step is an entry
// in the browser's history while the form is open.
let depth = 0;
function remember(step, replace = false) {
  const entry = { wiz: true, step };
  if (replace) history.replaceState(entry, "");
  else {
    history.pushState(entry, "");
    depth++;
  }
}
addEventListener("popstate", (e) => {
  if (wiz.hidden) return;
  if (e.state?.wiz && state.step !== "done") {
    depth = Math.max(0, depth - 1);
    show(e.state.step, { fromHistory: true });
  } else {
    depth = 0;
    hide();
  }
});

// Analytics (analytics.js's window.hsdTrack, absent or off on most visits):
// how far the form gets, as fixed words, each once each time it is opened;
// never what is entered.
const FORM_STEPS = { 2: "blocks", 3: "details", 4: "details", 5: "review", done: "sent", failed: "error" };
let counted = new Set();
function reachedStep(step) {
  const word = FORM_STEPS[step];
  if (!word || counted.has(word)) return;
  counted.add(word);
  window.hsdTrack?.("vineyard_form", { step: word });
}

function open() {
  counted = new Set();
  window.hsdTrack?.("vineyard_form", { step: "start" });
  const kept = readDraft();
  if (kept) state = kept;
  else if (state.step === "done" || state.changes) state = fresh(); // never a change's state
  shot = null;
  enter();
}
// The form over the page, at the state's step.
function enter() {
  if (state.step === "failed") state.step = 5;
  $("change-missing").hidden = true;
  wiz.hidden = false;
  depth = 0;
  remember(state.step);
  $("w-extra").value = "";
  html.classList.add("wiz-open");
  $("page").inert = true;
  fillFields();
  show(state.step, { focus: true });
  loadAreas().catch((error) => console.error("the areas did not load", error)).then(() => openMap())
    .then(() => {
      if (state.changes) fitBlocks();
    });
}

// "Suggest a change" to a listed vineyard: the form, filled with its public
// fields and blocks, at its blocks; a change's draft for the same vineyard
// is taken up again. A vineyard not in the site's data is said on the page.
let opening = false; // a second tap while the list loads opens it once
async function openChange(id) {
  if (!wiz.hidden || opening) return;
  opening = true;
  try {
    await startChange(id);
  } finally {
    opening = false;
  }
}
async function startChange(id) {
  opener =document.activeElement instanceof HTMLElement && document.activeElement !== document.body
    ? document.activeElement
    : null;
  counted = new Set();
  window.hsdTrack?.("vineyard_form", { step: "change_start" });
  const listed = typeof id === "string" && VINEYARD_ID.test(id) ? (await loadKnown())?.[id] : null;
  if (!listed || !Object.prototype.hasOwnProperty.call(known, id)) {
    console.error("no listed vineyard to change", String(id).slice(0, 80));
    $("change-missing").hidden = false;
    $("change-missing").scrollIntoView({ block: "center" });
    return;
  }
  const kept = readDraft(CHANGE_DRAFT);
  state = kept && kept.changes === id ? kept : prefilled(id, listed);
  if (state.step === "done") state.step = 2;
  shot = null;
  enter();
}
addEventListener("hsd-vineyard-change", (e) => openChange(e.detail));

// A fresh change's state, from the listed vineyard (known.json's entry).
function prefilled(id, listed) {
  const s = fresh();
  const varieties = Array.isArray(listed.varieties) ? listed.varieties.map(String) : [];
  Object.assign(s, {
    changes: id,
    listedName: String(listed.name),
    name: String(listed.name),
    planted: listed.category === "under-development" ? "planned" : "planted",
    year: Number.isInteger(listed.year) ? String(listed.year) : "",
    varieties: varieties.filter((v) => rules.VARIETIES.includes(v)),
    other: varieties.filter((v) => !rules.VARIETIES.includes(v)).join(", "),
    blocks: listed.blocks.map((ring) => ring.map((p) => [Number(p[0]), Number(p[1])])),
    current: null,
    step: 2,
  });
  const all = s.blocks.flat();
  const mean = (i) => all.reduce((t, p) => t + p[i], 0) / all.length;
  if (all.length) s.view = { center: [mean(0), mean(1)], zoom: 16 };
  return s;
}

// The map on the blocks (a change opens on the vineyard).
function fitBlocks() {
  const all = state.blocks.flat();
  if (!view || !all.length) return;
  const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
  const pad = 0.2 * Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 0.001);
  view.goTo({
    type: "extent", xmin: Math.min(...xs) - pad, ymin: Math.min(...ys) - pad, xmax: Math.max(...xs) + pad,
    ymax: Math.max(...ys) + pad, spatialReference: { wkid: 4326 },
  }, { animate: false }).catch(moved);
}

// The listed vineyards (known.json), loaded once; null when they could not be.
let knownLoading = null;
function loadKnown() {
  knownLoading ||= fetch(DATA.known).then((r) => {
    if (!r.ok) throw new Error(`${DATA.known}: ${r.status}`);
    return r.json();
  }).then((data) => {
    known = data && typeof data === "object" && !Array.isArray(data) ? data : {};
    return known;
  }).catch((error) => {
    console.error("the listed vineyards did not load", error);
    knownLoading = null; // asked again, it tries again
    return null;
  });
  return knownLoading;
}
function close() {
  const back = depth;
  hide();
  depth = 0;
  if (back > 0) history.go(-back); // leave the form's entries behind; popstate then finds it closed
}
function hide() {
  wiz.hidden = true;
  html.classList.remove("wiz-open");
  $("page").inert = false;
  if (state.step !== "done") {
    saveNow();
    if (!state.changes) {
      $("start").textContent = "Continue adding your vineyard";
      $("draft-note").hidden = false; // says whether this browser keeps them
    }
  }
  (opener?.isConnected ? opener : $("start")).focus();
  opener = null;
}
let opener = null; // the button a change was opened from, focused again after

// --- steps -----------------------------------------------------------------------------

const STEP_ERRORS = {
  2: (f) => f.startsWith("block") || ["where", "pin", "blocks"].includes(f),
  3: (f) => ["name", "county", "planted", "acres", "year", "varieties", "note"].includes(f),
  4: (f) => f.startsWith("contact"),
  5: (f) => f.startsWith("agree"),
};
const FIELD_ELEMENT = {
  name: "w-name", county: "w-county", planted: "w-planted", acres: "w-acres", year: "w-year",
  varieties: "w-other", "contact-name": "w-cname", "contact-email": "w-email",
  "contact-phone": "w-phone", "agree-permission": "w-agree-permission", "agree-public": "w-agree-public",
  note: "w-note",
};

function show(step, { focus = true, fromHistory = false } = {}) {
  if (!fromHistory && !wiz.hidden && history.state?.wiz && history.state.step !== step) {
    remember(step, step === "failed" || step === "done");
  }
  msg("");
  state.step = step;
  reachedStep(step);
  for (const s of wiz.querySelectorAll(".step")) s.hidden = s.dataset.step !== String(step);
  const n = typeof step === "number" ? step : 5;
  $("wiz-count").textContent = typeof step === "number" ? `Step ${step} of 5` : step === "done" ? "Sent" : "Step 5 of 5";
  $("wiz-title").textContent = (state.changes ? CHANGE_TITLES : TITLES)[step];
  changeMode();
  wiz.querySelectorAll(".wiz-progress li").forEach((li, i) => li.classList.toggle("on", i < n));
  const mapped = step === 1 || step === 2;
  $("wiz-map").hidden = !mapped;
  wiz.classList.toggle("no-map", !mapped);
  wiz.dataset.step = String(step);
  $("wiz-bottom").hidden = step === "done" || step === "failed";
  $("next").textContent = step === 5 ? "Send" : step === 1 ? "Next: draw the blocks" : "Next";
  $("next").disabled = false;
  bottom();
  $("wiz-close").hidden = step === "done";
  if (step === 2) drawUi();
  if (step === 3) stepThree();
  if (step === 5) review();
  hint();
  if (focus) $("wiz-title").focus({ preventScroll: true });
  $("wiz-body").scrollTop = 0;
  save();
}
// What differs in a change: the vineyard named at the top, the note, the
// pin left out (a change keeps blocks), and the words of the last screens.
function changeMode() {
  const on = Boolean(state.changes);
  $("wiz-change").hidden = !on;
  $("wiz-change").textContent = on ? `Suggesting a change to ${state.listedName}` : "";
  $("note-field").hidden = !on;
  $("public-change").hidden = !on;
  $("to-pin").parentElement.hidden = on;
  $("another").hidden = on;
  $("done-say").textContent = on ? "Your change is with the petitioners." : "Your vineyard is with the petitioners.";
  $("next-map").textContent = on
    ? "Once it's checked, the change appears on this website's map. We'll review it within about a week."
    : "Once it's checked, your vineyard appears on this website's map. We'll review it within about a week.";
}
$("done-close").addEventListener("click", close);
$("another").addEventListener("click", () => {
  state = fresh();
  shot = null;
  fillFields();
  render(); // the last vineyard's blocks leave the map
  show(1);
});

// Back on the screen goes to the step before, whatever the way here was (a
// resumed draft, a Change on the review, a retry); the phone's own Back
// follows the browser's history.
$("back").addEventListener("click", () => {
  if (typeof state.step !== "number" || state.step <= 1) return;
  show(state.step - 1);
});
$("next").addEventListener("click", async () => {
  const step = state.step;
  if (!areas) {
    await loadAreas().catch((error) => console.error("the areas did not load", error));
    if (!areas) {
      return msg("Part of the form didn't load. Check your connection and tap Next again, or email", { email: true });
    }
  }
  if (step === 2 && !finishOpenBlock()) return;
  if (step === 5) return send();
  const errors = stepErrors(step);
  showErrors(step, errors);
  if (errors.length) return;
  if (step === 2) await takeShot();
  show(step + 1);
});

// The submission, as the function receives it.
function payload() {
  let acresTyped = String(state.acres).trim().replace(/\s*(acres?|ac\.?)$/i, "");
  // "4,5" is four and a half; "1,200" is twelve hundred
  acresTyped = /^\d+,\d{1,2}$/.test(acresTyped) ? acresTyped.replace(",", ".") : acresTyped.replace(/,/g, "");
  const acres = acresTyped === "" ? null : Number.isFinite(Number(acresTyped)) ? Number(acresTyped) : acresTyped;
  const others = state.other.split(",").map((s) => s.trim()).filter(Boolean);
  return {
    form: rules.FORM,
    version: state.changes ? rules.CHANGE_VERSION : rules.VERSION,
    id: state.id,
    ...(state.changes ? { changes: state.changes, note: state.note } : {}),
    vineyard: {
      name: state.name,
      county: state.county,
      planted: state.planted,
      acres,
      year: state.year ? Number(state.year) : null,
      varieties: [...state.varieties, ...others],
    },
    blocks: state.mode === "blocks" ? state.blocks : [],
    pin: state.mode === "pin" ? state.pin : null,
    contact: { name: state.cname, email: state.email, phone: state.phone },
    agree: { permission: state.permission, public: state.public },
    website: $("w-extra").value,
  };
}

function allErrors() {
  if (!areas) return [];
  try {
    // the trap is the server's business: a grower is never stopped by it here
    return rules.check({ ...payload(), website: "" }, { llano: areas.llano, district: areas.district, known: known || {} }).errors;
  } catch {
    return [["where", "Something in the form could not be read. Close it and start again."]];
  }
}
const stepErrors = (step) => allErrors().filter(([f]) => STEP_ERRORS[step]?.(f));

function showErrors(step, errors) {
  const box = $("wiz-body");
  for (const p of box.querySelectorAll(`.step[data-step="${step}"] .w-error`)) {
    if (p.id === "err-send") continue;
    p.hidden = true;
    p.textContent = "";
  }
  for (const el of box.querySelectorAll(`.step[data-step="${step}"] [aria-invalid]`)) el.removeAttribute("aria-invalid");
  const where = [];
  let first = null;
  for (const [field, message] of errors) {
    const id = FIELD_ELEMENT[field];
    if (id) {
      const p = $(`err-${field}`);
      if (p && p.hidden) {
        p.textContent = message;
        p.hidden = false;
      }
      $(id).setAttribute("aria-invalid", "true");
      first ||= $(id).matches("fieldset") ? $(id).querySelector("input") : $(id);
    } else {
      where.push(message);
    }
  }
  if (step === 2) {
    $("err-where").textContent = where.join(" ");
    $("err-where").hidden = where.length === 0;
    first ||= where.length ? $("err-where") : null;
    drawUi(errors);
  }
  if (errors.length) {
    say(`${errors.length === 1 ? "One thing" : `${errors.length} things`} to fix: ${errors[0][1]}`);
    if (first) {
      if (first.matches(".w-error")) first.setAttribute("tabindex", "-1");
      first.focus({ preventScroll: false });
      first.scrollIntoView({ block: "center" });
    }
  }
}

// --- step 3, 4, 5: fields ---------------------------------------------------------

const thisYear = new Date().getFullYear();
for (let y = thisYear + 2; y >= 1970; y--) $("w-year").add(new Option(String(y), String(y)));
for (const name of rules.VARIETIES) {
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = "chip";
  chip.textContent = name;
  chip.dataset.variety = name;
  chip.setAttribute("aria-pressed", "false");
  chip.addEventListener("click", () => {
    const on = !state.varieties.includes(name);
    state.varieties = on ? [...state.varieties, name] : state.varieties.filter((v) => v !== name);
    chip.setAttribute("aria-pressed", String(on));
    save();
  });
  $("chips").append(chip);
}
const BIND = {
  "w-name": "name", "w-acres": "acres", "w-other": "other", "w-cname": "cname", "w-phone": "phone", "w-email": "email",
  "w-note": "note",
};
for (const [id, key] of Object.entries(BIND)) {
  $(id).addEventListener("input", () => {
    state[key] = $(id).value;
    save();
  });
}
$("w-county").addEventListener("change", () => {
  state.county = $("w-county").value;
  state.countyPicked = false;
  $("w-county-note").hidden = true;
  save();
});
$("w-year").addEventListener("change", () => {
  state.year = $("w-year").value;
  save();
});
for (const r of document.querySelectorAll('input[name="planted"]')) {
  r.addEventListener("change", () => {
    state.planted = r.value;
    save();
  });
}
$("w-agree-permission").addEventListener("change", (e) => {
  state.permission = e.target.checked;
  save();
});
$("w-agree-public").addEventListener("change", (e) => {
  state.public = e.target.checked;
  save();
});
// Enter on a phone keyboard's "Next" moves to the next box, never sends.
$("wiz-form").addEventListener("submit", (e) => e.preventDefault());
$("wiz-form").addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || e.isComposing || !(e.target instanceof HTMLInputElement)) return;
  e.preventDefault();
  if (e.target.id === "search") return find();
  const boxes = [...wiz.querySelectorAll(".step:not([hidden]) input[type=text], .step:not([hidden]) input[type=tel], .step:not([hidden]) input[type=email]")];
  const next = boxes[boxes.indexOf(e.target) + 1];
  if (next) next.focus();
  else e.target.blur();
});

function fillFields() {
  for (const [id, key] of Object.entries(BIND)) $(id).value = state[key] ?? "";
  $("w-county").value = state.county;
  $("w-county-note").hidden = !state.countyPicked;
  if (state.year && ![...$("w-year").options].some((o) => o.value === String(state.year))) {
    $("w-year").add(new Option(String(state.year), String(state.year))); // a listed year before the list's
  }
  $("w-year").value = state.year;
  for (const r of document.querySelectorAll('input[name="planted"]')) r.checked = r.value === state.planted;
  for (const chip of $("chips").children) chip.setAttribute("aria-pressed", String(state.varieties.includes(chip.dataset.variety)));
  $("w-agree-permission").checked = state.permission;
  $("w-agree-public").checked = state.public;
}

function stepThree() {
  if (!state.county) pickCounty();
  const drawn = state.mode === "blocks" ? state.blocks.reduce((t, r) => t + rules.areaAcres(r), 0) : 0;
  $("acres-hint").textContent = state.mode === "pin"
    ? "Needed with a pin: about how many acres of vines."
    : drawn ? `Your drawing is about ${acresText(drawn)} acres.` : "";
  $("acres-optional").textContent = state.mode === "pin" ? "(about)" : "(if you know)";
}

function pickCounty() {
  const at = state.mode === "pin" ? state.pin : state.blocks[0]?.[0];
  if (!at || !counties.length) return;
  const found = counties.find((c) => c.area.contains(at));
  if (found) {
    state.county = found.name;
    state.countyPicked = true;
    $("w-county").value = found.name;
    $("w-county-note").hidden = false;
    save();
  }
}

function review() {
  const box = $("review");
  box.replaceChildren();
  const card = (title, step, rows, picture) => {
    const c = document.createElement("section");
    c.className = "review-card";
    const head = document.createElement("div");
    head.className = "review-head";
    const h = document.createElement("h3");
    h.textContent = title;
    const change = document.createElement("button");
    change.type = "button";
    change.className = "w-link";
    change.textContent = "Change";
    change.setAttribute("aria-label", `Change ${title.toLowerCase()}`);
    change.addEventListener("click", () => show(step));
    head.append(h, change);
    c.append(head);
    if (picture) {
      const img = document.createElement("img");
      img.className = "review-shot";
      img.src = picture;
      img.alt = "Your blocks on the map";
      c.append(img);
    }
    const dl = document.createElement("dl");
    for (const [k, v] of rows) {
      const dt = document.createElement("dt");
      dt.textContent = k;
      const dd = document.createElement("dd");
      dd.textContent = v || "Not given";
      dl.append(dt, dd);
    }
    c.append(dl);
    box.append(c);
  };
  const p = payload();
  const total = state.blocks.reduce((t, r) => t + rules.areaAcres(r), 0);
  card("Where", 2, state.mode === "pin"
    ? [["Pin", "Dropped on the vineyard"]]
    : [["Blocks", String(state.blocks.length)], ["Drawn", `about ${acresText(total)} acres`]], state.mode === "blocks" ? shot : null);
  card("The vineyard", 3, [
    ["Name", p.vineyard.name], ["County", p.vineyard.county],
    ["Vines", { planted: "Planted", planned: "Planned" }[p.vineyard.planted]],
    ["Acres", p.vineyard.acres === null ? "" : String(p.vineyard.acres)],
    ["Planted in", p.vineyard.year ? String(p.vineyard.year) : ""],
    ["Varieties", p.vineyard.varieties.join(", ")],
    ...(state.changes ? [["What has changed", state.note.trim()]] : []),
  ]);
  card("You (private)", 4, [["Name", state.cname], ["Phone", state.phone], ["Email", state.email]]);
  if (CHECK_ON) loadTurnstile();
  else $("human").hidden = true;
}

// --- the map, and drawing by taps -----------------------------------------------

let view = null;
let esri = null;
let drawLayer = null;
let meLayer = null;

async function loadAreas() {
  if (areas) return;
  const get = (u) => fetch(u).then((r) => {
    if (!r.ok) throw new Error(u);
    return r.json();
  });
  const [llano, district, county] = await Promise.all([get(DATA.llano), get(DATA.district), get(DATA.counties)]);
  areas = { llano: rules.makeArea(llano), district: rules.makeArea(district) };
  counties = county.features.map((f) => ({ name: f.properties.name, area: rules.makeArea(f) }));
}

function loadScript(src, type) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    if (type) s.type = type;
    s.src = src;
    s.async = true;
    s.onload = resolve;
    s.onerror = () => reject(new Error(`${src} did not load`));
    document.head.append(s);
  });
}

let mapStarted = false;
async function openMap() {
  if (mapStarted) return;
  mapStarted = true;
  $("map-failed").hidden = true;
  $("map-loading").hidden = false;
  try {
    if (!window.$arcgis) await loadScript(SDK, "module");
    await customElements.whenDefined("arcgis-map");
    const names = ["config", "Map", "Basemap", "Graphic", "layers/GraphicsLayer", "layers/GeoJSONLayer", "geometry/Point"];
    const [config, Map, Basemap, Graphic, GraphicsLayer, GeoJSONLayer, Point] =
      await Promise.all(names.map((n) => $arcgis.import(`@arcgis/core/${n}.js`)));
    esri = { Graphic, Point };
    if (apiKey) config.apiKey = apiKey;
    const el = $("map");
    const district = new GeoJSONLayer({
      url: DATA.district,
      title: "The proposed Hickory Sands District",
      renderer: { type: "simple", symbol: { type: "simple-fill", color: [0, 0, 0, 0], outline: { color: [...YELLOW, 0.95], width: 2.5, style: "dash" } } },
    });
    drawLayer = new GraphicsLayer();
    meLayer = new GraphicsLayer();
    el.map = new Map({ basemap: new Basemap({ style: { id: "arcgis/imagery" } }), layers: [district, meLayer, drawLayer] });
    el.constraints = { rotationEnabled: false, minZoom: 7, maxZoom: 20, snapToZoom: false };
    const v = state.view;
    el.center = v ? v.center : [-98.95, 30.8];
    el.zoom = v ? v.zoom : 9;
    el.aria = { label: el.getAttribute("aria-label") };
    await el.viewOnReady();
    view = el.view;
    view.on("immediate-click", tap);
    view.on("double-click", (e) => e.stopPropagation()); // fast taps never zoom
    view.on("drag", drag);
    view.on("hold", (e) => e.stopPropagation());
    $arcgis.import("@arcgis/core/core/reactiveUtils.js").then((reactive) => {
      reactive.when(() => view.stationary, () => {
        state.view = { center: [view.center.longitude, view.center.latitude], zoom: view.zoom };
        hint();
        save();
      });
    }).catch((error) => console.error("the map's place will not be kept", error));
    $("map-loading").hidden = true;
    render();
    hint();
  } catch (error) {
    console.error("the map could not be drawn", error);
    mapStarted = false; // closing and reopening the form tries again
    $("map-loading").hidden = true;
    $("map-failed").hidden = false;
  }
}

// A move of the map that a newer one interrupts is no failure; any other is
// logged.
function moved(error) {
  if (error?.name !== "AbortError") console.error("the map could not move", error);
}
$("zoom-in").addEventListener("click", () => view?.goTo({ zoom: view.zoom + 1 }).catch(moved));
$("zoom-out").addEventListener("click", () => view?.goTo({ zoom: view.zoom - 1 }).catch(moved));

function hint() {
  const h = $("map-hint");
  if (!view || (state.step !== 1 && state.step !== 2)) return (h.textContent = "");
  if (state.step === 1) {
    h.textContent = view.zoom < DRAW_ZOOM - 1 ? "Find your vineyard, then zoom in close" : "";
    return;
  }
  if (view.zoom < DRAW_ZOOM) h.textContent = "Zoom in until you can see the rows of vines";
  else if (state.mode === "pin") h.textContent = state.pin ? "Drag the pin, or tap to move it" : "Tap on your vineyard";
  else if (!drawing()) h.textContent = "";
  else if (state.current.length === 0) h.textContent = "Tap a corner of the block";
  else if (state.current.length < 3) h.textContent = "Tap the next corner";
  else h.textContent = "Tap the next corner, or Done";
}

const drawing = () => state.mode === "blocks" && Array.isArray(state.current);
const lonlat = (mapPoint) => [Number(mapPoint.longitude.toFixed(6)), Number(mapPoint.latitude.toFixed(6))];

function tap(event) {
  if (state.step !== 2 || justDragged) return;
  if (view.zoom < DRAW_ZOOM) {
    view.goTo({ target: event.mapPoint, zoom: DRAW_ZOOM + 1.5 }).catch(moved);
    say("Zoomed in. Now tap the corners of the block.");
    return;
  }
  const near = corner(event.x, event.y);
  if (state.mode === "pin") {
    state.pin = lonlat(event.mapPoint);
    say("Pin dropped.");
  } else if (near && near.kind === "current" && near.i === 0 && state.current.length >= 3) {
    finishBlock(); // tapping the first dot closes the block, as Done does
    return;
  } else if (near) {
    // a tap on a dot is the start of a drag, not a new corner: say so
    $("map-hint").textContent = "That's a dot. Drag it to move it, or tap a little further away.";
    say("That's a corner dot. Drag it to move it, or tap a little further away.");
    clearTimeout(tap.timer);
    tap.timer = setTimeout(hint, 2500);
    return;
  } else {
    if (!drawing()) state.current = [];
    state.current.push(lonlat(event.mapPoint));
    const a = state.current.length >= 3 ? `, about ${acresText(rules.areaAcres(state.current))} acres` : "";
    say(`Corner ${state.current.length}${a}.`);
  }
  $("err-where").hidden = true;
  render();
  drawUi();
  save();
}

// The dot under a finger: the block being drawn first, then the others, then the pin.
function corner(x, y) {
  const within = (p) => {
    const s = view.toScreen(new esri.Point({ longitude: p[0], latitude: p[1] }));
    return s && Math.hypot(s.x - x, s.y - y) <= HIT_PX;
  };
  if (state.mode === "pin") return state.pin && within(state.pin) ? { kind: "pin" } : null;
  if (drawing()) {
    const i = state.current.findIndex(within);
    if (i >= 0) return { kind: "current", i };
  }
  for (let b = 0; b < state.blocks.length; b++) {
    const i = state.blocks[b].findIndex(within);
    if (i >= 0) return { kind: "block", b, i };
  }
  return null;
}

let dragging = null;
let justDragged = false;
let frame = 0;
function drag(event) {
  if (state.step !== 2) return;
  if (event.action === "start") dragging = corner((event.origin ?? event).x, (event.origin ?? event).y);
  if (!dragging) return;
  event.stopPropagation(); // the map does not move while a dot does
  const p = lonlat(view.toMap({ x: event.x, y: event.y }));
  if (dragging.kind === "pin") state.pin = p;
  else if (dragging.kind === "current") state.current[dragging.i] = p;
  else state.blocks[dragging.b][dragging.i] = p;
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(render);
  if (event.action === "end") {
    dragging = null;
    justDragged = true;
    setTimeout(() => (justDragged = false), 350);
    drawUi();
    save();
    say("Corner moved.");
  }
}

function polygon(ring) {
  return { type: "polygon", rings: [[...ring, ring[0]]], spatialReference: { wkid: 4326 } };
}
function render() {
  if (!drawLayer) return;
  const { Graphic } = esri;
  const g = [];
  const errors = new Set(allErrors().map(([f]) => f));
  const outline = (ring, closed, bad) => {
    const path = closed ? [...ring, ring[0]] : ring;
    const line = { type: "polyline", paths: [path], spatialReference: { wkid: 4326 } };
    g.push(new Graphic({ geometry: line, symbol: { type: "simple-line", color: [...INK, 0.85], width: 6 } }));
    g.push(new Graphic({ geometry: line, symbol: { type: "simple-line", color: bad ? [255, 80, 60, 1] : [...YELLOW, 1], width: 3 } }));
  };
  const dot = (p, size, fill) => new Graphic({
    geometry: { type: "point", longitude: p[0], latitude: p[1] },
    symbol: { type: "simple-marker", size, color: fill, outline: { color: [...INK, 1], width: 3 } },
  });
  const label = (ring, text) => {
    const lon = ring.reduce((s, p) => s + p[0], 0) / ring.length;
    const lat = ring.reduce((s, p) => s + p[1], 0) / ring.length;
    g.push(new Graphic({
      geometry: { type: "point", longitude: lon, latitude: lat },
      symbol: { type: "text", text, color: [255, 255, 255, 1], haloColor: [...INK, 1], haloSize: 2, font: { size: 15, weight: "bold" } },
    }));
  };
  if (state.mode === "blocks") {
    state.blocks.forEach((ring, b) => {
      const bad = errors.has(`block-${b + 1}`);
      g.push(new Graphic({ geometry: polygon(ring), symbol: { type: "simple-fill", color: [...YELLOW, 0.22], outline: { color: [0, 0, 0, 0], width: 0 } } }));
      outline(ring, true, bad);
      for (const p of ring) g.push(dot(p, 18, [255, 255, 255, 1]));
      label(ring, `Block ${b + 1} · ${acresText(rules.areaAcres(ring))} ac`);
    });
    if (drawing() && state.current.length) {
      const ring = state.current;
      if (ring.length >= 3) {
        g.push(new Graphic({ geometry: polygon(ring), symbol: { type: "simple-fill", color: [...YELLOW, 0.3], outline: { color: [0, 0, 0, 0], width: 0 } } }));
      }
      outline(ring, ring.length >= 3, ring.length >= 3 && rules.crossesItself(ring));
      ring.forEach((p, i) => g.push(dot(p, i === 0 ? 30 : 26, i === 0 ? [...WINE, 1] : [255, 255, 255, 1])));
      if (ring.length >= 3) label(ring, `${acresText(rules.areaAcres(ring))} ac`);
    }
  } else if (state.pin) {
    g.push(dot(state.pin, 34, [...WINE, 1]));
  }
  drawLayer.removeAll();
  drawLayer.addMany(g);
}

// The bar at the foot: Back and Next; while a block is being drawn, Undo and
// Done instead, under the thumb, so the next thing to tap is always there.
function bottom() {
  const corners = state.step === 2 && drawing() && state.current.length > 0;
  $("back").hidden = corners || state.step === 1;
  $("next").hidden = corners;
  $("undo").hidden = !corners;
  $("done-block").hidden = !corners;
  $("done-block").disabled = false; // with fewer than 3 corners, Done says why
  $("wiz-bottom").classList.toggle("one", state.step === 1);
  $("wiz-bottom").classList.toggle("pair", corners);
}

// The panel under the map in step 2.
function drawUi(errors = null) {
  const pin = state.mode === "pin";
  $("draw-mode").hidden = pin;
  $("pin-mode").hidden = !pin;
  const on = drawing();
  const n = on ? state.current.length : 0;
  $("after-row").hidden = on || state.blocks.length === 0;
  bottom();
  $("draw-say").textContent = !on
    ? state.blocks.length
      ? state.changes
        ? "These are the blocks listed now. Drag a corner to move it, remove a block or add one, then tap Next."
        : "Your blocks are drawn. Tap Next, or add another block."
      : "Tap each corner of your block, one after another."
    : n === 0
      ? state.blocks.length ? "Tap each corner of the next block." : "Tap each corner of your block, one after another."
      : n < 3 ? "Keep tapping the corners, all the way round." : "Tap Done when you've been all the way round.";
  $("draw-sub").textContent = n >= 3 ? "Or tap the first dot (the dark one) to finish." : "Drag a dot to move it. You don't need to be exact.";
  $("draw-live").textContent = on && n
    ? `Block ${state.blocks.length + 1}: ${n} corner${n === 1 ? "" : "s"}${n >= 3 ? ` · about ${acresText(rules.areaAcres(state.current))} acres` : ""}`
    : "";
  const found = new Map((errors || []).filter(([f]) => f.startsWith("block-")).map(([f, m]) => [Number(f.slice(6)), m]));
  const list = $("block-list");
  list.replaceChildren();
  if (pin) return hint();
  state.blocks.forEach((ring, b) => {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.className = "block-name";
    name.textContent = `Block ${b + 1} · about ${acresText(rules.areaAcres(ring))} acres`;
    if (found.has(b + 1)) {
      li.classList.add("bad");
      const small = document.createElement("small");
      small.textContent = found.get(b + 1);
      name.append(small);
    }
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "w-button w-secondary";
    remove.textContent = "Remove";
    remove.setAttribute("aria-label", `Remove block ${b + 1}`);
    remove.addEventListener("click", () => {
      state.blocks.splice(b, 1);
      if (!state.blocks.length) state.current = [];
      say(`Block ${b + 1} removed.`);
      render();
      drawUi();
      save();
    });
    li.append(name, remove);
    list.append(li);
  });
  hint();
}

// Done with this block: kept only when it is a block that can be sent.
function finishBlock() {
  const ring = state.current;
  let problem = null;
  if (ring.length < 3) problem = "A block needs at least 3 corners. Tap more corners on the map.";
  else if (rules.crossesItself(ring)) problem = "The edges cross. Drag a corner so they don't, or undo the last corner.";
  else if (areas && areas.llano.relation(ring) !== "in") {
    problem = "This block is outside the area this register covers (the proposed Llano Uplift AVA). Check that the map is on your vineyard.";
  }
  if (problem) {
    $("err-where").textContent = problem;
    $("err-where").hidden = false;
    say(problem);
    return false;
  }
  state.blocks.push(ring);
  state.current = null;
  $("err-where").hidden = true;
  say(`Block ${state.blocks.length} done: about ${acresText(rules.areaAcres(ring))} acres.`);
  render();
  drawUi();
  $("draw-say").focus({ preventScroll: true });
  save();
  if (!state.county) pickCounty();
  return true;
}
// Next with a block half drawn: three corners or more finish it; fewer stop.
function finishOpenBlock() {
  if (state.mode !== "blocks" || !drawing() || state.current.length === 0) return true;
  if (state.current.length >= 3) return finishBlock();
  $("err-where").textContent = "Finish the block (at least 3 corners), or undo its corners.";
  $("err-where").hidden = false;
  say($("err-where").textContent);
  return false;
}

$("undo").addEventListener("click", () => {
  if (!drawing() || !state.current.length) return;
  state.current.pop();
  say(state.current.length ? `Corner removed. ${state.current.length} left.` : "Corner removed.");
  render();
  drawUi();
  save();
});
$("done-block").addEventListener("click", finishBlock);
$("add-block").addEventListener("click", () => {
  state.current = [];
  say("Tap each corner of the next block.");
  drawUi();
  hint();
  save();
});
$("start-over").addEventListener("click", () => {
  $("confirm-over").hidden = false;
  $("over-yes").focus();
});
$("over-no").addEventListener("click", () => {
  $("confirm-over").hidden = true;
  $("start-over").focus();
});
$("over-yes").addEventListener("click", () => {
  state.blocks = [];
  state.current = [];
  $("confirm-over").hidden = true;
  say("All blocks removed. Tap each corner of your block.");
  render();
  drawUi();
  save();
});
$("to-pin").addEventListener("click", () => {
  state.mode = "pin";
  $("wiz-body").scrollTop = 0;
  say("Tap the map on your vineyard to drop a pin.");
  render();
  drawUi();
  save();
});
$("to-draw").addEventListener("click", () => {
  state.mode = "blocks";
  $("wiz-body").scrollTop = 0;
  if (!state.blocks.length) state.current = [];
  say("Tap each corner of your block.");
  render();
  drawUi();
  save();
});
$("corner-centre").addEventListener("click", () => {
  if (!view) return;
  tap({ mapPoint: view.center, x: -1000, y: -1000 });
});
$("pin-centre").addEventListener("click", () => {
  if (!view) return;
  state.pin = lonlat(view.center);
  say("Pin dropped at the center of the map.");
  render();
  save();
});
for (const id of ["corner-centre", "pin-centre"]) {
  $(id).addEventListener("focus", () => ($("map-cross").hidden = false));
  $(id).addEventListener("blur", () => ($("map-cross").hidden = true));
}

// A picture of the blocks for the review (in memory only, never sent).
async function takeShot() {
  shot = null;
  if (!view || state.mode !== "blocks" || !state.blocks.length) return;
  try {
    const all = state.blocks.flat();
    const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
    const pad = 0.25 * Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), 0.001);
    await view.goTo({ type: "extent", xmin: Math.min(...xs) - pad, ymin: Math.min(...ys) - pad, xmax: Math.max(...xs) + pad, ymax: Math.max(...ys) + pad, spatialReference: { wkid: 4326 } }, { animate: false });
    const picture = await view.takeScreenshot({ format: "jpg", quality: 75, width: 720 });
    shot = picture.dataUrl;
  } catch {
    shot = null; // the review shows the figures without the picture
  }
}

// --- finding the vineyard ----------------------------------------------------------

function locate() {
  const status = $("locate-status");
  if (!navigator.geolocation) {
    status.textContent = "This phone can't share its location. Search for a road or town instead.";
    return;
  }
  status.textContent = "Finding you…";
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const at = [pos.coords.longitude, pos.coords.latitude];
      status.textContent = "Found you. Move the map if your vines are off to one side.";
      if (meLayer && esri) {
        meLayer.removeAll();
        meLayer.add(new esri.Graphic({
          geometry: { type: "point", longitude: at[0], latitude: at[1] },
          symbol: { type: "simple-marker", size: 16, color: [26, 115, 232, 1], outline: { color: [255, 255, 255, 1], width: 3 } },
        }));
      }
      view?.goTo({ center: at, zoom: 17 }).catch(moved);
      say("Found your location. The map is on it.");
    },
    () => {
      status.textContent = "Your phone didn't share its location. Search for a road or town instead, or move the map.";
    },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
  );
}
$("locate").addEventListener("click", locate);
$("locate-map").addEventListener("click", locate);

const EXTENT = JSON.stringify({ xmin: -99.6, ymin: 30.1, xmax: -98.0, ymax: 31.4, spatialReference: { wkid: 4326 } });
async function find() {
  const text = $("search").value.trim();
  const list = $("search-results");
  list.replaceChildren();
  if (!text) return;
  const status = document.createElement("li");
  status.textContent = "Searching…";
  list.append(status);
  try {
    const q = new URLSearchParams({ f: "json", text, maxSuggestions: "5", countryCode: "USA", location: "-98.95,30.8", searchExtent: EXTENT, token: apiKey });
    const answer = await geocode(`${GEOCODE}/suggest?${q}`);
    list.replaceChildren();
    const found = (answer.suggestions || []).filter((s) => !s.isCollection);
    if (!found.length) {
      const li = document.createElement("li");
      li.textContent = "Nothing found. Try a road name and a town, like County Road 103, Mason.";
      list.append(li);
      return;
    }
    for (const s of found) {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = s.text;
      b.addEventListener("click", () => go(s));
      li.append(b);
      list.append(li);
    }
    say(`${found.length} places found.`);
  } catch (error) {
    console.error("the search did not answer", error);
    list.replaceChildren();
    const li = document.createElement("li");
    li.textContent = "The search isn't working just now. Move the map to your vineyard instead, or use your location.";
    list.append(li);
    say(li.textContent);
  }
}
// Esri's answer, or an error: an error status, or an answer that says it is
// one (Esri answers some errors with 200 and {"error": ...}).
async function geocode(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`search ${r.status}`);
  const answer = await r.json();
  if (answer?.error) throw new Error(`search ${answer.error.code}: ${answer.error.message}`);
  return answer;
}
async function go(suggestion) {
  try {
    const q = new URLSearchParams({ f: "json", singleLine: suggestion.text, magicKey: suggestion.magicKey, maxLocations: "1", token: apiKey });
    const answer = await geocode(`${GEOCODE}/findAddressCandidates?${q}`);
    const c = answer.candidates?.[0];
    if (!c) throw new Error("no place for the suggestion");
    await view?.goTo({ center: [c.location.x, c.location.y], zoom: 16 });
    $("search-results").replaceChildren();
    say(`The map is at ${suggestion.text}. Move it to your vines.`);
  } catch (error) {
    console.error("the place could not be shown", error);
    msg("That place could not be shown. Move the map to your vineyard instead.");
  }
}
$("search-go").addEventListener("click", find);

// --- sending ------------------------------------------------------------------------

// Cloudflare's check that a person is sending. It is given TURNSTILE_ERRORS
// errors or TURNSTILE_WAIT_MS before Send offers the email instead; every
// error is logged with Cloudflare's code; a script that did not load is
// loaded again on Try again.
const TURNSTILE_ERRORS = 3;
const TURNSTILE_WAIT_MS = 30000;
let turnstileLoading = null;
let turnstileFailed = false;
let turnstileErrors = 0;
let turnstileSince = 0;
let widget = null;
function turnstileGaveUp(why) {
  turnstileFailed = true;
  $("human-note").textContent = `${why} Tap Send to send it by email instead.`;
}
function loadTurnstile() {
  if (!turnstileSince) turnstileSince = Date.now();
  turnstileLoading ||= loadScript(TURNSTILE).catch((error) => {
    turnstileLoading = null; // Try again loads it again
    throw error;
  });
  turnstileLoading.then(() => {
    if (widget !== null || !window.turnstile) return;
    $("human").hidden = false;
    widget = window.turnstile.render("#turnstile", {
      sitekey: turnstileSiteKey,
      action: "vineyard-submit",
      size: "flexible",
      theme: "light",
      "retry-interval": 4000,
      callback: (t) => {
        token = t;
        turnstileErrors = 0;
        turnstileFailed = false;
        $("human-note").textContent = "Checked. You can send it.";
      },
      "expired-callback": () => {
        token = null;
        $("human-note").textContent = "The check ran out. It will run again by itself.";
      },
      "error-callback": (code) => {
        token = null;
        turnstileErrors += 1;
        console.error("the person check failed", code);
        if (turnstileErrors >= TURNSTILE_ERRORS) turnstileGaveUp("The check that you're a person isn't working.");
        else $("human-note").textContent = "The check that you're a person didn't work. It tries again by itself.";
        return false; // Cloudflare retries by itself, every few seconds
      },
    });
  }).catch((error) => {
    console.error("the person check did not load", error);
    turnstileGaveUp("The check that you're a person could not load.");
  });
}
// Try again: a fresh start for the check, and its script loaded again if it
// did not load before.
function retryTurnstile() {
  turnstileFailed = false;
  turnstileErrors = 0;
  turnstileSince = 0;
  token = null;
  if (widget !== null) {
    window.turnstile?.reset(widget); // a token is good for one send
    $("human-note").textContent = "Checking again…";
  }
}

// How many times Send may be refused in a row (by the person check, or a
// send still under way) before the email is offered instead.
const SEND_RETRIES = 3;
let refusals = 0;
// A change the function cannot take (a vineyard it does not know, or a
// function from before changes): no box can put it right, so the email.
const CANNOT_CHANGE = "This vineyard can't be changed from this page just now.";
async function send() {
  const errors = allErrors();
  if (errors.some(([f]) => f === "changes")) {
    $("fail-say").textContent = CANNOT_CHANGE;
    console.error("the change names no listed vineyard");
    return failed();
  }
  if (errors.length) {
    const step = [2, 3, 4, 5].find((s) => errors.some(([f]) => STEP_ERRORS[s](f)));
    if (step !== 5) show(step);
    showErrors(step, errors.filter(([f]) => STEP_ERRORS[step](f)));
    return;
  }
  if (!READY) {
    $("fail-say").textContent = "Sending from this page isn't open yet.";
    return failed();
  }
  if (CHECK_ON && (turnstileFailed || (!token && Date.now() - turnstileSince > TURNSTILE_WAIT_MS))) {
    $("fail-say").textContent = "The check that you're a person isn't working.";
    console.error("the person check gave no answer", turnstileErrors, "errors");
    return failed();
  }
  if (CHECK_ON && !token) {
    $("err-send").textContent = "Wait a moment for the check above to finish, then tap Send.";
    $("err-send").hidden = false;
    return;
  }
  $("err-send").hidden = true;
  $("next").disabled = true;
  $("next").textContent = "Sending…";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25000);
  let answer = null;
  let status = 0;
  try {
    const r = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(CHECK_ON ? { ...payload(), turnstile: token } : payload()),
      signal: controller.signal,
    });
    status = r.status;
    answer = await r.json().catch((error) => {
      console.error("the answer could not be read", error);
      return null;
    });
  } catch (error) {
    console.error("the vineyard could not be sent", error);
    status = 0;
  } finally {
    clearTimeout(timer);
  }
  token = null;
  if (widget !== null) {
    window.turnstile?.reset(widget); // a token is good for one send
    $("human-note").textContent = "Checking again…";
  }
  $("next").disabled = false;
  $("next").textContent = "Send";
  if (status === 200 && answer?.ok) {
    refusals = 0;
    return sent(answer);
  }
  if (state.changes && (status === 400 || (status === 422 && answer?.errors?.some?.((e) => e?.field === "changes")))) {
    refusals = 0;
    console.error("the change was not taken", status);
    $("fail-say").textContent = CANNOT_CHANGE;
    return failed();
  }
  if (status === 422 && Array.isArray(answer?.errors) && answer.errors.length) {
    const list = answer.errors.map((e) => [e.field, e.message]);
    const step = [2, 3, 4, 5].find((s) => list.some(([f]) => STEP_ERRORS[s](f))) || 5;
    if (step !== 5) show(step);
    const own = list.filter(([f]) => STEP_ERRORS[step]?.(f));
    if (own.length) return showErrors(step, own);
    // a refusal no box on the page can show: said, and the email offered
    console.error("the vineyard was refused", list.map(([f]) => f).join(", "));
    $("err-send").textContent = list[0][1];
    $("err-send").hidden = false;
    return;
  }
  // Refusals Send can get past by itself (the person check refused, the first
  // send still under way): said, and tried again; after SEND_RETRIES, the email.
  // (A 403 "turnstile" with no check on this page: the function asks for one
  // the page was not given; trying again cannot help, so the email.)
  if ((CHECK_ON && status === 403 && answer?.error === "turnstile") || status === 409) {
    refusals += 1;
    console.error("the vineyard was not sent yet", status, answer?.error || "");
    if (refusals < SEND_RETRIES) {
      $("err-send").textContent = status === 409
        ? "It's still being sent. Wait a moment, then tap Send again."
        : "The check that you're a person didn't go through. It runs again by itself; then tap Send.";
      $("err-send").hidden = false;
      return;
    }
  }
  refusals = 0;
  $("fail-say").textContent = answer?.error === "limit-ip"
    ? "Several vineyards have already been sent from this internet connection today."
    : answer?.error === "limit-day"
      ? "The form has had a lot of use today."
      : "It didn't go through just now.";
  if (status !== 0) console.error("the vineyard was not sent", status, answer?.error || "");
  failed();
}

function sent(answer) {
  forget();
  $("ref-line").hidden = answer.reference === null || answer.reference === undefined;
  $("ref").textContent = String(answer.reference ?? "");
  state.step = "done";
  show("done");
  say(answer.reference ? `Sent. Your reference number is ${answer.reference}.` : "Sent.");
  const change = Boolean(state.changes);
  state = { ...fresh(), step: "done" };
  shot = null;
  if (!change) {
    $("start").textContent = "Add another vineyard";
    $("draft-note").hidden = true;
  }
}

// The email fallback (vineyard-email.js): the whole message in the email when
// it fits; else the details are copied, and the email asks for them to be
// pasted. The screen says which happened, and a failure is logged.
let mail = null;
// The email's message: for a change, it names the listed vineyard.
const email = () => message(payload(), state.changes ? { id: state.changes, name: state.listedName } : null);
function failed() {
  mail = plan(email());
  $("mail").href = mail.url;
  $("mail-note").textContent = mail.long
    ? "The details are too long for an email link: tapping it copies them, and the email asks you to paste them in."
    : "Your email app opens with the details filled in. Nothing is sent until you send it there.";
  $("copy-status").textContent = "";
  // Not set up yet: trying again cannot help, so only the email is offered.
  $("retry").hidden = !READY;
  const cannot = $("fail-say").textContent === CANNOT_CHANGE;
  if (cannot) $("retry").hidden = true; // nor for a change the function cannot take
  saveNow();
  const kept = keeps ? "Your answers are kept on this device." : "Your answers stay only while this page is open.";
  const after = state.changes ? "the petitioners make the change" : "the petitioners add your vineyard";
  $("fail-lead").textContent = READY && !cannot
    ? `${kept} Try again in a minute, or send them by email instead.`
    : `${kept} Send them by email instead, and ${after}.`;
  show("failed");
}
function copyDetails(after) {
  const text = email().body.replace(/\r\n/g, "\n");
  if (!navigator.clipboard?.writeText) {
    console.error("this browser cannot copy");
    $("copy-status").textContent = `Your browser would not copy them. Email ${ADDRESS} with the details instead.`;
    return;
  }
  navigator.clipboard.writeText(text).then(
    () => ($("copy-status").textContent = after),
    (error) => {
      console.error("the details could not be copied", error);
      $("copy-status").textContent = `Your browser would not copy them. Email ${ADDRESS} with the details instead.`;
    },
  );
}
$("retry").addEventListener("click", () => {
  retryTurnstile();
  show(5); // the review loads the person check again
});
$("copy").addEventListener("click", () => copyDetails(`Copied. Paste them into an email to ${ADDRESS}.`));
$("mail").addEventListener("click", () => {
  window.hsdTrack?.("vineyard_form", { step: "email_fallback" });
  if (mail?.long) copyDetails("Copied. Paste them into the email that opened.");
});

// Opened from a link to vineyards.html#add-vineyard: straight into the form.
// From vineyards.html#change=<id> (a vineyard's popup on the map): the form
// for a change to that vineyard; followed on this page, the same. The address
// is left as it came (no script writes it).
function changeFromAddress() {
  if (!location.hash.startsWith("#change=")) return;
  openChange(location.hash.slice("#change=".length));
}
if (location.hash === "#add-vineyard") open();
else changeFromAddress();
addEventListener("hashchange", changeFromAddress);
