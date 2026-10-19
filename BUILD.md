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
- `./build.sh check-site` drives Google Chrome over every page of the website at phone sizes and on a desktop
  (`tests/live/test_site_mobile.py`, see Tests below): the live site, or `HSD_SITE_URL`; `./build.sh check-site --local`
  serves this checkout's `docs/` on 127.0.0.1 (port 8790, or `HSD_SITE_PORT`) for the run. Run it with `--local` before
  a website change is merged, and without it after the deploy. It takes no other argument. With `--local` it waits up to
  15 s for the server to answer (its log: `target/browser-tests/site-server.log`), and stops, printing the log, if the
  server exits (the port is taken, say) or another server answers on the port.
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
  dashboard (`tests/live/test_dashboard.py`, see Tests below), and only those: the website's have their own command,
  so a GitHub Pages delay or a fault on the website never fails an ArcGIS publish after its layers are uploaded. Right after a publish ArcGIS can take a minute to show a change to anonymous
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
pytest.ini, tests/       the unit tests (./build.sh test); tests/live/: the browser tests of the dashboard
                         (check-live) and of the website (check-site);
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
  site/                  make_site_data: the website's map data (docs/data/) from the boundary build, and (with
                         boundary_drawing) the boundary drawing on Home and The boundary; make_survey_map
                         (with survey_frame): the quads under that drawing;
                         make_aquifer_3d (with aquifer/): the 3D aquifer page's data (docs/assets/aquifer/);
                         make_vineyards (with aquifer/vineyards): the vineyards' data (docs/assets/vineyards/)
  vineyards/             the vineyards page's form, "Add your vineyard": submission (the rules, the issue, the review,
                         the vineyard file's writer), check_issue and approve (the two Actions), functions/vineyard-submit/
                         (the Supabase Edge Function and its table's SQL), bundle_function, check_function, outline_issue,
                         reconcile (the daily check);
                         SETUP.md: setting it up (the GitHub Apps, Turnstile, Supabase)
  publish/               ArcGIS Online: agol_publish, agol_layer, agol_dashboard, agol_org_categories, agol_share (what
                         is sent); agol_dryrun + agol_dryrun_checks (the dry run); agol_check (the live site)
resources/
  boundary/              what the boundary is built from (edit these, never the outputs); see resources/boundary/README.md
    revision-date.txt    the proposed revision's date (YYYY-MM-DD), typed only here (src/revision.py reads it)
    description/         the step texts: TTB's Notice 243, the petition
    proposed/            the proposed ring (Oct. 15), the Oct. 14 step lines and points, the Grit detour pins
    tracing/             pin-moves.json, trace priors, route overrides, hand-patches-EPSG4269.geojson
  ttb/                   TTB's Notice 243 PDF, the Federal Register's full-text XML of it (byte for byte), the
                         AVAs_Production record and polygon snapshot, and the proposed Llano Uplift AVA's (3D page)
  geology/               USGS SGMC units shifted to the outcrops, for the map only; see resources/geology/README.md
  aquifer/               the 3D aquifer page's inputs: inputs.csv (the pinned downloads), cache/ (them, not in git),
                         TWDB's fault lines; see resources/aquifer/README.md
  vineyards/             the vineyard outlines the site shows; see resources/vineyards/README.md
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
research/                research, audits, design proposals and prototypes until they are ready (#133); used by no
                         build, never in git, and not wiped by ./build.sh clean
```

## The stages and the checks

1. **tools and .venv** - Homebrew GDAL / Python 3.14 / Chrome if missing; the security audit; `.venv` from the lock.
2. **quads** - the 13 quads checked against their MD5s in `quads-manifest.csv`; missing or altered ones downloaded.
3. **stage** - a fresh `target/work/`; the inputs are read in place from `resources/`.
4. **trace** - every follow step traced onto the ink (`src/boundary/ink_centerline.py`), pins from `tracing/pin-moves.json`,
   route hints from `tracing/route-overrides-EPSG4269.geojson`. Deterministic: two runs on one machine give identical lines.
   The tracer's Gaussian weights come from the C library's `exp`, not NumPy's, which NumPy picks by the CPU (an AVX-512
   kernel where there is one): on a straight north-south or east-west road the first centring pass reads the ink exactly
   on cell edges, where the last bit of a weight decides the cell, and two of GitHub's Linux runners placed step 13
   0.34 m apart that way (#116). A Mac (Apple's C library) and Linux (glibc) may still differ in a last digit.
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
   hard. `docs/data/`, the walk page `docs/walk.html`, every figure marked `data-figure` and every path marked
   `data-figure-path` (the boundary drawing on Home and The boundary, and its scale bar) in the site's pages must
   match this build, so a boundary change stops the build until `./build.sh site-data` refreshes them and they are
   committed with the change. Only the traced lines may differ, and only a little: two machines
   (even two of GitHub's Linux runners) can place a vertex differently along the same ink (#116), so lines within 5 m
   of each other are reported in metres, not failed. The survey map under the boundary drawing
   (`src/site/make_survey_map.py`) is checked by its record, `docs/assets/survey-map.json` (its frame, the drawn line's
   box and its quads) and the image's size, never by its pixel values. The 3D aquifer page's data
   (`src/site/make_aquifer_3d.py --check`) is checked by its record, `docs/assets/aquifer/record.json`, with no
   download, and the vineyards' (`src/site/make_vineyards.py --check`) by theirs,
   `docs/assets/vineyards/record.json` (see The website below).

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
- `test_centerline.py`: the tracer's smoothing, its road offsets and the first centring pass on a north-south road give
  the same bits whether NumPy's `exp` is the C library's or one ulp higher, as another CPU's may be (#116), and its
  Gaussian filter is SciPy's;
- `test_make_readme.py`: README.txt's headings ("WHAT WE PROPOSE TO CHANGE IN NOTICE NO. 243 (...)") on the read-me page;
  every placeholder filled; the Web Mercator area against GDAL's for a one-degree square;
- `test_site_data.py`: the website's map data in `docs/data/`: every step from the Beginning point, each ending at its
  own point, around to the Beginning again; only the properties a reader needs; the README's area; a status the site can
  show; and, on a small made-up build, the generator's rounding and refusals and the check's line between a stale
  folder and platform drift, and the drawn paths written, checked and refused;
- `test_boundary_drawing.py`: Home and The boundary carry exactly the drawing (the line, its fill and the scale bar)
  that `docs/data/boundary.geojson` gives; The boundary's caption names the drawing's coordinate system, NAD83 / UTM
  zone 14N (EPSG:26914), as `docs/assets/survey-map.json` records it, and no page names another; the projection agrees
  with PROJ's values (and, marked `build`, with GDAL's
  for every point of the boundary, within a millimetre); the simplification keeps what lies beyond 12 m and a ring's
  first point; the fit centres the box with its margin on the tighter side; the paths are plain closed rings;
- `test_site_figures.py`: every page's figures and drawn paths are what the committed data gives, and no page types
  a figure without its mark;
- `test_site_maps.py`: the map pages load one pinned SDK release; the basemap key is empty or an API key; no map script
  parses text as HTML; the walk page lists every step of `docs/data/` with its own text; Explore's figures are the
  build's;
- `test_private_words.py`: the private-words hook, run in a throwaway repository: a git worktree is checked
  against the main checkout's gitignored list, a checkout's own list comes first, and with no list anywhere (as on
  GitHub's runners) every file passes;
- `test_survey_map.py`: Home and The boundary draw the boundary alike; the survey image fills their viewBox at the
  record's size; the record lists exactly the quads of both manifests; and, on made-up drawings, the frame's fit, its
  refusal of a drawing at two scales, and what the check calls stale;
- `test_aquifer_3d.py`: the 3D aquifer page's data is up to date with its record (the build's check); the page loads
  the pinned SDK and its script, and its scripts read only files that exist (every tile, heads file and report cell
  too); no well report keeps a removed field, or free text with a title, a role word, a company's name, a name after
  "by", a phone number, an e-mail or street address, a district's well number or initials on a number, or (in a note
  about people) a contact word or initials; on made-up names, a log line keeps its rock and loses the name, and an
  owner's initials, short names and "&" names are found (the review of #139); `stats.json` holds every figure the page
  marks, the wells' scales among them; the Wells group's controls and the groups' order; every file is under 2 MB; the
  wording; and, on made-up records, what the check calls stale;
- `test_make_vineyards.py`: the vineyards' data (`docs/assets/vineyards/`) is up to date with its record, and made
  again here it is the committed bytes (the wells near each block from the 3D page's well tiles); seven closed counties;
  one register entry per vineyard; the aquifer's record no longer lists the vineyards; what the check calls stale;
- `test_vineyard_rules.py`: the vineyard form's rules, `docs/assets/vineyard-blocks.js` (the page's and the function's,
  in node) against `src/vineyards/submission.py` (the Actions'): the same errors, facts, cleaned submission, title and
  issue for every fixture, hostile ones among them, and each limit on each side; the issue holds no contact and nothing
  that can close a code fence or carry HTML;
- `test_vineyard_function.py`: the Edge Function, bundled as Dan deploys it, run in node (22 or later) against stand-ins
  for its table, Turnstile and GitHub (`tests/vineyard_standin.mjs`): CORS, size, Turnstile (and Cloudflare failing,
  503), the trap, the rules and the private words (and the silent hold, off by default), the row and the issue, a
  retry, the limits, GitHub's answer lost (one issue, found again by its marker), the row not tied to its issue (never
  reported as sent), a dropped label, failures, the App's key in each form, the webhook (no row: 404; the table down:
  503), the reconciliation (at most every ten minutes; missed closings, reopenings and deletions; rows tied by their
  marker; failures answered 500) and the deletions; and `check_function.py`'s five checks, passing on it and failing on
  a forged address;
- `test_vineyard_sql.py`: the contacts table's SQL in a throwaway PostgreSQL, when one is installed (Supabase's roles
  kept out, row level security forced, the limits and a send again, a send that died taken up again after two
  minutes, a held row, the reconciliation's tick, only `hsd_vineyard_*` objects);
- `test_vineyard_actions.py`: `check_issue.py` and `approve.py` run as the workflows run them (`python -I -B`) on sample
  issue events, against a stand-in for GitHub's API: opened, edited, labelled by the owner, labelled by someone else, a
  forged issue, a body not in the layout, a body re-saved in GitHub's editor (CRLF), an overlap, a pin, a second
  approval (the branch never moved), the pull request refused, the environment open to any branch; and
  `reconcile.py`, the daily check, against a stand-in for the function (one issue for Dan when it fails);
- `test_vineyard_submission.py`: the review, and the vineyard file's writer (byte for byte, sorted, clockwise, the file's
  own block numbers, the year and varieties kept, a private word refused); a pin's outline drawn by the petitioners;
- `test_vineyard_form.py`: the vineyards page: the old email form gone; every field labelled and every message tied to
  its field; the counties and varieties the rules'; the config empty or well formed, and Send ending at the email while it
  is empty; no script that parses text as HTML or hides a failure in an empty catch; one pinned SDK, loaded when needed;
  the targets' sizes; the wording; and, in node, the fallback's email (every line in order, never a URL past 1,900
  characters, nothing typed able to add a header, an emoji never cut in half);
- `test_workflows.py`: every workflow's actions pinned to a commit, Linux only, no event text in a shell; the vineyard
  workflows' permissions and gates as reviewed, one bot and one label everywhere; a release only of `main`'s history;
- `test_site.py`: every page of the website in `docs/` is a complete HTML document (doctype, language, character set,
  phone viewport, title), every local file it links to or loads is in `docs/`, and every link off the site is https;
- `test_site_nav.py`: every page in `docs/`, and `src/site/walk.template.html`, has Home's menu links in Home's order,
  each opening a page in `docs/`, and marks its own link, and only that, `aria-current="page"` (a page not in the menu
  marks none);
- `test_public_text.py`: the claims that contradicted the petition or Comment 9 and were taken out stay out of `docs/`
  (every page, data file and script) and `src/site/` (its code and template): a phrase, and where its words are also
  said correctly, the words that make it wrong in the same sentence ("1:250,000" for the SGMC, not for the Geologic
  Atlas of Texas; "about 9%" and "about 47%" for soil, sandstone or granite), whatever its case and whatever separates
  its words (a space, a line break, a non-breaking space as a character, entity or escape, or an HTML tag), each wrong
  sentence as it was and each correct use tested; no page marks the petition's or Notice No. 243's area
  (`petition_area_whole`, `notice_243_area_whole`), which Home once showed as "about 194 square miles"; and the Status
  page dates the amended petition as `src/boundary/build_proposed.py` does ("as amended June 6, 2023");
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
.venv/bin/python -m pytest -v -m live tests/live/test_dashboard.py
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

### Browser tests of the website at phone sizes

Every change to the website is tested at phone sizes before it is merged, against a local server of its branch, and
live after it is deployed (Dan, 2026-10-18: mobile is always tested). `tests/live/test_site_mobile.py` (marked `live`)
opens every page in `docs/` in Google Chrome, as the dashboard's tests do, on three phones held upright, emulated with
their user agent, touch and pixel ratio (390x844, 360x780 and 375x667), and on a 1440x900 desktop:

```
./build.sh check-site --local    # before the merge: this checkout's docs/ on http://127.0.0.1:8790 (or HSD_SITE_PORT)
./build.sh check-site            # after the deploy: https://hickorysandsdistrictava.org
```

or by hand, against a server you started:

```
python3 -m http.server 8790 --bind 127.0.0.1 -d docs
HSD_SITE_URL=http://127.0.0.1:8790 .venv/bin/python -m pytest -v -m live tests/live/test_site_mobile.py
```

- every page at every size: no console error from the site's own files, uncaught error from them (or from no file) or
  failed request for one; no sideways scrolling, with the menu shut or open; the menu is a hamburger named "Menu" that
  opens and closes by a tap (a click on the desktop) and by the keyboard (Enter, Space), a cross while open, inside the
  screen, with its links in order (The boundary, The land, The water, The vineyards, Status, Journal, About & contact),
  the page's own marked `aria-current`, each answering 200; the header's place line reads "Llano Uplift · Texas Hill
  Country", on one line between the home link and the menu where it shows (also checked at 700 px, the narrowest screen
  that shows it);
  these buttons and action links are at least 44 px each way: the header's home link and menu button, the open menu's
  links, the footer's links, and on the pages those in the test's `ACTIONS` (`.text-link`, Explore's basemap
  buttons, The land's Earlier and Later, Home's ways in and arrival links, The water's panel links and About contents);
  other links and buttons (a link inside a sentence, the vineyards form) are not measured. One hidden by design is not
  measured: inside a `[hidden]` element, or not rendered (`checkVisibility()`: `display:none`, `visibility:hidden`, the
  content of a shut `<details>` or `<dialog>`); every other one is, so a box collapsed to 1.5 px or less fails;
- every menu link, tapped on a phone and clicked on the desktop from Home, opens its page, which marks it current;
- Explore, on the phones: tapping three steps, a quarter, a half and three quarters of the way along the line (from
  `docs/data/steps.geojson`), opens each step's popup, docked along the map's bottom, with the
  place tapped near the middle of the map left above it (the view's bottom is padded by the popup's height); the popup
  has no undock button, and the zoom and Home buttons are 44 px; a one-finger swipe beside the map (the page's margin)
  or on it scrolls the page and leaves the map still; two fingers move the map; Home shows the whole boundary again;
- The land, on the phones: the drawing shows the stage on its reading line as the page scrolls, and does so too when
  the reader scrolls right after tapping Later (whose hold ends after 1,200 ms); with the page's clock stopped, so that
  only the reader can end the hold, a touch outside the drawing's buttons or a turn of the wheel ends it at once, and a
  touch on the buttons does not (`timeline.js`, `reader()`);
- The water, at every size: its panel's links (on a phone, with the Layers sheet opened) and, opened from "About this
  map", the About panel's contents links and Close are 44 px each way, with no sideways scrolling.

Explore's map must settle (ready, not updating) within 30 s of each move, or the test fails there, with a screenshot.

The site is https://hickorysandsdistrictava.org unless `HSD_SITE_URL` names another. A console error counts only when
Chrome gives its source as one of the site's own files; what Esri's SDK logs (from js.arcgis.com) never counts, locally
or live. The basemap key serves only the live site and `http://localhost:8765`, so on any other local address Esri
refuses the basemaps (HTTP 401) and the maps draw the line alone: on a loopback address the test allows those refusals
(HTTP 401 or 403 from arcgis.com); on the live site they fail it (the key has expired or lost its referrer).
`./build.sh check-live` does not run it: a Pages delay or a fault on the website must never fail an ArcGIS publish.
Screenshots: `target/browser-tests/site/<page>-<viewport>-<test>.png` (`-FAILED.png` when it failed), with `-loaded.png`
after each load and `-menu-open.png` with the menu open.

## GitHub Actions and releases

Seven workflows in `.github/workflows/`, every action pinned to a commit:

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

  It releases only a tag on `main`'s history: a tag pushed on another branch (the vineyard pull request App can push
  branches and tags) is refused.

- **vineyard-check** (`vineyard-check.yml`, Linux): when an issue is opened, edited or labelled, and only for the
  form's issues (opened by the GitHub App "HSD vineyard form", labelled `vineyard-submission`, open), it checks the
  vineyard sent through the website's form again with the repository's data and posts one comment, which it edits when
  the issue changes (`src/vineyards/check_issue.py`). Its token can write issues only.
- **vineyard-approve** (`vineyard-approve.yml`, Linux): when the repository's owner adds the label `approved` to one of
  those issues, it adds the blocks to `resources/vineyards/`, makes the site's vineyard data again and opens the pull
  request, with a one-run token of the GitHub App "HSD vineyard PR" from the environment `vineyard-pr` (main only), so
  the pull request's checks run (`src/vineyards/approve.py`). Every such pull request is reviewed and merged by hand.
  Both read the issue from the event's file, never from an expression in a shell; an issues event runs them as they
  are on `main`. Setting them up: `src/vineyards/SETUP.md`.
- **vineyard-reconcile** (`vineyard-reconcile.yml`, Linux, daily, once Dan has set the repository variable
  `VINEYARD_FUNCTION_URL`): asks the vineyard function to put its private table right against GitHub (closings a failed
  webhook delivery missed, rows not yet tied to their issues, the deletions) and, when that fails, opens or comments on
  one issue for Dan (`src/vineyards/reconcile.py`).
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
elements marked `data-figure` (`area_sqmi`, `area_whole`, `step_count`, `point_count`, `miles`, `revision_date`), such
as `<span data-figure="area_sqmi">193.83</span>` or `<time data-figure="revision_date" datetime="…">…</time>`. The
site-data stage also has the petition's and Notice No. 243's areas, `petition_area_whole` and `notice_243_area_whole`,
from the review stage, but no page marks them now (`tests/test_public_text.py` keeps it so). The site-data stage
writes the marked figures from `docs/data/`; the revision date is the one in the build's file names, kept in the
boundary's record. `tests/test_site_figures.py` fails when a page types one without the mark. A journal note is history
and stays as written; a dated step in the status timeline keeps its date, but its figures are marked.

The boundary drawing on Home and The boundary (an inline SVG) is made by the site-data stage too (#126): its line and
fill, `<path … data-figure-path="boundary" d="…">`, are `docs/data/boundary.geojson` carried from NAD83 to UTM zone 14N
(EPSG:26914), each ring simplified by Douglas–Peucker at 12 m, and fitted to the drawing's viewBox (the boundary's box
centred, with a margin of 11% of its width, or of its height where that fits tighter, on each side), written to 0.01
of a unit; its 5 km scale bar (`data-figure-path="scale_bar"`) is drawn at the same scale.
`src/site/boundary_drawing.py` draws them with the standard library only (the projection is Karney's Krüger series,
within a micrometre of PROJ's here), so the lint workflow checks the pages (`tests/test_boundary_drawing.py`), and
`make_site_data.py --pages` writes them, or with `--check` stops the build when one is stale, drawing them from the
committed data as it makes the walk page.

The drawing sits on a survey map, `docs/assets/survey-map.webp`, made by the site-data stage after the drawing
(`src/site/make_survey_map.py`). It shows the ground the drawing's viewBox covers, found by
fitting the drawn line to `docs/data/boundary.geojson` in UTM zone 14N, on the USGS 1:24,000 historical quadrangles:
the 13 the description names and the 17 around them that fill the frame (`resources/quads/basemap-manifest.csv`, each
the earliest print of the quad's only 1:24,000 edition, the lowest scan number on a tie, checked against USGS's MD5 and downloaded to
`resources/quads/basemap/` when the image is made). Each quad is cropped to its 7.5-minute neatline and carried from
NAD27 to NAD83 UTM 14N through the NADCON 5.0 CONUS grid. `docs/assets/survey-map.json` records the frame, the drawn
line's bounding box and the quads; the image is made again only when that record would change or the image is missing
or the wrong size, and the check compares the record and the image's size, never its pixel values, so machines whose
GDAL rounds differently agree. A frame reaching past the listed quads stops `./build.sh site-data`, naming where.

- **The Hickory Aquifer in 3D** (`aquifer.html`, #135; linked from The land): the whole Hickory Aquifer as TWDB's
  Llano Uplift groundwater model (GAM v1.01, layer 7) draws it, under a see-through ground, in an `<arcgis-scene>`;
  TWDB's well reports (driller's reports and the Groundwater Database) coloured by the rock their logs record, without
  people's names; the vineyard outlines (a vineyard's popup lists the wells near it; their data is
  `docs/assets/vineyards/`, below); the proposed district, TTB's
  proposed Llano Uplift AVA, counties and towns; "My location", with the model's estimate of what lies beneath; a
  switch for every layer and group and filters for use, water volume (yield) and depth. Zoomed out (the opening Whole
  aquifer view) it draws one well per cell; from the District view's scale in (`WELLS_ALL_SCALE` in `params.py`,
  between the two views as measured on a wide screen and a phone), every well's head, from the compact
  `wells/heads-<n>.json`; closer in (`WELLS_LINES_SCALE`), every well's line too, around the middle of the view. Its
  code is `aquifer3d.js`,
  `aquifer-wells.js` and `aquifer.css`; its data is `docs/assets/aquifer/`, beside it, not in `docs/data/` (which
  `make_site_data.py` owns). Every figure it shows comes from `docs/assets/aquifer/stats.json` and, for the
  vineyards, `docs/assets/vineyards/stats.json` (made by `src/site/make_vineyards.py`), read when the page loads
  (`data-stat` elements, not `data-figure`). When Esri's ground (elevation) cannot be loaded, for example a
  refused key, the ground is drawn flat and the aquifer and wells at their depths below the model's own ground; when
  the basemap cannot be loaded, the layers are drawn on the page's background; the page says which.

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

