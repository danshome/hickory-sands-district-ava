"""The vineyard-approve Action: the owner's label opens the pull request.

Run by .github/workflows/vineyard-approve.yml when the label `approved` is
added (python -I -B src/vineyards/approve.py). It acts only when the
repository's owner added the label to one of the form's issues
(actions.approve_gate(), the workflow's own gate checked again); checks the
submission again (submission.review()) and refuses, with a comment, one
that is not ready (a name already in the data, an overlap, a pin without
blocks, a problem with the text); adds the blocks to
resources/vineyards/vineyards-EPSG4269.geojson (submission.add_blocks());
makes the site's vineyard data again (src/site/make_vineyards.py); and
opens the pull request through GitHub's API: a branch vineyard/issue-<n>
from the commit this run checked out, one commit, the pull request
"Vineyard: <name> (#n)" that closes the issue, labelled vineyard-data. Then
it comments on the issue with the pull request's link.

Tokens, from the environment, never printed or written to disk:
    GH_TOKEN   the Actions' own token (Issues write): the comments;
    PR_TOKEN   an installation token of the GitHub App "HSD vineyard PR"
               (Contents and Pull requests write), made for this run in the
               environment vineyard-pr: the branch, the commit and the pull
               request. A pull request opened with GITHUB_TOKEN would run
               no checks; one opened by an App runs them all.
Also GITHUB_REPOSITORY, GITHUB_SHA (the commit to build on) and, optionally,
PRIVATE_WORDS. Standard library only.

Usage (the workflow, or a test with --root on a copy of the files):
    approve.py [--event FILE] [--root DIR] [--today YYYY-MM-DD]
"""

import argparse
import base64
import datetime
import os
import subprocess
import sys

# The repository's root: -I leaves the script's own folder off sys.path.
sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ),
)

from src.vineyards import actions
from src.vineyards import github
from src.vineyards import submission as vs

ROOT = vs.ROOT

OUT = "docs/assets/vineyards"
BRANCH = "vineyard/issue-{n}"


def refuse(issues, number, why):
    """Comments why there is no pull request, and fails the run."""
    issues.request(
        "POST",
        f"{{repo}}/issues/{number}/comments",
        {
            "body": (
                f"No pull request: {why} See the check above; once it is "
                "put right (edit the data block, or ask the sender), remove "
                "the label `approved` and add it again."
            )
        },
    )
    print(f"issue #{number}: refused: {why}")
    return 1


def changed_files(root):
    """The files the pull request carries: the vineyard file and the data.

    Args:
        root: The repository, after add_blocks() and make_vineyards.py.

    Returns:
        {path from the root, with "/": bytes}.
    """
    out = {}
    with open(os.path.join(root, vs.VINEYARDS), "rb") as fh:
        out[vs.VINEYARDS] = fh.read()
    for name in sorted(os.listdir(os.path.join(root, OUT))):
        with open(os.path.join(root, OUT, name), "rb") as fh:
            out[f"{OUT}/{name}"] = fh.read()
    return out


def pr_body(number, sub, category, n):
    """The pull request's description."""
    return "\n".join(
        [
            f"Closes #{number}.",
            "",
            (
                f"Adds the vineyard {vs.code(sub['vineyard']['name'])}, sent"
                f" through the website's form (#{number}) and approved there"
                " with the label `approved`:"
            ),
            "",
            (
                f"- `{vs.VINEYARDS}`: {n} block{'' if n == 1 else 's'},"
                f" category `{category}`, with the year first planted and"
                " the varieties as the sender gave them;"
            ),
            (
                f"- `{OUT}/`: the site's vineyard data, made again by"
                " `src/site/make_vineyards.py` (the blocks' wells from the 3D"
                " page's committed well tiles)."
            ),
            "",
            (
                f"The check on #{number} found it ready for review. Before"
                " merging, look at the blocks on the issue's map against the"
                " imagery, and review this pull request as every other."
                " Merging it puts the vineyard on the site."
            ),
            "",
            "Made by the vineyard-approve Action (`src/vineyards/approve.py`).",
        ]
    )


