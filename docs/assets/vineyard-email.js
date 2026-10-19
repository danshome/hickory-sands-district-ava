// The email a vineyard's owner sends the district from vineyards.html: what the
// form's values mean, what needs fixing, and the message, as "Field: value"
// lines, with the mailto: URL that opens it in the visitor's own email app.
// No page here (vineyards.js wires it to the form), so the tests run it in node
// (tests/test_vineyards_form.py).

export const ADDRESS = "district@hickorysandsdistrictava.org";
// Some email apps cut a mailto: URL short near 2,000 characters (older Outlook,
// by report), so the URL never passes this. A longer message goes by the
// clipboard instead, and the email that opens asks for it to be pasted.
export const LONG_URL = 1900;
export const SUBJECT = "Vineyard submission";
// The subject's length, in characters (code points, never half an emoji).
export const SUBJECT_MAX = 140;
// The body of the email that opens when the details were copied instead.
export const COPIED_BODY =
  "The vineyard details were copied from the form: paste them here.";

// The text with each lone surrogate (half an emoji, cut short) replaced by
// U+FFFD, so encodeURIComponent never throws on it.
export function wellFormed(text) {
  let out = "";
  for (const character of String(text ?? "")) {
    const unit = character.charCodeAt(0);
    const lone = character.length === 1 && unit >= 0xd800 && unit <= 0xdfff;
    out += lone ? "�" : character;
  }
  return out;
}

// At most n characters, cut by code points, so never in half of one.
export function cut(text, n) {
  const characters = Array.from(wellFormed(text));
  return characters.length <= n ? characters.join("") : characters.slice(0, n).join("");
}

// One line: runs of white space, line breaks among them, become one space.
export const oneLine = (text) => wellFormed(text).replace(/\s+/g, " ").trim();

// Several lines, each line break the email's CRLF.
export const lines = (text) =>
  wellFormed(text).replace(/\r\n?/g, "\n").trim().split("\n")
    .map((line) => line.trim()).join("\r\n");

// Up to 6 decimal places (about 0.1 m), as typed when shorter.
export const decimal = (value, places = 6) => String(Number(value.toFixed(places)));

// A coordinate typed or pasted: "30.7647", "30.7647° N", "99.4107 W",
// "−99.4107" (a minus sign, as the page's own hint writes it). Null when it is
// not one.
export function coordinate(text) {
  const plain = oneLine(text).replace(/[°º]/g, "").replace(/[−–]/g, "-");
  const m = plain.match(/^(-?\d+(?:\.\d+)?)\s*([NSEW])?$/i);
  if (!m) return null;
  const value = Number(m[1]);
  return /[SW]/i.test(m[2] || "") ? -Math.abs(value) : value;
}

// A pair copied from a map app, "30.76468, -99.41073" or
// "30.764680° N, 99.410730° W": [latitude text, longitude text], or null.
export function pair(text) {
  const m = oneLine(text).match(
    /^([-−]?[\d.]+°?\s*[NS]?)\s*[,;\s]\s*([-−]?[\d.]+°?\s*[EW]?)$/i,
  );
  if (!m || coordinate(m[1]) === null || coordinate(m[2]) === null) return null;
  return [m[1].trim(), m[2].trim()];
}