The vineyards page (`vineyards.html`) lists every vineyard of the site's data, grouped as on The water, with a map
(`assets/vineyard-list.js`, from `assets/vineyards/register.json` and `vineyards.geojson`; Esri's SDK loads when the map
comes near the screen). Its "Not listed?" section opens "Add your vineyard", five steps over the whole screen
(`assets/vineyard-wizard.js`, `vineyard-form.css`): where the vineyard is (the phone's location or Esri's search), its
blocks tapped corner by corner on Esri World Imagery (or a pin), what it is, how to reach the sender, and a last check.
The rules are `assets/vineyard-blocks.js`, the module the Supabase function also runs. What the grower enters is kept on
the device as a draft (never the name, phone or email) until it is sent. It sends to the function named in
`assets/vineyard-config.js` (with the Turnstile site key; both public). While either is empty, or when the function does
not answer, the last screen offers to send the details by email (`assets/vineyard-email.js`, which node runs in the
tests) or to copy them; there is no email form beside it. `tests/test_vineyard_form.py` checks the page and the email;
`tests/live/test_vineyard_wizard.py` (marked live) drives the whole form in Chrome at 390x844 and 360x780 by touch and at
1440x900 by mouse, against the real function served with stand-ins (`tests/vineyard_standin.mjs`), on
`http://localhost:8765` for the real map (port 8765 must be free for the run):

