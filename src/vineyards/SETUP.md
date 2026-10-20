# Setting up "Add your vineyard": a guide for Dan

The vineyards page's form (docs/vineyards.html, "Add your vineyard") sends a grower's vineyard to one Supabase Edge
Function, `vineyard-submit`. The function keeps the grower's name, phone and email in one locked table and opens a
public GitHub issue with the vineyard's public fields only. The `vineyard-check` Action comments on the issue. Approving
it opens the pull request that adds the vineyard, and merging that pull request puts it on the site. With the second
GitHub App (section A, optional) your label `approved` makes the `vineyard-approve` Action open that pull request by
itself; until then Claude opens it by hand when you say so ("Day to day").

The code in the repository does nothing until you have set it up. Until then the page offers the email instead (once the
page's pull request is merged). This guide is click by click. Every secret is pasted by you and goes only where it says:
never into the repository, a pull request, an issue or a chat.

**What is needed now, and what can wait (Dan, 2026-10-19: no Cloudflare for now):**

- Now, steps 1 to 7: the form's GitHub App, the labels, the Supabase table, the function's secrets, the deploy, the
  check and the page. The Supabase secrets needed are exactly these five: `GITHUB_APP_ID`,
  `GITHUB_APP_INSTALLATION_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET` and `IP_SALT`. (`PRIVATE_WORDS` and
  `PRIVATE_WORDS_SILENT` are optional.)
- Later, optional: **A.** the second App, "HSD vineyard PR", so that your label `approved` opens the pull request by
  itself. Without it, approving is done by hand: you tell Claude, and Claude opens the pull request.
- Only if bots show up: **B.** Cloudflare Turnstile, the check that a person is sending. Without it, the form still
  has its hidden trap field, its limits (five sends a day from one connection, thirty a day in all) and every rule; the
  function and the page each ask for the check only once its key is set.

**Two things that differ from the proposal (§11), and why:**

1. **Two GitHub Apps, not one App and a personal token.** The form's App, "HSD vineyard form", can only open issues and
   comment. Its key lives in Supabase, and anything that can deploy a function to that project can read every secret
   there. vote-api is deployed there by another agent's credential. The second App, "HSD vineyard PR" (section A), can
   push branches and open pull requests. Its key lives only in the GitHub environment `vineyard-pr`, which only
   `main`'s own workflow can use. Two Apps keep a write path to the code out of Supabase. An App's key never expires,
   unlike a personal token, and a pull request opened by an App runs every check. The fallback, if you would rather
   not make a second App, is the proposal's fine-grained token ("token 2"); ask Claude to switch the workflow back.
2. **The form App also has a webhook, and there is a daily check.** The webhook is how the function learns that an
   issue was closed: you asked for a contact to be deleted one year after its issue is closed. The function records
   the closing date and deletes the rows closed more than a year ago each time it runs. GitHub never sends a failed
   delivery again, so a daily Action (`vineyard-reconcile`) also asks the function to put its table right against
   GitHub, and opens an issue for you when that fails (step 6.2).

Allow about forty minutes for steps 1 to 7. Do them in order, after the machinery's pull request (the one that adds
this file) is merged. The page's pull request comes last (step 7).

## 1. The form's GitHub App: "HSD vineyard form"

1. On github.com, click your picture (top right) > **Settings** > **Developer settings** (bottom of the left menu) >
   **GitHub Apps** > **New GitHub App**.
2. **GitHub App name:** `HSD vineyard form`, exactly. Its bot is then `hsd-vineyard-form[bot]`, the name the
   workflows check. If GitHub says the name is taken, stop and tell Claude: the name is in the code.
3. **Homepage URL:** `https://hickorysandsdistrictava.org`
4. **Identifying and authorizing users:** leave the Callback URL empty, and leave both boxes unticked.
5. **Webhook:** tick **Active**.
   - **Webhook URL:** `https://yayebhncbagmebwgmezd.supabase.co/functions/v1/vineyard-submit/github`
   - **Webhook secret:** make one. In Terminal, run `openssl rand -hex 32 | pbcopy`, then paste it here. Keep it in
     your password manager as "HSD vineyard webhook secret": you paste it again in step 4.
   - **SSL verification:** Enable.
