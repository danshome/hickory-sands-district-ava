// The growers' logo vote (logo-vote.html).
//
// Talks to vote-api (src/vote/functions/vote-api/): state as JSON, POST
// register / vote / unvote / my_votes / upload. What differs from the Shopify
// page it replaces:
// - it reads state with fetch (JSON), not a <script> tag (JSONP), so the
//   function's answer can never run as code on this site;
// - it reads each POST's answer ("ok", "slow down", ...) and says so plainly;
// - votes that fail to send wait on this phone and go when the signal is back;
// - no person's name is asked for or shown, and all text goes in as text.
import * as config from "./vote-config.js?v=012d667";

const ENDPOINT = config.endpoint;
const IMG_PREFIX = ENDPOINT + "/img/";
const LIVE = config.live === true;
const CLOSED = config.closed === true;
const CHECK_ON = Boolean(config.turnstileSiteKey);

const $ = (id) => document.getElementById(id);

// --- this phone's storage (it can be missing: private windows) -------------
function load(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    return v == null ? fallback : JSON.parse(v);
  } catch (e) {
    return fallback;
  }
}
function save(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    /* nothing kept: the vote still counts for this visit */
  }
}
// The voter id is issued by vote-api (register, after the person check when
// it is on), and signed by it. Kept as plain text. Anything else stored here is ignored:
// the function would answer "bad" to it.
const SIGNED = /^v2-[0-9a-f]{24}-[0-9a-f]{32}$/;
function saveVoter(v) {
  try {
    if (v) localStorage.setItem("hsd_voter", v);
    else localStorage.removeItem("hsd_voter");
  } catch (e) {
    /* nothing kept */
  }
}
let voter = null;
try {
  voter = localStorage.getItem("hsd_voter");
} catch (e) {
  voter = null;
}
if (typeof voter !== "string" || !SIGNED.test(voter)) voter = null;
let myVotes = load("hsd_my_votes", {});
if (!myVotes || typeof myVotes !== "object") myVotes = {};
let outbox = load("hsd_outbox", []);
if (!Array.isArray(outbox)) outbox = [];
// Only well-formed votes from this page's own outbox are ever sent again.
outbox = outbox
  .filter((f) => f && (f.action === "vote" || f.action === "unvote") && okIdEarly(f.id))
  .map((f) => (f.action === "vote"
    ? { action: "vote", id: f.id, dir: Number(f.dir) < 0 ? "-1" : "1" }
    : { action: "unvote", id: f.id }));
function okIdEarly(id) {
  return /^[A-Za-z0-9_-]{1,90}$/.test(String(id));
}

// --- data --------------------------------------------------------------------
let builtIn = [];
let subs = [];
let up = {};
let down = {};
let retired = new Set();
let reached = false;
let queue = [];
const history = [];
let busy = false;
let chosenId = "";
// The rule the function applies (its state's rule), shown on the page.
let rule = null;

const okId = (id) => /^[A-Za-z0-9_-]{1,90}$/.test(String(id));
const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 0;
};
const likes = (id) => num(up[id]);
const passes = (id) => num(down[id]);
const total = (id) => likes(id) + passes(id);
const share = (id) => (total(id) ? likes(id) / total(id) : 1);
const plural = (n, one, many) => n + " " + (n === 1 ? one : many);

function allItems() {
  return builtIn.concat(subs);
}
function byId(id) {
  return allItems().find((it) => it.id === id);
}

// Least-voted first, with a little chance, and designs near the line get
// another look (as on the Shopify page).
function buildQueue() {
  const items = allItems().filter((it) => !retired.has(it.id) && !myVotes[it.id]);
  for (const it of items) {
    let w = total(it.id) + Math.random() * 6;
    const r = share(it.id);
    const line = rule ? rule.retireRatio : 0.35;
    if (total(it.id) >= 10 && r >= line && r < line + 0.1) w += 12;
    it._w = w;
  }
  return items.sort((a, b) => a._w - b._w);
}

// --- talking to vote-api -----------------------------------------------------
async function post(fields) {
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(fields).toString(),
  });
  const text = (await res.text()).trim().slice(0, 40);
  if (!res.ok) throw new Error("status " + res.status);
  return text;
}

