"""Checks the deployed vineyard function from outside, as the site sees it.

Five checks, each with its own PASS, FAIL or SKIP line; no secret is needed
or sent, and nothing is stored or posted (src/vineyards/SETUP.md, step 6):

1. GET .../health: the function answers, and every secret it needs is set
   ("ready"); it also says which address headers reach it (never their
   values) and whether the person check (Turnstile) is on;
2. OPTIONS from https://hickorysandsdistrictava.org: 204, and the site
   allowed (CORS);
3. OPTIONS from another site: 403;
4. only when the function reports the person check on: POST from the site
   without a Turnstile token: 403 "turnstile" (the check runs before
   anything else is done). With it off (TURNSTILE_SECRET unset; Dan,
   2026-10-19: added only if bots show up) this check is SKIP and nothing
   is sent. A function that does not say (one older than the switch) is
   taken as on, as it was;
5. two health checks that claim other addresses (forged cf-connecting-ip,
   x-real-ip and x-forwarded-for): the digest of the address the limits use
   must not change with them, or one connection could send without limit.
   A test of the limits by sending needs the person check, so this asks the
   function which address it would count instead.

    .venv/bin/python -E -s -B src/vineyards/check_function.py [URL]

The URL defaults to the function in the project yayebhncbagmebwgmezd.
The first line says which mode the function reported. Exit status 0 when
none fails (a SKIP is not a failure). Standard library only.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

URL = "https://yayebhncbagmebwgmezd.supabase.co/functions/v1/vineyard-submit"
SITE = "https://hickorysandsdistrictava.org"


def call(url, method="GET", origin=None, body=None, extra=None):
    """One request: (status, headers, parsed JSON or None)."""
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    for name, value in (extra or {}).items():
        req.add_header(name, value)
    if origin:
        req.add_header("Origin", origin)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if method == "OPTIONS":
        req.add_header("Access-Control-Request-Method", "POST")
        req.add_header("Access-Control-Request-Headers", "content-type")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, headers, text = resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as error:
        status, headers, text = error.code, error.headers, error.read()
    except OSError as error:
        return 0, {}, {"error": f"no answer ({type(error).__name__})"}
    try:
        parsed = json.loads(text) if text.strip() else None
    except ValueError:
        parsed = None
    return status, headers, parsed


def person_check_on(body):
    """Whether the health answer says the person check is on.

    Args:
        body: The health check's parsed answer (or None).

    Returns:
        True or False as the function says; True when it does not say (a
        function older than the switch always checked).
    """
    return (body or {}).get("person_check") is not False


def checks(url):
    """Runs the five checks.

    Args:
        url: The function's URL.

    Returns:
        A pair: whether the person check is on (as the function reported
        it), and a list of (result, what, detail), where result is True
        (pass), False (fail) or None (skipped).
    """
    out = []
    status, _, body = call(url.rstrip("/") + "/health")
    check_on = person_check_on(body)
    if status == 401:
        out.append(
            (
                False,
                "the function answers",
                "401: turn off JWT verification for vineyard-submit",
            )
        )
    else:
        ready = status == 200 and bool(body) and body.get("ready") is True
        missing = (body or {}).get("missing") or []
        detail = (
            f"{status}; address headers {(body or {}).get('address_headers')}, "
            f"forwarded entries {(body or {}).get('forwarded_entries')}"
            if ready
            else f"{status}; secrets missing: {', '.join(missing) or '?'}"
        )
        out.append(
            (ready, "the function answers and every secret is set", detail)
        )
    status, headers, _ = call(url, "OPTIONS", SITE)
    allowed = headers.get("Access-Control-Allow-Origin") if headers else None
    out.append(
        (
            status == 204 and allowed == SITE,
            "the site may send to it",
            f"{status}, allowed origin {allowed}",
        )
    )
    status, headers, _ = call(url, "OPTIONS", "https://example.com")
    out.append(
        (status == 403, "another site may not", f"{status} (403 expected)")
    )
    if check_on:
        status, _, body = call(
            url, "POST", SITE, {"form": "hsd-vineyard", "version": 1}
        )
        out.append(
            (
                status == 403 and (body or {}).get("error") == "turnstile",
                "a send without the person check is refused",
                f"{status} {body}",
            )
        )
    else:
        out.append(
            (
                None,
                "a send without the person check is refused",
                "person check off (TURNSTILE_SECRET not set): nothing sent",
            )
        )
    digests = []
    for forged in ("203.0.113.7", "198.51.100.9"):
        _, _, body = call(
            url.rstrip("/") + "/health",
            extra={
                "cf-connecting-ip": forged,
                "x-real-ip": forged,
                "x-forwarded-for": forged,
            },
        )
        digests.append((body or {}).get("address_digest"))
    out.append(
        (
            None not in digests and digests[0] == digests[1],
            "a forged address does not change the address counted",
            "the same"
            if None not in digests and digests[0] == digests[1]
            else f"{digests}: tell Claude, the limits must use another header",
        )
    )
    return check_on, out


def main(argv=None):
    """Prints one line per check.

    Args:
        argv: The command line's arguments (sys.argv[1:] when None).

    Returns:
        0 when no check failed (a skipped one is not a failure), else 1.
    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("url", nargs="?", default=URL, help="the function")
    args = parser.parse_args(argv)
    local = args.url.startswith(("http://127.0.0.1:", "http://localhost:"))
    if not (args.url.startswith("https://") or local):
        parser.error("the URL must be https (or a local stand-in)")
    check_on, results = checks(args.url)
    print(
        "Person check (Turnstile): "
        + ("on" if check_on else "off (TURNSTILE_SECRET not set)")
    )
    words = {True: "PASS", False: "FAIL", None: "SKIP"}
    for result, what, detail in results:
        print(f"{words[result]}  {what}: {detail}")
    good = all(result is not False for result, _, _ in results)
    skipped = sum(result is None for result, _, _ in results)
    if not good:
        print("Not yet: see FAIL above.")
    elif skipped:
        print(f"All checks passed ({skipped} skipped: person check off).")
    else:
        print("All five checks passed.")
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
