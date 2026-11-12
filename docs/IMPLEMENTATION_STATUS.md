# Implementation status

## Checkpoint — living, updated after every task

Rules: `AGENTS.md` and `CLAUDE.md`. Handoff prompt: `NEXT_AGENT_PROMPT.md`.

- **Roadmap:** `prompts/PHASE-01-FOUNDATION.md` … `PHASE-05-FINAL-VALIDATION.md`; gates in `docs/ACCEPTANCE_MATRIX.md`
- **Current phase:** 2 — Bitbucket repositories and pull requests (`prompts/PHASE-02-BITBUCKET.md`)
- **Last updated:** 2026-11-12
- **Branch / latest commit:** (verified with `git ls-remote origin` on 2026-11-12)
  - GitHub has **no `main` branch**. The default and integration branch is `feat/p1-foundation`, at `98c9d92`, which is the merge of pull request #1 (`feat/p2-bitbucket-provider`, P2 task 1). Where the rules say "never commit to `main`", read "never commit directly to `feat/p1-foundation`".
  - `feat/p2-bitbucket-provider` at `08b3b1b` — P2 task 1 and the handoff system. On GitHub; already merged into `feat/p1-foundation`.
  - `feat/p2-bitbucket-settings` at `ebc9068`, cut from `08b3b1b` — P2 task 2. Committed with the owner's approval. **Not on GitHub yet**: the agent session had no GitHub credential. Check `git ls-remote origin feat/p2-bitbucket-settings`.
  - `feat/p2-migration-2`, cut from `ebc9068` — P2 task 3. Committed with the owner's approval (branch head). **Not on GitHub yet**, for the same reason; push it only after `feat/p2-bitbucket-settings`.

### Completed and verified
- Baseline v0.2 ("Phase 0") — imported as `10f3cee`.
- Phase 1 — complete on `feat/p1-foundation` (101 backend tests, frontend build; see matrix), which is the repository's default branch. Not tagged; human review is still open.
- Agent handoff system installed 2026-11-12: `AGENTS.md`, entry section in `CLAUDE.md`, this checkpoint, `NEXT_AGENT_PROMPT.md`.
- P2 task 1 — read-only Bitbucket Cloud provider (`backend/app/providers/bitbucket.py`) implementing all three provider protocols. Mocked HTTP only. `08b3b1b`.
- P2 task 2 — Bitbucket settings and credential loading; `create_app` builds the provider only when configured. 32 tests. `ebc9068`.
- P2 task 3 — migration 2 and storage helpers; local scans are stored with provider, repository and full commit SHAs. 17 new tests.

### Phase 2 task list (order; one task at a time)
1. [x] Bitbucket Cloud provider + mocked-HTTP tests
2. [x] Bitbucket settings and credential loading
3. [x] Migration 2: provider / repository / PR / full base+head SHA columns, stale marker
4. [ ] API: list repositories, list PRs, scan a PR bound to exact SHAs, stale detection (**next**)
5. [ ] Frontend: Repositories, Pull Requests, PR Analysis screens with typed client
6. [ ] Human-run read-only live smoke test (PASS or BLOCKED), docs, gates

### Current working state
- **Functional now:**
  - `BitbucketCloudProvider` — allowlisted repository discovery with pagination, PR list/detail with full-SHA binding, ref resolution, two-dot change sets with per-file patches, tree listing, file reads; auth, error handling, retries, byte and page caps. `scan_changes()` produces a report from it.
  - Settings: `Settings.bitbucket` is `None` unless `SHIPSAFE_BITBUCKET_WORKSPACE`, `_REPOSITORIES`, `_TOKEN` are all set (`_EMAIL` optional); otherwise `ConfigError`. Token held in `config.Secret`. `create_app` builds the provider into `app.state.bitbucket` without sending a request.
  - Schema version 2: `scans` gained `provider` (default `local-git`), `repository_id`, `pull_request_id`, `base_commit`, `head_commit`, `stale_at`, and an index. Version-1 and v0.2 databases migrate with `id`, `created_at`, `report_json` and `ai_reviews` byte-identical.
  - `db.insert_scan` stores a report beside its binding and refuses abbreviated SHAs. `POST /api/scans` uses it, so new local scans carry provider, repository path and full base/head SHAs. The report JSON and every API response are unchanged.
  - `db.sync_stale` marks a pull request's scans stale when their `head_commit` differs from a given current head, and clears the marker when it matches again.
  - `scanner.scan_change_set` returns `(report, ChangeSet)`; `scan_changes` is unchanged for callers.
