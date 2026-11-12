# Next Agent — Copy/Paste Continuation Prompt

You are joining **ShipSafe**, an existing project, mid-implementation. The v0.2 baseline and Phase 1 are finished. **Do not restart the project, re-plan its phases, or redo completed work.**

Read `AGENTS.md`, `CLAUDE.md`, and the checkpoint at the top of `docs/IMPLEMENTATION_STATUS.md`. Read only `prompts/PHASE-02-BITBUCKET.md` and the code your task touches. Verify the checkpoint below against `git status`, `git log`, and the tests before trusting it.

**Current phase:** 2 — Bitbucket repositories and pull requests.

**Next atomic task (P2 task 4):** API over the Bitbucket provider. List approved repositories, list a repository's open pull requests, scan a pull request bound to its exact base and head SHAs, and stale detection. Backend only; mocked HTTP only.

**Relevant files:** `backend/app/main.py` (routes; the provider is at `app.state.bitbucket`, `None` when not configured), `backend/app/db.py` (`insert_scan`, `sync_stale`), `backend/app/scanner.py` (`scan_change_set`, `import_dependencies`), `backend/app/providers/bitbucket.py` and `base.py` (read, do not rewrite), `backend/tests/test_bitbucket_provider.py` (mocked transport to reuse), `docs/ARCHITECTURE.md` (API table).

**Already implemented:**
- Task 1 (`08b3b1b`): read-only `BitbucketCloudProvider`, 38 mocked-HTTP tests.
- Task 2 (`ebc9068`): `SHIPSAFE_BITBUCKET_*` settings, `config.Secret`, provider built at startup into `app.state.bitbucket`. 32 tests.
- Task 3: schema version 2 — `scans` has `provider`, `repository_id`, `pull_request_id`, `base_commit`, `head_commit`, `stale_at`. `db.insert_scan` stores a report with its binding (full SHAs only). `db.sync_stale` sets or clears `stale_at` for one pull request given its current head. Local scans already fill provider, repository and SHAs. 17 tests. Nothing calls `sync_stale` yet and no response exposes the new columns.

**Tests last run (2026-11-12, Linux cloud container, Python 3.13.18):**
- `cd backend && python -m pytest -q tests/test_migration_2.py tests/test_foundation.py` → 32 passed
- `cd backend && python -m pytest -q` → 188 passed, 1 warning
- Not re-run on Windows since `08b3b1b`. On Windows use `.venv\Scripts\python`; the full suite took about four minutes there.

**Branch / commit / uncommitted edits:** GitHub has no `main`; the default branch is `feat/p1-foundation` (`98c9d92`, already contains task 1 through pull request #1). Stacked on `08b3b1b`: `feat/p2-bitbucket-settings` (`ebc9068`, task 2) → `feat/p2-migration-2` (task 3, branch head). Both are committed but were **not pushed** (no GitHub credential in the agent session); check `git ls-remote origin`. No uncommitted edits. Start task 4 on a new `feat/p2-<ticket>` branch from `feat/p2-migration-2`. Commit or push only if the owner says so; never commit directly to `feat/p1-foundation`.

**Known blockers:** live Bitbucket is NOT TESTED (no credentials; never ask for a token in chat). A database opened by this code becomes version 2 and older branches refuse it; use a separate `SHIPSAFE_DB_PATH` when switching back.

**Decide and record in `docs/DECISIONS.md` before coding** (see "Blockers / known issues" in the checkpoint): merge-base semantics for PR scans (`get_changes` is two-dot; Bitbucket has `GET /merge-base/{revspec}`), a cap or skip for `import_dependencies` (one HTTP request per file today), HTTP 555 on large diffs, fork pull requests with no readable head SHA, and the request/response shapes agreed with the frontend owner.

**Acceptance check for the next task:** with mocked HTTP, repository list → PR list → PR scan → stored report works end to end; the stored row has `provider = 'bitbucket-cloud'`, `repository_id`, `pull_request_id` and full SHAs; scanning after the PR head moves marks earlier scans stale and the API shows it; every Bitbucket route answers clearly when Bitbucket is not configured; provider errors map to HTTP statuses without leaking the token; local scanning and review import are unchanged; full suite passes.

Implement only that task, run focused tests plus the full backend suite, then update the checkpoint in `docs/IMPLEMENTATION_STATUS.md`, any gate backed by executed evidence, and this file for the following agent. Keep your reply under six lines. Do not claim success without checking.