def open_pull_request(prs, number, sub, category, files, base):
    """Makes the branch, the commit and the pull request.

    Args:
        prs: A github.GitHub with PR_TOKEN.
        number: The issue's number.
        sub: The checked submission.
        category: Its category.
        files: changed_files().
        base: The commit the files were made from.

    Returns:
        The pull request's number and its URL.
    """
    tree = prs.request("GET", f"{{repo}}/git/commits/{base}")["tree"]["sha"]
    entries = []
    for path, data in files.items():
        blob = prs.request(
            "POST",
            "{repo}/git/blobs",
            {"content": base64.b64encode(data).decode(), "encoding": "base64"},
        )
        entries.append(
            {"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]}
        )
    new_tree = prs.request(
        "POST", "{repo}/git/trees", {"base_tree": tree, "tree": entries}
    )
    name = sub["vineyard"]["name"]
    commit = prs.request(
        "POST",
        "{repo}/git/commits",
        {
            "message": (
                f"Vineyard: {name} (#{number})\n\nAdded from the website's "
                f"vineyard form, issue #{number}, approved there with the "
                "label approved; the site's vineyard data made again."
            ),
            "tree": new_tree["sha"],
            "parents": [base],
        },
    )
    branch = BRANCH.format(n=number)
    try:
        prs.request(
            "POST",
            "{repo}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": commit["sha"]},
        )
    except github.GitHubError as error:
        if error.status != 422:  # 422: the branch is there, from before
            raise
        prs.request(
            "PATCH",
            f"{{repo}}/git/refs/heads/{branch}",
            {"sha": commit["sha"], "force": True},
        )
    owner = prs.repo.split("/")[0]
    found = prs.request(
        "GET", f"{{repo}}/pulls?state=open&head={owner}:{branch}"
    )
    if found:
        pull = found[0]
    else:
        pull = prs.request(
            "POST",
            "{repo}/pulls",
            {
                "title": f"Vineyard: {name} (#{number})",
                "head": branch,
                "base": "main",
                "body": pr_body(number, sub, category, len(sub["blocks"])),
                "maintainer_can_modify": True,
            },
        )
    try:
        prs.request(
            "POST",
            f"{{repo}}/issues/{pull['number']}/labels",
            {"labels": [vs.DATA_LABEL]},
        )
    except github.GitHubError as error:
        print(f"the label {vs.DATA_LABEL} was not added: {error}")
    return pull["number"], pull["html_url"]


def main(argv=None):
    """Opens the pull request that adds an approved vineyard.

    Args:
        argv: The command line's arguments (sys.argv[1:] when None).

    Returns:
        The exit status: 0 when the pull request is open (or the event is
        not one to act on), 1 when the submission was refused.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--event", help="the event (default: $GITHUB_EVENT_PATH)"
    )
    parser.add_argument("--root", default=ROOT, help="the repository")
    parser.add_argument("--today", help="the source note's date (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    event = actions.load_event(args.event)
    why = actions.approve_gate(event)
    if why:
        print(f"nothing to do: {why}")
        return 0
    repo = os.environ["GITHUB_REPOSITORY"]
    issues = github.GitHub(os.environ.get("GH_TOKEN", ""), repo)
    number = event["issue"]["number"]
    try:
        data = vs.parse_issue(event["issue"].get("body"))
    except vs.SubmissionError as error:
        return refuse(issues, number, f"the issue is not the form's ({error}).")
    words = actions.private_words()
    today = args.today or datetime.datetime.now(datetime.UTC).date().isoformat()
    _, ok, result = vs.review(
        data,
        number,
        actions.other_submissions(issues, number),
        words,
        today=today,
        root=args.root,
    )
    if not ok:
        return refuse(issues, number, "the check found something to look at.")
    new_text, _ = vs.add_blocks(result, number, today, args.root, words)
    with open(
        os.path.join(args.root, vs.VINEYARDS),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as fh:
        fh.write(new_text)
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            os.path.join(ROOT, "src", "site", "make_vineyards.py"),
            "--root",
            args.root,
        ],
        check=True,
    )
    prs = github.GitHub(os.environ.get("PR_TOKEN", ""), repo)
    pr_number, url = open_pull_request(
        prs,
        number,
        result["submission"],
        result["category"],
        changed_files(args.root),
        os.environ["GITHUB_SHA"],
    )
    issues.request(
        "POST",
        f"{{repo}}/issues/{number}/comments",
        {
            "body": (
                f"Approved: pull request #{pr_number} adds this vineyard "
                f"({url}). Its checks run now; merging it puts the vineyard "
                "on the site and closes this issue."
            )
        },
    )
    print(f"issue #{number}: pull request #{pr_number} open")
    return 0


if __name__ == "__main__":
    sys.exit(main())
