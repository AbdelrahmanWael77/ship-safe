# Implementation status

## Checkpoint — living, updated after every task

Rules: `AGENTS.md` and `CLAUDE.md`. Handoff prompt: `NEXT_AGENT_PROMPT.md`.

- **Roadmap:** `prompts/PHASE-01-FOUNDATION.md` … `PHASE-05-FINAL-VALIDATION.md`; gates in `docs/ACCEPTANCE_MATRIX.md`
- **Current phase:** 5 — final validation (`prompts/PHASE-05-FINAL-VALIDATION.md`). **Everything an agent can build without the owner is built; no phase after 1 is complete, reviewed, merged or tagged.** Open, owner-only: Phase 2 live Bitbucket smoke test and browser walk-through; Phase 3 one real Claude Code review round trip; Phase 4 isolated runner (execution is **BLOCKED**), baseline/head comparison and challenge cases; Phase 5 rehearsed demo, hidden-change evaluation and human review. Exact feature status: `docs/handoffs/P5-FINAL-SESSION_HANDOFF.md`.
- **Last updated:** 2026-11-13

### OpenAI as a second AI review provider, with token usage and cost — 2026-11-13 (on `Test-Branch`, uncommitted; owner request)
- **What changed:** `backend/app/openai_review.py` (new): Responses API client (`Authorization` header only, key masked out of errors, `store: false`, strict JSON schema, `reasoning.effort` default `low` with automatic fallback for models without reasoning, same retry policy as Gemini). Settings `SHIPSAFE_OPENAI_API_KEY`, `SHIPSAFE_OPENAI_MODEL` (default `gpt-6-luna`), `SHIPSAFE_OPENAI_REASONING_EFFORT`. New routes `GET /api/ai/providers` and `POST /api/scans/{id}/ai/model-reviews` `{provider, acknowledge_source_sharing}`; the Gemini route stays. Every model review stores `generator.usage` (input/output/reasoning tokens), `duration_ms`, and for OpenAI models with a published price `estimated_cost_usd` (`PRICES_PER_MILLION`, read from developers.openai.com/api/docs/pricing on 2026-11-13). UI: provider picker + per-provider sharing confirmation on Claude Review and PR analysis ("Also review with AI", remembered per repository; switching company clears it); usage/cost shown with each review; Configuration lists the configured models.
- **Tests:** full backend `pytest -q` → 473 passed (13 min 6 s); `pytest tests/test_openai_review.py tests/test_gemini.py` → 49 passed (22 new); `vitest run` → 169 passed (`PrAnalysisAI.test.tsx` replaces `PrAnalysisGemini.test.tsx`; App panel tests rewritten); `tsc -b` ✓; `npm run e2e` → 6 passed, 1 skipped.
- **Executed live — PASS:** PR #48 through the UI with OpenAI `gpt-6-luna` (owner requested): scan 29.6 s, review done at 54.5 s (24.9 s model time), 6,126 tokens (3,487 in / 2,639 out), ≈ $0.0017; block_release, 8 findings (1 critical, 5 high, 2 medium), 7 test ideas; missed only the button disabled/loading change. Shown on PR analysis, Risk findings (8) and Test intelligence (7).

### One-click "Scan + AI review" on PR analysis — 2026-11-13 (on `Test-Branch`, uncommitted; owner request)
- **What changed:** PR analysis has an "Also review with Gemini (<model>)" checkbox, which is the person's confirmation that the repository's code may be sent to Google (remembered per repository in localStorage). With it ticked, "Scan this pull request + AI review" scans, then calls `POST /api/scans/{id}/ai/gemini-reviews` with `acknowledge_source_sharing: true`, and shows the AI risks and test ideas in an "AI review" section with links to Risk findings and Test intelligence (`openHistory` takes a target page). Opening a stored scan shows its latest AI review. Without the checkbox nothing is sent. `gemini.py` now retries temporary failures (429/5xx, timeouts, connection errors) up to 3 attempts with 3 s / 8 s backoff and includes Google's reason in the error.
- **Tests:** `pytest tests/test_gemini.py` → 27 passed (3 new retry tests); `vitest run` → 167 passed (new `PrAnalysisGemini.test.tsx`, 5 tests); `tsc -b` ✓; `npm run e2e` → 6 passed, 1 skipped.
- **Executed against real services — PASS:** owner set `SHIPSAFE_GEMINI_MODEL=gemini-3.6-flash`. Through the UI (Playwright), PR #48 of liwan_elsokan_app: scan 27 s, Gemini review done at 56 s (one transient 503 "model is currently experiencing high demand" was retried). Gemini: block_release, 6 findings (2 critical: SSL bypass, unknown status → succeeded; 2 high: return-URL host/port, payableId; 2 medium: idempotency key, button state) and 3 test ideas, shown on PR analysis, Risk findings and Test intelligence. It missed 3 issues the manual Claude review found (resident login gate, success flag, logout token guard). Sending PR #48 to Gemini was requested by the owner.

### AI review results on Risk findings / Test intelligence — 2026-11-13 (on `Test-Branch`, uncommitted; owner report: "PR has issues but 0 found")
- **Root cause:** every static rule in `scanner.analyze_risks` applies to `.py` files only; PR #48 of liwan_elsokan_app changes 10 `.dart` files, so it had 0 static findings and therefore 0 test suggestions. Both pages showed only static results and ignored AI reviews, and said "No risk patterns detected" for code that was never analysed.
- **Fix (frontend only):** Risk findings shows the newest AI review's findings in a separate "AI review findings · UNVERIFIED AI SUGGESTIONS" section (static count unchanged); Test intelligence shows its test ideas as "AI · NOT RUN"; both pages and the Overview say how many changed files the Python-only static rules did not analyse. 4 new tests in `App.test.tsx`.
- **Executed:** PR #48 scanned through the UI (Playwright); review package downloaded through the UI; review written by Claude acting as the AI reviewer (9 findings: TLS bypass, payment status fails open to succeeded, return-URL host/port check removed, resident login gate removed, success flag ignored, idempotency key regenerated, payableId dropped, logout token race, disabled/loading button; the 10th file is a behaviour-neutral rename); imported through the UI → 9 findings, 9 test ideas shown on Claude Review, Risk findings and Test intelligence. `vitest run` → 162 passed; `tsc -b` ✓; `npm run e2e` → 6 passed, 1 skipped.
- **Not done:** no Dart static rules (static scan of Dart is still 0); test discovery is still pytest-only, so "Existing tests" finds nothing for Dart. The AI review is unverified; nothing was executed.