6. **Permissions** > **Repository permissions** > **Issues:** "Read and write". Leave everything else at "No access".
   **Metadata** turns to "Read-only" by itself.
7. **Subscribe to events:** tick **Issues**.
8. **Where can this GitHub App be installed?** "Only on this account".
9. Click **Create GitHub App**.
10. On the App's page, under **About**, copy the **App ID** (a number). Keep it: it is `GITHUB_APP_ID` in step 4.
11. Scroll to **Private keys** > **Generate a private key**. A `.pem` file downloads. It is `GITHUB_APP_PRIVATE_KEY`
    in step 4.
12. In the left menu, click **Install App** > **Install** (beside danshome) > **Only select repositories** >
    `hickory-sands-district-ava` > **Install**.
13. You land on a page whose address ends in `/settings/installations/` and a number. Copy that number: it is the
    installation ID, `GITHUB_APP_INSTALLATION_ID` in step 4.

GitHub sends the webhook a "ping" now. It fails until step 5, and that does no harm.

## 2. GitHub: the labels and the private words

1. **Labels.** In the repository: **Issues** > **Labels** > **New label**, four times: `vineyard-submission`,
   `approved`, `vineyard-data` and `vineyard-change` (a change to a listed vineyard). Any colours. The form's App
   applies an existing label; it cannot make one.
   Until section A is done, do not add `approved` to an issue: its Action would run without the second App, fail,
   and make the environment `vineyard-pr` with no rule (see step A.2). Approve by telling Claude instead
   ("Day to day").
2. **The private words** (optional). What they are: `.private-words` is a short list of words, one per line, kept
   only on your Mac (git never takes it: it is in `.gitignore`). It holds names that must never appear in this public
   repository, its issues or the site, such as people's names. The commit hooks already refuse any commit that holds
   one; the website's data generators refuse them too. Setting this secret is optional: it lets the vineyard form
   check a grower's public text against the same list, so a person's name typed as a vineyard's name or a variety is
   not posted on GitHub. Without it, the form still refuses titles, email addresses, telephone numbers and the words
   in its own rules, and you check each issue before approving anything.

   If you set it, set it in **both** places or in **neither**: here and in Supabase (step 4). With it in only one
   place, the form and the check disagree about what is refused. Here: **Settings** > **Secrets and variables** >
   **Actions** > **New repository secret:** name `PRIVATE_WORDS`; value: your `.private-words` list
   (`pbcopy < .private-words` from the main checkout). The Actions then refuse a public field that holds one of the
   words, and never print them.

   What a grower sees when their text holds one of the words is your choice, made when you set it up:
   - **Refused (as built):** "The register can't show this name as written. Change the wording, or email the
     petitioners." It names no word. But someone could try word after word and learn which words are on the list.
   - **Held quietly:** the grower is thanked as usual (with no reference number), nothing is posted, and the row in
     Supabase's Table Editor is marked `held` for you to read and answer. To choose this, also add the Supabase secret
     `PRIVATE_WORDS_SILENT` with the value `1` (step 4). See "A private word, silently" below.

## 3. Supabase: the table

1. On supabase.com/dashboard, open the project **Hickory Sands District AVA** (ref `yayebhncbagmebwgmezd`, the one
   that runs vote-api).
2. In the left menu, click **SQL Editor** > **New query** (the + at the top).
3. In Terminal, at the repository's root, run
   `pbcopy < src/vineyards/functions/vineyard-submit/hsd_vineyard_contacts.sql`, then click into the editor and paste.
4. Click **Run**. You should see "Success. No rows returned".
5. Check it: **Table Editor** lists `hsd_vineyard_contacts`, marked as having row level security on.

The SQL makes only things named `hsd_vineyard_...`: two tables (the contacts, and when the function last
reconciled), two indexes and two functions. It changes nothing of vote-api's, and running it again changes nothing.

## 4. Supabase: the function's secrets

