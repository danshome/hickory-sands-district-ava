"""The two vineyard Actions' scripts, run as the workflows run them.

src/vineyards/check_issue.py and approve.py run here with `python -I -B`,
as .github/workflows/vineyard-check.yml and vineyard-approve.yml run them,
on sample issue events, against a local stand-in for GitHub's API
(GITHUB_API_URL, as GitHub's runners set it): a submission opened by the
form's App; the same edited; the label `approved` added by the owner; the
same label added by someone else; a forged issue (the form's layout, opened
by a person); a body not in the layout; a submission that overlaps a
vineyard on the map; a pin with no outline; a second approval. approve.py
works on a copy of the files it changes. Standard library only.
"""

import base64
import copy
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.parse

import pytest

from src.vineyards import submission as vs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "danshome/hickory-sands-district-ava"
SENT = "2026-10-19T08:30:00.000Z"
GOOD = {
    "form": "hsd-vineyard",
    "version": 1,
    "id": "3f2b8c1e-5d4a-4e6f-9a7b-1c2d3e4f5a6b",
    "vineyard": {
        "name": "Prairie Gap Vineyard",
        "county": "Mason",
        "planted": "planted",
        "acres": 4.5,
        "year": 2019,
        "varieties": ["Tempranillo", "Mourvèdre"],
    },
    "blocks": [
        [
            [-99.295, 30.865],
            [-99.2925, 30.865],
            [-99.2925, 30.8632],
            [-99.295, 30.8632],
        ]
    ],
    "pin": None,
    "contact": {"name": "Jane Q. Grower", "email": "jane@example.com"},
    "agree": {"public": True, "permission": True},
    "website": "",
}
CERTENBURG = [
    [-99.19212, 30.99374],
    [-99.189576, 30.993743],
    [-99.189571, 30.991343],
    [-99.192115, 30.991339],
]


def body_of(raw):
    sub, errors, _ = vs.check(raw, year=2026)
    assert not errors
    return vs.issue_body(sub, SENT)


class GitHubStandIn(http.server.ThreadingHTTPServer):
    """GitHub's REST API, as much as the scripts use, in memory."""

    def __init__(self):
        """Starts on a free local port."""
        super().__init__(("127.0.0.1", 0), Handler)
        self.calls = []
        self.issues = []
        self.comments = {}
        self.refs = set()
        self.blobs = {}
        self.pulls = []
        self.pulls_fail = False
        self.policy = {
            "protected_branches": False,
            "custom_branch_policies": True,
        }
        self.branch_policies = [{"name": "main", "type": "branch"}]

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"


