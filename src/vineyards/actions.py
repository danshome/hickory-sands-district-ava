"""What the two vineyard Actions share: the event, the gates, the comments.

The workflows (.github/workflows/vineyard-check.yml and vineyard-approve.yml)
run src/vineyards/check_issue.py and approve.py, which read the issue from
the event's JSON file ($GITHUB_EVENT_PATH), never from the workflow's
expressions, and check again here the gates the workflows' `if:` already
hold, so a gate that was loosened by mistake still holds. Standard library
only.
"""

import json
import os

from src.site.aquifer import record
from src.vineyards import submission as vs


def load_event(path=None):
    """The event that started the run.

    Args:
        path: The event's JSON file (default: $GITHUB_EVENT_PATH).

    Returns:
        The event, a dict.

    Raises:
        SystemExit: No event file, or not a JSON object.
    """
    path = path or os.environ.get("GITHUB_EVENT_PATH")
    if not path:
        raise SystemExit("no GITHUB_EVENT_PATH")
    with open(path, encoding="utf-8") as fh:
        event = json.load(fh)
    if not isinstance(event, dict):
        raise SystemExit("the event is not a JSON object")
    return event


def _login(value):
    return (value or {}).get("login") if isinstance(value, dict) else None


def labels_of(issue):
    """The names of an issue's labels."""
    return {
        label.get("name")
        for label in issue.get("labels") or []
        if isinstance(label, dict)
    }


def submission_gate(event):
    """Why the event's issue is not a form submission to act on, or None.

    The issue must be opened by the form's App (BOT: no person can open an
    issue as it), carry the label vineyard-submission and be open.

    Args:
        event: load_event()'s event.

    Returns:
        A short reason, or None.
    """
    issue = event.get("issue")
    if not isinstance(issue, dict) or not isinstance(issue.get("number"), int):
        return "no issue"
    if "pull_request" in issue:
        return "a pull request"
    if _login(issue.get("user")) != vs.BOT:
        return "not opened by the form's App"
    if vs.LABEL not in labels_of(issue):
        return f"no label {vs.LABEL}"
    if issue.get("state") != "open":
        return "not open"
    return None


def check_gate(event):
    """submission_gate(), and a labelled event only for the form's label."""
    why = submission_gate(event)
    if why:
        return why
    action = event.get("action")
    if action not in {"opened", "edited", "labeled"}:
        return f"the action {action}"
    label = event.get("label") if isinstance(event.get("label"), dict) else {}
    if action == "labeled" and label.get("name") != vs.LABEL:
        return "another label"
    return None


def approve_gate(event):
    """Why the event is not the owner's approval of a submission, or None.

    The label `approved`, added by the repository's owner (the sender), to
    an issue that passes submission_gate(). The form's App can add labels
    too, but only as its bot, never as the owner.

    Args:
        event: load_event()'s event.

    Returns:
        A short reason, or None.
    """
    label = event.get("label") if isinstance(event.get("label"), dict) else {}
    if event.get("action") != "labeled" or label.get("name") != vs.APPROVED:
        return f"not the label {vs.APPROVED}"
    owner = _login((event.get("repository") or {}).get("owner"))
    if not owner or _login(event.get("sender")) != owner:
        return "not added by the repository's owner"
    return submission_gate(event)


def private_words():
    """The private lists' words (the PRIVATE_WORDS secret on the runners)."""
    return record.private_words()


def other_submissions(gh, number):
    """The other open submissions' names, as (issue number, name) pairs.

    Args:
        gh: A github.GitHub.
        number: This issue's number (left out).

    Returns:
        A list of pairs; issues that cannot be read are left out.
    """
    out = []
    path = f"{{repo}}/issues?state=open&labels={vs.LABEL}"
    for issue in gh.paged(path):
        if issue.get("number") == number or "pull_request" in issue:
            continue
        if _login(issue.get("user")) != vs.BOT:
            continue
        try:
            data = vs.parse_issue(issue.get("body"))
        except vs.SubmissionError:
            continue
        v = (
            data.get("vineyard")
            if isinstance(data.get("vineyard"), dict)
            else {}
        )
        name = vs.clean(v.get("name"))
        if name:
            out.append((issue["number"], name))
    return out


def upsert_check(gh, number, markdown):
    """Posts the check comment, or edits the one the Action posted before.

    The comment is found by its marker (CHECK_MARK) and its author, the
    Actions' own bot, so no one else's comment is ever edited.

    Args:
        gh: A github.GitHub (the Actions' GITHUB_TOKEN).
        number: The issue's number.
        markdown: The comment.

    Returns:
        "edited" or "posted".
    """
    for comment in gh.paged(f"{{repo}}/issues/{number}/comments"):
        body = comment.get("body") or ""
        if body.startswith(vs.CHECK_MARK) and (
            _login(comment.get("user")) == vs.ACTIONS_BOT
        ):
            gh.request(
                "PATCH",
                f"{{repo}}/issues/comments/{comment['id']}",
                {"body": markdown},
            )
            return "edited"
    gh.request("POST", f"{{repo}}/issues/{number}/comments", {"body": markdown})
    return "posted"
