// Stand-ins for what the logo vote's Edge Function talks to: Supabase's
// tables (through its REST API, with hsd_vote_tally(), hsd_vote_cast(),
// hsd_vote_register() and hsd_vote_cull() as hsd_vote_migration.sql makes
// them; tests/test_vote_sql.py runs that SQL in PostgreSQL), its Storage
// bucket, and Cloudflare's Turnstile check. The function itself is the real
// one, the one-file bundle Dan deploys (src/vote/bundle_function.py).
//
//   node --experimental-strip-types tests/vote_standin.mjs cases BUNDLE
//       runs every case of tests/test_vote_function.py and prints what
//       happened, as JSON;
//   node --experimental-strip-types tests/vote_standin.mjs serve PORT BUNDLE
//       serves the function on 127.0.0.1:PORT for the browser test
//       (tests/live/test_logo_vote.py): a request from the local page is
//       passed on as if from the site; POST /standin resets the stand-ins
//       ({"reset": true, "turnstile": true or false}), adds votes
//       ({"votes": [...]}) and answers what they hold.
import http from "node:http";
import { pathToFileURL } from "node:url";

const SITE = "https://hickorysandsdistrictava.org";
const DB = "https://db.example.invalid";
const URL_BASE = `${DB}/functions/v1/vote-api`;
const DAY = 86400000;

const reply = (status, body, headers = {}) =>
  new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });

