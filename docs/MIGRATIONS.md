# Database migrations

## What exists

`backend/app/db.py` holds an ordered tuple of `Migration(version, description, statements)` and a `migrate(db_file)` function that the API runs at startup. The schema version is stored in SQLite's `PRAGMA user_version`.

- Version 1 is the v0.2 schema, written with `IF NOT EXISTS`. A database created by v0.2 reports version 0, is stamped to 1, and no row changes.
- Each migration runs in one `BEGIN IMMEDIATE` transaction together with its version bump. A failure rolls the whole step back and stops startup.
- If the file's version is higher than the code knows, startup stops with `SchemaVersionError` and the file is not modified.

Phase 1 made **no schema change**. Phase 2 added version 2 and Phase 4 task B added version 3 (both below). Phase 3 made no schema change. A database that has reached a version is refused by any build that only knows an older one (`SchemaVersionError`), so after running this code, do not point an older branch at the same `scans.db`; use a separate `SHIPSAFE_DB_PATH`.

Covered by `backend/tests/test_foundation.py` (the runner: adoption of a populated v0.2 database, idempotence, rollback of a failing migration, refusal of a newer database, row preservation across an additive column), `backend/tests/test_migration_2.py` (version 2 itself) and `backend/tests/test_proposals.py` (version 3 itself).

## Version 3 — test proposals and decisions (Phase 4 task B, implemented)

Two new tables; no existing table, column or row is touched.

- `test_proposals`: `id`, `scan_id` (→ `scans.id`), `created_at`, `target_path`, `content` (untrusted test source, stored as text and never executed by this code), `content_digest` (SHA-256), `origin` (`human` or `imported_ai_review`), `finding_ref`, `rationale`, `base_commit`, `head_commit` (full SHAs copied from the scan). A row is never updated.
- `test_proposal_decisions`: `id`, `proposal_id` (→ `test_proposals.id`), `decision` (`approved` or `rejected`), `decided_at`, `decided_by` (a self-declared name: there is no authentication), `note`. Append-only: a proposal's status is its latest decision, and earlier decisions stay.
- Stale state is not stored here. A proposal is stale when its scan is (`scans.stale_at`).

Tested: fresh database reaches version 3; version 2 rows survive byte for byte; idempotent; a failing version 3 rolls back to version 2; a build that only knows version 2 refuses a version 3 database; the statements only add.

## Rules

1. Append a migration with the next integer. Never edit, reorder, or remove one that has been merged.
2. Additive only: `CREATE TABLE`, `CREATE INDEX`, `ALTER TABLE … ADD COLUMN` where the column is NULL-able or has a constant default.
3. No `DROP`, `DELETE`, or table rebuild that could lose rows. Never delete a database file to get past an error.
4. Do not rewrite `scans.report_json`. Stored reports are evidence, and the Claude review `context_digest` is recomputed from them; changing a stored report invalidates its imported reviews.
5. Every migration ships with a test that starts from the previous version with rows present and asserts those rows are unchanged.
6. The migration reviewer named in `docs/DECISIONS.md` approves it before merge.

## Version 2 — scan binding (Phase 2 task 3, implemented)

```sql
ALTER TABLE scans ADD COLUMN provider TEXT NOT NULL DEFAULT 'local-git';
ALTER TABLE scans ADD COLUMN repository_id TEXT;    -- provider-scoped id, e.g. workspace/repo; local Git: resolved path
ALTER TABLE scans ADD COLUMN pull_request_id TEXT;  -- NULL for branch comparisons
ALTER TABLE scans ADD COLUMN base_commit TEXT;      -- full commit SHA
ALTER TABLE scans ADD COLUMN head_commit TEXT;      -- full commit SHA
ALTER TABLE scans ADD COLUMN stale_at TEXT;         -- ISO time the PR head was first seen to differ; NULL = not known stale
CREATE INDEX IF NOT EXISTS idx_scans_pull_request
    ON scans(provider, repository_id, pull_request_id, created_at);
```

- **Existing rows** become `provider = 'local-git'` with every other new column NULL. They are not backfilled: NULL commits mean "not commit-bound". `id`, `created_at`, `report_json` and all of `ai_reviews` are byte-identical after the migration.
- **New local scans** (`POST /api/scans`) are stored through `db.insert_scan` with `provider`, `repository_id` (the resolved path), and the full `base_commit` / `head_commit` from the `ChangeSet`. `pull_request_id` stays NULL. `insert_scan` refuses anything that is not a full lowercase SHA (40 or 64 hex characters).
- **The report JSON is unchanged.** It keeps its 12-character `base_sha` / `head_sha` and gains no key, so stored reports, exports, and the Claude review `context_digest` are unaffected. Since task 4 the API serves the columns as `binding` beside the report (see `docs/ARCHITECTURE.md`).
- **Stale marker.** `db.sync_stale(conn, provider=, repository_id=, pull_request_id=, current_head=, observed_at=)` sets `stale_at` on that pull request's scans whose `head_commit` differs from `current_head` (keeping the first observation time) and clears it if the head returns to the scanned commit. Scans without a `head_commit` are never touched. Since task 4 the Bitbucket pull request routes call it on list (scanned pull requests only), detail, and scan.
- **Not stored:** pull request title, URL, author (fetched live from the provider), and credentials (never in this database).
- An imported AI review is stale when its scan is: join `ai_reviews.scan_id` to `scans.stale_at`. `ai_reviews` has no column of its own.
