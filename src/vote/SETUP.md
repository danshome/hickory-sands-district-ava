# Moving the logo vote to the site: a guide for Dan

The growers' logo vote moves from the Shopify page (robertclayvineyards.com/pages/hsd-logo-vote) to
hickorysandsdistrictava.org/logo-vote.html (issue #100). The page (`docs/logo-vote.html`) is already on the site, but
until step 4 it only says "The vote moves here soon" and links to the Shopify page: it calls nothing. The function
(`src/vote/functions/vote-api/index.ts`) and the database change (`hsd_vote_migration.sql` beside it) do nothing until
you put them in Supabase.

What changes for the vote: no names are kept or shown; voter ids are made and signed by the function; at most 10
voters per design per day from one internet connection, and 5 new voter ids per connection per day; votes only for
the designs the page knows; nothing is ever deleted (a retired design has a dated record and can be restored; a
removed design is marked `removed` and can be restored); the person check (Cloudflare Turnstile) is off, ready to be
turned on if bots show up.

Do steps 3 to 5 within a few minutes of each other: from step 3 the Shopify page can no longer vote (its voter ids
are refused), and from step 5 it sends growers, with their votes, to the new page. Allow half an hour in all.

## 1. Supabase: the two secrets

A project's secrets are shared by all its functions, so the vote's have its own names (the vineyard form's are
`IP_SALT` and `TURNSTILE_SECRET`).

1. On supabase.com/dashboard, open the project **Hickory Sands District AVA** (ref `yayebhncbagmebwgmezd`).
2. **Edge Functions** > **Secrets**. Add each (Key, then Value) and click **Save**:

   | Key | Value |
   |---|---|
   | `VOTE_ID_SECRET` | new random text: in Terminal, `openssl rand -hex 32 \| pbcopy`, then paste |
   | `VOTE_IP_SALT` | new random text, made the same way (a different one) |

   `OPERATOR_KEY` is already there; leave it. Keep none of these anywhere but Supabase (and your password manager).

## 2. Supabase: the database change

The change keeps every vote, design, file and retire record. It blanks the names growers typed on the Shopify page
(they are never shown again). If you want to keep them privately to thank people, first run
`select title, name, created_at from hsd_submissions where name <> '';` in the SQL Editor and download the result
(**Results** > **Export** > CSV) to your Mac, never to the repository.

1. In Terminal, at the repository's root, on an up-to-date `main`:
   `pbcopy < src/vote/functions/vote-api/hsd_vote_migration.sql`
2. **SQL Editor** > **New query** (the +), click into the editor and paste. Click **Run**. You should see "Success.
   No rows returned".
3. Check it: **Table Editor** lists `hsd_vote_networks`, `hsd_vote_registrations` and `hsd_vote_exchanged`, and
   `hsd_retired` has the columns `retired_at`, `reason` and `restored_at`.

Running it again changes nothing. The Shopify page and the function as it is today go on working after it.

## 3. Supabase: deploy the new function

**The dashboard, not the CLI**, as for the vineyard form: you paste one file.

1. In Terminal, at the repository's root, on an up-to-date `main`:
   `.venv/bin/python -E -s -B src/vote/bundle_function.py --copy`
   It prints the file's size and "copied". The file is the function with the page's design ids in it. It is also left
   in `target/vote-api/index.ts`.
2. **Edge Functions** > `vote-api` > **Code**. Click into the editor, press ⌘A, then ⌘V. Click **Deploy updates** and
   wait for the message that it is deployed.
3. Check that **Enforce JWT verification** is still off (`vote-api` > **Details**): the page is public.
4. Check it: in Terminal,
   `curl -s https://yayebhncbagmebwgmezd.supabase.co/functions/v1/vote-api | head -c 300`
   shows the counts and, at the end, `"rule":{"minVotes":25,"retireRatio":0.35,"votersPerNetwork":10}`, and no
   `"name"`. An answer of `unavailable` means the database change (step 2) is missing.

If something is wrong, the old function is in the repository's history:
`git show 1275d9c:vote-backend/vote-api-index.ts | pbcopy`, and paste it back the same way. It still works on the
changed database.

## 4. The page goes live

Tell Claude the function is deployed. Claude opens a small pull request that sets `live = true` in
`docs/assets/vote-config.js`; merge it. A minute later hickorysandsdistrictava.org/logo-vote.html shows the vote.
Try it on your phone: Like a design, then Undo.

## 5. Shopify: the hand-off

In the Shopify theme's repository (danshome/robertclayvineyards.com), in `sections/hsd-logo-vote.liquid`, replace the
section's vote markup and script with the contents of `src/vote/shopify-handoff.liquid` from this repository, and
publish the theme. The page keeps its address, so old links still work: it sends each grower on to the new page with
their voter id, and the new page hands their Shopify votes to their new id, once (they show under "Your votes" and are
not offered again).

Do not set `Referrer-Policy: no-referrer` on that page: the new page takes a carried id only from a visit that comes
from robertclayvineyards.com.

Check it: on a phone that voted on the Shopify page, open the Shopify page. It should land on the new page saying
"Welcome back. Your ... votes from the old vote page are here".

## 6. Optional: the old addresses

The old function kept each upload's address (`ip`) for its daily limit; the new one keeps only an HMAC
(`ip_hash`). To clear the old addresses, run in the SQL Editor:
`update hsd_submissions set ip = null where ip is not null;`

## Day to day: the operator's actions

Each is one command in Terminal. Put the operator key in your shell first, from your password manager, so it is not in
your history: `read -s OPERATOR_KEY` (paste, Enter). Then, with
`F=https://yayebhncbagmebwgmezd.supabase.co/functions/v1/vote-api`:

| to | run |
|---|---|
| see the designs waiting | `curl -s "$F" -d action=admin_pending --data-urlencode "key=$OPERATOR_KEY"` |
| approve one | `curl -s "$F" -d action=admin_approve -d id=<fileId> --data-urlencode "key=$OPERATOR_KEY"` |
| retire the designs few like (25 votes, under 35 percent likes) | `curl -s "$F" -d action=admin_cull --data-urlencode "key=$OPERATOR_KEY"` |
| retire one by hand | `curl -s "$F" -d action=admin_retire -d id=<design id> -d "reason=<why>" --data-urlencode "key=$OPERATOR_KEY"` |
| put a retired design back | `curl -s "$F" -d action=admin_unretire -d id=<design id> --data-urlencode "key=$OPERATOR_KEY"` |
| take a sent-in design out | `curl -s "$F" -d action=admin_trash -d id=<fileId> --data-urlencode "key=$OPERATOR_KEY"` (or `admin_remove`) |
| put it back | `curl -s "$F" -d action=admin_restore -d id=<fileId> --data-urlencode "key=$OPERATOR_KEY"` |
| see every retire record and removed design, with their votes | `curl -s "$F" -d action=admin_history --data-urlencode "key=$OPERATOR_KEY"` |

A design id is `c1` and the like for the page's own designs, `sub-<fileId>` for a sent-in one. The cull leaves alone a
design restored since its last vote, so a design put back after a fix is not retired again at once. Nothing is ever
deleted: votes on a retired or removed design are kept, and it comes back with them.

When the vote closes: tell Claude the chosen design's id. `closed` and `chosen` in `docs/assets/vote-config.js` then
show it as the growers' choice, and the page stops taking votes and designs.

## If bots show up: the person check

The person check is Cloudflare Turnstile, once per phone, before a phone's first vote. It is off. It is on when both
are set: the widget's site key in `docs/assets/vote-config.js` and its secret in Supabase as `VOTE_TURNSTILE_SECRET`.
Set them in this order: the secret alone would refuse every new voter.

1. On dash.cloudflare.com, **Turnstile** > **Add widget**. **Widget name:** `HSD logo vote`. **Hostnames:**
   `hickorysandsdistrictava.org` (and `localhost`, to try it on your Mac). **Widget mode:** Managed.
   **Pre-clearance:** No. **Create**.
2. Send Claude the **Site Key** (it is public). Claude opens a pull request that puts it in `vote-config.js`; merge it.
3. Then, in Supabase, **Edge Functions** > **Secrets**: add `VOTE_TURNSTILE_SECRET` with the widget's **Secret Key**.
   No deploy is needed.

To turn it off again: delete the secret first, then ask Claude to empty the site key.

## Where each secret lives

| secret | lives in | used by |
|---|---|---|
| `VOTE_ID_SECRET` | Supabase: Edge Functions > Secrets | vote-api: signs the voter ids |
| `VOTE_IP_SALT` | Supabase | vote-api: the limits, without keeping any address |
| `OPERATOR_KEY` | Supabase, and your password manager | vote-api: the admin actions |
| `VOTE_TURNSTILE_SECRET` (only if bots show up) | Supabase | vote-api: the person check |
| the function's URL, the Turnstile site key (not secret) | `docs/assets/vote-config.js` | the page |