// Sends what waits in the outbox, oldest first. Each entry is removed by
// identity once sent (send() may have replaced the outbox meanwhile, e.g. an
// undo while its vote was still going). No answer: it waits for the signal.
// A refusal (4xx) drops that entry; a server fault (5xx) waits like no signal.
class Refused extends Error {}
class BadVoter extends Error {}
async function postVote(fields) {
  let res;
  try {
    res = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ ...fields, voter }).toString(),
    });
  } catch (e) {
    throw new Error("offline");
  }
  const text = (await res.text()).trim();
  if (res.status >= 400 && res.status < 500) throw new Refused(String(res.status));
  if (!res.ok) throw new Error("server");
  if (text === "bad") throw new BadVoter("bad");
  if (text === "limit") throw new Refused("limit");
}
let flushing = false;
let badVoterOnce = false;
async function flush() {
  if (flushing || !outbox.length) return;
  if (!voter) {
    needCheck();
    $("status").textContent = CHECK_ON
      ? "Your votes are sent once the check below is done."
      : "Your votes wait on this phone until the vote answers.";
    return;
  }
  flushing = true;
  let refused = 0;
  const limited = [];
  try {
    while (outbox.length) {
      const entry = outbox[0];
      try {
        await postVote(entry);
      } catch (e) {
        if (e instanceof BadVoter && !badVoterOnce) {
          // The id isn't accepted (e.g. the function's secret changed): the
          // check once more, then these votes go with the new id.
          badVoterOnce = true;
          voter = null;
          saveVoter(null);
          throw e;
        }
        if (!(e instanceof Refused) && !(e instanceof BadVoter)) throw e;
        if (e.message === "limit") limited.push(entry.id);
        else refused++;
      }
      outbox = outbox.filter((f) => f !== entry);
      save("hsd_outbox", outbox);
    }
    for (const id of limited) unmark(id);
    if (limited.length) {
      renderDeck();
      renderLists();
    }
    const most = rule ? num(rule.votersPerNetwork) : 0;
    $("status").textContent = limited.length
      ? (most ? most + " people" : "Many people") +
        " on this same internet connection have already voted on " +
        limited.map((id) => (byId(id) || { name: "that design" }).name).join(", ") +
        " today. That vote wasn't counted. Please try it again tomorrow."
      : refused
        ? "The vote didn't accept " + plural(refused, "vote", "votes") + ". Please try again later, or email district@hickorysandsdistrictava.org."
        : "";
  } catch (e) {
    $("status").textContent = e instanceof BadVoter
      ? "Your votes wait on this phone and are sent in a moment."
      : e.message === "server"
      ? "The vote isn't answering properly just now. Your votes wait on this phone and are sent later."
      : "No signal just now. Your votes wait on this phone and are sent when you're back online.";
  } finally {
    flushing = false;
  }
  if (!voter) needCheck();
}
// Takes a vote off this phone's list when the function didn't count it.
function unmark(id) {
  const dir = myVotes[id];
  if (!dir) return;
  delete myVotes[id];
  save("hsd_my_votes", myVotes);
  if (dir > 0) up[id] = Math.max(0, likes(id) - 1);
  else down[id] = Math.max(0, passes(id) - 1);
}
function send(fields) {
  // A newer vote on the same design replaces any unsent one.
  outbox = outbox.filter((f) => f.id !== fields.id);
  outbox.push(fields);
  save("hsd_outbox", outbox);
  flush();
}

async function loadState() {
  try {
    const res = await fetch(ENDPOINT + "?v=" + Date.now(), { cache: "no-store" });
    if (!res.ok) throw new Error("status " + res.status);
    const data = await res.json();
    up = data && typeof data.up === "object" ? data.up : {};
    const r = data && data.rule;
    rule = r && typeof r === "object" &&
      Number.isFinite(Number(r.minVotes)) && Number.isFinite(Number(r.retireRatio))
      ? { minVotes: num(r.minVotes), retireRatio: Number(r.retireRatio),
          votersPerNetwork: num(r.votersPerNetwork) }
      : null;
    down = data && typeof data.down === "object" ? data.down : {};
    retired = new Set((Array.isArray(data.retired) ? data.retired : []).filter(okId));
    // An image is taken only as /img/<uuid> of this endpoint, and its address
    // is rebuilt from the endpoint, so a host the function names differently
    // (url.host behind Supabase's gateway) can't drop every design.
    subs = [];
    for (const s of Array.isArray(data.submissions) ? data.submissions : []) {
      const m = s && typeof s.img === "string" &&
        /\/vote-api\/img\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/.exec(s.img);
      if (!m || !okId(s.id) || s.id !== "sub-" + m[1]) continue;
      subs.push({
        id: s.id,
        name: String(s.title || "").slice(0, 60).trim() || "Untitled",
        // Never a person's name: vote-api keeps none.
        sub: "Sent in by a grower",
        img: IMG_PREFIX + m[1],
      });
    }
    reached = true;
  } catch (e) {
    reached = false;
    $("status").textContent =
      "Couldn't reach the vote just now. You can still vote: your votes wait on this phone.";
  }
}

