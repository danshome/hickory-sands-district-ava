// A vineyard sent through the form (vineyards.html, "Add your vineyard"): the
// rules, the blocks' acres and the public issue's text. One module for the
// page (it checks each step as the grower goes) and the Supabase Edge Function
// (src/vineyards/functions/vineyard-submit/, which checks again before
// anything is posted), so both say the same thing. The Python twin,
// src/vineyards/submission.py, which the repository's Actions run, is held to
// the same results by tests/test_vineyard_rules.py. No page code and no
// imports: node and Deno run it as it is. Text from a grower is only ever set
// as text.
//
// Version 1 adds a vineyard. Version 2 suggests a change to a listed one
// ("Suggest a change"): it names the vineyard by its id (changes: one of the
// ids of assets/vineyards/known.json, which the page and the function both
// read from the site) and carries the sender's short public note on what changed. A
// function from before version 2 refuses it as unreadable, so a change is
// never posted as a new vineyard.

export const FORM = "hsd-vineyard";
export const VERSION = 1;
export const CHANGE_VERSION = 2;
export const MARK = "<!-- hsd-vineyard-submission: v1 -->";
export const COUNTIES = ["Blanco", "Burnet", "Gillespie", "Llano", "Mason",
  "McCulloch", "San Saba", "Not sure"];
export const VARIETIES = ["Aglianico", "Albariño", "Barbera",
  "Blanc du Bois", "Cabernet Sauvignon", "Charbono", "Chardonnay",
  "Chenin Blanc", "Cinsault", "Graciano", "Grenache", "Grenache Blanc",
  "Malbec", "Malvasia Bianca", "Marsanne", "Merlot", "Montepulciano",
  "Mourvèdre", "Muscat Canelli", "Petit Verdot", "Petite Sirah",
  "Picpoul Blanc", "Pinot Grigio", "Roussanne", "Ruby Cabernet",
  "Sangiovese", "Semillon", "Syrah", "Tannat", "Tempranillo",
  "Touriga Nacional", "Vermentino", "Viognier"];
export const LIMITS = {
  name: 80, variety: 40, varieties: 20, contactName: 80, email: 120,
  phone: 30, blocks: 20, corners: 100, blockMinAcres: 0.02,
  blockMaxAcres: 300, totalMaxAcres: 2000, acresMax: 2000, yearMin: 1900,
  yearAhead: 5, bodyBytes: 65536, note: 300,
};
const TEXAS = [-107, 25, -93, 37];
export const ACRE_M2 = 4046.8564224;
const A = 6378137;
const F = 1 / 298.257222101;
const E2 = F * (2 - F);
const E = Math.sqrt(E2);

