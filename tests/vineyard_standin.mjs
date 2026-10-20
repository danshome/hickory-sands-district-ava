// Stand-ins for what the vineyard form's Edge Function talks to: Supabase's
// table (and hsd_vineyard_reserve(), as hsd_vineyard_contacts.sql does it),
// Cloudflare's Turnstile check, GitHub's API (the App's token, verified
// against a key made here, and the issues) and the site's listed vineyards
// (docs/assets/vineyards/known.json, as GitHub Pages serves it). The function itself is the real
// one, the one-file bundle Dan deploys (src/vineyards/bundle_function.py).
//
//   node tests/vineyard_standin.mjs cases BUNDLE
//       runs every case of tests/test_vineyard_function.py and prints what
//       happened, as JSON;
//   node tests/vineyard_standin.mjs serve PORT BUNDLE
//       serves the function on 127.0.0.1:PORT for the browser tests
//       (tests/live/test_vineyard_wizard.py): a request from the local page
//       is passed on as if from the site; GET /standin and POST /standin
//       read and set the stand-ins.
import { createHmac, createVerify, generateKeyPairSync } from "node:crypto";
import { readFileSync } from "node:fs";
import http from "node:http";
import { pathToFileURL } from "node:url";

const SITE = "https://hickorysandsdistrictava.org";
const API = "https://api.github.com";
const URL_BASE = "https://yayebhncbagmebwgmezd.supabase.co/functions/v1/vineyard-submit";
const KNOWN_PATH = "/assets/vineyards/known.json";
const KNOWN_FILE = new URL("../docs/assets/vineyards/known.json", import.meta.url);

const json = (status, body) => new Response(body === null ? null : JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json" },
});

