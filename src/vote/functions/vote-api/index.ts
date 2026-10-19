// The growers' logo vote's one server: the Supabase Edge Function "vote-api"
// in the project "Hickory Sands District AVA" (ref yayebhncbagmebwgmezd).
// The page is docs/logo-vote.html. Dan deploys it from the Supabase dashboard
// as one file that src/vote/bundle_function.py makes from this one and the
// page's own designs (docs/assets/logo-vote/designs.json); src/vote/SETUP.md
// says how. Its tables are as src/vote/functions/vote-api/hsd_vote_migration.sql
// leaves them.
//
// GET  /vote-api            the state, as JSON: likes and passes per design,
//                           the retired designs, the sent-in designs in the
//                           vote ({id, title, img}: never a name), the rule.
// GET  /vote-api/img/<uuid> a sent-in design's image, only while approved.
// POST /vote-api            a form (application/x-www-form-urlencoded):
//   register   a new voter id, signed with VOTE_ID_SECRET: after Cloudflare
//              Turnstile when VOTE_TURNSTILE_SECRET is set (token=), with no
//              check when it is not; at most NEW_VOTERS_PER_NETWORK_DAY new
//              ids per address per day ("limit"). carry=<Shopify-era id>
//              hands that id's votes to the new one, once. Answers
//              {voter, carried}.
//   vote       voter, id (a design the page knows: one of designs.json, or
//              an approved sent-in design), dir (1 or -1). At most
//              VOTERS_PER_DESIGN_PER_NETWORK_DAY voters per design per
//              address per day ("limit"); changing a vote does not count.
//   unvote     voter, id.
//   my_votes   voter: {votes: {<design id>: 1 | -1}}.
//   upload     data (base64 JPEG or PNG, 3 MB), title: waits for the
//              operator ("ok", or "full", "queue full", "slow down",
//              "too big", "bad data", "not an image").
//   A voter id this function did not sign answers "bad".
//   admin_*    with key=OPERATOR_KEY: admin_pending, admin_approve,
//              admin_retire (id, reason), admin_cull, admin_unretire,
//              admin_trash, admin_remove, admin_restore, admin_history.
//              Nothing is ever deleted: a retirement is a dated record
//              (unretire dates its end); trash and remove set the status
//              'removed', and restore puts back the status it had.
//
// Addresses are kept only as an HMAC with VOTE_IP_SALT. The browser may call
// it only from the site (CORS, and a POST with another Origin is refused);
// the operator's calls, from a terminal, send no Origin.
//
// Secrets (Dan sets them in the dashboard; never in the repository). Their
// names are the vote's own: a project's secrets are shared by all its
// functions, and the vineyard form's are IP_SALT and TURNSTILE_SECRET.
//   VOTE_ID_SECRET          random text: signs the voter ids
//   VOTE_IP_SALT            random text: the address is kept only as an HMAC
//   OPERATOR_KEY            the operator's key, for the admin_* actions
//   VOTE_TURNSTILE_SECRET   optional: the Turnstile widget's secret key;
//                           unset, there is no person check
// Settings: JWT verification off (a public page).
import designs from "./designs.json" with { type: "json" };

export const SITE_ORIGINS = ["https://hickorysandsdistrictava.org"];
const HOSTNAMES = ["hickorysandsdistrictava.org"];
export const ACTIVATION_UPVOTES = 50;
export const MIN_VOTES_TO_RETIRE = 25;
export const RETIRE_RATIO = 0.35;
export const VOTERS_PER_DESIGN_PER_NETWORK_DAY = 10;
export const NEW_VOTERS_PER_NETWORK_DAY = 5;
export const MAX_UPLOAD_BYTES = 3 * 1024 * 1024;
export const MAX_SUBMISSIONS = 200;
export const MAX_PENDING = 50;
export const MAX_UPLOADS_PER_IP_DAY = 5;
const MAX_BODY = 6 * 1024 * 1024;
const BUCKET = "hsd-submissions";
const PATH = "/functions/v1/vote-api";
const WAIT_MS = 8000;
export const SIGNED = /^v2-([0-9a-f]{24})-([0-9a-f]{32})$/;
const LEGACY = /^v[0-9a-z]{10,20}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const BUILT_IN = new Set((designs as { id: string }[]).map((d) => d.id));

// What the function needs from its runtime: Deno's in Supabase, stand-ins in
// the tests (tests/test_vote_function.py).
export interface Deps {
  env(name: string): string;
  fetch(url: string, init?: RequestInit): Promise<Response>;
  now(): Date;
  log(...args: unknown[]): void;
}

