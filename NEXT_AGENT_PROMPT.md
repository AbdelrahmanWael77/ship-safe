# Next Agent — Copy/Paste Continuation Prompt

You are joining **ShipSafe**, an existing project, mid-implementation. The v0.2 baseline and Phase 1 are finished. **Do not restart the project, re-plan its phases, or redo completed work.**

Read `AGENTS.md`, `CLAUDE.md`, and the checkpoint at the top of `docs/IMPLEMENTATION_STATUS.md`. Read only `prompts/PHASE-02-BITBUCKET.md` and the code your task touches. Verify the checkpoint below against `git status` and the tests before trusting it.

**Current phase:** 2 — Bitbucket repositories and pull requests.

**Next atomic task (P2 task 2):** Bitbucket settings and credential loading. Read `SHIPSAFE_BITBUCKET_WORKSPACE`, `SHIPSAFE_BITBUCKET_REPOSITORIES` (comma-separated slugs), `SHIPSAFE_BITBUCKET_TOKEN`, and optional `SHIPSAFE_BITBUCKET_EMAIL` in `backend/app/config.py`; construct `BitbucketCloudProvider` at startup in `backend/app/main.py` only when configured. No routes, no schema change.

**Relevant files:** `backend/app/config.py`, `backend/app/main.py`, `backend/app/providers/bitbucket.py` (constructor signature), `.env.example`, `docs/CONFIGURATION.md`, `backend/tests/test_foundation.py` (settings test style).

**Already implemented:** `backend/app/providers/bitbucket.py` — read-only Bitbucket Cloud provider for all three protocols in `providers/base.py` (repository allowlist, pagination, PR list/detail with full SHAs, ref resolution, two-dot change sets, tree and file reads, auth, retries, byte caps). `backend/app/errors.py` gained `ProviderAuthError` and `ProviderUnavailable`. It is **not** wired into settings, the API, the database, or the UI.

**Tests last run (2026-11-12, Windows 11, Python 3.12.4):**
- `cd backend && python -m pytest -q tests/test_bitbucket_provider.py` → 38 passed
- `cd backend && python -m pytest -q` → 139 passed, 1 warning in 270.52 s (101 existing + 38 new)
- Use `.venv\Scripts\python`. The full suite takes about four minutes.

**Branch / commit / uncommitted edits:** branch `feat/p2-bitbucket-provider`, on top of `feat/p1-foundation` at `9ed331c`. Uncommitted: `AGENTS.md`, `NEXT_AGENT_PROMPT.md`, `CLAUDE.md`, `docs/IMPLEMENTATION_STATUS.md`, `docs/DECISIONS.md`, `backend/app/errors.py`, `backend/app/providers/__init__.py`, `base.py`, `bitbucket.py`, `backend/tests/test_bitbucket_provider.py`. Do not discard them. Commit only if the owner says so; never touch `main` or push.

**Known blockers:** live Bitbucket is NOT TESTED (no credentials; never ask for a token in chat). Phase 1 is unmerged. Open design points for task 4 are listed under "Blockers / known issues" in the checkpoint (merge-base semantics, per-file HTTP cost of import analysis, HTTP 555, fork PRs).

**Acceptance check for the next task:** with no Bitbucket variables the app starts and all existing tests pass; a partial configuration (for example a workspace without a token) raises `ConfigError`; the token is absent from `repr(settings)`, logs, and every API response; new tests cover each case.

Implement only that task, run focused tests plus the full backend suite, then update the checkpoint in `docs/IMPLEMENTATION_STATUS.md`, any gate backed by executed evidence, and this file for the following agent. Keep your reply under six lines. Do not claim success without checking.