async function loadBuiltIn() {
  try {
    const res = await fetch("assets/logo-vote/designs.json");
    const list = await res.json();
    builtIn = list
      .filter((e) => okId(e.id) && /^assets\/logo-vote\/designs\/[a-z0-9-]+\.(png|jpg|webp)$/.test(e.img))
      .map((e) => ({ id: e.id, name: String(e.name), sub: String(e.sub || ""), img: e.img }));
  } catch (e) {
    builtIn = [];
  }
}

// --- the card ----------------------------------------------------------------
const card = $("card");
function renderDeck() {
  const seen = Object.keys(myVotes).length;
  const it = queue[0];
  $("undo").hidden = !history.length;
  if (!it) {
    card.hidden = true;
    $("buttons").hidden = true;
    $("swipe-hint").hidden = true;
    $("empty").hidden = false;
    $("empty").textContent = seen
      ? "You've seen every design. Thank you for voting. New designs are added as they come in, so look again another day."
      : "There are no designs to vote on yet.";
    $("progress").textContent = seen ? "You've voted on " + plural(seen, "design", "designs") + "." : "";
    return;
  }
  $("card-img").src = it.img;
  $("card-img").alt = "Design: " + it.name;
  $("card-name").textContent = it.name;
  $("card-sub").textContent = it.sub;
  card.hidden = false;
  $("buttons").hidden = false;
  $("swipe-hint").hidden = false;
  $("empty").hidden = true;
  resetCard(true);
  fitCard();
  const left = queue.length;
  $("progress").textContent =
    left + " to go" + (seen ? " · " + seen + " voted" : "");
}

// On a phone, shrinks the picture so the Like and Pass buttons are on the
// first screen, whatever the length of the design's name and line.
function fitCard() {
  const img = $("card-img");
  img.style.maxHeight = "";
  if (innerWidth >= 900) return;
  const bottom = $("buttons").getBoundingClientRect().bottom + scrollY + 8;
  const over = bottom - innerHeight;
  if (over > 0) {
    const h = img.getBoundingClientRect().height;
    img.style.maxHeight = Math.max(120, Math.floor(h - over)) + "px";
  }
}
let fitTimer = 0;
addEventListener("resize", () => {
  clearTimeout(fitTimer);
  fitTimer = setTimeout(fitCard, 150);
});

function resetCard(instant) {
  card.style.transition = instant ? "none" : "transform .18s ease-out";
  card.style.transform = "";
  $("stamp-like").style.opacity = 0;
  $("stamp-pass").style.opacity = 0;
}

const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
function vote(dir) {
  if (busy || !queue.length || CLOSED) return;
  busy = true;
  const it = queue[0];
  myVotes[it.id] = dir;
  save("hsd_my_votes", myVotes);
  if (dir > 0) up[it.id] = likes(it.id) + 1;
  else down[it.id] = passes(it.id) + 1;
  history.push({ item: it, dir });
  send({ action: "vote", id: it.id, dir: String(dir) });
  const said = dir > 0 ? "Liked." : "Passed.";
  const finish = () => {
    queue.shift();
    busy = false;
    renderDeck();
    renderLists();
    const next = queue[0];
    $("progress").textContent = said + " " + $("progress").textContent;
    fitCard();
    if (next) $("card-name").focus({ preventScroll: true });
    else $("empty").focus({ preventScroll: true });
  };
  if (reduceMotion) return finish();
  card.style.transition = "transform .24s ease-in";
  card.style.transform = "translateX(" + (dir > 0 ? 120 : -120) + "%) rotate(" + (dir > 0 ? 8 : -8) + "deg)";
  setTimeout(finish, 250);
}