// The form's values, as typed (strings, and true or false for the boxes), made
// ready for the checks and the email. source says where a point came from:
// "typed", or "from a pin on the map".
export function normalize(raw) {
  const lat = coordinate(raw.lat ?? "");
  let lon = coordinate(raw.lon ?? "");
  if (lon !== null && lon > 0) lon = -lon; // west of Greenwich, here
  let website = oneLine(raw.website ?? "");
  if (website && !/^https?:\/\//i.test(website)) website = `https://${website}`;
  return {
    name: oneLine(raw.name ?? ""),
    business: oneLine(raw.business ?? ""),
    status: oneLine(raw.status ?? ""),
    website,
    latText: oneLine(raw.lat ?? ""),
    lonText: oneLine(raw.lon ?? ""),
    lat,
    lon,
    source: raw.source === "pin" ? "from a pin on the map" : "typed",
    road: oneLine(raw.road ?? ""),
    directions: oneLine(raw.directions ?? ""),
    county: oneLine(raw.county ?? ""),
    acres: oneLine(raw.acres ?? "").replace(/,/g, ""),
    year: oneLine(raw.year ?? ""),
    varieties: oneLine(raw.varieties ?? ""),
    sells: Boolean(raw.sells),
    makes: Boolean(raw.makes),
    contact: oneLine(raw.contact ?? ""),
    email: oneLine(raw.email ?? ""),
    consent: Boolean(raw.consent),
    note: lines(raw.note ?? ""),
  };
}

// What needs fixing, as [field id, message] in the order of the form. year is
// this year (the latest year planted it accepts is five years on).
export function problems(d, year) {
  const found = [];
  if (!d.name) found.push(["v-name", "Enter the vineyard’s name."]);
  if (!d.status) found.push(["v-status", "Choose the vineyard’s status."]);
  if (d.website) {
    let ok = false;
    try {
      ok = new URL(d.website).hostname.includes(".");
    } catch {
      ok = false;
    }
    if (!ok) found.push(["v-website", "Enter a web address, such as example.com."]);
  }
  const hasLat = d.latText !== "";
  const hasLon = d.lonText !== "";
  if (!hasLat && !hasLon && !d.road) {
    found.push([
      "v-where",
      "Give a point in the vineyard (a pin, or latitude and longitude) or the nearest road.",
    ]);
  }
  if (hasLat && (d.lat === null || d.lat < 25 || d.lat > 37)) {
    found.push(["v-lat", "Latitude in Texas is a number between 25 and 37, such as 30.7647."]);
  }
  if (hasLon && (d.lon === null || d.lon > -93 || d.lon < -107)) {
    found.push(["v-lon", "Longitude in Texas is between −93 and −107, such as −99.4107."]);
  }
  if (hasLat !== hasLon) {
    found.push([hasLat ? "v-lon" : "v-lat", "Give both latitude and longitude, or neither."]);
  }
  if (!d.county) found.push(["v-county", "Choose the county, or Not sure."]);
  if (d.acres && !(/^\d+(\.\d+)?$/.test(d.acres) && Number(d.acres) <= 10000)) {
    found.push(["v-acres", "Enter the acres as a number, such as 12 or 4.5."]);
  }
  const planted = Number(d.year);
  if (d.year && !(/^\d{4}$/.test(d.year) && planted >= 1800 && planted <= year + 5)) {
    found.push(["v-year", `Enter a year from 1800 to ${year + 5}.`]);
  }
  if (!d.contact) found.push(["v-contact", "Enter your name, for the reply."]);
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(d.email)) {
    found.push(["v-email", "Enter an email address, such as name@example.com."]);
  }
  if (!d.consent) found.push(["v-consent", "Tick the box to give permission."]);
  return found;
}

// The email: the subject names the vineyard; the body is "Field: value" lines,
// every one always there (blank when not given) and in the same order, so each
// message reads, and parses, the same. consent is the permission's own words,
// as the page's label gives them; the note comes last, as it may run to
// several lines.
export function message(d, consent) {
  const point = d.lat !== null && d.lon !== null
    ? `${decimal(d.lat)}, ${decimal(d.lon)} (WGS 84, ${d.source})`
    : "";
  const body = [
    `Vineyard name: ${d.name}`,
    `Business name: ${d.business}`,
    `Status: ${d.status}`,
    `Website: ${d.website}`,
    "",
    `Point: ${point}`,
    `Nearest road: ${d.road}`,
    `How to find it: ${d.directions}`,
    `County: ${d.county}`,
    "",
    `Acres planted: ${d.acres}`,
    `Year first planted: ${d.year}`,
    `Varieties: ${d.varieties}`,
    `Sells grapes: ${d.sells ? "Yes" : "No"}`,
    `Makes wine: ${d.makes ? "Yes" : "No"}`,
    "",
    "Contact (for replies only, not to be published)",
    `Name: ${d.contact}`,
    `Email: ${d.email}`,
    "",
    `Consent: ${d.consent ? `Yes. ${oneLine(consent)}` : "No"}`,
    `Note: ${d.note}`,
  ].map(wellFormed).join("\r\n");
  const subject = cut(oneLine(`${SUBJECT}: ${d.name || "(no name given)"}`), SUBJECT_MAX);
  return { subject, body };
}

// The mailto: URL. encodeURIComponent leaves no raw "&", "?", "#" or line
// break, so nothing a visitor types can add a header (a cc or a bcc).
export const mailto = (subject, body) =>
  `mailto:${ADDRESS}?subject=${encodeURIComponent(wellFormed(subject))}` +
  `&body=${encodeURIComponent(wellFormed(body))}`;

// What the button opens: the whole message when its URL fits in LONG_URL;
// else the subject and COPIED_BODY, while the page copies the details (long is
// then true). The URL never passes LONG_URL.
export function plan(built) {
  const full = mailto(built.subject, built.body);
  if (full.length <= LONG_URL) return { url: full, subject: built.subject, long: false };
  for (const subject of [built.subject, SUBJECT]) {
    const url = mailto(subject, COPIED_BODY);
    if (url.length <= LONG_URL) return { url, subject, long: true };
  }
  return { url: `mailto:${ADDRESS}`, subject: SUBJECT, long: true };
}
