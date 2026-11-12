"""SQLite access and forward-only schema migrations.

The schema version lives in SQLite's ``PRAGMA user_version``. A database
created by v0.2 has version 0 and already contains both tables; migration 1 is
written with ``IF NOT EXISTS`` so adopting it changes no data.

Rules for adding a migration (see docs/MIGRATIONS.md):

* Append a new ``Migration`` with the next integer. Never edit or reorder one
  that has shipped.
* Additive only: ``CREATE TABLE``, ``CREATE INDEX``, ``ALTER TABLE ... ADD
  COLUMN`` with a NULL-able column or a constant default. No ``DROP``, no
  ``DELETE``, no table rebuilds that discard rows.
* Each migration runs in a single transaction; a failure rolls it back and
  stops startup, leaving the previous version intact.
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


class SchemaVersionError(RuntimeError):
    """The database was written by a newer ShipSafe than this code understands."""


@dataclass(frozen=True)
class Migration:
    version: int
    description: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "baseline: scans and ai_reviews (identical to the v0.2 schema)", (
        """CREATE TABLE IF NOT EXISTS scans (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, report_json TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS ai_reviews (
            id TEXT PRIMARY KEY,
            scan_id TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            review_json TEXT NOT NULL,
            FOREIGN KEY(scan_id) REFERENCES scans(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_ai_reviews_scan ON ai_reviews(scan_id, imported_at)",
    )),
    Migration(2, "scans: provider, repository, pull request, full commit SHAs, stale marker", (
        # Rows written before this migration become provider 'local-git' with
        # every other new column NULL, meaning "not commit-bound".
        "ALTER TABLE scans ADD COLUMN provider TEXT NOT NULL DEFAULT 'local-git'",
        "ALTER TABLE scans ADD COLUMN repository_id TEXT",    # provider-scoped id, e.g. workspace/repo
        "ALTER TABLE scans ADD COLUMN pull_request_id TEXT",  # NULL for branch comparisons
        "ALTER TABLE scans ADD COLUMN base_commit TEXT",      # full commit SHA
        "ALTER TABLE scans ADD COLUMN head_commit TEXT",      # full commit SHA
        "ALTER TABLE scans ADD COLUMN stale_at TEXT",         # when the PR head was seen to differ; NULL = not known stale
        """CREATE INDEX IF NOT EXISTS idx_scans_pull_request
            ON scans(provider, repository_id, pull_request_id, created_at)""",
    )),
)
LATEST_VERSION = MIGRATIONS[-1].version


@contextmanager
def session(db_file: Path) -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, roll back on error, always close."""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def schema_version(db_file: Path) -> int:
    with session(db_file) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(db_file: Path, migrations: tuple[Migration, ...] = MIGRATIONS) -> int:
    """Apply pending migrations in order and return the resulting version.

    Fails closed with ``SchemaVersionError`` if the file is newer than the
    code, so an old build never writes into a schema it does not understand.
    """
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file, isolation_level=None)  # explicit transactions
    try:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        latest = migrations[-1].version
        if current > latest:
            raise SchemaVersionError(
                f"Database schema version {current} is newer than this ShipSafe build supports ({latest}). "
                "Upgrade ShipSafe; the database was left untouched."
            )
        for migration in migrations:
            if migration.version <= current:
                continue
            conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in migration.statements:
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {int(migration.version)}")
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            current = migration.version
        return current
    finally:
        conn.close()


_FULL_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def _full_sha(value: str | None, name: str) -> str | None:
    if value is not None and not _FULL_SHA.fullmatch(value):
        raise ValueError(f"{name} must be a full lowercase commit SHA, not an abbreviation or a ref name")
    return value


def insert_scan(
    conn: sqlite3.Connection, report: dict, *, provider: str = "local-git", repository_id: str | None = None,
    pull_request_id: str | None = None, base_commit: str | None = None, head_commit: str | None = None,
) -> None:
    """Store a report with the commit binding it was produced from.

    ``report`` is stored as given and never rewritten afterwards. The binding
    columns sit beside it: full SHAs only, so a scan can later be compared
    with a pull request's current head. Credentials are never stored here.
    """
    conn.execute(
        "INSERT INTO scans (id, created_at, report_json, provider, repository_id, pull_request_id, base_commit, head_commit)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (report["id"], report["created_at"], json.dumps(report), provider, repository_id, pull_request_id,
         _full_sha(base_commit, "base_commit"), _full_sha(head_commit, "head_commit")),
    )


def sync_stale(
    conn: sqlite3.Connection, *, provider: str, repository_id: str, pull_request_id: str,
    current_head: str, observed_at: str,
) -> int:
    """Record which scans of one pull request no longer match its head commit.

    A scan is stale when its ``head_commit`` differs from ``current_head``.
    ``stale_at`` keeps the first time that was observed; it is cleared if the
    pull request head returns to the scanned commit, because the evidence
    then describes the current code again. Scans with no ``head_commit`` are
    not commit-bound and are left alone. Returns how many scans were newly
    marked stale. ``report_json`` is never touched.
    """
    _full_sha(current_head, "current_head")
    scope = "provider = ? AND repository_id = ? AND pull_request_id = ? AND head_commit IS NOT NULL"
    key = (provider, repository_id, pull_request_id)
    conn.execute(
        f"UPDATE scans SET stale_at = NULL WHERE {scope} AND head_commit = ? AND stale_at IS NOT NULL",
        (*key, current_head),
    )
    return conn.execute(
        f"UPDATE scans SET stale_at = ? WHERE {scope} AND head_commit <> ? AND stale_at IS NULL",
        (observed_at, *key, current_head),
    ).rowcount
