"""A small client for GitHub's REST API, for the vineyard Actions.

Standard library only (urllib), so the Actions install nothing. A token is
sent only to the API's own address, never written to disk, logged or put in
an error: a failure says the method, the path, the status and GitHub's
short message. Tests point it at a local stand-in with GITHUB_API_URL, as
GitHub's own runners set that variable.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
TIMEOUT_S = 30


class GitHubError(Exception):
    """A request to GitHub's API failed."""

    def __init__(self, method, path, status, message):
        """Keeps what failed, never the token or a request's body.

        Args:
            method: The HTTP method.
            path: The API path.
            status: The HTTP status, or 0 when nothing came back.
            message: GitHub's short message, or the network error.
        """
        super().__init__(f"{method} {path}: {status} {message}"[:300])
        self.status = status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses every redirect, so the token goes only to the API's host."""

    def redirect_request(self, *args):
        """Follows nothing: urllib then raises the redirect as an HTTP error.

        Args:
            *args: The request, the response, its code, message and headers,
                and the new URL (all unused).
        """


def api_url():
    """The API's address: GITHUB_API_URL (as Actions set it), else GitHub's.

    Returns:
        The URL, without a final slash.

    Raises:
        ValueError: Neither GitHub's https API nor a local test server.
    """
    url = os.environ.get("GITHUB_API_URL", API).rstrip("/")
    parts = urllib.parse.urlsplit(url)
    local = parts.scheme == "http" and parts.hostname in {
        "127.0.0.1",
        "localhost",
    }
    if not (parts.scheme == "https" or local):
        raise ValueError(
            "GITHUB_API_URL must be https (or a local test server)"
        )
    return url


class GitHub:
    """One repository, through one token."""

    def __init__(self, token, repo):
        """Starts a client.

        Args:
            token: The token (never printed).
            repo: "owner/name".

        Raises:
            ValueError: No token, or the repository is not owner/name.
        """
        if not token:
            raise ValueError("no token")
        if repo.count("/") != 1 or not all(repo.split("/")):
            raise ValueError("the repository is owner/name")
        self._token = token
        self.repo = repo
        self.base = api_url()
        self._opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, path, body=None):
        """Sends one request and answers its JSON.

        Args:
            method: GET, POST, PATCH, PUT or DELETE.
            path: The API path; "{repo}" stands for /repos/owner/name.
            body: JSON-ready data to send, or None.

        Returns:
            The parsed JSON answer, or None when there is none.

        Raises:
            GitHubError: GitHub answered an error, or did not answer.
        """
        path = path.replace("{repo}", f"/repos/{self.repo}")
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(  # https, or a local test server
            self.base + path, data=data, method=method
        )
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "hsd-vineyard-actions")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with self._opener.open(req, timeout=TIMEOUT_S) as resp:
                text = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            try:
                message = json.loads(error.read() or b"{}").get("message", "")
            except ValueError:
                message = ""
            raise GitHubError(method, path, error.code, message) from None
        except OSError as error:
            raise GitHubError(method, path, 0, type(error).__name__) from None
        return json.loads(text) if text.strip() else None

    def paged(self, path):
        """Every item of a list, following up to ten pages of 100."""
        out = []
        sep = "&" if "?" in path else "?"
        for page in range(1, 11):
            items = self.request("GET", f"{path}{sep}per_page=100&page={page}")
            out += items or []
            if not items or len(items) < 100:
                break
        return out