1. In the left menu, click **Edge Functions** > **Secrets**.
2. Add each one (Key, then Value), and click **Save** when all are in. These five are needed:

   | Key | Value |
   |---|---|
   | `GITHUB_APP_ID` | the form App's App ID (step 1.10) |
   | `GITHUB_APP_INSTALLATION_ID` | the installation number (step 1.13) |
   | `GITHUB_APP_PRIVATE_KEY` | the whole first `.pem` file: run `pbcopy < ~/Downloads/` and the file's name (it starts `hsd-vineyard-form.`). Pasted with or without its line breaks, the function reads it. |
   | `GITHUB_WEBHOOK_SECRET` | the webhook secret from step 1.5 |
   | `IP_SALT` | new random text: `openssl rand -hex 32 \| pbcopy` |

   Optional:

   | Key | Value |
   |---|---|
   | `PRIVATE_WORDS` | the same list as in step 2.2 (both places, or neither) |
   | `PRIVATE_WORDS_SILENT` | `1` to hold a private word quietly (step 2.2); unset, it is refused |

   Not now: `TURNSTILE_SECRET`, only if bots show up (section B). While it is unset, the function does not ask
   Cloudflare, and it is ready without it.
3. Put the first `.pem` file in the Trash and empty it.

A project's secrets are shared by all its functions. vote-api reads only its own (`OPERATOR_KEY` and the `VOTE_*`
secrets, `src/vote/SETUP.md`), never these.

## 5. Supabase: deploy the function

**The dashboard, not the CLI.** It needs nothing installed and no login on the Mac: you paste one file. The CLI would
need Homebrew, a login token and the project linked first.

1. In Terminal, at the repository's root, on an up-to-date `main`, run:
   `.venv/bin/python -E -s -B src/vineyards/bundle_function.py --copy`
   It prints the file's size and "copied". The file is the function, the site's rules and TTB's proposed Llano Uplift
   AVA in one piece. It is also left in `target/vineyard-submit/index.ts`.
2. In the dashboard: **Edge Functions** > **Deploy a new function** > **Via Editor**.
3. Click into the editor, press ⌘A to select the template's code, then ⌘V to paste.
4. Name the function `vineyard-submit`, exactly. Click **Deploy function** and wait for the message that it is
   deployed (10 to 30 seconds).
5. **Turn off JWT verification**, as for vote-api: the form is public. Open `vineyard-submit` > its **Details** (or
   **Settings**) tab, find "Enforce JWT verification" (some versions say "Verify JWT with legacy secret"), switch it
   off and save. The check in step 6 says so if it is still on.

Leave vote-api alone. To update the function later: run the same command, open `vineyard-submit` > **Code**, select
all, paste and click **Deploy updates**.

## 6. Check that it works

1. In Terminal, at the repository's root: `.venv/bin/python -E -s -B src/vineyards/check_function.py`.
   Its first line says which mode the function reports: "Person check (Turnstile): off (TURNSTILE_SECRET not set)"
   for now. Success, with the check off, is four lines starting `PASS` and one starting `SKIP`, then "All checks
   passed (1 skipped: person check off).":
   - the function answers and every secret is set (if not, it names the missing secrets; a 401 means JWT
     verification is still on);
   - the site may send to it;
   - another site may not;
   - a send without the person check is refused: `SKIP` while the check is off (nothing is sent); with
     `TURNSTILE_SECRET` set (section B), a `PASS`, and then all five pass;
   - a forged address does not change the address counted. The limit of five sends a day from one connection counts
     the address the function reads from `cf-connecting-ip` (which Cloudflare sets in front of Supabase), else
     `x-real-ip`, else `x-forwarded-for`. The check asks the function, twice, with each of those headers forged to a
     different address, for a digest of the address it would count. If the digest changes, a sender could dodge the
     limit by forging the header. Send Claude the line; the fix is to count only the header the gateway proves it
     sets.

   The first check's line also shows which address headers reach the function, names only.
