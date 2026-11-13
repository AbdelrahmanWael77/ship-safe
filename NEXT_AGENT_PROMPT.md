# Next Agent — Copy/Paste Continuation Prompt

You are joining **ShipSafe**, an existing project, mid-implementation. The v0.2 baseline and Phase 1 are finished. **Do not restart the project, re-plan its phases, or redo completed work.**

Read `AGENTS.md`, `CLAUDE.md`, and the checkpoint at the top of `docs/IMPLEMENTATION_STATUS.md`. Verify the state below against `git status`, `git log`, and the tests before trusting it.

**Current phase:** 2 — Bitbucket repositories and pull requests (`prompts/PHASE-02-BITBUCKET.md`).

**State (2026-11-13):** P2 tasks 1–4 (backend) are committed. P2 task 5 (frontend screens) is code-complete, tested and committed on `feat/p2-frontend-pr-screens` (local only). Never push or merge without the owner.

**Task 5 files:** `frontend/src/bitbucket/PullRequestsPage.tsx`, `PrAnalysisPage.tsx`, `mock.ts` (each with a `.test.tsx`), `BitbucketSection.tsx`, `client.ts`, `pages.ts`, `ErrorPanel.tsx`, `frontend/src/components.tsx` (moved out of `App.tsx`), `App.tsx`, `App.test.tsx`, `bitbucket.css`, `test/fixtures.ts`, `frontend/package.json` (`dev:mock`), `README.md`, `docs/ACCEPTANCE_MATRIX.md`, and the two status files.

**What works (jsdom tests, stubbed `fetch`):** sidebar BITBUCKET group → Repositories, Pull requests (repository picker, state filter, search, truncated notice) → Analyze → PR analysis: the scan sends the `head_commit` on screen; 409 `head_changed` reloads the pull request; the report shows bound full SHAs, a Current / Stale / Not checked badge, findings, diff, Open in Bitbucket; stored scans can be viewed and opened in the existing dashboard pages; the scan history marks pull request scans. `npm run dev:mock` is development-only invented data with a permanent MOCK DATA banner; none of it is in the production bundle.

**Tests last run (2026-11-13, Windows 11, Node 24.22.2):**
- `cd frontend && npm test` → 100 passed (7 files); `npm run build` → ✓; `npm audit` → 0
- `cd backend && ..\.venv\Scripts\python -m pytest -q` → 236 passed, 1 warning (about 6 minutes on Windows)

**NOT TESTED:** the new screens in a real browser; narrow screens; live Bitbucket (no request has ever gone to `api.bitbucket.org`; payload shapes come from Bitbucket's published API description).

**Immediate next action:**
1. Owner review of the task 5 commit.
2. Browser walk-through: `cd frontend && npm run dev:mock` (Pull requests → Analyze #101 → scan; #106 head-changed reload; #104 fork refusal; #105 oversized diff), then `python scripts\dev.py` for the demo and the "Bitbucket is not configured" state. Fix what the walk-through shows; record the result.
3. **P2 task 6:** human-run read-only live smoke test with approved credentials in the server's local `.env` only. Record PASS or BLOCKED and any payload difference in `docs/IMPLEMENTATION_STATUS.md` and `docs/ACCEPTANCE_MATRIX.md`. Never ask for a token in chat; never put one in a `VITE_*` variable.

**Known limits:** a large scan has no progress report; stale state on lists is checked for at most 20 scanned pull requests; a version 2 database is refused by older branches. Do not start Phase 3 until the Phase 2 gates are reviewed.

Keep your reply under six lines. Do not claim success without checking.
