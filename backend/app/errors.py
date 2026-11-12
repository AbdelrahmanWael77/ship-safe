"""Error types shared by the scanner, providers, and API layer.

The API maps these to HTTP statuses in ``main``. Local scans
(``create_scan``):

* ``RepositoryAccessDenied`` -> 403
* every other ``ScanError``  -> 400

Bitbucket routes use the finer table in ``main.bitbucket_failure``.

Messages are returned to the client, so they must never contain credentials
or other secrets.
"""
from __future__ import annotations


class ScanError(ValueError):
    """A scan could not be completed for a predictable, reportable reason."""


class ProviderError(ScanError):
    """A source-control provider could not satisfy a request."""


class RepositoryAccessDenied(ProviderError):
    """The repository exists outside what this installation is authorized to read."""


class RepositoryNotFound(ProviderError):
    """The repository identifier is malformed or does not name a repository."""


class RefNotFound(ProviderError):
    """A branch, tag, or commit could not be resolved to a commit."""


class PullRequestNotFound(ProviderError):
    """The pull request id does not exist in that repository."""


class ChangeTooLarge(ProviderError):
    """The provider could not produce the comparison because it is too large."""


class ProviderAuthError(ProviderError):
    """A remote provider rejected the configured credentials or their scope."""


class ProviderUnavailable(ProviderError):
    """A remote provider timed out, was unreachable, or kept rate-limiting us."""


class ConfigError(RuntimeError):
    """Startup configuration is unsafe or unusable. The application must not start."""