- **Not wired:** no API route, no UI uses the Bitbucket provider. Nothing calls `sync_stale` and nothing writes `pull_request_id`, so no scan is ever marked stale yet. No API response exposes the new columns.
- **Changed files (task 3 commit on `feat/p2-migration-2`):**
  - `backend/app/db.py` — migration 2, `insert_scan`, `sync_stale`
  - `backend/app/scanner.py` — `scan_change_set`; `scan_changes` delegates to it
  - `backend/app/main.py` — `create_scan` stores through `insert_scan`
  - `backend/tests/test_migration_2.py` — new, 17 tests
  - `backend/tests/test_foundation.py` — three migration tests no longer hard-code "version 1 is the latest" or a three-column `scans` table; they assert the same behaviour
  - `docs/MIGRATIONS.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/IMPLEMENTATION_STATUS.md`, `NEXT_AGENT_PROMPT.md`
- **Tests (2026-11-12, Linux cloud container, Python 3.13.18, fresh virtualenv from `backend/requirements.txt`):**
  - `cd backend && python -m pytest -q tests/test_migration_2.py tests/test_foundation.py` → 32 passed (17 new + 15 existing)
  - `cd backend && python -m pytest -q` → 188 passed, 1 warning (171 after task 2 + 17 new)
  - Task 2 for reference: 171 passed; baseline at `08b3b1b`: 139 passed.
  - **Not re-run on Windows** since `08b3b1b` (earlier runs: Windows 11, Python 3.12.4, about four minutes per full run). Frontend build not re-run (no frontend change).

### Blockers / known issues
- **Pushes of `feat/p2-bitbucket-settings` and `feat/p2-migration-2` are pending** (no GitHub credential in the agent session). Push them in that order.
- **Live Bitbucket: NOT TESTED.** No credentials were used and no request has ever left the machine for `api.bitbucket.org`. Payload shapes come from Bitbucket's OpenAPI file, not from observed responses.
- Phase 2 branches are stacked; tasks 2 and 3 are not yet merged into `feat/p1-foundation`.
- A database opened by this code becomes version 2 and is then refused by older branches. When switching back to an older branch, use another `SHIPSAFE_DB_PATH`.
- Migration 2 decisions (stored stale marker, no backfill, report JSON unchanged) were approved by Mohamed Elsayed on 2026-11-12; see `docs/DECISIONS.md`.
- The provider's HTTP client is never closed (it lives for the whole process).
- `scanner.import_dependencies` reads every unchanged `.py` file in the tree: over Bitbucket that is one HTTP request per file. Needs a cap or skip before PR scans run on a real repository (task 4).
- HTTP 555 (diff too large) fails the comparison; there is no per-file fallback.
- Pull requests from forks: the head SHA is left unset when the commit cannot be read through the approved repository.
- `get_changes` is a two-dot comparison, as the protocol requires. PR scans must pass the merge base as `base` (Bitbucket `GET /merge-base/{revspec}`) or record a different choice; undecided until task 4.

