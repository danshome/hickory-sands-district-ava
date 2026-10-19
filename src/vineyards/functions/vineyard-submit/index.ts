// The vineyard form's one server: the Supabase Edge Function "vineyard-submit"
// in the project "Hickory Sands District AVA" (ref yayebhncbagmebwgmezd),
// beside vote-api, which it leaves alone. Dan deploys it from the Supabase
// dashboard as one file that src/vineyards/bundle_function.py makes from this
// one, the site's rules (docs/assets/vineyard-blocks.js) and TTB's proposed
// Llano Uplift AVA as the site publishes it
// (docs/assets/aquifer/llano-uplift.geojson); src/vineyards/SETUP.md says how.
//
// POST /vineyard-submit, JSON from https://hickorysandsdistrictava.org only.
// In order:
//   1. CORS allow-list of one origin, POST, application/json, at most 64 KB;
//   2. Cloudflare Turnstile (siteverify): a success, for the site's hostname
//      and the form's action, never a test key's;
//   3. the checks: vineyard-blocks.js, the same module the page runs (held to
//      src/vineyards/submission.py's answers by the tests), then the private
//      words; a filled trap field is answered as sent, and nothing is kept;
//   4. hsd_vineyard_reserve() (hsd_vineyard_contacts.sql), one transaction:
//      the same submission sent again gets its first answer; else the limits
//      per connection and per day; else one row with the contact;
//   5. one public issue in danshome/hickory-sands-district-ava, the fixed
//      layout, public fields only, label vineyard-submission, posted as the
//      GitHub App "HSD vineyard form" (a bot, never Dan); then the row gets the
//      issue's number. If GitHub fails, the row is freed and the page offers
//      to try again or to email.
// Answers {ok: true, reference: <issue number>}.
//
// POST /vineyard-submit/github: the App's webhook (Issues events), signed with
// GITHUB_WEBHOOK_SECRET. A submission's issue closed (or deleted) sets its
// row's closed_at; reopened clears it. Every send and every webhook delivery
// then deletes the rows closed more than a year ago (KEEP_DAYS): a contact is
// kept for a year after its issue is closed, and no longer.
//
// GET /vineyard-submit/health: {ready, missing: [secret names]} and which
// address headers a request carries, never a value: for Dan's check
// (src/vineyards/check_function.py).
//
// Logs status codes and issue numbers, never a body, a contact or a secret.
// Every outside call has a timeout.
//
// Secrets (Dan sets them in the dashboard; never in the repository):
//   GITHUB_APP_ID, GITHUB_APP_INSTALLATION_ID   the form's App
//   GITHUB_APP_PRIVATE_KEY   the App's private key, as GitHub gives it (the
//                            whole file, or its lines run together)
//   GITHUB_WEBHOOK_SECRET    the App's webhook secret
//   TURNSTILE_SECRET         the Turnstile widget's secret key
//   IP_SALT                  random text: the IP is kept only as an HMAC
//   PRIVATE_WORDS            optional: words never to publish, one per line
// Settings: JWT verification off (a public form, like vote-api).
import * as rules from "./vineyard-blocks.js";
import llanoUplift from "./llano-uplift.json" with { type: "json" };

export const SITE = "https://hickorysandsdistrictava.org";
const HOSTNAMES = ["hickorysandsdistrictava.org"];
const ACTION = "vineyard-submit";
export const OWNER = "danshome";
export const REPO = "hickory-sands-district-ava";
export const LABEL = "vineyard-submission";
export const BOT = "hsd-vineyard-form[bot]";
export const PER_IP_PER_DAY = 5;
export const PER_DAY = 30;
export const KEEP_DAYS = 365;
const WAIT_MS = 8000;
const WEBHOOK_BYTES = 1048576;
const TABLE = "hsd_vineyard_contacts";
export const SECRETS = [
  "GITHUB_APP_ID",
  "GITHUB_APP_INSTALLATION_ID",
  "GITHUB_APP_PRIVATE_KEY",
  "GITHUB_WEBHOOK_SECRET",
  "TURNSTILE_SECRET",
  "IP_SALT",
];

