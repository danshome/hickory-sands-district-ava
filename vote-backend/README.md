# Hickory Sands District AVA logo vote backend

The growers vote page (robertclayvineyards.com/pages/hsd-logo-vote) is a Shopify
page. Its front end lives in the theme repo danshome/robertclayvineyards.com
(sections/hsd-logo-vote.liquid, assets/hsd-logo-vote.css,
templates/page.hsd-logo-vote.json, templates/robots.txt.liquid).
The shared backend lives here because Liquid cannot store shared state.

Backend: Supabase project "Hickory Sands District AVA"
(ref yayebhncbagmebwgmezd, us-east-1), owned by Dan.

- vote-api-index.ts: the Edge Function "vote-api" (deployed, verify_jwt off).
  Endpoints: JSONP state (callback param), POST actions vote / unvote / upload,
  and key protected admin actions admin_pending / admin_approve / admin_trash /
  admin_remove / admin_cull / admin_unretire. GET /img/<uuid> serves an image
  only when its submission is approved.
- Database tables: hsd_votes (design_id + voter_token primary key, dir),
  hsd_submissions (uuid, name, title, storage_path, content_type, status
  pending/approved), hsd_retired (design_id). Row level security is on with no
  public policies; only the function (service role) touches the tables.
- Storage: private bucket "hsd-submissions" holds uploaded images.
- The OPERATOR_KEY function secret gates the admin actions. Its value is kept
  locally, never in this repo.
- Culling (operator triggered only, never automatic on page load): a design
  with at least 25 total votes and under 35 percent likes retires.
- Upload flood limits: max 5 uploads per IP per day, max 50 submissions
  waiting in the pending queue, max 200 total, 3 MB per file, JPEG/PNG only
  (magic bytes), and nothing is visible until approved.
- sb.py: Management API helper (list projects, run SQL, set secrets).
  sb_deploy.py: deploys vote-api-index.ts via
  POST /v1/projects/{ref}/functions/deploy?slug=vote-api.
  Both attach the Muse connector's credential surrogate (custom.supabase) to
  each request; no token is stored in these files.