2. **Turn on the daily check.** Repository **Settings** > **Secrets and variables** > **Actions** > **Variables** >
   **New repository variable:** name `VINEYARD_FUNCTION_URL`; value
   `https://yayebhncbagmebwgmezd.supabase.co/functions/v1/vineyard-submit`. Then **Actions** > **vineyard-reconcile** >
   **Run workflow**: it should end green. Every day it asks the function to put its table right against GitHub (a
   closing the webhook missed, a row not yet tied to its issue, the year's deletions). If that fails, it opens an
   issue, "Vineyard form: the daily check failed", or comments on it, and the run fails.
3. GitHub: the form App's page > **Advanced** > **Recent Deliveries**. Open the failed "ping" > **Redeliver**. It
   should now show 200.
4. After the page's pull request is merged (step 7), send a test from your phone:
   hickorysandsdistrictava.org/vineyards.html > **Add my vineyard**. Draw one small block on any vineyard, name it
   `Test vineyard`, put in your own phone or email, tick both boxes and **Send**. Success:
   - the thank-you screen gives a reference number, say 160;
   - within a minute, issue #160 appears, opened by `hsd-vineyard-form[bot]` with the label `vineyard-submission`
     and the block drawn on a map, then a comment by `github-actions[bot]` headed "The check: ...";
   - in Supabase's **Table Editor** > `hsd_vineyard_contacts`, one row with your contact and `issue_number` 160.
5. Close the test issue as "not planned". Within seconds, its row's `closed_at` is filled in (refresh the Table
   Editor). The row is deleted a year later; you may delete the test row now (select it > Delete).

Leaving the test issue without the label keeps the site unchanged. Once section A is done, you can try the approval as
well: add `approved`, and a pull request "Vineyard: Test vineyard (#160)" opens. Close it without merging and delete its
branch.

## 7. The page

Tell Claude the function is deployed and checked. Its address is already known and public:
`https://yayebhncbagmebwgmezd.supabase.co/functions/v1/vineyard-submit`. It goes into `endpoint` in
`docs/assets/vineyard-config.js` in a small pull request, with `turnstileSiteKey` left empty (no person check). Until
it is there, the page's form ends at the email fallback.

## A. Later, optional: the pull request's GitHub App, "HSD vineyard PR"