// What the function needs from its runtime: Deno's in Supabase, stand-ins in
// the tests (tests/test_vineyard_function.py).
export interface Deps {
  env(name: string): string;
  fetch(url: string, init?: RequestInit): Promise<Response>;
  now(): Date;
  log(...args: unknown[]): void;
}

type Json = Record<string, unknown>;

const llano = rules.makeArea(llanoUplift);
const enc = new TextEncoder();

const hex = (bytes: Uint8Array) => [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
const b64url = (bytes: Uint8Array) => {
  let text = "";
  for (const b of bytes) text += String.fromCharCode(b);
  return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};

function derLength(n: number): number[] {
  if (n < 128) return [n];
  const out: number[] = [];
  for (let k = n; k > 0; k >>= 8) out.unshift(k & 255);
  return [0x80 | out.length, ...out];
}

// The App's key as PKCS#8 DER, whatever GitHub's file gave: the PEM's text
// with or without its line breaks; its PKCS#1 body (what GitHub hands out) is
// wrapped as PKCS#8, which WebCrypto reads.
export function appKey(text: string): Uint8Array {
  const body = text.replace(/-----[A-Z ]+-----/g, "").replace(/\\n/g, "").replace(/[^A-Za-z0-9+/=]/g, "");
  const der = Uint8Array.from(atob(body), (c) => c.charCodeAt(0));
  let i = 1;
  const first = der[i++];
  if (first & 0x80) i += first & 0x7f;
  if (der[0] !== 0x30 || der[i] !== 0x02) throw new Error("the App's key is not an RSA key");
  i += 2 + der[i + 1];
  if (der[i] === 0x30) return der; // PKCS#8 already
  const rsa = [0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01, 0x01, 0x05, 0x00];
  const inner = [0x02, 0x01, 0x00, ...rsa, 0x04, ...derLength(der.length), ...der];
  return new Uint8Array([0x30, ...derLength(inner.length), ...inner]);
}

// The same bytes, compared in constant time.
function same(a: string, b: string): boolean {
  const x = enc.encode(a);
  const y = enc.encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}

async function hmacHex(secret: string, data: Uint8Array): Promise<string> {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(new Uint8Array(await crypto.subtle.sign("HMAC", key, data)));
}

// The sender's address, for the limits only: Cloudflare's header, else the
// gateway's, else the first of X-Forwarded-For. Kept only as an HMAC.
export function clientIp(req: Request): string {
  const h = req.headers;
  return (h.get("cf-connecting-ip") || h.get("x-real-ip") || (h.get("x-forwarded-for") || "").split(",")[0]).trim();
}

export function makeHandler(deps: Deps): (req: Request) => Promise<Response> {
  const env = (k: string) => (deps.env(k) || "").trim();
  const serviceKey = () => {
    const legacy = env("SUPABASE_SERVICE_ROLE_KEY");
    if (legacy) return legacy;
    try {
      return JSON.parse(deps.env("SUPABASE_SECRET_KEYS") || "{}").default || "";
    } catch {
      return "";
    }
  };
  const missing = () => [...SECRETS.filter((k) => !env(k)), ...(env("SUPABASE_URL") && serviceKey() ? [] : ["SUPABASE_URL"])];
  const privateWords = () => (deps.env("PRIVATE_WORDS") || "").split("\n")
    .map((w) => w.trim().toLowerCase()).filter((w) => w && !w.startsWith("#"));

  const headers = (origin: string | null): Record<string, string> => {
    const h: Record<string, string> = { "Content-Type": "application/json", "Cache-Control": "no-store", Vary: "Origin" };
    if (origin === SITE) h["Access-Control-Allow-Origin"] = origin;
    return h;
  };
  const answer = (status: number, body: unknown, origin: string | null = null) =>
    new Response(JSON.stringify(body), { status, headers: headers(origin) });
  const timed = (url: string, init: RequestInit) => deps.fetch(url, { ...init, signal: AbortSignal.timeout(WAIT_MS) });

  // The table, through Supabase's REST API with the service role (row level
  // security keeps every other role out).
  async function db(method: string, path: string, body?: unknown): Promise<unknown> {
    const key = serviceKey();
    const h: Record<string, string> = { apikey: key, "Content-Type": "application/json", Prefer: "return=representation" };
    if (key.startsWith("eyJ")) h.Authorization = `Bearer ${key}`;
    const r = await timed(`${env("SUPABASE_URL")}/rest/v1/${path}`, {
      method,
      headers: h,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`database ${r.status}`);
    const text = await r.text();
    return text ? JSON.parse(text) : null;
  }

  // Rows whose issue was closed more than KEEP_DAYS ago go; a failure here
  // never fails the request.
  async function forget(): Promise<void> {
    const before = new Date(deps.now().getTime() - KEEP_DAYS * 86400000).toISOString();
    try {
      await db("DELETE", `${TABLE}?closed_at=lt.${encodeURIComponent(before)}`);
    } catch (error) {
      deps.log("vineyard contacts: the yearly sweep failed", String(error).slice(0, 80));
    }
  }

  // A one-hour token for the App's one installation: Issues on this
  // repository only, whatever else the App may hold.
  async function appToken(): Promise<string> {
    const key = await crypto.subtle.importKey(
      "pkcs8", appKey(env("GITHUB_APP_PRIVATE_KEY")), { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["sign"],
    );
    const now = Math.floor(deps.now().getTime() / 1000);
    const head = b64url(enc.encode(JSON.stringify({ alg: "RS256", typ: "JWT" })));
    const claims = b64url(enc.encode(JSON.stringify({ iat: now - 60, exp: now + 540, iss: env("GITHUB_APP_ID") })));
    const sig = new Uint8Array(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, enc.encode(`${head}.${claims}`)));
    const r = await timed(`https://api.github.com/app/installations/${env("GITHUB_APP_INSTALLATION_ID")}/access_tokens`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${head}.${claims}.${b64url(sig)}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hsd-vineyard-submit",
      },
      body: JSON.stringify({ repositories: [REPO], permissions: { issues: "write" } }),
    });
    if (!r.ok) throw new Error(`app token ${r.status}`);
    return (await r.json()).token;
  }

  async function github(token: string, method: string, path: string, body: unknown): Promise<Json> {
    const r = await timed(`https://api.github.com/repos/${OWNER}/${REPO}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hsd-vineyard-submit",
      },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`github ${r.status}`);
    return await r.json();
  }

  async function human(token: unknown, ip: string): Promise<boolean> {
    if (typeof token !== "string" || !token || token.length > 2048) return false;
    const form = new URLSearchParams({ secret: env("TURNSTILE_SECRET"), response: token });
    if (ip) form.set("remoteip", ip);
    const r = await timed("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form });
    const v = await r.json().catch(() => ({}));
    return v.success === true && !v.metadata?.result_with_testing_key && HOSTNAMES.includes(v.hostname) && v.action === ACTION;
  }

  async function submit(req: Request, origin: string | null): Promise<Response> {
    if (origin !== SITE) return answer(403, { error: "origin" }, origin);
    if (!(req.headers.get("Content-Type") || "").startsWith("application/json")) {
      return answer(415, { error: "JSON only" }, origin);
    }
    const length = Number(req.headers.get("Content-Length") || "0");
    if (!(length > 0 && length <= rules.LIMITS.bodyBytes)) return answer(413, { error: "too large" }, origin);
    const bytes = new Uint8Array(await req.arrayBuffer());
    if (bytes.length > rules.LIMITS.bodyBytes) return answer(413, { error: "too large" }, origin);
    if (missing().length) return answer(503, { error: "not-ready" }, origin);

    let raw: Json;
    try {
      raw = rules.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new rules.Invalid("shape");
    } catch {
      return answer(400, { error: "unreadable" }, origin);
    }
    const ip = clientIp(req);
    const token = raw.turnstile;
    delete raw.turnstile;
    try {
      if (!(await human(token, ip))) return answer(403, { error: "turnstile" }, origin);
    } catch {
      return answer(503, { error: "turnstile-unreachable" }, origin);
    }

    let checked;
    try {
      checked = rules.check(raw, { llano, year: deps.now().getUTCFullYear() });
    } catch (error) {
      if (error instanceof rules.Invalid && error.message === "trap") {
        return answer(200, { ok: true, reference: null }, origin);
      }
      return answer(400, { error: "unreadable" }, origin);
    }
    const sub = checked.submission;
    const publicText = [sub.vineyard.name, ...sub.vineyard.varieties].join(" ").toLowerCase();
    if (privateWords().some((w) => publicText.includes(w))) checked.errors.push(["name", rules.NAME_PROBLEMS.personal]);
    if (checked.errors.length) {
      return answer(422, { errors: checked.errors.map(([field, message]: [string, string]) => ({ field, message })) }, origin);
    }

    let reserved: Json;
    try {
      const rows = await db("POST", "rpc/hsd_vineyard_reserve", {
        p_submission: sub.id,
        p_ip_hash: (await hmacHex(env("IP_SALT"), enc.encode(ip))).slice(0, 32),
        p_name: sub.contact.name,
        p_email: sub.contact.email || null,
        p_phone: sub.contact.phone || null,
        p_per_ip: PER_IP_PER_DAY,
        p_per_day: PER_DAY,
      });
      reserved = (Array.isArray(rows) ? rows[0] : rows) as Json;
      if (!reserved || typeof reserved.verdict !== "string") throw new Error("no verdict");
    } catch (error) {
      deps.log("vineyard submission: the table failed", String(error).slice(0, 80));
      return answer(503, { error: "store" }, origin);
    }
    if (reserved.verdict === "again") {
      return reserved.issue_number
        ? answer(200, { ok: true, reference: reserved.issue_number, again: true }, origin)
        : answer(409, { error: "in-progress" }, origin);
    }
    if (reserved.verdict !== "new") return answer(429, { error: reserved.verdict }, origin);

    try {
      const token = await appToken();
      const issue = await github(token, "POST", "/issues", {
        title: rules.issueTitle(sub),
        body: rules.issueBody(sub, deps.now().toISOString()),
        labels: [LABEL],
      });
      const number = issue.number as number;
      const labels = (issue.labels as Json[] | undefined) || [];
      if (!labels.some((l) => l.name === LABEL)) {
        // GitHub drops a label it will not set on a new issue: add it again,
        // so the repository's check runs.
        await github(token, "POST", `/issues/${number}/labels`, { labels: [LABEL] });
        deps.log("vineyard submission: label added after", number);
      }
      try {
        await db("PATCH", `${TABLE}?id=eq.${encodeURIComponent(String(reserved.id))}`, { issue_number: number });
      } catch (error) {
        deps.log("vineyard submission: the issue number was not stored", number, String(error).slice(0, 80));
      }
      deps.log("vineyard submission", number);
      await forget();
      return answer(200, { ok: true, reference: number }, origin);
    } catch (error) {
      // the issue was not made (or not known to be): free the row, so a
      // retry starts again
      deps.log("vineyard submission failed", String(error).slice(0, 80));
      try {
        await db("DELETE", `${TABLE}?id=eq.${encodeURIComponent(String(reserved.id))}&issue_number=is.null`);
      } catch (freeing) {
        deps.log("vineyard submission: the row was not freed", String(freeing).slice(0, 80));
      }
      return answer(502, { error: "github" }, origin);
    }
  }

  async function webhook(req: Request): Promise<Response> {
    const length = Number(req.headers.get("Content-Length") || "0");
    if (length > WEBHOOK_BYTES) return answer(413, { error: "too large" });
    const bytes = new Uint8Array(await req.arrayBuffer());
    if (bytes.length > WEBHOOK_BYTES) return answer(413, { error: "too large" });
    const secret = env("GITHUB_WEBHOOK_SECRET");
    const signed = req.headers.get("X-Hub-Signature-256") || "";
    if (!secret || !same(signed, `sha256=${await hmacHex(secret, bytes)}`)) {
      return answer(401, { error: "signature" });
    }
    const event = req.headers.get("X-GitHub-Event");
    if (event === "ping") return answer(200, { ok: true });
    if (event !== "issues") return answer(202, { ok: true, ignored: event });
    let payload: Json;
    try {
      payload = JSON.parse(new TextDecoder().decode(bytes));
    } catch {
      return answer(400, { error: "unreadable" });
    }
    const issue = (payload.issue || {}) as Json;
    const user = (issue.user || {}) as Json;
    const action = payload.action;
    const number = issue.number;
    if (user.login !== BOT || !Number.isInteger(number) || !["closed", "reopened", "deleted"].includes(String(action))) {
      await forget();
      return answer(202, { ok: true, ignored: String(action) });
    }
    const at = typeof issue.closed_at === "string" && !Number.isNaN(Date.parse(issue.closed_at))
      ? new Date(issue.closed_at).toISOString()
      : deps.now().toISOString();
    try {
      await db("PATCH", `${TABLE}?issue_number=eq.${number}`, { closed_at: action === "reopened" ? null : at });
    } catch (error) {
      deps.log("vineyard webhook: the table failed", number, String(error).slice(0, 80));
      return answer(503, { error: "store" });
    }
    deps.log("vineyard webhook", action, number);
    await forget();
    return answer(200, { ok: true });
  }

  return async (req: Request): Promise<Response> => {
    const path = new URL(req.url).pathname.replace(/\/+$/, "");
    const origin = req.headers.get("Origin");
    if (path.endsWith("/health")) {
      if (req.method !== "GET") return answer(405, { error: "GET only" });
      const h = req.headers;
      return answer(200, {
        ok: true,
        ready: missing().length === 0,
        missing: missing(),
        address_headers: ["cf-connecting-ip", "x-real-ip", "x-forwarded-for"].filter((n) => h.has(n)),
        forwarded_entries: (h.get("x-forwarded-for") || "").split(",").filter((s) => s.trim()).length,
      });
    }
    if (path.endsWith("/github")) {
      if (req.method !== "POST") return answer(405, { error: "POST only" });
      return await webhook(req);
    }
    if (req.method === "OPTIONS") {
      if (origin !== SITE) return new Response(null, { status: 403 });
      return new Response(null, {
        status: 204,
        headers: {
          ...headers(origin),
          "Access-Control-Allow-Methods": "POST",
          "Access-Control-Allow-Headers": "content-type",
          "Access-Control-Max-Age": "600",
        },
      });
    }
    if (req.method !== "POST") return answer(405, { error: "POST only" }, origin);
    return await submit(req, origin);
  };
}

// In Supabase: serve. (In node, under the tests, there is no Deno.)
interface DenoLike {
  serve(handler: (req: Request) => Promise<Response>): unknown;
  env: { get(name: string): string | undefined };
}
const deno = (globalThis as { Deno?: DenoLike }).Deno;
if (deno) {
  deno.serve(
    makeHandler({
      env: (k) => deno.env.get(k) ?? "",
      fetch: (url, init) => fetch(url, init),
      now: () => new Date(),
      log: (...args) => console.log(...args),
    }),
  );
}
