"""Read-only Bitbucket **Cloud** connector (REST API 2.0, ``api.bitbucket.org``).

Implements ``RepositoryProvider``, ``PullRequestProvider`` and
``ChangeProvider``. Bitbucket Data Center has a different API and is not
covered; it needs its own provider.

Boundaries enforced here:

* **GET only.** No method writes to Bitbucket, and nothing is cloned.
* **Deny by default.** Only the configured workspace and the explicitly listed
  repository slugs are readable; an empty list means nothing is.
* **Credentials stay in the Authorization header.** They are never placed in a
  URL or an error message, redirects are not followed, and pagination links
  are followed only when they point back at the Bitbucket API.
* **Bounded work.** Timeouts, a retry cap, page caps, and byte caps on diffs
  and files.
* **Untrusted payloads.** Every field is type-checked; web links are built
  here from validated slugs instead of being copied from a response.

Endpoint behaviour follows Bitbucket's published OpenAPI description
(``https://api.bitbucket.org/swagger.json``, read 2026-11-12). Tested against
mocked HTTP only; no live call has been made.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Iterable
from urllib.parse import quote, urlsplit

import httpx

from ..errors import (
    ChangeTooLarge, ConfigError, ProviderAuthError, ProviderError, ProviderUnavailable, PullRequestNotFound,
    RefNotFound, RepositoryAccessDenied, RepositoryNotFound, ScanError,
)
from .base import MAX_CHANGED_FILES, ChangeSet, FileDelta, PullRequestRef, RepositoryRef, valid_ref

API_HOST = "api.bitbucket.org"
API_ROOT = f"https://{API_HOST}/2.0"
WEB_ROOT = "https://bitbucket.org"

TIMEOUT_SECONDS = 15.0
MAX_RETRIES = 2
MAX_RETRY_WAIT_SECONDS = 10.0
MAX_PAGES = 50
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_DIFF_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024
MAX_REPOSITORIES = 2000
MAX_PULL_REQUESTS = 200
MAX_TREE_ENTRIES = 5000
MAX_TREE_DEPTH = 20

_SLUG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,61}")
_FULL_SHA = re.compile(r"[0-9a-f]{40}")
_ANY_SHA = re.compile(r"[0-9a-f]{7,40}")
_RETRYABLE = {429, 502, 503, 504}
_PR_STATES = {"open": "OPEN", "merged": "MERGED", "declined": "DECLINED"}
_PR_STATE_NAMES = {"OPEN": "open", "MERGED": "merged", "DECLINED": "declined", "SUPERSEDED": "declined"}
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}
_UNEXPECTED = "Bitbucket returned an unexpected response"


class _NotFound(ProviderError):
    """HTTP 404; callers turn this into the specific error for what was asked."""


def _slug(value: str) -> bool:
    return bool(_SLUG.fullmatch(value)) and ".." not in value


def _text(value: Any, limit: int = 300) -> str | None:
    return value[:limit] if isinstance(value, str) and value else None


def _dig(payload: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(payload, dict):
            return None
        payload = payload.get(key)
    return payload


def _unquote(name: str) -> str:
    """Undo Git's C-style quoting of unusual file names in diff headers."""
    if len(name) < 2 or name[0] != '"' or name[-1] != '"':
        return name
    body, out, i = name[1:-1], bytearray(), 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            octal = re.match(r"[0-7]{1,3}", body[i + 1:])
            if octal:
                out.append(int(octal.group(), 8) & 0xFF)
                i += 1 + len(octal.group())
            else:
                out += _ESCAPES.get(body[i + 1], body[i + 1]).encode("utf-8")
                i += 2
        else:
            out += body[i].encode("utf-8")
            i += 1
    return out.decode("utf-8", "replace")


