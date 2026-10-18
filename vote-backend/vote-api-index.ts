// Hickory Sands District AVA logo vote backend (Supabase Edge Function)
// Mirrors the reviewed Apps Script design: state reads never write; culling runs
// only via the key protected admin_cull action; uploads are size capped, magic byte
// verified, count capped, and held as pending until approved; images are served
// only for approved submissions; the operator key lives in a function secret.
import { createClient } from "jsr:@supabase/supabase-js@2";

const ACTIVATION_UPVOTES = 50;
const MIN_VOTES_TO_RETIRE = 8;
const BOTTOM_FRACTION = 0.10;
const RATIO_FLOOR = 0.5;
const MAX_UPLOAD_BYTES = 3 * 1024 * 1024;
const MAX_SUBMISSIONS = 200;
const BUCKET = "hsd-submissions";

const sb = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);
const OPERATOR_KEY = Deno.env.get("OPERATOR_KEY") ?? "";

function clean(v: unknown): string {
  return String(v ?? "").replace(/[<>&"']/g, "").replace(/^[\s=+\-@\t\r\n]+/, "").slice(0, 200);
}
function cleanId(v: unknown): string {
  return String(v ?? "").replace(/[^A-Za-z0-9\-_]/g, "").slice(0, 80);
}
function adminOk(key: unknown): boolean {
  return !!OPERATOR_KEY && !!key && String(key) === OPERATOR_KEY;
}
function detectImageType(bytes: Uint8Array): string | null {
  if (bytes.length > 3 && bytes[0] === 0xFF && bytes[1] === 0xD8 && bytes[2] === 0xFF) return "image/jpeg";
  if (bytes.length > 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4E && bytes[3] === 0x47) return "image/png";
  return null;
}
async function tally() {
  const { data } = await sb.from("hsd_votes").select("design_id, dir");
  const up: Record<string, number> = {};
  const down: Record<string, number> = {};
  let totalUp = 0;
  for (const r of data ?? []) {
    if (Number(r.dir) < 0) down[r.design_id] = (down[r.design_id] || 0) + 1;
    else { up[r.design_id] = (up[r.design_id] || 0) + 1; totalUp++; }
  }
  return { up, down, totalUp };
}
async function retiredIds(): Promise<string[]> {
  const { data } = await sb.from("hsd_retired").select("design_id");
  return (data ?? []).map((r) => String(r.design_id));
}
async function cullNow() {
  const t = await tally();
  if (t.totalUp < ACTIVATION_UPVOTES) return { culled: [] as string[], reason: "not activated" };
  const retired = await retiredIds();
  const ids = new Set([...Object.keys(t.up), ...Object.keys(t.down)]);
  const scored: { id: string; ratio: number }[] = [];
  for (const id of ids) {
    const u = t.up[id] || 0;
    const d = t.down[id] || 0;
    if (u + d >= MIN_VOTES_TO_RETIRE && !retired.includes(id)) {
      scored.push({ id, ratio: u / (u + d) });
    }
  }
  scored.sort((x, y) => x.ratio - y.ratio);
  const n = Math.floor(scored.length * BOTTOM_FRACTION);
  const culled: string[] = [];
  for (let i = 0; i < Math.min(n, scored.length); i++) {
    if (scored[i].ratio < RATIO_FLOOR) {
      await sb.from("hsd_retired").insert({ design_id: scored[i].id });
      culled.push(scored[i].id);
    }
  }
  return { culled };
}
async function state(base: string) {
  const t = await tally();
  const { data: subs } = await sb
    .from("hsd_submissions")
    .select("id, name, title")
    .eq("status", "approved")
    .order("created_at");
  const list = (subs ?? []).map((s) => ({
    id: "sub-" + s.id,
    name: s.name,
    title: s.title,
    img: base + "/img/" + s.id,
  }));
  return {
    up: t.up,
    down: t.down,
    totalUp: t.totalUp,
    cullingActive: t.totalUp >= ACTIVATION_UPVOTES,
    retired: await retiredIds(),
    submissions: list,
  };
}
const CORS = { "Access-Control-Allow-Origin": "*" };
function jsonOut(obj: unknown, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...CORS },
  });
}
function textOut(s: string, status = 200) {
  return new Response(s, { status, headers: { "Content-Type": "text/plain", ...CORS } });
}