// The generator's privacy rules (src/site/aquifer/vineyards.py named()).
const PERSONAL = /\b(Dan|Daniel|McLaughlin)\b|\b(owner|owners|proprietor)\b/i;
const TITLE = /\b(mr|mrs|ms|miss|dr)\.?\s+[a-z]/i;
const PHONE_IN_TEXT = /\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b/;
const EMAIL_IN_TEXT = /\S+@\S+/;
const PUBLIC_TEXT = /^[\p{L}\p{N}_ .,'’&()/:-]*$/u;
const WEBBY = /https?:|www\.|\/\/|(?<![\p{L}\p{N}_])[a-z0-9-]+\.(com|net|org|io|co|us|info|biz|xyz|ru|cn|top|site|online|shop|app|dev|link|me|ly|tk|gg)(?![\p{L}\p{N}_])/iu;
const PERSON_TEXT = /^\p{L}+(?:[ .'’-]+\p{L}+)*\.?$/u;
const EMAIL = /^[^\s@<>()[\],;:"]+@[^\s@<>()[\],;:"]+\.[a-z]{2,}$/i;
const DIGIT_RUN = /\d{7,}/;
const SEPARATORS = /[\s().\/-]/g;
const VINEYARD_ID = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const UUID4 =/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const DROP = /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}]/u;
const SPACE = /[\t\r\n\p{Zs}\p{Zl}\p{Zp}]/u;

// --- text ---------------------------------------------------------------------

// One line of text: NFC, no control or format characters, one space.
export function clean(value, limit) {
  if (typeof value !== "string") return "";
  let out = "";
  for (const ch of value.normalize("NFC")) {
    if (SPACE.test(ch)) out += " ";
    else if (!DROP.test(ch)) out += ch;
  }
  const text = out.split(" ").filter(Boolean).join(" ");
  return limit ? Array.from(text).slice(0, limit).join("") : text;
}

// Why a public free-text value is refused, or null: "web", "characters",
// "contact" (an email address or a telephone number, however written),
// "title", "personal" (the rest of the generator's privacy rule). Public text
// is posted at once.
export function publicTextProblem(text) {
  if (WEBBY.test(text)) return "web";
  if (!PUBLIC_TEXT.test(text)) return "characters";
  if (DIGIT_RUN.test(text.replace(SEPARATORS, "")) || EMAIL_IN_TEXT.test(text) || PHONE_IN_TEXT.test(text)) {
    return "contact";
  }
  if (TITLE.test(text)) return "title";
  if (PERSONAL.test(text)) return "personal";
  return null;
}

export const NAME_PROBLEMS = {
  web: "Leave web addresses out of the name.",
  characters: "Use only letters, numbers and simple punctuation.",
  contact: "Leave phone numbers and email addresses out of the name. There is a place for them in step 4.",
  title: "Leave out titles like Mr., Mrs. or Dr. (write Drive in full).",
  personal: "The register can't show this name as written. Change the wording, or email the petitioners.",
};

export const NOTE_PROBLEMS = {
  web: "Leave web addresses out of the note.",
  characters: "Use only letters, numbers and simple punctuation in the note.",
  contact: "Leave phone numbers and email addresses out of the note. There is a place for them in step 4.",
  title: "Leave out titles like Mr., Mrs. or Dr. (write Drive in full).",
  personal: "The register can't show this note as written. Change the wording, or email the petitioners.",
};

// A US telephone number as (325) 555-0100, or null.
export function phoneFormat(text) {
  let d = text.replace(/\D/g, "");
  if (d.length === 11 && d[0] === "1") d = d.slice(1);
  if (d.length !== 10 || !/^[\d\s().+-]*$/.test(text)) return null;
  return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`;
}

// --- geometry -----------------------------------------------------------------

function q(phi) {
  const s = Math.sin(phi);
  return (1 - E2) * (s / (1 - E2 * s * s) -
    (1 / (2 * E)) * Math.log((1 - E * s) / (1 + E * s)));
}
const QP = q(Math.PI / 2);
const RQ = A * Math.sqrt(QP / 2);
const rad = (d) => (d * Math.PI) / 180;
const authalic = (lat) => Math.asin(Math.max(-1, Math.min(1, q(rad(lat)) / QP)));

// A ring on an equal-area plane in metres (the sinusoidal projection of the
// authalic sphere): areas on it are areas on the ellipsoid.
function plane(ring) {
  const lon0 = ring.reduce((s, p) => s + p[0], 0) / ring.length;
  const b0 = authalic(ring[0][1]);
  return ring.map(([lon, lat]) => {
    const b = authalic(lat);
    return [RQ * rad(lon - lon0) * Math.cos(b), RQ * (b - b0)];
  });
}

// The area of an open ring of [lon, lat], in acres.
export function areaAcres(ring) {
  if (ring.length < 3) return 0;
  const pts = plane(ring);
  let s = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x1, y1] = pts[i];
    const [x2, y2] = pts[(i + 1) % pts.length];
    s += x1 * y2 - x2 * y1;
  }
  return Math.abs(s) / 2 / ACRE_M2;
}

const orient = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
const on = (a, b, c) => Math.min(a[0], b[0]) <= c[0] && c[0] <= Math.max(a[0], b[0]) &&
  Math.min(a[1], b[1]) <= c[1] && c[1] <= Math.max(a[1], b[1]);

export function segmentsMeet(a, b, c, d) {
  const o1 = orient(a, b, c), o2 = orient(a, b, d), o3 = orient(c, d, a), o4 = orient(c, d, b);
  if (((o1 > 0 && o2 < 0) || (o1 < 0 && o2 > 0)) && ((o3 > 0 && o4 < 0) || (o3 < 0 && o4 > 0))) {
    return true;
  }
  return (o1 === 0 && on(a, b, c)) || (o2 === 0 && on(a, b, d)) ||
    (o3 === 0 && on(c, d, a)) || (o4 === 0 && on(c, d, b));
}

// Whether an open ring's edges cross or touch, or a corner folds back.
export function crossesItself(ring) {
  const pts = plane(ring);
  const n = pts.length;
  const edges = pts.map((p, i) => [p, pts[(i + 1) % n]]);
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (j === i + 1 || (i === 0 && j === n - 1)) {
        const [a, b] = edges[i];
        const [c, d] = edges[j];
        const [shared, p, r] = j === i + 1 ? [b, a, d] : [a, b, c];
        const v1 = [p[0] - shared[0], p[1] - shared[1]];
        const v2 = [r[0] - shared[0], r[1] - shared[1]];
        const cross = v1[0] * v2[1] - v1[1] * v2[0];
        const dot = v1[0] * v2[0] + v1[1] * v2[1];
        const n1 = Math.hypot(...v1), n2 = Math.hypot(...v2);
        if (n1 && n2 && Math.abs(cross) <= 1e-9 * n1 * n2 && dot > 0) return true;
        continue;
      }
      if (segmentsMeet(...edges[i], ...edges[j])) return true;
    }
  }
  return false;
}

export function pointInRing([x, y], ring) {
  let inside = false;
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[(i + 1) % ring.length];
    if ((y1 > y) !== (y2 > y) && x < x1 + ((y - y1) * (x2 - x1)) / (y2 - y1)) inside = !inside;
  }
  return inside;
}

// A polygon to test blocks against, from GeoJSON (a FeatureCollection's first
// feature, a Feature or a geometry; Polygon or MultiPolygon).
export function makeArea(geojson) {
  const geom = geojson.features ? geojson.features[0].geometry : geojson.geometry || geojson;
  const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
  const rings = polys.flatMap((poly) => poly.map((r) => r.map((p) => [p[0], p[1]])));
  const edges = [];
  for (const r of rings) {
    for (let i = 0; i + 1 < r.length; i++) {
      const [a, b] = [r[i], r[i + 1]];
      edges.push([a, b, Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])]);
    }
  }
  const contains = (pt) => rings.reduce((inside, r) => (pointInRing(pt, r) ? !inside : inside), false);
  const crossed = (a, b) => {
    const w = Math.min(a[0], b[0]), s = Math.min(a[1], b[1]);
    const e = Math.max(a[0], b[0]), n = Math.max(a[1], b[1]);
    return edges.some(([p, r, ew, es, ee, en]) => ew <= e && ee >= w && es <= n && en >= s &&
      segmentsMeet(a, b, p, r));
  };
  // "in", "out" or "both": where an open ring lies against the area.
  const relation = (ring) => {
    const flags = new Set(ring.map(contains));
    if (flags.size === 2 || ring.some((p, i) => crossed(p, ring[(i + 1) % ring.length]))) return "both";
    return flags.has(true) ? "in" : "out";
  };
  return { contains, relation };
}

export function ringsOverlap(r1, r2) {
  const xs1 = r1.map((p) => p[0]), xs2 = r2.map((p) => p[0]);
  const ys1 = r1.map((p) => p[1]), ys2 = r2.map((p) => p[1]);
  if (Math.max(...xs1) < Math.min(...xs2) || Math.max(...xs2) < Math.min(...xs1) ||
    Math.max(...ys1) < Math.min(...ys2) || Math.max(...ys2) < Math.min(...ys1)) return false;
  for (let i = 0; i < r1.length; i++) {
    for (let j = 0; j < r2.length; j++) {
      if (segmentsMeet(r1[i], r1[(i + 1) % r1.length], r2[j], r2[(j + 1) % r2.length])) return true;
    }
  }
  return pointInRing(r1[0], r2) || pointInRing(r2[0], r1);
}

// Whether two open rings are the same block, to the 6 decimal places a
// submission keeps: from any corner, either way round.
const ringKey = (r) => r.map((p) => `${Number(p[0]).toFixed(6)},${Number(p[1]).toFixed(6)}`);
export function sameRing(a, b) {
  const x = ringKey(a), y = ringKey(b).join(" ");
  if (x.length !== ringKey(b).length || !x.length) return false;
  for (const r of [x, [...x].reverse()]) {
    for (let k = 0; k < r.length; k++) {
      if ([...r.slice(k), ...r.slice(0, k)].join(" ") === y) return true;
    }
  }
  return false;
}

// --- the submission -----------------------------------------------------------

export class Invalid extends Error {}

// Strict JSON, as the function reads a request: at most LIMITS.bodyBytes
// bytes; JSON.parse already refuses NaN and Infinity.
export function parse(text) {
  if (new TextEncoder().encode(text).length > LIMITS.bodyBytes) throw new Invalid("too large");
  try {
    return JSON.parse(text);
  } catch {
    throw new Invalid("not JSON");
  }
}

const number = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const round = (v, places) => Number(v.toFixed(places));

function point(value) {
  if (!Array.isArray(value) || value.length !== 2) return null;
  const lon = number(value[0]), lat = number(value[1]);
  if (lon === null || lat === null) return null;
  if (!(TEXAS[0] <= lon && lon <= TEXAS[2] && TEXAS[1] <= lat && lat <= TEXAS[3])) return null;
  return [round(lon, 6), round(lat, 6)];
}

// An open ring of rounded [lon, lat]: no repeats, no closing corner.
export function ring(value) {
  if (!Array.isArray(value) || value.length > LIMITS.corners + 1) return null;
  const out = [];
  for (const v of value) {
    const p = point(v);
    if (p === null) return null;
    const last = out[out.length - 1];
    if (!last || last[0] !== p[0] || last[1] !== p[1]) out.push(p);
  }
  if (out.length > 1 && out[0][0] === out[out.length - 1][0] && out[0][1] === out[out.length - 1][1]) out.pop();
  return out;
}

const obj = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});
const s = (n) => (n === 1 ? "" : "s");

// Checks a submission: { submission, errors, facts }, as vineyard_check.check().
// areas: { llano, district } from makeArea(); district may be left out (the
// function does not need it), and then each fact's district is null. known:
// the listed vineyards by id (assets/vineyards/known.json), which a change
// must name.
export function check(raw, { llano, district = null, known = {}, year = new Date().getUTCFullYear() }) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw) || raw.form !== FORM) {
    throw new Invalid("not a vineyard submission");
  }
  if (raw.version !== VERSION && raw.version !== CHANGE_VERSION) throw new Invalid("an unknown version");
  const change = raw.version === CHANGE_VERSION;
  if (typeof raw.id !== "string" || !UUID4.test(raw.id)) throw new Invalid("no submission id");
  const errors = [];
  const err = (field, message) => errors.push([field, message]);
  const v = obj(raw.vineyard), c = obj(raw.contact), agree = obj(raw.agree);

  // 1-2. where: the blocks, or a pin
  const blocks = [];
  const facts = [];
  let rawBlocks = raw.blocks ?? [];
  if (!Array.isArray(rawBlocks)) throw new Invalid("blocks");
  if (rawBlocks.length > LIMITS.blocks) {
    err("blocks", `Send up to ${LIMITS.blocks} blocks at a time.`);
    rawBlocks = rawBlocks.slice(0, LIMITS.blocks);
  }
  rawBlocks.forEach((rb, k) => {
    const i = k + 1;
    const r = ring(rb);
    if (r === null) return err(`block-${i}`, `Block ${i} could not be read. Start it again.`);
    if (r.length < 3) return err(`block-${i}`, `Block ${i} needs at least 3 corners.`);
    if (r.length > LIMITS.corners) {
      return err(`block-${i}`, `Block ${i} has more than ${LIMITS.corners} corners. ` +
        "Use fewer: one at each turn of the edge is enough.");
    }
    const acres = areaAcres(r);
    const fact = { block: i, corners: r.length, acres: round(acres, 2) };
    if (crossesItself(r)) {
      err(`block-${i}`, `Block ${i}'s edges cross. Drag a corner so they don't, or start the block again.`);
    } else if (acres < LIMITS.blockMinAcres) {
      err(`block-${i}`, `Block ${i} is very small. Check its corners.`);
    } else if (acres > LIMITS.blockMaxAcres) {
      err(`block-${i}`, `Block ${i} is very large. Draw just the vines, not the whole property.`);
    }
    if (llano.relation(r) !== "in") {
      err(`block-${i}`, `Block ${i} is outside the area this register covers ` +
        "(the proposed Llano Uplift AVA). Check that the map is on your vineyard.");
    }
    fact.district = district ? district.relation(r) : null;
    blocks.push(r);
    facts.push(fact);
  });
  // A change may keep two listed blocks that touch as they are listed.
  const listedRings = change && typeof raw.changes === "string" &&
    Object.prototype.hasOwnProperty.call(known, raw.changes) ? known[raw.changes].blocks || [] : [];
  const asListed = (r) => listedRings.some((l) => sameRing(r, l));
  for (let i = 0; i < blocks.length; i++) {
    for (let j = i + 1; j < blocks.length; j++) {
      const kept = asListed(blocks[i]) && asListed(blocks[j]) && !sameRing(blocks[i], blocks[j]);
      if (ringsOverlap(blocks[i], blocks[j]) && !kept) {
        err(`block-${j + 1}`, `Blocks ${i + 1} and ${j + 1} overlap. Move a corner so they don't.`);
      }
    }
  }
  if (facts.reduce((t, f) => t + f.acres, 0) > LIMITS.totalMaxAcres) {
    err("blocks", "The blocks add up to too many acres. Draw just the vines.");
  }
  let pin = null;
  if (raw.pin !== undefined && raw.pin !== null) {
    pin = point(raw.pin);
    if (pin === null || !llano.contains(pin)) {
      err("pin", "The pin is outside the area this register covers (the proposed " +
        "Llano Uplift AVA). Move it onto your vineyard.");
      pin = null;
    }
  }
  const hasPin = raw.pin !== undefined && raw.pin !== null;
  if (change && !rawBlocks.length) {
    err("where", "A change needs the vineyard's blocks drawn, not a pin: keep one block or more.");
  } else if (!rawBlocks.length && !hasPin) err("where", "Draw your blocks, or drop a pin on the vineyard.");

  // 3. about the vineyard
  const name = clean(v.name);
  if (!name) err("name", "Type the vineyard's name.");
  else if (Array.from(name).length > LIMITS.name) err("name", `Shorten the name to ${LIMITS.name} letters or fewer.`);
  else {
    const problem = publicTextProblem(name);
    if (problem) err("name", NAME_PROBLEMS[problem]);
  }
  const county = clean(v.county);
  if (!COUNTIES.includes(county)) err("county", "Pick the county.");
  const planted = v.planted;
  if (planted !== "planted" && planted !== "planned") err("planted", "Choose planted or planned.");
  let acres = null;
  if (v.acres !== undefined && v.acres !== null && v.acres !== "") {
    acres = number(v.acres);
    if (acres === null || !(acres > 0 && acres <= LIMITS.acresMax)) {
      err("acres", "Type the acres as a number, like 12 or 4.5.");
      acres = null;
    } else acres = round(acres, 2);
  }
  if (!rawBlocks.length && hasPin && acres === null && !errors.some((e) => e[0] === "acres")) {
    err("acres", "Type about how many acres are planted, so the petitioners can draw the vineyard.");
  }
  let plantYear = v.year ?? null;
  if (plantYear !== null) {
    if (!Number.isInteger(plantYear) || plantYear < LIMITS.yearMin || plantYear > year + LIMITS.yearAhead) {
      err("year", "Pick a year from the list.");
      plantYear = null;
    }
  }
  const varieties = [];
  const rawV = v.varieties ?? [];
  if (!Array.isArray(rawV)) throw new Invalid("varieties");
  for (const item of rawV.slice(0, LIMITS.varieties + 1)) {
    const text = clean(item, LIMITS.variety + 1);
    if (!text || varieties.includes(text)) continue;
    if (!VARIETIES.includes(text) && (Array.from(text).length > LIMITS.variety || publicTextProblem(text))) {
      err("varieties", `Check the other varieties: only names of grapes, each under ${LIMITS.variety} letters, with no phone numbers or web addresses.`);
      continue;
    }
    varieties.push(text);
  }
  if (varieties.length > LIMITS.varieties) {
    err("varieties", `Pick up to ${LIMITS.varieties} varieties.`);
    varieties.length = LIMITS.varieties;
  }

  // 3, a change: which vineyard it changes, and the note on what (public)
  let changes = null;
  let note = "";
  if (change) {
    const id = typeof raw.changes === "string" ? raw.changes : "";
    if (VINEYARD_ID.test(id) && Object.prototype.hasOwnProperty.call(known, id)) changes = id;
    else err("changes", "This vineyard can't be changed from this page just now. Email the petitioners instead.");
    note = clean(raw.note);
    if (!note) err("note", "Say in a few words what changed.");
    else if (Array.from(note).length > LIMITS.note) err("note", `Shorten the note to ${LIMITS.note} letters or fewer.`);
    else {
      const problem = publicTextProblem(note);
      if (problem) err("note", NOTE_PROBLEMS[problem]);
    }
  }

  // 4. how to reach them (private)
  const who = clean(c.name);
  const email = clean(c.email);
  const phoneRaw = clean(c.phone);
  if (!who) err("contact-name", "Type your name, so we know who to reply to.");
  else if (Array.from(who).length > LIMITS.contactName || !PERSON_TEXT.test(who)) {
    err("contact-name", "Type just your name, in letters.");
  }
  if (email && (Array.from(email).length > LIMITS.email || !EMAIL.test(email))) {
    err("contact-email", "Check the email address. It looks like name@example.com.");
  }
  let phone = null;
  if (phoneRaw) {
    phone = phoneFormat(phoneRaw);
    if (phone === null || phoneRaw.length > LIMITS.phone) {
      err("contact-phone", "Check the phone number: 10 digits, like 325 555 0100.");
    }
  }
  if (!email && !phoneRaw) {
    err("contact-email", "Give an email address or a phone number, so we can reach you.");
  }

  // 5. the two boxes, and the trap
  if (agree.permission !== true) err("agree-permission", "Tick this box to send.");
  if (agree.public !== true) err("agree-public", "Tick this box to send.");
  if (raw.website !== undefined && raw.website !== null && raw.website !== "") throw new Invalid("trap");

  const submission = {
    form: FORM,
    version: change ? CHANGE_VERSION : VERSION,
    id: raw.id,
    ...(change ? { changes, note: Array.from(note).slice(0, LIMITS.note).join("") } : {}),
    vineyard: {
      name: Array.from(name).slice(0, LIMITS.name).join(""),
      county: COUNTIES.includes(county) ? county : "",
      planted: planted === "planted" || planted === "planned" ? planted : "",
      acres,
      year: plantYear,
      varieties,
    },
    blocks,
    pin,
    contact: { name: who, email, phone: phone || "" },
  };
  return { submission, errors, facts };
}

