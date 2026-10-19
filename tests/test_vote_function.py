"""The logo vote's Edge Function, as Dan deploys it, against stand-ins.

src/vote/bundle_function.py makes the one file Dan pastes into the Supabase
dashboard; node runs that same file here (it reads TypeScript that only
needs its types erased), with tests/vote_standin.mjs standing in for
Supabase's tables, its Storage bucket and Cloudflare's Turnstile. The cases,
ported from the prototype's checks (guard, carry-over, history): CORS for the
site only, and no JSONP; the person check on (VOTE_TURNSTILE_SECRET set) and
off; signed voter ids (a made-up, forged, altered or empty id is "bad");
votes only for designs the page knows; ten voters per design per address per
day, and five new ids per address per day, with only an HMAC of the address
kept; the Shopify-era id's votes handed to a new id once; no name kept or
returned; images only while approved; nothing ever deleted (retire records,
unretire, the cull skipping a design restored since its last vote, trash,
remove and restore); missing secrets and the database down. Skipped without
node 22 or later.
"""

import json
import os
import re
import shutil
import subprocess

import pytest

from src.vote import bundle_function

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
STANDIN = os.path.join(ROOT, "tests", "vote_standin.mjs")
SITE = "https://hickorysandsdistrictava.org"
SIGNED = re.compile(r"v2-[0-9a-f]{24}-[0-9a-f]{32}")
HASH = re.compile(r"[0-9a-f]{64}")


