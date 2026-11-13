# Next Agent — Copy/Paste Continuation Prompt

You are joining **ShipSafe**, an existing project, mid-implementation. The v0.2 baseline and Phase 1 are finished. **Do not restart the project, re-plan its phases, or redo completed work.**

Read `AGENTS.md`, `CLAUDE.md`, and the checkpoint at the top of `docs/IMPLEMENTATION_STATUS.md`. Verify the state below against `git status`, `git log`, and the tests before trusting it.

**Current phase:** 3 — Claude Code review (`prompts/PHASE-03-CLAUDE-REVIEW.md`), started by owner decision while **Phase 2 is still open**.

**Phase 2 open items (owner-run):** task 6, the read-only live Bitbucket smoke test (the owner is preparing credentials in the root `.env`, which is git-ignored and already has the empty variable names), and a browser walk-through of the Bitbucket screens (`cd frontend && npm run dev:mock`, with the backend running on port 8000). Record PASS / FAIL / BLOCKED in the checkpoint and `docs/ACCEPTANCE_MATRIX.md` when the owner reports. Never ask for a token in chat; never read or print the values in `.env`.

**Branches (all local, nothing pushed):** `feat/p2-frontend-pr-screens` at `74661f4` (P2 task 5, committed with approval). `feat/p3-review-package`, cut from it: Phase 3 task 1 is committed (`d0d19d2`); **Phase 3 task 2 is done and uncommitted in the working tree.** Do not discard it. Commit only when the owner says so.

**Phase 3 task 2 (done):** review schema `shipsafe.ai-review.v2` in `backend/app/ai_handoff.py` (`AIReviewImportV2`, `parse_review`, `source_echo`): finding `id`, `status: "suspected"`, `suggested_validation`, optional `proposed_patch`; review `reviewed_source` (must equal the scan's provider / repository / pull request / head commit, else 409) and `missing_context`. v1 still accepted. Template and instructions updated. Review cards show the new fields as unverified. Files: `ai_handoff.py`, `main.py`, `backend/tests/test_review_schema_v2.py`, `test_bitbucket_api.py`, `frontend/src/types.ts`, `App.tsx`, `App.test.tsx`, `bitbucket.css`, `docs/CLAUDE-CODE-HANDOFF.md`.

**Phase 3 task 1 (done):** review package with identity and exact commits under the digest, `PACKAGE.json` manifest, best-effort secret redaction, 1 MiB limit with marked omissions, HTTP 428 without `acknowledge_source_sharing=true` for non-demo scans, confirmation checkbox on the Claude Review page. Files: `backend/app/ai_handoff.py`, `backend/app/main.py`, `backend/tests/test_review_package.py`, `test_bitbucket_api.py`, `test_ai_handoff.py`, `frontend/src/App.tsx`, `App.test.tsx`, `bitbucket.css`, docs.

**Tests last run (2026-11-13, Windows 11):**
- `cd backend && ..\.venv\Scripts\python -m pytest -q` → 284 passed, 1 warning (about 8 minutes)
- `cd frontend && npm test` → 105 passed (7 files); `npm run build` → ✓

**Next atomic task — Phase 3 task 3 (strict import and history):** already enforced: schema version, JSON size and types, scan id, context digest, repository / pull request / head commit (v2), changed-file references, static finding ids, no fabricated verified or test status. Still to do: (a) reject a duplicate import of the same review content for a scan (decide by a digest of the canonical review JSON; return 409); (b) make a review of a pull request scan **stale, not current**, when the pull request head moves: review responses should carry the scan's `binding` stale state (`stale`, `stale_at`, `stale_checked`) read from the scan row, never stored in the review; (c) keep every import with its timestamp and the static results untouched (add tests that pin this); (d) list reviews across the scans of one pull request so history survives a new scan. Avoid a schema migration if the existing `ai_reviews` table is enough; if one is needed it must be a safe migration 3 with tests. Tests: wrong scan, wrong SHA, bad digest, missing and extra fields, unknown paths, duplicates, size limit, stale after head move (mocked Bitbucket).

**Decisions to keep:** the context digest covers the identity, so packages exported before task 1 are refused on import (deliberate). Stale state is never part of the package or digest. Unknown acknowledgement state in the UI is treated as "required". The echoed identity is `reviewed_source`, never `source` (that key is the saved review's provenance marker). No Claude API key, no Claude subprocess, no automatic patch execution.

**NOT TESTED:** a real Claude Code session (only synthetic JSON fixtures); live Bitbucket; any screen in a real browser.

Keep your reply under six lines. Do not claim success without checking.
