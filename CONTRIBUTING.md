# Contributing

This repository holds the Hickory Sands District AVA boundary as proposed to TTB (Docket TTB-2026-0005, Notice No. 243,
91 FR 52576), the build that draws it on the USGS quadrangles and packages it, and the district's website. It is public,
and its maintainer is Dan McLaughlin, for the petitioners. The same rules apply to people and to AI agents. Agents also
read [AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md).

## Reporting a problem

Open a [GitHub issue](https://github.com/danshome/hickory-sands-district-ava/issues). Say what is wrong and where:
- the step number, the quadrangle, the coordinates, or the page and link;
- what you expected;
- what you saw (a screenshot or a link to the map helps).

A security problem is reported privately instead, as [SECURITY.md](SECURITY.md) explains. An issue is a claim to check,
not an order: each one is checked against the source before anything changes. Comments on the proposal itself belong in
TTB's docket, not here: https://www.regulations.gov/docket/TTB-2026-0005.

## Proposing a change

Every change, however small, goes the same way:

1. **An issue** that says what should change and why. Open one, or name the one you are fixing. A security fix is the
   exception: it starts from its private report and stays private until fixed ([SECURITY.md](SECURITY.md)).
2. **A branch off `main`**, named by kind and topic: `docs/...`, `fix/...`, `feature/...`, `qa/...`.
3. **Commits that pass the commit hooks.** Never skip them with `--no-verify`.
4. **A pull request to `main`** that says `Fixes #n`, what changed, why, and how you checked it. GitHub runs the hooks
   and the tests on it, and the whole build when the build's inputs change.
5. **The maintainer reviews it and merges it.** Before merging, the maintainer's Claude Code session also reviews every
   pull request to `main` with the `pr-review-toolkit` plugin's `/pr-review-toolkit:review-pr` and with Claude Code's
   `/security-review`. Their findings come back in the pull request, to be fixed on the branch or answered there. Nobody
   can push to `main` directly; the branch is protected.

Keep a pull request to one change. Something else you notice on the way gets its own issue.

## Setting up and checking your work

macOS or Linux with [Homebrew](https://brew.sh). From the repository's root:

```
./build.sh env        # the project's .venv (hash-pinned, audited packages) and the commit hooks
./build.sh lint       # every commit hook on every file
./build.sh test       # the unit tests
./build.sh            # the whole build, into dist/
```

[BUILD.md](BUILD.md) explains the stages, the checks, the tests and the GitHub Actions workflows.

## Where things go

| What                                   | Where                                                              |
|----------------------------------------|--------------------------------------------------------------------|
| Code                                   | `src/<area>/` (quads, tracing, fixing, review, boundary, documents, checks, package, publish, setup) |
| The build's inputs                     | `resources/` (the boundary's are in `resources/boundary/`)         |
| Templates for the package's documents  | `documents/`                                                       |
| The website, hickorysandsdistrictava.org | `docs/`                                                          |
| Tests                                  | `tests/`                                                           |
| GitHub Actions                         | `.github/workflows/`                                               |
| Everything the build makes             | `target/` and `dist/` (never committed)                            |
| Research, audits, design proposals, prototypes, until ready | `research/` (gitignored: never committed; never in `target/`) |

A new top-level folder needs an issue that agrees to it first.

## Standards

- **Python** follows the Google Python Style Guide: `ruff format` at 80 columns, and every rule in `ruff.toml`, with no
  exceptions list. Tests go in `tests/`, run by pytest.
- **No secrets.** Tokens, keys, passwords and connection strings never go into a file, a commit or an issue. The
  `detect-secrets` hook looks for them.
- **The boundary changes only through `resources/boundary/`**, followed by a rebuild. Never edit the build's outputs.
  No geometry is copied from an existing boundary layer: every coordinate is a pin on a printed mark, a straight line
  between pins, or a trace of the centre of the printed ink.
- **Wording.** The boundary is "proposed", never "agreed". Use the official names: Notice No. 243 (TTB's published
  text), the AVA Map Explorer polygon (TTB's layer), the proposed revision (this boundary).
- **The petition and Comment 9.** Everything public agrees with the petition (as amended June 6, 2023) and Comment 9,
  the petitioners' response to Comment 8, and every statement is backed by a published source. Raise any question
  about either document with the maintainer privately, never in an issue or pull request.
- **New website features** start as a design and a working prototype (in `research/`), are checked by someone other
  than their author (facts and sources, usability, security), and are built only after the maintainer approves the
  prototype. A finding is confirmed independently before it goes to anyone outside the project.
- **The website.** Merging a change to `docs/` publishes it at hickorysandsdistrictava.org; `site.yml` tests it first.
  Test every change at phone sizes before the pull request: `./build.sh check-site --local` runs
  `tests/live/test_site_mobile.py` against a local server of your branch; after the deploy, `./build.sh check-site`
  runs it against the live site ([BUILD.md](BUILD.md)). After changing a script or stylesheet in `docs/`, run
  `./build.sh stamp` and commit what it changes: every URL that loads one carries a hash of the file, so browsers
  fetch a changed file at once, and the checks (`tests/test_site.py`, the build) fail on a stale one.
- **Publishing** to ArcGIS Online, tagging releases, and changing DNS or the domains are the maintainer's alone.

## Conduct

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

The petitioners' work here is dedicated to the public domain under CC0 1.0 ([LICENSE.txt](LICENSE.txt)). By sending a
pull request you agree that your contribution is dedicated in the same way.
