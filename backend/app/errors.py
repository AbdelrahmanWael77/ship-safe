"""Error types shared by the scanner, providers, and API layer.

The API maps these to HTTP statuses in one place (``main.create_scan``):

* ``RepositoryAccessDenied`` -> 403
* every other ``ScanError``  -> 400

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


class ConfigError(RuntimeError):
    """Startup configuration is unsafe or unusable. The application must not start."""