This can wait. Without it, your label `approved` cannot open the pull request by itself: the `vineyard-approve` Action
needs this App's key. Approving is then done by hand: tell Claude "approve #160" (the issue's number), and Claude makes
the same change the Action would (the same checks again, the blocks added to
`resources/vineyards/vineyards-EPSG4269.geojson`, the site's vineyard data made again) on a branch and opens the pull
request "Vineyard: <name> (#160)" that closes the issue. You review and merge it as every pull request. Do not add
`approved` until this section is done (step 2.1).

When you want the label to do it, set this up in order:

1. **The App.**
   1. **Developer settings** > **GitHub Apps** > **New GitHub App** again.
   2. **GitHub App name:** `HSD vineyard PR`. **Homepage URL:** `https://hickorysandsdistrictava.org`.
   3. **Webhook:** untick **Active** (this App needs none).
   4. **Repository permissions:** **Contents:** "Read and write"; **Pull requests:** "Read and write". Nothing else.
   5. "Only on this account" > **Create GitHub App**.
   6. Under **About**, copy the **Client ID** (it starts `Iv`). It is `VINEYARD_PR_CLIENT_ID` in step A.2.
   7. **Private keys** > **Generate a private key**. A second `.pem` file downloads: `VINEYARD_PR_PRIVATE_KEY` in
      step A.2.
   8. **Install App** > **Install** > **Only select repositories** > `hickory-sands-district-ava` > **Install**.

   Optional, and a second lock: the `main` ruleset could also require one approval. Neither App could then merge a
   pull request, and your own merges with `--admin` would go on as now. Settings > Rules > Rulesets > the ruleset for
   `main` > "Require a pull request before merging" > "Required approvals: 1".
2. **The environment.** Do this before the first `approved` label: a workflow that names a missing environment makes
   it with no rule. (If one was added early and `vineyard-pr` already exists, open it and do 2 before 3.) And do these
   three in this order.
   1. Repository **Settings** > **Environments** > **New environment**, name it `vineyard-pr` > **Configure
      environment**.
   2. **Deployment branches and tags:** choose "Selected branches and tags" > **Add deployment branch or tag rule** >
      `main` > **Add rule**. **Look that the page now lists `main` as the only rule.** Optional: **Required
      reviewers:** add yourself; each approval then waits for one more click in the Actions tab.
   3. **Only now** add the key. **Environment secrets** > **Add environment secret:** name
      `VINEYARD_PR_PRIVATE_KEY`; value: the whole second `.pem` file. To copy it, run `pbcopy < ~/Downloads/`
      followed by the file's name (it starts `hsd-vineyard-pr.`). Then **Environment variables** > **Add environment
      variable:** name `VINEYARD_PR_CLIENT_ID`; value: the Client ID from step A.1.6.

   Before every approval, the approve Action checks that only `main` may use this environment. If any branch may, it
   comments "may be used from any branch" on the issue and opens nothing.
3. **Recommended: only you may make `v*` tags.** The PR App can push branches and tags. `release.yml` refuses a tag on
   a commit that is not on `main`'s history, but it runs as it is in the tagged commit, so a tag on a commit of `main`
   from before that guard would still build. A tag ruleset closes that: **Settings** > **Rules** > **Rulesets** >
   **New ruleset** > **New tag ruleset**. Name it `release tags`; **Enforcement status:** Active; **Bypass list:** add
   **Repository admin** (you); **Target tags** > **Add target** > **Include by pattern** `v*`; tick **Restrict
   creations**, **Restrict updates** and **Restrict deletions** > **Create**.
4. Once the second key is pasted, put that `.pem` file in the Trash and empty it. GitHub can make a new key at any
   time.

## B. If bots show up: Cloudflare Turnstile (the check that a person is sending)

Off for now (Dan, 2026-10-19). Both sides are switched on by a key: the function asks Cloudflare only while
`TURNSTILE_SECRET` is set, and the page loads and requires the widget only while `turnstileSiteKey` is set in
`docs/assets/vineyard-config.js`. Set both, or neither: with only the secret set, the page sends no check and every
send is refused, so it ends at the email.

1. On dash.cloudflare.com, open **Turnstile** in the left menu (under "Application security" in the newer layout) and
   click **Add widget**.
2. **Widget name:** `HSD vineyard form`.
3. **Hostnames:** add `hickorysandsdistrictava.org`, then `localhost`. The function accepts only the site's own
   checks; `localhost` lets the widget be tried on your Mac.
4. **Widget mode:** Managed. **Pre-clearance:** No. Click **Create**.
5. Copy the **Site Key**. It is public: send it to Claude for the page. Claude puts it in `turnstileSiteKey` in a small
   pull request, and puts the Turnstile mention back on the site's About and Colophon pages.
6. Copy the **Secret Key**. In Supabase, **Edge Functions** > **Secrets**, add it as `TURNSTILE_SECRET`, and nowhere
   else. Do this when the page's pull request is merged: from then on, a send without a check is refused.
7. Run the check (step 6.1) again: its first line says "Person check (Turnstile): on", and all five checks pass.

## Day to day

- **A submission arrives:** an issue and the check's comment.
  - "Ready for review": approve it. With section A done, add the label `approved`; without it, tell Claude "approve
    #n" (section A). Either way a pull request opens and its checks run. Review it as every pull request, then merge
    it, and the site shows the vineyard.
  - "Something to look at": put it right first. The sender's contact is in Supabase's Table Editor: filter
    `issue_number` by the issue's number. To decline, close the issue as "not planned".
- **A change to a listed vineyard** ("Suggest a change", beside each vineyard in the list on the vineyards page and
  in its popup on The map): an issue titled "Vineyard change: <the listed name>", labelled `vineyard-submission` and
  `vineyard-change` (make that label once, step 2.1; until it is there, the function leaves it off and the issue
  still comes, with `vineyard-submission`). The issue shows what is listed now beside what the grower
  suggests, with the grower's short public note on what has changed, and both outlines on its map (listed grey,
  suggested gold). The check compares it with the vineyard file as it is now ("A change to ..."): it says "Nothing
  would change" when the suggestion is what is listed, and that the vineyard is not in the file when it was renamed
  or removed since. Approve it as a new vineyard (the label `approved`, or "approve #n" to Claude): the pull request
  "Vineyard change: <name> (#n)" replaces that vineyard's blocks and fields in
  `resources/vineyards/vineyards-EPSG4269.geojson`, under the same `vineyard_id`, never as a second entry. A block
  the grower left as it was keeps its outline, label, acres and source, with a note of the change added to the source;
  a block drawn anew gets "Changed through the website's vineyard form (GitHub issue #n) ...". A historical
  vineyard stays historical. The sender's contact is in the Table Editor, as for a new vineyard.
