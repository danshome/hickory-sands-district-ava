"""The vineyard form's Edge Function, as Dan deploys it, against stand-ins.

src/vineyards/bundle_function.py makes the one file Dan pastes into the
Supabase dashboard; node runs that same file here (it reads TypeScript that
only needs its types erased), with tests/vineyard_standin.mjs standing in for
Supabase's table, Cloudflare's Turnstile and GitHub's API. The cases: CORS
for one origin; the request's type and size; Turnstile's answer (a success,
for the site, for the form's action, never a test key's); the trap; the
rules and the private words; the row and the issue (no contact in the
issue, the App's token asked for Issues only); a retry; the limits per
address and per day; GitHub or the table failing; a dropped label; missing
secrets and the health check; the App's key in each form Dan may paste it;
and the webhook (its signature, closing, reopening, the sweep a year after
an issue is closed). Skipped without node 22 or later.
"""

import json
import os
import re
import shutil
import socket
import subprocess

import pytest

from src.vineyards import bundle_function
from src.vineyards import check_function

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
STANDIN = os.path.join(ROOT, "tests", "vineyard_standin.mjs")
SOURCE = bundle_function.SOURCE
SITE = "https://hickorysandsdistrictava.org"


def node_major():
    if not NODE:
        return 0
    out = subprocess.run(
        [NODE, "--version"], capture_output=True, text=True, check=True
    ).stdout
    return int(out.strip().lstrip("v").split(".")[0])


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    path = tmp_path_factory.mktemp("function") / "index.mts"
    path.write_text(bundle_function.bundle(), encoding="utf-8")
    return str(path)