function takeBack(id) {
  const dir = myVotes[id];
  if (!dir) return;
  delete myVotes[id];
  save("hsd_my_votes", myVotes);
  if (dir > 0) up[id] = Math.max(0, likes(id) - 1);
  else down[id] = Math.max(0, passes(id) - 1);
  send({ action: "unvote", id });
  const it = byId(id);
  if (it && !retired.has(id)) queue.unshift(it);
}

function undo() {
  if (busy || !history.length) return;
  const h = history.pop();
  takeBack(h.item.id);
  renderDeck();
  renderLists();
  $("progress").textContent = "Vote taken back. " + $("progress").textContent;
  fitCard();
  $("card-name").focus({ preventScroll: true });
}

// Swiping is a shortcut only; the buttons do the same.
let startX = null;
let dx = 0;
card.addEventListener("pointerdown", (ev) => {
  if (busy || CLOSED || ev.button > 0) return;
  startX = ev.clientX;
  dx = 0;
  card.setPointerCapture(ev.pointerId);
  card.style.transition = "none";
});
card.addEventListener("pointermove", (ev) => {
  if (startX == null) return;
  dx = ev.clientX - startX;
  card.style.transform = "translateX(" + dx + "px) rotate(" + dx / 20 + "deg)";
  $("stamp-like").style.opacity = dx > 0 ? Math.min(1, dx / 90) : 0;
  $("stamp-pass").style.opacity = dx < 0 ? Math.min(1, -dx / 90) : 0;
});
function dragEnd() {
  if (startX == null) return;
  const d = dx;
  startX = null;
  dx = 0;
  if (d > 100) vote(1);
  else if (d < -100) vote(-1);
  else resetCard(false);
}
card.addEventListener("pointerup", dragEnd);
card.addEventListener("pointercancel", dragEnd);
$("like").addEventListener("click", () => vote(1));
$("pass").addEventListener("click", () => vote(-1));
$("undo").addEventListener("click", undo);

// --- lists -------------------------------------------------------------------
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function thumb(it) {
  const box = el("div", "lv-thumb");
  const img = el("img");
  img.src = it.img;
  img.alt = "";
  img.loading = "lazy";
  box.append(img);
  return box;
}
function tally(id) {
  return plural(likes(id), "like", "likes") + " · " + plural(passes(id), "pass", "passes");
}

function topRated() {
  return allItems()
    .filter((it) => !retired.has(it.id) && total(it.id) >= 3)
    .sort((a, b) => share(b.id) - share(a.id) || total(b.id) - total(a.id));
}

function renderLists() {
  // Top rated
  const top = topRated().filter((it) => it.id !== chosenId).slice(0, 5);
  const ol = $("top");
  ol.replaceChildren();
  for (const it of top) {
    const li = el("li", "lv-row");
    const text = el("div", "lv-row-text");
    text.append(el("span", "lv-row-name", it.name), el("span", "lv-row-tally", tally(it.id)));
    li.append(thumb(it), text);
    ol.append(li);
  }
  $("top-wrap").hidden = !top.length;

  // Your votes
  const mine = Object.keys(myVotes).map(byId).filter(Boolean);
  const ul = $("mine");
  ul.replaceChildren();
  for (const it of mine) {
    const li = el("li", "lv-row");
    const text = el("div", "lv-row-text");
    text.append(el("span", "lv-row-name", it.name),
      el("span", "lv-row-tally", myVotes[it.id] > 0 ? "You liked it" : "You passed"));
    const b = el("button", "w-link lv-take", "Take back");
    b.type = "button";
    b.setAttribute("aria-label", "Take back your vote on " + it.name);
    b.addEventListener("click", () => {
      takeBack(it.id);
      renderDeck();
      renderLists();
      $("status").textContent = "Vote on " + it.name + " taken back. It's back in the vote.";
      $("mine-title").focus();
    });
    li.append(thumb(it), text);
    if (!CLOSED && !retired.has(it.id)) li.append(b);
    ul.append(li);
  }
  $("mine-count").textContent = mine.length ? "(" + mine.length + ")" : "";
  $("mine-wrap").hidden = !mine.length;
  $("mine-title").tabIndex = -1;

  // Retired
  const gone = allItems().filter((it) => retired.has(it.id));
  const grid = $("retired");
  grid.replaceChildren();
  for (const it of gone) {
    const li = el("li", "lv-tile");
    li.append(thumb(it), el("span", "lv-row-name", it.name), el("span", "lv-row-tally", tally(it.id)));
    grid.append(li);
  }
  $("retired-count").textContent = gone.length ? "(" + gone.length + ")" : "";
  $("retired-wrap").hidden = !gone.length;
}