def _stanza_path(stanza: str) -> str | None:
    """The file one ``diff --git`` stanza is about, or None if unreadable."""
    old = new = None
    lines = stanza.split("\n")
    for line in lines[1:]:
        if line.startswith("@@"):
            break
        if line.startswith("--- "):
            old = line[4:]
        elif line.startswith("+++ "):
            new = line[4:]
    chosen = new if new not in (None, "/dev/null") else old
    if chosen not in (None, "/dev/null"):
        name = _unquote(chosen.rstrip("\t"))
        return name[2:] if name[:2] in ("a/", "b/") else name
    # No ---/+++ lines (binary, empty, or mode-only change): read the header.
    rest = lines[0][len("diff --git "):]
    if rest.startswith('"'):
        match = re.match(r'"(?:[^"\\]|\\.)*"', rest)
        name = _unquote(match.group()) if match else ""
        return name[2:] if name.startswith("a/") else None
    half, odd = divmod(len(rest) - 5, 2)  # "a/" + path + " b/" + path
    if half > 0 and not odd and rest.startswith("a/") and rest[2 + half:5 + half] == " b/":
        return rest[2:2 + half]
    return None


def split_patches(diff: str, *, cut: bool = False) -> dict[str, str]:
    """Split a raw multi-file diff into ``{path: patch}``.

    With ``cut`` (the download hit the byte cap) the last stanza is dropped,
    because it may be incomplete.
    """
    stanzas = [part for part in re.split(r"(?m)^(?=diff --git )", diff) if part.startswith("diff --git ")]
    if cut and stanzas:
        stanzas.pop()
    patches: dict[str, str] = {}
    for stanza in stanzas:
        path = _stanza_path(stanza)
        if path:
            patches.setdefault(path, stanza)
    return patches


