# The growers' logo vote: its backend

The vote's page is hickorysandsdistrictava.org/logo-vote.html (`docs/logo-vote.html`, `docs/assets/logo-vote.js`,
`vote-config.js`). It moves there from the Shopify page robertclayvineyards.com/pages/hsd-logo-vote (issue #100), whose
front end lives in the theme repository danshome/robertclayvineyards.com. `SETUP.md` is the switch-over, step by step.

Backend: the Supabase project "Hickory Sands District AVA" (ref `yayebhncbagmebwgmezd`, us-east-1), owned by Dan.

- `functions/vote-api/index.ts`: the Edge Function "vote-api" (JWT verification off). Its first lines list its
  endpoints and secrets. Dan deploys it from the dashboard as one file made by `bundle_function.py`, which inlines the
  page's design ids (`docs/assets/logo-vote/designs.json`). `tests/test_vote_function.py` runs that file in node against
  stand-ins (`tests/vote_standin.mjs`).
- `functions/vote-api/hsd_vote_migration.sql`: the database change for this function, run once in the SQL Editor
  (again changes nothing). Tables: `hsd_votes` (design_id + voter_token key, dir, updated_at), `hsd_submissions` (uuid,
  title, storage_path, content_type, status pending / approved / removed, ip_hash, the removal and restore dates; the
  name column is kept blank), `hsd_retired` (dated retire records, never deleted), `hsd_vote_networks` and
  `hsd_vote_registrations` (the limits, by an HMAC of the address, a day long), `hsd_vote_exchanged` (Shopify-era ids
  already carried over). Row level security is on and forced, with no policies; only the function (service role)
  touches the tables. `tests/test_vote_sql.py` runs it in PostgreSQL.
- Storage: the private bucket "hsd-submissions" holds the uploaded images; the function serves one only while its
  design is approved.
- The function reads `VOTE_ID_SECRET` (signs the voter ids), `VOTE_IP_SALT` (the HMAC of addresses), `OPERATOR_KEY` (the admin
  actions), and, only if bots show up, `VOTE_TURNSTILE_SECRET` (the person check). Their values are kept by Dan, never
  in this repository.
- Culling, only when the operator asks (`admin_cull`): a design with at least 25 votes and under 35 percent likes is
  retired, unless it was restored since its last vote.
- Limits: 10 voters per design per address per day; 5 new voter ids per address per day; 5 uploads per address per
  day, 50 waiting, 200 in all, 3 MB, JPEG or PNG (magic bytes); nothing shown until approved.
- `shopify-handoff.liquid`: what the Shopify page becomes at the switch-over (it sends each grower on with their voter
  id).
- `sb.py`, `sb_deploy.py`: Management API helpers (run SQL, set secrets, deploy) for another agent's connector, which
  attaches its credential surrogate to each request; no token is stored in these files. Dan's own way is the dashboard
  (`SETUP.md`).
