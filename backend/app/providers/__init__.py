"""Source-control provider contracts and the local Git implementation."""
from .base import (
    MAX_CHANGED_FILES, ChangeProvider, ChangeSet, FileDelta, PullRequestProvider,
    PullRequestRef, RepositoryProvider, RepositoryRef, valid_ref,
)
from .local_git import LocalGitProvider

__all__ = [
    "MAX_CHANGED_FILES", "ChangeProvider", "ChangeSet", "FileDelta", "LocalGitProvider",
    "PullRequestProvider", "PullRequestRef", "RepositoryProvider", "RepositoryRef", "valid_ref",
]
