# Implementation status

## Checkpoint — living, updated after every task

Rules: `AGENTS.md` and `CLAUDE.md`. Handoff prompt: `NEXT_AGENT_PROMPT.md`.

- **Roadmap:** `prompts/PHASE-01-FOUNDATION.md` … `PHASE-05-FINAL-VALIDATION.md`; gates in `docs/ACCEPTANCE_MATRIX.md`
- **Current phase:** 2 — Bitbucket repositories and pull requests (`prompts/PHASE-02-BITBUCKET.md`)
- **Last updated:** 2026-11-13
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