def node_major():
    if not NODE:
        return 0
    out = subprocess.run(
        [NODE, "--version"], capture_output=True, text=True, check=True
    ).stdout
    return int(out.strip().lstrip("v").split(".")[0])


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    if node_major() < 22:
        pytest.skip("node 22 or later is not installed")
    path = tmp_path_factory.mktemp("function") / "index.mts"
    path.write_text(bundle_function.bundle(), encoding="utf-8")
    done = subprocess.run(
        [NODE, "--experimental-strip-types", STANDIN, "cases", str(path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return json.loads(done.stdout)


def test_the_bundle_carries_the_page_s_design_ids():
    text = bundle_function.bundle()
    with open(bundle_function.DESIGNS, encoding="utf-8") as fh:
        ids = [d["id"] for d in json.load(fh)]
    assert len(ids) == 13
    for i in ids:
        assert f'{{"id":"{i}"}}' in text
    assert "import designs" not in text


def test_only_the_site_may_call_and_there_is_no_jsonp(out):
    assert out["preflight"]["status"] == 204
    assert out["preflight"]["acao"] == SITE
    assert out["preflightOther"]["status"] == 403
    assert out["stateSite"]["acao"] == SITE
    assert out["stateOther"]["acao"] is None
    assert out["postOther"]["status"] == 403
    assert out["jsonp"]["type"] == "application/json"
    assert out["unknownAction"]["status"] == 400


def test_the_state_names_no_one_and_carries_the_rule(out):
    st = out["stateSite"]["body"]
    assert st["rule"] == {
        "minVotes": 25,
        "retireRatio": 0.35,
        "votersPerNetwork": 10,
    }
    assert out["stateSubs"] and all(
        set(s) == {"id", "title", "img"} for s in out["stateSubs"]
    )


def test_the_person_check_on(out):
    for token in ("", "fail", "other-host", "test-key"):
        assert out[f"checkOn:{token}"]["body"] == "check failed", token
    # Cloudflare failing is never a refusal
    assert out["checkOn:down"]["status"] == 503
    assert SIGNED.fullmatch(out["checkOnPass"]["body"]["voter"])
    assert out["checkOnRows"] == 1  # refused checks mint no id


def test_the_person_check_off(out):
    assert out["checkOff"]["status"] == 200
    assert SIGNED.fullmatch(out["checkOff"]["body"]["voter"])
    assert out["checkOffCalls"] == 0


@pytest.mark.parametrize("mode", ["on", "off"])
def test_signed_ids_and_the_limits(out, mode):
    r = out[f"mode:{mode}"]
    assert SIGNED.fullmatch(r["voter"])
    for name in ("made-up", "forged", "tampered", "empty"):
        assert r[f"vote:{name}"] == "bad", name
    assert r["unvoteForged"] == "bad"
    assert r["myVotesForged"] == "bad"
    assert r["vote"] == "ok"
    assert r["upAfter"] == 1
    assert r["myVotes"] == {"votes": {"c3": 1}}
    # only designs the page knows
    assert r["unknown"]["status"] == 400
    assert r["unknownSub"]["status"] == 400
    # ten voters per design per address per day
    assert r["network"] == ["ok"] * 10 + ["limit"]
    assert r["change"] == "ok"
    assert r["again"] == "ok"
    assert r["otherDesign"] == "ok"
    assert r["otherNetwork"] == "ok"
    assert r["nextDay"] == "ok"
    # five new ids per address per day
    assert r["registers"] == ["id"] * 5 + ["limit"]
    assert r["registerOther"] == "object"
    # only an HMAC of the address is kept
    for h in r["hashes"] + r["regHashes"]:
        assert HASH.fullmatch(h), h
    assert "198.51.100" not in json.dumps(r)
    assert "192.0.2" not in json.dumps(r)


def test_the_carry_over_from_the_shopify_page(out):
    assert out["carried"] == 3
    assert out["carriedMine"] == {"votes": {"c1": 1, "c3": -1, "c4": 1}}
    before_up, before_down, after_up, after_down = out["carriedCounts"]
    assert (before_up, before_down) == (after_up, after_down)
    assert out["oldIdVotes"] == "bad"
    assert out["secondCarry"] == 0
    assert out["badCarry"] == 0


def test_a_sent_design_waits_and_keeps_no_name(out):
    assert out["upload"] == "ok"
    assert out["notImage"] == "not an image"
    assert out["badData"] == "bad data"
    row = out["uploadRow"]
    assert row["name"] == ""
    assert row["status"] == "pending"
    assert row["ip"] is None
    assert HASH.fullmatch(row["ipHash"])
    # the title as text: ' and & kept, no markup
    assert row["title"] == "Grandpa's bMesa/b & Co"
    assert out["pendingBadKey"]["status"] == 403
    assert [set(p) for p in out["pending"]] == [{"title", "fileId", "when"}]
    assert out["imgPending"] == 404
    assert out["img"]["status"] == 200
    assert out["img"]["type"] == "image/jpeg"
    assert out["img"]["nosniff"] == "nosniff"
    assert out["img"]["cache"] == "public, max-age=300"
    assert out["imgBadId"] == 404
    assert out["uploadsPerAddress"] == ["ok"] * 5 + ["slow down"]


def test_nothing_is_ever_deleted(out):
    h = out["history"]
    assert h["cull"] == {"culled": ["c5"]}
    assert h["retired"] == ["c5"]
    assert h["afterCull"] == h["before"] == [3, 22]
    assert h["record"][0]["reason"] == "cull: 3 up, 22 down"
    assert h["record"][0]["retired_at"]
    assert h["record"][0]["restored_at"] is None
    assert h["retiredAfterUnretire"] == []
    assert h["recordAfterUnretire"][0]["restored_at"]
    # restored since its last vote: the cull leaves it; a vote after, not
    assert h["cullRestored"] == {"culled": []}
    assert h["cullAfterVote"] == {"culled": ["c5"]}
    assert h["records"] == 2
    assert h["retireByHand"] == "ok"
    assert h["retiredByHand"]["reason"] == "a bug"
    for step in h["removal"]:
        how = step["how"][len("admin_") :]
        assert step["inVote"] is False, how
        assert step["img"] == 404, how
        assert step["votesKept"] is True, how
        assert step["fileKept"] is True, how
        assert step["history"]["status"] == "removed", how
        assert step["history"]["how"] == how
        assert step["history"]["status_before"] == "approved", how
        assert step["backInVote"] is True, how
        assert step["imgBack"] == 200, how
    assert h["waitingRemoved"] is False
    assert h["waitingBack"] is True
    assert h["rowsKept"] == 2


def test_not_ready_and_the_database_down(out):
    assert out["notReady"]["status"] == 503
    assert out["notReady"]["body"] == "not ready"
    assert out["dbDown"]["status"] == 503
    assert out["dbDown"]["body"] == "unavailable"
    assert out["logs"] == ["vote: failed Error: database hsd_vote_tally 503"]
