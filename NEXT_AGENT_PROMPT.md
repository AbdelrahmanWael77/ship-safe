# Next Agent — Copy/Paste Continuation Prompt

You are joining **ShipSafe (Release Guardian)**, an existing project: FastAPI backend (`backend/`) + React/TypeScript/Vite frontend (`frontend/`). It scans a Git change or a Bitbucket pull request, flags risks, gets an AI review (OpenAI or Gemini on the server, or a Claude Code review imported as JSON), finds existing tests, turns AI findings into manual QC test cases, and builds a release assessment. **Do not restart the project, re-plan it, or redo completed work.**

**Read first:** `AGENTS.md`, `CLAUDE.md`, `docs/handoffs/P6-QC-TEST-CASES-SESSION_HANDOFF.md` (latest state, routes, what is and is not verified), then `docs/IMPLEMENTATION_STATUS.md`, `docs/CONFIGURATION.md`. Check them against `git log`, `git status` and the tests before trusting them.

**Branches (2026-11-14):** `Test-Branch` (`2e2b4a4`) → `fix/p5-feature-check` (`ff2311e`, fixes from testing PR #48) → `feat/p6-qc-test-cases` (QC test cases + handoff). Work on top of `feat/p6-qc-test-cases`. Database schema version **5**.

**Run it:** Python 3.11+, Node 22.12+ (or 24+). `python -m venv .venv` → activate → `python -m pip install -r backend/requirements.txt`; `cd frontend && npm install`; then `python scripts/dev.py` (dashboard http://127.0.0.1:5173, API docs http://127.0.0.1:8000/docs). `npm run dev:mock` in `frontend/` shows canned Bitbucket data without a backend. Keys go in `.env` only (`SHIPSAFE_OPENAI_API_KEY`, `SHIPSAFE_GEMINI_API_KEY`, Bitbucket settings — `docs/CONFIGURATION.md`).

**Tests last run (2026-11-14, Linux):** `cd backend && python -m pytest -q` → 493 passed; `cd frontend && npx vitest run` → 196 passed; `npx tsc -b` ✓; `npm run build` ✓. On Windows the backend suite is slow: run it per file or in the background.

**Rules (from the owner):**
- Never commit, push, merge, rebase, force-push or tag without the owner's explicit approval. Do not modify existing branches or merge into `Test-Branch` / `feat/p1-foundation`. Keep the branch naming convention (`feat/pN-…`, `fix/…`); no personal names in branches.
- Never read, print or copy `.env` values, API keys or tokens; never ask anyone to paste a token; never put one in code, logs, fixtures or Git.
- Send repository code to an AI provider only with the person's confirmation (the API enforces 428 for non-demo code). Bitbucket stays read-only.
- ShipSafe never executes repository code: every run is BLOCKED until an isolated runner is approved. Never fake test logs or results.
- AI findings and AI-written test cases are unverified; tester results are self-declared. Never add AI findings to the static risk score, and never say a change is safe.
- Every fix gets a regression test. Do not claim success without running the tests. After each task stop and report: what changed, files, actual test results, branch, what is left.

**Not verified yet:** QC test cases with a real OpenAI/Gemini call and on Windows.

**Suggested next tasks (the owner picks):** (1) try QC test cases on PR #48 with real OpenAI and tune the prompt in `backend/app/qc_tests.py`; (2) language-independent static checks (e.g. Semgrep) so Dart/JS/TS/Kotlin PRs are not "N/A"; (3) release-level view across PRs; (4) OpenAI + Gemini agreement on findings; (5) failed case → Jira bug (write access needs approval); (6) text-only "propose a fix". Details: section 5 of the P6 handoff.

Start by confirming the branch and running the tests, then wait for the owner's task.
