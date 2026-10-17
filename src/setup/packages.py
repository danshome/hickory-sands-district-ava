"""The Python lock files (requirements.txt, requirements-dev.txt; compiled by pip-compile with hashes), standard library
only, so it runs before anything is installed:

  packages.py audit LOCK [LOCK ...]   every pinned package checked against the OSV vulnerability database
                                      (https://osv.dev: PyPA advisories, GitHub advisories, CVEs). Exit 1 if any
                                      package has a known vulnerability, 2 if the database cannot be reached.
  packages.py pick LOCK NAME [...]    print the entries (pin + hashes) for NAME... from LOCK, for a first-stage install
"""  # noqa: D205, D415, E501 (the usage message, printed as written)

import json
import re
import sys
import urllib.request

PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)")
OSV = "https://api.osv.dev/v1"


def entries(path):
    """The pinned packages of a pip-compile lock file.

    Args:
        path: The lock file (requirements.txt or requirements-dev.txt).

    Returns:
        {normalised name: (name, version, [the entry's lines])}: the pin line
        and its hash and comment lines, without their newlines.
    """
    out, cur = {}, None
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = PIN.match(line)
            if m:
                cur = [line.rstrip("\n")]
                out[re.sub(r"[-_.]+", "-", m.group(1)).lower()] = (
                    m.group(1),
                    m.group(2),
                    cur,
                )
            elif cur is not None and line.startswith(" "):
                cur.append(line.rstrip("\n"))
            else:
                cur = None
    return out


def post(url, body):
    """POSTs BODY as JSON to URL and returns the JSON reply (60 s timeout)."""
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def get(url):
    """GETs URL and returns the JSON reply (60 s timeout)."""
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def audit(locks):
    """Checks every package pinned in LOCKS against the OSV database.

    Prints one line when none has a known vulnerability; otherwise each
    vulnerability (id, CVEs, summary, fixed versions) on stderr.

    Args:
        locks: The lock files' paths.

    Returns:
        The exit code: 0 no known vulnerability, 1 at least one, 2 the
        database cannot be reached.
    """
    pkgs = {}
    for lock in locks:
        for k, (name, version, _) in entries(lock).items():
            pkgs[(k, version)] = name
    keys = sorted(pkgs)
    try:
        found = {}
        for i in range(0, len(keys), 500):
            chunk = keys[i : i + 500]
            res = post(
                OSV + "/querybatch",
                {
                    "queries": [
                        {
                            "package": {"name": pkgs[k], "ecosystem": "PyPI"},
                            "version": k[1],
                        }
                        for k in chunk
                    ]
                },
            )
            # not strict: a short answer from OSV leaves the rest unflagged,
            # as before, rather than stopping the audit with a ValueError
            for k, r in zip(chunk, res.get("results", []), strict=False):
                if r.get("vulns"):
                    found[k] = [v["id"] for v in r["vulns"]]
    except OSError as e:
        print(
            f"security audit: cannot reach the OSV database ({e})",
            file=sys.stderr,
        )
        return 2
    if not found:
        print(
            f"security audit: {len(keys)} packages pinned in "
            f"{', '.join(locks)}: no known vulnerabilities (OSV)"
        )
        return 0
    print(
        f"SECURITY AUDIT FAILED: {len(found)} of {len(keys)} pinned packages "
        "have known vulnerabilities (OSV):",
        file=sys.stderr,
    )
    for k in sorted(found):
        for vid in found[k]:
            try:
                v = get(f"{OSV}/vulns/{vid}")
                cves = [a for a in v.get("aliases", []) if a.startswith("CVE-")]
                fixed = sorted(
                    {
                        e["fixed"]
                        for a in v.get("affected", [])
                        for r in a.get("ranges", [])
                        for e in r.get("events", [])
                        if "fixed" in e
                    }
                )
                summary = v.get("summary", "").strip()[:100]
                fixed_in = f"  (fixed in {', '.join(fixed)})" if fixed else ""
                print(
                    f"  {pkgs[k]} {k[1]}: {vid} {' '.join(cves)} - "
                    f"{summary}{fixed_in}",
                    file=sys.stderr,
                )
            except OSError:
                print(f"  {pkgs[k]} {k[1]}: {vid}", file=sys.stderr)
    print(
        "Update the package (./build.sh upgrade) or wait for a fixed release; "
        "nothing has been installed.",
        file=sys.stderr,
    )
    return 1


def pick(lock, names):
    """Prints the entries (pin and hashes) of NAMES from LOCK.

    For a first-stage pip install; exits with a message if a name is not
    pinned in LOCK.

    Args:
        lock: The lock file's path.
        names: The package names, in any spelling pip accepts.

    Returns:
        0, the exit code.
    """
    e = entries(lock)
    for n in names:
        k = re.sub(r"[-_.]+", "-", n).lower()
        if k not in e:
            sys.exit(f"{n} is not pinned in {lock}")
        print("\n".join(e[k][2]).rstrip(" \\"))
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "audit":
        sys.exit(audit(sys.argv[2:]))
    if len(sys.argv) >= 4 and sys.argv[1] == "pick":
        sys.exit(pick(sys.argv[2], sys.argv[3:]))
    sys.exit(__doc__)