Deno.serve(async (req) => {
  const url = new URL(req.url);
  const parts = url.pathname.split("/").filter(Boolean);
  const tail = parts.slice(parts.indexOf("vote-api") + 1);
  const base = "https://" + url.host + "/functions/v1/vote-api";

  if (req.method === "OPTIONS") {
    return new Response(null, {
      headers: {
        ...CORS,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
      },
    });
  }

  if (req.method === "GET" && tail[0] === "img" && tail[1]) {
    const { data: row } = await sb
      .from("hsd_submissions")
      .select("storage_path, content_type, status")
      .eq("id", tail[1])
      .maybeSingle();
    if (!row || row.status !== "approved") return textOut("not found", 404);
    const { data: blob, error } = await sb.storage.from(BUCKET).download(row.storage_path);
    if (error || !blob) return textOut("not found", 404);
    return new Response(blob, {
      headers: { "Content-Type": row.content_type, "Cache-Control": "public, max-age=86400", ...CORS },
    });
  }

  if (req.method === "GET") {
    const st = await state(base);
    const cb = url.searchParams.get("callback");
    if (cb && /^[A-Za-z_$][A-Za-z0-9_$]*(\.[A-Za-z_$][A-Za-z0-9_$]*)*$/.test(cb)) {
      return new Response(cb + "(" + JSON.stringify(st) + ");", {
        headers: { "Content-Type": "application/javascript", ...CORS },
      });
    }
    return jsonOut(st);
  }

  if (req.method === "POST") {
    const form = await req.formData().catch(() => null);
    const p: Record<string, string> = {};
    if (form) for (const [k, v] of form.entries()) p[k] = String(v);
    const action = p.action || "";

    if (action === "vote" && p.id && p.voter) {
      const id = cleanId(p.id);
      const voter = cleanId(p.voter);
      if (!id || !voter) return textOut("bad");
      const dir = Number(p.dir) < 0 ? -1 : 1;
      await sb.from("hsd_votes").upsert(
        { design_id: id, voter_token: voter, dir },
        { onConflict: "design_id,voter_token" },
      );
    } else if (action === "unvote" && p.id && p.voter) {
      await sb.from("hsd_votes").delete()
        .eq("design_id", cleanId(p.id))
        .eq("voter_token", cleanId(p.voter));
    } else if (action === "upload" && p.data) {
      const { count } = await sb.from("hsd_submissions").select("id", { count: "exact", head: true });
      if ((count ?? 0) >= MAX_SUBMISSIONS) return textOut("full");
      if (p.data.length > 4500000) return textOut("too big");
      let bytes: Uint8Array;
      try {
        bytes = Uint8Array.from(atob(p.data), (c) => c.charCodeAt(0));
      } catch {
        return textOut("bad data");
      }
      if (bytes.length > MAX_UPLOAD_BYTES) return textOut("too big");
      const mime = detectImageType(bytes);
      if (!mime) return textOut("not an image");
      const id = crypto.randomUUID();
      const path = id + (mime === "image/png" ? ".png" : ".jpg");
      const { error: upErr } = await sb.storage.from(BUCKET).upload(path, bytes, { contentType: mime });
      if (upErr) return textOut("upload failed", 500);
      await sb.from("hsd_submissions").insert({
        id,
        name: clean(p.name).slice(0, 60),
        title: clean(p.title).slice(0, 60),
        storage_path: path,
        content_type: mime,
        status: "pending",
      });
    } else if (action === "admin_pending" && adminOk(p.key)) {
      const { data } = await sb
        .from("hsd_submissions")
        .select("id, name, title, created_at")
        .eq("status", "pending")
        .order("created_at");
      return jsonOut((data ?? []).map((r) => ({ name: r.name, title: r.title, fileId: r.id, when: r.created_at })));
    } else if (action === "admin_approve" && adminOk(p.key) && p.id) {
      await sb.from("hsd_submissions").update({ status: "approved" }).eq("id", p.id);
    } else if (action === "admin_cull" && adminOk(p.key)) {
      return jsonOut(await cullNow());
    } else if (action === "admin_trash" && adminOk(p.key) && p.id) {
      // Metadata level only: deletes the stored file and its row. Never reads content.
      const { data: row } = await sb
        .from("hsd_submissions")
        .select("storage_path")
        .eq("id", p.id)
        .maybeSingle();
      if (row) await sb.storage.from(BUCKET).remove([row.storage_path]);
      await sb.from("hsd_submissions").delete().eq("id", p.id);
      await sb.from("hsd_votes").delete().eq("design_id", "sub-" + p.id);
      await sb.from("hsd_retired").delete().eq("design_id", "sub-" + p.id);
    } else if (action === "admin_remove" && adminOk(p.key) && p.id) {
      await sb.from("hsd_submissions").delete().eq("id", p.id);
      await sb.from("hsd_votes").delete().eq("design_id", "sub-" + p.id);
      await sb.from("hsd_retired").delete().eq("design_id", "sub-" + p.id);
    } else if (action === "admin_unretire" && adminOk(p.key) && p.id) {
      await sb.from("hsd_retired").delete().eq("design_id", p.id);
    }
    return textOut("ok");
  }
  return textOut("not found", 404);
});
