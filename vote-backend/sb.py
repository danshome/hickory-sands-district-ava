#!/usr/bin/env python3
"""Supabase Management API helper for the custom.supabase connector.

Usage:
  sb.py req METHOD PATH [--json '<body>'] [--file-body <path>] [--out <path>]
PATH is appended to https://api.supabase.com. Prints status and response body.
The Management API access token is supplied by the connector credential
surrogate; it is never read from a file or printed here.
"""
import json
import sys
import urllib.request
import urllib.error

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

BASE = "https://api.supabase.com"
HOSTS = ["api.supabase.com"]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def do(method, path, body=None, raw=False):
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
    # --file-body content is sent as-is with JSON content type set by caller need;
    # for database query etc. prefer --json.
    status, payload = do(method, path, body=body, raw=raw)
    sys.stdout.write("HTTP %d\n" % status)
    try:
        sys.stdout.write(payload.decode("utf-8") + "\n")
    except Exception:
        sys.stdout.write("<binary %d bytes>\n" % len(payload))
    return 0 if status < 400 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
