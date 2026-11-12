# Implementation status

## Checkpoint — living, updated after every task

Rules: `AGENTS.md` and `CLAUDE.md`. Handoff prompt: `NEXT_AGENT_PROMPT.md`.

- **Roadmap:** `prompts/PHASE-01-FOUNDATION.md` … `PHASE-05-FINAL-VALIDATION.md`; gates in `docs/ACCEPTANCE_MATRIX.md`
- **Current phase:** 2 — Bitbucket repositories and pull requests (`prompts/PHASE-02-BITBUCKET.md`)
- **Last updated:** 2026-11-12
- **Branch / latest commit:** `feat/p2-bitbucket-provider` at `08b3b1b` (committed and pushed; holds P2 task 1 and the handoff system), stacked on `feat/p1-foundation` at `9ed331c`. P2 task 2 is committed on `feat/p2-bitbucket-settings`, cut from `08b3b1b` (the branch head is the task 2 commit; commit and push were authorized by the owner on 2026-11-12).

### Completed and verified
- Baseline v0.2 ("Phase 0") — imported as `10f3cee`.
- Phase 1 — complete on `feat/p1-foundation` (101 backend tests, frontend build; see matrix). **Not merged to `main`, not tagged**; human review is still open.
- Agent handoff system installed 2026-11-12: `AGENTS.md`, entry section in `CLAUDE.md`, this checkpoint, `NEXT_AGENT_PROMPT.md`.
- P2 task 1 — read-only Bitbucket Cloud provider (`backend/app/providers/bitbucket.py`) implementing all three provider protocols. Mocked HTTP only. Committed in `08b3b1b`.
- P2 task 2 — Bitbucket settings and credential loading. `config.load_settings` reads the four `SHIPSAFE_BITBUCKET_*` variables; `create_app` builds the provider only when configured. 32 new tests.

### Phase 2 task list (order; one task at a time)
1. [x] Bitbucket Cloud provider + mocked-HTTP tests
2. [x] Bitbucket settings and credential loading
3. [ ] Migration 2: provider / repository / PR / full base+head SHA columns, stale flag (**next**)
4. [ ] API: list repositories, list PRs, scan a PR bound to exact SHAs, stale detection
5. [ ] Frontend: Repositories, Pull Requests, PR Analysis screens with typed client
6. [ ] Human-run read-only live smoke test (PASS or BLOCKED), docs, gates

### Current working state
- **Functional now:**
  - `BitbucketCloudProvider` — allowlisted repository discovery with pagination, PR list/detail with full-SHA binding, ref resolution, two-dot change sets with per-file patches, tree listing, file reads; auth (Bearer token, or Basic e-mail + API token), 401/403/404/429/5xx/555, timeouts, bounded retries, byte and page caps. `scan_changes()` produces a report from it.
  - Settings: `Settings.bitbucket` is `None` unless `SHIPSAFE_BITBUCKET_WORKSPACE`, `_REPOSITORIES`, `_TOKEN` are all set (`_EMAIL` optional). Partial, blank-list, bad-slug, or unsendable-token configurations raise `ConfigError` (variable names only in the message). The token is a `config.Secret`: hidden in `repr`/`str`, refuses `asdict`, JSON, pickle.
  - Startup: `create_app` builds the provider into `app.state.bitbucket` (else `None`). No request is sent at startup; a wrong token is found only on first use.
- **Not wired:** no API route, no UI, no database column uses the provider. `app.state.bitbucket` is read by nothing yet.
- **Changed files (task 2 commit on `feat/p2-bitbucket-settings`):**
  - `backend/app/config.py` — `Secret`, `BitbucketSettings`, `Settings.bitbucket`, `_bitbucket()`
  - `backend/app/main.py` — builds the provider, `app.state.bitbucket`
  - `backend/tests/test_bitbucket_settings.py` — new, 32 tests
  - `.env.example`, `docs/CONFIGURATION.md` — the four variables and the secret-handling rules
  - `docs/ARCHITECTURE.md` — three lines on settings and provider construction
  - `docs/DECISIONS.md` — settings decision; corrected the stale "uncommitted" note on the Phase 2 entry
  - `docs/IMPLEMENTATION_STATUS.md`, `NEXT_AGENT_PROMPT.md` — this checkpoint and the handoff
- **Tests (2026-11-12, Linux cloud container, Python 3.13.18, fresh virtualenv from `backend/requirements.txt`):**
  - Baseline before any edit, at `08b3b1b`: `cd backend && python -m pytest -q` → 139 passed, 1 warning in 14.96 s
  - `cd backend && python -m pytest -q tests/test_bitbucket_settings.py` → 32 passed, 1 warning
  - `cd backend && python -m pytest -q` → 171 passed, 1 warning (139 existing + 32 new)
  - Real server check: `uvicorn app.main:app` with a fake workspace, repository and token started, `GET /api/health` returned 200, and the debug log did not contain the token. With only `SHIPSAFE_BITBUCKET_WORKSPACE` set, startup failed with `ConfigError` naming the two missing variables.
  - **Not re-run on Windows** (the earlier runs were Windows 11, Python 3.12.4, about four minutes per full run). Frontend build not re-run (no frontend change).

