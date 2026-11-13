# Next Agent — Copy/Paste Continuation Prompt

You are joining **ShipSafe**, an existing project. All five phases have been worked through as far as an agent can go without the owner. **Do not restart the project, re-plan its phases, or redo completed work. Do not start new features.**

Read `AGENTS.md`, `CLAUDE.md`, the checkpoint at the top of `docs/IMPLEMENTATION_STATUS.md`, and `docs/handoffs/P5-FINAL-SESSION_HANDOFF.md` (exact feature status). Verify against `git status`, `git log` and the tests before trusting any of it.

**State (2026-11-13):** no phase after Phase 1 is complete, reviewed, merged or tagged. Built and passing automated tests: Bitbucket read-only integration and screens (mocked), Claude review package and import (synthetic JSON), test discovery, test proposals with recorded human decisions, a runner boundary that fails closed, release assessment with exports, security assessment, demo script, results document.

**Never happened, and must not be claimed:** a request to live Bitbucket; a review written by a real Claude Code session; the execution of any repository test; a browser walk-through; a rehearsed demo; a hidden-change evaluation; human review.

**Branches (all local, nothing pushed):** `feat/p2-frontend-pr-screens` (`74661f4`) → `feat/p3-review-package` (`f0fd75c`) → `feat/p4-test-discovery` (`8dcd34a`) → `feat/p5-final-validation` (Phase 5 commit on top). Database schema version 4. Commit only with the owner's approval; never push, merge, tag or deploy.

**Tests last run (2026-11-13, Windows 11, Node 24.22.2, Python from `.venv`):**
- `cd backend && ..\.venv\Scripts\python -m pytest -q` → 424 passed, 1 warning (**about 11.5 minutes: run it in the background or per file**)
- `cd frontend && npm test` → 150 passed (10 files); `npm run build` → ✓; `npm audit` → 0

**What happens next depends on the owner. When they report something:**
1. **Browser walk-through results** (`docs/DEMO_SCRIPT.md`, or `npm run dev:mock`): fix what they found on `feat/p5-final-validation`, add a regression test for each fix, record the result.
2. **Live Bitbucket smoke test results** (Phase 2 task 6): record PASS / FAIL / BLOCKED per step in the checkpoint and `docs/ACCEPTANCE_MATRIX.md`. Payload shapes came from Bitbucket's published API description, so differences are likely: fix them in `backend/app/providers/bitbucket.py` with a mocked test reproducing the real payload shape (without real names or data). Never ask for or print the token; never read the values in `.env`.
3. **A real `claude-review.json`** (Phase 3): if the import is refused, read the API's reason; fix the instructions or template in `backend/app/ai_handoff.py` rather than loosening validation.
4. **Approval for a container runner** (Phase 4): only in a session that is permitted to start Docker containers (in the 2026-11-13 session this was refused by the permission settings and was not worked around). Order: prove isolation with controlled probes (no network, no credentials, read-only source, non-root, dropped capabilities, CPU / memory / pids / time limits, no Docker socket) → run only the synthetic demo repository → write the approved proposal only into a disposable workspace after re-checking the path there → store real start, end, exit code and bounded output in `test_runs` → base versus head comparison → the four LedgerLite challenge cases. **Never run repository tests on the host. No fake logs.**
5. **Human review comments:** address them on the branch of the phase they belong to.

**Decisions to keep:** the review context digest covers identity and commits. Stale state is never stored in a package, review or proposal; it is read from the scan row. The echoed identity in a v2 review is `reviewed_source`. A proposal only ever adds a new file. `eligible_to_run` = approved and not stale. A blocked run has no start, end, exit code or output. The assessment never says a change is safe. No Claude API key, no Claude subprocess, no automatic patch application, no Bitbucket write.

Keep your reply under six lines. Do not claim success without checking.