### Next exact task
- **Goal (P2 task 4):** API over the Bitbucket provider — list approved repositories, list a repository's open pull requests, scan a pull request bound to its exact base and head SHAs, and stale detection.
- **Likely files:** `backend/app/main.py` (routes; `app.state.bitbucket`), `backend/app/db.py` (`insert_scan`, `sync_stale` already exist), `backend/app/scanner.py` (cap or skip for `import_dependencies`), new tests with the mocked transport from `backend/tests/test_bitbucket_provider.py`, `docs/ARCHITECTURE.md` (API table).
- **Done when:** with mocked HTTP, repository list → PR list → PR scan → stored report works end to end; the scan row carries `provider`, `repository_id`, `pull_request_id`, and full SHAs; a changed PR head marks earlier scans stale and the API reports it; routes return a clear "not configured" answer when `app.state.bitbucket` is `None`; provider errors map to sensible HTTP statuses without leaking the token; local scanning is unchanged; full suite passes.
- **Decide and record first:** the four open design points above (merge-base semantics, import-analysis HTTP cost, HTTP 555, fork PRs) and the request/response shapes, agreed with the frontend owner.
- **Avoid:** frontend work (task 5); any Bitbucket write; live calls from tests; changing the keys `review_context()` reads.

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
| Schema migration runner | IMPLEMENTED | `db.migrate`; version 1 equals the v0.2 schema, version 2 adds scan binding columns. Adoption, rollback, and fail-closed tests in `test_foundation.py` and `test_migration_2.py` | Maintain |
| Claude ZIP export and strict JSON import (manual) | IMPLEMENTED | `test_ai_handoff.py`; live export/import round trip | Phase 3 extends |
| React dashboard: production build | IMPLEMENTED | `npm run build` passes after the Phase 1 fix; it failed on the v0.2 baseline | Maintain |
| React dashboard: behaviour in a browser | PARTIAL | Scripted headless-Chrome runs passed: default scan, all pages, review import, restart (2026-11-11); all six demo branches scanned from the UI with export JSON and handoff ZIP verified per scan (2026-11-12, 33 checks). No human click-through, no visual or layout check, no frontend tests in the repository | Human check before merge |
| Dashboard UI for scanning a non-demo repository | NOT IMPLEMENTED | API only (`repository_path`) | Phase 2 |
| Provider interfaces (repository, PR, change, orchestration) | IMPLEMENTED | `providers/base.py`; exercised by a local and an in-memory provider | Phase 2 builds on these |
| Pull-request discovery | PARTIAL | `BitbucketCloudProvider` implements the protocol; `test_bitbucket_provider.py` (mocked HTTP). Not reachable from the API or UI (2026-11-12, `feat/p2-bitbucket-provider`, `08b3b1b`) | Phase 2 |
| Bitbucket Cloud repository and PR discovery | PARTIAL | Provider class, mocked HTTP only; no routes or UI; never run against live Bitbucket | Phase 2 |
| Bitbucket settings and credential loading | IMPLEMENTED | `test_bitbucket_settings.py` (32 tests): all-or-nothing variables, `ConfigError` on partial or malformed values, token absent from `repr`, logs, and every GET route. Unmerged (2026-11-12, `feat/p2-bitbucket-settings`); the provider it builds is used by no route | Phase 2 |
| Commit-scoped Bitbucket scans and stale detection | PARTIAL | Storage only: migration 2 columns, `db.insert_scan`, `db.sync_stale` (`test_migration_2.py`, 17 tests); local scans store full SHAs. No pull request scan route, nothing calls `sync_stale`, reports still show 12-character SHAs (2026-11-12, `feat/p2-migration-2`) | Phase 2 |
| Automated Claude or other model invocation | NOT IMPLEMENTED | By design; handoff is manual | Not planned |
| Secure regression test runner | NOT IMPLEMENTED | No repository code is ever executed | Phase 4 |
| Test patch approval and execution | NOT IMPLEMENTED | | Phase 4 |
| Evidence-based release assessment | NOT IMPLEMENTED | Only the heuristic score and JSON export exist | Phase 5 |
| Authentication, roles, multi-user | NOT IMPLEMENTED | Loopback-only development API | Phase 5 assessment |
| Webhooks and CI gating | NOT IMPLEMENTED | | Not scheduled |

Update this table only after integration and verification.
