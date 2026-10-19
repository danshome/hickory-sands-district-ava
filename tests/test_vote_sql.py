"""The logo vote's migration, in a throwaway PostgreSQL (when one is here).

src/vote/functions/vote-api/hsd_vote_migration.sql runs twice (Dan may run
it again) on vote-api's tables as they are before it (votes, a design sent
in with its sender's name and address, a retired design keyed by its id),
and once on an empty database. Then: every vote, design and retire record
is kept, the names are blank, and a retire record can be restored and made
again; the public and signed-in roles can call nothing and read nothing;
the limit of voters per design per address per day, and of new voter ids
per address per day; a Shopify-era voter's votes handed to a new id once;
the cull, which skips a design restored since its last vote; and the
script makes only hsd_* objects and drops no table, column or row. Skipped
when PostgreSQL's initdb, pg_ctl and psql are not on PATH.
"""

import os
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL = os.path.join(
    ROOT, "src", "vote", "functions", "vote-api", "hsd_vote_migration.sql"
)
TOOLS = ("initdb", "pg_ctl", "psql")
ROLES = """
create role anon nologin; create role authenticated nologin;
create role service_role nologin bypassrls;
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables
  to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions
  to anon, authenticated, service_role;
"""
# vote-api's tables as they were before the migration (src/vote/README.md)
BEFORE = """
create table public.hsd_votes (
  design_id text not null, voter_token text not null,
  dir integer not null default 1, primary key (design_id, voter_token));
create table public.hsd_submissions (
  id uuid primary key default gen_random_uuid(), name text, title text,
  storage_path text not null, content_type text not null,
  status text not null default 'pending'
    check (status in ('pending', 'approved')),
  ip text, created_at timestamptz not null default now());
create table public.hsd_retired (design_id text primary key);
alter table public.hsd_votes enable row level security;
alter table public.hsd_submissions enable row level security;
alter table public.hsd_retired enable row level security;
insert into public.hsd_votes (design_id, voter_token, dir) values
  ('c1', 'vshopify00001', 1), ('c3', 'vshopify00001', -1),
  ('c1', 'vshopify00002', 1), ('c7', 'vshopify00002', -1);
insert into public.hsd_submissions
  (id, name, title, storage_path, content_type, status, ip) values
  ('11111111-1111-4111-8111-111111111111', 'A Grower', 'The Mesa',
   '11111111-1111-4111-8111-111111111111.jpg', 'image/jpeg', 'approved',
   '198.51.100.7');
insert into public.hsd_retired (design_id) values ('c7');
"""
H = "a" * 64  # an address's HMAC


