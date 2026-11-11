# Database migrations

## What exists

`backend/app/db.py` holds an ordered tuple of `Migration(version, description, statements)` and a `migrate(db_file)` function that the API runs at startup. The schema version is stored in SQLite's `PRAGMA user_version`.

- Version 1 is the v0.2 schema, written with `IF NOT EXISTS`. A database created by v0.2 reports version 0, is stamped to 1, and no row changes.
- Each migration runs in one `BEGIN IMMEDIATE` transaction together with its version bump. A failure rolls the whole step back and stops startup.
- If the file's version is higher than the code knows, startup stops with `SchemaVersionError` and the file is not modified.

Phase 1 made **no schema change**. The runner was added so Phase 2 has a tested path that does not involve deleting `scans.db`.

Covered by `backend/tests/test_foundation.py`: adoption of a populated v0.2 database, idempotence, rollback of a failing migration, refusal of a newer database, and row preservation across an additive column.

## Rules

1. Append a migration with the next integer. Never edit, reorder, or remove one that has been merged.
2. Additive only: `CREATE TABLE`, `CREATE INDEX`, `ALTER TABLE … ADD COLUMN` where the column is NULL-able or has a constant default.
3. No `DROP`, `DELETE`, or table rebuild that could lose rows. Never delete a database file to get past an error.
4. Do not rewrite `scans.report_json`. Stored reports are evidence, and the Claude review `context_digest` is recomputed from them; changing a stored report invalidates its imported reviews.
5. Every migration ships with a test that starts from the previous version with rows present and asserts those rows are unchanged.
6. The migration reviewer named in `docs/DECISIONS.md` approves it before merge.

## Proposed for Phase 2 (design only, not implemented)

Bitbucket scans need provider identity, full commit SHAs, and the pull request, without touching existing rows. Proposed migration 2:

```sql
ALTER TABLE scans ADD COLUMN provider TEXT NOT NULL DEFAULT 'local-git';
ALTER TABLE scans ADD COLUMN repository_id TEXT;    -- provider-scoped id, e.g. workspace/repo
ALTER TABLE scans ADD COLUMN pull_request_id TEXT;  -- NULL for branch comparisons
ALTER TABLE scans ADD COLUMN base_commit TEXT;      -- full 40-character SHA
ALTER TABLE scans ADD COLUMN head_commit TEXT;      -- full 40-character SHA
CREATE INDEX idx_scans_pull_request
    ON scans(provider, repository_id, pull_request_id, created_at);
```

- Existing rows become `provider = 'local-git'` with the other columns NULL. They stay readable and exportable exactly as before; NULL commits mean "not commit-bound".
- New scans fill the columns from `ChangeSet` (`base_sha` and `head_sha` are already full SHAs) and `PullRequestRef`.
- Stale detection compares a scan's `head_commit` with the pull request's current `source_sha`. It needs no change to stored reports.
- Whether the report JSON also gains these fields is an API-contract decision for the Phase 2 backend and frontend owners. If it does, add keys; do not change the keys `review_context()` reads without a new review schema version.
- Credentials are never stored in this database.

Open questions for the team: whether `repository_id` should be backfilled for local rows from `report_json.repository_path`, and whether a pull request's title and URL are stored or always fetched live.
