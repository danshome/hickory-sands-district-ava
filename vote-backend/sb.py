#!/usr/bin/env python3
"""Supabase Management API helper for the custom.supabase connector.

Usage:
  sb.py req METHOD PATH [--json '<body>'] [--file-body <path>]
PATH is appended to https://api.supabase.com. Prints status and response body.
Other options are ignored.
The Management API access token is supplied by the connector credential
surrogate; it is never read from a file or printed here.
"""

import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request

BASE = "https://api.supabase.com"
HOSTS = ["api.supabase.com"]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses every redirect, so the token goes only to the API's own host."""

    def redirect_request(self, *args):
        """Raises instead of following a redirect.

        Args:
            *args: The original request, the response, its status code,
                message and headers, and the new URL (all unused).

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("redirect refused, verify the endpoint")


def do(method, path, body=None, raw=False):
    """Sends one request to the Management API.

    Args:
        method: The HTTP method, such as GET or POST.
        path: The path after https://api.supabase.com.
        body: The request body: a value json.dumps can encode when raw is
            False, bytes when raw is True, or None for no body.
        raw: True to send body (bytes) as it is, which urllib labels
            application/x-www-form-urlencoded; False to send it as JSON,
            labelled application/json.

    Returns:
        The HTTP status code and the response body (bytes).

    Raises:
        RuntimeError: On a redirect (see NoRedirect).
        urllib.error.URLError: On a network failure or a timeout.
    """
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        if raw:
            data = body
        else:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    add_surrogate_to_request(req, "custom.supabase", allowed_hosts=HOSTS)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=60) as resp:
            payload = resp.read()
            return resp.status, payload
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main(argv):
    """Runs the command line in argv.

    Args:
        argv: The command line, as sys.argv.

    Returns:
        The exit status: 0 for an HTTP status below 400, 1 for an error
        status, 2 for a usage error. Other errors (a malformed --json value,
        a missing --file-body file, a network failure) raise.
    """
    if len(argv) < 4 or argv[1] != "req":
        print(__doc__)
        return 2
    method, path = argv[2], argv[3]
    body = None
    rest = argv[4:]
    i = 0
    while i < len(rest):
        if rest[i] == "--json":
            body = json.loads(rest[i + 1])
            i += 2
        elif rest[i] == "--file-body":
            with open(rest[i + 1], "rb") as fh:
                body = fh.read()
            i += 2
        else:
            i += 1
    raw = isinstance(body, bytes)
    # A --file-body body is sent as its bytes, which urllib labels
    # application/x-www-form-urlencoded; use --json for a JSON body (a
    # database query, for example).
    status, payload = do(method, path, body=body, raw=raw)
    sys.stdout.write(f"HTTP {status}\n")
    try:
        sys.stdout.write(payload.decode("utf-8") + "\n")
    except UnicodeError:  # not UTF-8, or stdout cannot encode it
        sys.stdout.write(f"<binary {len(payload)} bytes>\n")
    return 0 if status < 400 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