def start(base):
    data = base / "data"
    # a short folder for the socket (a Unix socket's path is short), no TCP
    short = "/tmp" if os.path.isdir("/tmp") else None  # noqa: S108
    sock = tempfile.mkdtemp(prefix="pg", dir=short)
    subprocess.run(
        ["initdb", "-D", str(data), "-U", "postgres", "--auth=trust"],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        [
            "pg_ctl",
            "-D",
            str(data),
            "-l",
            str(base / "log"),
            "-o",
            f"-k {sock} -c listen_addresses=''",
            "-w",
            "start",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=60,
    )
    return data, sock


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    if not all(shutil.which(t) for t in TOOLS):
        pytest.skip("PostgreSQL is not installed here")
    data, sock = start(tmp_path_factory.mktemp("pg"))

    def run(sql, db="postgres", role=None, check=True):
        text = f"set role {role};\n{sql}" if role else sql
        done = subprocess.run(
            [
                "psql",
                "-h",
                str(sock),
                "-U",
                "postgres",
                "-d",
                db,
                "-v",
                "ON_ERROR_STOP=1",
                "-qAt",
                "-c",
                text,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if check and done.returncode:
            raise AssertionError(done.stderr)
        return done

    run(ROLES)
    run("create database fresh;")
    yield run
    subprocess.run(
        ["pg_ctl", "-D", str(data), "-m", "immediate", "stop"],
        capture_output=True,
        check=False,
    )
    shutil.rmtree(sock, ignore_errors=True)


@pytest.fixture(scope="module")
def script():
    with open(SQL, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def psql(server, script):
    server(BEFORE)
    server(script)
    server(script)  # again: nothing changes, nothing fails
    return server


def one(psql, sql, role=None):
    return psql(sql, role=role).stdout.strip()


def test_an_empty_project_gets_the_tables(server, script):
    server(script, db="fresh")
    server(script, db="fresh")
    tables = server(
        "select string_agg(tablename, ',' order by tablename) from "
        "pg_tables where schemaname = 'public';",
        db="fresh",
    ).stdout.strip()
    assert tables == (
        "hsd_retired,hsd_submissions,hsd_vote_exchanged,hsd_vote_networks,"
        "hsd_vote_registrations,hsd_votes"
    )


def test_nothing_is_lost_and_the_names_are_blank(psql):
    assert one(psql, "select count(*) from public.hsd_votes;") == "4"
    row = one(
        psql,
        "select name || '|' || title || '|' || status || '|' || ip "
        "from public.hsd_submissions;",
    )
    assert row == "|The Mesa|approved|198.51.100.7"
    rec = one(
        psql,
        "select design_id || '|' || reason || '|' || "
        "(retired_at is not null) || '|' || (restored_at is null) "
        "from public.hsd_retired;",
    )
    assert rec == "c7|cull (before records)|true|true"


def test_a_retire_record_is_restored_and_made_again(psql):
    psql(
        "update public.hsd_retired set restored_at = now() "
        "where design_id = 'c7';"
    )
    psql(
        "insert into public.hsd_retired (design_id, reason) "
        "values ('c7', 'by hand');"
    )
    assert (
        one(
            psql,
            "select count(*) || '|' || count(restored_at) "
            "from public.hsd_retired where design_id = 'c7';",
        )
        == "2|1"
    )
    psql(
        "update public.hsd_submissions set status = 'removed' "
        "where title = 'The Mesa';"
    )
    psql(
        "update public.hsd_submissions set status = 'approved' "
        "where title = 'The Mesa';"
    )


@pytest.mark.parametrize(
    "sql",
    [
        "select * from public.hsd_votes;",
        "select * from public.hsd_submissions;",
        "select * from public.hsd_retired;",
        "select * from public.hsd_vote_networks;",
        "select public.hsd_vote_tally();",
        "select public.hsd_vote_cast('c1', 'x', 1, repeat('a', 64), 10);",
        "select public.hsd_vote_register(repeat('a', 64), 5, 'x', '');",
        "select public.hsd_vote_cull(25, 0.35);",
    ],
)
def test_the_public_roles_are_kept_out(psql, sql):
    for role in ("anon", "authenticated"):
        done = psql(sql, role=role, check=False)
        assert done.returncode, (role, sql)
        assert "permission denied" in done.stderr, done.stderr


def test_rls_is_on_and_forced_with_no_policies(psql):
    out = one(
        psql,
        "select count(*) from pg_class where relname like 'hsd\\_%' "
        "and relkind = 'r' and relrowsecurity and relforcerowsecurity;",
    )
    assert out == "6"
    assert one(psql, "select count(*) from pg_policies;") == "0"


def cast(psql, design, voter, ip=H, limit=10, d=1):
    return one(
        psql,
        f"select public.hsd_vote_cast('{design}', '{voter}', {d}, "
        f"'{ip}', {limit});",
        role="service_role",
    )


def test_the_limit_of_voters_per_design_per_address(psql):
    answers = [cast(psql, "c6", f"v2-net-{n}") for n in range(11)]
    assert answers == ["ok"] * 10 + ["limit"]
    # changing a vote, or voting again after taking it back, is not counted
    assert cast(psql, "c6", "v2-net-0", d=-1) == "ok"
    psql(
        "delete from public.hsd_votes where design_id = 'c6' "
        "and voter_token = 'v2-net-1';"
    )
    assert cast(psql, "c6", "v2-net-1") == "ok"
    # another design, another address
    assert cast(psql, "c8", "v2-net-10") == "ok"
    assert cast(psql, "c6", "v2-net-10", ip="b" * 64) == "ok"
    # a day on, the address may again
    psql(
        "update public.hsd_vote_networks set at = now() - interval '25 hours';"
    )
    assert cast(psql, "c6", "v2-net-11") == "ok"
    assert one(psql, "select count(*) from public.hsd_vote_networks;") == "1"
    tally = one(
        psql,
        "select up || '|' || down from public.hsd_vote_tally() "
        "where design_id = 'c6';",
    )
    assert tally == "11|1"


def register(psql, voter, carry="", ip="c" * 64, limit=5):
    return one(
        psql,
        f"select public.hsd_vote_register('{ip}', {limit}, '{voter}', "
        f"'{carry}');",
        role="service_role",
    )


def test_new_ids_per_address_and_the_carry_over(psql):
    first = register(psql, "v2-new-1", carry="vshopify00001")
    assert first == '{"carried": 2, "verdict": "ok"}'
    votes = one(
        psql,
        "select string_agg(design_id || dir, ',' order by design_id) "
        "from public.hsd_votes where voter_token = 'v2-new-1';",
    )
    assert votes == "c11,c3-1"
    assert (
        one(
            psql,
            "select count(*) from public.hsd_votes "
            "where voter_token = 'vshopify00001';",
        )
        == "0"
    )
    # once only, and nothing made up
    assert register(psql, "v2-new-2", carry="vshopify00001") == (
        '{"carried": 0, "verdict": "ok"}'
    )
    assert register(psql, "v2-new-3", carry="vnotavoter00") == (
        '{"carried": 0, "verdict": "ok"}'
    )
    assert register(psql, "v2-new-4") == '{"carried": 0, "verdict": "ok"}'
    assert register(psql, "v2-new-5") == '{"carried": 0, "verdict": "ok"}'
    assert register(psql, "v2-new-6") == '{"carried": 0, "verdict": "limit"}'
    assert register(psql, "v2-new-6", ip="d" * 64) == (
        '{"carried": 0, "verdict": "ok"}'
    )


def test_the_cull_skips_a_design_restored_since_its_last_vote(psql):
    for n in range(25):
        cast(psql, "c5", f"v2-cull-{n}", ip=f"{n:064d}", d=1 if n < 3 else -1)
    culled = one(
        psql, "select public.hsd_vote_cull(25, 0.35);", role="service_role"
    )
    assert culled == "c5"
    rec = one(
        psql,
        "select reason from public.hsd_retired where design_id = 'c5';",
    )
    assert rec == "cull: 3 up, 22 down"
    # retired now: not again
    assert one(psql, "select public.hsd_vote_cull(25, 0.35);") == ""
    # restored: skipped until it gets a vote after
    psql(
        "update public.hsd_retired set restored_at = now() + interval '1 "
        "second' where design_id = 'c5';"
    )
    assert one(psql, "select public.hsd_vote_cull(25, 0.35);") == ""
    psql(
        "update public.hsd_votes set updated_at = now() + interval '1 "
        "minute' where design_id = 'c5' and voter_token = 'v2-cull-24';"
    )
    assert one(psql, "select public.hsd_vote_cull(25, 0.35);") == "c5"
    assert (
        one(
            psql,
            "select count(*) from public.hsd_retired where design_id = 'c5';",
        )
        == "2"
    )


def test_the_script_makes_only_its_own_objects_and_drops_no_data(script):
    text = script.lower()
    made = re.findall(
        r"create (?:or replace )?(?:table|function|index)(?: if not exists)?"
        r" (?:public\.)?(\w+)",
        text,
    )
    assert made
    assert all(name.startswith("hsd_") for name in made), made
    assert not any(name.startswith("hsd_vineyard") for name in made)
    for gone in ("drop table", "drop column", "truncate", "drop function"):
        assert gone not in text, gone
    deletes = re.findall(r"delete from (?:public\.)?(\w+)", text)
    assert set(deletes) == {"hsd_vote_networks", "hsd_vote_registrations"}
