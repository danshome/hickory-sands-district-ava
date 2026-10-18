# Security policy

## Reporting a problem

Report a security problem privately, never in a public issue or pull request:

- **On GitHub:** [report a vulnerability](https://github.com/danshome/hickory-sands-district-ava/security/advisories/new)
  (the repository's Security tab, then *Report a vulnerability*). Only the maintainer sees it.
- **By email:** district@hickorysandsdistrictava.org.

Say what is affected, how to reproduce it, and what an attacker could do with it. Please do not test against anyone
else's data, and give us a reasonable time to fix a problem before you disclose it.

## What is in scope

- the build and its checks (`build.sh`, `src/`, `tests/`), and the Python packages it installs and audits;
- the GitHub Actions workflows (`.github/workflows/`);
- the website at hickorysandsdistrictava.org (`docs/`);
- the code that publishes to ArcGIS Online (`src/publish/`);
- the logo vote's backend (`vote-backend/`).

Out of scope: the third-party services themselves (GitHub, ArcGIS Online, Supabase, Google Fonts, Squarespace), and the
content of the proposal. Comments on the proposed boundary belong in TTB's docket, TTB-2026-0005.

## What to expect

The maintainer aims to acknowledge a report within seven days. A fix is made on its own branch through a pull request,
like every change here, and the reporter is credited unless they ask not to be.

## Supported versions

Only the current `main` branch and the live website are supported.
