# Setting up "Add your vineyard": a guide for Dan

The vineyards page's form (docs/vineyards.html, "Add your vineyard") sends a grower's vineyard to one Supabase Edge
Function, `vineyard-submit`. The function keeps the grower's name, phone and email in one locked table and opens a
public GitHub issue with the vineyard's public fields only. The `vineyard-check` Action comments on the issue. Your label
`approved` makes the `vineyard-approve` Action open the pull request that adds the vineyard, and merging that pull request
puts it on the site.

The code in the repository does nothing until you have set it up. Until then the page offers the email instead (once the
page's pull request is merged). This guide is click by click. Every secret is pasted by you and goes only where it says:
never into the repository, a pull request, an issue or a chat.

**Two things that differ from the proposal (§11), and why:**

1. **Two GitHub Apps, not one App and a personal token.** The form's App, "HSD vineyard form", can only open issues and
   comment. Its key lives in Supabase, and anything that can deploy a function to that project can read every secret
   there. vote-api is deployed there by another agent's credential. The second App, "HSD vineyard PR", can push
   branches and open pull requests. Its key lives only in the GitHub environment `vineyard-pr`, which only `main`'s own
   workflow can use. Two Apps keep a write path to the code out of Supabase. An App's key never expires, unlike a
   personal token, and a pull request opened by an App runs every check. The fallback, if you would rather not make a
   second App, is the proposal's fine-grained token ("token 2"); ask Claude to switch the workflow back.
2. **The form App also has a webhook.** It is how the function learns that an issue was closed: you asked for a contact
   to be deleted one year after its issue is closed. The function records the closing date and deletes the rows closed
   more than a year ago each time it runs: on every send, and every time GitHub tells it about an issue. This repository
   has issue events most days, so the deletion runs often. If you want it to run at an exact time each day, Supabase's
   pg_cron can do the same deletion on a schedule; ask Claude.

Allow about an hour. Do the steps in order, after the machinery's pull request (the one that adds this file) is merged.
The page's pull request comes last (step 9).

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
     your password manager as "HSD vineyard webhook secret": you paste it again in step 6.
   - **SSL verification:** Enable.
6. **Permissions** > **Repository permissions** > **Issues:** "Read and write". Leave everything else at "No access".
   **Metadata** turns to "Read-only" by itself.
7. **Subscribe to events:** tick **Issues**.
8. **Where can this GitHub App be installed?** "Only on this account".
9. Click **Create GitHub App**.
10. On the App's page, under **About**, copy the **App ID** (a number). Keep it: it is `GITHUB_APP_ID` in step 6.
11. Scroll to **Private keys** > **Generate a private key**. A `.pem` file downloads. It is `GITHUB_APP_PRIVATE_KEY`
    in step 6.
12. In the left menu, click **Install App** > **Install** (beside danshome) > **Only select repositories** >
    `hickory-sands-district-ava` > **Install**.
13. You land on a page whose address ends in `/settings/installations/` and a number. Copy that number: it is the
    installation ID, `GITHUB_APP_INSTALLATION_ID` in step 6.

GitHub sends the webhook a "ping" now. It fails until step 7, and that does no harm.

## 2. The pull request's GitHub App: "HSD vineyard PR"

1. **Developer settings** > **GitHub Apps** > **New GitHub App** again.
2. **GitHub App name:** `HSD vineyard PR`. **Homepage URL:** `https://hickorysandsdistrictava.org`.
3. **Webhook:** untick **Active** (this App needs none).
4. **Repository permissions:** **Contents:** "Read and write"; **Pull requests:** "Read and write". Nothing else.
5. "Only on this account" > **Create GitHub App**.
6. Under **About**, copy the **Client ID** (it starts `Iv`). It is `VINEYARD_PR_CLIENT_ID` in step 3.
7. **Private keys** > **Generate a private key**. A second `.pem` file downloads: `VINEYARD_PR_PRIVATE_KEY` in step 3.
8. **Install App** > **Install** > **Only select repositories** > `hickory-sands-district-ava` > **Install**.

Optional, and a second lock: the `main` ruleset could also require one approval. Neither App could then merge a pull
request, and your own merges with `--admin` would go on as now. Settings > Rules > Rulesets > the ruleset for `main` >
"Require a pull request before merging" > "Required approvals: 1".

## 3. GitHub: the labels, the environment and the secrets

1. **Labels.** In the repository: **Issues** > **Labels** > **New label**, three times: `vineyard-submission`,
   `approved` and `vineyard-data`. Any colours. The form's App applies an existing label; it cannot make one.
2. **The environment, before the first approval** (a workflow that names a missing environment makes it, unprotected).
   Repository **Settings** > **Environments** > **New environment** > name `vineyard-pr` > **Configure environment**:
   - **Deployment branches and tags:** choose "Selected branches and tags" > **Add deployment branch or tag rule** >
     `main` > **Add rule**.
   - Optional: **Required reviewers:** add yourself. Each approval then waits for one more click in the Actions tab.
   - **Environment secrets** > **Add environment secret:** name `VINEYARD_PR_PRIVATE_KEY`; value: the whole second
     `.pem` file. To copy it, run `pbcopy < ~/Downloads/` followed by the file's name (it starts `hsd-vineyard-pr.`).
   - **Environment variables** > **Add environment variable:** name `VINEYARD_PR_CLIENT_ID`; value: the Client ID from
     step 2.6.
3. **The private words** (optional, recommended). **Settings** > **Secrets and variables** > **Actions** > **New
   repository secret:** name `PRIVATE_WORDS`; value: your `.private-words` list (`pbcopy < .private-words` from the main
   checkout). The Actions then refuse a public field that holds one of the words, and never print them.
4. Once the second key is pasted, put that `.pem` file in the Trash and empty it. GitHub can make a new key at any time.

## 4. Cloudflare Turnstile (the check that a person is sending)

1. On dash.cloudflare.com, open **Turnstile** in the left menu (under "Application security" in the newer layout) and
   click **Add widget**.
2. **Widget name:** `HSD vineyard form`.
3. **Hostnames:** add `hickorysandsdistrictava.org`, then `localhost`. The function accepts only the site's own
   checks; `localhost` lets the widget be tried on your Mac.
4. **Widget mode:** Managed. **Pre-clearance:** No. Click **Create**.
5. Copy the **Site Key**. It is public: send it to Claude for the page (step 9).
6. Copy the **Secret Key**. It is `TURNSTILE_SECRET` in step 6, and nowhere else.

## 5. Supabase: the table

1. On supabase.com/dashboard, open the project **Hickory Sands District AVA** (ref `yayebhncbagmebwgmezd`, the one
   that runs vote-api).
2. In the left menu, click **SQL Editor** > **New query** (the + at the top).
3. In Terminal, at the repository's root, run
   `pbcopy < src/vineyards/functions/vineyard-submit/hsd_vineyard_contacts.sql`, then click into the editor and paste.
4. Click **Run**. You should see "Success. No rows returned".
5. Check it: **Table Editor** lists `hsd_vineyard_contacts`, marked as having row level security on.

The SQL makes only things named `hsd_vineyard_...`: one table, two indexes and one function. It changes nothing of
vote-api's, and running it again changes nothing.

## 6. Supabase: the function's secrets

1. In the left menu, click **Edge Functions** > **Secrets**.
2. Add each one (Key, then Value), and click **Save** when all are in:

   | Key | Value |
   |---|---|
   | `GITHUB_APP_ID` | the form App's App ID (step 1.10) |
   | `GITHUB_APP_INSTALLATION_ID` | the installation number (step 1.13) |
   | `GITHUB_APP_PRIVATE_KEY` | the whole first `.pem` file: run `pbcopy < ~/Downloads/` and the file's name (it starts `hsd-vineyard-form.`). Pasted with or without its line breaks, the function reads it. |
   | `GITHUB_WEBHOOK_SECRET` | the webhook secret from step 1.5 |
   | `TURNSTILE_SECRET` | Turnstile's Secret Key (step 4.6) |
   | `IP_SALT` | new random text: `openssl rand -hex 32 \| pbcopy` |
   | `PRIVATE_WORDS` | optional: the same list as in step 3.3 |

3. Put the first `.pem` file in the Trash and empty it.

A project's secrets are shared by all its functions. vote-api reads only its own (`OPERATOR_KEY`), and its code is
not changed.

## 7. Supabase: deploy the function

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
   off and save. The check in step 8 says so if it is still on.

Leave vote-api alone. To update the function later: run the same command, open `vineyard-submit` > **Code**, select
all, paste and click **Deploy updates**.

## 8. Check that it works

1. In Terminal, at the repository's root: `.venv/bin/python -E -s -B src/vineyards/check_function.py`.
   Success is four lines starting `PASS`, then "All four checks passed.":
   - the function answers and every secret is set (if not, it names the missing secrets; a 401 means JWT
     verification is still on);
   - the site may send to it;
   - another site may not;
   - a send without the person check is refused.

   The first line also shows which address headers reach the function, names only (for example
   `['cf-connecting-ip', 'x-forwarded-for']`). Tell Claude what it says: the limit of five sends a day from one
   connection uses the first of these.
2. GitHub: the form App's page > **Advanced** > **Recent Deliveries**. Open the failed "ping" > **Redeliver**. It
   should now show 200.
3. After the page's pull request is merged (step 9), send a test from your phone:
   hickorysandsdistrictava.org/vineyards.html > **Add my vineyard**. Draw one small block on any vineyard, name it
   `Test vineyard`, put in your own phone or email, tick both boxes and **Send**. Success:
   - the thank-you screen gives a reference number, say 160;
   - within a minute, issue #160 appears, opened by `hsd-vineyard-form[bot]` with the label `vineyard-submission`
     and the block drawn on a map, then a comment by `github-actions[bot]` headed "The check: ...";
   - in Supabase's **Table Editor** > `hsd_vineyard_contacts`, one row with your contact and `issue_number` 160.
4. Close the test issue as "not planned". Within seconds, its row's `closed_at` is filled in (refresh the Table
   Editor). The row is deleted a year later; you may delete the test row now (select it > Delete).