class BitbucketCloudProvider:
    """One Bitbucket Cloud workspace, limited to an explicit repository list.

    ``token`` alone is sent as ``Authorization: Bearer`` (repository, project
    or workspace access token). With ``email`` it is sent as Basic auth
    (Atlassian account e-mail plus a scoped API token). Either way the
    credential needs read access to repositories and pull requests only.
    """

    name = "bitbucket-cloud"

    def __init__(
        self, workspace: str, repositories: Iterable[str], *, token: str, email: str | None = None,
        transport: httpx.BaseTransport | None = None, timeout: float = TIMEOUT_SECONDS,
        max_retries: int = MAX_RETRIES, sleep: Callable[[float], None] = time.sleep,
    ):
        if not _slug(workspace):
            raise ConfigError("Bitbucket workspace is not a valid workspace slug")
        slugs = tuple(dict.fromkeys(slug.strip().lower() for slug in repositories if slug.strip()))
        if not all(_slug(slug) for slug in slugs):
            raise ConfigError("Bitbucket repository list contains an invalid repository slug")
        if not token or not token.strip():
            raise ConfigError("Bitbucket credentials are not configured")
        self.workspace = workspace.lower()
        self.repositories = slugs
        self._timeout = timeout
        self._max_retries = max(0, max_retries)
        self._sleep = sleep
        self._client = httpx.Client(
            auth=httpx.BasicAuth(email, token) if email else None,
            headers={"Accept": "application/json", "User-Agent": "ShipSafe"}
            | ({} if email else {"Authorization": f"Bearer {token}"}),
            timeout=timeout, follow_redirects=False, transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    # -- HTTP -----------------------------------------------------------------

    def _get(self, url: str, params: dict[str, Any] | None = None, *, limit: int = MAX_JSON_BYTES,
             accept: str | None = None) -> tuple[bytes, bool, int]:
        """GET ``url`` and return ``(body, cut, status)`` for a 2xx or 3xx reply.

        ``cut`` is True when the body was longer than ``limit`` and was
        truncated. Retries timeouts, 429 and 502/503/504 a bounded number of
        times. Every other failure raises without the request ever being
        repeated elsewhere: redirects are returned, not followed.
        """
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc != API_HOST or not parts.path.startswith("/2.0/"):
            raise ProviderError("Bitbucket returned a link outside its API; refusing to follow it")
        headers = {"Accept": accept} if accept else None
        attempt = 0
        while True:
            wait = min(2.0 ** attempt, MAX_RETRY_WAIT_SECONDS)
            try:
                with self._client.stream("GET", url, params=params, headers=headers) as response:
                    status = response.status_code
                    if status in _RETRYABLE:
                        retry_after = response.headers.get("Retry-After", "")
                        if retry_after.isdigit():
                            wait = min(float(retry_after), MAX_RETRY_WAIT_SECONDS)
                        failure: str | None = (
                            "Bitbucket rate limit reached; try again later" if status == 429
                            else f"Bitbucket is temporarily unavailable (HTTP {status})"
                        )
                    else:
                        failure = None
                        body = bytearray()
                        if status < 400:
                            for chunk in response.iter_bytes():
                                body += chunk
                                if len(body) > limit:
                                    break
            except httpx.TimeoutException:
                failure = f"Bitbucket did not respond within {self._timeout:g} seconds"
            except httpx.HTTPError as exc:
                failure = f"Could not reach Bitbucket ({type(exc).__name__})"
            if failure is None:
                break
            if attempt >= self._max_retries:
                raise ProviderUnavailable(failure)
            attempt += 1
            self._sleep(wait)
        if status == 401:
            raise ProviderAuthError("Bitbucket rejected the configured credentials (HTTP 401)")
        if status == 403:
            raise ProviderAuthError("The configured Bitbucket credentials lack permission for this request (HTTP 403)")
        if status == 404:
            raise _NotFound("Not found on Bitbucket")
        if status == 555:
            raise ChangeTooLarge("Bitbucket timed out producing this response (HTTP 555); the change is too large")
        if status >= 400:
            raise ProviderError(f"Bitbucket returned HTTP {status}")
        return bytes(body[:limit]), len(body) > limit, status

    def _json(self, url: str, params: dict[str, Any] | None = None) -> dict:
        body, cut, status = self._get(url, params)
        try:
            payload = json.loads(body) if status == 200 and not cut else None
        except (ValueError, RecursionError):
            payload = None
        if not isinstance(payload, dict):
            raise ProviderError(_UNEXPECTED)
        return payload

    def _collect(self, url: str, params: dict[str, Any], limit: int) -> tuple[list[dict], int]:
        """Follow ``next`` links. Returns up to ``limit`` items and the total
        count (Bitbucket's ``size`` when given, else what was seen)."""
        items: list[dict] = []
        size = None
        more = False
        next_params: dict[str, Any] | None = params
        for _ in range(MAX_PAGES):
            page = self._json(url, next_params)
            values = page.get("values")
            if not isinstance(values, list) or not all(isinstance(value, dict) for value in values):
                raise ProviderError(_UNEXPECTED)
            if size is None and isinstance(page.get("size"), int):
                size = page["size"]
            items.extend(values)
            next_url = page.get("next")
            more = isinstance(next_url, str) and bool(next_url)
            if not more or len(items) > limit:
                break
            url, next_params = next_url, None  # the link already carries the query
        seen = len(items) + (1 if more and len(items) <= limit else 0)
        return items[:limit], max(size or 0, seen)

    # -- RepositoryProvider ---------------------------------------------------

    def list_repositories(self) -> list[RepositoryRef]:
        """The allowlisted repositories that exist in the workspace and that
        the credential can see, sorted by slug."""
        if not self.repositories:
            return []
        items, _ = self._collect(f"{API_ROOT}/repositories/{self.workspace}", {"pagelen": 100}, MAX_REPOSITORIES)
        found = {}
        for item in items:
            slug = item.get("slug")
            if isinstance(slug, str) and slug.lower() in self.repositories:
                found[slug.lower()] = self._repository(slug.lower(), item)
        return [found[slug] for slug in sorted(found)]

    def get_repository(self, repository_id: str) -> RepositoryRef:
        """``repository_id`` is ``"workspace/slug"``."""
        workspace, _, slug = repository_id.partition("/") if isinstance(repository_id, str) else ("", "", "")
        if not _slug(workspace) or not _slug(slug):
            raise RepositoryNotFound("Bitbucket repository must be given as 'workspace/repository'")
        workspace, slug = workspace.lower(), slug.lower()
        self._authorize(workspace, slug)
        try:
            payload = self._json(f"{API_ROOT}/repositories/{workspace}/{slug}")
        except _NotFound as exc:
            raise RepositoryNotFound("Repository not found on Bitbucket, or not visible to the configured credentials") from exc
        return self._repository(slug, payload)

    def _authorize(self, workspace: str, slug: str) -> None:
        if workspace != self.workspace or slug not in self.repositories:
            raise RepositoryAccessDenied(
                "Repository is not in the approved Bitbucket repository list. "
                "Scanning it requires explicit local configuration."
            )

    def _repository(self, slug: str, payload: dict) -> RepositoryRef:
        return RepositoryRef(
            provider=self.name, id=f"{self.workspace}/{slug}", name=_text(payload.get("name"), 120) or slug,
            location=f"{WEB_ROOT}/{self.workspace}/{slug}",
            default_branch=_text(_dig(payload, "mainbranch", "name"), 150),
        )

    def _api(self, repository: RepositoryRef) -> str:
        """API base URL for ``repository``, re-checking the allowlist: a
        ``RepositoryRef`` is plain data and may not have come from this provider."""
        workspace, _, slug = repository.id.partition("/")
        if repository.provider != self.name or not _slug(workspace) or not _slug(slug):
            raise RepositoryNotFound("Not a Bitbucket Cloud repository")
        self._authorize(workspace, slug)
        return f"{API_ROOT}/repositories/{workspace}/{slug}"

    # -- PullRequestProvider --------------------------------------------------

    def list_pull_requests(self, repository: RepositoryRef, state: str = "open") -> list[PullRequestRef]:
        """Up to ``MAX_PULL_REQUESTS`` pull requests in Bitbucket's order.

        ``source_sha``/``target_sha`` are None here: the list payload carries
        abbreviated hashes only. Use :meth:`get_pull_request` to bind a scan.
        """
        return self.list_pull_requests_page(repository, state)[0]

    def list_pull_requests_page(self, repository: RepositoryRef, state: str = "open") -> tuple[list[PullRequestRef], bool]:
        """:meth:`list_pull_requests` plus whether the list was cut.

        The flag is True only when pull requests were actually left out:
        Bitbucket has more than ``MAX_PULL_REQUESTS`` in this state, or the
        page limit stopped the walk early. A list of exactly
        ``MAX_PULL_REQUESTS`` with nothing after it is complete.
        """
        if state not in _PR_STATES:
            raise ScanError(f"Unknown pull request state: {state!r}")
        items, total = self._collect(
            f"{self._api(repository)}/pullrequests", {"state": _PR_STATES[state], "pagelen": 50}, MAX_PULL_REQUESTS,
        )
        return [self._pull_request(repository, item) for item in items], total > len(items)

    def get_pull_request(self, repository: RepositoryRef, pull_request_id: str) -> PullRequestRef:
        """One pull request with full 40-character SHAs for both sides.

        A SHA stays None when its branch is gone or its commit cannot be read
        through this repository (a pull request from a fork that is not on the
        allowlist).
        """
        if not isinstance(pull_request_id, str) or not re.fullmatch(r"[0-9]{1,10}", pull_request_id):
            raise ScanError("Invalid pull request id")
        try:
            payload = self._json(f"{self._api(repository)}/pullrequests/{pull_request_id}")
        except _NotFound as exc:
            raise PullRequestNotFound(f"Pull request {pull_request_id} not found in {repository.id}") from exc
        return self._pull_request(repository, payload, resolve=True)

    def _pull_request(self, repository: RepositoryRef, payload: dict, *, resolve: bool = False) -> PullRequestRef:
        number = payload.get("id")
        source = _text(_dig(payload, "source", "branch", "name"), 150)
        target = _text(_dig(payload, "destination", "branch", "name"), 150)
        if not isinstance(number, int) or isinstance(number, bool) or number < 0 or not source or not target:
            raise ProviderError(_UNEXPECTED)
        return PullRequestRef(
            provider=self.name, repository_id=repository.id, id=str(number),
            title=_text(payload.get("title")) or f"Pull request {number}",
            state=_PR_STATE_NAMES.get(payload.get("state"), "declined"),
            source_ref=source, target_ref=target,
            source_sha=self._sha(repository, _dig(payload, "source", "commit", "hash"), resolve),
            target_sha=self._sha(repository, _dig(payload, "destination", "commit", "hash"), resolve),
            author=_text(_dig(payload, "author", "display_name"), 120),
            url=f"{WEB_ROOT}/{repository.id}/pull-requests/{number}",
            updated_at=_text(payload.get("updated_on"), 40),
        )

    def _sha(self, repository: RepositoryRef, value: Any, resolve: bool) -> str | None:
        if not isinstance(value, str) or not _ANY_SHA.fullmatch(value):
            return None
        if _FULL_SHA.fullmatch(value):
            return value
        if not resolve:
            return None
        try:
            return self._commit(repository, value)
        except RefNotFound:
            return None

    # -- ChangeProvider -------------------------------------------------------

    def resolve_commit(self, repository: RepositoryRef, ref: str) -> str:
        """Branch, then tag, then commit hash. Branches and tags are looked up
        with a filter so names containing ``/`` never enter the URL path."""
        if not valid_ref(ref):
            raise ScanError(f"Invalid Git reference: {ref!r}")
        api = self._api(repository)
        if not _FULL_SHA.fullmatch(ref):
            for kind in ("branches", "tags"):
                page = self._json(f"{api}/refs/{kind}", {"q": f'name = "{ref}"', "pagelen": 2})
                values = page.get("values")
                if not isinstance(values, list):
                    raise ProviderError(_UNEXPECTED)
                for value in values:
                    sha = _dig(value, "target", "hash")
                    if _dig(value, "name") == ref and isinstance(sha, str) and _FULL_SHA.fullmatch(sha):
                        return sha
        if _ANY_SHA.fullmatch(ref):
            return self._commit(repository, ref)
        raise RefNotFound(f"Git reference not found in this repository: {ref!r}")

    def _commit(self, repository: RepositoryRef, sha: str) -> str:
        try:
            full = self._json(f"{self._api(repository)}/commit/{sha}").get("hash")
        except _NotFound as exc:
            raise RefNotFound(f"Git reference not found in this repository: {sha!r}") from exc
        if not isinstance(full, str) or not _FULL_SHA.fullmatch(full):
            raise ProviderError(_UNEXPECTED)
        return full

    def merge_base(self, repository: RepositoryRef, first_sha: str, second_sha: str) -> str:
        """Full SHA of the best common ancestor of two commits.

        A pull request is compared from here to its head, which is what
        Bitbucket's own pull request view shows. Not part of the provider
        protocols; only pull request scans need it.
        """
        if not all(isinstance(sha, str) and _FULL_SHA.fullmatch(sha) for sha in (first_sha, second_sha)):
            raise ScanError("Full commit SHAs are required to find a merge base")
        try:
            found = self._json(f"{self._api(repository)}/merge-base/{first_sha}..{second_sha}").get("hash")
        except _NotFound as exc:
            raise RefNotFound("These commits have no common ancestor readable through this repository") from exc
        if not isinstance(found, str) or not _FULL_SHA.fullmatch(found):
            raise ProviderError(_UNEXPECTED)
        return found

    def get_changes(
        self, repository: RepositoryRef, base_ref: str, head_ref: str,
        *, max_files: int = MAX_CHANGED_FILES,
    ) -> ChangeSet:
        """Two-dot comparison of the two commits, as the protocol requires.

        Bitbucket's spec is ``<new>..<old>`` (the reverse of ``git diff``) and
        defaults to a three-dot diff, so ``topic=false`` is sent explicitly.
        Rename detection is off: a rename is a ``D`` plus an ``A``, like the
        local provider. A file is dropped and counted in ``omitted`` when it
        is beyond ``max_files`` or when the diff download hit
        ``MAX_DIFF_BYTES`` before reaching it.
        """
        api = self._api(repository)
        base_sha = self.resolve_commit(repository, base_ref)
        head_sha = self.resolve_commit(repository, head_ref)
        spec = f"{head_sha}..{base_sha}"
        options = {"topic": "false", "renames": "false"}
        try:
            stats, total = self._collect(f"{api}/diffstat/{spec}", {**options, "pagelen": 100}, max_files)
            entries = [entry for stat in stats for entry in self._entries(stat)]
            body, cut, status = (b"", False, 200)
            if entries:
                body, cut, status = self._get(
                    f"{api}/diff/{spec}", {**options, "binary": "false", "context": 3},
                    limit=MAX_DIFF_BYTES, accept="text/plain",
                )
        except _NotFound as exc:
            raise ProviderError("Bitbucket could not compare these commits") from exc
        if status != 200:
            raise ProviderError(_UNEXPECTED)
        patches = split_patches(body.decode("utf-8", "replace"), cut=cut)
        files = [
            FileDelta(path=path, status=letter, additions=added, deletions=removed, patch=patches.get(path, ""))
            for letter, path, added, removed in entries
            if not cut or path in patches
        ]
        omitted = max(0, total - len(stats)) + (len(entries) - len(files))
        return ChangeSet(
            repository=repository, base_ref=base_ref, head_ref=head_ref, base_sha=base_sha, head_sha=head_sha,
            files=tuple(files), truncated=omitted > 0, omitted=omitted,
        )

    @staticmethod
    def _entries(stat: dict) -> list[tuple[str, str, int, int]]:
        def count(key: str) -> int:
            value = stat.get(key)
            return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0

        old, new = _dig(stat, "old", "path"), _dig(stat, "new", "path")
        old = old if isinstance(old, str) and old else None
        new = new if isinstance(new, str) and new else None
        status = stat.get("status")
        added, removed = count("lines_added"), count("lines_removed")
        if status == "renamed" and old and new and old != new:
            return [("D", old, 0, removed), ("A", new, added, 0)]
        if status == "added" and new:
            return [("A", new, added, removed)]
        if status == "removed" and old:
            return [("D", old, added, removed)]
        if new:
            return [("M", new, added, removed)]
        if old:
            return [("D", old, added, removed)]
        raise ProviderError(_UNEXPECTED)

    def list_files(self, repository: RepositoryRef, commit: str) -> list[str]:
        """File paths at ``commit``, capped at ``MAX_TREE_ENTRIES`` tree entries."""
        if not isinstance(commit, str) or not _FULL_SHA.fullmatch(commit):
            raise ScanError("A full commit SHA is required to list files")
        try:
            items, _ = self._collect(
                f"{self._api(repository)}/src/{commit}/", {"max_depth": MAX_TREE_DEPTH, "pagelen": 100}, MAX_TREE_ENTRIES,
            )
        except _NotFound as exc:
            raise RefNotFound(f"Git reference not found in this repository: {commit!r}") from exc
        return [
            item["path"] for item in items
            if item.get("type") == "commit_file" and isinstance(item.get("path"), str) and item["path"]
        ]

    def read_file(self, repository: RepositoryRef, commit: str, path: str) -> str:
        """Text of ``path`` at ``commit``; ``""`` when it is absent, larger
        than ``MAX_FILE_BYTES``, stored in LFS, or not a plain relative path.
        Authentication and availability failures are raised, not hidden."""
        api = self._api(repository)
        if not isinstance(commit, str) or not _FULL_SHA.fullmatch(commit) or not isinstance(path, str):
            return ""
        if "\x00" in path or any(part in ("", ".", "..") for part in path.split("/")):
            return ""
        try:
            body, cut, status = self._get(f"{api}/src/{commit}/{quote(path, safe='/')}", limit=MAX_FILE_BYTES, accept="*/*")
        except _NotFound:
            return ""
        return "" if cut or status != 200 else body.decode("utf-8", "replace")