type Row = Record<string, unknown>;

const enc = new TextEncoder();
const hex = (bytes: Uint8Array) => [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");

// The same bytes, compared in constant time.
function same(a: string, b: string): boolean {
  const x = enc.encode(a);
  const y = enc.encode(b);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) diff |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return diff === 0;
}

async function hmacHex(secret: string, data: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
  ]);
  return hex(new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(data))));
}

// A title as typed, without control characters or a spreadsheet formula's
// lead; the page shows it as text, so ' and & stay.
export function clean(v: unknown): string {
  return String(v ?? "")
    .replace(/[\u0000-\u001f\u007f<>]/g, "")
    .replace(/^[\s=+\-@]+/, "")
    .trim()
    .slice(0, 60);
}

export function cleanId(v: unknown): string {
  return String(v ?? "").replace(/[^A-Za-z0-9\-_]/g, "").slice(0, 80);
}

function detectImageType(bytes: Uint8Array): string | null {
  if (bytes.length > 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return "image/jpeg";
  if (bytes.length > 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) {
    return "image/png";
  }
  return null;
}

// The sender's address, for the limits only: Cloudflare's header, else the
// gateway's, else the first of X-Forwarded-For. Kept only as an HMAC.
export function clientIp(req: Request): string {
  const h = req.headers;
  return (h.get("cf-connecting-ip") || h.get("x-real-ip") || (h.get("x-forwarded-for") || "").split(",")[0]).trim();
}

export function makeHandler(deps: Deps): (req: Request) => Promise<Response> {
  const env = (k: string) => deps.env(k) || "";

  function headers(origin: string | null): Record<string, string> {
    const h: Record<string, string> = { Vary: "Origin" };
    if (origin && SITE_ORIGINS.includes(origin)) h["Access-Control-Allow-Origin"] = origin;
    return h;
  }
  function text(s: string, status: number, origin: string | null): Response {
    return new Response(s, {
      status,
      headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store", ...headers(origin) },
    });
  }
  function json(body: unknown, status: number, origin: string | null): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...headers(origin) },
    });
  }

  async function timed(url: string, init: RequestInit): Promise<Response> {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), WAIT_MS);
    try {
      return await deps.fetch(url, { ...init, signal: ctl.signal });
    } finally {
      clearTimeout(timer);
    }
  }

  // The database, through its REST API with the service role.
  function auth(): Record<string, string> {
    const key = env("SUPABASE_SERVICE_ROLE_KEY");
    return { apikey: key, Authorization: `Bearer ${key}` };
  }
  async function db(method: string, path: string, body?: unknown, prefer = "return=representation"): Promise<Row[]> {
    const r = await timed(`${env("SUPABASE_URL")}/rest/v1/${path}`, {
      method,
      headers: { ...auth(), "Content-Type": "application/json", Prefer: prefer },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`database ${r.status}`);
    const t = await r.text();
    return t ? JSON.parse(t) : [];
  }
  async function count(path: string): Promise<number> {
    const r = await timed(`${env("SUPABASE_URL")}/rest/v1/${path}`, {
      method: "HEAD",
      headers: { ...auth(), Prefer: "count=exact" },
    });
    if (!r.ok) throw new Error(`database ${r.status}`);
    const n = Number((r.headers.get("Content-Range") || "").split("/")[1]);
    if (!Number.isFinite(n)) throw new Error("database count");
    return n;
  }
  async function rpc(name: string, args: Row): Promise<unknown> {
    const r = await timed(`${env("SUPABASE_URL")}/rest/v1/rpc/${name}`, {
      method: "POST",
      headers: { ...auth(), "Content-Type": "application/json" },
      body: JSON.stringify(args),
    });
    if (!r.ok) throw new Error(`database ${name} ${r.status}`);
    return await r.json();
  }
  function storage(path: string): string {
    return `${env("SUPABASE_URL")}/storage/v1/object/${BUCKET}/${encodeURIComponent(path)}`;
  }

  // Voter ids: v2-<24 hex random>-<32 hex HMAC-SHA256 of "v2-<random>">.
  async function issueVoter(): Promise<string> {
    const rand = hex(crypto.getRandomValues(new Uint8Array(12)));
    const body = `v2-${rand}`;
    return `${body}-${(await hmacHex(env("VOTE_ID_SECRET"), body)).slice(0, 32)}`;
  }
  async function signedOk(voter: string): Promise<boolean> {
    const m = SIGNED.exec(voter);
    if (!m || !env("VOTE_ID_SECRET")) return false;
    return same(m[2], (await hmacHex(env("VOTE_ID_SECRET"), `v2-${m[1]}`)).slice(0, 32));
  }
  async function ipHash(req: Request): Promise<string> {
    return await hmacHex(env("VOTE_IP_SALT"), `vote:${clientIp(req)}`);
  }
  function adminOk(key: unknown): boolean {
    const want = env("OPERATOR_KEY");
    return !!want && typeof key === "string" && key.length > 0 && same(key, want);
  }

  // Cloudflare Turnstile: true for a success for the site; false for a
  // refusal; throws when Cloudflare cannot be asked (never a refusal).
  async function personOk(token: string, ip: string): Promise<boolean> {
    if (!token) return false;
    const form = new URLSearchParams({ secret: env("VOTE_TURNSTILE_SECRET"), response: token });
    if (ip) form.set("remoteip", ip);
    const r = await timed("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form });
    if (!r.ok) throw new Error(`siteverify ${r.status}`);
    const a = await r.json();
    return a?.success === true && HOSTNAMES.includes(String(a.hostname)) && !a?.metadata?.result_with_testing_key;
  }

  async function tally() {
    const rows = (await rpc("hsd_vote_tally", {})) as { design_id: string; up: number; down: number }[];
    const up: Record<string, number> = {};
    const down: Record<string, number> = {};
    let totalUp = 0;
    for (const r of rows ?? []) {
      if (Number(r.up)) up[r.design_id] = Number(r.up);
      if (Number(r.down)) down[r.design_id] = Number(r.down);
      totalUp += Number(r.up) || 0;
    }
    return { up, down, totalUp };
  }

  async function state() {
    const t = await tally();
    const retired = await db("GET", "hsd_retired?select=design_id&restored_at=is.null");
    const subs = await db("GET", "hsd_submissions?select=id,title&status=eq.approved&order=created_at");
    const base = `${env("SUPABASE_URL")}${PATH}`;
    return {
      up: t.up,
      down: t.down,
      totalUp: t.totalUp,
      cullingActive: t.totalUp >= ACTIVATION_UPVOTES,
      retired: [...new Set(retired.map((r) => String(r.design_id)))],
      submissions: subs.map((s) => ({ id: `sub-${s.id}`, title: String(s.title ?? ""), img: `${base}/img/${s.id}` })),
      rule: {
        minVotes: MIN_VOTES_TO_RETIRE,
        retireRatio: RETIRE_RATIO,
        votersPerNetwork: VOTERS_PER_DESIGN_PER_NETWORK_DAY,
      },
    };
  }

  async function knownDesign(id: string): Promise<boolean> {
    if (BUILT_IN.has(id)) return true;
    const m = /^sub-(.+)$/.exec(id);
    if (!m || !UUID.test(m[1])) return false;
    return (await db("GET", `hsd_submissions?select=id&status=eq.approved&id=eq.${m[1]}`)).length === 1;
  }

  async function image(id: string): Promise<Response> {
    const none = text("not found", 404, null);
    if (!UUID.test(id)) return none;
    const rows = await db("GET", `hsd_submissions?select=storage_path,content_type,status&id=eq.${id}`);
    const row = rows[0];
    if (!row || row.status !== "approved") return none;
    const r = await timed(storage(String(row.storage_path)), { method: "GET", headers: auth() });
    if (!r.ok) return none;
    return new Response(await r.arrayBuffer(), {
      headers: {
        "Content-Type": row.content_type === "image/png" ? "image/png" : "image/jpeg",
        "Cache-Control": "public, max-age=300",
        "X-Content-Type-Options": "nosniff",
      },
    });
  }

  async function upload(p: Record<string, string>, req: Request, origin: string | null): Promise<Response> {
    if ((await count("hsd_submissions?select=id")) >= MAX_SUBMISSIONS) return text("full", 200, origin);
    if ((await count("hsd_submissions?select=id&status=eq.pending")) >= MAX_PENDING) {
      return text("queue full", 200, origin);
    }
    const ip = await ipHash(req);
    const dayAgo = new Date(deps.now().getTime() - 86400000).toISOString();
    if ((await count(`hsd_submissions?select=id&ip_hash=eq.${ip}&created_at=gte.${dayAgo}`)) >= MAX_UPLOADS_PER_IP_DAY) {
      return text("slow down", 200, origin);
    }
    if (p.data.length > 4500000) return text("too big", 200, origin);
    let bytes: Uint8Array;
    try {
      bytes = Uint8Array.from(atob(p.data), (c) => c.charCodeAt(0));
    } catch {
      return text("bad data", 200, origin);
    }
    if (bytes.length > MAX_UPLOAD_BYTES) return text("too big", 200, origin);
    const mime = detectImageType(bytes);
    if (!mime) return text("not an image", 200, origin);
    const id = crypto.randomUUID();
    const path = id + (mime === "image/png" ? ".png" : ".jpg");
    const put = await timed(storage(path), {
      method: "POST",
      headers: { ...auth(), "Content-Type": mime, "x-upsert": "false" },
      body: bytes,
    });
    if (!put.ok) return text("upload failed", 500, origin);
    await db(
      "POST",
      "hsd_submissions",
      { id, name: "", title: clean(p.title), storage_path: path, content_type: mime, status: "pending", ip_hash: ip },
      "return=minimal",
    );
    deps.log("vote: a design waits", id);
    return text("ok", 200, origin);
  }

  async function history(): Promise<unknown> {
    const t = await tally();
    const votes = (d: string) => ({ up: t.up[d] || 0, down: t.down[d] || 0 });
    const retired = await db("GET", "hsd_retired?select=id,design_id,retired_at,reason,restored_at&order=retired_at");
    const removed = await db(
      "GET",
      "hsd_submissions?select=id,title,status,status_before,removed_by,removed_at,restored_at" +
        "&removed_at=not.is.null&order=removed_at",
    );
    return {
      retired: retired.map((r) => ({ ...r, ...votes(String(r.design_id)) })),
      removed: removed.map((s) => ({
        fileId: s.id,
        design_id: `sub-${s.id}`,
        title: s.title,
        status: s.status,
        status_before: s.status_before,
        how: s.removed_by,
        removed_at: s.removed_at,
        restored_at: s.restored_at,
        ...votes(`sub-${s.id}`),
      })),
    };
  }

  async function admin(action: string, p: Record<string, string>, origin: string | null): Promise<Response> {
    const now = deps.now().toISOString();
    const fileId = UUID.test(p.id || "") ? p.id : "";
    const design = cleanId(p.id);
    switch (action) {
      case "admin_pending": {
        const rows = await db("GET", "hsd_submissions?select=id,title,created_at&status=eq.pending&order=created_at");
        return json(
          rows.map((r) => ({ title: r.title, fileId: r.id, when: r.created_at })),
          200,
          origin,
        );
      }
      case "admin_approve":
        if (!fileId) return text("bad id", 400, origin);
        await db("PATCH", `hsd_submissions?id=eq.${fileId}&status=eq.pending`, { status: "approved" });
        return text("ok", 200, origin);
      case "admin_cull": {
        const culled = (await rpc("hsd_vote_cull", { p_min: MIN_VOTES_TO_RETIRE, p_ratio: RETIRE_RATIO })) as string[];
        return json({ culled: culled ?? [] }, 200, origin);
      }
      case "admin_retire": {
        if (!design) return text("bad id", 400, origin);
        const live = await db("GET", `hsd_retired?select=id&design_id=eq.${design}&restored_at=is.null`);
        if (!live.length) {
          await db(
            "POST",
            "hsd_retired",
            { design_id: design, retired_at: now, reason: clean(p.reason) || "by the operator" },
            "return=minimal",
          );
        }
        return text("ok", 200, origin);
      }
      case "admin_unretire":
        if (!design) return text("bad id", 400, origin);
        await db("PATCH", `hsd_retired?design_id=eq.${design}&restored_at=is.null`, { restored_at: now });
        return text("ok", 200, origin);
      case "admin_trash":
      case "admin_remove": {
        if (!fileId) return text("bad id", 400, origin);
        const row = (await db("GET", `hsd_submissions?select=status&id=eq.${fileId}`))[0];
        if (row && row.status !== "removed") {
          await db("PATCH", `hsd_submissions?id=eq.${fileId}&status=eq.${row.status}`, {
            status: "removed",
            status_before: row.status,
            removed_at: now,
            removed_by: action.slice("admin_".length),
            restored_at: null,
          });
        }
        return text("ok", 200, origin);
      }
      case "admin_restore": {
        if (!fileId) return text("bad id", 400, origin);
        const row = (await db("GET", `hsd_submissions?select=status,status_before&id=eq.${fileId}`))[0];
        if (row && row.status === "removed") {
          const back = row.status_before === "approved" ? "approved" : "pending";
          await db("PATCH", `hsd_submissions?id=eq.${fileId}&status=eq.removed`, { status: back, restored_at: now });
        }
        return text("ok", 200, origin);
      }
      case "admin_history":
        return json(await history(), 200, origin);
    }
    return text("unknown action", 400, origin);
  }

  async function post(req: Request, origin: string | null): Promise<Response> {
    if (origin && !SITE_ORIGINS.includes(origin)) return text("not allowed", 403, null);
    if (Number(req.headers.get("Content-Length") || 0) > MAX_BODY) return text("too big", 413, origin);
    const form = await req.formData().catch(() => null);
    const p: Record<string, string> = {};
    if (form) for (const [k, v] of form.entries()) if (typeof v === "string" && !(k in p)) p[k] = v;
    const action = p.action || "";
    if (action.startsWith("admin_")) {
      if (!adminOk(p.key)) return text("no", 403, origin);
      return await admin(action, p, origin);
    }
    if (!env("VOTE_ID_SECRET") || !env("VOTE_IP_SALT")) return text("not ready", 503, origin);

    if (action === "register") {
      if (env("VOTE_TURNSTILE_SECRET")) {
        try {
          if (!(await personOk(p.token || "", clientIp(req)))) return text("check failed", 200, origin);
        } catch (error) {
          deps.log("vote: Turnstile could not be asked", String(error).slice(0, 80));
          return text("check unavailable", 503, origin);
        }
      }
      const voter = await issueVoter();
      const carry = LEGACY.test(p.carry || "") ? p.carry : "";
      const a = (await rpc("hsd_vote_register", {
        p_ip_hash: await ipHash(req),
        p_limit: NEW_VOTERS_PER_NETWORK_DAY,
        p_voter: voter,
        p_carry: carry,
      })) as { verdict?: string; carried?: number };
      if (a?.verdict !== "ok") return text("limit", 200, origin);
      return json({ voter, carried: Number(a.carried) || 0 }, 200, origin);
    }

    if (action === "vote" || action === "unvote" || action === "my_votes") {
      const voter = p.voter || "";
      if (!(await signedOk(voter))) return text("bad", 200, origin);
      if (action === "my_votes") {
        const rows = await db("GET", `hsd_votes?select=design_id,dir&voter_token=eq.${voter}`);
        const votes: Record<string, number> = {};
        for (const r of rows) votes[String(r.design_id)] = Number(r.dir) < 0 ? -1 : 1;
        return json({ votes }, 200, origin);
      }
      const id = cleanId(p.id);
      if (!id) return text("bad id", 400, origin);
      if (action === "unvote") {
        await db("DELETE", `hsd_votes?design_id=eq.${id}&voter_token=eq.${voter}`, undefined, "return=minimal");
        return text("ok", 200, origin);
      }
      if (!(await knownDesign(id))) return text("unknown design", 400, origin);
      const verdict = await rpc("hsd_vote_cast", {
        p_design: id,
        p_voter: voter,
        p_dir: Number(p.dir) < 0 ? -1 : 1,
        p_ip_hash: await ipHash(req),
        p_limit: VOTERS_PER_DESIGN_PER_NETWORK_DAY,
      });
      return text(verdict === "limit" ? "limit" : "ok", 200, origin);
    }

    if (action === "upload" && p.data) return await upload(p, req, origin);
    return text("unknown action", 400, origin);
  }

  return async (req: Request): Promise<Response> => {
    const url = new URL(req.url);
    const parts = url.pathname.split("/").filter(Boolean);
    const tail = parts.slice(parts.indexOf("vote-api") + 1);
    const origin = req.headers.get("Origin");
    try {
      if (req.method === "OPTIONS") {
        if (!origin || !SITE_ORIGINS.includes(origin)) return new Response(null, { status: 403 });
        return new Response(null, {
          status: 204,
          headers: {
            ...headers(origin),
            "Access-Control-Allow-Methods": "GET, POST",
            "Access-Control-Allow-Headers": "content-type",
            "Access-Control-Max-Age": "600",
          },
        });
      }
      if (req.method === "GET" && tail[0] === "img") return await image(tail[1] || "");
      if (req.method === "GET" && tail.length === 0) return json(await state(), 200, origin);
      if (req.method === "POST" && tail.length === 0) return await post(req, origin);
      return text("not found", 404, origin);
    } catch (error) {
      // the detail goes to the log, never to the page
      deps.log("vote: failed", String(error).slice(0, 120));
      return text("unavailable", 503, origin);
    }
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
