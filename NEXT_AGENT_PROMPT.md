# Next Agent — Copy/Paste Continuation Prompt

You are joining **ShipSafe**, an existing project, mid-implementation. The v0.2 baseline and Phase 1 are finished. **Do not restart the project, re-plan its phases, or redo completed work.**

Read `AGENTS.md`, `CLAUDE.md`, and the checkpoint at the top of `docs/IMPLEMENTATION_STATUS.md`. Read only `prompts/PHASE-02-BITBUCKET.md` (section C), the "HTTP API" section of `docs/ARCHITECTURE.md` (especially "Bitbucket routes"), `docs/example-bitbucket-responses.json`, and the code your task touches. Verify the checkpoint below against `git status`, `git log`, and the tests before trusting it.

**Current phase:** 2 — Bitbucket repositories and pull requests.

**Next atomic task (P2 task 5):** Frontend. Add Repositories, Pull Requests, and PR Analysis screens to the dashboard, using a typed client against the existing Bitbucket routes. No backend change unless a contract gap is found and recorded.

**Relevant files:** `frontend/src/types.ts`, `frontend/src/App.tsx` (single component file, `useState` page switching, `api<T>()` helper, `describeError` reads `detail` as a string), `frontend/src/styles.css`. Backend contract: `docs/ARCHITECTURE.md` → "Bitbucket routes"; example responses (mock data) in `docs/example-bitbucket-responses.json`; behaviour in `backend/tests/test_bitbucket_api.py`.

**Already implemented (backend, mocked HTTP only):**
- `GET /api/bitbucket/status`, `GET /api/bitbucket/repositories`, `GET /api/bitbucket/repositories/{slug}/pull-requests?state=`, `GET …/pull-requests/{id}`, `POST …/pull-requests/{id}/scans` (optional body `{"head_commit": "<40-hex>"}`).
- Pull request scans compare merge base → head, are stored with full SHAs, and go stale when the head moves. Scan responses (`POST /api/scans`, `GET /api/scans`, `GET /api/scans/{id}`, export) carry `binding`.
- Stale display rule: show "stale" only when `binding.stale` is true; show "current" only when `stale` is false **and** `stale_checked` is true; otherwise "not checked". The list checks at most 20 scanned pull requests per request; history and scan detail never check. See the reading table in `docs/ARCHITECTURE.md`.
- Errors from Bitbucket routes: `{"detail": string, "code": string}`; 503 `bitbucket_not_configured` when the server has no Bitbucket settings; 409 `head_changed`, `head_commit_unavailable`, `base_commit_unavailable`; 422 `diff_too_large`; 502/503 for Bitbucket trouble.
- Earlier: provider (task 1, `08b3b1b`), settings (task 2, `ebc9068`), migration 2 (task 3, `82d14ed`).

**Tests last run (2026-11-12, Linux cloud container, Python 3.13.18, Node from the container image):**
- `cd backend && python -m pytest -q tests/test_bitbucket_api.py` → 41 passed
- `cd backend && python -m pytest -q` → 229 passed, 1 warning
- `cd frontend && npm ci && npm run build` → ✓ built (no frontend source changed)
- Not re-run on Windows since `08b3b1b`. On Windows use `.venv\Scripts\python`.

**Branch / commit / uncommitted edits:** GitHub has no `main`; the default branch is `feat/p1-foundation` (`98c9d92`, contains task 1). Stacked on `08b3b1b`: `feat/p2-bitbucket-settings` (`ebc9068`, task 2) → `feat/p2-migration-2` (`82d14ed`, task 3) → `feat/p2-bitbucket-api` (task 4, branch head). All three are committed; none was on GitHub when this was written (the agent session had no GitHub credential), so check `git ls-remote origin`. No uncommitted edits. Start task 5 on a new `feat/p2-<ticket>` branch from `feat/p2-bitbucket-api`. Commit or push only if the owner says so; never commit directly to `feat/p1-foundation`, and never force push or rebase.

**Known blockers:** live Bitbucket is NOT TESTED (no credentials; never ask for a token in chat), so every payload shape is unconfirmed until task 6. The owner accepted the response shapes as the initial contract, subject to frontend integration validation; record any gap you find instead of silently changing the backend. The repository has no frontend test harness, while the Phase 2 prompt asks for frontend tests: raise this with the owner before choosing one. A database opened by this code is version 2; older branches refuse it.

**Acceptance check for the next task:** with Bitbucket not configured the new screens show a clear setup message and the demo flow works as before; with a configured (or clearly labelled mock) backend the user can pick a repository, see its pull requests, scan one, and see findings, diff, bound commits, a stale badge and an "Open in Bitbucket" link; loading, empty and error states are real; `head_changed` is handled by reloading; no credential reaches the browser bundle; `npm run build` passes; backend suite still passes.

Implement only that task, run the frontend build and the backend suite, then update the checkpoint in `docs/IMPLEMENTATION_STATUS.md`, any gate backed by executed evidence, and this file for the following agent. Keep your reply under six lines. Do not claim success without checking.