Leaving the test issue without the label keeps the site unchanged. To try the approval as well, add `approved`: a pull
request "Vineyard: Test vineyard (#160)" opens. Close it without merging and delete its branch.

## 9. The page

Send Claude the Turnstile **Site Key** (step 4.5). The function's address is already known:
`https://yayebhncbagmebwgmezd.supabase.co/functions/v1/vineyard-submit`. Both are public and go into
`docs/assets/vineyard-config.js` in a small pull request. Until they are there, the page's form ends at the email
fallback.

## Day to day

- **A submission arrives:** an issue and the check's comment.
  - "Ready for review": add the label `approved`. A pull request opens; its checks run. Review it as every pull
    request, then merge it, and the site shows the vineyard.
  - "Something to look at": put it right first. The sender's contact is in Supabase's Table Editor: filter
    `issue_number` by the issue's number. To decline, close the issue as "not planned".
- **A pin with no outline:** the blocks are drawn from imagery before approval.
  1. In QGIS, add Esri World Imagery (XYZ Tiles) and zoom to the pin (the issue's map shows it).
  2. Make a new GeoPackage or scratch polygon layer in EPSG:4326, and draw each block of vines along the rows' outer
     edges.
  3. Export the layer: right-click > **Export** > **Save Features As** > GeoJSON, CRS EPSG:4326, as `drawn.geojson`.
  4. In Terminal, at the repository's root (160 is the issue's number):
     `.venv/bin/python -E -s -B src/vineyards/outline_issue.py 160 drawn.geojson >body.md`
     then `gh issue edit 160 --body-file body.md`.
     The script refuses blocks that break a rule (outside the proposed Llano Uplift AVA, crossing edges).
  5. The check runs again on the edit. When it says "ready for review", add `approved`. The pull request records the
     blocks as drawn by the petitioners from the sender's pin.
