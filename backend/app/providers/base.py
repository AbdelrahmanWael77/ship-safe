"""Provider-neutral contracts for source-control access.

These are the seams Phase 2 plugs a Bitbucket connector into. Phase 1 ships
exactly one implementation, :class:`app.providers.local_git.LocalGitProvider`,
which covers repository discovery and change retrieval. Nothing in ShipSafe
implements :class:`PullRequestProvider` yet.

Design rules for every implementation:

* **Read-only.** No method may write to a repository, a pull request, or a
  remote service.
* **No execution.** Never run code, hooks, filters, or tests from a repository.
* **Untrusted content.** Paths, patches, titles, and file contents are data
  supplied by whoever can push to the repository. Never interpret them.
* **Predictable failures.** Raise the :mod:`app.errors` types; the API layer
  turns them into 4xx responses. Error text must not include credentials.
* **Bounded work.** Honour ``max_files`` and apply timeouts to I/O.

The dataclasses are frozen and JSON-friendly (``dataclasses.asdict`` works),
so a frontend type can mirror each one field-for-field.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

#: Upper bound on changed files returned for one comparison.
MAX_CHANGED_FILES = 300


def valid_ref(ref: str) -> bool:
    """Return True when ``ref`` is safe to hand to a provider as a revision.

    Accepts branch names, tags, and commit SHAs. Rejects anything that could be
    read as an option (leading ``-``), a range (``..``), or shell/revision
    syntax (spaces, ``~``, ``^``, ``:``, ``@{``).
    """
    return bool(
        ref and len(ref) <= 150 and re.fullmatch(r"[a-zA-Z0-9_./-]+", ref)
        and not ref.startswith("-") and ".." not in ref and "//" not in ref
        and not ref.endswith("/") and not ref.endswith(".lock")
    )


@dataclass(frozen=True)
class RepositoryRef:
    """One repository a provider can read."""

    #: Provider name, e.g. ``"local-git"``. Phase 2 adds ``"bitbucket-cloud"``.
    provider: str
    #: Provider-scoped stable identifier. Local Git: the resolved absolute path.
    #: A hosted provider would use its own slug, e.g. ``"workspace/repo"``.
    id: str
    #: Short display name.
    name: str
    #: Where the repository lives, for display. Local Git: the absolute path.
    #: Must never embed credentials (no ``https://user:token@host`` URLs).
    location: str
    #: Default branch if cheaply known, else None.
    default_branch: str | None = None


@dataclass(frozen=True)
class PullRequestRef:
    """A pull request as listed by a provider. Not produced by any Phase 1 code."""

    provider: str
    repository_id: str
    #: Provider-scoped identifier, kept as a string (Bitbucket uses integers).
    id: str
    title: str
    #: ``"open"``, ``"merged"``, or ``"declined"``.
    state: str
    #: Branch being merged (the scan ``head``).
    source_ref: str
    #: Branch being merged into (the scan ``base``).
    target_ref: str
    #: Full commit SHAs at the time the PR was listed, when the provider gives
    #: them. Scan these, not the branch names, to bind a scan to an exact
    #: commit and to detect a stale scan after the PR head moves.
    source_sha: str | None = None
    target_sha: str | None = None
    author: str | None = None
    url: str | None = None
    #: ISO 8601 timestamp of the last update, if known.
    updated_at: str | None = None


@dataclass(frozen=True)
class FileDelta:
    """One changed file within a :class:`ChangeSet`."""

    #: Repository-relative POSIX path, unquoted, exactly as stored in the tree.
    path: str
    #: Git-style single letter: ``A`` added, ``M`` modified, ``D`` deleted,
    #: ``T`` type changed. Renames are reported as a ``D`` plus an ``A``.
    status: str
    additions: int
    deletions: int
    #: Complete unified diff (3 context lines) for this file; ``""`` if none is
    #: available. The report truncates this for display; the provider does not.
    patch: str


@dataclass(frozen=True)
class ChangeSet:
    """The difference between two commits of one repository."""

    repository: RepositoryRef
    #: Refs as requested by the caller.
    base_ref: str
    head_ref: str
    #: Full 40-character commit SHAs the refs resolved to.
    base_sha: str
    head_sha: str
    files: tuple[FileDelta, ...]
    #: True when more than ``max_files`` files changed and the rest were dropped.
    truncated: bool = False


@runtime_checkable
class RepositoryProvider(Protocol):
    """Repository discovery."""

    name: str

    def list_repositories(self) -> list[RepositoryRef]:
        """Return the repositories this installation is authorized to read."""
        ...

    def get_repository(self, repository_id: str) -> RepositoryRef:
        """Resolve one repository.

        Raises ``RepositoryAccessDenied`` if it is outside the authorized
        scope and ``RepositoryNotFound`` if the identifier is malformed or
        does not name a repository. Authorization is checked first.
        """
        ...


@runtime_checkable
class PullRequestProvider(Protocol):
    """Pull-request discovery. No implementation exists in Phase 1."""

    def list_pull_requests(self, repository: RepositoryRef, state: str = "open") -> list[PullRequestRef]:
        ...

    def get_pull_request(self, repository: RepositoryRef, pull_request_id: str) -> PullRequestRef:
        ...


@runtime_checkable
class ChangeProvider(Protocol):
    """Commit resolution plus change, tree, and file retrieval."""

    def resolve_commit(self, repository: RepositoryRef, ref: str) -> str:
        """Return the full commit SHA for ``ref``.

        Raises ``ScanError`` if ``ref`` fails :func:`valid_ref` and
        ``RefNotFound`` if it does not resolve to a commit.
        """
        ...

    def get_changes(
        self, repository: RepositoryRef, base_ref: str, head_ref: str,
        *, max_files: int = MAX_CHANGED_FILES,
    ) -> ChangeSet:
        """Return files changed from ``base_ref`` to ``head_ref`` (a two-dot,
        tree-to-tree comparison), in the provider's stable order."""
        ...

    def list_files(self, repository: RepositoryRef, commit: str) -> list[str]:
        """Return every file path in the tree at ``commit``."""
        ...

    def read_file(self, repository: RepositoryRef, commit: str, path: str) -> str:
        """Return the text of ``path`` at ``commit``, decoded as UTF-8 with
        replacement. Returns ``""`` when the file is absent or unreadable."""
        ...