class Handler(http.server.BaseHTTPRequestHandler):
    """Answers each path the scripts call; records every call."""

    def log_message(self, *args):
        """Keeps the test's output quiet."""

    def _send(self, status, data):
        text = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(text)))
        self.end_headers()
        self.wfile.write(text)

    def _route(self, method):
        gh = self.server
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"null")
        url = urllib.parse.urlsplit(self.path)
        token = self.headers.get("Authorization", "")
        gh.calls.append((method, url.path, token, body))
        base = f"/repos/{REPO}"
        path = url.path.removeprefix(base)
        query = dict(urllib.parse.parse_qsl(url.query))
        if method == "POST" and path == "/issues":
            made = {"number": 500 + len(gh.issues), **body, "state": "open"}
            gh.issues.append(made)
            return self._send(201, made)
        if method == "GET" and path == "/issues":
            return self._send(
                200, gh.issues if query.get("page") == "1" else []
            )
        if path.startswith("/issues/") and path.endswith("/comments"):
            number = int(path.split("/")[2])
            found = gh.comments.setdefault(number, [])
            if method == "GET":
                return self._send(
                    200, found if query.get("page") == "1" else []
                )
            item = {
                "id": 1000 + len(found),
                "body": body["body"],
                "user": {"login": "github-actions[bot]"},
            }
            found.append(item)
            return self._send(201, item)
        if method == "PATCH" and path.startswith("/issues/comments/"):
            cid = int(path.rsplit("/", 1)[1])
            for found in gh.comments.values():
                for item in found:
                    if item["id"] == cid:
                        item["body"] = body["body"]
                        return self._send(200, item)
            return self._send(404, {"message": "Not Found"})
        if method == "GET" and path == "/environments/vineyard-pr":
            return self._send(200, {"deployment_branch_policy": gh.policy})
        if method == "GET" and path.endswith("/deployment-branch-policies"):
            return self._send(200, {"branch_policies": gh.branch_policies})
        if method == "GET" and path.startswith("/git/ref/heads/"):
            ref = "refs/heads/" + path.removeprefix("/git/ref/heads/")
            if ref in gh.refs:
                return self._send(200, {"ref": ref})
            return self._send(404, {"message": "Not Found"})
        if method == "POST" and path == "/pulls" and gh.pulls_fail:
            return self._send(422, {"message": "Validation Failed"})
        if method == "GET" and path.startswith("/git/commits/"):
            return self._send(200, {"tree": {"sha": "tree-base"}})
        if method == "POST" and path == "/git/blobs":
            sha = f"blob-{len(gh.blobs)}"
            gh.blobs[sha] = base64.b64decode(body["content"])
            return self._send(201, {"sha": sha})
        if method == "POST" and path == "/git/trees":
            return self._send(201, {"sha": "tree-new", "tree": body["tree"]})
        if method == "POST" and path == "/git/commits":
            return self._send(201, {"sha": f"commit-{len(gh.calls)}"})
        if method == "POST" and path == "/git/refs":
            if body["ref"] in gh.refs:
                return self._send(422, {"message": "Reference already exists"})
            gh.refs.add(body["ref"])
            return self._send(201, {"ref": body["ref"]})
        if method == "PATCH" and path.startswith("/git/refs/heads/"):
            return self._send(200, {"ref": path})
        if method == "GET" and path == "/pulls":
            return self._send(200, gh.pulls)
        if method == "POST" and path == "/pulls":
            pull = {
                "number": 77,
                "html_url": f"https://github.com/{REPO}/pull/77",
                **body,
            }
            gh.pulls.append(pull)
            return self._send(201, pull)
        if method == "POST" and path.endswith("/labels"):
            return self._send(200, [{"name": n} for n in body["labels"]])
        return self._send(404, {"message": f"no stand-in for {path}"})

    def do_GET(self):
        """GET."""
        self._route("GET")

    def do_POST(self):
        """POST."""
        self._route("POST")

    def do_PATCH(self):
        """PATCH."""
        self._route("PATCH")