- **Spam:** close it as "not planned", or delete the issue (Issues > the issue > Delete issue). To stop a wave of
  spam, remove the `TURNSTILE_SECRET` secret in Supabase. The function then answers "not ready" and the page offers
  the email address. Add the secret again to reopen the form.
- **Contacts:** each row is deleted a year after its issue is closed. A deleted issue counts as closed on the day of
  its deletion.
- **A paused project:** Supabase pauses a free project after a week without activity. The page then offers the email
  address. Restore the project in the dashboard; it pauses vote-api too.
- **A new key:** on the App's page > **Private keys** > **Generate a private key**, paste it where the old one was
  (step 3.2 or step 6), then delete the old key on the App's page.

## Where each secret lives

| secret | lives in | used by |
|---|---|---|
| form App's private key, App ID, installation ID | Supabase: Edge Functions > Secrets | the function: opens the issues |
| webhook secret | the form App's webhook settings, and Supabase | the function: knows an issue was closed |
| Turnstile Secret Key | Supabase | the function: the person check |
| IP salt | Supabase | the function: the limits, without keeping any IP address |
| PR App's private key | GitHub: environment `vineyard-pr` (main only) | vineyard-approve: the branch and the pull request |
| PR App's Client ID (not secret) | GitHub: environment `vineyard-pr`, a variable | the same |
| private words (optional) | GitHub: repository secret; Supabase | the Actions and the function: refuse those words |
| Turnstile Site Key, the function's URL (not secret) | `docs/assets/vineyard-config.js` | the page |
