# Next Agent — Copy/Paste Continuation Prompt

You are joining **ShipSafe (Release Guardian)**, an existing project: FastAPI backend (`backend/`) + React/TypeScript/Vite frontend (`frontend/`). It scans a Git change or a Bitbucket pull request, flags risks, gets an AI review (OpenAI or Gemini on the server, or a Claude Code review imported as JSON), finds existing tests, turns AI findings into manual QC test cases, and builds a release assessment. **Do not restart the project, re-plan it, or redo completed work.**

**Read first:** `AGENTS.md`, `CLAUDE.md`, `docs/handoffs/P7-STATIC-RULES-SESSION_HANDOFF.md` (latest task), `docs/handoffs/P6-QC-TEST-CASES-SESSION_HANDOFF.md` (routes, what is and is not verified), then `docs/IMPLEMENTATION_STATUS.md`, `docs/CONFIGURATION.md`. Check them against `git log`, `git status` and the tests before trusting them.

**Branches (2026-11-14):** `Test-Branch` (`2e2b4a4`) → `fix/p5-feature-check` (`ff2311e`, fixes from testing PR #48) → `feat/p6-qc-test-cases` (`31f7fc4`, QC test cases + handoff) → `feat/p7-static-rules` (static pattern rules for Dart, JS/TS, Kotlin, Java; **committed locally on 2026-11-14 with the owner's approval; check with `git log` and `git status` whether it has been pushed**). Work on top of `feat/p7-static-rules`. Database schema version **5**.

**Phase 7 task 1 (done):** `backend/app/pattern_rules.py` holds 8 line-pattern rules (ids `shipsafe.*`); `backend/app/scanner.py` reads base and head of changed Dart/JS/TS/Kotlin/Java files through the provider and appends findings with `source: "pattern-rules"`, `rule_id`, `language`; `summary.pattern_rules` reports files analysed and skipped. Owner-delegated decisions: built-in engine (no Semgrep, no new dependency); pattern findings are **counted as static findings and never added to the risk score**. The rules were written from a description of PR #48 and tested on synthetic code only: **PR #48 has not been scanned with them and their precision on real code is unknown.**

**Run it:** Python 3.11+, Node 22.12+ (or 24+). `python -m venv .venv` → activate → `python -m pip install -r backend/requirements.txt`; `cd frontend && npm install`; then `python scripts/dev.py` (dashboard http://127.0.0.1:5173, API docs http://127.0.0.1:8000/docs). `npm run dev:mock` in `frontend/` shows canned Bitbucket data without a backend. Keys go in `.env` only (`SHIPSAFE_OPENAI_API_KEY`, `SHIPSAFE_GEMINI_API_KEY`, Bitbucket settings — `docs/CONFIGURATION.md`).

**Tests last run (2026-11-14, Windows 11, on `feat/p7-static-rules`):** `cd backend && ..\.venv\Scripts\python -m pytest -q` → 554 passed (14 min 10 s: run it in the background or per file); `cd frontend && npx vitest run` → 198 passed; `npx tsc -b` ✓; `npm run build` ✓.

**Rules (from the owner):**
- Never commit, push, merge, rebase, force-push or tag without the owner's explicit approval. Do not modify existing branches or merge into `Test-Branch` / `feat/p1-foundation`. Keep the branch naming convention (`feat/pN-…`, `fix/…`); no personal names in branches.
- Never read, print or copy `.env` values, API keys or tokens; never ask anyone to paste a token; never put one in code, logs, fixtures or Git.
- Send repository code to an AI provider only with the person's confirmation (the API enforces 428 for non-demo code). Bitbucket stays read-only.
- ShipSafe never executes repository code: every run is BLOCKED until an isolated runner is approved. Never fake test logs or results.
- AI findings and AI-written test cases are unverified; tester results are self-declared. Never add AI findings to the static risk score, and never say a change is safe.
- Every fix gets a regression test. Do not claim success without running the tests. After each task stop and report: what changed, files, actual test results, branch, what is left.

**Not verified yet:** the pattern rules on a real pull request (PR #48) and through a Bitbucket scan; QC test cases with a real OpenAI/Gemini call and on Windows; any of the Phase 7 UI in a browser.

**Suggested next tasks (the owner picks):** (1) owner scans PR #48 on `feat/p7-static-rules` and reports hits, misses and false alarms; tune `backend/app/pattern_rules.py` with a synthetic flagged and clean fixture for each change, and add a mocked Bitbucket test with a `.dart` file; (2) try QC test cases on PR #48 with real OpenAI and tune the prompt in `backend/app/qc_tests.py`; (3) release-level view across PRs; (4) OpenAI + Gemini agreement on findings; (5) failed case → Jira bug (write access needs approval); (6) text-only "propose a fix". Details: the P7 handoff, and section 5 of the P6 handoff.

Start by confirming the branch and running the tests, then wait for the owner's task.