@pytest.fixture
def github():
    server = GitHubStandIn()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def copy_root(tmp_path):
    """The files approve.py reads and changes, in a throwaway folder."""
    for rel in (
        vs.VINEYARDS,
        vs.LLANO,
        vs.DISTRICT,
        "docs/assets/aquifer/context.geojson",
        "docs/vineyards.html",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(os.path.join(ROOT, rel), tmp_path / rel)
    shutil.copytree(
        os.path.join(ROOT, "docs", "assets", "vineyards"),
        tmp_path / "docs" / "assets" / "vineyards",
    )
    (tmp_path / vs.WELLS).symlink_to(os.path.join(ROOT, vs.WELLS))
    return tmp_path


def issue(number=12, body=None, user=vs.BOT, labels=(vs.LABEL,), state="open"):
    return {
        "number": number,
        "title": "Vineyard submission, Mason County",
        "body": body_of(GOOD) if body is None else body,
        "user": {"login": user},
        "labels": [{"name": n} for n in labels],
        "state": state,
    }


def event(action, the_issue, label=None, sender="danshome"):
    out = {
        "action": action,
        "issue": the_issue,
        "sender": {"login": sender},
        "repository": {"full_name": REPO, "owner": {"login": "danshome"}},
    }
    if label:
        out["label"] = {"name": label}
    return out


def run(script, github, tmp_path, the_event, *args):
    path = tmp_path / "event.json"
    path.write_text(json.dumps(the_event), encoding="utf-8")
    env = {
        "PATH": os.environ.get("PATH", ""),
        "GITHUB_EVENT_PATH": str(path),
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_API_URL": github.url,
        "GITHUB_SHA": "a" * 40,
        "GH_TOKEN": "actions-token",
        "PR_TOKEN": "pr-app-token",
        "PRIVATE_WORDS": "quillfeather\n",
    }
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            os.path.join(ROOT, "src", "vineyards", script),
            *args,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def comments(github, number=12):
    return [c["body"] for c in github.comments.get(number, [])]


# ---- vineyard-check ---------------------------------------------------------


def test_an_opened_submission_gets_one_check_and_an_edit_updates_it(
    github, tmp_path
):
    the_issue = issue()
    github.issues = [the_issue, issue(13, user=vs.BOT)]
    done = run("check_issue.py", github, tmp_path, event("opened", the_issue))
    assert done.returncode == 0, done.stderr
    # the other open submission, #13, has the same name: Dan looks first
    assert "posted: something to look at" in done.stdout
    first = comments(github)
    assert len(first) == 1
    assert first[0].startswith(vs.CHECK_MARK)
    assert "something to look at" in first[0]
    assert "Another open submission has this name: #13." in first[0]
    assert "the private list was checked" in first[0]
    assert "quillfeather" not in first[0]
    # an edit (here, by the owner) changes the same comment
    changed = issue(
        body=body_of(
            dict(
                copy.deepcopy(GOOD),
                vineyard=dict(GOOD["vineyard"], name="Prairie Gap Vineyards"),
            )
        )
    )
    done = run("check_issue.py", github, tmp_path, event("edited", changed))
    assert done.returncode == 0, done.stderr
    assert "edited: ready for review" in done.stdout
    assert len(comments(github)) == 1
    assert "Another open submission" not in comments(github)[0]
    assert "ready for review" in comments(github)[0]
    # every call with the Actions' token
    assert {c[2] for c in github.calls} == {"Bearer actions-token"}


@pytest.mark.parametrize(
    ("the_event", "why"),
    [
        (
            event("opened", issue(user="mallory")),
            "not opened by the form's App",
        ),
        (event("opened", issue(labels=())), "no label vineyard-submission"),
        (event("edited", issue(state="closed")), "not open"),
        (event("labeled", issue(), label="approved"), "another label"),
        (event("closed", issue()), "the action closed"),
    ],
)
def test_the_check_acts_only_on_the_form_s_issues(
    github, tmp_path, the_event, why
):
    done = run("check_issue.py", github, tmp_path, the_event)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == f"nothing to do: {why}"
    assert github.calls == []


def test_a_body_not_in_the_layout_is_said_so(github, tmp_path):
    forged = issue(body=vs.MARK + "\n<script>alert(1)</script>\n")
    done = run("check_issue.py", github, tmp_path, event("opened", forged))
    assert done.returncode == 0, done.stderr
    (text,) = comments(github)
    assert "this is not the form's layout" in text
    assert "<script>" not in text


def test_an_overlap_and_a_pin_are_flagged(github, tmp_path):
    overlap = dict(
        copy.deepcopy(GOOD),
        blocks=[CERTENBURG],
        vineyard=dict(GOOD["vineyard"], name="Certenburg Vineyard"),
    )
    run(
        "check_issue.py",
        github,
        tmp_path,
        event("opened", issue(12, body_of(overlap))),
    )
    (text,) = comments(github, 12)
    assert "something to look at" in text
    assert "overlaps Certenburg Vineyard, block 1" in text
    assert "already on the map" in text
    assert "TWDB wells within 1 km of the blocks: 28 " in text
    pin = dict(copy.deepcopy(GOOD), blocks=[], pin=[-99.294, 30.864])
    run(
        "check_issue.py",
        github,
        tmp_path,
        event("opened", issue(14, body_of(pin))),
    )
    (text,) = comments(github, 14)
    assert "No outline: only a pin" in text


# ---- vineyard-approve -------------------------------------------------------


def test_the_owner_s_label_opens_a_complete_pull_request(
    github, tmp_path, copy_root
):
    the_issue = issue(labels=(vs.LABEL, vs.APPROVED))
    github.issues = [the_issue]
    done = run(
        "approve.py",
        github,
        tmp_path,
        event("labeled", the_issue, label=vs.APPROVED),
        "--root",
        str(copy_root),
        "--today",
        "2026-10-19",
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "pull request #77 open" in done.stdout
    (pull,) = github.pulls
    assert pull["title"] == "Vineyard: Prairie Gap Vineyard (#12)"
    assert pull["head"] == "vineyard/issue-12"
    assert pull["base"] == "main"
    assert pull["body"].startswith("Closes #12.")
    assert "refs/heads/vineyard/issue-12" in github.refs
    # the branch, commit and pull request with the PR App's token; the
    # comments with the Actions' own
    by_token = {}
    for method, path, token, _ in github.calls:
        by_token.setdefault(token, set()).add((method, path.split("/")[4]))
    assert ("POST", "pulls") in by_token["Bearer pr-app-token"]
    assert ("POST", "git") in by_token["Bearer pr-app-token"]
    assert all(p != "git" for _, p in by_token["Bearer actions-token"])
    # the files: the vineyard file with the new block, the site's data
    tree = next(c for c in github.calls if c[1].endswith("/git/trees"))[3]
    paths = {e["path"]: github.blobs[e["sha"]] for e in tree["tree"]}
    assert vs.VINEYARDS in paths
    assert "docs/assets/vineyards/vineyards.geojson" in paths
    assert "docs/assets/vineyards/record.json" in paths
    # the page's list, readable without JavaScript (#171)
    assert b">Prairie Gap Vineyard</h4>" in paths["docs/vineyards.html"]
    added = [
        line
        for line in paths[vs.VINEYARDS].decode().splitlines()
        if "Prairie Gap" in line
    ]
    assert len(added) == 1
    props = json.loads(added[0].rstrip(","))["properties"]
    assert props["category"] == "hsd"
    assert props["year"] == 2019
    assert props["varieties"] == ["Tempranillo", "Mourvèdre"]
    assert "issue #12" in props["source"]
    assert "2026-10-19" in props["source"]
    register = json.loads(paths["docs/assets/vineyards/register.json"])
    entry = [
        v for v in register["vineyards"] if v["name"] == "Prairie Gap Vineyard"
    ]
    assert entry[0]["year"] == 2019
    for data in paths.values():
        assert b"jane" not in data.lower()
    # and a comment back with the link
    assert any("pull request #77" in c for c in comments(github))
    # a second approval, the first pull request's branch still there: the
    # branch is never moved (it may hold the petitioner's own commits)
    shutil.copy(os.path.join(ROOT, vs.VINEYARDS), copy_root / vs.VINEYARDS)
    done = run(
        "approve.py",
        github,
        tmp_path,
        event("labeled", the_issue, label=vs.APPROVED),
        "--root",
        str(copy_root),
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert "is there already" in comments(github)[-1]
    assert not any(
        m == "PATCH" and "/git/refs/" in p for m, p, _, _ in github.calls
    )
    assert len(github.pulls) == 1


@pytest.mark.parametrize(
    ("the_event", "why"),
    [
        (
            event("labeled", issue(), label=vs.APPROVED, sender="mallory"),
            "not added by the repository's owner",
        ),
        (
            event("labeled", issue(), label=vs.APPROVED, sender=vs.BOT),
            "not added by the repository's owner",
        ),
        (
            event("labeled", issue(user="mallory"), label=vs.APPROVED),
            "not opened by the form's App",
        ),
        (
            event("labeled", issue(labels=()), label=vs.APPROVED),
            "no label vineyard-submission",
        ),
        (
            event("labeled", issue(state="closed"), label=vs.APPROVED),
            "not open",
        ),
        (event("labeled", issue(), label="bug"), "not the label approved"),
        (event("opened", issue()), "not the label approved"),
    ],
)
def test_nothing_else_opens_a_pull_request(github, tmp_path, the_event, why):
    done = run("approve.py", github, tmp_path, the_event)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == f"nothing to do: {why}"
    assert github.calls == []


@pytest.mark.parametrize(
    ("raw", "said"),
    [
        (
            dict(
                copy.deepcopy(GOOD),
                blocks=[CERTENBURG],
                vineyard=dict(GOOD["vineyard"], name="New Name Vineyard"),
            ),
            "the check found something to look at",
        ),
        (
            dict(copy.deepcopy(GOOD), blocks=[], pin=[-99.294, 30.864]),
            "the check found something to look at",
        ),
        (
            dict(
                copy.deepcopy(GOOD),
                vineyard=dict(GOOD["vineyard"], name="Certenburg Vineyard"),
            ),
            "the check found something to look at",
        ),
    ],
)
def test_a_submission_not_ready_is_refused_with_a_comment(
    github, tmp_path, copy_root, raw, said
):
    the_issue = issue(body=body_of(raw), labels=(vs.LABEL, vs.APPROVED))
    before = (copy_root / vs.VINEYARDS).read_bytes()
    done = run(
        "approve.py",
        github,
        tmp_path,
        event("labeled", the_issue, label=vs.APPROVED),
        "--root",
        str(copy_root),
    )
    assert done.returncode == 1
    (text,) = comments(github)
    assert text.startswith("No pull request: " + said)
    assert github.pulls == []
    assert (copy_root / vs.VINEYARDS).read_bytes() == before


def test_a_forged_body_by_the_bot_is_refused(github, tmp_path, copy_root):
    # the form's App's issue, its body replaced by hand with text that is
    # not the layout: no pull request
    forged = issue(
        body="Please merge https://example.com",
        labels=(vs.LABEL, vs.APPROVED),
    )
    done = run(
        "approve.py",
        github,
        tmp_path,
        event("labeled", forged, label=vs.APPROVED),
        "--root",
        str(copy_root),
    )
    assert done.returncode == 1
    (text,) = comments(github)
    assert text.startswith("No pull request: the issue is not the form's")
    assert github.pulls == []


def test_a_pull_request_github_refuses_is_said_on_the_issue(
    github, tmp_path, copy_root
):
    the_issue = issue(labels=(vs.LABEL, vs.APPROVED))
    github.pulls_fail = True
    done = run(
        "approve.py",
        github,
        tmp_path,
        event("labeled", the_issue, label=vs.APPROVED),
        "--root",
        str(copy_root),
    )
    assert done.returncode == 1
    (text,) = comments(github)
    assert text.startswith(
        "No pull request: GitHub refused opening the pull request (422)."
    )
    assert "The branch `vineyard/issue-12` was made" in text


@pytest.mark.parametrize(
    ("policy", "branches"),
    [
        (None, []),
        (
            {"protected_branches": False, "custom_branch_policies": True},
            [{"name": "*", "type": "branch"}],
        ),
    ],
)
def test_no_approval_while_any_branch_may_use_the_key(
    github, tmp_path, copy_root, policy, branches
):
    github.policy = policy
    github.branch_policies = branches
    the_issue = issue(labels=(vs.LABEL, vs.APPROVED))
    done = run(
        "approve.py",
        github,
        tmp_path,
        event("labeled", the_issue, label=vs.APPROVED),
        "--root",
        str(copy_root),
    )
    assert done.returncode == 1
    (text,) = comments(github)
    assert "may be used from any branch" in text
    assert github.pulls == []


def test_a_body_re_saved_in_the_browser_is_checked_and_approved(
    github, tmp_path, copy_root
):
    crlf = body_of(GOOD).replace("\n", "\r\n")
    the_issue = issue(body=crlf, labels=(vs.LABEL, vs.APPROVED))
    github.issues = [the_issue]
    done = run("check_issue.py", github, tmp_path, event("edited", the_issue))
    assert done.returncode == 0, done.stderr
    assert "ready for review" in comments(github)[0]
    done = run(
        "approve.py",
        github,
        tmp_path,
        event("labeled", the_issue, label=vs.APPROVED),
        "--root",
        str(copy_root),
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert len(github.pulls) == 1


# ---- a change to a listed vineyard ------------------------------------------

BLACKMON = "blackmon-vineyard"
NEW_BLOCK = [
    [-99.3680, 30.8225],
    [-99.3672, 30.8225],
    [-99.3672, 30.8218],
    [-99.3680, 30.8218],
]


def change_body(**changes):
    """A change to Blackmon Vineyard: blocks 1 and 3 kept, 2 drawn anew."""
    listed = vs.listed_vineyards()[BLACKMON]
    raw = copy.deepcopy(GOOD)
    raw.update(
        version=2,
        changes=BLACKMON,
        note="Block 2 replanted further east in 2024.",
        blocks=[listed["blocks"][0], NEW_BLOCK, listed["blocks"][2]],
    )
    raw["vineyard"].update(
        name="Blackmon Estate Vineyard",
        year=2015,
        varieties=["Tempranillo", "Tannat"],
    )
    raw.update(changes)
    sub, errors, _ = vs.check(raw, year=2026)
    assert not errors, errors
    return vs.issue_body(sub, SENT, listed)


def file_lines(text, vid):
    return [
        json.loads(line.rstrip(","))
        for line in text.splitlines()
        if f'"vineyard_id":"{vid}"' in line
    ]


def test_a_change_is_checked_against_the_listing(github, tmp_path):
    the_issue = issue(body=change_body(), labels=(vs.LABEL, vs.CHANGE_LABEL))
    github.issues = [the_issue]
    done = run("check_issue.py", github, tmp_path, event("opened", the_issue))
    assert done.returncode == 0, done.stderr
    (check,) = comments(github)
    assert "### The check: ready for review" in check
    assert f"A change to **`Blackmon Vineyard`** (`{BLACKMON}`)" in check
    assert (
        "| Name | `Blackmon Vineyard` | `Blackmon Estate Vineyard` |" in check
    )
    assert "3, " in check
    assert "2 drawn as listed" in check
    assert "`Block 2 replanted further east in 2024.`" in check
    # its own listed blocks are not "already on the map", nor its name
    assert "Already on the map" not in check
    assert "already on the map (" not in check
    assert "replaces the vineyard's blocks and fields" in check


def test_a_change_that_changes_nothing_or_names_no_vineyard_is_held(
    github, tmp_path
):
    listed = vs.listed_vineyards()[BLACKMON]
    same = change_body(blocks=listed["blocks"])
    same = same.replace("Blackmon Estate Vineyard", "Blackmon Vineyard")
    same = same.replace('"year":2015', '"year":null').replace(
        '"varieties":["Tempranillo","Tannat"]', '"varieties":[]'
    )
    the_issue = issue(body=same)
    github.issues = [the_issue]
    done = run("check_issue.py", github, tmp_path, event("opened", the_issue))
    assert done.returncode == 0, done.stderr
    assert "Nothing would change" in comments(github)[-1]
    assert "something to look at" in comments(github)[-1]
    gone = change_body().replace(f'"changes":"{BLACKMON}"', '"changes":"gone"')
    the_issue = issue(13, body=gone)
    github.issues = [the_issue]
    done = run("check_issue.py", github, tmp_path, event("opened", the_issue))
    assert done.returncode == 0, done.stderr
    assert "is not in the vineyard file" in comments(github, 13)[-1]
    assert "something to look at" in comments(github, 13)[-1]


def test_an_approved_change_replaces_the_vineyard_never_adds_one(
    github, tmp_path, copy_root
):
    before = (copy_root / vs.VINEYARDS).read_text(encoding="utf-8")
    old = file_lines(before, BLACKMON)
    total = len(json.loads(before)["features"])
    the_issue = issue(
        body=change_body(), labels=(vs.LABEL, vs.CHANGE_LABEL, vs.APPROVED)
    )
    github.issues = [the_issue]
    done = run(
        "approve.py",
        github,
        tmp_path,
        event("labeled", the_issue, label=vs.APPROVED),
        "--root",
        str(copy_root),
        "--today",
        "2026-10-19",
    )
    assert done.returncode == 0, done.stdout + done.stderr
    (pull,) = github.pulls
    assert pull["title"] == "Vineyard change: Blackmon Estate Vineyard (#12)"
    assert "(no new entry)" in pull["body"]
    tree = next(c for c in github.calls if c[1].endswith("/git/trees"))[3]
    paths = {e["path"]: github.blobs[e["sha"]] for e in tree["tree"]}
    after = paths[vs.VINEYARDS].decode()
    # the same number of blocks in the file; the vineyard's three replaced
    assert len(json.loads(after)["features"]) == total
    assert '"name":"Blackmon Vineyard"' not in after
    new = file_lines(after, BLACKMON)
    assert len(new) == 3
    assert {f["properties"]["name"] for f in new} == {
        "Blackmon Estate Vineyard"
    }
    assert all(f["properties"]["year"] == 2015 for f in new)
    assert all(f["properties"]["category"] == "hsd" for f in new)
    # blocks 1 and 3 kept as they were, with the change noted; 2 is new
    kept = [f for f in new if f["properties"]["block"] in ("1", "3")]
    assert [f["geometry"] for f in kept] == [
        old[0]["geometry"],
        old[2]["geometry"],
    ]
    for f in kept:
        assert f["properties"]["source"].startswith(
            old[0]["properties"]["source"]
        )
        assert "issue #12" in f["properties"]["source"]
    (drawn,) = [f for f in new if f["properties"]["block"] == "2"]
    assert drawn["properties"]["source"].startswith("Changed through")
    # the site's data: one entry, the same id, the new name
    register = json.loads(paths["docs/assets/vineyards/register.json"])
    entries = [v for v in register["vineyards"] if v["id"] == BLACKMON]
    assert len(entries) == 1
    assert entries[0]["name"] == "Blackmon Estate Vineyard"
    assert len(entries[0]["vids"]) == 3
    known = json.loads(paths["docs/assets/vineyards/known.json"])
    assert known[BLACKMON]["name"] == "Blackmon Estate Vineyard"
    assert any("makes this change" in c for c in comments(github))
    for data in paths.values():
        assert b"jane" not in data.lower()


class FunctionStandIn(http.server.ThreadingHTTPServer):
    """The vineyard function's /reconcile, answering as told."""

    def __init__(self, status, body):
        """Starts on a free local port."""
        super().__init__(("127.0.0.1", 0), ReconcileHandler)
        self.answer = (status, body)
        self.calls = 0

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}/vineyard-submit"


class ReconcileHandler(http.server.BaseHTTPRequestHandler):
    """POST /vineyard-submit/reconcile."""

    def log_message(self, *args):
        """Keeps the test's output quiet."""

    def do_POST(self):
        """Answers as the stand-in was told."""
        self.server.calls += 1
        status, body = self.server.answer
        if self.path != "/vineyard-submit/reconcile":
            status, body = 404, {"error": "not here"}
        text = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(text)))
        self.end_headers()
        self.wfile.write(text)


def reconcile(github, function):
    env = {
        "PATH": os.environ.get("PATH", ""),
        "FUNCTION_URL": function.url,
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_API_URL": github.url,
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_RUN_ID": "4242",
        "GH_TOKEN": "actions-token",
    }
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            os.path.join(ROOT, "src", "vineyards", "reconcile.py"),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.fixture
def function_server(request):
    server = FunctionStandIn(*request.param)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize(
    "function_server",
    [(200, {"ok": True, "ran": True, "linked": 0, "closed": 1})],
    indirect=True,
)
def test_the_daily_check_passing_says_nothing_on_github(
    github, function_server
):
    done = reconcile(github, function_server)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "the vineyard function's table is right" in done.stdout
    assert function_server.calls == 1
    assert github.calls == []


@pytest.mark.parametrize(
    "function_server",
    [(500, {"ok": False, "failed": "sweep"})],
    indirect=True,
)
def test_the_daily_check_failing_is_said_on_one_issue(github, function_server):
    done = reconcile(github, function_server)
    assert done.returncode == 1
    (made,) = github.issues
    assert made["title"] == "Vineyard form: the daily check failed"
    assert "500, sweep" in made["body"]
    assert "actions/runs/4242" in made["body"]
    # failing again comments on that issue; no second issue
    done = reconcile(github, function_server)
    assert done.returncode == 1
    assert len(github.issues) == 1
    assert "500, sweep" in comments(github, made["number"])[0]
