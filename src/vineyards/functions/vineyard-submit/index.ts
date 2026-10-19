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
//      and the form's action, never a test key's (Cloudflare failing answers
//      503, never a refusal);
//   3. the checks: vineyard-blocks.js, the same module the page runs (held to
//      src/vineyards/submission.py's answers by the tests), then the private
//      words; a filled trap field is answered as sent, and nothing is kept;
//   4. hsd_vineyard_reserve() (hsd_vineyard_contacts.sql), one transaction:
//      the same submission sent again gets its first answer (409 while it is
//      under way; taken up again after two minutes if it died); else the
//      limits per connection and per day; else one row with the contact;
//   5. one public issue in danshome/hickory-sands-district-ava, the fixed
//      layout, public fields only, label vineyard-submission, posted as the
//      GitHub App "HSD vineyard form" (a bot, never Dan), with a marker (an
//      HMAC of the submission's id) by which a retry finds it instead of
//      making a second; then the row is tied to the issue's number, and only
//      then is the sender told it is sent. GitHub refusing frees the row (502);
//      a lost answer keeps it (409); the row not tied answers 503.
// Answers {ok: true, reference: <issue number>}.
//
// POST /vineyard-submit/github: the App's webhook (Issues events), signed with
// GITHUB_WEBHOOK_SECRET. A submission's issue closed (or deleted) sets its
// row's closed_at; reopened clears it; no row for it answers 404, so it shows
// in the App's delivery log.
//
// POST /vineyard-submit/reconcile, by the daily Action vineyard-reconcile.yml,
// and on every webhook delivery, at most once every ten minutes: ties a row to
// the issue its marker names, records the closings, reopenings and deletions a
// failed delivery missed (GitHub never sends one again), and puts back a label
// GitHub dropped. Every send, delivery and reconciliation also sweeps: a row
// goes a year after its issue was closed (KEEP_DAYS), and a row never tied to
// an issue goes after UNLINKED_HOURS. A failure answers 500, and the Action
// reports it on an issue for Dan.
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
//   PRIVATE_WORDS_SILENT     optional, off: "1" holds a submission with a
//                            private word for the petitioners (a 200 with no
//                            reference, a row marked held, no issue) instead
//                            of refusing it with a 422 that names no word but
//                            lets a stranger probe the list
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
export const UNLINKED_HOURS = 24; // a row never tied to its issue
export const STALE_MS = 120000; // a send still under way (the SQL's two minutes)
export const RECONCILE_EVERY_S = 600;
const FIND_DAYS = 3; // how far back a retry looks for its issue
const PAGES = 10; // of 100 issues, when reconciling
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
    } catch (error) {
      deps.log("vineyard: SUPABASE_SECRET_KEYS could not be read", String(error).slice(0, 80));
      return "";
    }
  };
  const missing = () => [...SECRETS.filter((k) => !env(k)), ...(env("SUPABASE_URL") && serviceKey() ? [] : ["SUPABASE_URL"])];
  const privateWords = () => (deps.env("PRIVATE_WORDS") || "").split("\n")
    .map((w) => w.trim().toLowerCase()).filter((w) => w && !w.startsWith("#"));
  const silent = () => env("PRIVATE_WORDS_SILENT") === "1";
  const now = () => deps.now().getTime();
  const iso = (ms: number) => new Date(ms).toISOString();
  const short = (error: unknown) => String(error).slice(0, 80);

  const headers = (origin: string | null): Record<string, string> => {
    const h: Record<string, string> = { "Content-Type": "application/json", "Cache-Control": "no-store", Vary: "Origin" };
    if (origin === SITE) h["Access-Control-Allow-Origin"] = origin;
    return h;
  };
  const answer = (status: number, body: unknown, origin: string | null = null) =>
    new Response(JSON.stringify(body), { status, headers: headers(origin) });
  const timed = (url: string, init: RequestInit) => deps.fetch(url, { ...init, signal: AbortSignal.timeout(WAIT_MS) });

  // The table, through Supabase's REST API with the service role (row level
  // security keeps every other role out). Throws on any error.
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
  // The rows a PATCH changed: none is a failure the caller reports.
  async function patched(path: string, body: unknown): Promise<number> {
    const rows = await db("PATCH", path, body);
    return Array.isArray(rows) ? rows.length : 0;
  }

  // The submission's marker in its issue: an HMAC of its id, so a retry finds
  // the issue a lost answer made, and nothing in the issue tells the id.
  const marker = async (id: string) => (await hmacHex(env("IP_SALT"), enc.encode(`ref:${id}`))).slice(0, 24);
  const markerLine = (ref: string) => `<!-- hsd-vineyard-ref: ${ref} -->`;
  const markerOf = (body: unknown) => /<!-- hsd-vineyard-ref: ([0-9a-f]{24}) -->/.exec(String(body ?? ""))?.[1] ?? null;

  // A one-hour token for the App's one installation: Issues on this
  // repository only, whatever else the App may hold.
  async function appToken(): Promise<string> {
    const key = await crypto.subtle.importKey(
      "pkcs8", appKey(env("GITHUB_APP_PRIVATE_KEY")), { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["sign"],
    );
    const at = Math.floor(now() / 1000);
    const head = b64url(enc.encode(JSON.stringify({ alg: "RS256", typ: "JWT" })));
    const claims = b64url(enc.encode(JSON.stringify({ iat: at - 60, exp: at + 540, iss: env("GITHUB_APP_ID") })));
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

  // One call to the repository's API. Throws when no answer came (a lost
  // answer: the call may have done its work); answers the status otherwise.
  async function github(token: string, method: string, path: string, body?: unknown): Promise<{ status: number; data: unknown }> {
    const r = await timed(`https://api.github.com/repos/${OWNER}/${REPO}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hsd-vineyard-submit",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await r.text();
    let data: unknown = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = null; // not JSON: the status says what happened
    }
    return { status: r.status, data };
  }

  // The form App's issues made or changed since a time (not pull requests),
  // newest first, up to PAGES pages; and whether that is all of them.
  async function botIssues(token: string, since: number): Promise<{ issues: Json[]; whole: boolean }> {
    const issues: Json[] = [];
    for (let page = 1; page <= PAGES; page++) {
      const q = new URLSearchParams({ creator: BOT, state: "all", since: iso(since), per_page: "100", page: String(page) });
      const { status, data } = await github(token, "GET", `/issues?${q}`);
      if (status !== 200 || !Array.isArray(data)) throw new Error(`issues ${status}`);
      issues.push(...(data as Json[]).filter((i) => !("pull_request" in i)));
      if (data.length < 100) return { issues, whole: true };
    }
    return { issues, whole: false };
  }

  const labelled = (issue: Json) => ((issue.labels as Json[] | undefined) || []).some((l) => l.name === LABEL);
  async function addLabel(token: string, number: number): Promise<boolean> {
    try {
      const { status } = await github(token, "POST", `/issues/${number}/labels`, { labels: [LABEL] });
      if (status === 200) return true;
      deps.log("vineyard: the label was not added", number, status);
    } catch (error) {
      deps.log("vineyard: the label was not added", number, short(error));
    }
    return false;
  }

  // Rows whose issue was closed more than KEEP_DAYS ago go; rows that never
  // got their issue (a send that died between GitHub and the table, and that
  // the reconciliation could not tie to an issue) UNLINKED_HOURS on; a held
  // row KEEP_DAYS after it came. Answers whether it worked; the
  // reconciliation reports a failure.
  async function sweep(): Promise<boolean> {
    const year = encodeURIComponent(iso(now() - KEEP_DAYS * 86400000));
    const unlinked = encodeURIComponent(iso(now() - UNLINKED_HOURS * 3600000));
    try {
      await db("DELETE", `${TABLE}?closed_at=lt.${year}`);
      await db("DELETE", `${TABLE}?issue_number=is.null&held=is.null&created_at=lt.${unlinked}`);
      await db("DELETE", `${TABLE}?held=not.is.null&created_at=lt.${year}`);
      return true;
    } catch (error) {
      deps.log("vineyard contacts: the sweep failed", short(error));
      return false;
    }
  }

  // Puts the table right against GitHub, at most once every RECONCILE_EVERY_S
  // (hsd_vineyard_tick()): a row whose send died before it was tied to its
  // issue is tied by the issue's marker; a closing, reopening or deletion the
  // webhook missed (GitHub does not send a failed delivery again) is recorded;
  // an issue that lost its label gets it back. Throws on a failure.
  async function reconcile(): Promise<Json> {
    const out = { ran: false, linked: 0, closed: 0, reopened: 0, labelled: 0 };
    const ticked = await db("POST", "rpc/hsd_vineyard_tick", { p_name: "reconcile", p_every_seconds: RECONCILE_EVERY_S });
    if (ticked !== true) return out;
    out.ran = true;
    const rows = ((await db("GET", `${TABLE}?select=id,submission_id,issue_number,created_at,closed_at,held`)) as Json[])
      .filter((r) => r.held === null); // a held row has no issue, by design
    const token = await appToken();
    const oldest = rows.reduce((t, r) => Math.min(t, Date.parse(String(r.created_at))), now());
    const { issues, whole } = await botIssues(token, oldest - 86400000);
    const byNumber = new Map(issues.map((i) => [i.number, i]));
    const byMarker = new Map(issues.map((i) => [markerOf(i.body), i]));
    for (const row of rows) {
      if (row.issue_number === null) {
        if (now() - Date.parse(String(row.created_at)) < STALE_MS) continue; // a send under way
        const found = byMarker.get(await marker(String(row.submission_id)));
        if (!found) continue; // the sweep expires it
        if (!(await patched(`${TABLE}?id=eq.${encodeURIComponent(String(row.id))}&issue_number=is.null`, { issue_number: found.number }))) {
          throw new Error("a row could not be tied to its issue");
        }
        row.issue_number = found.number;
        out.linked++;
      }
      const issue = byNumber.get(row.issue_number);
      if (!issue && !whole) continue; // not in the pages read: unknown
      const closedAt = !issue ? iso(now()) : issue.state === "closed" ? String(issue.closed_at || iso(now())) : null;
      if (closedAt && row.closed_at === null) {
        await patched(`${TABLE}?id=eq.${encodeURIComponent(String(row.id))}`, { closed_at: closedAt });
        out.closed++;
      } else if (!closedAt && row.closed_at !== null) {
        await patched(`${TABLE}?id=eq.${encodeURIComponent(String(row.id))}`, { closed_at: null });
        out.reopened++;
      }
    }
    for (const issue of issues) {
      if (issue.state === "open" && !labelled(issue) && (await addLabel(token, Number(issue.number)))) out.labelled++;
    }
    return out;
  }

  async function human(token: unknown, ip: string): Promise<boolean> {
    if (typeof token !== "string" || !token || token.length > 2048) return false;
    const form = new URLSearchParams({ secret: env("TURNSTILE_SECRET"), response: token });
    if (ip) form.set("remoteip", ip);
    const r = await timed("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form });
    // Cloudflare failing (an error status, an answer that is not JSON) is not
    // the sender's fault: it throws, and the page offers to try again.
    if (!r.ok) throw new Error(`siteverify ${r.status}`);
    const v = await r.json();
    return v.success === true && !v.metadata?.result_with_testing_key && HOSTNAMES.includes(v.hostname) && v.action === ACTION;
  }

  // Frees a row whose issue is known not to exist, so a retry starts again.
  async function free(id: unknown): Promise<void> {
    try {
      await db("DELETE", `${TABLE}?id=eq.${encodeURIComponent(String(id))}&issue_number=is.null`);
    } catch (error) {
      deps.log("vineyard submission: the row was not freed (the sweep expires it)", short(error));
    }
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
      return answer(400, { error: "unreadable" }, origin); // the sender's own fault: nothing to log
    }
    const ip = clientIp(req);
    const token = raw.turnstile;
    delete raw.turnstile;
    try {
      if (!(await human(token, ip))) return answer(403, { error: "turnstile" }, origin);
    } catch (error) {
      deps.log("vineyard submission: Turnstile did not answer", short(error));
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
    const held = privateWords().some((w) => publicText.includes(w));
    if (held && !silent()) checked.errors.push(["name", rules.NAME_PROBLEMS.personal]);
    if (checked.errors.length) {
      return answer(422, { errors: checked.errors.map(([field, message]: [string, string]) => ({ field, message })) }, origin);
    }

    // 4. the row: a retry, the limits, the contact (hsd_vineyard_contacts.sql)
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
      deps.log("vineyard submission: the table failed", short(error));
      return answer(503, { error: "store" }, origin);
    }
    if (reserved.verdict === "held") return answer(200, { ok: true, reference: null }, origin);
    if (reserved.verdict === "again") {
      return reserved.issue_number
        ? answer(200, { ok: true, reference: reserved.issue_number, again: true }, origin)
        : answer(409, { error: "in-progress" }, origin);
    }
    if (reserved.verdict !== "new") return answer(429, { error: reserved.verdict }, origin);
    const row = `${TABLE}?id=eq.${encodeURIComponent(String(reserved.id))}`;
    if (held) {
      // PRIVATE_WORDS_SILENT: kept for the petitioners, never posted, and the
      // sender is thanked as for any other
      try {
        if (!(await patched(row, { held: "private-word" }))) throw new Error("no row");
      } catch (error) {
        deps.log("vineyard submission: the table failed", short(error));
        return answer(503, { error: "store" }, origin);
      }
      deps.log("vineyard submission held for the petitioners");
      await sweep();
      return answer(200, { ok: true, reference: null }, origin);
    }

    // 5. the issue, once: a retry finds the one a lost answer made by its marker
    let app: string;
    let ref: string;
    let issue: Json | undefined;
    try {
      app = await appToken();
      ref = await marker(sub.id);
      issue = (await botIssues(app, now() - FIND_DAYS * 86400000)).issues.find((i) => markerOf(i.body) === ref);
    } catch (error) {
      deps.log("vineyard submission: GitHub could not be asked", short(error));
      await free(reserved.id);
      return answer(502, { error: "github" }, origin);
    }
    if (!issue) {
      let made;
      try {
        made = await github(app, "POST", "/issues", {
          title: rules.issueTitle(sub),
          body: `${rules.issueBody(sub, deps.now().toISOString())}${markerLine(ref)}\n`,
          labels: [LABEL],
        });
      } catch (error) {
        // No answer: the issue may have been made. The row is kept; a retry
        // after two minutes finds the issue by its marker, or makes it.
        deps.log("vineyard submission: GitHub's answer was lost", short(error));
        return answer(409, { error: "in-progress" }, origin);
      }
      if (made.status !== 201 || !made.data) {
        deps.log("vineyard submission: GitHub refused the issue", made.status);
        await free(reserved.id);
        return answer(502, { error: "github" }, origin);
      }
      issue = made.data as Json;
    }
    const number = Number(issue.number);

    // The row is tied to its issue before anything is reported: until it is,
    // the sender is told it is not sent, and a retry ties it.
    try {
      if (!(await patched(`${row}&issue_number=is.null`, { issue_number: number }))) throw new Error("no row");
    } catch (error) {
      deps.log("vineyard submission: issue made, its row not tied to it", number, short(error));
      return answer(503, { error: "store" }, origin);
    }
    // The label, last: if GitHub drops it, the issue and its row stand, and
    // the reconciliation adds it.
    if (!labelled(issue)) await addLabel(app, number);
    deps.log("vineyard submission", number);
    await sweep();
    return answer(200, { ok: true, reference: number }, origin);
  }

  async function webhook(req: Request): Promise<Response> {
    const length = Number(req.headers.get("Content-Length") || "0");
    if (length > WEBHOOK_BYTES) return answer(413, { error: "too large" });
    const bytes = new Uint8Array(await req.arrayBuffer());
    if (bytes.length > WEBHOOK_BYTES) return answer(413, { error: "too large" });
    const secret = env("GITHUB_WEBHOOK_SECRET");
    const signed = req.headers.get("X-Hub-Signature-256") || "";
    if (!secret || !same(signed, `sha256=${await hmacHex(secret, bytes)}`)) {
      deps.log("vineyard webhook: a delivery without a good signature");
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
    if (user.login === BOT && Number.isInteger(number) && ["closed", "reopened", "deleted"].includes(String(action))) {
      const at = typeof issue.closed_at === "string" && !Number.isNaN(Date.parse(issue.closed_at))
        ? new Date(issue.closed_at).toISOString()
        : deps.now().toISOString();
      let changed: number;
      try {
        changed = await patched(`${TABLE}?issue_number=eq.${number}`, { closed_at: action === "reopened" ? null : at });
      } catch (error) {
        deps.log("vineyard webhook: the table failed", number, short(error));
        return answer(503, { error: "store" });
      }
      if (!changed) {
        // shown in the App's delivery log; the reconciliation ties it later
        deps.log("vineyard webhook: no row for the issue", number);
        return answer(404, { error: "no row", issue: number });
      }
      deps.log("vineyard webhook", action, number);
    }
    // Every delivery (one for every issue event in the repository) puts the
    // table right, at most once every RECONCILE_EVERY_S.
    const swept = await sweep();
    try {
      await reconcile();
    } catch (error) {
      deps.log("vineyard: the reconciliation failed", short(error));
    }
    return swept ? answer(200, { ok: true }) : answer(500, { error: "sweep" });
  }

  // POST /reconcile, by the daily Action (vineyard-reconcile.yml): the sweep
  // and the reconciliation; a failure answers 500, which the Action reports.
  async function check(): Promise<Response> {
    if (missing().length) return answer(503, { ok: false, failed: "not-ready", missing: missing() });
    if (!(await sweep())) return answer(500, { ok: false, failed: "sweep" });
    try {
      return answer(200, { ok: true, ...(await reconcile()) });
    } catch (error) {
      deps.log("vineyard: the reconciliation failed", short(error));
      return answer(500, { ok: false, failed: "reconcile", why: short(error) });
    }
  }

  return async (req: Request): Promise<Response> => {
    const path = new URL(req.url).pathname.replace(/\/+$/, "");
    const origin = req.headers.get("Origin");
    if (path.endsWith("/health")) {
      if (req.method !== "GET") return answer(405, { error: "GET only" });
      const h = req.headers;
      // address_digest: an HMAC of the address the limits would use, never
      // the address. check_function.py sends two forged addresses: the
      // digest must not follow them.
      return answer(200, {
        ok: true,
        ready: missing().length === 0,
        missing: missing(),
        address_headers: ["cf-connecting-ip", "x-real-ip", "x-forwarded-for"].filter((n) => h.has(n)),
        forwarded_entries: (h.get("x-forwarded-for") || "").split(",").filter((s) => s.trim()).length,
        address_digest: env("IP_SALT") ? (await hmacHex(env("IP_SALT"), enc.encode(`probe:${clientIp(req)}`))).slice(0, 8) : null,
      });
    }
    if (path.endsWith("/github")) {
      if (req.method !== "POST") return answer(405, { error: "POST only" });
      return await webhook(req);
    }
    if (path.endsWith("/reconcile")) {
      if (req.method !== "POST") return answer(405, { error: "POST only" });
      return await check();
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
