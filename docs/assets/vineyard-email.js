// The email a grower can send the petitioners from vineyards.html when the form
// could not send: the details as "Field: value" lines, and the mailto: URL that
// opens them in the grower's own email app. Only the failure screen offers it.
// No page code here (vineyard-wizard.js wires it in), so the tests run it in
// node (tests/test_vineyard_form.py).

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

// A point as latitude, longitude (what map apps take), 5 decimal places
// (about a metre).
const where = ([lon, lat]) => `${lat.toFixed(5)}, ${lon.toFixed(5)}`;

// The email from the form's submission (vineyard-wizard.js's payload()): the
// subject names the vineyard; the body is "Field: value" lines, every one
// always there (blank when not given) and in the same order. Each block is
// its corners, latitude and longitude, one corner a line. For a change to a
// listed vineyard (listed: { id, name }), the subject and the first lines name
// the vineyard being changed, and the note on what has changed follows.
export const CHANGE_SUBJECT = "Vineyard change";
export function message(p, listed = null) {
  const v = p.vineyard || {};
  const contact = p.contact || {};
  const blocks = (p.blocks || []).flatMap((ring, i) => [
    `Block ${i + 1}:`,
    ...ring.map(where),
  ]);
  const change = listed
    ? [
      `Changes the listed vineyard: ${oneLine(listed.name)} (${oneLine(listed.id)})`,
      `What has changed: ${oneLine(p.note)}`,
      "",
    ]
    : [];
  const body = [
    ...change,
    `Vineyard: ${oneLine(v.name)}`,
    `County: ${oneLine(v.county)}`,
    `Planted or planned: ${oneLine(v.planted)}`,
    `Acres planted: ${v.acres ?? ""}`,
    `Year first planted: ${v.year ?? ""}`,
    `Varieties: ${(v.varieties || []).map(oneLine).join(", ")}`,
    "",
    `Pin: ${p.pin ? where(p.pin) : ""}`,
    ...blocks,
    "",
    "Contact (for the petitioners only, never published)",
    `Name: ${oneLine(contact.name)}`,
    `Phone: ${oneLine(contact.phone)}`,
    `Email: ${oneLine(contact.email)}`,
  ].map(wellFormed).join("\r\n");
  const subject = listed
    ? cut(oneLine(`${CHANGE_SUBJECT}: ${oneLine(listed.name)}`), SUBJECT_MAX)
    : cut(oneLine(`${SUBJECT}: ${oneLine(v.name) || "(no name given)"}`), SUBJECT_MAX);
  return { subject, body };
}

// The mailto: URL. encodeURIComponent leaves no raw "&", "?", "#" or line
// break, so nothing a grower types can add a header (a cc or a bcc).
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
  return { url: mailto(SUBJECT, COPIED_BODY), subject: SUBJECT, long: true };
}
