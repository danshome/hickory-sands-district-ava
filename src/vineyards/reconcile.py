"""The vineyard-reconcile Action: the function's daily check, reported.

Run once a day by .github/workflows/vineyard-reconcile.yml (python -I -B
src/vineyards/reconcile.py). It asks the vineyard function to put its table
right against GitHub (POST <FUNCTION_URL>/reconcile: rows tied to their
issues, the closings and deletions a failed webhook delivery missed, the
year's and the day's deletions; at most once every ten minutes, so the
answer may be that it ran a moment ago). When that fails, it opens one issue
for Dan, "Vineyard form: the daily check failed", or comments on the one
already open, with what failed and a link to the run; and the run fails.

Environment: FUNCTION_URL (the repository variable VINEYARD_FUNCTION_URL),
GH_TOKEN (the Actions' token, Issues write), GITHUB_REPOSITORY, and GitHub's
GITHUB_SERVER_URL and GITHUB_RUN_ID for the link. Standard library only.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

# The repository's root: -I leaves the script's own folder off sys.path.
sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ),
)

from src.vineyards import github

TITLE = "Vineyard form: the daily check failed"
URL = re.compile(
    r"^https://[a-z0-9]+\.supabase\.co/functions/v1/vineyard-submit$"
    r"|^http://127\.0\.0\.1:\d+/vineyard-submit$"
)
TIMEOUT_S = 60


def ask(url):
    """POSTs to the function's /reconcile: (status, its JSON or {})."""
    req = urllib.request.Request(url + "/reconcile", data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            status, text = resp.status, resp.read()
    except urllib.error.HTTPError as error:
        status, text = error.code, error.read()
    except OSError as error:
        return 0, {"failed": f"no answer ({type(error).__name__})"}
    try:
        body = json.loads(text or b"{}")
    except ValueError:
        body = {}
    return status, body if isinstance(body, dict) else {}


def report(gh, why):
    """Opens the issue for Dan, or comments on the one already open.

    Args:
        gh: A github.GitHub (the Actions' token).
        why: What failed, in a sentence.

    Returns:
        The issue's number.
    """
    run = (
        f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
        f"{gh.repo}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    )
    text = (
        f"The vineyard function's daily check failed: {why}\n\n"
        f"The run: {run}\n\n"
        "Until it passes, a contact may be kept past its year, or a closing "
        "missed. src/vineyards/SETUP.md, step 8, has the checks; the "
        "function's logs are in Supabase (Edge Functions > vineyard-submit > "
        "Logs). Close this issue once the check passes again."
    )
    for issue in gh.paged("{repo}/issues?state=open"):
        if issue.get("title") == TITLE and "pull_request" not in issue:
            gh.request(
                "POST",
                f"{{repo}}/issues/{issue['number']}/comments",
                {"body": text},
            )
            return issue["number"]
    made = gh.request("POST", "{repo}/issues", {"title": TITLE, "body": text})
    return made["number"]


def main():
    """Asks the function to reconcile, and reports a failure.

    Returns:
        0 when it passed, 1 when it failed (and the issue says so).
    """
    url = os.environ.get("FUNCTION_URL", "").rstrip("/")
    if not URL.match(url):
        print("FUNCTION_URL is not the vineyard function's address")
        return 1
    status, body = ask(url)
    if status == 200 and body.get("ok") is True:
        found = {k: v for k, v in body.items() if k != "ok"}
        print(f"the vineyard function's table is right: {found}")
        return 0
    why = (
        f"{status or 'no answer'}, "
        f"{body.get('failed') or body.get('error') or 'no reason given'}"
    )
    if body.get("missing"):
        why += f" (secrets missing: {', '.join(body['missing'])})"
    gh = github.GitHub(
        os.environ.get("GH_TOKEN", ""), os.environ["GITHUB_REPOSITORY"]
    )
    number = report(gh, why)
    print(f"the daily check failed ({why}): said on issue #{number}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
