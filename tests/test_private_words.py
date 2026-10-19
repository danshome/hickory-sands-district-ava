"""The private-words hook (src/checks/check_private_words.py).

The list, .private-words, is gitignored, so a git worktree has no copy of it.
These build a throwaway repository with a worktree and check that the hook run
from the worktree still refuses a listed word (it reads the main checkout's
list), and passes where there is no list anywhere, as on GitHub's runners.
Standard library and git only, so the lint workflow runs these.
"""

import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "src", "checks", "check_private_words.py")

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def git(*args, cwd):
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull},
    )


@pytest.fixture
def checkouts(tmp_path):
    """A main checkout and a worktree of it, each with a copy of the hook."""
    main = tmp_path / "main"
    (main / "src" / "checks").mkdir(parents=True)
    shutil.copy(HOOK, main / "src" / "checks")
    git("init", "-q", cwd=main)
    git("add", ".", cwd=main)
    git(
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.invalid",
        "commit",
        "-q",
        "-m",
        "hook",
        cwd=main,
    )
    tree = tmp_path / "tree"
    git("worktree", "add", "-q", str(tree), cwd=main)
    return main, tree


def run_hook(checkout, text):
    sample = checkout / "sample.txt"
    sample.write_text(text, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "-I",
            str(checkout / "src/checks/check_private_words.py"),
            str(sample),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_worktree_uses_the_main_checkouts_list(checkouts):
    main, tree = checkouts
    (main / ".private-words").write_text("# a comment\nZebrafinch\n")
    assert run_hook(tree, "a zebrafinch here").returncode == 1
    assert run_hook(tree, "nothing private").returncode == 0


def test_the_checkouts_own_list_comes_first(checkouts):
    main, tree = checkouts
    (main / ".private-words").write_text("Zebrafinch\n")
    (tree / ".private-words").write_text("Kestrel\n")
    assert run_hook(tree, "a kestrel").returncode == 1
    assert run_hook(tree, "a zebrafinch").returncode == 0


def test_no_list_anywhere_passes(checkouts):
    _, tree = checkouts
    assert run_hook(tree, "anything at all").returncode == 0