export function standIn({ turnstile = true } = {}) {
  const state = {
    votes: [], // {design_id, voter_token, dir, updated_at}
    subs: [], // hsd_submissions rows
    retired: [], // hsd_retired rows
    networks: [], // hsd_vote_networks
    registrations: [], // hsd_vote_registrations
    exchanged: new Set(),
    files: new Map(),
    turnstile: "pass",
    db: "ok",
    logs: [],
    now: new Date("2026-10-19T12:00:00.000Z"),
    seq: 0,
  };
  const env = {
    SUPABASE_URL: DB,
    SUPABASE_SERVICE_ROLE_KEY: "eyJ.service.role", // pragma: allowlist secret
    VOTE_ID_SECRET: "vote-id-secret-for-tests", // pragma: allowlist secret
    VOTE_IP_SALT: "vote-salt-for-tests", // pragma: allowlist secret
    OPERATOR_KEY: "operator-key-for-tests", // pragma: allowlist secret
  };
  if (turnstile) env.VOTE_TURNSTILE_SECRET = "turnstile-secret-for-tests"; // pragma: allowlist secret
  const iso = () => state.now.toISOString();
  const tick = (ms = 1000) => {
    state.now = new Date(state.now.getTime() + ms);
  };

  const tables = {
    hsd_votes: () => state.votes,
    hsd_submissions: () => state.subs,
    hsd_retired: () => state.retired,
  };
  function matches(row, f) {
    return Object.entries(f).every(([k, v]) => {
      if (v === "is.null") return row[k] === null || row[k] === undefined;
      if (v === "not.is.null") return row[k] !== null && row[k] !== undefined;
      const [op, ...rest] = v.split(".");
      const value = decodeURIComponent(rest.join("."));
      if (op === "eq") return String(row[k]) === value;
      if (op === "gte") return new Date(row[k]) >= new Date(value);
      throw new Error(`filter ${k}=${v}`);
    });
  }
  function query(path) {
    const [name, q] = path.split("?");
    const f = {};
    let select = null;
    let order = null;
    for (const part of (q || "").split("&").filter(Boolean)) {
      const i = part.indexOf("=");
      const k = part.slice(0, i);
      const v = part.slice(i + 1);
      if (k === "select") select = v.split(",");
      else if (k === "order") order = v;
      else f[k] = v;
    }
    return { name, f, select, order };
  }
  const pick = (r, select) => (select ? Object.fromEntries(select.map((k) => [k, r[k] ?? null])) : { ...r });

  // The SQL functions, as hsd_vote_migration.sql has them.
  function tally() {
    const t = new Map();
    for (const v of state.votes) {
      const e = t.get(v.design_id) || { design_id: v.design_id, up: 0, down: 0 };
      if (v.dir < 0) e.down++;
      else e.up++;
      t.set(v.design_id, e);
    }
    return [...t.values()];
  }
  function cast(a) {
    const dayAgo = state.now.getTime() - DAY;
    state.networks = state.networks.filter((n) => new Date(n.at).getTime() >= dayAgo);
    const has = state.votes.find((v) => v.design_id === a.p_design && v.voter_token === a.p_voter);
    const logged = state.networks.some(
      (n) => n.ip_hash === a.p_ip_hash && n.design_id === a.p_design && n.voter_token === a.p_voter,
    );
    if (!has && !logged) {
      if (state.networks.filter((n) => n.ip_hash === a.p_ip_hash && n.design_id === a.p_design).length >= a.p_limit) {
        return "limit";
      }
      if (String(a.p_ip_hash).length !== 64) throw new Error("check ip_hash");
      state.networks.push({ ip_hash: a.p_ip_hash, design_id: a.p_design, voter_token: a.p_voter, at: iso() });
    }
    const dir = a.p_dir < 0 ? -1 : 1;
    if (has) Object.assign(has, { dir, updated_at: iso() });
    else state.votes.push({ design_id: a.p_design, voter_token: a.p_voter, dir, updated_at: iso() });
    return "ok";
  }
  function register(a) {
    const dayAgo = state.now.getTime() - DAY;
    state.registrations = state.registrations.filter((r) => new Date(r.at).getTime() >= dayAgo);
    if (state.registrations.filter((r) => r.ip_hash === a.p_ip_hash).length >= a.p_limit) {
      return { verdict: "limit", carried: 0 };
    }
    state.registrations.push({ ip_hash: a.p_ip_hash, at: iso() });
    let carried = 0;
    const c = a.p_carry || "";
    if (/^v[0-9a-z]{8,40}$/.test(c) && !state.exchanged.has(c) && state.votes.some((v) => v.voter_token === c)) {
      state.exchanged.add(c);
      for (const v of state.votes) {
        if (v.voter_token === c) {
          v.voter_token = a.p_voter;
          carried++;
        }
      }
    }
    return { verdict: "ok", carried };
  }
  function cull(a) {
    const culled = [];
    const last = new Map();
    for (const v of state.votes) {
      if (!last.has(v.design_id) || v.updated_at > last.get(v.design_id)) last.set(v.design_id, v.updated_at);
    }
    for (const t of tally()) {
      const lastVote = last.get(t.design_id);
      if (t.up + t.down < a.p_min || t.up / (t.up + t.down) >= a.p_ratio) continue;
      if (state.retired.some((r) => r.design_id === t.design_id && (!r.restored_at || r.restored_at > lastVote))) continue;
      if (
        state.subs.some(
          (s) => `sub-${s.id}` === t.design_id && (s.status !== "approved" || (s.restored_at && s.restored_at > lastVote)),
        )
      ) {
        continue;
      }
      state.retired.push({
        id: ++state.seq,
        design_id: t.design_id,
        retired_at: iso(),
        reason: `cull: ${t.up} up, ${t.down} down`,
        restored_at: null,
      });
      culled.push(t.design_id);
    }
    return culled;
  }

  function database(url, init) {
    if (state.db === "down") return reply(503, { message: "down" });
    if (init.headers.apikey !== env.SUPABASE_SERVICE_ROLE_KEY) return reply(401, { message: "no key" });
    const u = new URL(url);
    const path = `${u.pathname}${u.search}`.replace(/^\/rest\/v1\//, "");
    const body = init.body ? JSON.parse(init.body) : null;
    if (path.startsWith("rpc/")) {
      const fn = { hsd_vote_tally: tally, hsd_vote_cast: cast, hsd_vote_register: register, hsd_vote_cull: cull }[
        path.slice(4)
      ];
      return fn ? reply(200, fn(body)) : reply(404, { message: path });
    }
    const { name, f, select, order } = query(path);
    if (!tables[name]) return reply(404, { message: name });
    const rows = tables[name]();
    const hit = rows.filter((r) => matches(r, f));
    if (order) hit.sort((a, b) => String(a[order] ?? "").localeCompare(String(b[order] ?? "")));
    if (init.method === "HEAD") {
      return new Response(null, { status: 200, headers: { "Content-Range": `*/${hit.length}` } });
    }
    if (init.method === "GET") return reply(200, hit.map((r) => pick(r, select)));
    if (init.method === "POST") {
      const row = { ...body };
      if (name === "hsd_submissions") Object.assign(row, { created_at: iso(), removed_at: null, restored_at: null });
      if (name === "hsd_retired") Object.assign(row, { id: ++state.seq, restored_at: null });
      rows.push(row);
      return reply(201, null);
    }
    if (init.method === "PATCH") {
      for (const r of hit) Object.assign(r, body);
      return reply(200, hit);
    }
    if (init.method === "DELETE") {
      for (const r of hit) rows.splice(rows.indexOf(r), 1);
      return reply(200, null);
    }
    return reply(405, { message: init.method });
  }

  function storage(url, init) {
    if (init.headers.apikey !== env.SUPABASE_SERVICE_ROLE_KEY) return reply(401, { message: "no key" });
    const key = decodeURIComponent(new URL(url).pathname.replace(/^\/storage\/v1\/object\/hsd-submissions\//, ""));
    if (init.method === "POST") {
      if (state.files.has(key)) return reply(409, { message: "exists" });
      state.files.set(key, init.body);
      return reply(200, { Key: key });
    }
    if (init.method === "GET") {
      const data = state.files.get(key);
      return data ? new Response(data, { status: 200 }) : reply(404, { message: "not found" });
    }
    return reply(405, { message: init.method });
  }

  function cloudflare(init) {
    if (state.turnstile === "down") throw new TypeError("network");
    const form = new URLSearchParams(init.body.toString());
    if (form.get("secret") !== env.VOTE_TURNSTILE_SECRET) return reply(200, { success: false });
    const answers = {
      pass: { success: true, hostname: "hickorysandsdistrictava.org" },
      fail: { success: false, "error-codes": ["invalid-input-response"] },
      "other-host": { success: true, hostname: "example.org" },
      "test-key": { success: true, hostname: "hickorysandsdistrictava.org", metadata: { result_with_testing_key: true } },
    };
    return reply(200, answers[form.get("response")] || answers[state.turnstile] || answers.fail);
  }

  async function fetchStub(url, init = {}) {
    init = { ...init, headers: { ...(init.headers || {}) } };
    const u = new URL(url);
    if (u.origin === DB && u.pathname.startsWith("/rest/v1/")) return database(url, init);
    if (u.origin === DB && u.pathname.startsWith("/storage/v1/object/hsd-submissions/")) return storage(url, init);
    if (u.origin === "https://challenges.cloudflare.com" && u.pathname === "/turnstile/v0/siteverify") {
      return cloudflare(init);
    }
    throw new Error(`no stand-in for ${url}`);
  }

  const deps = {
    env: (k) => env[k] ?? "",
    fetch: fetchStub,
    now: () => state.now,
    log: (...args) => state.logs.push(args.map(String).join(" ")),
  };
  return { state, env, deps, tick };
}

// --- requests -------------------------------------------------------------

function form(fields, { origin = SITE, ip = "203.0.113.7", path = "" } = {}) {
  const body = new URLSearchParams(fields).toString();
  const h = { "Content-Type": "application/x-www-form-urlencoded", "cf-connecting-ip": ip };
  if (origin) h.Origin = origin;
  return new Request(URL_BASE + path, { method: "POST", headers: h, body });
}
function get(path = "", { origin = SITE } = {}) {
  const h = origin ? { Origin: origin } : {};
  return new Request(URL_BASE + path, { method: "GET", headers: h });
}
async function look(res) {
  const t = await res.text();
  let body = t;
  try {
    body = JSON.parse(t);
  } catch {
    body = t;
  }
  return {
    status: res.status,
    body,
    acao: res.headers.get("Access-Control-Allow-Origin"),
    type: res.headers.get("Content-Type"),
    nosniff: res.headers.get("X-Content-Type-Options"),
    cache: res.headers.get("Cache-Control"),
  };
}

const JPEG = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0, 16, 74, 70, 73, 70, 0, 1]).toString("base64");

export async function cases(bundlePath) {
  const fn = await import(pathToFileURL(bundlePath));
  const out = {};
  const fresh = (opts) => {
    const s = standIn(opts);
    const handle = fn.makeHandler(s.deps);
    const ask = async (req) => await look(await handle(req));
    const post = (fields, o) => ask(form(fields, o));
    const admin = (action, fields = {}) => post({ action, key: s.env.OPERATOR_KEY, ...fields }, { origin: null });
    const voter = async (ip = "203.0.113.7", token = "pass") => (await post({ action: "register", token }, { ip })).body.voter;
    return { ...s, handle, ask, post, admin, voter };
  };

  // --- CORS: the site only ---------------------------------------------------
  let t = fresh();
  out.preflight = await t.ask(new Request(URL_BASE, { method: "OPTIONS", headers: { Origin: SITE } }));
  out.preflightOther = await t.ask(
    new Request(URL_BASE, { method: "OPTIONS", headers: { Origin: "https://example.com" } }),
  );
  out.stateSite = await t.ask(get());
  out.stateOther = await t.ask(get("", { origin: "https://example.com" }));
  out.postOther = await t.post({ action: "register", token: "pass" }, { origin: "https://example.com" });
  out.jsonp = await t.ask(get("?callback=steal"));
  out.unknownAction = await t.post({ action: "nothing" });

  // --- the person check ON (VOTE_TURNSTILE_SECRET set) ----------------------
  t = fresh({ turnstile: true });
  for (const token of ["", "fail", "other-host", "test-key"]) {
    out[`checkOn:${token}`] = await t.post({ action: "register", token });
  }
  t.state.turnstile = "down";
  out["checkOn:down"] = await t.post({ action: "register", token: "anything" });
  t.state.turnstile = "pass";
  out.checkOnPass = await t.post({ action: "register", token: "pass" });
  out.checkOnRows = t.state.registrations.length;

  // --- the person check OFF (no VOTE_TURNSTILE_SECRET) ----------------------
  t = fresh({ turnstile: false });
  out.checkOff = await t.post({ action: "register" });
  out.checkOffCalls = t.state.logs.filter((l) => l.includes("Turnstile")).length;

  // --- both modes: signed ids, the limits ------------------------------------
  for (const mode of ["on", "off"]) {
    t = fresh({ turnstile: mode === "on" });
    const r = {};
    const v = await t.voter();
    r.voter = v;
    const forged = `v2-${"0".repeat(24)}-${"0".repeat(32)}`;
    const tampered = v.slice(0, -1) + (v.endsWith("0") ? "1" : "0");
    for (const [name, bad] of [
      ["made-up", "vmadeup123456"],
      ["forged", forged],
      ["tampered", tampered],
      ["empty", ""],
    ]) {
      r[`vote:${name}`] = (await t.post({ action: "vote", id: "c3", voter: bad, dir: "1" })).body;
    }
    r.unvoteForged = (await t.post({ action: "unvote", id: "c3", voter: forged })).body;
    r.myVotesForged = (await t.post({ action: "my_votes", voter: forged })).body;
    r.vote = (await t.post({ action: "vote", id: "c3", voter: v, dir: "1" })).body;
    r.upAfter = (await t.ask(get())).body.up.c3;
    r.unknown = await t.post({ action: "vote", id: "c99", voter: v, dir: "1" });
    r.unknownSub = await t.post({ action: "vote", id: "sub-11111111-1111-4111-8111-111111111111", voter: v, dir: "1" });
    r.myVotes = (await t.post({ action: "my_votes", voter: v })).body;
    // ten voters per design per address per day; changing a vote is free
    const net = "198.51.100.20";
    const voters = [];
    for (let i = 0; i < 11; i++) voters.push(await t.voter(`198.51.100.${100 + i}`));
    r.network = [];
    for (const x of voters) r.network.push((await t.post({ action: "vote", id: "c6", voter: x, dir: "1" }, { ip: net })).body);
    r.change = (await t.post({ action: "vote", id: "c6", voter: voters[0], dir: "-1" }, { ip: net })).body;
    await t.post({ action: "unvote", id: "c6", voter: voters[1] }, { ip: net });
    r.again = (await t.post({ action: "vote", id: "c6", voter: voters[1], dir: "1" }, { ip: net })).body;
    r.otherDesign = (await t.post({ action: "vote", id: "c8", voter: voters[10], dir: "1" }, { ip: net })).body;
    r.otherNetwork = (await t.post({ action: "vote", id: "c6", voter: voters[10], dir: "1" }, { ip: "198.51.100.21" })).body;
    t.tick(25 * 3600 * 1000);
    r.nextDay = (await t.post({ action: "vote", id: "c6", voter: voters[10], dir: "1" }, { ip: "198.51.100.20" })).body;
    r.hashes = t.state.networks.map((n) => n.ip_hash);
    // five new ids per address per day
    const regs = [];
    for (let i = 0; i < 6; i++) regs.push(await t.post({ action: "register", token: "pass" }, { ip: "192.0.2.50" }));
    r.registers = regs.map((x) => (typeof x.body === "object" ? "id" : x.body));
    r.registerOther = typeof (await t.post({ action: "register", token: "pass" }, { ip: "192.0.2.51" })).body;
    r.regHashes = t.state.registrations.map((x) => x.ip_hash);
    out[`mode:${mode}`] = r;
  }

  // --- the carry-over from the Shopify page ---------------------------------
  t = fresh();
  t.state.votes.push(
    { design_id: "c1", voter_token: "vshopify0001", dir: 1, updated_at: "2026-10-01T00:00:00.000Z" },
    { design_id: "c3", voter_token: "vshopify0001", dir: -1, updated_at: "2026-10-01T00:00:00.000Z" },
    { design_id: "c4", voter_token: "vshopify0001", dir: 1, updated_at: "2026-10-01T00:00:00.000Z" },
  );
  const before = await t.ask(get());
  const carried = await t.post({ action: "register", token: "pass", carry: "vshopify0001" });
  out.carried = carried.body.carried;
  out.carriedMine = (await t.post({ action: "my_votes", voter: carried.body.voter })).body;
  const after = await t.ask(get());
  out.carriedCounts = [before.body.up, before.body.down, after.body.up, after.body.down];
  out.oldIdVotes = (await t.post({ action: "vote", id: "c5", voter: "vshopify0001", dir: "1" })).body;
  out.secondCarry = (await t.post({ action: "register", token: "pass", carry: "vshopify0001" })).body.carried;
  out.badCarry = (await t.post({ action: "register", token: "pass", carry: "../etc" })).body.carried;

  // --- sending a design, names, the image ------------------------------------
  t = fresh();
  out.upload = (await t.post({ action: "upload", data: JPEG, title: "Grandpa's <b>Mesa</b> & Co", name: "A Grower" })).body;
  out.notImage = (await t.post({ action: "upload", data: Buffer.from("%PDF-1.4").toString("base64") })).body;
  out.badData = (await t.post({ action: "upload", data: "***" })).body;
  const row = t.state.subs[0];
  out.uploadRow = { name: row.name, title: row.title, status: row.status, ipHash: row.ip_hash, ip: row.ip ?? null };
  out.pendingBadKey = await t.post({ action: "admin_pending", key: "wrong" }, { origin: null });
  out.pending = (await t.admin("admin_pending")).body;
  out.imgPending = (await t.ask(get(`/img/${row.id}`))).status;
  await t.admin("admin_approve", { id: row.id });
  const st = (await t.ask(get())).body;
  out.stateSubs = st.submissions;
  out.stateRule = st.rule;
  out.img = await t.ask(get(`/img/${row.id}`));
  out.img.body = null;
  out.imgBadId = (await t.ask(get("/img/..%2Fsecret"))).status;
  const uploads = [];
  for (let i = 0; i < 6; i++) uploads.push((await t.post({ action: "upload", data: JPEG }, { ip: "192.0.2.9" })).body);
  out.uploadsPerAddress = uploads;

  // --- nothing is ever deleted: retire, restore, remove, restore -------------
  t = fresh();
  for (let i = 0; i < 3; i++) await t.post({ action: "vote", id: "c5", voter: await t.voter(`10.5.1.${i}`), dir: "1" }, { ip: `10.5.0.${i}` });
  for (let i = 3; i < 25; i++) {
    await t.post({ action: "vote", id: "c5", voter: await t.voter(`10.5.1.${i}`), dir: "-1" }, { ip: `10.5.0.${i}` });
  }
  t.tick();
  const counts = async (d) => {
    const s = (await t.ask(get())).body;
    return [s.up[d] || 0, s.down[d] || 0];
  };
  const h = {};
  h.before = await counts("c5");
  h.cull = (await t.admin("admin_cull")).body;
  h.retired = (await t.ask(get())).body.retired;
  h.afterCull = await counts("c5");
  h.record = (await t.admin("admin_history")).body.retired;
  t.tick();
  await t.admin("admin_unretire", { id: "c5" });
  h.retiredAfterUnretire = (await t.ask(get())).body.retired;
  h.recordAfterUnretire = (await t.admin("admin_history")).body.retired;
  t.tick();
  h.cullRestored = (await t.admin("admin_cull")).body; // skipped: restored since its last vote
  await t.post({ action: "vote", id: "c5", voter: await t.voter("10.5.9.9"), dir: "-1" }, { ip: "10.5.9.9" });
  t.tick();
  h.cullAfterVote = (await t.admin("admin_cull")).body;
  h.records = (await t.admin("admin_history")).body.retired.filter((r) => r.design_id === "c5").length;
  await t.admin("admin_unretire", { id: "c5" });
  h.retireByHand = (await t.admin("admin_retire", { id: "c8", reason: "a bug" })).body;
  h.retiredByHand = (await t.admin("admin_history")).body.retired.find((r) => r.design_id === "c8");
  // a sent-in design: trash, restore, remove, restore
  await t.post({ action: "upload", data: JPEG, title: "Sent in" });
  const sub = t.state.subs[0];
  await t.admin("admin_approve", { id: sub.id });
  for (let i = 0; i < 4; i++) {
    await t.post({ action: "vote", id: `sub-${sub.id}`, voter: await t.voter(`10.6.1.${i}`), dir: "1" }, { ip: `10.6.0.${i}` });
  }
  const subVotes = await counts(`sub-${sub.id}`);
  h.removal = [];
  for (const how of ["admin_trash", "admin_remove"]) {
    const step = { how };
    t.tick();
    await t.admin(how, { id: sub.id });
    step.inVote = (await t.ask(get())).body.submissions.some((s) => s.id === `sub-${sub.id}`);
    step.img = (await t.ask(get(`/img/${sub.id}`))).status;
    step.votesKept = JSON.stringify(await counts(`sub-${sub.id}`)) === JSON.stringify(subVotes);
    step.history = (await t.admin("admin_history")).body.removed.find((r) => r.fileId === sub.id);
    step.fileKept = t.state.files.has(sub.storage_path);
    t.tick();
    await t.admin("admin_restore", { id: sub.id });
    step.backInVote = (await t.ask(get())).body.submissions.some((s) => s.id === `sub-${sub.id}`);
    step.imgBack = (await t.ask(get(`/img/${sub.id}`))).status;
    h.removal.push(step);
  }
  await t.post({ action: "upload", data: JPEG, title: "Waiting" }, { ip: "10.7.0.1" });
  const waiting = t.state.subs.find((s) => s.title === "Waiting");
  await t.admin("admin_trash", { id: waiting.id });
  h.waitingRemoved = (await t.admin("admin_pending")).body.some((p) => p.fileId === waiting.id);
  await t.admin("admin_restore", { id: waiting.id });
  h.waitingBack = (await t.admin("admin_pending")).body.some((p) => p.fileId === waiting.id);
  h.rowsKept = t.state.subs.length;
  out.history = h;

  // --- not set up yet, and the database down --------------------------------
  t = fresh();
  delete t.env.VOTE_ID_SECRET;
  out.notReady = await t.post({ action: "register", token: "pass" });
  t = fresh();
  t.state.db = "down";
  out.dbDown = await t.ask(get());
  out.logs = t.state.logs;
  return out;
}

// --- the browser test's server ----------------------------------------------

export async function serve(port, bundlePath) {
  const fn = await import(pathToFileURL(bundlePath));
  let s = standIn();
  let handle = fn.makeHandler(s.deps);
  const server = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const body = Buffer.concat(chunks);
    const origin = req.headers.origin || "";
    if (req.url.startsWith("/standin")) {
      if (req.method === "POST") {
        const set = JSON.parse(body.toString() || "{}");
        if (set.reset) {
          s = standIn({ turnstile: set.turnstile !== false });
          handle = fn.makeHandler(s.deps);
        }
        for (const v of set.votes || []) s.state.votes.push({ updated_at: new Date().toISOString(), ...v });
      }
      res.writeHead(200, { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" });
      const subs = s.state.subs.map((r) => ({ title: r.title, name: r.name, status: r.status }));
      res.end(JSON.stringify({ votes: s.state.votes, subs }));
      return;
    }
    s.state.now = new Date();
    // the local page's requests pass as the site's; any other origin as it is
    const local = /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
    const headers = { ...req.headers, origin: local ? SITE : origin };
    headers["cf-connecting-ip"] = req.socket.remoteAddress || "";
    delete headers.host;
    const answer = await handle(
      new Request(URL_BASE + req.url.replace(/^\/functions\/v1\/vote-api/, ""), {
        method: req.method,
        headers,
        body: ["GET", "HEAD", "OPTIONS"].includes(req.method) ? undefined : body,
      }),
    );
    const out = Object.fromEntries(answer.headers.entries());
    if (local && out["access-control-allow-origin"]) out["access-control-allow-origin"] = origin;
    res.writeHead(answer.status, out);
    res.end(Buffer.from(await answer.arrayBuffer()));
  });
  server.listen(port, "127.0.0.1", () => process.stdout.write(`stand-in on http://127.0.0.1:${port}\n`));
}

const mode = process.argv[2];
if (mode === "cases") {
  console.log(JSON.stringify(await cases(process.argv[3])));
} else if (mode === "serve") {
  await serve(Number(process.argv[3]), process.argv[4]);
}
