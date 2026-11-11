"""Runtime settings, read from SHIPSAFE_* environment variables.

See docs/CONFIGURATION.md and .env.example. No setting holds a secret.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .errors import ConfigError

BACKEND_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    #: Where the synthetic LedgerLite repository is generated.
    demo_dir: Path
    #: SQLite database file holding scans and imported reviews.
    db_path: Path
    #: Directories under which local repositories may be scanned. Always
    #: contains ``demo_dir``; contains nothing else unless explicitly configured.
    allowed_roots: tuple[Path, ...]


def _path(value: str | os.PathLike | None, default: Path, name: str) -> Path:
    try:
        return Path(value if value not in (None, "") else default).expanduser().resolve()
    except (OSError, ValueError, RuntimeError) as exc:
        raise ConfigError(f"{name} is not a usable path") from exc


def load_settings(
    env: Mapping[str, str] | None = None, *,
    demo_root: Path | None = None, db_file: Path | None = None, allowed_root: Path | None = None,
) -> Settings:
    """Build settings from explicit arguments, then the environment, then defaults.

    Unset and empty variables are treated the same. Raises ``ConfigError``
    rather than starting with an allowlist that would cover a whole drive.
    """
    env = os.environ if env is None else env
    demo_dir = _path(demo_root or env.get("SHIPSAFE_DEMO_DIR"), BACKEND_DIR / "demo-repo", "SHIPSAFE_DEMO_DIR")
    db_path = _path(db_file or env.get("SHIPSAFE_DB_PATH"), BACKEND_DIR / ".shipsafe-data" / "scans.db", "SHIPSAFE_DB_PATH")
    roots = [demo_dir]
    extra = allowed_root or env.get("SHIPSAFE_ALLOWED_ROOT")
    if extra not in (None, ""):
        root = _path(extra, demo_dir, "SHIPSAFE_ALLOWED_ROOT")
        if root == Path(root.anchor):
            raise ConfigError(
                "SHIPSAFE_ALLOWED_ROOT must not be a filesystem or drive root; "
                "name the specific workspace directory you have approved for scanning."
            )
        if root not in roots:
            roots.append(root)
    return Settings(demo_dir=demo_dir, db_path=db_path, allowed_roots=tuple(roots))