function renderClosed() {
  // The petitioners name the chosen design; the page never crowns the leader
  // by itself.
  $("closed").hidden = false;
  $("vote").hidden = true;
  $("send").hidden = true;
  document.querySelector(".lv-heading h1").textContent = "The district's mark.";
  $("lead").textContent = "The growers' vote is closed. Thank you to everyone who voted and sent in a design.";
  $("closed-note").hidden = true;
  const id = config.chosen;
  const it = id && byId(id);
  if (it) {
    chosenId = it.id;
    renderLists();
  }
  if (!it) {
    $("closed-title").textContent = "The vote is closed";
    $("winner").hidden = true;
    $("closed-note").hidden = false;
    $("closed-note").textContent = "The petitioners will show the chosen mark here.";
    return;
  }
  $("winner-img").src = it.img;
  $("winner-img").alt = "The chosen design: " + it.name;
  $("winner-name").textContent = it.name;
  $("winner-tally").textContent = reached ? tally(it.id) : "";
  $("top-title").textContent = "How the others did";
}

// --- sending a design ----------------------------------------------------------
const MAX_SIDE = 1200;
const MAX_B64 = 4500000;
let chosenFile = null;
let previewUrl = null;

function fileError(text) {
  $("err-file").textContent = text;
  $("err-file").hidden = !text;
}

$("file").addEventListener("change", () => {
  const f = $("file").files[0];
  fileError("");
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  chosenFile = null;
  $("preview").hidden = true;
  $("pick-text").textContent = "Choose a photo";
  if (!f) return;
  if (f.type && !f.type.startsWith("image/")) {
    fileError("That file isn't a photo. Choose a photo or a picture.");
    return;
  }
  previewUrl = URL.createObjectURL(f);
  const probe = new Image();
  probe.onload = () => {
    chosenFile = f;
    // The loaded photo becomes the preview itself (a blob: address, made by
    // the browser from the chosen file; never text from the page).
    probe.id = "preview-img";
    probe.alt = "The photo you chose";
    $("preview-img").replaceWith(probe);
    $("preview").hidden = false;
    $("pick-text").textContent = "Choose a different photo";
  };
  probe.onerror = () => {
    fileError("This phone's photo can't be opened here. Take a screenshot of the photo and choose the screenshot instead.");
    $("pick-label").focus();
  };
  probe.src = previewUrl;
});

function toJpeg(file) {
  // Redraws the photo as a JPEG no wider than MAX_SIDE. This also drops the
  // photo's hidden details (camera, time, GPS position).
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const scale = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
      const cv = document.createElement("canvas");
      cv.width = Math.max(1, Math.round(img.naturalWidth * scale));
      cv.height = Math.max(1, Math.round(img.naturalHeight * scale));
      const ctx = cv.getContext("2d");
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, cv.width, cv.height);
      ctx.drawImage(img, 0, 0, cv.width, cv.height);
      URL.revokeObjectURL(url);
      resolve(cv.toDataURL("image/jpeg", 0.85).split(",")[1]);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("not an image"));
    };
    img.src = url;
  });
}

const ANSWERS = {
  ok: "Thank you. Your design is with the petitioners. It shows in the vote once they've checked it.",
  full: "The vote can't take any more designs. To send one anyway, email it to district@hickorysandsdistrictava.org.",
  "queue full": "Many designs are waiting to be checked. Please try again in a few days.",
  "slow down": "That's the most designs that can come from one place in a day. Please try again tomorrow.",
  "too big": "That photo is too large. Try a smaller one, or a screenshot of it.",
  "not an image": "That file didn't read as a photo. Try a JPEG or PNG.",
  "bad data": "That file didn't read as a photo. Try a JPEG or PNG.",
};