// --- the issue (the function writes it; the contact is never in it) ---------

export function code(text) {
  // A backslash, a backtick and a pipe (which the rules already refuse in
  // public text) each become a lookalike: nothing is escaped, so nothing
  // can end the code span or the table's cell, or escape anything.
  const t = clean(text).replace(/[\\`|]/g, (c) => ({ "\\": "∖", "`": "ˋ", "|": "｜" })[c]);
  return t ? `\`${t}\`` : "_not given_";
}

// Compact JSON that cannot end a Markdown code fence or hold HTML.
export const safeJson = (value) => JSON.stringify(value)
  .replace(/&/g, "\\u0026").replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/`/g, "\\u0060");

// A neutral title: nothing a stranger typed, only the county from the list,
// or, for a change, the listed vineyard's name as the site lists it.
export const issueTitle = (sub, listed = null) => (listed
  ? `Vineyard change: ${clean(listed.name)}`
  : COUNTIES.slice(0, -1).includes(sub.vineyard.county)
    ? `Vineyard submission, ${sub.vineyard.county} County`
    : "Vineyard submission");

const PLANTED = { planted: "Planted", planned: "Planned" };
const blocksText = (n, drawn) => `${n} block${s(n)}${drawn ? " drawn" : ""}`;

// A change's issue: what is listed now beside what the sender suggests, and
// both outlines on the map (the listed ones grey, the suggested ones gold).
// listed: the vineyard's entry in assets/vineyards/known.json.
function changeBody(sub, sent, listed) {
  const v = sub.vineyard;
  const old = {
    name: listed.name,
    planted: listed.category === "under-development" ? "Planned" : "Planted",
    year: listed.year === null || listed.year === undefined ? "" : String(listed.year),
    varieties: (listed.varieties || []).join(", "),
    where: blocksText(listed.blocks.length, false),
  };
  const notListed = "_not listed_";
  const rows = [
    ["Vineyard", code(old.name), code(v.name)],
    ["County", notListed, code(v.county)],
    ["Planted or planned", code(old.planted), code(PLANTED[v.planted] || "")],
    ["Acres planted (as given)", notListed, code(v.acres === null ? "" : String(v.acres))],
    ["Year first planted", code(old.year), code(v.year === null ? "" : String(v.year))],
    ["Varieties", code(old.varieties), code(v.varieties.join(", "))],
    ["Where", code(old.where), code(blocksText(sub.blocks.length, true))],
  ];
  const look = (listing, colour) => ({ listing, stroke: colour, fill: colour });
  const features = [
    ...listed.blocks.map((r, k) => ({
      type: "Feature",
      properties: { block: k + 1, ...look("listed now", "#6e7781") },
      geometry: { type: "Polygon", coordinates: [[...r, r[0]]] },
    })),
    ...sub.blocks.map((r, k) => ({
      type: "Feature",
      properties: { block: k + 1, ...look("suggested", "#bf8700") },
      geometry: { type: "Polygon", coordinates: [[...r, r[0]]] },
    })),
  ];
  const pub = {
    form: sub.form, version: sub.version, changes: sub.changes, note: sub.note,
    vineyard: sub.vineyard, blocks: sub.blocks, pin: sub.pin, sent,
  };
  return [
    MARK,
    "A change to a vineyard listed on hickorysandsdistrictava.org, sent through its form, as the sender " +
      "typed it. Nothing on the site changes until the petitioners have checked it. " +
      "The sender's contact details are kept privately, not here.",
    "",
    `| | Listed now (\`${sub.changes}\`) | Suggested |`,
    "|---|---|---|",
    ...rows.map(([k, a, b]) => `| ${k} | ${a} | ${b} |`),
    `| What changed (the sender's note) | | ${code(sub.note)} |`,
    `| Sent | | ${code(`${sent.slice(0, 16).replace("T", " ")} UTC`)} |`,
    "",
    "The map: the blocks listed now in grey, the suggested blocks in gold.",
    "",
    "```geojson",
    safeJson({ type: "FeatureCollection", features }),
    "```",
    "",
    "<details><summary>The submission's data, read by the check</summary>",
    "",
    "```json",
    safeJson(pub),
    "```",
    "",
    "</details>",
  ].join("\n") + "\n";
}

export function issueBody(sub, sent, listed = null) {
  if (sub.version === CHANGE_VERSION && listed) return changeBody(sub, sent, listed);
  const v = sub.vineyard;
  const n = sub.blocks.length;
  const where = n ? `${n} block${s(n)} drawn` : "a pin (no outline drawn)";
  const rows = [
    ["Vineyard", code(v.name)],
    ["County", code(v.county)],
    ["Planted or planned", code({ planted: "Planted", planned: "Planned" }[v.planted] || "")],
    ["Acres planted (as given)", code(v.acres === null ? "" : String(v.acres))],
    ["Year first planted", code(v.year === null ? "" : String(v.year))],
    ["Varieties", code(v.varieties.join(", "))],
    ["Where", code(where)],
    ["Sent", code(`${sent.slice(0, 16).replace("T", " ")} UTC`)],
  ];
  const features = sub.blocks.map((r, k) => ({
    type: "Feature",
    properties: { block: k + 1 },
    geometry: { type: "Polygon", coordinates: [[...r, r[0]]] },
  }));
  if (sub.pin) {
    features.push({ type: "Feature", properties: { pin: true }, geometry: { type: "Point", coordinates: sub.pin } });
  }
  const pub = {
    form: sub.form, version: sub.version,
    ...(sub.version === CHANGE_VERSION ? { changes: sub.changes, note: sub.note } : {}),
    vineyard: sub.vineyard, blocks: sub.blocks, pin: sub.pin, sent,
  };
  return [
    MARK,
    "A vineyard sent through the form on hickorysandsdistrictava.org, as the sender typed it. " +
      "Nothing is shown on the site until the petitioners have checked it. " +
      "The sender's contact details are kept privately, not here.",
    "",
    "| | |",
    "|---|---|",
    ...rows.map(([k, val]) => `| ${k} | ${val} |`),
    "",
    "```geojson",
    safeJson({ type: "FeatureCollection", features }),
    "```",
    "",
    "<details><summary>The submission's data, read by the check</summary>",
    "",
    "```json",
    safeJson(pub),
    "```",
    "",
    "</details>",
  ].join("\n") + "\n";
}
