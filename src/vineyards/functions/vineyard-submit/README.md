# vineyard-submit: the vineyard form's Supabase Edge Function

The one server of the vineyards page's form ("Add your vineyard"). It runs in the Supabase project "Hickory Sands
District AVA" (ref `yayebhncbagmebwgmezd`) beside vote-api, and leaves vote-api alone. The layout is the Supabase CLI's
(`functions/<name>/index.ts`), as issue #99 plans for vote-api under `src/vote/`.

| file | what it is |
|---|---|
| `index.ts` | the function: the form's POST, the GitHub App's webhook (`/github`) and a health check (`/health`); its header says what it does, step by step |
| `hsd_vineyard_contacts.sql` | the private table of contacts and `hsd_vineyard_reserve()`, which Dan runs once in the SQL editor |

`index.ts` imports two files that live elsewhere in the repository and are never copied here: the site's rules,
`docs/assets/vineyard-blocks.js` (the module the page runs, so the page and the function say the same thing), and TTB's
proposed Llano Uplift AVA as the site publishes it, `docs/assets/aquifer/llano-uplift.geojson`.
`src/vineyards/bundle_function.py` puts the three into one file, `target/vineyard-submit/index.ts`, which Dan pastes into
the dashboard's editor.

- Setting it up, deploying it and checking it: `src/vineyards/SETUP.md`.
- Tests: `tests/test_vineyard_function.py` runs the bundled file in node against stand-ins for the table, Turnstile and
  GitHub (`tests/vineyard_standin.mjs`); `tests/test_vineyard_sql.py` runs the SQL in a throwaway PostgreSQL;
  `tests/test_vineyard_rules.py` holds the rules to the Python twin, `src/vineyards/submission.py`.
- Secrets are set in the dashboard only; none is in these files. The function logs status codes and issue numbers,
  never a body, a contact or a secret.