$("send-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const status = $("send-status");
  status.textContent = "";
  if (!chosenFile) {
    fileError("Choose a photo of your design first.");
    $("pick-label").focus();
    return;
  }
  const button = $("send-button");
  button.disabled = true;
  button.textContent = "Sending…";
  let answer = "";
  try {
    const data = await toJpeg(chosenFile);
    if (data.length > MAX_B64) {
      answer = "too big";
    } else {
      answer = await post({
        action: "upload",
        name: "",
        title: $("title").value.trim().slice(0, 60),
        filename: "submission.jpg",
        data,
      });
    }
  } catch (e) {
    answer = e.message === "not an image" ? "not an image" : "";
  }
  button.disabled = false;
  button.textContent = "Send it in";
  status.className = "lv-status" + (answer === "ok" ? " lv-good" : " lv-bad");
  status.textContent = ANSWERS[answer] ||
    "It didn't send. Check your signal and try again.";
  if (answer === "ok") {
    $("send-form").reset();
    $("file").dispatchEvent(new Event("change"));
  }
  status.focus();
});

// --- carry-over from the Shopify page ----------------------------------------
// The inline script in <head> took #voter=<id> off the address. Adopt it only
// if this phone has voted on nothing here yet; otherwise keep this phone's own
// id, so one person's votes are never split or doubled by accident.
// Guards against a planted id (someone sending a link with an id they chose,
// to read or change that person's votes): adopt only an id in the Shopify
// page's own shape, only when arriving from the Shopify page itself, and only
// once on this phone.
function adoptCarried() {
  const carried = window.hsdCarriedVoter;
  delete window.hsdCarriedVoter;
  if (!carried || carried === voter) return "";
  let from = "";
  try {
    from = document.referrer ? new URL(document.referrer).origin : "";
  } catch (e) {
    from = "";
  }
  if (!/^v[0-9a-z]{8,40}$/.test(carried) || !(config.carryFrom || []).includes(from) ||
      load("hsd_carried", false)) return "";
  save("hsd_carried", true);
  if (voter || Object.keys(myVotes).length || outbox.length) return "kept";
  // Exchanged for a signed id after the person check (register, carry=...).
  pendingCarry = carried;
  return "carry";
}
let pendingCarry = "";

// --- a voter id: once per phone, only when needed --------------------------------
// With the person check on (a Turnstile site key in vote-config.js), the
// Turnstile widget is loaded for a phone with no voter id yet, and its token
// goes to vote-api's register action, which answers with a signed id. With it
// off, register is called at once, with no token.
let checkShown = false;
let turnstileId = null;
function checkError(text) {
  $("check-error").textContent = text;
  $("check-error").hidden = !text;
  $("check-retry").hidden = !text;
}
function loadTurnstile() {
  return new Promise((resolve, reject) => {
    // (No element may have the id "turnstile": it would shadow window.turnstile.)
    if (window.turnstile && window.turnstile.render) return resolve(window.turnstile);
    const s = document.createElement("script");
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    s.async = true;
    s.onload = () => (window.turnstile && window.turnstile.render ? resolve(window.turnstile) : reject(new Error("no turnstile")));
    s.onerror = () => reject(new Error("no turnstile"));
    document.head.append(s);
  });
}
const NO_ID =
  "The vote isn't answering just now. Check your signal, then tap Try again. Your votes wait on this phone.";
const CHECK_FAILED =
  "The check didn't work. Check your signal, then tap Try again. If it keeps failing, email district@hickorysandsdistrictava.org.";
const TOO_MANY =
  "Many new voters have started from this internet connection today. Please try again tomorrow, or from another connection.";