- **After a vineyard is added or changed** (its pull request merged): deploy the function again (step 5's "To update
  the function later"). The function knows the listed vineyards from the site's data as it was when the function was
  made (`docs/assets/vineyards/known.json`, in the bundle): until it is deployed again, a change to a vineyard added
  since is refused (the grower is offered the email), and a renamed vineyard's next change is titled by its old name.
- **A pin with no outline:** the blocks are drawn from imagery before approval.
  1. In QGIS, add Esri World Imagery (XYZ Tiles) and zoom to the pin (the issue's map shows it).
  2. Make a new GeoPackage or scratch polygon layer in EPSG:4326, and draw each block of vines along the rows' outer
     edges.
  3. Export the layer: right-click > **Export** > **Save Features As** > GeoJSON, CRS EPSG:4326, as `drawn.geojson`.
  4. In Terminal, at the repository's root (160 is the issue's number):
     `.venv/bin/python -E -s -B src/vineyards/outline_issue.py 160 drawn.geojson >body.md`
     then `gh issue edit 160 --body-file body.md`.
     The script refuses blocks that break a rule (outside the proposed Llano Uplift AVA, crossing edges).
  5. The check runs again on the edit. When it says "ready for review", approve it as above. The pull request records
     the blocks as drawn by the petitioners from the sender's pin.
- **Spam:** close it as "not planned", or delete the issue (Issues > the issue > Delete issue). If it keeps coming,
  set up Turnstile (section B). To stop a wave at once, remove the `IP_SALT` secret in Supabase: the function then
  answers "not ready", the page offers the email address, and the daily check fails until it is back. Add the same
  value again to reopen the form (a new value starts today's counts per connection again).
- **Contacts:** each row is deleted a year after its issue is closed. A deleted issue counts as closed on the day of
  its deletion. A row never tied to an issue (a send that died between GitHub and the table, and that the daily check
  could not tie to its issue) is deleted after a day.
- **The daily check failed:** an issue "Vineyard form: the daily check failed" says what failed. The function's logs
  are in Supabase (**Edge Functions** > `vineyard-submit` > **Logs**). Run **Actions** > **vineyard-reconcile** >
  **Run workflow** again once it is put right, and close the issue.
- **A private word, silently (off; your choice):** a name or variety with one of your private words is now refused
  with "The register can't show this name as written". The reply names no word, but a stranger could try word after
  word. Setting the Supabase secret `PRIVATE_WORDS_SILENT` to `1` holds such a vineyard instead: the sender is thanked
  as usual (with no reference number), nothing is posted, and the row in the Table Editor is marked `held` for you to
  read. It is deleted a year after it came.
- **A paused project:** Supabase pauses a free project after a week without activity. The page then offers the email
  address. Restore the project in the dashboard; it pauses vote-api too.
- **A new key:** on the App's page > **Private keys** > **Generate a private key**, paste it where the old one was
  (step 4, or step A.2 for the PR App), then delete the old key on the App's page.

## Where each secret lives

| secret | lives in | used by |
|---|---|---|
| form App's private key, App ID, installation ID | Supabase: Edge Functions > Secrets | the function: opens the issues |
| webhook secret | the form App's webhook settings, and Supabase | the function: knows an issue was closed |
| IP salt | Supabase | the function: the limits, without keeping any IP address |
| private words (optional) | GitHub: repository secret; Supabase (both, or neither) | the Actions and the function: refuse those words |
| the function's URL, for the daily check (not secret) | GitHub: repository variable `VINEYARD_FUNCTION_URL` | vineyard-reconcile |
| the function's URL (not secret) | `docs/assets/vineyard-config.js`, `endpoint` | the page |
| PR App's private key (section A, optional) | GitHub: environment `vineyard-pr` (main only) | vineyard-approve: the branch and the pull request |
| PR App's Client ID (section A; not secret) | GitHub: environment `vineyard-pr`, a variable | the same |
| Turnstile Secret Key (section B, only if bots show up) | Supabase | the function: the person check |
| Turnstile Site Key (section B; not secret) | `docs/assets/vineyard-config.js`, `turnstileSiteKey` | the page: the person check |