@pytest.fixture(scope="module")
def out(bundle):
    if node_major() < 22:
        pytest.skip("node 22 or later is not installed")
    done = subprocess.run(
        [NODE, "--experimental-strip-types", STANDIN, "cases", bundle],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return json.loads(done.stdout)


def test_only_the_site_may_send(out):
    assert out["preflight"]["status"] == 204
    assert out["preflight"]["acao"] == SITE
    assert out["preflightOther"]["status"] == 403
    assert out["preflightOther"]["acao"] is None
    for case in ("otherOrigin", "noOrigin"):
        assert out[case]["status"] == 403, case
        assert out[case]["acao"] is None, case


def test_the_request_is_json_and_small(out):
    assert out["get"]["status"] == 405
    assert out["textPlain"]["status"] == 415
    assert out["tooLarge"]["status"] == 413
    for case in ("notJson", "array", "nan"):
        assert out[case]["status"] == 400, case


def test_turnstile_must_pass_for_the_site_and_the_form(out):
    for token in ("", "fail", "test-key", "other-host", "other-action"):
        assert out[f"turnstile:{token}"]["status"] == 403, token
        assert out[f"turnstile:{token}"]["body"] == {"error": "turnstile"}
    assert out["turnstile:down"]["status"] == 503
    assert out["afterTurnstile"] == {"rows": 0, "issues": 0}


def test_the_trap_the_rules_and_the_private_words(out):
    assert out["trap"] == {
        "status": 200,
        "body": {"ok": True, "reference": None},
        "acao": SITE,
    }
    assert out["invalid"]["status"] == 422
    assert out["invalid"]["body"]["errors"][0]["field"] == "name"
    assert out["privateWord"]["status"] == 422
    assert "quillfeather" not in json.dumps(out["privateWord"]).lower()
    assert out["afterRefusals"] == {"rows": 0, "issues": 0}


def test_a_good_one_keeps_the_contact_privately_and_posts_the_rest(out):
    assert out["good"]["body"] == {"ok": True, "reference": 9001}
    row = out["goodRow"]
    assert row["issue_number"] == 9001
    assert row["contact_name"] == "Jane Q. Grower"
    assert row["email"] == "jane@example.com"
    assert row["phone"] == "(325) 555-0100"
    assert re.fullmatch(r"[0-9a-f]{32}", row["ip_hash"])
    assert "203.0.113.7" not in json.dumps(row)
    issue = out["goodIssue"]
    assert issue["title"] == "Vineyard submission, Mason County"
    assert [label["name"] for label in issue["labels"]] == [
        "vineyard-submission"
    ]
    for private in ("Jane", "jane@example.com", "555", row["submission_id"]):
        assert private not in issue["body"], private
    assert "Prairie Gap Vineyard" in issue["body"]
    # the App's token: this repository, Issues only
    assert out["tokenAsked"] == {
        "token": {
            "repositories": ["hickory-sands-district-ava"],
            "permissions": {"issues": "write"},
        }
    }
    # the log: the issue's number, nothing else
    assert out["logs"] == ["vineyard submission 9001"]


def test_a_retry_gets_the_first_answer(out):
    assert out["again"]["body"] == {
        "ok": True,
        "reference": 9001,
        "again": True,
    }
    assert out["afterAgain"] == {"rows": 1, "issues": 1}
    assert out["inProgress"]["status"] == 409
    # a send that died before its issue was known is sent anew, not stuck
    assert out["stale"]["status"] == 200
    assert out["staleRow"]["issue_number"] == out["stale"]["body"]["reference"]
    # and a row that never got an issue goes a week on
    assert out["orphans"] == ["3f2b8c1e-5d4a-4e6f-9a7b-000000000096"]


def test_the_limits(out):
    assert out["perIp"] == [200] * 5 + [429]
    assert out["perIpLast"]["body"] == {"error": "limit-ip"}
    assert out["perDay"] == [200] * 30 + [429]
    assert out["perDayLast"]["body"] == {"error": "limit-day"}
    assert out["nextDay"]["status"] == 200


def test_a_failure_frees_the_row_and_says_so(out):
    assert out["githubFails"]["status"] == 502
    assert out["githubFails"]["acao"] == SITE  # the page can read it
    assert out["afterGithubFails"] == {"rows": 0, "issues": 0}
    assert out["retry"]["body"] == {"ok": True, "reference": 9001}
    assert out["tokenFails"]["status"] == 502
    assert out["afterTokenFails"] == {"rows": 0}
    assert out["dbDown"]["status"] == 503
    assert out["dbDownIssues"] == 0


def test_a_dropped_label_is_added_again(out):
    assert out["dropped"]["status"] == 200
    assert out["droppedLabels"] == ["vineyard-submission"]


def test_missing_secrets_and_the_health_check(out):
    assert out["notReady"]["status"] == 503
    health = out["health"]["body"]
    assert health["ready"] is False
    assert health["missing"] == ["TURNSTILE_SECRET", "IP_SALT"]
    assert health["address_headers"] == ["cf-connecting-ip", "x-forwarded-for"]
    assert health["forwarded_entries"] == 2
    assert "198.51.100.1" not in json.dumps(health)
    assert out["healthReady"]["body"]["ready"] is True


@pytest.mark.parametrize(
    "form", ["pkcs1-lines", "pkcs1-one-line", "pkcs8-lines", "pkcs8-escaped"]
)
def test_the_app_key_in_each_form(out, form):
    assert out[f"key:{form}"] == 200
    assert out[f"keyRows:{form}"] == 1


def test_a_bad_key_frees_the_row(out):
    assert out["key:not-a-key"] == 502
    assert out["keyRows:not-a-key"] == 0


def test_the_webhook_and_the_year(out):
    assert out["hookBad"]["status"] == 401
    assert out["hookUnsigned"]["status"] == 401
    assert out["hookPing"]["status"] == 200
    assert out["hookOther"]["status"] == 200  # not the form's: no change
    assert out["afterOther"] == [None, None]
    assert out["hookClosed"]["status"] == 200
    assert out["afterClosed"] == [
        [9001, "2026-10-19T13:00:00.000Z"],
        [9002, None],
    ]
    assert out["afterReopened"] == [[9001, None], [9002, None]]
    assert out["underAYear"] == [9001, 9002]
    assert out["aYearOn"] == []


def test_the_bundle_is_the_sources():
    text = bundle_function.bundle()
    with open(bundle_function.RULES, encoding="utf-8") as fh:
        rules = fh.read()
    body = re.sub(r"^export ", "", rules, flags=re.MULTILINE).rstrip("\n")
    assert body in text
    assert "import " not in text.replace("import(", "")
    assert text.startswith("// @ts-nocheck\n")
    with open(SOURCE, encoding="utf-8") as fh:
        source = fh.read()
    assert source.count(bundle_function.IMPORT_RULES) == 1
    assert source.count(bundle_function.IMPORT_LLANO) == 1


def test_the_source_holds_no_secret_and_logs_no_body():
    with open(SOURCE, encoding="utf-8") as fh:
        source = fh.read()
    assert "PRIVATE KEY-----" not in source
    assert not re.search(r"(ghs|ghp|github_pat)_[A-Za-z0-9]", source)
    for line in re.findall(r"deps\.log\(([^;]*)\);", source):
        for word in ("body", "contact", "raw", "sub.", "token", "secret"):
            assert word not in line.split('"')[-1], line
    # the one origin, hostname and action
    assert 'SITE = "https://hickorysandsdistrictava.org"' in source
    assert 'HOSTNAMES = ["hickorysandsdistrictava.org"]' in source
    assert 'ACTION = "vineyard-submit"' in source
    assert 'BOT = "hsd-vineyard-form[bot]"' in source


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_dans_check_passes_on_a_ready_function(bundle, capsys):
    # src/vineyards/check_function.py, the four checks of SETUP.md, against
    # the function served by the stand-in (every secret set).
    if node_major() < 22:
        pytest.skip("node 22 or later is not installed")
    port = free_port()
    server = subprocess.Popen(
        [
            NODE,
            "--experimental-strip-types",
            STANDIN,
            "serve",
            str(port),
            bundle,
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert "stand-in on" in server.stdout.readline()
        url = f"http://127.0.0.1:{port}/vineyard-submit"
        assert check_function.main([url]) == 0
        printed = capsys.readouterr().out
        assert printed.count("PASS") == 5
        assert "All five checks passed." in printed
    finally:
        server.terminate()
        server.wait(timeout=10)


def test_a_lost_answer_never_makes_a_second_issue(out):
    # GitHub made the issue but its answer was lost: the row is kept and the
    # sender told to wait (409); after two minutes a retry finds the issue by
    # its marker (an HMAC of the submission's id) and ties the row to it.
    assert out["lost"]["status"] == 409
    assert out["afterLost"] == {"rows": [None], "issues": 1}
    assert out["lostSoon"]["status"] == 409
    assert out["lostLater"]["body"] == {"ok": True, "reference": 9001}
    assert out["afterLostLater"] == {"rows": [9001], "issues": 1}
    assert out["markerInBody"] is True


def test_success_only_once_the_row_is_tied_to_its_issue(out):
    assert out["linkFails"] == {
        "status": 503,
        "body": {"error": "store"},
        "acao": SITE,
    }
    assert out["afterLinkFails"] == {"rows": [None], "issues": 1}
    assert out["linkRetry"]["body"] == {"ok": True, "reference": 9001}
    assert out["afterLinkRetry"] == {"rows": [9001], "issues": 1}


def test_a_refused_label_keeps_the_issue_and_is_put_back(out):
    assert out["labelFails"]["body"] == {"ok": True, "reference": 9001}
    assert out["afterLabelFails"] == {"rows": [9001], "labels": 0}
    assert out["reconcileLabel"]["body"]["labelled"] == 1
    assert out["afterReconcileLabel"] == ["vineyard-submission"]


def test_turnstile_failing_is_not_a_refusal(out):
    for case in ("turnstile5xx", "turnstileHtml"):
        assert out[case]["status"] == 503, case
        assert out[case]["body"] == {"error": "turnstile-unreachable"}


def test_the_reconciliation_puts_the_table_right(out):
    assert out["recThrottled"]["body"]["ran"] is False  # once in ten minutes
    assert out["recClosed"]["body"]["closed"] == 1
    assert out["afterRecClosed"] == [
        [9001, "2026-10-19T12:30:00Z"],
        [9002, None],
    ]
    # 9001 reopened, 9002 deleted (counted as closed)
    assert out["recReopened"]["body"]["reopened"] == 1
    assert out["recReopened"]["body"]["closed"] == 1
    assert out["afterRecReopened"] == [[9001, True], [9002, False]]
    # a row whose send died is tied to its issue by the marker
    assert out["recLinked"]["body"]["linked"] == 1
    assert out["afterRecLinked"] == [9001]
    # failures are answered 500, for the daily Action to report
    assert out["recSweepFails"]["status"] == 500
    assert out["recSweepFails"]["body"]["failed"] == "sweep"
    assert out["recGithubFails"]["status"] == 500
    assert out["recGithubFails"]["body"]["failed"] == "reconcile"
    assert out["recNotReady"]["status"] == 503


def test_the_webhook_says_when_nothing_matched_or_the_table_failed(out):
    assert out["hookNoRow"] == {
        "status": 404,
        "body": {"error": "no row", "issue": 9999},
        "acao": None,
    }
    assert out["hookDbDown"]["status"] == 503


def test_silent_hold_is_ready_but_off(out):
    # Off by default: a private word is refused (422, no word named). With
    # PRIVATE_WORDS_SILENT=1 it is held: thanked with no reference, kept for
    # the petitioners, never posted, never said.
    assert out["privateWord"]["status"] == 422
    assert out["silent"]["body"] == {"ok": True, "reference": None}
    assert out["silentAgain"]["body"] == {"ok": True, "reference": None}
    assert out["afterSilent"] == {
        "rows": [[None, "private-word"]],
        "issues": 0,
    }
    assert out["silentKept"] == 1
    assert "quillfeather" not in json.dumps(out["silentLogs"]).lower()


def test_the_health_digest_follows_the_address_only(out):
    same, again, other = out["digests"]
    assert re.fullmatch(r"[0-9a-f]{8}", same)
    assert same == again
    assert same != other


def test_dans_check_fails_when_a_forged_address_counts(monkeypatch, capsys):
    # A gateway that let the sender's own header through: the digest follows
    # the forged address, and the check says so.
    def call(url, method="GET", origin=None, body=None, extra=None):
        if url.endswith("/health"):
            forged = (extra or {}).get("cf-connecting-ip", "")
            return 200, {}, {"ready": True, "address_digest": forged[-8:]}
        if method == "OPTIONS":
            ok = origin == SITE
            return (
                (204, {"Access-Control-Allow-Origin": SITE}, None)
                if ok
                else (403, {}, None)
            )
        return 403, {}, {"error": "turnstile"}

    monkeypatch.setattr(check_function, "call", call)
    assert check_function.main(["https://example.supabase.co/x"]) == 1
    printed = capsys.readouterr().out
    assert "FAIL  a forged address does not change the address counted" in (
        printed
    )


# Every error reply is one of these fixed words: never an error's message or
# stack (the log has the detail).
FIXED = {
    "error": {
        "origin",
        "JSON only",
        "too large",
        "not-ready",
        "unreadable",
        "turnstile",
        "turnstile-unreachable",
        "store",
        "in-progress",
        "limit-ip",
        "limit-day",
        "github",
        "signature",
        "no row",
        "sweep",
        "POST only",
        "GET only",
    },
    "failed": {"not-ready", "sweep", "reconcile"},
}


def test_no_reply_carries_an_error_s_detail(out):
    replies = [
        v
        for v in out.values()
        if isinstance(v, dict) and isinstance(v.get("status"), int)
    ]
    assert len(replies) > 40
    for reply in replies:
        body = reply["body"]
        if reply["status"] < 400 or not isinstance(body, dict):
            continue
        for key in ("error", "failed"):
            if key in body:
                assert body[key] in FIXED[key], body
        assert set(body) <= {
            "ok",
            "error",
            "failed",
            "missing",
            "issue",
            "errors",
        }, body
        text = json.dumps(body)
        for leak in ("Error", "stack", " at ", "database", "github "):
            assert leak not in text, body
