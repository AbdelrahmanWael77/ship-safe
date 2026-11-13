# Next Agent — Copy/Paste Continuation Prompt

You are joining **ShipSafe**, an existing project, mid-implementation. The v0.2 baseline and Phase 1 are finished. **Do not restart the project, re-plan its phases, or redo completed work.**

Read `AGENTS.md`, `CLAUDE.md`, and the checkpoint at the top of `docs/IMPLEMENTATION_STATUS.md`. Verify the state below against `git status`, `git log`, and the tests before trusting it.

**Current phase:** 3 — Claude Code review (`prompts/PHASE-03-CLAUDE-REVIEW.md`), started by owner decision while **Phase 2 is still open**.

**Phase 2 open items (owner-run):** task 6, the read-only live Bitbucket smoke test (the owner is preparing credentials in the root `.env`, which is git-ignored and already has the empty variable names), and a browser walk-through of the Bitbucket screens (`cd frontend && npm run dev:mock`, with the backend running on port 8000). Record PASS / FAIL / BLOCKED in the checkpoint and `docs/ACCEPTANCE_MATRIX.md` when the owner reports. Never ask for a token in chat; never read or print the values in `.env`.

**Branches (all local, nothing pushed):** `feat/p2-frontend-pr-screens` at `74661f4` (P2 task 5, committed with approval). `feat/p3-review-package`, cut from it: **Phase 3 task 1 is done and uncommitted in the working tree.** Do not discard it. Commit only when the owner says so.

**Phase 3 task 1 (done):** review package with identity and exact commits under the digest, `PACKAGE.json` manifest, best-effort secret redaction, 1 MiB limit with marked omissions, HTTP 428 without `acknowledge_source_sharing=true` for non-demo scans, confirmation checkbox on the Claude Review page. Files: `backend/app/ai_handoff.py`, `backend/app/main.py`, `backend/tests/test_review_package.py`, `test_bitbucket_api.py`, `test_ai_handoff.py`, `frontend/src/App.tsx`, `App.test.tsx`, `bitbucket.css`, docs.

**Tests last run (2026-11-13, Windows 11):**
- `cd backend && ..\.venv\Scripts\python -m pytest -q` → 257 passed, 1 warning (about 7 minutes)
- `cd frontend && npm test` → 103 passed (7 files); `npm run build` → ✓

**Next atomic task — Phase 3 task 2 (review prompt/schema):** add review schema `shipsafe.ai-review.v2` in `backend/app/ai_handoff.py`: each finding gets an `id`, a fixed `status: "suspected"`, `suggested_validation`, optional `proposed_patch` (stored as text, never applied), and the review gets `missing_context`; the review echoes `source` (repository, pull request, head commit) so task 3 can reject a wrong commit. Keep accepting v1 imports. Update `instructions()` and `response-template.json` to cover security, authorization, API compatibility, money/data integrity, validation, exception handling, affected modules and missing tests, and to forbid claims of executed commands or tests. Update `frontend/src/types.ts` and the review cards only as far as needed to show the new fields as UNVERIFIED. Tests: round trip for a local and a mocked Bitbucket scan, v1 still accepted, fabricated `verified` / test-result fields rejected.

**Decisions to keep:** the context digest covers the identity, so packages exported before task 1 are refused on import (deliberate). Stale state is never part of the package or digest. Unknown acknowledgement state in the UI is treated as "required". No Claude API key, no Claude subprocess, no automatic patch execution.

**NOT TESTED:** a real Claude Code session (only synthetic JSON fixtures); live Bitbucket; any screen in a real browser.

Keep your reply under six lines. Do not claim success without checking.
