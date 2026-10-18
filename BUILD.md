# Building the Hickory Sands District AVA package for TTB

One command, run from the repository root, rebuilds everything that goes to TTB from source. No manual steps:

```
./build.sh
```

It installs what is missing (GDAL, poppler, Python 3.14, and on macOS Google Chrome, via Homebrew, on macOS or Linux), checks every Python package it will
install against the OSV vulnerability database, creates the project's Python environment `.venv` from the hash-pinned
`requirements.txt` (nothing global), downloads any USGS quad that is missing or altered, builds, checks, and packages. The result is in `dist/`:

| file | what it is |
|---|---|
| `Hickory-Sands-District-AVA_boundary-as-proposed-<revision date>.zip` | the package to upload: description (PDF/DOCX/TXT/CSV), TTB's Notice 243 with the changes highlighted, the side-by-side, GIS (GeoPackage, GeoJSON, shapefiles), the 13 USGS quads with the boundary |
| `...-README.txt` | the package's README, for reading without unzipping |
| `SHA256SUMS.txt` | checksums of the above |
| `build-report.txt` | area, step count, check results, source commit |

Two builds of the same commit on the same machine give the same bytes (issue #65). Every date and time the build writes
into what it makes (the PDFs' CreationDate and ModDate, the times of the members of every zip, the Word files included,
the GeoPackage's `last_change`, the shapefiles' `.dbf` headers) is the revision's date
(`resources/boundary/revision-date.txt`), as in the file names, at 00:00 UTC: `build.sh` works it out and exports it as
`SOURCE_DATE_EPOCH` (1792022400 for 2026-10-15), the
[reproducible-builds.org](https://reproducible-builds.org/specs/source-date-epoch/) convention, unless the environment
already sets it, and the scripts read it from there (a script run alone without it uses the present time). Chrome cannot
be told a date, so `src/documents/pdf_dates.py` dates its PDFs after printing; the notice copy keeps the first part of
GPO's file identifier (`/ID`), and its second part is the MD5 of the copy's bytes. Only the build report's `built` line,
which is not in the zip, says when the build ran.

Other commands:

- `./build.sh env` sets up the tools, `.venv` and the git pre-commit hooks only.
- `./build.sh lint` runs every pre-commit hook on every file.
- `./build.sh test` runs the unit tests (see Tests below).
- `./build.sh audit` re-checks the lock files (OSV) and the installed `.venv` (pip-audit, PyPI and OSV databases).
- `./build.sh upgrade` moves every Python package to its latest compatible version, audits, and rebuilds `.venv`.
- `./build.sh clean` removes `target/` and `dist/`.
- `./build.sh distclean` also removes `.venv`.
- `./build.sh publish` pushes the built package to ArcGIS Online: items, descriptions, metadata, categories, the hosted
  layers (the boundary, the differences from the AVA Map Explorer polygon, the change near Grit, the shifted geology),
  the web map over the 13 quads with TTB's live AVA Map Explorer polygon, and the dashboard that links everything; it
  makes the folder if it is missing and shares everything publicly. It signs in with Dan's saved `arcgis` profile `hsd`.
  Publishing is never part of a normal build; run it only when you mean to update ArcGIS Online. Its first step is the
  publish dry run below, and it uploads nothing if one of its checks fails; its last step is `check-live`, so a publish
  ends with the live site's pass/fail report.
- `./build.sh publish-dry-run` (or `./build.sh publish --dry-run`) builds everything the publish would send, from the
  build's outputs, without signing in or touching the network (`src/publish/agol_dryrun.py`, issue #58): it calls the
  publish scripts' own builders (each script builds what it sends in functions that need no sign-in, and its `main()`
  signs in and sends it), never their `main()`, and `arcgis.gis.GIS` is replaced by one that raises. What only ArcGIS
  knows, item ids, service URLs and the hosted layers' fields, comes from stand-ins: the group's item list in
  `tests/fixtures/publish/agol-items.json` (fake ids, and the layers' public definitions; `agol_dryrun.py --fetch FILE`
  writes it again, anonymously). It writes `target/publish/`: `items.json` (every item's title, type, file, group and
  organization categories, and the properties it is sent: summary, description, tags, licence, credits, extent,
  culture), `services.json` (each hosted layer's definition, layer names, field aliases, visualization), `webmap.json`,
  `dashboard.json`, `group.json` (access, tags, description), `item-list.json`, `facts.json`; then checks them
  (`src/publish/agol_dryrun_checks.py`, one line per check, exit 1 on a failure):
  - items: the publish makes exactly the items of the group's item list (a new, retitled or dropped item fails until
    the fixture is updated with it);
  - security: every hosted layer is set read-only, capabilities Query,Extract (#25);
  - web map: the quadrangles with no band legend, a short pop-up naming the sheet, years without a thousands separator
    and no time filter (#46); every layer a layer of a hosted item in the group or a known service;
  - dashboard: the desktop and phone views both there and wired (`check_views()`, which `agol_dashboard.py` also runs
    before sending), its map and data sources the web map's; every link to an item goes to one in the list and its text
    is in that item's title; every item linked; indicator captions within their width (#45); link cells in tables that
    do not wrap (#47);
  - metadata: culture `en-us`, the tags "Notice No. 243" and "TTB-2026-0005", credits, an extent around the AVA on every
    item numbered 4 or 5, a group category under the item's number (#31);
  - licences: each names the terms of what the item carries, TTB's text and data, USGS's maps and geology, Esri's
    basemaps, the petitioner's work under CC0 (#11, #30; the table `LICENCES`), and the credits name them;
  - descriptions: each has its own text beyond the shared opening and a summary of 45 characters or more (#34); the Word
    files and the CSV say what they are, TTB's notice is not "prepared by" the petitioner, a layer offering exports says
    they are Web Mercator and where the NAD83 data is (#29);
  - quadrangle titles: a GeoPDF and a GeoTIFF for each quadrangle of paragraph (b), titled with its edition (#44);
  - wording: no "agreed", "ours", "our boundary", "TTB's published polygon", "final text" or bare "Hickory Sandstone";
  - group: public, its tags, its description linking the dashboard and the read-me.
- `./build.sh check-live` checks the public site the way TTB sees it, without signing in (`src/publish/agol_check.py`,
  anonymous read-only requests; it changes nothing, so it is safe to run any time). One line per check, and every failure
  names the item and what is wrong; it exits 1 on any failure:
  - security: no hosted feature service in the group, nor any of its layers, allows Create, Update, Delete, Editing or
    Sync, and sync is off;
  - sharing: the group and every item in it are public, one item for each number (0 Read me first, 0 Dashboard,
    1a-1d, 2a-2d, 3a-3b, 4a-4o, a 5a and a 5b for each of the 13 quadrangles; `CODES` in the script);
  - links: every URL in the group's description, the items' descriptions, snippets, licenses and credits, and the
    dashboard answers 200, and every link to an item goes to a public item in the group with the title it names;
  - web map: every layer and basemap URL answers without an error and each layer's item is in the group;
  - dashboard: its JSON parses, its layout, data sources and actions name widgets and web map layers that exist, its
    map is the group's web map and it links every other item; no phone layout (`mobileView`) yet is only a note (#49);
  - figures, against the build's outputs in `target/work` (run by hand, `HSD_WORK` can point at another copy of them;
    `./build.sh` always sets it to `target/work`): the AVA polygon's area (0.01 sq mi), the
    steps and points, the differences from the AVA Map Explorer polygon (pieces and acres by cause and side, each
    big difference's acres, 0.1 acre), the change near Grit (acres, granite, sandstone, 0.01 acre);
  - files: each uploaded file is the size of the one just built (and, up to 4 MB, downloaded and the same SHA-256),
    and the documents attached to the AVA polygon match the build's.

  Without build outputs the figures and files are skipped with a note. Then it runs the browser tests of the published
  dashboard (`tests/live`, see Tests below). Right after a publish ArcGIS can take a minute to show a change to anonymous
  users: run `./build.sh check-live` again before chasing a failure.

The only prerequisites are Homebrew (https://brew.sh, on macOS or Linux), Google Chrome on Linux, and network access the
first time (packages and quads).

## Project layout

```
build.sh                 the build
requirements.in          the Python packages the build uses (edit this)
requirements.txt         compiled from it: every package and indirect dependency pinned, with SHA-256 hashes
requirements-dev.in/.txt the same for the lint, audit and lock tools, pytest and Playwright
.pre-commit-config.yaml  the hooks; .githooks/pre-commit runs them; ruff.toml, .codespellrc, .secrets.baseline;
                         .editorconfig: the same rules for editors
pytest.ini, tests/       the unit tests (./build.sh test); tests/live/: the browser tests of the dashboard (check-live);
                         tests/fixtures/publish/: the publish dry run's item list and a dry run
README.md, BUILD.md      this documentation; CLAUDE.md: notes for Claude Code; LICENSE.txt
src/
  setup/                 packages.py: the security audit of the lock files (standard library only), lock helper
  quads/                 fetch_quads (the 13 USGS quads, MD5-checked), build_cropped_quads (neatline VRTs for viewing)
  tracing/               traces each "along the road / creek / contour" step onto the centre of the printed ink
  fixing/                hand patches: patchlib (making them) and apply_patches (splicing them onto the traces)
  review/                tipcheck (tips the line stops short of), compare_ttb (vs the AVA Map Explorer polygon),
                         grit_change (the change near Grit, acre by acre, with its granite), triage tools
  boundary/              ink_centerline (runs the tracer), build_proposed (pins, polygon, GIS), quad sheets, TTB record
  documents/             description, side-by-side, notice copy, DOCX, README / read-me-first, PDF text, PDF dates
  checks/                hard checks: quads vs manifest, every pin on its line, no self-crossing, valid polygon;
                         check_outputs: what reaches TTB (PDF fonts, compare text, figures, wording, GIS, zip paths)
  package/               make_package.sh (the zip)
  site/                  make_site_data: the website's map data (docs/data/) from the boundary build
  publish/               ArcGIS Online: agol_publish, agol_layer, agol_dashboard, agol_org_categories, agol_share (what
                         is sent); agol_dryrun + agol_dryrun_checks (the dry run); agol_check (the live site)
resources/
  boundary/              what the boundary is built from (edit these, never the outputs); see resources/boundary/README.md
    revision-date.txt    the proposed revision's date (YYYY-MM-DD), typed only here (src/revision.py reads it)
    description/         the step texts: TTB's Notice 243, the petition
    proposed/            the proposed ring (Oct. 15), the Oct. 14 step lines and points, the Grit detour pins
    tracing/             pin-moves.json, trace priors, route overrides, hand-patches-EPSG4269.geojson
  ttb/                   TTB's Notice 243 PDF, the Federal Register's full-text XML of it (byte for byte), the
                         AVAs_Production record and polygon snapshot
  geology/               USGS SGMC units shifted to the outcrops, for the map only; see resources/geology/README.md
  quads/                 quads-manifest.csv, cropped/ (neatline VRT templates); geotiff/ and geopdf/ are downloaded
documents/               hand-written texts: README.template.txt ({AREA_SQMI} filled by the build),
                         read-me-first.template.html
docs/                    the website, hickorysandsdistrictava.org, as GitHub Pages serves it (site.yml deploys it);
                         docs/data/: its map data, made by the build (./build.sh site-data), never edited by hand
LICENSE.txt              CC0 1.0 (also copied into the package)
.venv/                   the project's Python environment (made by build.sh; not in git)
target/                  everything the build makes (not in git): work/ (recreated on every run), quads-cropped/,
                         publish/ (the publish dry run)
dist/                    the distribution (not in git)
tobedeleted/             set aside for review and deletion, used by nothing (not in git)
```

## The stages and the checks

1. **tools and .venv** - Homebrew GDAL / Python 3.14 / Chrome if missing; the security audit; `.venv` from the lock.
2. **quads** - the 13 quads checked against their MD5s in `quads-manifest.csv`; missing or altered ones downloaded.
3. **stage** - a fresh `target/work/`; the inputs are read in place from `resources/`.
4. **trace** - every follow step traced onto the ink (`src/boundary/ink_centerline.py`), pins from `tracing/pin-moves.json`,
   route hints from `tracing/route-overrides-EPSG4269.geojson`. Deterministic: two runs on one machine give identical lines (two
   machines can place a vertex differently along the same ink: #116).
5. **hand patches** - spliced onto the traces; a patch whose ends no longer lie on the trace stops the build (redo
   that patch). Patch joins that turn more than 25 degrees are rounded.
6. **boundary** - pins, straight-line steps, traced steps, polygon, points, GeoPackage, shapefiles.
7. **checks** - hard (stop the build): every pin exactly on its two steps; no step line crosses
   itself; the polygon is valid; the step text uses only the Federal Register's characters and TTB's 96 steps are
   identical to the Federal Register's XML (`src/checks/check_step_text.py`, also a commit hook). Reports (in `target/work/review/`): tips of contours the line stops short of; where the
   proposed revision and the AVA Map Explorer polygon differ (rings beyond hand-drawing noise, the big differences 100 m
   or more apart, and every piece of land between the two lines); the change near Grit, line by line and acre by acre,
   with the granite in each piece (`src/review/grit_change.py`).
8. **documents**, 9. **quad sheets**, 10. **package** into `dist/`, with `build-report.txt`. Then hard checks on what
   reaches TTB (`src/checks/check_outputs.py`, output in `target/work/review/output-checks.txt` and the build report):
   every font embedded in the PDFs the build makes and none Mac-only (Helvetica Neue, Menlo); the notice copy (2a)
   with no AcroForm, /Perms, document XMP, signature or annotation but links; the two compare-text files differing in
   exactly the steps whose `change` in `proposed-steps.json` is not "unchanged", as the proposed text, and README.txt
   naming those steps; the area and README.md's figures equal to the build's statistics, rounded once, half up;
   no "agreed", "ours", "our boundary", "TTB's published polygon", "final text" or bare "Hickory Sandstone" in a
   generated document; every point's and step end's `quad` the quadrangle whose neatline holds it (the 7.5-minute
   NAD27 cell, through NADCON 5.0 CONUS), every `length_m` geodesic, every layer and `.prj` NAD83. A warning, not a
   failure: zip paths longer than Windows' 260-character limit when Explorer extracts the zip under
   `C:\Users\<name>\Downloads\` (Dan: leave the names for now).
11. **site data** - last, so it never holds back the package: the website's map data (`src/site/make_site_data.py`),
   hard. `docs/data/`, the walk page `docs/walk.html` and every figure marked `data-figure` in the site's pages must
   match this build, so a boundary change stops the build until `./build.sh site-data` refreshes them and they are
   committed with the change. Only the traced lines may differ, and only a little: two machines
   (even two of GitHub's Linux runners) can place a vertex differently along the same ink (#116), so lines within 5 m
   of each other are reported in metres, not failed.

## Python packages and security

`requirements.in` and `requirements-dev.in` name the packages; `./build.sh upgrade` compiles them (pip-compile) into
`requirements.txt` and `requirements-dev.txt`, with every package, every indirect dependency and pip itself pinned to the
latest compatible version and every downloadable file's SHA-256 recorded. Never edit the `.txt` files by hand.

Every build, before installing anything, sends every pinned version to the OSV vulnerability database (osv.dev: PyPA and
GitHub advisories, CVEs) with `src/setup/packages.py`, which uses only Python's standard library. Any known
vulnerability stops the build, naming the advisory, the CVE and the fixed version. When the lock files change, `.venv` is
recreated and filled only from them with `pip install --require-hashes`, so a download that does not match its recorded
hash is refused. Offline, a build continues only when `.venv` already holds exactly the audited lock.

Three indirect dependencies are held below their latest versions by Esri's `arcgis` package (latest 2.4.3): dask < 2025.3,
pyarrow < 24, puremagic < 2. They stay at the newest versions `arcgis` allows, and the audit covers them like every
other package. `GDAL` must equal Homebrew's GDAL library (`gdal-config --version`); the build stops if they differ.

## Commits: the pre-commit hooks

`./build.sh env` (and every build) installs the lint tools into `.venv` and points git at `.githooks/`, so every
`git commit` runs the hooks in `.pre-commit-config.yaml` on the staged files, all from `.venv` (nothing global):

- files: no files over 2 MB, no case clashes or names Windows cannot hold, no merge-conflict markers, no broken or
  replaced symlinks, no submodules, shebangs and executable bits agree, LF line endings, no trailing whitespace, one
  final newline, no byte-order marks, JSON/GeoJSON/YAML/TOML parse, permanent links to code;
- step text: only the Federal Register's characters (no en or em dashes, curly apostrophes, non-breaking or hidden
  spaces), and TTB's steps identical to the Federal Register's XML;
- secrets and private material: no private keys; detect-secrets (passwords, tokens, API keys; the three known false
  alarms are recorded in `.secrets.baseline`); no word listed in `.private-words` (gitignored: put names that must
  never be committed there, one per line); the OSV audit whenever a requirements file changes;
- Python: parses, no debugger calls, literals not `list()`; laid out by `ruff format`; `ruff check` with the rules
  in `ruff.toml` (below);
- shell: shellcheck (warnings and errors); spelling: codespell (`.codespellrc`).

Hooks that fix files (whitespace, newlines, line endings, Python layout) stop the commit after fixing; `git add` the
fixes and commit again. Run them all with `./build.sh lint`.

### Python style

The Python follows the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) (no federal or
TTB rule covers code): lines of at most 80 columns (long URLs excepted), 4-space indents, one statement per line,
imports one per line in three sorted groups (standard library, third party, local), Google-style docstrings (a summary
line, then Args/Returns/Raises), `lower_with_under` names (CAPS for module constants, CapWords for classes).
`ruff format` lays the code out (Black's style at 80 columns, as the guide allows); `ruff check` enforces a strict rule
set approximating Google's pylintrc plus stricter checks (bugbear, bandit, simplify, ...). Both read `ruff.toml`, which
gives the reason for each rule left out for good; every other rule is enforced on all the code (the last 3,175 places
were fixed by hand on Oct. 17, 2026, each change proved not to alter the build's output).
`.editorconfig` gives editors the same settings (UTF-8, LF, final newline, no trailing whitespace, spaces; 80 columns
for Python; 2-space YAML and TOML). By hand: `.venv/bin/ruff format .` and `.venv/bin/ruff check .`.

## Tests

`./build.sh test` runs the unit tests in `tests/` with pytest (from `requirements-dev.txt`, in `.venv`; settings in
`pytest.ini`). They are small and fast: no network, no quads, no Chrome. They cover the logic that has bitten before:

- `test_pdf_text.py`: the compare-text paragraphs rebuilt from poppler's positions (an indent starts a paragraph; a flush
  block carries on a paragraph cut by a column or page break only after a full line that did not end a sentence; the
  page furniture placed at the page break; GPO's stars on one line; "ACTION :"), the line-end hyphen rules, and
  pdftotext on TTB's Notice No. 243 itself (471 paragraphs; steps (1)-(96) each one line, TTB's text);
- `test_check_step_text.py`: TTB's 96 steps identical to the Federal Register's XML, and every blocked character
  refused with its fix, the check run as the commit hook runs it (skipped while `src/checks/check_step_text.py` and
  the Federal Register's XML are not in the repository);
- `test_grit_change.py`: geodesic line lengths on GRS 1980 (#35), totals summed unrounded and rounded once (#33);
- `test_compare_ttb.py`: a big difference's acres are the whole pieces its ring touches, even inside a hole in the
  ring (#26), and the helpers that find the stretches;
- `test_make_readme.py`: README.txt's headings ("WHAT WE PROPOSE TO CHANGE IN NOTICE NO. 243 (...)") on the read-me page;
- `test_site_data.py`: the website's map data in `docs/data/`: every step from the Beginning point, each ending at its
  own point, around to the Beginning again; only the properties a reader needs; the README's area; a status the site can
  show; and, on a small made-up build, the generator's rounding and refusals and the check's line between a stale
  folder and platform drift;
- `test_site_maps.py`: the map pages load one pinned SDK release; the basemap key is empty or an API key; no map script
  parses text as HTML; the walk page lists every step of `docs/data/` with its own text; Explore's figures are the
  build's;
- `test_site.py`: every page of the website in `docs/` is a complete HTML document (doctype, language, character set,
  phone viewport, title), every local file it links to or loads is in `docs/`, and every link off the site is https;
- `test_publish_dryrun.py`: the publish dry run's checks pass on a dry run of the current build
  (`tests/fixtures/publish/dry-run/`, a copy of `target/publish/`: copy it there again after changing what the publish
  sends) and each fails on a fault planted in it (a layer left editable, plain CC0 on TTB's text, a phone element
  without its twin, a link to an item not in the group, a caption too long, a link cell that wraps, the quads' band
  legend, ...); the one marked `build` runs the whole dry run on the build's outputs.

The scripts keep their work under `if __name__ == "__main__":`, so the tests import them (`src.documents.pdf_text`)
without running them. Tests marked `build` need the build's own tools (GDAL, NumPy and SciPy, poppler's pdftotext); the
lint workflow, which installs only the lint tools, runs the rest but the live ones (`pytest -m "not build and not live"`),
and a test whose tool is missing is skipped, not failed. One file: `.venv/bin/python -m pytest -q tests/test_pdf_text.py`.

### Browser tests of the published dashboard

`tests/live/test_dashboard.py` (marked `live`; #68) opens the public dashboard in Google Chrome the way a reader does,
anonymously, and checks what is on the screen. Playwright (in `requirements-dev.txt`) drives the installed Chrome
(`channel="chrome"`, a fresh temporary profile, nothing downloaded; `HSD_CHROME` can name another Chrome). They need
network access, Google Chrome and the published site, so `./build.sh test` and the lint workflow leave them out
(`pytest.ini`: `-m "not live"`); `./build.sh check-live` (and so every publish) runs them after `agol_check.py`. Alone:

```
.venv/bin/python -m pytest -v -m live tests/live
```

- two phones, emulated as Esri requires for its phone layout (Playwright's iPhone 14 and Pixel 7: their user agent,
  touch, mobile and pixel ratio; a narrow desktop window would still get the desktop layout), at 390x844 and 412x915:
  the phone layout (`mobileView`) is shown, not the desktop one (`dashboards-mobile-layout` and the Filter button
  present, the desktop layout and the selected step's details panel absent); the header; the three indicators'
  numbers, and every caption inside its indicator and not printed over the number (each text's em box, measured in
  the page); the map drawn; the four tabs (Steps, What changes, Grit, Documents) each open with content; all the steps
  in the Steps list (it draws only the rows near its scroll position: the test scrolls it through); tapping a step
  zooms the map; the Documents tab's links open items of the group, with their titles; no sideways scrolling; the
  drawer's step selector, whose "Corrections to Notice No. 243's wording" leaves (49) and (85). A header cut short
  with an ellipsis is a warning, not a failure (Esri's phone header is one line);
- four laptop and desktop screens, 1280x720, 1366x650, 1536x750 (1920x1080 at 125% Windows scaling) and 1920x1080: the
  desktop layout; the five indicators' numbers and captions (#45); every left tab reachable (Documents, The change near
  Grit, What changes, USGS quadrangles), the GeoPDF and GeoTIFF links each on one line (#47); the right tabs (Steps,
  Big differences, All differences); no sideways scrolling.

The figures (area, steps, reworded steps, big differences, acres, the corrected steps) come from the build's outputs in
`target/work` (or `HSD_WORK`), else from the publish of Oct. 17, 2026. Every test leaves a screenshot,
`target/browser-tests/<viewport>-<test>.png` (`-FAILED.png` when it failed, named in the failure's report), and
`<viewport>-loaded.png` shows each page as it first loaded. A page that does not load in two minutes is tried once more.

## GitHub Actions and releases

Four workflows in `.github/workflows/`, every action pinned to a commit:

- **lint** (`lint.yml`, GitHub's Linux machines): every pre-commit hook on every file, then the unit tests that need
  only the lint tools, on every pull request and every push to `main`. The lint tools come from `requirements-dev.txt`,
  audited first, as on the Mac.
- **build** (`build.yml`, GitHub's Linux machines): the whole `./build.sh` on pull requests that change what the build
  reads (`build.sh`, `src/`, `resources/`, `documents/`, the lock files) or what the publish would send (`src/publish/`,
  `tests/fixtures/publish/`), then `./build.sh publish-dry-run` on the build it made (it needs GDAL and the build's
  outputs, so it cannot run in lint), and by hand (Actions > build > Run workflow).
  Linux, not GitHub's Mac machines, whose minutes cost ten times as much (Dan, 2026-10-17). Homebrew on Linux installs
  the same versions of the tools as on the Mac (GDAL, PROJ with the NADCON5 grid, poppler, Python 3.14); the PDFs ask
  for Times New Roman, Arial and Courier New and get the Liberation fonts there, which have the same character widths,
  so lines and pages break in the same places. The 13 USGS quads are cached between runs (the build still checks their
  MD5s). It keeps the build report, the checksums, the GIS lines and the dry run's JSON for 14 days, not the 290 MB zip.
- **release** (`release.yml`, Linux): push a tag such as `v2026.10.20` and it builds that commit and makes a GitHub
  release of the same name with `dist/` attached (the package zip, its README, `SHA256SUMS.txt`, `build-report.txt`).
  Run it by hand with an existing tag to rebuild that release's files.

```
git tag v2026.10.20 && git push origin v2026.10.20
```

- **site** (`site.yml`, Linux): the website. On pull requests that touch `docs/`, its tests (`tests/test_site.py`); on
  a push to `main` that touches `docs/`, and by hand, the same tests and then `docs/` deployed to GitHub Pages as it
  is (no build step: what is in `docs/` is what is served).

### The website

hickorysandsdistrictava.org is GitHub Pages serving `docs/` (issue #96). Its maps read `docs/data/`: the boundary,
steps and points as GeoJSON (NAD83 rounded to 6 decimal places, shown as WGS 84; the record is the package for TTB) and
`status.json`, the AVA's status as TTB's own record gives it (`Status`, `Established` and `CFR_Section` in the
AVAs_Production snapshot in `resources/ttb/`). When TTB establishes the AVA, refresh that snapshot, run the build and
`./build.sh site-data`, and the site's status follows.

The maps are drawn with Esri's ArcGIS Maps SDK for JavaScript, loaded from js.arcgis.com (release 5.1, pinned in the
pages and checked by `tests/test_site_maps.py`), on Esri's basemaps:

- **Explore** (`explore.html`, #113): one map with a popup for every step and point, and the dark grey map or greyscale
  imagery.
- **Walk the line** (`walk.html`, #112): every step's text in order, made by the build from `src/site/walk.template.html`
  and the data (so it reads without JavaScript and cannot drift from the boundary); the map follows the step being
  read.

No page types a boundary figure (#124). The area, the step and point counts, the line's length and the revision date are
elements marked `data-figure` (`area_sqmi`, `area_whole`, `step_count`, `point_count`, `miles`, `revision_date`, and the
petition's and Notice No. 243's areas, `petition_area_whole` and `notice_243_area_whole`, from the review stage), such
as `<span data-figure="area_sqmi">193.83</span>` or `<time data-figure="revision_date" datetime="…">…</time>`. The
site-data stage writes them from `docs/data/`; the revision date is the one in the build's file names, kept in the
boundary's record. `tests/test_site_figures.py` fails when a page types one without the mark. A journal note is history
and stays as written; a dated step in the status timeline keeps its date, but its figures are marked.

Their code is `docs/assets/maps.js` (shared), `explore.js`, `walk.js` and `maps.css`. Text from the data is only ever set
as text, never parsed as HTML. The basemaps need the ArcGIS Online API key in `docs/assets/map-config.js`. It is public by
design and limited to the basemap styles service and to the referrers `https://hickorysandsdistrictava.org` and
`http://localhost:8765` (for previews: `python3 -m http.server 8765 -d docs`). Stored geocoding and other credit-consuming
services are refused to it. It lasts up to a year: renew it in ArcGIS Online (Content > the API key item) and replace the string
in `map-config.js`. With the key empty, the maps draw the line on a plain background. A
change to the site is a pull request like any other: `site.yml` tests it on the pull request and deploys it when it is
merged to `main`. The rest is set outside the repository, once:

- the repository's Pages settings: source GitHub Actions, custom domain hickorysandsdistrictava.org, HTTPS enforced;
- the danshome account's verified domains (Settings > Pages): hickorysandsdistrictava.org, by the TXT record
  `_github-pages-challenge-danshome`, so no other account can serve it;
- its DNS at Squarespace: A records 185.199.108.153 to 185.199.111.153, AAAA records 2606:50c0:8000::153 to
  2606:50c0:8003::153, and `www` a CNAME to danshome.github.io (GitHub redirects it to the bare domain). The mail
  records beside them (MX, SPF, DKIM, DMARC, Google's verification) are Google Workspace's; leave them alone. The
  other Hickory Sands domains forward to hickorysandsdistrictava.org at Squarespace.

The land page's geologic timeline (#117) is plain HTML in `docs/land.html`: eight stages, oldest first, each with its
age, its uncertainty in words and numbered citations to the Sources list at its end. `docs/assets/timeline.js` only adds
a schematic section to step through (the page reads the same without it); `timeline.css` styles it. Its one basis is
the research notes in `resources/site/hickory-geology-research.md` (sources, confidence, claims to avoid): change a
stage only from them. `tests/test_timeline.py` (run by the lint workflow with the other tests; `site.yml` runs only
`test_site.py`) checks that every stage has an age and a citation in its text, the dates match the ages, every citation
resolves, every source is cited, and the wording, with no claim the notes say to avoid.

Publishing to ArcGIS Online is not in Actions: it stays `./build.sh publish`, run by Dan. Changes to `src/publish/` start
a build only for its publish dry run, which signs in to nothing (that code never touches `dist/`).

The runners install whatever GDAL Homebrew has that day, and the build stops when it differs from the `GDAL==` pin in
the lock (the Python bindings must match the library). When Homebrew moves GDAL on, every build stops with that message
until the lock follows: `brew upgrade gdal`, then `./build.sh upgrade` on the Mac, in a pull request.

## Changing the boundary

Change only the inputs in `resources/boundary/` (a pin in `tracing/pin-moves.json`, a patch in
`tracing/hand-patches-EPSG4269.geojson`, a route hint in `tracing/route-overrides-EPSG4269.geojson`) or the step texts, then run `./build.sh`. The area and every figure in the
README and the ArcGIS descriptions come from the build, so nothing else needs editing by hand.

The revision's date is typed once, in `resources/boundary/revision-date.txt` (#127). `build.sh`, the package script
and every script in `src/` (through `src/revision.py`) take from it the package's name and its files' names, the labels
such as "as proposed to TTB, Oct. 15, 2026", the GeoPackage's date and every date the build writes into what it makes
(`SOURCE_DATE_EPOCH`: its midnight UTC). To date a new revision, change that file and rebuild. Not derived from it, on
purpose: the published ArcGIS Online services' names, which are their URLs and stay fixed so no link breaks
(`src/publish/agol_layer.py`); and dates of events in the documents' text (the changes discussed with TTB on Oct. 15,
2026; TTB's notice downloaded and checked that day), which are history and stay as written.
