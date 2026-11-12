# Next Agent — Copy/Paste Continuation Prompt

You are joining **ShipSafe**, an existing project, mid-implementation. The v0.2 baseline and Phase 1 are finished. **Do not restart the project, re-plan its phases, or redo completed work.**

Read `AGENTS.md`, `CLAUDE.md`, and the checkpoint at the top of `docs/IMPLEMENTATION_STATUS.md`. Read only `prompts/PHASE-02-BITBUCKET.md`, `docs/MIGRATIONS.md`, and the code your task touches. Verify the checkpoint below against `git status` and the tests before trusting it.

**Current phase:** 2 — Bitbucket repositories and pull requests.

**Next atomic task (P2 task 3):** Migration 2. Add `provider`, `repository_id`, `pull_request_id`, `base_commit`, `head_commit` (full 40-character SHAs) to `scans`, plus stale detection support, following the proposal in `docs/MIGRATIONS.md`. Existing rows must survive unchanged. No routes.

**Relevant files:** `backend/app/db.py` (`MIGRATIONS`, `migrate`), `docs/MIGRATIONS.md` (rules and the proposed SQL), the migration tests in `backend/tests/test_foundation.py` (style to follow), `backend/app/main.py` (`create_scan` insert, only if local scans should fill the new columns).

**Already implemented:**
- P2 task 1 (`08b3b1b`): `backend/app/providers/bitbucket.py`, read-only Bitbucket Cloud provider, 38 mocked-HTTP tests.
- P2 task 2: `backend/app/config.py` reads `SHIPSAFE_BITBUCKET_WORKSPACE`, `_REPOSITORIES`, `_TOKEN`, optional `_EMAIL` into `Settings.bitbucket` (all-or-nothing; `ConfigError` otherwise; token held in `config.Secret`). `create_app` builds the provider into `app.state.bitbucket`, or `None`. Nothing reads `app.state.bitbucket` yet: no route, no schema, no UI.

**Tests last run (2026-11-12, Linux cloud container, Python 3.13.18):**
- `cd backend && python -m pytest -q tests/test_bitbucket_settings.py` → 32 passed
- `cd backend && python -m pytest -q` → 171 passed, 1 warning (139 existing + 32 new)
- Not re-run on Windows after task 2. On Windows use `.venv\Scripts\python`; the full suite took about four minutes there.

**Branch / commit / uncommitted edits:** `feat/p2-bitbucket-provider` at `08b3b1b` (stacked on `feat/p1-foundation` at `9ed331c`). Task 2 is committed on `feat/p2-bitbucket-settings`, cut from `08b3b1b`; start task 3 from that branch's head, on a new `feat/p2-<ticket>` branch. No uncommitted edits. Commit only if the owner says so; never touch `main` or push without approval.

**Known blockers:** live Bitbucket is NOT TESTED (no credentials; never ask for a token in chat). Phase 1 is unmerged. Open design points for task 4 are listed under "Blockers / known issues" in the checkpoint (merge-base semantics, per-file HTTP cost of import analysis, HTTP 555, fork PRs).

**Decide and record in `docs/DECISIONS.md` before coding:** whether "stale" is a stored column or computed by comparing `head_commit` with the pull request's current head (`docs/MIGRATIONS.md` proposes computed), and the two open questions at the end of `docs/MIGRATIONS.md`.

**Acceptance check for the next task:** a version-1 database with rows migrates to version 2 with those rows unchanged in the old columns and `provider = 'local-git'`; a failed migration rolls back completely; a database from a newer build is still refused; existing scan, export, and review-import tests pass; new tests cover each case; full suite passes.

Implement only that task, run focused tests plus the full backend suite, then update the checkpoint in `docs/IMPLEMENTATION_STATUS.md`, any gate backed by executed evidence, and this file for the following agent. Keep your reply under six lines. Do not claim success without checking.
