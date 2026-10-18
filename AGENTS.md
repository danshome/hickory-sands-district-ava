# AGENTS.md

For every AI coding agent working in this repository: Claude Code, Codex, Muse, Copilot, Cursor, Gemini or any other.

**Read [CLAUDE.md](CLAUDE.md) before you change anything. Its rules apply to every agent, not only to Claude.** Then
[CONTRIBUTING.md](CONTRIBUTING.md) (the same workflow, for people) and [BUILD.md](BUILD.md) (the layout and the
checks). Where this file and CLAUDE.md differ, CLAUDE.md wins.

## The rules no agent may break

1. **Never push to `main`.** Not a commit, not a merge, not a force push. `main` is protected. Only Dan, or the Claude
   Code session he runs, merges to it.
2. **Every change goes issue, branch, pull request.** Open or name a GitHub issue first. Branch off `main`, named by
   kind and topic (`docs/...`, `fix/...`, `feature/...`). Commit, push the branch, and open a pull request to `main`
   that says `Fixes #n` and what changed, why, and how you checked it. Then stop. Don't merge it yourself. Every pull
   request is reviewed with Claude Code's `/pr-review-toolkit:review-pr` before it is merged, and its findings must
   be fixed on your branch or answered in the pull request.
3. **The commit hooks must pass.** Run `./build.sh env` once (it makes `.venv` and installs the hooks), and let them
   run on every commit. Never `--no-verify`. Every rule in `ruff.toml` applies to all Python, new code included:
   Google style, 80 columns. `./build.sh lint` runs every hook on every file.
4. **Put files where they belong** (the layout is in BUILD.md):
   - code under `src/<area>/`;
   - the website in `docs/`;
   - the build's inputs in `resources/`;
   - tests in `tests/`.
   Don't add a new top-level folder unless an issue agrees to it first.
5. **No secrets in the repository. It is public.** Tokens, keys, passwords and connection strings stay in your
   tool's credential store or in environment variables, never in a file, a commit message or an issue.
6. **Publish nothing without Dan.** Merging to `main` deploys `docs/` to the public website. ArcGIS Online
   (`./build.sh publish`), releases, DNS and the domains are Dan's to change.
7. **The boundary changes only through `resources/boundary/`, and the build.** No geometry is copied from an existing
   boundary layer.
8. **Say "proposed", never "agreed"**, and use the official names: Notice No. 243, the AVA Map Explorer polygon, the
   proposed revision.

Keep each pull request to one change. If you find something else wrong, open an issue for it; don't fix it on the side.