### Gemini AI review + Playwright e2e — 2026-11-13 (on `Test-Branch`, uncommitted; owner request)
- **What changed:** `backend/app/gemini.py` (new) calls the Gemini API server-side (`x-goog-api-key` header; key in `config.Secret`; masked out of Google error text). `config.py` reads `SHIPSAFE_GEMINI_API_KEY` and optional `SHIPSAFE_GEMINI_MODEL` (default `gemini-flash-latest`). Routes: `GET /api/ai/gemini/status`, `POST /api/scans/{id}/ai/gemini-reviews` (428 for non-demo code without `acknowledge_source_sharing: true`; 503 when not configured; Google failures mapped to 429/502/503/504 with a `code`). Gemini receives the same redacted review context as the Claude package; its answer is reshaped (identity set by ShipSafe, out-of-scan/incomplete findings dropped and counted, unknown static ids removed) and validated with the v2 import rules, then stored as `gemini_api_generated_unverified`. Claude Review page: "Review with Gemini" panel with its own per-scan sharing confirmation; Gemini reviews are labelled in the history and summary; Configuration shows the Gemini model.
- **Playwright:** `frontend/e2e/live.spec.ts` + `playwright.config.ts` (`npm run e2e`, local Chrome, needs the app running). Default run reads only; scanning a PR (`E2E_PR_REPO`, `E2E_PR_ID`) and sending it to Gemini (`E2E_GEMINI=1`) are opt-in. `@playwright/test` 1.56.1 (1.49.1 had GHSA-7mvr-c777-76hp); Vitest limited to `src/`.
- **Test PR fixture:** `d:\Ship_Safe\shipsafe-test-pr` (outside this repo, synthetic code): `main` + `feature/invoice-export` with planted defects. Not pushed: ShipSafe's Bitbucket access is read-only; the owner pushes it (instructions in its README).
- **Tests:** full backend `pytest -q` → 447 passed (15 min 25 s; started before the final 403-message change to `gemini.py`, after which `tests/test_gemini.py` was rerun alone) ; `pytest tests/test_gemini.py` → 24 passed; frontend `vitest run` → 158 passed; `tsc -b` ✓; `vite build` ✓; `npm audit` → 0; `npm run e2e` against the live app → 6 passed, 1 skipped (opt-in).
- **Executed against real services:** local scan of the test fixture → 3 static findings, risk 97 (PASS); Gemini route returned 428 without confirmation (PASS); a real Gemini call with confirmation → **FAIL / BLOCKED by Google**: HTTP 403 "The Gemini API free tier is not available for this project. … set up billing". Key is valid (model listing works). **No Gemini review has been produced by the real API yet.**
- **Not done:** no liwan_elsokan_app code was sent to Gemini (per-scan consent belongs to the owner). Bitbucket responses were slow during testing (5–12 s per call); e2e waits allow 60 s.

