# Security policy

## Reporting a problem

Report a security problem privately, never in a public issue or pull request:

- **On GitHub:** [report a vulnerability][report] (the repository's Security tab, then *Report a vulnerability*).
  Only the maintainer sees it.
- **By email:** district@hickorysandsdistrictava.org.

Say what is affected, how to reproduce it, and what an attacker could do with it. Please do not test against anyone
else's data, and give the maintainer a reasonable time to fix a problem before you disclose it.

## What is in scope

- the build and its checks (`build.sh`, `src/`, `tests/`), including how it pins and audits its Python packages (a
  flaw in a package itself goes to that package's maintainers);
- the GitHub Actions workflows (`.github/workflows/`);
- the website at hickorysandsdistrictava.org (`docs/`);
- the code that publishes to ArcGIS Online (`src/publish/`);
- the logo vote's page and backend (`docs/logo-vote.html`, `src/vote/`).

Out of scope: the third-party services themselves (GitHub, ArcGIS Online, Supabase, Google Fonts, Squarespace), and the
content of the proposal. Comments on the proposed boundary belong in TTB's docket, TTB-2026-0005.

## What to expect

The maintainer aims to acknowledge a report within seven days. A security fix does not start from a public issue: it is
made in the advisory's temporary private fork and merged through that fork's pull request, so nothing about the problem
is public until the fix is in and the advisory is published. The reporter is credited unless they ask not to be.

## Supported versions

Only the current `main` branch and the live website are supported.

[report]: https://github.com/danshome/hickory-sands-district-ava/security/advisories/new
