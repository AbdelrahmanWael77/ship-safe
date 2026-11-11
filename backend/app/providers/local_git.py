"""Read-only access to local Git repositories inside an explicit allowlist."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable

from ..errors import RefNotFound, RepositoryAccessDenied, RepositoryNotFound, ScanError
from .base import MAX_CHANGED_FILES, ChangeSet, FileDelta, RepositoryRef, valid_ref

GIT_TIMEOUT_SECONDS = 20
#: Upper bound on repositories returned by discovery.
MAX_DISCOVERED_REPOSITORIES = 200

# A scanned repository's .git/config is untrusted. These flags stop `git diff`
# from running commands it can name there (diff.<driver>.command / .textconv).
_SAFE_DIFF = ("diff", "--no-ext-diff", "--no-textconv", "--no-renames")


def run_git(repo: Path, *args: str, allow_error: bool = False) -> str:
    """Run one Git command against ``repo`` and return its stdout.

    Arguments are passed as an array (never through a shell). Output is decoded
    as UTF-8 with replacement so results do not depend on the OS locale.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True,
            encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise ScanError(f"Git is unavailable or timed out: {exc}") from exc
    if proc.returncode != 0:
        if allow_error:
            return ""
        raise ScanError(proc.stderr.strip()[:350] or "Git command failed")
    return proc.stdout


class LocalGitProvider:
    """Implements ``RepositoryProvider`` and ``ChangeProvider`` for local clones.

    Deny-by-default: a repository is readable only if its resolved path is one
    of ``allowed_roots`` or lies beneath one. Symlinks and ``..`` are resolved
    before the check.
    """

    name = "local-git"

    def __init__(self, allowed_roots: Iterable[Path]):
        self.allowed_roots = tuple(dict.fromkeys(Path(root).resolve() for root in allowed_roots))

    # -- RepositoryProvider -------------------------------------------------

    def list_repositories(self) -> list[RepositoryRef]:
        """Each allowed root that is a repository, else its immediate child
        repositories. Does not recurse further."""
        found: dict[Path, None] = {}
        for root in self.allowed_roots:
            try:
                if (root / ".git").exists():
                    found[root] = None
                elif root.is_dir():
                    for child in sorted(root.iterdir()):
                        if child.is_dir() and (child / ".git").exists():
                            found[child.resolve()] = None
            except OSError:
                continue
        repositories = []
        for path in list(found)[:MAX_DISCOVERED_REPOSITORIES]:
            branch = run_git(path, "symbolic-ref", "--quiet", "--short", "HEAD", allow_error=True).strip()
            repositories.append(self._ref(path, branch or None))
        return repositories

    def get_repository(self, repository_id: str) -> RepositoryRef:
        """``repository_id`` is a filesystem path. ``default_branch`` is left
        unset here to avoid an extra Git call on every scan."""
        try:
            path = Path(repository_id).expanduser().resolve()
        except (OSError, ValueError, RuntimeError) as exc:
            raise RepositoryNotFound("Repository path is not a valid local path") from exc
        if not any(path.is_relative_to(root) for root in self.allowed_roots):
            raise RepositoryAccessDenied(
                "Repository is outside SHIPSAFE_ALLOWED_ROOT. Scanning other paths requires explicit local configuration."
            )
        if not (path / ".git").exists():
            raise RepositoryNotFound("This path is not a local Git repository")
        return self._ref(path, None)

    def _ref(self, path: Path, default_branch: str | None) -> RepositoryRef:
        return RepositoryRef(
            provider=self.name, id=str(path), name=path.name,
            location=str(path), default_branch=default_branch,
        )

    # -- ChangeProvider -----------------------------------------------------

    def resolve_commit(self, repository: RepositoryRef, ref: str) -> str:
        if not valid_ref(ref):
            raise ScanError(f"Invalid Git reference: {ref!r}")
        sha = run_git(
            Path(repository.id), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", allow_error=True,
        ).strip()
        if not sha:
            raise RefNotFound(f"Git reference not found in this repository: {ref!r}")
        return sha

    def get_changes(
        self, repository: RepositoryRef, base_ref: str, head_ref: str,
        *, max_files: int = MAX_CHANGED_FILES,
    ) -> ChangeSet:
        repo = Path(repository.id)
        base_sha = self.resolve_commit(repository, base_ref)
        head_sha = self.resolve_commit(repository, head_ref)
        # -z gives NUL-separated, unquoted paths, so non-ASCII and unusual file
        # names round-trip exactly.
        tokens = run_git(repo, *_SAFE_DIFF, "--name-status", "-z", base_sha, head_sha, "--").split("\0")
        entries = [(tokens[i], tokens[i + 1]) for i in range(0, len(tokens) - 1, 2) if tokens[i + 1]]
        counts: dict[str, tuple[int, int]] = {}
        for record in run_git(repo, *_SAFE_DIFF, "--numstat", "-z", base_sha, head_sha, "--").split("\0"):
            chunks = record.split("\t", 2)
            if len(chunks) == 3:
                added, deleted, name = chunks
                counts[name] = (int(added) if added.isdigit() else 0, int(deleted) if deleted.isdigit() else 0)
        files = []
        for status, path in entries[:max_files]:
            patch = run_git(repo, *_SAFE_DIFF, "--unified=3", base_sha, head_sha, "--", path)
            additions, deletions = counts.get(path, (0, 0))
            files.append(FileDelta(path=path, status=status, additions=additions, deletions=deletions, patch=patch))
        return ChangeSet(
            repository=repository, base_ref=base_ref, head_ref=head_ref,
            base_sha=base_sha, head_sha=head_sha, files=tuple(files),
            truncated=len(entries) > max_files,
        )

    def list_files(self, repository: RepositoryRef, commit: str) -> list[str]:
        listing = run_git(Path(repository.id), "ls-tree", "-r", "--name-only", "-z", commit)
        return [name for name in listing.split("\0") if name]

    def read_file(self, repository: RepositoryRef, commit: str, path: str) -> str:
        return run_git(Path(repository.id), "show", f"{commit}:{path}", allow_error=True)