export function standIn() {
  const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  const state = {
    rows: [], issues: [], logs: [], calls: [], nextIssue: 9001, siteverify: 0,
    turnstile: "pass", github: "ok", dropLabels: false, labelFails: false, db: "ok",
    now: new Date("2026-10-19T12:00:00.000Z"), seq: 0, lastTick: null,
    // the site's known.json: "ok" (the file, or knownData when set), "down"
    // (no answer), "500", "html", "malformed" (not JSON), "array" and
    // "badShape" (JSON, not the list's shape)
    known: "ok", knownData: null, knownFetches: [],
  };
  const env = {
    SUPABASE_URL: "https://db.example.invalid",
    SUPABASE_SERVICE_ROLE_KEY: "eyJ.service.role",
    GITHUB_APP_ID: "123456",
    GITHUB_APP_INSTALLATION_ID: "7890",
    // as GitHub hands it out: PKCS#1, with its line breaks
    GITHUB_APP_PRIVATE_KEY: privateKey.export({ type: "pkcs1", format: "pem" }),
    GITHUB_WEBHOOK_SECRET: "webhook-secret-for-tests", // pragma: allowlist secret
    TURNSTILE_SECRET: "turnstile-secret-for-tests", // pragma: allowlist secret
    IP_SALT: "salt-for-tests",
    PRIVATE_WORDS: "quillfeather\n# a comment\n",
  };

  function filters(query) {
    const out = {};
    for (const [k, v] of new URLSearchParams(query)) out[k] = v;
    return out;
  }
  function matches(row, f) {
    return Object.entries(f).every(([k, v]) => {
      const [op, ...rest] = v.split(".");
      const value = rest.join(".");
      if (op === "eq") return String(row[k]) === value;
      if (op === "is" && value === "null") return row[k] === null;
      if (op === "not" && value === "is.null") return row[k] !== null;
      if (op === "lt") return row[k] !== null && new Date(row[k]) < new Date(decodeURIComponent(value));
      throw new Error(`filter ${k}=${v}`);
    });
  }

  function reserve(a) {
    if (state.verdict) return [{ id: "row-forced", issue_number: null, verdict: state.verdict }];
    const again = state.rows.find((r) => r.submission_id === a.p_submission);
    if (again && again.held) return [{ id: again.id, issue_number: null, verdict: "held" }];
    // as hsd_vineyard_contacts.sql: a row without its issue for two minutes
    // belongs to a send that died, and is sent anew
    if (again && again.issue_number === null && state.now.getTime() - new Date(again.created_at).getTime() > 120000) {
      Object.assign(again, { created_at: state.now.toISOString(), ip_hash: a.p_ip_hash, contact_name: a.p_name,
        email: a.p_email, phone: a.p_phone });
      return [{ id: again.id, issue_number: null, verdict: "new" }];
    }
    if (again) return [{ id: again.id, issue_number: again.issue_number, verdict: "again" }];
    const dayAgo = state.now.getTime() - 86400000;
    const recent = state.rows.filter((r) => new Date(r.created_at).getTime() > dayAgo);
    if (recent.filter((r) => r.ip_hash === a.p_ip_hash).length >= a.p_per_ip) {
      return [{ id: null, issue_number: null, verdict: "limit-ip" }];
    }
    if (recent.length >= a.p_per_day) return [{ id: null, issue_number: null, verdict: "limit-day" }];
    if (!a.p_email && !a.p_phone) throw new Error("check hsd_vineyard_contacts_reach");
    if (String(a.p_ip_hash).length !== 32) throw new Error("check ip_hash");
    const row = {
      id: `row-${++state.seq}`, submission_id: a.p_submission, issue_number: null,
      created_at: state.now.toISOString(), closed_at: null, ip_hash: a.p_ip_hash,
      contact_name: a.p_name, email: a.p_email, phone: a.p_phone, held: null,
    };
    state.rows.push(row);
    return [{ id: row.id, issue_number: null, verdict: "new" }];
  }

  function database(url, init) {
    if (state.db === "down") return json(503, { message: "down" });
    if (state.db === "link" && init.method === "PATCH" && init.body?.includes("issue_number")) {
      return json(500, { message: "link failed" });
    }
    if (init.headers.apikey !== env.SUPABASE_SERVICE_ROLE_KEY) return json(401, { message: "no key" });
    const u = new URL(url);
    const path = `${u.pathname}${u.search}`.replace(/^\/rest\/v1\//, "");
    const [name, query] = path.split("?");
    const body = init.body ? JSON.parse(init.body) : null;
    if (name === "rpc/hsd_vineyard_reserve" && init.method === "POST") return json(200, reserve(body));
    if (name === "rpc/hsd_vineyard_tick" && init.method === "POST") {
      // as hsd_vineyard_contacts.sql: true, and the time noted, once the last
      // time is older than p_every_seconds
      const due = state.lastTick === null || state.now - state.lastTick >= body.p_every_seconds * 1000;
      if (due) state.lastTick = state.now.getTime();
      return json(200, due);
    }
    if (name !== "hsd_vineyard_contacts") return json(404, { message: name });
    const f = filters(query || "");
    const select = f.select;
    delete f.select;
    if (init.method === "GET") {
      const fields = (select || "").split(",").filter(Boolean);
      const hit = state.rows.filter((r) => matches(r, f));
      return json(200, hit.map((r) => (fields.length ? Object.fromEntries(fields.map((k) => [k, r[k]])) : { ...r })));
    }
    if (init.method === "PATCH") {
      const hit = state.rows.filter((r) => matches(r, f));
      for (const r of hit) Object.assign(r, body);
      return json(200, hit);
    }
    if (init.method === "DELETE") {
      const hit = state.rows.filter((r) => matches(r, f));
      state.rows = state.rows.filter((r) => !hit.includes(r));
      return json(200, hit);
    }
    return json(405, { message: init.method });
  }

  function verifyJwt(auth) {
    const [head, claims, sig] = auth.replace(/^Bearer /, "").split(".");
    const v = createVerify("RSA-SHA256");
    v.update(`${head}.${claims}`);
    const ok = v.verify(publicKey, Buffer.from(sig, "base64url"));
    const c = JSON.parse(Buffer.from(claims, "base64url").toString());
    return ok && c.iss === env.GITHUB_APP_ID && c.exp - c.iat <= 660;
  }

  function github(url, init) {
    const u = new URL(url);
    const path = u.pathname;
    const body = init.body ? JSON.parse(init.body) : null;
    if (path === `/app/installations/${env.GITHUB_APP_INSTALLATION_ID}/access_tokens`) {
      if (state.github === "token-fails" || !verifyJwt(init.headers.Authorization)) return json(401, { message: "Bad credentials" });
      state.calls.push({ token: body });
      return json(201, { token: "ghs_installation_token_for_tests" });
    }
    if (init.headers.Authorization !== "Bearer ghs_installation_token_for_tests") return json(401, { message: "Bad credentials" });
    const repo = "/repos/danshome/hickory-sands-district-ava";
    if (path === `${repo}/issues` && init.method === "GET") {
      if (state.github === "list-fails") return json(500, { message: "Server Error" });
      const q = u.searchParams;
      const since = new Date(q.get("since") || 0).getTime();
      const found = state.issues
        .filter((i) => i.user.login === q.get("creator") && new Date(i.updated_at).getTime() >= since)
        .sort((a, b) => b.number - a.number);
      const per = Number(q.get("per_page") || 30);
      const page = Number(q.get("page") || 1);
      return json(200, found.slice((page - 1) * per, page * per));
    }
    if (path === `${repo}/issues` && init.method === "POST") {
      if (state.github === "issue-fails") return json(502, { message: "Server Error" });
      const at = state.now.toISOString();
      const issue = {
        number: state.nextIssue++, title: body.title, body: body.body, state: "open", closed_at: null,
        created_at: at, updated_at: at,
        labels: state.dropLabels ? [] : body.labels.map((name) => ({ name })),
        user: { login: "hsd-vineyard-form[bot]" },
      };
      state.issues.push(issue);
      if (state.github === "answer-lost") throw new TypeError("network");
      return json(201, issue);
    }
    const m = path.match(new RegExp(`^${repo}/issues/(\\d+)/labels$`));
    if (m && init.method === "POST") {
      if (state.labelFails) return json(500, { message: "Server Error" });
      if (state.labelMissing && body.labels.includes(state.labelMissing)) {
        return json(422, { message: "Validation Failed" }); // a label not made yet
      }
      const issue = state.issues.find((i) => i.number === Number(m[1]));
      issue.labels.push(...body.labels.map((name) => ({ name })));
      return json(200, issue.labels);
    }
    return json(404, { message: path });
  }

  function turnstile(init) {
    state.siteverify += 1;
    if (state.turnstile === "down") throw new TypeError("network");
    if (state.turnstile === "5xx") return new Response("<html>Bad gateway</html>", { status: 502 });
    if (state.turnstile === "html") return new Response("<html>a challenge page</html>", { status: 200 });
    const form = new URLSearchParams(init.body.toString());
    if (form.get("secret") !== env.TURNSTILE_SECRET) return json(200, { success: false });
    const token = form.get("response");
    const answers = {
      pass: { success: true, hostname: "hickorysandsdistrictava.org", action: "vineyard-submit" },
      "test-key": { success: true, hostname: "example.com", action: "vineyard-submit", metadata: { result_with_testing_key: true } },
      "other-host": { success: true, hostname: "example.org", action: "vineyard-submit" },
      "other-action": { success: true, hostname: "hickorysandsdistrictava.org", action: "vote" },
      fail: { success: false, "error-codes": ["invalid-input-response"] },
    };
    // a named token answers as named; any other (the browser's) as the
    // stand-in is set: "pass" by default
    const mode = answers[token] ? token : state.turnstile;
    return json(200, answers[mode] || { success: false, "error-codes": ["invalid-input-response"] });
  }

  function knownList(url, init) {
    state.knownFetches.push({ url, method: init.method || "GET", timeout: Boolean(init.signal) });
    if (state.known === "down") throw new TypeError("fetch failed");
    if (state.known === "500") return new Response("oops", { status: 500 });
    if (state.known === "html") return new Response("<!doctype html><p>Not found</p>", { status: 200 });
    if (state.known === "malformed") return new Response('{"blackmon-vineyard": {"name": "Blackmon', { status: 200 });
    if (state.known === "array") return json(200, [{ name: "Blackmon Vineyard" }]);
    if (state.known === "badShape") {
      const list = JSON.parse(readFileSync(KNOWN_FILE, "utf8"));
      list["blackmon-vineyard"].blocks = [[[-99.37, "30.82"], [-99.36, 30.82], [-99.36, 30.81]]];
      return json(200, list);
    }
    return json(200, state.knownData ?? JSON.parse(readFileSync(KNOWN_FILE, "utf8")));
  }

  async function fetchStub(url, init = {}) {
    init = { ...init, headers: { ...(init.headers || {}) } };
    // each stand-in by the URL's protocol and host name, parsed, never by its text
    const u = new URL(url);
    const at = (base) => {
      const b = new URL(base);
      return u.protocol === b.protocol && u.hostname === b.hostname;
    };
    if (at(env.SUPABASE_URL)) return database(url, init);
    if (at(API)) return github(url, init);
    if (at(SITE) && u.pathname === KNOWN_PATH) return knownList(url, init);
    if (at("https://known.example.invalid")) return knownList(url, init); // KNOWN_VINEYARDS_URL
    if (at("https://challenges.cloudflare.com") && u.pathname === "/turnstile/v0/siteverify") return turnstile(init);
    throw new Error(`no stand-in for ${url}`);
  }

  const deps = {
    env: (k) => env[k] ?? "",
    fetch: fetchStub,
    now: () => state.now,
    log: (...args) => state.logs.push(args.map(String).join(" ")),
  };
  return { state, env, deps, privateKey, publicKey };
}

// --- the cases (tests/test_vineyard_function.py) ---------------------------

const GOOD = {
  form: "hsd-vineyard", version: 1, id: "3f2b8c1e-5d4a-4e6f-9a7b-1c2d3e4f5a6b",
  vineyard: { name: "Prairie Gap Vineyard", county: "Mason", planted: "planted", acres: 4.5, year: 2019,
    varieties: ["Tempranillo", "Mourvèdre"] },
  blocks: [[[-99.295, 30.865], [-99.2925, 30.865], [-99.2925, 30.8632], [-99.295, 30.8632]]],
  pin: null,
  contact: { name: "Jane Q. Grower", email: "jane@example.com", phone: "325-555-0100" },
  agree: { public: true, permission: true }, website: "", turnstile: "pass",
};
const uuid = (n) => `3f2b8c1e-5d4a-4e6f-9a7b-${String(n).padStart(12, "0")}`;

function request(body, { origin = SITE, type = "application/json", ip = "203.0.113.7", path = "", method = "POST", headers = {} } = {}) {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  const h = { "Content-Type": type, "cf-connecting-ip": ip, ...headers };
  if (origin) h.Origin = origin;
  if (method !== "GET" && method !== "OPTIONS") h["Content-Length"] = String(Buffer.byteLength(text));
  return new Request(URL_BASE + path, { method, headers: h, body: method === "GET" || method === "OPTIONS" ? undefined : text });
}

async function look(res) {
  const text = await res.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  return { status: res.status, body, acao: res.headers.get("Access-Control-Allow-Origin") };
}

function hook(env, payload, event = "issues", secret = env.GITHUB_WEBHOOK_SECRET) {
  const text = JSON.stringify(payload);
  const sig = `sha256=${createHmac("sha256", secret).update(text).digest("hex")}`;
  return request(text, { origin: null, path: "/github", headers: { "X-GitHub-Event": event, "X-Hub-Signature-256": sig } });
}

export async function cases(bundlePath) {
  const fn = await import(pathToFileURL(bundlePath));
  const out = {};
  const fresh = () => {
    const s = standIn();
    return { ...s, handle: fn.makeHandler(s.deps) };
  };

  // CORS and the request's shape
  let t = fresh();
  out.preflight = await look(await t.handle(request(null, { method: "OPTIONS" })));
  out.preflightOther = await look(await t.handle(request(null, { method: "OPTIONS", origin: "https://example.com" })));
  out.otherOrigin = await look(await t.handle(request(GOOD, { origin: "https://example.com" })));
  out.noOrigin = await look(await t.handle(request(GOOD, { origin: null })));
  out.get = await look(await t.handle(request(null, { method: "GET" })));
  out.textPlain = await look(await t.handle(request(GOOD, { type: "text/plain" })));
  out.tooLarge = await look(await t.handle(request({ ...GOOD, pad: "x".repeat(70000) })));
  out.notJson = await look(await t.handle(request("{")));
  out.array = await look(await t.handle(request("[]")));
  out.nan = await look(await t.handle(request(JSON.stringify(GOOD).replace("-99.295", "NaN"))));

  // Turnstile
  for (const token of ["", "fail", "test-key", "other-host", "other-action"]) {
    out[`turnstile:${token}`] = await look(await t.handle(request({ ...GOOD, turnstile: token })));
  }
  t.state.turnstile = "down";
  out["turnstile:down"] = await look(await t.handle(request(GOOD)));
  out.afterTurnstile = { rows: t.state.rows.length, issues: t.state.issues.length };

  // the trap, the rules, the private words
  t = fresh();
  out.trap = await look(await t.handle(request({ ...GOOD, website: "http://spam" })));
  out.invalid = await look(await t.handle(request({ ...GOOD, vineyard: { ...GOOD.vineyard, name: "Call 3255550100" } })));
  out.privateWord = await look(await t.handle(request({ ...GOOD, vineyard: { ...GOOD.vineyard, name: "Quillfeather Vineyard" } })));
  out.afterRefusals = { rows: t.state.rows.length, issues: t.state.issues.length };

  // a good one, and the same one again
  t = fresh();
  out.good = await look(await t.handle(request(GOOD)));
  out.goodRow = { ...t.state.rows[0] };
  out.goodIssue = t.state.issues[0];
  out.tokenAsked = t.state.calls[0];
  out.again = await look(await t.handle(request(GOOD)));
  out.afterAgain = { rows: t.state.rows.length, issues: t.state.issues.length };
  out.logs = [...t.state.logs];

  // a send still under way: the row is there, its issue number not yet
  const orphan = (id, ms) => ({ id: `row-${id}`, submission_id: uuid(id), issue_number: null,
    created_at: new Date(t.state.now.getTime() - ms).toISOString(), closed_at: null, ip_hash: "f".repeat(32),
    contact_name: "X", email: "x@example.com", phone: null, held: null });
  t.state.rows.push(orphan(99, 30000));
  out.inProgress = await look(await t.handle(request({ ...GOOD, id: uuid(99) })));
  // a send that died between GitHub and the table, three minutes ago: sent anew
  t.state.rows.push(orphan(98, 180000));
  out.stale = await look(await t.handle(request({ ...GOOD, id: uuid(98) })));
  out.staleRow = t.state.rows.find((r) => r.submission_id === uuid(98));
  // rows never tied to an issue go after a day
  t.state.rows.push(orphan(97, 25 * 3600000), orphan(96, 23 * 3600000));
  await t.handle(request({ ...GOOD, id: uuid(95) }));
  out.orphans = t.state.rows.filter((r) => [uuid(97), uuid(96)].includes(r.submission_id)).map((r) => r.submission_id);

  // GitHub's answer lost: the issue was made, the row kept (409); a retry
  // within two minutes is told to wait; after, it finds the issue by its
  // marker and ties the row to it: one issue, never two
  t = fresh();
  t.state.github = "answer-lost";
  out.lost = await look(await t.handle(request(GOOD)));
  out.afterLost = { rows: t.state.rows.map((r) => r.issue_number), issues: t.state.issues.length };
  t.state.github = "ok";
  out.lostSoon = await look(await t.handle(request(GOOD)));
  t.state.now = new Date(t.state.now.getTime() + 180000);
  out.lostLater = await look(await t.handle(request(GOOD)));
  out.afterLostLater = { rows: t.state.rows.map((r) => r.issue_number), issues: t.state.issues.length };
  out.markerInBody = /<!-- hsd-vineyard-ref: [0-9a-f]{24} -->/.test(t.state.issues[0].body);

  // the row not tied to its issue: never reported as sent (503); a retry
  // after two minutes ties it to the same issue
  t = fresh();
  t.state.db = "link";
  out.linkFails = await look(await t.handle(request(GOOD)));
  out.afterLinkFails = { rows: t.state.rows.map((r) => r.issue_number), issues: t.state.issues.length };
  t.state.db = "ok";
  t.state.now = new Date(t.state.now.getTime() + 180000);
  out.linkRetry = await look(await t.handle(request(GOOD)));
  out.afterLinkRetry = { rows: t.state.rows.map((r) => r.issue_number), issues: t.state.issues.length };

  // the label refused: the issue and its row stand (200); the reconciliation
  // puts the label back
  t = fresh();
  t.state.dropLabels = true;
  t.state.labelFails = true;
  out.labelFails = await look(await t.handle(request(GOOD)));
  out.afterLabelFails = { rows: t.state.rows.map((r) => r.issue_number), labels: t.state.issues[0].labels.length };
  t.state.labelFails = false;
  out.reconcileLabel = await look(await t.handle(request(null, { origin: null, path: "/reconcile" })));
  out.afterReconcileLabel = t.state.issues[0].labels.map((l) => l.name);

  // Turnstile itself failing is not a refusal: 503, so the page offers a retry
  t = fresh();
  t.state.turnstile = "5xx";
  out.turnstile5xx = await look(await t.handle(request(GOOD)));
  t.state.turnstile = "html";
  out.turnstileHtml = await look(await t.handle(request(GOOD)));

  // the reconciliation: a close the webhook missed, at most once every ten
  // minutes; a reopening; a deleted issue; a row tied by its marker; the
  // sweep failing is reported
  t = fresh();
  await t.handle(request(GOOD));
  await t.handle(request({ ...GOOD, id: uuid(2) }, { ip: "198.51.100.2" }));
  const closeIssue = (n) => {
    const i = t.state.issues.find((x) => x.number === n);
    Object.assign(i, { state: "closed", closed_at: "2026-10-19T12:30:00Z", updated_at: t.state.now.toISOString() });
  };
  closeIssue(9001);
  t.state.lastTick = t.state.now.getTime(); // a reconciliation just ran
  out.recThrottled = await look(await t.handle(request(null, { origin: null, path: "/reconcile" })));
  t.state.now = new Date(t.state.now.getTime() + 11 * 60000);
  out.recClosed = await look(await t.handle(request(null, { origin: null, path: "/reconcile" })));
  out.afterRecClosed = t.state.rows.map((r) => [r.issue_number, r.closed_at]);
  Object.assign(t.state.issues[0], { state: "open", closed_at: null });
  t.state.issues = t.state.issues.filter((i) => i.number !== 9002); // 9002 deleted
  t.state.now = new Date(t.state.now.getTime() + 11 * 60000);
  out.recReopened = await look(await t.handle(request(null, { origin: null, path: "/reconcile" })));
  out.afterRecReopened = t.state.rows.map((r) => [r.issue_number, r.closed_at === null]);
  t = fresh();
  t.state.github = "answer-lost";
  await t.handle(request(GOOD));
  t.state.github = "ok";
  t.state.now = new Date(t.state.now.getTime() + 180000);
  out.recLinked = await look(await t.handle(request(null, { origin: null, path: "/reconcile" })));
  out.afterRecLinked = t.state.rows.map((r) => r.issue_number);
  t.state.db = "down";
  out.recSweepFails = await look(await t.handle(request(null, { origin: null, path: "/reconcile" })));
  t.state.db = "ok";
  t.state.github = "list-fails";
  t.state.now = new Date(t.state.now.getTime() + 11 * 60000);
  out.recGithubFails = await look(await t.handle(request(null, { origin: null, path: "/reconcile" })));
  t = fresh();
  t.env.IP_SALT = "";
  out.recNotReady = await look(await t.handle(request(null, { origin: null, path: "/reconcile" })));

  // PRIVATE_WORDS_SILENT (off unless Dan sets it): a private word is held
  // for the petitioners, thanked as any other, never posted; a retry gets the
  // same; the held row outlives the day's sweep of rows without an issue
  t = fresh();
  t.env.PRIVATE_WORDS_SILENT = "1";
  const quill = { ...GOOD, vineyard: { ...GOOD.vineyard, name: "Quillfeather Vineyard" } };
  out.silent = await look(await t.handle(request(quill)));
  out.silentAgain = await look(await t.handle(request(quill)));
  out.afterSilent = { rows: t.state.rows.map((r) => [r.issue_number, r.held]), issues: t.state.issues.length };
  t.state.now = new Date(t.state.now.getTime() + 2 * 86400000);
  await t.handle(request({ ...GOOD, id: uuid(94) }));
  out.silentKept = t.state.rows.filter((r) => r.held).length;
  out.silentLogs = [...t.state.logs];

  // the health check's digest of the address the limits use
  t = fresh();
  const probe = async (ip) => (await look(await t.handle(request(null, { method: "GET", path: "/health", ip })))).body.address_digest;
  out.digests = [await probe("203.0.113.1"), await probe("203.0.113.1"), await probe("198.51.100.2")];

  // the limits: 5 a day from one address, 30 a day in all
  t = fresh();
  const perIp = [];
  for (let i = 1; i <= 6; i++) perIp.push((await look(await t.handle(request({ ...GOOD, id: uuid(i) })))).status);
  out.perIp = perIp;
  out.perIpLast = await look(await t.handle(request({ ...GOOD, id: uuid(7) })));
  t = fresh();
  const perDay = [];
  for (let i = 1; i <= 31; i++) {
    perDay.push((await look(await t.handle(request({ ...GOOD, id: uuid(100 + i) }, { ip: `198.51.100.${i}` })))).status);
  }
  out.perDay = perDay;
  out.perDayLast = await look(await t.handle(request({ ...GOOD, id: uuid(200) }, { ip: "198.51.100.200" })));
  t.state.now = new Date(t.state.now.getTime() + 86400000 + 1000);
  out.nextDay = await look(await t.handle(request({ ...GOOD, id: uuid(201) }, { ip: "198.51.100.201" })));

  // GitHub failing: the row is freed, a retry starts again
  t = fresh();
  t.state.github = "issue-fails";
  out.githubFails = await look(await t.handle(request(GOOD)));
  out.afterGithubFails = { rows: t.state.rows.length, issues: t.state.issues.length };
  t.state.github = "ok";
  out.retry = await look(await t.handle(request(GOOD)));
  t = fresh();
  t.state.github = "token-fails";
  out.tokenFails = await look(await t.handle(request(GOOD)));
  out.afterTokenFails = { rows: t.state.rows.length };
  t = fresh();
  t.state.db = "down";
  out.dbDown = await look(await t.handle(request(GOOD)));
  out.dbDownIssues = t.state.issues.length;

  // a label GitHub dropped is added again
  t = fresh();
  t.state.dropLabels = true;
  out.dropped = await look(await t.handle(request(GOOD)));
  out.droppedLabels = t.state.issues[0].labels.map((l) => l.name);

  // secrets missing
  t = fresh();
  t.env.TURNSTILE_SECRET = "";
  t.env.IP_SALT = "";
  out.notReady = await look(await t.handle(request(GOOD)));
  out.health = await look(await t.handle(request(null, { method: "GET", path: "/health", headers: { "x-forwarded-for": "198.51.100.1, 10.0.0.1" } })));
  t = fresh();
  out.healthReady = await look(await t.handle(request(null, { method: "GET", path: "/health" })));

  // the person check off (TURNSTILE_SECRET unset): ready, Cloudflare never
  // asked, a token ignored; the trap and the limits stay
  t = fresh();
  t.env.TURNSTILE_SECRET = "";
  out.offHealth = await look(await t.handle(request(null, { method: "GET", path: "/health" })));
  const { turnstile: _, ...noToken } = GOOD;
  out.offSent = await look(await t.handle(request(noToken)));
  out.offFailToken = await look(await t.handle(request({ ...GOOD, id: uuid(300), turnstile: "fail" }, { ip: "198.51.100.30" })));
  out.offTrap = await look(await t.handle(request({ ...noToken, id: uuid(301), website: "http://spam" }, { ip: "198.51.100.31" })));
  out.offInvalid = await look(await t.handle(request({ ...noToken, id: uuid(302), vineyard: { ...GOOD.vineyard, name: "Call 3255550100" } }, { ip: "198.51.100.32" })));
  out.afterOff = { rows: t.state.rows.length, issues: t.state.issues.length };
  const offPerIp = [];
  for (let i = 0; i < 6; i++) {
    offPerIp.push((await look(await t.handle(request({ ...noToken, id: uuid(310 + i) }, { ip: "198.51.100.40" })))).status);
  }
  out.offPerIp = offPerIp;
  out.offSiteverify = t.state.siteverify;

  // the key, in each form Dan may paste it
  for (const form of ["pkcs1-lines", "pkcs1-one-line", "pkcs8-lines", "pkcs8-escaped", "not-a-key"]) {
    t = fresh(); // the stand-in's GitHub checks the JWT against this run's key
    const type = form.startsWith("pkcs1") ? "pkcs1" : "pkcs8";
    let text = t.privateKey.export({ type, format: "pem" });
    if (form.endsWith("one-line")) text = text.replace(/\n/g, " ");
    if (form.endsWith("escaped")) text = text.replace(/\n/g, "\\n");
    if (form === "not-a-key") text = "c2hvcnQ=";
    t.env.GITHUB_APP_PRIVATE_KEY = text;
    out[`key:${form}`] = (await look(await t.handle(request(GOOD)))).status;
    out[`keyRows:${form}`] = t.state.rows.length;
  }

  // the webhook: closing, reopening, the sweep a year on
  t = fresh();
  await t.handle(request(GOOD));
  await t.handle(request({ ...GOOD, id: uuid(2) }, { ip: "198.51.100.2" }));
  const issue = (n, extra = {}) => ({ number: n, user: { login: "hsd-vineyard-form[bot]" }, ...extra });
  out.hookBad = await look(await t.handle(hook(t.env, { action: "closed", issue: issue(9001) }, "issues", "wrong")));
  out.hookUnsigned = await look(await t.handle(request(JSON.stringify({ action: "closed" }), { origin: null, path: "/github", headers: { "X-GitHub-Event": "issues" } })));
  out.hookPing = await look(await t.handle(hook(t.env, { zen: "hello" }, "ping")));
  out.hookOther = await look(await t.handle(hook(t.env, { action: "closed", issue: { number: 9002, user: { login: "someone" } } })));
  out.afterOther = t.state.rows.map((r) => r.closed_at);
  out.hookClosed = await look(await t.handle(hook(t.env, { action: "closed", issue: issue(9001, { closed_at: "2026-10-19T13:00:00Z" }) })));
  out.afterClosed = t.state.rows.map((r) => [r.issue_number, r.closed_at]);
  out.hookReopened = await look(await t.handle(hook(t.env, { action: "reopened", issue: issue(9001) })));
  out.afterReopened = t.state.rows.map((r) => [r.issue_number, r.closed_at]);
  // a closing for an issue with no row shows in the App's delivery log (404)
  out.hookNoRow = await look(await t.handle(hook(t.env, { action: "closed", issue: issue(9999) })));
  t.state.db = "down";
  out.hookDbDown = await look(await t.handle(hook(t.env, { action: "closed", issue: issue(9001) })));
  t.state.db = "ok";
  // GitHub's own state follows, as the reconciliation reads it
  Object.assign(t.state.issues[0], { state: "closed", closed_at: "2026-10-19T13:00:00Z" });
  t.state.issues = t.state.issues.filter((i) => i.number !== 9002);
  await t.handle(hook(t.env, { action: "closed", issue: issue(9001, { closed_at: "2026-10-19T13:00:00Z" }) }));
  await t.handle(hook(t.env, { action: "deleted", issue: issue(9002) }));
  t.state.now = new Date("2027-10-01T00:00:00Z"); // under a year after closing
  await t.handle(hook(t.env, { zen: "hi" }, "ping"));
  await t.handle(hook(t.env, { action: "labeled", issue: issue(9001) }));
  out.underAYear = t.state.rows.map((r) => r.issue_number);
  t.state.now = new Date("2027-10-20T12:00:00Z"); // a year and a day on
  await t.handle(hook(t.env, { action: "labeled", issue: issue(9001) }));
  out.aYearOn = t.state.rows.map((r) => r.issue_number);

  // a change to a listed vineyard: the same rules and limits; the vineyard it
  // names must be in the bundled list; its issue is titled by the listed name
  // and labelled as a change, the listing beside the suggestion
  const CHANGE = { ...GOOD, version: 2, id: uuid(500), changes: "blackmon-vineyard", note: "Added a block in 2024." };
  t = fresh();
  out.changeHealth = (await look(await t.handle(request(null, { method: "GET", path: "/health" })))).body;
  out.change = await look(await t.handle(request(CHANGE)));
  out.changeIssue = t.state.issues[0];
  out.changeRow = t.state.rows.length;
  out.changeUnknown = await look(await t.handle(request({ ...CHANGE, id: uuid(501), changes: "no-such-vineyard" })));
  out.changeProto = await look(await t.handle(request({ ...CHANGE, id: uuid(502), changes: "__proto__" })));
  out.changeNoNote = await look(await t.handle(request({ ...CHANGE, id: uuid(503), note: "" })));
  out.changePin = await look(await t.handle(request({ ...CHANGE, id: uuid(504), blocks: [], pin: [-99.294, 30.864] })));
  out.changePrivateWord = await look(await t.handle(request({ ...CHANGE, id: uuid(505), note: "Quillfeather planted it" })));
  out.changeTrap = await look(await t.handle(request({ ...CHANGE, id: uuid(506), website: "x" })));
  out.afterChangeRefusals = { rows: t.state.rows.length, issues: t.state.issues.length };
  out.changeAgain = await look(await t.handle(request(CHANGE)));
  // a change GitHub dropped the labels of: both added again
  t = fresh();
  t.state.dropLabels = true;
  out.changeDropped = await look(await t.handle(request(CHANGE)));
  out.changeDroppedLabels = t.state.issues[0].labels.map((l) => l.name);
  // the label vineyard-change not made yet: the issue stands, with the other
  t = fresh();
  t.state.labelMissing = "vineyard-change";
  out.changeNoLabel = await look(await t.handle(request(CHANGE)));
  out.changeNoLabelLabels = t.state.issues[0].labels.map((l) => l.name);
  out.changeIssueAsked = t.state.issues.length;
  // the limits count changes and additions together
  t = fresh();
  const mixed = [];
  for (let i = 1; i <= 6; i++) {
    const body = i % 2 ? { ...GOOD, id: uuid(600 + i) } : { ...CHANGE, id: uuid(600 + i) };
    mixed.push((await look(await t.handle(request(body)))).status);
  }
  out.changeLimits = mixed;

  // the listed vineyards are the site's, read when a change comes
  t = fresh();
  out.knownGood = await look(await t.handle(request(GOOD)));
  out.knownGoodFetches = t.state.knownFetches.length; // a new vineyard never asks
  out.knownChange = await look(await t.handle(request(CHANGE)));
  out.knownFetched = t.state.knownFetches[0];
  // kept five minutes, then read again
  t.state.now = new Date(t.state.now.getTime() + 4 * 60000);
  await t.handle(request({ ...CHANGE, id: uuid(701) }));
  out.knownWithin = t.state.knownFetches.length;
  t.state.now = new Date(t.state.now.getTime() + 2 * 60000);
  await t.handle(request({ ...CHANGE, id: uuid(702) }));
  out.knownAfter = t.state.knownFetches.length;
  // the list could not be read, or not as the site makes it: refused on the
  // field "changes", as an id not listed is; nothing kept, nothing posted;
  // a failure is never kept, so the next change asks again
  for (const mode of ["down", "500", "html", "malformed", "array", "badShape"]) {
    t = fresh();
    t.state.known = mode;
    out[`known:${mode}`] = await look(await t.handle(request(CHANGE)));
    out[`knownAfter:${mode}`] = { rows: t.state.rows.length, issues: t.state.issues.length };
    out[`knownLogs:${mode}`] = [...t.state.logs];
    // a new vineyard does not depend on it
    out[`knownNew:${mode}`] = (await look(await t.handle(request({ ...GOOD, id: uuid(710) })))).status;
    t.state.known = "ok";
    out[`knownRetry:${mode}`] = (await look(await t.handle(request(CHANGE)))).status;
    out[`knownFetches:${mode}`] = t.state.knownFetches.length;
  }
  // a vineyard listed since the function was deployed: taken, with no new
  // deploy; only the list's public fields reach the issue
  t = fresh();
  const list = JSON.parse(readFileSync(KNOWN_FILE, "utf8"));
  list["newly-listed-vineyard"] = {
    name: "Newly Listed Vineyard", category: "hsd", year: 2021, varieties: ["Tannat"],
    blocks: GOOD.blocks, contact: "grower@example.com",
  };
  t.state.knownData = list;
  out.knownNew = await look(await t.handle(request({ ...CHANGE, id: uuid(720), changes: "newly-listed-vineyard" })));
  out.knownNewIssue = t.state.issues[0];
  out.knownUnknown = await look(await t.handle(request({ ...CHANGE, id: uuid(721), changes: "no-such-vineyard" })));
  // KNOWN_VINEYARDS_URL, for the tests; an address that is not https is ignored
  t = fresh();
  t.env.KNOWN_VINEYARDS_URL = "https://known.example.invalid/known.json";
  out.knownEnv = await look(await t.handle(request(CHANGE)));
  out.knownEnvHealth = (await look(await t.handle(request(null, { method: "GET", path: "/health" })))).body;
  out.knownEnvUrls = t.state.knownFetches.map((f) => f.url);
  t = fresh();
  t.env.KNOWN_VINEYARDS_URL = "http://known.example.invalid/known.json";
  out.knownEnvHttp = (await look(await t.handle(request(CHANGE)))).status;
  out.knownEnvHttpUrls = t.state.knownFetches.map((f) => f.url);
  return out;
}

// --- the browser tests' server ------------------------------------------------

export async function serve(port, bundlePath) {
  const fn = await import(pathToFileURL(bundlePath));
  let s = standIn();
  let handle = fn.makeHandler(s.deps);
  s.state.now = new Date();
  const server = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const body = Buffer.concat(chunks);
    const origin = req.headers.origin || "";
    const cors = { "Access-Control-Allow-Origin": origin || "*", Vary: "Origin" };
    if (req.url.startsWith("/standin")) {
      if (req.method === "POST") {
        const set = JSON.parse(body.toString() || "{}");
        if (set.reset) {
          s = standIn();
          s.state.now = new Date();
          handle = fn.makeHandler(s.deps);
        }
        Object.assign(s.state, set.state || {});
        Object.assign(s.env, set.env || {}); // after a reset: its env is fresh
      }
      res.writeHead(200, { "Content-Type": "application/json", ...cors });
      res.end(JSON.stringify({ rows: s.state.rows, issues: s.state.issues, logs: s.state.logs }));
      return;
    }
    if (s.state.github === "unreachable") {
      req.socket.destroy();
      return;
    }
    // the local page's requests pass as the site's; any other origin as it is
    const local = /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
    const headers = { ...req.headers, origin: local ? SITE : origin };
    // a gateway that sets the sender's address, as Cloudflare does in front
    // of Supabase: a forged one never gets through
    headers["cf-connecting-ip"] = req.socket.remoteAddress || "";
    delete headers.host;
    const answer = await handle(new Request(URL_BASE + req.url.replace(/^\/vineyard-submit/, ""), {
      method: req.method,
      headers,
      body: ["GET", "HEAD", "OPTIONS"].includes(req.method) ? undefined : body,
    }));
    const out = Object.fromEntries(answer.headers.entries());
    if (local && out["access-control-allow-origin"]) out["access-control-allow-origin"] = origin;
    res.writeHead(answer.status, out);
    res.end(Buffer.from(await answer.arrayBuffer()));
  });
  server.listen(port, "127.0.0.1", () => process.stdout.write(`stand-in on http://127.0.0.1:${port}\n`));
}

const [mode, ...rest] = process.argv.slice(2);
if (mode === "cases") {
  process.stdout.write(JSON.stringify(await cases(rest[0])));
} else if (mode === "serve") {
  await serve(Number(rest[0]), rest[1]);
}