async function needCheck() {
  if (voter || checkShown || CLOSED || !LIVE) return;
  checkShown = true;
  checkError("");
  if (!CHECK_ON) {
    await register("");
    return;
  }
  $("check").hidden = false;
  try {
    const ts = await loadTurnstile();
    if (turnstileId != null) ts.remove(turnstileId);
    turnstileId = ts.render("#person-check-widget", {
      sitekey: config.turnstileSiteKey,
      size: "flexible",
      callback: (token) => register(token),
      "error-callback": () => {
        checkError(CHECK_FAILED);
        return true;
      },
      "expired-callback": () => ts.reset(turnstileId),
    });
  } catch (e) {
    console.warn("person check:", e);
    checkError(CHECK_FAILED);
  }
}
$("check-retry").addEventListener("click", () => {
  checkShown = false;
  needCheck();
});
async function register(token) {
  let data = null;
  let text = "";
  try {
    const res = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ action: "register", token, carry: pendingCarry }).toString(),
    });
    text = (await res.text()).trim();
    data = JSON.parse(text);
  } catch (e) {
    data = null;
  }
  if (!data || typeof data.voter !== "string" || !SIGNED.test(data.voter)) {
    // Shown under the buttons, with Try again, whether or not the check is on.
    $("check").hidden = false;
    $("check-say").hidden = !CHECK_ON;
    checkError(text === "limit" ? TOO_MANY : CHECK_ON ? CHECK_FAILED : NO_ID);
    checkShown = false;
    return;
  }
  voter = data.voter;
  saveVoter(voter);
  pendingCarry = "";
  $("check").hidden = true;
  checkShown = false;
  const carried = num(data.carried);
  if (await loadMine()) {
    queue = buildQueue();
    renderDeck();
    renderLists();
  }
  await flush();
  if (carried) {
    $("status").textContent = "Welcome back. Your " + plural(carried, "vote", "votes") +
      " from the old vote page " + (carried === 1 ? "is" : "are") + " here, under Your votes.";
  } else if (CHECK_ON && !$("status").textContent.includes("internet connection")) {
    $("status").textContent = "Thank you. You can vote now.";
  }
}

// Rebuilds this phone's list of its own votes from vote-api (my_votes), with
// any votes still waiting to send laid over it. If the function answers
// anything else, the list on this phone is kept as it is.
async function loadMine() {
  if (!voter) return false;
  try {
    const res = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ action: "my_votes", voter }).toString(),
    });
    const data = JSON.parse(await res.text());
    if (!data || typeof data.votes !== "object" || !data.votes) return false;
    const mine = {};
    for (const [id, d] of Object.entries(data.votes)) {
      if (okId(id)) mine[id] = Number(d) < 0 ? -1 : 1;
    }
    for (const f of outbox) {
      if (f.action === "vote") mine[f.id] = Number(f.dir) < 0 ? -1 : 1;
      else if (f.action === "unvote") delete mine[f.id];
    }
    myVotes = mine;
    save("hsd_my_votes", myVotes);
    return true;
  } catch (e) {
    return false;
  }
}

// --- start -----------------------------------------------------------------------
function showRule() {
  const li = $("rule-line");
  if (!rule) {
    li.textContent = "The petitioners may retire a design that few people like. Retired designs leave the vote and are kept below for the record.";
    return;
  }
  for (const e of document.querySelectorAll("[data-rule=min]")) e.textContent = String(rule.minVotes);
  for (const e of document.querySelectorAll("[data-rule=pct]")) {
    e.textContent = Math.round(rule.retireRatio * 100) + " percent";
  }
}

async function start() {
  if (!LIVE) {
    // Before the switch-over: the page says the vote moves here soon, and
    // calls nothing. A carried id (from the inline script) is dropped.
    delete window.hsdCarriedVoter;
    return;
  }
  $("soon").hidden = true;
  for (const id of ["vote", "send", "how", "foot"]) $(id).hidden = false;
  const carry = adoptCarried();
  // A new phone gets its id when it first has something to send (or an id to
  // carry over), so a visit that only looks mints none; with the person check
  // on, the check is offered at once.
  if (!voter && !CLOSED && (CHECK_ON || pendingCarry || outbox.length)) needCheck();
  const [, , rebuilt] = await Promise.all([loadBuiltIn(), loadState(), loadMine()]);
  // A vote waiting to send is already in myVotes; drop any for retired designs.
  queue = buildQueue();
  showRule();
  if (CLOSED) renderClosed();
  renderDeck();
  renderLists();
  if (!reached) $("status").textContent ||= "Couldn't reach the vote just now.";
  void rebuilt;
  if (carry === "kept") {
    $("status").textContent = "You've already voted on this site from this phone, so your votes here are kept as they are.";
  }
  flush();
}
window.addEventListener("online", () => {
  if (LIVE) flush();
});
start();