```
.venv/bin/python -m pytest -v -m live tests/live/test_vineyard_wizard.py
```

The 3D aquifer page's data is made by `src/site/make_aquifer_3d.py` (with `src/site/aquifer/`) from the downloads
`resources/aquifer/inputs.csv` pins (TWDB's model archive, 364 MB, its 2017 aquifer outlines, its two well databases,
the Census counties and places) and committed inputs (TWDB's fault lines in
`resources/aquifer/`, TTB's Llano Uplift AVA in `resources/ttb/`, the shifted geology). `docs/assets/aquifer/record.json`
records every input's SHA-256, the generator's parameters (`src/site/aquifer/params.py` and a digest of the privacy
rules) and every file written with its size. `./build.sh` (and so the build workflow) only checks it
(`make_aquifer_3d.py --check`): it reads the manifest, the committed inputs and the record, downloads nothing, and
exits 3 when an input, a parameter or a file changed. GitHub Actions never download the model or the well files.
`./build.sh site-data` makes the data again only when it is stale: it fetches any input missing from the gitignored
`resources/aquifer/cache/` (as the quads are kept in `resources/quads/geotiff/`), checks every one against its bytes and
SHA-256, extracts the model's GeoPackage with `bsdtar` (macOS has it; on Linux `brew install libarchive`), writes every
file into the gitignored `target/aquifer-next/`, and swaps that in only after two hard checks: no person's name or address
survives in the well reports (`src/site/aquifer/privacy.py`: the removed fields; then every note blanked, and in a line
of a well's log only the words taken out and marked `[removed]`, where it holds a word or the initials of a name on the
record, a name from the area, a title, a person's role, a company's name, a name after "by", a rare word, a phone
number, an e-mail or street address, a groundwater district's well number or initials on a number, or in a note about
people a contact word or initials; the check also fails on a record's own names in any of its other text but TWDB's
codes), and every file is under the hooks' 2 MB. The generator also
reads the gitignored `.private-words`, when present (in a git worktree, the main checkout's, as the hook does), as
more words to blank. Commit the data and its record together.

**Refreshing an input.** TWDB's well databases are served from one URL that always gives today's file, so a fetch
on another day does not match the pinned SHA-256 and the run stops, naming the input. Moving to a new snapshot is a
deliberate change: download the file, put its date (`snapshot`: the date of the data, here the files' own date inside the
zip; `fetched`: today), byte count and SHA-256 (`shasum -a 256`) in its row of `resources/aquifer/inputs.csv`, put the
file in `resources/aquifer/cache/` under the row's `file` name (or delete the cached one and let the run fetch it),
run `./build.sh site-data`, look at the figures in `docs/assets/aquifer/stats.json` and commit the data, the record and
the manifest in one pull request. A changed fault-line file in `resources/` makes the data stale the same way.

The vineyards' data, `docs/assets/vineyards/`, is made apart by `src/site/make_vineyards.py`, from committed files only:
`resources/vineyards/vineyards-EPSG4269.geojson`, the 3D page's well tiles (`docs/assets/aquifer/wells/index.json` and
`draw-*.json`) and its county lines (`context.geojson`). It writes `vineyards.geojson` (the blocks), `vineyard-wells.json`
(the wells within a kilometre of each block, nearest first), `register.json` (one entry per vineyard, with the year
first planted and the varieties when given, for the vineyards page), `counties.geojson` (the seven Llano Uplift counties
closed into polygons, for the form's county guess), `stats.json` (the figures, which the 3D page merges with its own) and
`record.json` (the inputs' SHA-256s, the parameters and the files). So a vineyard can be added anywhere, GitHub's runners
among them, without the 3D page's downloads: `./build.sh` checks it (`--check`, exit 3 when stale), `./build.sh
site-data` makes it again after the aquifer's data (new well tiles make it stale too), and the `vineyard-approve` Action
runs it for its pull request. Like the aquifer's generator, it reads the private words (`.private-words`, or the
`PRIVATE_WORDS` secret on the runners) and refuses a vineyard field that holds one, a person's name, a title, an e-mail
address or a telephone number.

The vineyards page's form, "Add your vineyard", sends a vineyard to the Supabase Edge Function `vineyard-submit`
(`src/vineyards/functions/vineyard-submit/`), which checks it with the page's own rules (`docs/assets/vineyard-blocks.js`),
keeps the sender's contact in one locked table (`hsd_vineyard_contacts`: row level security on, no policies, written only
by the function, each row deleted a year after its issue is closed, or a day after it was made if it was never tied to an
issue) and opens a public issue with the public fields only, once: a marker in the issue (an HMAC of the submission's id)
lets a retry after a lost answer find it instead of making a second, and the sender is told it is sent only once the row
is tied to its issue. Its webhook records closings; the daily check (`vineyard-reconcile`) catches what it missed.
The two Actions above check it and, on the owner's label, open the pull request. Dan sets it up once and deploys the
function from the Supabase dashboard as one file (`src/vineyards/bundle_function.py`); `src/vineyards/SETUP.md` gives
every click, and `src/vineyards/check_function.py` checks the deployed function from outside.

The land page's geologic timeline (#117) is plain HTML in `docs/land.html`: eight stages, oldest first, each with its
age, its uncertainty in words and numbered citations to the Sources list at its end. `docs/assets/timeline.js` only adds
a schematic section to step through (the page reads the same without it); `timeline.css` styles it. Where the drawing
stays in view, scrolling steps it: beside the list on a wide screen, and on a phone held upright as a short panel stuck
to the top of the screen; a phone on its side steps it with the buttons. Every statement
rests on the published sources the page cites; the research notes behind it are kept in the gitignored `research/` folder (never
checked in): change a stage only from a published source, and cite it. `tests/test_timeline.py` (run by the lint workflow with the other tests; `site.yml` runs only
`test_site.py`) checks that every stage has an age and a citation in its text, the dates match the ages, every citation
resolves, every source is cited, the wording, with no claim the notes say to avoid, and that the script and the styles
use one query for a phone held upright.

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
