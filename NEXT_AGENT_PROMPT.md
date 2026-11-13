# Next Agent — Copy/Paste Continuation Prompt

You are joining **ShipSafe**, an existing project, mid-implementation. The v0.2 baseline and Phase 1 are finished. **Do not restart the project, re-plan its phases, or redo completed work.**

Read `AGENTS.md`, `CLAUDE.md`, and the checkpoint at the top of `docs/IMPLEMENTATION_STATUS.md`. Verify the state below against `git status`, `git log`, and the tests before trusting it.

**Current phase:** 3 — Claude Code review (`prompts/PHASE-03-CLAUDE-REVIEW.md`), started by owner decision while **Phase 2 is still open**.

**Phase 2 open items (owner-run):** task 6, the read-only live Bitbucket smoke test (the owner is preparing credentials in the root `.env`, which is git-ignored and already has the empty variable names), and a browser walk-through of the Bitbucket screens (`cd frontend && npm run dev:mock`, with the backend running on port 8000). Record PASS / FAIL / BLOCKED in the checkpoint and `docs/ACCEPTANCE_MATRIX.md` when the owner reports. Never ask for a token in chat; never read or print the values in `.env`.

**Branches (all local, nothing pushed):** `feat/p2-frontend-pr-screens` at `74661f4` (P2 task 5, committed with approval). `feat/p3-review-package`, cut from it: Phase 3 tasks 1–3 are committed (`d0d19d2`, `779932e`, `dd4c6db`); **Phase 3 task 4 is done and uncommitted in the working tree.** Do not discard it. Commit only when the owner says so.

**Phase 3 task 4 (done, frontend only):** Claude Review page in `frontend/src/App.tsx`: "Previous reviews" table (history route, falls back to this scan's reviews), selectable review with stale warning and an "earlier scan" notice, side-by-side panel of static suspicions and imported findings, import result shown next to the import control. Files: `App.tsx`, `App.test.tsx`, `types.ts`, `bitbucket.css`, `test/setup.ts`.

**Phase 3 task 3 (done):** duplicate review imports refused (409, `review_content_digest` in `ai_handoff.py`); every served review carries `scan_id` and `scan_binding` (read from the scan row at response time, never stored), so a review is stale when its scan is; `GET /api/scans/{id}/ai/reviews/history` lists reviews across all stored scans of the same pull request with `current_scan`; stale warning on the Claude Review page. No migration. Files: `backend/app/main.py`, `ai_handoff.py`, `backend/tests/test_review_import_history.py`, `test_bitbucket_api.py`, `test_migration_2.py`, `frontend/src/types.ts`, `App.tsx`, `App.test.tsx`, `docs/ARCHITECTURE.md`.

**Phase 3 task 2 (done):** review schema `shipsafe.ai-review.v2` in `backend/app/ai_handoff.py` (`AIReviewImportV2`, `parse_review`, `source_echo`): finding `id`, `status: "suspected"`, `suggested_validation`, optional `proposed_patch`; review `reviewed_source` (must equal the scan's provider / repository / pull request / head commit, else 409) and `missing_context`. v1 still accepted. Template and instructions updated. Review cards show the new fields as unverified. Files: `ai_handoff.py`, `main.py`, `backend/tests/test_review_schema_v2.py`, `test_bitbucket_api.py`, `frontend/src/types.ts`, `App.tsx`, `App.test.tsx`, `bitbucket.css`, `docs/CLAUDE-CODE-HANDOFF.md`.

**Phase 3 task 1 (done):** review package with identity and exact commits under the digest, `PACKAGE.json` manifest, best-effort secret redaction, 1 MiB limit with marked omissions, HTTP 428 without `acknowledge_source_sharing=true` for non-demo scans, confirmation checkbox on the Claude Review page. Files: `backend/app/ai_handoff.py`, `backend/app/main.py`, `backend/tests/test_review_package.py`, `test_bitbucket_api.py`, `test_ai_handoff.py`, `frontend/src/App.tsx`, `App.test.tsx`, `bitbucket.css`, docs.

**Tests last run (2026-11-13, Windows 11):**
- `cd backend && ..\.venv\Scripts\python -m pytest -q` → 299 passed, 1 warning (about 9 minutes)
- `cd frontend && npm test` → 119 passed (7 files); `npm run build` → ✓ (backend not re-run after task 4: no backend change)

**Next atomic task — Phase 3 task 5 (operating model) and phase close-out, documentation plus evidence:** (a) in `docs/CLAUDE-CODE-HANDOFF.md` (or `docs/TEAM_WORKFLOW.md` where it fits) write the short operating model for the company Team subscription: each reviewer uses their own approved Claude Code sign-in; source-sharing approval before export; inspect `review-input.json` first; never share session files, credentials or subscription access; ShipSafe needs no Claude API key; Bitbucket read-only credentials stay separate and server-side. Add a source-export review checklist for QA/security. (b) Tick the Phase 3 acceptance gates in `prompts/PHASE-03-CLAUDE-REVIEW.md` and add Phase 3 rows to `docs/ACCEPTANCE_MATRIX.md` **only** with the executed evidence recorded in the checkpoint; state plainly that only synthetic JSON fixtures were imported and that no real authenticated Claude Code session was run (the owner must run one for that evidence: export a demo scan, review it in their own Claude Code, import the result). (c) Write the Phase 3 session handoff in `templates/SESSION_HANDOFF.md` format under `docs/handoffs/`. Do not tag `shipsafe-phase-3` and do not start Phase 4 (test execution) without the owner's approval.

**Decisions to keep:** the context digest covers the identity, so packages exported before task 1 are refused on import (deliberate). Stale state is never part of the package or digest. Unknown acknowledgement state in the UI is treated as "required". The echoed identity is `reviewed_source`, never `source` (that key is the saved review's provenance marker). No Claude API key, no Claude subprocess, no automatic patch execution.

**NOT TESTED:** a real Claude Code session (only synthetic JSON fixtures); live Bitbucket; any screen in a real browser.

Keep your reply under six lines. Do not claim success without checking.
