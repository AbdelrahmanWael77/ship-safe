"""Runtime settings, read from SHIPSAFE_* environment variables.

See docs/CONFIGURATION.md and .env.example. The only secret is the Bitbucket
token; it is held in a ``Secret`` so it cannot be printed or serialised by
accident.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .errors import ConfigError

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Secret:
    """A credential that never shows itself in ``repr``, ``str``, logs or JSON.

    Only ``reveal()`` returns the value. ``json.dumps``, ``pickle``, ``copy``
    and ``dataclasses.asdict`` fail on it rather than writing the value
    somewhere it could leak.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str):
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret(***)"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Secret) and other._value == self._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __reduce__(self):
        raise TypeError("Secret values are never copied or serialised")


@dataclass(frozen=True)
class BitbucketSettings:
    """Read-only Bitbucket Cloud access. Present only when fully configured."""
    workspace: str
    #: Approved repository slugs; nothing else in the workspace is readable.
    repositories: tuple[str, ...]
    token: Secret
    #: Atlassian account e-mail. Set = Basic auth with an API token; unset = Bearer access token.
    email: str | None = None


@dataclass(frozen=True)
class Settings:
    #: Where the synthetic LedgerLite repository is generated.
    demo_dir: Path
    #: SQLite database file holding scans and imported reviews.
    db_path: Path
    #: Directories under which local repositories may be scanned. Always
    #: contains ``demo_dir``; contains nothing else unless explicitly configured.
    allowed_roots: tuple[Path, ...]
    #: ``None`` unless the SHIPSAFE_BITBUCKET_* variables are set.
    bitbucket: BitbucketSettings | None = None


def _path(value: str | os.PathLike | None, default: Path, name: str) -> Path:
    try:
        return Path(value if value not in (None, "") else default).expanduser().resolve()
    except (OSError, ValueError, RuntimeError) as exc:
        raise ConfigError(f"{name} is not a usable path") from exc


def _scannable_root(value: str | os.PathLike | None, default: Path, name: str) -> Path:
    """A directory that will become an allowed scanning root.

    A filesystem or drive root is refused: every repository on the machine
    would otherwise become scannable through the unauthenticated API.
    """
    root = _path(value, default, name)
    if root == Path(root.anchor):
        raise ConfigError(
            f"{name} must not be a filesystem or drive root; "
            "name the specific directory you have approved for scanning."
        )
    return root


def _bitbucket(env: Mapping[str, str]) -> BitbucketSettings | None:
    """Bitbucket settings: all required variables, or none of them.

    A partial configuration is refused so a typo cannot silently start the
    API without the integration, or with a credential and no repository
    allowlist. Messages name variables only, never values.
    """
    prefix = "SHIPSAFE_BITBUCKET_"
    values = {name: (env.get(prefix + name) or "").strip() for name in ("WORKSPACE", "REPOSITORIES", "TOKEN", "EMAIL")}
    if not any(values.values()):
        return None
    missing = [prefix + name for name in ("WORKSPACE", "REPOSITORIES", "TOKEN") if not values[name]]
    if missing:
        raise ConfigError(
            f"Bitbucket is partly configured: {', '.join(missing)} must also be set. "
            "Set all of them, or remove every SHIPSAFE_BITBUCKET_* variable."
        )
    # Checked here, by name only, so a malformed value can never reach an
    # HTTP library error message or traceback.
    token = values["TOKEN"]
    if not token.isascii() or not token.isprintable() or " " in token:
        raise ConfigError("SHIPSAFE_BITBUCKET_TOKEN contains whitespace or characters that cannot be sent in a header")
    email = values["EMAIL"]
    if email and (not email.isascii() or not email.isprintable() or " " in email or ":" in email or "@" not in email):
        raise ConfigError("SHIPSAFE_BITBUCKET_EMAIL is not a usable e-mail address")
    repositories = tuple(dict.fromkeys(slug.strip() for slug in values["REPOSITORIES"].split(",") if slug.strip()))
    if not repositories:
        raise ConfigError("SHIPSAFE_BITBUCKET_REPOSITORIES must list at least one repository slug")
    return BitbucketSettings(
        workspace=values["WORKSPACE"], repositories=repositories,
        token=Secret(token), email=email or None,
    )


def load_settings(
    env: Mapping[str, str] | None = None, *,
    demo_root: Path | None = None, db_file: Path | None = None, allowed_root: Path | None = None,
) -> Settings:
    """Build settings from explicit arguments, then the environment, then defaults.

    Unset and empty variables are treated the same. Raises ``ConfigError``
    rather than starting with an allowlist that would cover a whole drive, or
    with a partial Bitbucket configuration.
    """
    env = os.environ if env is None else env
    # The demo directory is always an allowed root, so it gets the same
    # drive-root check as SHIPSAFE_ALLOWED_ROOT.
    demo_dir = _scannable_root(demo_root or env.get("SHIPSAFE_DEMO_DIR"), BACKEND_DIR / "demo-repo", "SHIPSAFE_DEMO_DIR")
    db_path = _path(db_file or env.get("SHIPSAFE_DB_PATH"), BACKEND_DIR / ".shipsafe-data" / "scans.db", "SHIPSAFE_DB_PATH")
    roots = [demo_dir]
    extra = allowed_root or env.get("SHIPSAFE_ALLOWED_ROOT")
    if extra not in (None, ""):
        root = _scannable_root(extra, demo_dir, "SHIPSAFE_ALLOWED_ROOT")
        if root not in roots:
            roots.append(root)
    return Settings(demo_dir=demo_dir, db_path=db_path, allowed_roots=tuple(roots), bitbucket=_bitbucket(env))
