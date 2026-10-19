"""The vineyard form's table, in a throwaway PostgreSQL (when one is here).

src/vineyards/functions/vineyard-submit/hsd_vineyard_contacts.sql runs
twice (Dan may run it again) in a new database with Supabase's roles; then:
the public and signed-in roles can neither read nor write the table nor
call hsd_vineyard_reserve(); the service role (the function) can; a
submission sent again gets its first row; the limits per address and per
day hold; a row needs an email or a phone; and the script makes only
hsd_vineyard_* objects. Skipped when PostgreSQL's initdb, pg_ctl and psql
are not on PATH (GitHub's runners keep them off it).
"""

import os
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL = os.path.join(
    ROOT,
    "src",
    "vineyards",
    "functions",
    "vineyard-submit",
    "hsd_vineyard_contacts.sql",
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


@pytest.fixture(scope="module")
def psql(tmp_path_factory):
    if not all(shutil.which(t) for t in TOOLS):
        pytest.skip("PostgreSQL is not installed here")
    base = tmp_path_factory.mktemp("pg")
    data = base / "data"
    # a short folder for the socket (a Unix socket's path is short), no TCP
    short = "/tmp" if os.path.isdir("/tmp") else None  # noqa: S108
    sock = tempfile.mkdtemp(prefix="pg", dir=short)
    subprocess.run(
        ["initdb", "-D", str(data), "-U", "postgres", "--auth=trust"],
        capture_output=True,
        check=True,
    )
    # the server's output goes to its log, so no pipe is held open
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

    def run(sql, role=None, check=True):
        text = f"set role {role};\n{sql}" if role else sql
        done = subprocess.run(
            [
                "psql",
                "-h",
                str(sock),
                "-U",
                "postgres",
                "-d",
                "postgres",
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
    with open(SQL, encoding="utf-8") as fh:
        script = fh.read()
    run(script)
    run(script)  # again: nothing changes, nothing fails
    yield run
    subprocess.run(
        ["pg_ctl", "-D", str(data), "-m", "immediate", "stop"],
        capture_output=True,
        check=False,
    )
    shutil.rmtree(sock, ignore_errors=True)


def reserve(psql, n, ip="a", email="'x@example.com'", per_ip=5, per_day=30):
    sid = f"00000000-0000-4000-8000-{n:012d}"
    out = psql(
        "select verdict from public.hsd_vineyard_reserve("  # noqa: S608 (test)
        f"'{sid}', '{ip * 32}', 'Jane', {email}, null, {per_ip}, {per_day});",
        role="service_role",
    )
    return out.stdout.strip()


def test_the_public_roles_are_kept_out(psql):
    for role in ("anon", "authenticated"):
        for sql in (
            "select * from public.hsd_vineyard_contacts;",
            (
                "insert into public.hsd_vineyard_contacts (submission_id,"
                " ip_hash, contact_name, email) values (gen_random_uuid(),"
                " repeat('a', 32), 'x', 'x@example.com');"
            ),
            (
                "select public.hsd_vineyard_reserve(gen_random_uuid(),"
                " repeat('a', 32), 'x', 'x@example.com', null, 5, 30);"
            ),
        ):
            done = psql(sql, role=role, check=False)
            assert done.returncode, (role, sql)
            assert "permission denied" in done.stderr, done.stderr


def test_rls_is_on_and_forced_with_no_policies(psql):
    out = psql(
        "select relrowsecurity, relforcerowsecurity from pg_class "
        "where relname = 'hsd_vineyard_contacts';"
    )
    assert out.stdout.strip() == "t|t"
    out = psql(
        "select count(*) from pg_policies "
        "where tablename = 'hsd_vineyard_contacts';"
    )
    assert out.stdout.strip() == "0"


def test_a_send_again_the_limits_and_a_way_to_reach(psql):
    psql("delete from public.hsd_vineyard_contacts;")
    assert reserve(psql, 1) == "new"
    assert reserve(psql, 1) == "again"
    for n in range(2, 6):
        assert reserve(psql, n) == "new"
    assert reserve(psql, 6) == "limit-ip"
    assert reserve(psql, 7, ip="b", per_day=5) == "limit-day"
    done = psql(
        "select public.hsd_vineyard_reserve('00000000-0000-4000-8000-"
        "000000000099', repeat('c', 32), 'Jane', null, null, 5, 30);",
        role="service_role",
        check=False,
    )
    assert done.returncode
    assert "hsd_vineyard_contacts_reach" in done.stderr
    # a send that died before its issue was known: again for two minutes,
    # then taken up anew, so it never waits for ever
    assert reserve(psql, 2) == "again"
    psql(
        "update public.hsd_vineyard_contacts set created_at = now() - "
        "interval '3 minutes' where submission_id = "
        "'00000000-0000-4000-8000-000000000002';"
    )
    assert reserve(psql, 2, per_ip=99) == "new"
    out = psql(
        "select count(*) from public.hsd_vineyard_contacts where "
        "submission_id = '00000000-0000-4000-8000-000000000002' and "
        "created_at > now() - interval '1 minute';"
    )
    assert out.stdout.strip() == "1"
    # the function's sweep: a year after the issue was closed
    psql(
        "update public.hsd_vineyard_contacts set issue_number = 1, "
        "closed_at = now() - interval '366 days' where submission_id = "
        "'00000000-0000-4000-8000-000000000001';",
        role="service_role",
    )
    psql(
        "delete from public.hsd_vineyard_contacts where closed_at < "
        "now() - interval '365 days';",
        role="service_role",
    )
    out = psql("select count(*) from public.hsd_vineyard_contacts;")
    assert out.stdout.strip() == "4"


def test_a_held_submission_stays_held(psql):
    # PRIVATE_WORDS_SILENT's rows: answered "held" however often it is sent,
    # never taken up again as a new send
    assert reserve(psql, 300, ip="h") == "new"
    psql(
        "update public.hsd_vineyard_contacts set held = 'private-word', "
        "created_at = now() - interval '1 hour' where submission_id = "
        "'00000000-0000-4000-8000-000000000300';"
    )
    assert reserve(psql, 300, ip="h") == "held"


def test_the_reconciliation_runs_at_most_once_in_a_while(psql):
    def tick():
        out = psql(
            "select public.hsd_vineyard_tick('reconcile', 600);",
            role="service_role",
        )
        return out.stdout.strip()

    assert tick() == "t"
    assert tick() == "f"
    psql(
        "update public.hsd_vineyard_ticks set at = now() - interval '11 "
        "minutes';"
    )
    assert tick() == "t"
    for role in ("anon", "authenticated"):
        done = psql(
            "select public.hsd_vineyard_tick('x', 1);", role=role, check=False
        )
        assert "permission denied" in done.stderr


def test_the_script_makes_only_its_own_objects():
    with open(SQL, encoding="utf-8") as fh:
        script = fh.read().lower()
    made = re.findall(
        r"create (?:or replace )?(?:table|function|index)(?: if not exists)?"
        r" (?:public\.)?(\w+)",
        script,
    )
    assert made
    assert all(name.startswith("hsd_vineyard_") for name in made), made
    assert "drop " not in script
    assert "vote" not in script.replace("vote-api", "")
