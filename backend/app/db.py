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