### Live Bitbucket mode — 2026-11-13 (on `Test-Branch`, uncommitted; owner request)
- **What changed (frontend only, no API change):** when `/api/bitbucket/status` says `configured`, the dashboard starts in **live mode**: it never requests `/api/demo`, never creates a demo scan, opens the newest **pull request** scan (if any), lists only pull request scans in Scan history, and shows Bitbucket workspace/repositories in the sidebar, top bar, Overview, Configuration and footer. The Overview's demo branch form is replaced by "Analyze a pull request", which links to the Pull requests page; the demo fixture-suite panel on Test intelligence is hidden. If Bitbucket is not configured or the status can't be read, the synthetic demo runs exactly as before. The literal `` `n `` that was rendered before `<main>` is removed.
- **Configuration:** owner's local `.env` sets `SHIPSAFE_DB_PATH` to `backend/.shipsafe-data/live-scans.db`, so live scans don't share a database with demo scans (the old `scans.db` is untouched).
- **Files:** `frontend/src/App.tsx`, `frontend/src/App.test.tsx` (live-mode helper, 4 new tests, 8 adapted), `frontend/src/bitbucket/mock.test.tsx` (mock mode now starts in live mode).
- **Tests (Node 22.13.1):** `vitest run` → 154 passed (10 files); `tsc -b` → ✓; `vite build` → ✓. Live check: API reports `configured: true` against the owner's workspace and the PR list loads (HTTP 200).
- **Real pull request scan — PASS:** `POST …/pull-requests/45/scans` with the PR's head commit → 201, stored in the live database (merge-base comparison, 1 file changed, 0 findings). The only changed file is Markdown, so 0 findings is expected (the risk rules are Python-only); its diff is cut at 140 lines and the report says so.
- **Browser check — PASS:** headless Chrome (playwright-core in a scratch folder, not added to the project) loaded Overview, Scan history and Configuration: PR #45 shown on Overview and as the only history row; no "LedgerLite", "LOCAL DEMO", "LIVE DEMO", "ShipSafe Demo" or "Synthetic demo repository" text on any of them. The only browser console error is the 404 for `/favicon.ico` (no favicon in the project; not related to this change).
- **Note:** the machine's default Node is 20.18.1, which the project does not support (`vitest` crashes on `Map.groupBy`); tests were run with nvm's 22.13.1.

### Phase 5 — done 2026-11-13 as far as it can be without the owner (Windows 11, Python from `.venv`, Node 24.22.2)
- **Task 2, evidence-based assessment:** `backend/app/assessment.py`; `GET /api/scans/{id}/assessment` (JSON) and `/assessment/report` (Markdown); "Release assessment" page (`frontend/src/ReleaseAssessmentPanel.tsx`) with both exports. States: assessment unavailable, stale, confirmed regression, tests incomplete, review required. It arranges stored evidence only, keeps static (SUSPECTED), imported AI (UNVERIFIED) and executed tests apart, lists unknowns, and never says a change is safe. With execution blocked, every commit-bound scan is "tests incomplete".
- **Task 1, UX integration:** the new page is in the primary navigation; the other screens were connected in earlier phases. No further polish was done and nothing was viewed in a browser.
- **Task 3, security:** `docs/SECURITY_ASSESSMENT.md`. No critical issue needing a code change was found. Classification: localhost-only, single trusted user (no authentication).
- **Task 4, verification:** `cd backend && ..\.venv\Scripts\python -m pytest -q` → 424 passed, 1 warning (11 min 29 s); `cd frontend && npm test` → 150 passed (10 files); `npm run build` → ✓; `npm audit` → 0. Synthetic approved regression: **BLOCKED** (controls demonstrated by `test_runner.py`).
- **Task 5, evidence:** `docs/DEMO_SCRIPT.md` (not rehearsed) and `docs/STUMP_THE_MODEL_RESULTS.md` (first prompt, interventions counted from the session, the model's errors and how they were caught; **no hidden-change evaluation was done**).
- **Task 6, optional webhooks:** not started (core gates are not all passed).
- **Gates:** 5 of 8 ticked in the Phase 5 prompt; 3 open (real Claude Code step, hidden-test findings, verified demo and human review).
- **Container runner attempt:** Docker's daemon was running (29.1.3), and the owner had said to continue all phases. Building a runner image and starting a locked-down container was **refused by the agent session's permission settings**; it was not retried or worked around. Nothing was built or started. Execution stays BLOCKED.
- **Files:** see `docs/handoffs/P5-FINAL-SESSION_HANDOFF.md`.

### Phase 4 task list (order; one task at a time)
- A. [x] Test discovery without executing code (committed `e092f9e` on `feat/p4-test-discovery`, cut from `f0fd75c`)
- B. [x] Proposed tests as untrusted data + explicit, recorded human approval, migration 3 (committed `f70e769`)
- C. [x] Runner interface that fails closed: `execution_unavailable`, run requests recorded as BLOCKED, migration 4 (committed `8dcd34a`). **Real execution in a verified isolated container is NOT built**; it needs the owner's explicit approval and a session that is permitted to start containers
- D. [ ] Baseline versus changed-commit comparison
- E. [ ] Synthetic challenge cases (LedgerLite)
- F. [ ] UI and persistence for proposals, approvals, logs, timeline

### Phase 4 task C — done 2026-11-13 (Windows 11, Python from `.venv`, Node 24.22.2) — execution status: **BLOCKED**
- **What changed:** `backend/app/runner.py` defines the runner boundary and its only implementation, `UnavailableRunner`. **The build contains no code that executes a test.** **Migration 4** (schema version is now 4) adds `test_runs`. `GET /api/tests/runner` always reports `available: false`, `status: execution_unavailable`. `POST /api/scans/{id}/tests/proposals/{pid}/runs` checks, in order: proposal exists (404), approved and not stale (409), scan is of the synthetic demo repository (403); then the runner refuses and the request is stored as a `blocked` run and answered **503 `execution_unavailable`**. A blocked run has real request time, requester name, runner identity and commits, and NULL start, end, exit code and output. A runner that claims to be available, or that fails, is blocked too ("no execution engine"). The Run button of an approved, non-stale proposal records a blocked request and shows the reason and the request history.
- **Files:** `backend/app/runner.py` (new), `db.py`, `main.py`, `proposals.py` (`RunRequest`), `backend/tests/test_runner.py` (new, 10 tests), `test_proposals.py` (its migration tests stop at migration 3), `frontend/src/TestProposalsPanel.tsx`, `TestProposalsPanel.test.tsx` (2 new tests, 1 adjusted), `types.ts`, `bitbucket.css`, `docs/MIGRATIONS.md`, `docs/ARCHITECTURE.md`, `docs/ACCEPTANCE_MATRIX.md`, `prompts/PHASE-04-REGRESSION-TESTS.md` (gates).
- **Tests:** `cd backend && ..\.venv\Scripts\python -m pytest -q` → 414 passed, 1 warning (11 min 9 s); `cd frontend && npm test` → 138 passed (9 files); `npm run build` → ✓.
- **Evidence that nothing runs:** a run request for an approved hostile proposal is served with `subprocess.run`, `Popen`, `call`, `check_output` and `os.system` replaced by functions that fail the test: none is called, the proposal's marker file is not created and the file is not in the repository. `runner.py` imports no process, file or container module (checked by a test).
- **Limits / NOT TESTED:** no test has been executed by ShipSafe, so there is **no real pass/fail evidence, no baseline-versus-head comparison and no confirmed regression**; Phase 4 gates 3 and 4 are open. Requester names are self-declared. A database at version 4 is refused by older builds. Not viewed in a browser.

### Phase 4 task B — done 2026-11-13 (Windows 11, Python from `.venv`, Node 24.22.2)
- **What changed:** **migration 3** (schema version is now 3): tables `test_proposals` and `test_proposal_decisions`, additive only. `backend/app/proposals.py` validates and stores a proposed test file as untrusted text bound to the scan's full base and head commits. Path rules: relative POSIX path of plain name segments inside a `tests` / `test` directory, file named `test_*.py` or `*_test.py`; refused are `..`, absolute paths, drives, backslashes, control characters, hidden and reserved names, `conftest.py`, non-test files, a path that already exists at the scanned commit, and a path that passes through a file or symbolic link. Content must parse as Python and contain a pytest test, at most 64 KiB; it is parsed, never run. Decisions (`approved` / `rejected`) require a name and are append-only; a proposal's status is its latest decision. A stale scan takes no new proposal and no approval. `eligible_to_run` is true only for an approved, non-stale proposal; `applied` and `executed` are always false. Routes: `GET` / `POST /api/scans/{id}/tests/proposals`, `POST …/proposals/{pid}/decisions`. The Test intelligence page lists proposals with their full content as inert text, the decision history, approve / reject with a name, and a disabled Run control labelled BLOCKED.
- **Honest limitation, shown in the UI and the API:** ShipSafe has no authentication, so the name recorded with a decision is self-declared and not verified.
- **Files:** `backend/app/db.py`, `proposals.py` (new), `main.py`, `backend/tests/test_proposals.py` (new, 80 tests), `test_migration_2.py` (its tests now stop at migration 2), `frontend/src/TestProposalsPanel.tsx` (new), `TestProposalsPanel.test.tsx` (new, 9 tests), `TestDiscoveryPanel.test.tsx` (one query scoped), `App.tsx`, `types.ts`, `bitbucket.css`, `docs/MIGRATIONS.md`, `docs/ARCHITECTURE.md`.
- **Tests:** `cd backend && ..\.venv\Scripts\python -m pytest -q` → 404 passed, 1 warning (10 min 56 s); `cd frontend && npm test` → 136 passed (9 files); `npm run build` → ✓.
- **Evidence that nothing is applied or run:** after storing and approving a hostile proposal, its marker file does not exist, the file is not in the demo repository, `git status` of the demo repository is clean, and the only processes started were Git commands (none of `apply`, `commit`, `checkout`, `pytest`, `python`). A separate test checks that `proposals.py` imports no process, file or import machinery and never calls `open`, `exec`, `eval` or `compile`.
- **Limits / NOT TESTED:** a database at version 3 is refused by builds that know only version 2. No authentication (above). The symbolic-link check relies on Git listing a link as a file at the scanned commit; it says nothing about a future workspace, which must check again before writing. Bitbucket path for proposals is covered only through the shared helper, not with its own mocked test. Not viewed in a browser. **No test has been run by ShipSafe.**

### Phase 4 task A — done 2026-11-13 (Windows 11, Python from `.venv`, Node 24.22.2)
- **What changed:** `backend/app/discovery.py` finds existing pytest tests for a scan's change by reading test files (`test_*.py`, `*_test.py`) at the scan's head commit and parsing them with `ast`. It never imports, collects or runs them. A test is a candidate when its file imports a changed module; it ranks higher when its body mentions a changed function. Changed files that no test file imports (and all non-Python files) are listed as coverage gaps with their static and imported-AI findings. The selection rules are returned with the result. `GET /api/scans/{id}/tests/discovery` serves it for local scans and, through the read-only Bitbucket provider (at most 60 test files), for pull request scans. Nothing is stored. The Test intelligence page shows the result in a new panel labelled NOT RUN.
- **Files:** `backend/app/discovery.py` (new), `backend/app/main.py`, `backend/tests/test_discovery.py` (new, 23 tests), `test_bitbucket_api.py` (2 tests), `frontend/src/TestDiscoveryPanel.tsx` (new), `TestDiscoveryPanel.test.tsx` (new, 8 tests), `App.tsx`, `types.ts`, `bitbucket.css`, `docs/ARCHITECTURE.md`.
- **Tests:** `cd backend && ..\.venv\Scripts\python -m pytest -q` → 324 passed, 1 warning; `cd frontend && npm test` → 127 passed (8 files); `npm run build` → ✓.
- **Evidence that nothing executes:** a hostile test file whose module-level code would write a marker file and exit is parsed and listed; the marker is not created, `exec` / `eval` / `subprocess` / `os.system` are not called, and the file is not imported. A second test checks that the module itself does not import `subprocess`, `importlib`, `runpy`, `os` or `pytest`, nor call `exec` / `eval` / `compile`.
- **Limits / NOT TESTED:** heuristic only: indirect imports, `conftest.py` fixtures, relative and dynamic imports are not followed; parametrized cases are not expanded; a candidate is not known to cover the change. Not viewed in a browser. Mocked Bitbucket only. **No test of any repository has been run by ShipSafe.**

### Phase 3 task list (order; one task at a time)
1. [x] Trusted identity + minimal review package (committed `d0d19d2` on `feat/p3-review-package`, cut from `74661f4`)
2. [x] Claude Code review prompt/schema v2 (committed `779932e`)
3. [x] Strict import and history (committed `dd4c6db`)
4. [x] Functional UX (committed `73a658c`)
5. [x] Operating model documentation for the Team subscription, gates and matrix from executed evidence, session handoff (**uncommitted** on `feat/p3-review-package`)

**Phase 3 state:** all five tasks are implemented; five of six acceptance gates are ticked in `prompts/PHASE-03-CLAUDE-REVIEW.md`. The gate "a developer can import a well-formed review from their Claude Code session" is **NOT TESTED** (synthetic JSON fixtures only). Phase 3 is not tagged and not merged. Handoff: `docs/handoffs/P3-CLAUDE-REVIEW-SESSION_HANDOFF.md`.

**Phase 4 readiness (checked 2026-11-13 on the owner's Windows machine):** `docker.exe` is installed (Docker Desktop) but the daemon was not running, so no isolated runner was available at that moment; `podman` is not installed; `wsl.exe` exists. Phase 4 has not been started. Per `CLAUDE.md`, repository tests must never run on the host; without a verified isolated runner the Run action must fail closed (BLOCKED).

### Phase 3 task 5 — done 2026-11-13 (documentation and evidence only)
- **What changed:** `docs/CLAUDE-CODE-HANDOFF.md` gained "Operating model for a company Team subscription" and a "Source-export review checklist"; `docs/ACCEPTANCE_MATRIX.md` Phase 3 rows filled from the executed runs (with what is not covered); gates ticked in the Phase 3 prompt; `docs/handoffs/P3-CLAUDE-REVIEW-SESSION_HANDOFF.md` written.
- **Evidence gathered for the "no API key / no execution" gate:** code search of 32 application source files: no `anthropic` / Claude API reference; process execution only in `local_git.py` and `demo_seed.py` (Git commands, since Phase 1); `proposed_patch` appears only in the schema, instructions and template.
- **No code changed;** no test re-run was needed (last runs: backend 299 passed, frontend 119 passed, build ✓).

### Phase 3 task 4 — done 2026-11-13 (Windows 11, Node 24.22.2; frontend only)
- **What changed (Claude Review page, `frontend/src/App.tsx`):** "Previous reviews" table from `GET …/ai/reviews/history` (imported time, this scan or earlier scan with its head commit, suggestion, finding count, stale badge, Show); falls back to this scan's reviews if the route cannot be read. The newest review of the scan on screen is shown by default; a review of an earlier scan is shown only when picked, with the stale warning and a line saying it does not describe the scan on screen. "Static scan and imported review, side by side" panel: static suspicions and imported findings labelled apart, linked through `related_static_finding_ids`, with "Test evidence: none". The import result (success, or the API's reason for 409 / 413 / 422, or the local size refusal) is shown next to the import control instead of the page banner.
- **Files:** `frontend/src/App.tsx`, `App.test.tsx` (12 new tests, 4 adjusted because a finding title now appears twice), `types.ts` (`current_scan`), `bitbucket.css`, `test/setup.ts` (`Blob.text` for jsdom, test environment only).
- **Tests:** `cd frontend && npm test` → 119 passed (7 files); `npm run build` → ✓ (240.00 kB JS). Backend not re-run: no backend file changed since the 299-passed run of task 3.
- **Limits / NOT TESTED:** not viewed in a real browser (layout, narrow screens); the file upload was exercised in jsdom with a stubbed API only; no real Claude Code review was imported. `App.tsx` was not split into a separate page component.

### Phase 3 task 3 — done 2026-11-13 (Windows 11, Python from `.venv`, Node 24.22.2)
- **What changed:** a review already imported for a scan is refused (409; compared by a digest of the review content, so key order and whitespace do not matter). Every served review carries `scan_id` and `scan_binding` (the scan's binding, read at response time, never stored in the review): when a pull request's head moves, the scan and therefore its reviews show as stale. New route `GET /api/scans/{id}/ai/reviews/history`: reviews across all stored scans of the same pull request, each with its own scan's binding and `current_scan`. A review made for an older scan is refused for a newer scan of the same pull request. The Claude Review page shows a "This review is stale" warning with the commit the review was made for.
- **Already enforced before this task (now pinned by tests):** schema version, size and types, scan id, digest, head commit, unknown paths, missing and extra fields; rejected imports leave no row; history keeps every import with its timestamp; the stored scan report is byte-for-byte unchanged.
- **No migration:** the existing `ai_reviews` table was enough. Schema version stays 2.
- **Contract change:** review responses gained `scan_id` (already present) and `scan_binding`; `test_migration_2.py` was updated for it.
- **Files:** `backend/app/main.py`, `ai_handoff.py` (`review_content_digest`), `backend/tests/test_review_import_history.py` (new, 14 tests), `test_bitbucket_api.py` (1 test), `test_migration_2.py`, `frontend/src/types.ts`, `App.tsx`, `App.test.tsx` (2 tests), `docs/ARCHITECTURE.md` (also repaired a table that the task 1 edit had split).
- **Tests:** `cd backend && ..\.venv\Scripts\python -m pytest -q` → 299 passed, 1 warning (a first full run had 1 failure, `test_migration_2`, which pinned the old review response shape; the test was updated and the full suite re-run). Frontend: `npm test` → 107 passed (7 files); `npm run build` → ✓.
- **Limits / NOT TESTED:** stale state is only as fresh as the last pull request list, detail or scan call; review routes never ask Bitbucket. The duplicate check reads all reviews of the scan (bounded in practice, not by a limit). Synthetic fixtures and mocked Bitbucket only; not viewed in a browser.

### Phase 3 task 2 — done 2026-11-13 (Windows 11, Python from `.venv`, Node 24.22.2)
- **What changed:** review schema `shipsafe.ai-review.v2`. Each finding has `id` (unique in the review), `status` fixed to `"suspected"`, `suggested_validation`, optional `proposed_patch` (stored as text, never applied). The review has `reviewed_source` (provider, repository, pull request, head commit; must equal the scan's, else 409) and `missing_context`. The response template now asks for v2 with the binding pre-filled; v1 reviews are still accepted. The instructions name the review areas (security, authorization, API compatibility, money/data integrity, validation, exception handling, affected modules, missing tests) and forbid claims of executed commands or tests. Neither schema can express "verified", test results or commands run (rejected, 422).
- **Bug found and fixed while building it:** the echoed identity was first named `source` and overwrote the saved review's provenance marker (`source: user_imported_json_unverified_provenance`). It is `reviewed_source`; tests assert the marker survives and cannot be supplied.
- **UI:** the Claude Review cards show the finding id, a SUSPECTED · UNVERIFIED pill, "How to validate (not done)", the proposed patch as inert text labelled unverified and not applied, and "Context the reviewer did not have".
- **Files:** `backend/app/ai_handoff.py`, `backend/app/main.py`, `backend/tests/test_review_schema_v2.py` (new, 27 tests), `test_bitbucket_api.py` (1 test), `frontend/src/types.ts`, `App.tsx`, `App.test.tsx` (2 tests), `bitbucket.css`, `docs/CLAUDE-CODE-HANDOFF.md`.
- **Tests:** `cd backend && ..\.venv\Scripts\python -m pytest -q` → 284 passed, 1 warning; `cd frontend && npm test` → 105 passed (7 files); `npm run build` → ✓.
- **Limits / NOT TESTED:** only synthetic JSON fixtures; no real Claude Code session has produced a v2 review, so whether Claude follows the instructions and template is unverified. Not viewed in a browser.

### Phase 3 task 1 — done 2026-11-13 (Windows 11, Python from `.venv`, Node 24.22.2)
- **What changed:** the review package (`GET /api/scans/{id}/ai/handoff`) now carries `review_context.source` (provider, repository, pull request, full base and head commits, comparison) and the context digest covers it; a `PACKAGE.json` manifest (format `shipsafe.review-package.v2`, new package id per export, digest, incomplete / omitted / truncated counts); best-effort secret redaction of patches and finding evidence, reported as a limitation; a 1 MiB context limit that drops the largest patches and marks them; HTTP 428 unless `acknowledge_source_sharing=true` for any scan that is not the synthetic demo; `GET …/ai/context` adds `acknowledgement_required`. The dashboard's Claude Review page shows a confirmation checkbox when required (also when it cannot tell).
- **Contract change (deliberate):** the context digest of every scan changed because it now includes the identity. A package exported before this change is refused on import (409, "export a fresh handoff bundle"). Review JSON schema is still `shipsafe.ai-review.v1`.
- **Files:** `backend/app/ai_handoff.py`, `backend/app/main.py`, `backend/tests/test_review_package.py` (new, 19 tests), `test_bitbucket_api.py` (one test replaced by three, one call updated), `test_ai_handoff.py` (ZIP now has 4 entries), `frontend/src/App.tsx`, `App.test.tsx` (3 tests), `bitbucket.css`, `docs/ARCHITECTURE.md`, `docs/CLAUDE-CODE-HANDOFF.md`.
- **Tests:** `cd backend && ..\.venv\Scripts\python -m pytest -q` → 257 passed, 1 warning; `cd frontend && npm test` → 103 passed (7 files); `npm run build` → ✓.
- **Limits / NOT TESTED:** only synthetic JSON fixtures were imported; no real Claude Code session was run. Redaction is pattern-based and will miss secrets it has no pattern for. The package id is not stored. Bitbucket evidence is mocked HTTP only. Not viewed in a browser.
- **Branch / latest commit:** (remote state verified with `git ls-remote origin` on 2026-11-13)
  - GitHub has **no `main` branch**. The default and integration branch is `feat/p1-foundation`, at `98c9d92`, which is the merge of pull request #1 (`feat/p2-bitbucket-provider`, P2 task 1). The rule files name it accordingly.
  - On GitHub, stacked on `08b3b1b`, none merged: `feat/p2-bitbucket-settings` (`ebc9068`, task 2) → `feat/p2-migration-2` (`82d14ed`, task 3) → `feat/p2-bitbucket-api` (`790b293`, task 4). Pushed by the owner on 2026-11-12.
  - **Working branch: `feat/p2-frontend-pr-screens`** (HEAD `11d057f` "Merge Phase 2 work into main", which contains milestones 1–4). Milestones 5–7 of task 5 (Pull Requests screen, PR Analysis screen, mock mode) were committed on this branch on 2026-11-13 with the owner's approval (local only, not pushed).
  - Earlier note, kept for history: `feat/p2-frontend-screens`, cut from `790b293`. Milestone 1 (frontend toolchain and test setup, `1851b6f`) and milestone 2 (`truncated` flag on the pull request list, `3bf1fbd`) milestone 3 (types, API helper, stale logic and badge, `4a4eeb3`) and milestone 4 (Bitbucket navigation, connection status, Repositories screen, branch head) are committed.

### Completed and verified
- Baseline v0.2 ("Phase 0") — imported as `10f3cee`.
- Phase 1 — complete on `feat/p1-foundation`, the repository's default branch. Not tagged; human review is still open.
- Agent handoff system installed 2026-11-12: `AGENTS.md`, entry section in `CLAUDE.md`, this checkpoint, `NEXT_AGENT_PROMPT.md`.
- P2 task 1 — read-only Bitbucket Cloud provider, mocked HTTP only. `08b3b1b`.
- P2 task 2 — Bitbucket settings and credential loading. `ebc9068`.
- P2 task 3 — migration 2 and storage helpers. `82d14ed`.
- P2 task 4 — Bitbucket API: repository list, pull request list and detail, pull request scan bound to merge base and head, stale detection with `stale_checked`, `binding` in scan responses, published example responses. 41 new tests, mocked HTTP only. Contract accepted by the owner on 2026-11-12 as the initial contract for task 5, subject to frontend integration validation.

### Phase 2 task list (order; one task at a time)
1. [x] Bitbucket Cloud provider + mocked-HTTP tests
2. [x] Bitbucket settings and credential loading
3. [x] Migration 2: provider / repository / PR / full base+head SHA columns, stale marker
4. [x] API: list repositories, list PRs, scan a PR bound to exact SHAs, stale detection
5. [x] Frontend: Repositories, Pull Requests, PR Analysis screens with typed client (code and tests done and committed 2026-11-13; not yet viewed in a real browser)
   - [x] Milestone 1: toolchain (Vite 6.4.6, Vitest 5.1.0, Testing Library), `npm test`, smoke test of the demo dashboard
   - [x] Milestone 2: `truncated` flag on the pull request list (approved backend change), 7 new backend tests
   - [x] Milestone 3: typed contracts (`types.ts`), API helper with `ApiError` (`api.ts`), stale logic and `StaleBadge` (`bitbucket/`), 32 new frontend tests
   - [x] Milestone 4: Bitbucket navigation group, connection status, Repositories screen, 29 new frontend tests
   - [x] Milestone 5: Pull Requests screen (repository picker, state filter, search, truncated notice, stale badge, Analyze, Open in Bitbucket), 13 tests
   - [x] Milestone 6: PR Analysis screen (pull request facts, scan with `head_commit`, `head_changed` reload, stored scans, bound full SHAs, findings, diff); history rows marked for pull request scans; "Open in dashboard"; 15 tests
   - [x] Milestone 7: development mock mode (`npm run dev:mock`, permanent MOCK DATA banner, canned data absent from the production bundle), 7 tests; README line
6. [ ] Human-run read-only live smoke test (PASS or BLOCKED), docs, gates

### Current working state
- **Functional now (backend):**
  - Routes, all documented in `docs/ARCHITECTURE.md` ("Bitbucket routes"): `GET /api/bitbucket/status`, `GET /api/bitbucket/repositories`, `GET /api/bitbucket/repositories/{slug}/pull-requests`, `GET …/pull-requests/{id}`, `POST …/pull-requests/{id}/scans`.
  - A pull request scan compares merge base → head, stores the report with `provider`, `repository_id`, `pull_request_id` and both full SHAs, and returns the report with `binding`.
  - Stale: earlier scans of a pull request are marked when its head moves (on list for up to 20 scanned pull requests, on detail, on scan) and unmarked if the head returns. Every `binding` says with `stale_checked` whether that response actually compared with Bitbucket; stored-scan routes never do.
  - `binding` (`provider, repository_id, pull_request_id, base_commit, head_commit, comparison, stale, stale_at, stale_checked`) is returned by `POST /api/scans`, `GET /api/scans`, `GET /api/scans/{id}`, and the export. The stored report, handoff ZIP and review digest do not contain it.
  - Errors from Bitbucket routes are `{"detail": string, "code": string}`; 503 `bitbucket_not_configured` when the server has no Bitbucket settings.
  - Import analysis over Bitbucket is capped at 200 file reads; a cut report says so in `summary` (two keys present only when cut; approved) and in the handoff limitations.
  - Contract for task 5: `docs/ARCHITECTURE.md` → "Bitbucket routes" (shapes, nullability, error kinds, stale reading table, the 20-lookup limit), plus `docs/example-bitbucket-responses.json` (mock data), guarded against drift by a test.
  - Provider additions: `merge_base()`, `PullRequestNotFound`, `ChangeTooLarge` (HTTP 555).
  - Earlier tasks: settings with `config.Secret`, schema version 2, `db.insert_scan`, `db.sync_stale`.
- **Functional now (frontend, task 5):** sidebar BITBUCKET group (Repositories, Pull requests); Pull requests → Analyze → PR analysis → scan → findings, diff, bound commits, stale badge, Open in Bitbucket. A pull request scan opened with "Open in dashboard" uses the existing pages (export, Claude review); those pages then show a "Scan source" panel (repository, PR, full commits, stale badge) and Bitbucket labels instead of the demo labels (2 regression tests in `App.test.tsx`).
- **Not wired:** the Claude handoff ZIP does not carry the binding (Phase 3).
- **Changed files (task 4 commit on `feat/p2-bitbucket-api`):**
  - `backend/app/main.py` — Bitbucket routes, error mapping, `binding` in scan responses, `stale_checked`, `create_app(bitbucket=)` test seam
  - `backend/app/db.py` — `binding`, `pull_request_scans`, `scanned_pull_requests`
  - `backend/app/providers/bitbucket.py` — `merge_base()`; two errors made specific (nothing else changed)
  - `backend/app/errors.py` — `PullRequestNotFound`, `ChangeTooLarge`
  - `backend/app/scanner.py` — `max_import_reads` bound and the two truncation summary keys
  - `backend/app/ai_handoff.py` — `INCOMPLETE` limitation line when import analysis was cut
  - `backend/tests/test_bitbucket_api.py` — new, 41 tests
  - `docs/example-bitbucket-responses.json` — new, captured from the mocked fixtures (generator kept outside the repository; regenerate when the contract changes)
  - `backend/tests/test_foundation.py`, `test_migration_2.py` — three assertions updated because scan responses now include `binding`
  - `AGENTS.md`, `CLAUDE.md`, `docs/TEAM_WORKFLOW.md`, `docs/TEAM_START_HERE.md` — only the outdated `main` branch references corrected (owner-approved); no other rule changed
  - `README.md`, `.env.example`, `docs/ARCHITECTURE.md`, `CONFIGURATION.md`, `MIGRATIONS.md`, `DECISIONS.md`, `ACCEPTANCE_MATRIX.md`, `IMPLEMENTATION_STATUS.md`, `NEXT_AGENT_PROMPT.md`
- **Tests (2026-11-12, Linux cloud container, Python 3.13.18, fresh virtualenv from `backend/requirements.txt`):**
  - `cd backend && python -m pytest -q tests/test_bitbucket_api.py` → 41 passed
  - `cd backend && python -m pytest -q` → 229 passed, 1 warning (188 after task 3 + 41 new)
  - Two deliberate breakages were caught by the new tests (target tip used instead of merge base: 11 failures; stale refresh removed from the list route: 1 failure), then reverted.
  - `cd frontend && npm ci && npm run build` → ✓ built (198.79 kB JS; no frontend source changed)
- **Frontend toolchain milestone (2026-11-13, Linux cloud container, on `feat/p2-frontend-screens`):**
  - Node 22.23.4 / npm 10.9.9: `npm ci` (no flags) exit 0; `npm test` → 2 passed; `npm run build` → ✓ built (200.11 kB JS); `npm audit` → 0 vulnerabilities; `npm ls --all` → no invalid, missing or extraneous packages.
  - Node 24.22.1 / npm 11.19.1: `npm ci`, `npm test` (2 passed), `npm run build`, `npm audit` (0) all pass; the lock file is not modified. npm 11 prints an "install-scripts" notice for esbuild's postinstall; the build still works.
  - Scripted headless-browser run of the demo (overview, all pages, findings, diff, two new scans, history, handoff ZIP, `/api` proxy): identical results on Vite 5.4.21 and Vite 6.4.6.
  - `cd backend && python -m pytest -q` → 229 passed (unchanged; only an error message in `scripts/dev.py` changed outside the frontend).
  - **Not verified:** Node 20 (unsupported from now on), `vite preview`.
  - **OUTSTANDING — Windows verification of the toolchain milestone (`1851b6f`): NOT TESTED.** The agent session could not run commands on the owner's machine. To do, in `frontend` on Windows with Node 22.12+ or 24+: `npm ci`, `npm test` (expect 2 passed), `npm run build`, `npm audit` (expect 0); then `python scripts\dev.py` and a walk through the demo.
- **Milestones 5–7 — Pull Requests, PR Analysis, mock mode (2026-11-13, Windows 11, Node 24.22.2, Python from `.venv`; on `feat/p2-frontend-pr-screens`):**
  - `cd frontend && npm test` → 100 passed (7 files); `npm run build` → ✓ built (231.88 kB JS, 38.56 kB CSS); `npm audit` → 0 vulnerabilities
  - `cd backend && ..\.venv\Scripts\python -m pytest -q` → 236 passed, 1 warning (no backend change)
  - Production bundle searched for the canned data (`mock-workspace`, `Mock Ledger`, `Mock finding`, the banner text): 0 occurrences. The only "MOCK DATA" string left is the pill label in the report header.
  - Changed files: `frontend/src/App.tsx`, `App.test.tsx`, `components.tsx` (new; presentational pieces moved out of `App.tsx` unchanged), `bitbucket.css`, `bitbucket/BitbucketSection.tsx`, `client.ts`, `pages.ts`, `ErrorPanel.tsx`, `PullRequestsPage.tsx` (+test), `PrAnalysisPage.tsx` (+test), `mock.ts` (+test), `test/fixtures.ts`, `frontend/package.json` (`dev:mock` script), `README.md`.
  - **NOT TESTED:** the new screens in a real browser (real backend or `npm run dev:mock`), narrow-screen layout, live Bitbucket. All evidence is jsdom with stubbed `fetch` or the in-memory mock.
  - First Windows run of the frontend toolchain: `npm test`, `npm run build` and `npm audit` pass on Windows 11 / Node 24.22.2 (`npm ci` and the `scripts\dev.py` demo walk were not repeated).
- **Milestone 4 — navigation, connection status, Repositories screen (2026-11-13, Linux cloud container, Node 22.23.4):**
  - `cd frontend && npm test` → 63 passed (4 files); `npm run build` → ✓ built (209.71 kB JS, 35.63 kB CSS); `npm audit` → 0
  - Headless browser against the real backend with Bitbucket not configured: the Repositories page shows the setup message and the navigation entry is tagged "Off". Configured, error and narrow-screen states were viewed with the two Bitbucket routes intercepted in the browser (mock answers), because no Bitbucket credential exists. No request went to Bitbucket.
  - Scripted run of the demo on a fresh database: identical to the Vite 5 baseline.
  - Not run on Windows. Not seen against live Bitbucket.
- **Milestone 3 — types, API helper, stale logic (2026-11-13, Linux cloud container, Node 22.23.4):**
  - `cd frontend && npm test` → 34 passed (3 files); `npm run build` → ✓ built (200.48 kB JS); `npm audit` → 0
  - Scripted headless-browser run of the demo: identical to the Vite 5 baseline (the API helper was moved out of `App.tsx`; the smoke test and the type check caught a missed `API` reference before commit)
  - Not run on Windows.
- **`truncated` milestone (2026-11-13, Linux cloud container, Python 3.13.18):**
  - `cd backend && python -m pytest -q tests/test_bitbucket_api.py tests/test_bitbucket_provider.py` → 86 passed (45 + 41)
  - `cd backend && python -m pytest -q` → 236 passed, 1 warning (229 + 7 new)
  - `cd frontend && npm test` → 2 passed; `npm run build` → ✓ built (no frontend change in this milestone)
  - **Not re-run on Windows** since `08b3b1b`. **Live Bitbucket: NOT TESTED.**

### Blockers / known issues
- **Nothing after `08b3b1b` is on GitHub** (no credential in the agent session). Tasks 2, 3 and 4 are committed locally and delivered to the owner as a Git bundle.
- **Live Bitbucket: NOT TESTED.** No request has ever left the machine for `api.bitbucket.org`. Payload shapes and the `merge-base` endpoint come from Bitbucket's published API description, not from observed responses. Task 6 must confirm them.
- Response shapes for the Bitbucket routes were designed by the backend agent and reviewed by the owner; the frontend owner has not confirmed them. The backend has no Pydantic response models, so Swagger does not show them.
- Three error body kinds exist (Bitbucket `{detail, code}`, validation 422 list, unmatched route 404); local scan routes have no `code`.
- `docs/TEAM_START_HERE.md` still shows `git init -b main` in its from-scratch setup example; left as is because it describes creating a new repository, not this one.
- **Stale state is not always live.** The pull request list re-checks at most 20 scanned pull requests per request (up to about 60 extra Bitbucket requests, no overall time budget); beyond that, and on every stored-scan route, `stale_checked` is false and the UI must show "not checked", never "current". A pull request whose head became unreadable cannot be checked at all. Persisting a "last checked at" time would need migration 3 (not planned).
- Fork pull requests and pull requests whose branch commits cannot be read are refused (409), by decision.
- HTTP 555 fails the scan (422); no per-file fallback.
- Local scans still cap import analysis silently at the first 250 tree entries (unchanged, pre-existing).
- A scan of a large pull request makes many sequential Bitbucket requests inside one HTTP request (up to about 200 file reads plus one per changed Python file per side); there is no progress reporting or background job.
- A database opened by this code is version 2 and is refused by older branches; use a separate `SHIPSAFE_DB_PATH` when switching back.
- The provider's HTTP client is never closed (it lives for the whole process).

### Next exact task
- **Open for Phase 2:** a browser walk-through: `cd frontend && npm run dev:mock` (Pull requests → Analyze #101 → scan; #106 shows the head-changed reload, #104 the fork refusal, #105 the oversized diff), and `python scripts\dev.py` to confirm the demo and the "Bitbucket is not configured" state.
- **Then (P2 task 6):** human-run read-only live smoke test against Bitbucket with approved credentials set only in the server's local `.env` (PASS or BLOCKED); record observed payload differences; update docs and gates. An agent must not ask for or handle the token.
- **Task 5 reference (done):** Frontend — Repositories, Pull Requests, and PR Analysis screens against the task 4 routes, with a typed client.
- **Likely files:** `frontend/src/types.ts` (add `Binding`, `BitbucketRepository`, `PullRequestListItem`, `PullRequestDetail`, `PullRequestScan`, optional `binding` on `Report`/`ScanHistory`, the two optional summary keys), `frontend/src/App.tsx`, `frontend/src/styles.css`.
- **Done when:** the dashboard lists approved repositories and their pull requests, scans a pull request and shows its diff and findings, shows the bound commits, a stale badge and an "Open in Bitbucket" link, handles loading, empty, error and "Bitbucket not configured" (503 `bitbucket_not_configured`) states, sends `head_commit` with the scan request and handles 409 `head_changed`; any mock data is labelled as mock; `npm run build` passes; the existing demo flow is unchanged.
- **Decided (owner, 2026-11-12/13):** Vitest with Testing Library (installed in milestone 1); development-only fixture mock mode with a permanent "MOCK DATA" banner; a `truncated` flag on the pull request list; new files under `frontend/src/bitbucket/`; Playwright end-to-end deferred until after task 6. Response shapes are accepted as the initial contract, subject to integration.
- **Avoid:** backend contract changes without recording them; any Bitbucket write; putting a credential in a `VITE_*` variable.

### Deferred (existing roadmap only)
Phase 3 Claude review binding (including the binding in the handoff ZIP), Phase 4 isolated test runner, Phase 5 release assessment — see `prompts/`.

## Capability table

Verified on branch `feat/p1-foundation` on 2026-11-11 and re-verified on 2026-11-12 after the independent-review remediation (Windows 11, Python 3.12.4, Node 24.22.2; 101 backend tests, `npm run build`, all six demo branches driven through the dashboard). **These statuses describe an unmerged branch.** The integrator confirms or corrects them after merge.

Labels: IMPLEMENTED (code and passing tests exist), PARTIAL (works within stated limits), NOT IMPLEMENTED (no code), NOT TESTED (code exists, not exercised).

| Capability | Status | Evidence or limit | Planned phase |
|---|---|---|---|
| Local Git diff scanning through the API | IMPLEMENTED | `backend/tests`; live HTTP run recorded in the Phase 1 session handoff | Maintain |
| Synthetic LedgerLite fixture (main + 6 branches) | IMPLEMENTED | `test_scanner.py`; interrupted-seed repair in `test_phase1_regressions.py` | Maintain |
| Deny-by-default path allowlist | IMPLEMENTED | `test_foundation.py`, `test_phase1_regressions.py`, `test_phase1_remediation.py` (redirecting `.git` files, demo-dir drive root) | Maintain |
| Loopback-only API: bind, CORS, Host-header check | IMPLEMENTED | `test_phase1_remediation.py`; live check through the Vite proxy | Maintain |
| Literal file names; no repository-defined command runs during a scan | IMPLEMENTED | `test_phase1_remediation.py` (hostile tree names, armed config/hooks) | Maintain |
| Python AST and rule findings | PARTIAL | Three heuristics tuned to the demo; Python only; absolute imports only | Phase 5 hardening |
| Diff display | PARTIAL | First 140 lines per file; first 300 files. Both limits are reported (`summary.truncated`, `files_omitted`, per-file `diff_truncated`), shown in the UI, and stated in the handoff ZIP | Raise or make configurable in Phase 2 or 5 |
| SQLite scan and review history | IMPLEMENTED | Survives restart (`test_scans_and_reviews_survive_an_application_restart`, live restart check) | Maintain |
| Schema migration runner | IMPLEMENTED | `db.migrate`; version 1 equals the v0.2 schema, version 2 adds scan binding columns. Adoption, rollback, and fail-closed tests in `test_foundation.py` and `test_migration_2.py` | Maintain |
| Claude ZIP export and strict JSON import (manual) | IMPLEMENTED | `test_ai_handoff.py`; live export/import round trip | Phase 3 extends |
| React dashboard: production build | IMPLEMENTED | `npm run build` passes after the Phase 1 fix; it failed on the v0.2 baseline | Maintain |
| React dashboard: behaviour in a browser | PARTIAL | Scripted headless-Chrome runs passed: default scan, all pages, review import, restart (2026-11-11); all six demo branches scanned from the UI with export JSON and handoff ZIP verified per scan (2026-11-12, 33 checks). No human click-through, no visual or layout check, no frontend tests in the repository | Human check before merge |
| Dashboard UI for scanning a non-demo repository | NOT IMPLEMENTED | API only (`repository_path`) | Phase 2 |
| Provider interfaces (repository, PR, change, orchestration) | IMPLEMENTED | `providers/base.py`; exercised by a local and an in-memory provider | Phase 2 builds on these |
| Pull-request discovery | PARTIAL | Backend routes over `BitbucketCloudProvider` (`test_bitbucket_api.py`, `test_bitbucket_provider.py`, mocked HTTP). No dashboard screen; never run against live Bitbucket | Phase 2 |
| Bitbucket Cloud repository and PR discovery | PARTIAL | `GET /api/bitbucket/repositories` and `…/pull-requests` (mocked HTTP only); no UI; never run against live Bitbucket | Phase 2 |
| Bitbucket settings and credential loading | IMPLEMENTED | `test_bitbucket_settings.py` (32 tests): all-or-nothing variables, `ConfigError` on partial or malformed values, token absent from `repr`, logs, and every GET route. Unmerged (2026-11-12, `feat/p2-bitbucket-settings`); the provider it builds is used by no route | Phase 2 |
| Commit-scoped Bitbucket scans and stale detection | PARTIAL | Backend complete against mocked HTTP: pull request scan bound to merge base and head full SHAs, stale marking, `binding` in responses (`test_bitbucket_api.py` 35 tests, `test_migration_2.py`). No UI; live NOT TESTED (2026-11-12, `feat/p2-bitbucket-api`) | Phase 2 |
| Automated Claude or other model invocation | NOT IMPLEMENTED | By design; handoff is manual | Not planned |
| Secure regression test runner | NOT IMPLEMENTED | No repository code is ever executed | Phase 4 |
| Test patch approval and execution | NOT IMPLEMENTED | | Phase 4 |
| Evidence-based release assessment | NOT IMPLEMENTED | Only the heuristic score and JSON export exist | Phase 5 |
| Authentication, roles, multi-user | NOT IMPLEMENTED | Loopback-only development API | Phase 5 assessment |
| Webhooks and CI gating | NOT IMPLEMENTED | | Not scheduled |

Update this table only after integration and verification.
