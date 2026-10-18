#!/usr/bin/env python3
"""Deploy a Supabase Edge Function through the Management API.

Usage: sb_deploy.py PROJECT_REF SLUG PATH_TO_INDEX_TS
Sends multipart/form-data with a metadata part and the entrypoint file.
The access token comes from the connector credential surrogate.
"""

import json
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request

BASE = "https://api.supabase.com"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses every redirect, so the token goes only to the API's own host."""

    def redirect_request(self, *args):
        """Raises instead of following a redirect.

        Args:
            *args: The redirect's request, response and headers (unused).

        Raises:
            RuntimeError: Always.
        """
        raise RuntimeError("redirect refused, verify the endpoint")


def main(argv):
    """Deploys the function named on the command line in argv.

    Args:
        argv: The command line, as sys.argv: the project's ref, the
            function's slug and the path to its index.ts.

    Returns:
        The exit status: 0 when deployed, 1 for an HTTP error, 2 for a usage
        error.
    """
    if len(argv) != 4:
        print(__doc__)
        return 2
    ref, slug, entry_path = argv[1], argv[2], argv[3]
    with open(entry_path, "rb") as fh:
        source = fh.read()
    boundary = "----sb" + uuid.uuid4().hex
    metadata = json.dumps(
        {
            "name": slug,
            "entrypoint_path": "index.ts",
            "verify_jwt": False,
            "import_map": False,
        }
    ).encode("utf-8")
    chunks = []
    chunks.append(("--" + boundary + "\r\n").encode())
    chunks.append(b'Content-Disposition: form-data; name="metadata"\r\n\r\n')
    chunks.append(metadata + b"\r\n")
    chunks.append(("--" + boundary + "\r\n").encode())
    chunks.append(
        b'Content-Disposition: form-data; name="file"; filename="index.ts"\r\n'
        b"Content-Type: application/typescript\r\n\r\n"
    )
    chunks.append(source + b"\r\n")
    chunks.append(("--" + boundary + "--\r\n").encode())
    body = b"".join(chunks)
    url = BASE + "/v1/projects/" + ref + "/functions/deploy?slug=" + slug
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=" + boundary)
    add_surrogate_to_request(
        req, "custom.supabase", allowed_hosts=["api.supabase.com"]
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=120) as resp:
            print("HTTP", resp.status)
            print(resp.read().decode("utf-8", "replace"))
            return 0
    except urllib.error.HTTPError as e:
        print("HTTP", e.code)
        print(e.read().decode("utf-8", "replace"))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
