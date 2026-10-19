"""The GitHub Actions workflows (.github/workflows/): pinned, Linux, least.

Every workflow: each action pinned to a full commit (40 hex digits); GitHub's
Linux machines only (Dan, 2026-10-17); no `${{ github.event... }}` and no
other event text in a `run:` (an issue's or a pull request's text reaches a
script only through a file or the environment). The two vineyard workflows:
no permission at the top, and each job only what it needs; their gates
exactly as reviewed (src/vineyards/SETUP.md), naming the same App's bot as
the scripts and the function; the approval only in the environment
vineyard-pr. release.yml releases only a tag on main's history. PyYAML comes
with the lint tools (requirements-dev.txt).
"""

import os
import re

import pytest
import yaml

from src.vineyards import submission as vs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOWS = os.path.join(ROOT, ".github", "workflows")
NAMES = sorted(n for n in os.listdir(FLOWS) if n.endswith((".yml", ".yaml")))
CHECK_GATE = (
    "contains(github.event.issue.labels.*.name, 'vineyard-submission') && "
    "github.event.issue.user.login == 'hsd-vineyard-form[bot]' && "
    "github.event.issue.state == 'open' && "
    "(github.event.action != 'labeled' || "
    "github.event.label.name == 'vineyard-submission')"
)
APPROVE_GATE = (
    "github.event.label.name == 'approved' && "
    "github.event.sender.login == github.repository_owner && "
    "github.event.issue.user.login == 'hsd-vineyard-form[bot]' && "
    "contains(github.event.issue.labels.*.name, 'vineyard-submission') && "
    "github.event.issue.state == 'open'"
)


def load(name):
    with open(os.path.join(FLOWS, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def steps(flow):
    for job in flow["jobs"].values():
        yield from job.get("steps", [])


@pytest.mark.parametrize("name", NAMES)
def test_every_action_is_pinned_to_a_commit(name):
    for step in steps(load(name)):
        if "uses" in step:
            assert re.fullmatch(
                r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", step["uses"]
            ), step["uses"]


@pytest.mark.parametrize("name", NAMES)
def test_linux_machines_only(name):
    for job in load(name)["jobs"].values():
        assert str(job["runs-on"]).startswith("ubuntu-"), job["runs-on"]


@pytest.mark.parametrize("name", NAMES)
def test_no_event_text_in_a_shell(name):
    for step in steps(load(name)):
        run = step.get("run", "")
        assert "${{" not in run or not re.search(
            r"\$\{\{[^}]*(github\.event|github\.head_ref|inputs\.)", run
        ), (name, run)


@pytest.mark.parametrize("name", ["vineyard-check.yml", "vineyard-approve.yml"])
def test_the_vineyard_workflows_hold_the_least(name):
    flow = load(name)
    assert flow["permissions"] == {}
    assert flow[True] == {"issues": {"types": flow[True]["issues"]["types"]}}
    (job,) = flow["jobs"].values()
    assert job["permissions"] == {"contents": "read", "issues": "write"}
    for step in steps(flow):
        if step.get("uses", "").startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] is False
        if "run" in step:
            assert step["run"].startswith("python -I -B src/vineyards/")


def gate(name):
    (job,) = load(name)["jobs"].values()
    return " ".join(job["if"].split())


def test_the_check_runs_only_on_the_form_s_issues():
    flow = load("vineyard-check.yml")
    assert flow[True]["issues"]["types"] == ["opened", "edited", "labeled"]
    assert gate("vineyard-check.yml") == CHECK_GATE


def test_the_approval_gate_is_as_reviewed():
    flow = load("vineyard-approve.yml")
    assert flow[True]["issues"]["types"] == ["labeled"]
    assert gate("vineyard-approve.yml") == APPROVE_GATE
    (job,) = flow["jobs"].values()
    assert job["environment"] == "vineyard-pr"
    assert flow["concurrency"]["cancel-in-progress"] is False
    (token,) = [
        s
        for s in steps(flow)
        if s.get("uses", "").startswith("actions/create-github-app-token@")
    ]
    assert token["with"] == {
        "client-id": "${{ vars.VINEYARD_PR_CLIENT_ID }}",
        "private-key": "${{ secrets.VINEYARD_PR_PRIVATE_KEY }}",
        "permission-contents": "write",
        "permission-pull-requests": "write",
    }


def test_one_bot_one_label_everywhere():
    # A typo in the bot's name would stop every submission silently.
    with open(
        os.path.join(
            ROOT, "src", "vineyards", "functions", "vineyard-submit", "index.ts"
        ),
        encoding="utf-8",
    ) as fh:
        function = fh.read()
    assert vs.BOT == "hsd-vineyard-form[bot]"
    assert f'BOT = "{vs.BOT}"' in function
    assert f'LABEL = "{vs.LABEL}"' in function
    for name in ("vineyard-check.yml", "vineyard-approve.yml"):
        assert f"'{vs.BOT}'" in gate(name)
        assert f"'{vs.LABEL}'" in gate(name)
    assert f"'{vs.APPROVED}'" in gate("vineyard-approve.yml")


def test_a_release_is_only_of_main_s_history():
    flow = load("release.yml")
    (job,) = flow["jobs"].values()
    checkout = job["steps"][0]
    assert checkout["with"]["fetch-depth"] == 0
    guard = job["steps"][1]["run"]
    assert "git merge-base --is-ancestor HEAD origin/main" in guard
    assert "exit 1" in guard