### Blockers / known issues
- **Live Bitbucket: NOT TESTED.** No credentials were used and no request has ever left the machine for `api.bitbucket.org`. Payload shapes come from Bitbucket's OpenAPI file, not from observed responses. The settings tests use a made-up token and send nothing.
- Phase 1 is unmerged; Phase 2 is stacked on it by the owner's instruction (see `docs/DECISIONS.md`).
- The provider's HTTP client is never closed (it lives for the whole process); revisit if `create_app` is ever called repeatedly in one long-lived process.
- `scanner.import_dependencies` reads every unchanged `.py` file in the tree: over Bitbucket that is one HTTP request per file. Needs a cap or skip before PR scans run on a real repository (task 4).
- HTTP 555 (diff too large) fails the comparison; there is no per-file fallback.
- Pull requests from forks: the head SHA is left unset when the commit cannot be read through the approved repository.
- `get_changes` is a two-dot comparison, as the protocol requires. PR scans must pass the merge base as `base` (Bitbucket `GET /merge-base/{revspec}`) or record a different choice; undecided until task 4.

### Next exact task
- **Goal:** Migration 2 — add `provider`, `repository_id`, `pull_request_id`, `base_commit`, `head_commit` (full SHAs) to `scans`, plus the stale flag, following the proposal in `docs/MIGRATIONS.md`. Existing rows must survive unchanged.
- **Likely files:** `backend/app/db.py` (`MIGRATIONS`), `docs/MIGRATIONS.md`, new tests in `backend/tests/` (style: the migration tests in `test_foundation.py`), `backend/app/main.py` only if local scans should start filling the new columns.
- **Done when:** a version-1 database with rows migrates to version 2 with those rows byte-identical in the old columns; failure rolls back; a newer database is still refused; local scans and review import still pass; full suite passes.
- **Decide and record first:** where "stale" lives (stored column vs. computed by comparing `head_commit` with the PR's current head — `docs/MIGRATIONS.md` proposes computed), and the two open questions at the end of `docs/MIGRATIONS.md`.
- **Avoid:** adding routes (task 4); rewriting stored `report_json`; storing credentials in the database.

### Deferred (existing roadmap only)
Phase 3 Claude review binding, Phase 4 isolated test runner, Phase 5 release assessment — see `prompts/`.

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
| Schema migration runner | IMPLEMENTED | `db.migrate`, version 1 equals the v0.2 schema; adoption, rollback, and fail-closed tests | Use in Phase 2 |
| Claude ZIP export and strict JSON import (manual) | IMPLEMENTED | `test_ai_handoff.py`; live export/import round trip | Phase 3 extends |
| React dashboard: production build | IMPLEMENTED | `npm run build` passes after the Phase 1 fix; it failed on the v0.2 baseline | Maintain |
| React dashboard: behaviour in a browser | PARTIAL | Scripted headless-Chrome runs passed: default scan, all pages, review import, restart (2026-11-11); all six demo branches scanned from the UI with export JSON and handoff ZIP verified per scan (2026-11-12, 33 checks). No human click-through, no visual or layout check, no frontend tests in the repository | Human check before merge |
| Dashboard UI for scanning a non-demo repository | NOT IMPLEMENTED | API only (`repository_path`) | Phase 2 |
| Provider interfaces (repository, PR, change, orchestration) | IMPLEMENTED | `providers/base.py`; exercised by a local and an in-memory provider | Phase 2 builds on these |
| Pull-request discovery | PARTIAL | `BitbucketCloudProvider` implements the protocol; `test_bitbucket_provider.py` (mocked HTTP). Not reachable from the API or UI (2026-11-12, `feat/p2-bitbucket-provider`, `08b3b1b`) | Phase 2 |
| Bitbucket Cloud repository and PR discovery | PARTIAL | Provider class, mocked HTTP only; no routes or UI; never run against live Bitbucket | Phase 2 |
| Bitbucket settings and credential loading | IMPLEMENTED | `test_bitbucket_settings.py` (32 tests): all-or-nothing variables, `ConfigError` on partial or malformed values, token absent from `repr`, logs, and every GET route. Unmerged (2026-11-12, `feat/p2-bitbucket-settings`); the provider it builds is used by no route | Phase 2 |
| Commit-scoped Bitbucket scans and stale detection | NOT IMPLEMENTED | Reports store 12-character SHAs only | Phase 2 |
| Automated Claude or other model invocation | NOT IMPLEMENTED | By design; handoff is manual | Not planned |
| Secure regression test runner | NOT IMPLEMENTED | No repository code is ever executed | Phase 4 |
| Test patch approval and execution | NOT IMPLEMENTED | | Phase 4 |
| Evidence-based release assessment | NOT IMPLEMENTED | Only the heuristic score and JSON export exist | Phase 5 |
| Authentication, roles, multi-user | NOT IMPLEMENTED | Loopback-only development API | Phase 5 assessment |
| Webhooks and CI gating | NOT IMPLEMENTED | | Not scheduled |

Update this table only after integration and verification.
