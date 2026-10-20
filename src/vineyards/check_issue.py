"""The vineyard-check Action: checks a submission's issue and comments.

Run by .github/workflows/vineyard-check.yml when an issue is opened, edited
or labelled (python -I -B src/vineyards/check_issue.py). It reads the issue
from $GITHUB_EVENT_PATH; acts only on the form's issues (opened by the
form's App, labelled vineyard-submission, open: actions.check_gate());
checks the submission again with the repository's current data
(submission.review(); a change to a listed vineyard is compared with that
vineyard's entry in the vineyard file as it is now); and posts one comment,
marked CHECK_MARK, which it edits when the issue changes. It needs GH_TOKEN
(the Actions' token, Issues write) and GITHUB_REPOSITORY; PRIVATE_WORDS, an
optional secret, is never printed. Standard library only.
"""

import os
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


def main(event_path=None, root=ROOT):
    """Checks the event's issue and comments on it.

    Args:
        event_path: The event file (default: $GITHUB_EVENT_PATH).
        root: The repository.

    Returns:
        The exit status: 0, also when the event is not one to act on.
    """
    event = actions.load_event(event_path)
    why = actions.check_gate(event)
    if why:
        print(f"nothing to do: {why}")
        return 0
    number = event["issue"]["number"]
    gh = github.GitHub(
        os.environ.get("GH_TOKEN", ""), os.environ["GITHUB_REPOSITORY"]
    )
    try:
        data = vs.parse_issue(event["issue"].get("body"))
    except vs.SubmissionError as error:
        markdown, ok = vs.not_layout(error), False
    else:
        markdown, ok, _ = vs.review(
            data,
            number,
            actions.other_submissions(gh, number),
            actions.private_words(),
            root=root,
        )
    done = actions.upsert_check(gh, number, markdown)
    print(
        f"issue #{number}: check comment {done}: "
        + ("ready for review" if ok else "something to look at")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
