# Implementation status

## Checkpoint — living, updated after every task

Rules: `AGENTS.md` and `CLAUDE.md`. Handoff prompt: `NEXT_AGENT_PROMPT.md`.

- **Roadmap:** `prompts/PHASE-01-FOUNDATION.md` … `PHASE-05-FINAL-VALIDATION.md`; gates in `docs/ACCEPTANCE_MATRIX.md`
- **Current phase:** 2 — Bitbucket repositories and pull requests (`prompts/PHASE-02-BITBUCKET.md`)
- **Last updated:** 2026-11-12
- **Branch / latest commit:** `feat/p2-bitbucket-provider`, stacked on `feat/p1-foundation` at `9ed331c`. Everything listed under "Changed files" is **uncommitted** (no commit was authorized).

### Completed and verified
- Baseline v0.2 ("Phase 0") — imported as `10f3cee`.
- Phase 1 — complete on `feat/p1-foundation` (101 backend tests, frontend build; see matrix). **Not merged to `main`, not tagged**; human review is still open.
- Agent handoff system installed 2026-11-12: `AGENTS.md`, entry section in `CLAUDE.md`, this checkpoint, `NEXT_AGENT_PROMPT.md`.
- P2 task 1 — read-only Bitbucket Cloud provider (`backend/app/providers/bitbucket.py`) implementing all three provider protocols. Mocked HTTP only.

### Phase 2 task list (order; one task at a time)
1. [x] Bitbucket Cloud provider + mocked-HTTP tests
2. [ ] Bitbucket settings and credential loading (**next**)
3. [ ] Migration 2: provider / repository / PR / full base+head SHA columns, stale flag
4. [ ] API: list repositories, list PRs, scan a PR bound to exact SHAs, stale detection
5. [ ] Frontend: Repositories, Pull Requests, PR Analysis screens with typed client
6. [ ] Human-run read-only live smoke test (PASS or BLOCKED), docs, gates

### Current working state
- **Functional now:** `BitbucketCloudProvider` — allowlisted repository discovery with pagination, PR list/detail with full-SHA binding, ref resolution, two-dot change sets with per-file patches, tree listing, file reads; auth (Bearer token, or Basic e-mail + API token), 401/403/404/429/5xx/555, timeouts, bounded retries, byte and page caps. `scan_changes()` produces a report from it.
- **Not wired:** no settings, no API route, no UI, no database column uses it. Nothing in the running app constructs the provider.
- **Changed files (uncommitted):**
  - `AGENTS.md`, `NEXT_AGENT_PROMPT.md` — new, handoff system
  - `CLAUDE.md` — agent entry section added at the top
  - `docs/IMPLEMENTATION_STATUS.md` — this checkpoint; two Bitbucket rows in the table
  - `docs/DECISIONS.md` — Phase 2 start and Bitbucket Cloud entry
  - `backend/app/providers/bitbucket.py` — new provider
  - `backend/app/providers/__init__.py` — exports `BitbucketCloudProvider`
  - `backend/app/providers/base.py` — docstring only
  - `backend/app/errors.py` — `ProviderAuthError`, `ProviderUnavailable`
  - `backend/tests/test_bitbucket_provider.py` — new, 38 tests
- **Tests (2026-11-12, Windows 11, Python 3.12.4, `.venv`):**
  - `cd backend && python -m pytest -q tests/test_bitbucket_provider.py` → 38 passed in 0.30 s
  - `cd backend && python -m pytest -q` → 139 passed, 1 warning in 270.52 s (101 existing + 38 new)
  - Frontend build not re-run (no frontend change).

### Blockers / known issues
- **Live Bitbucket: NOT TESTED.** No credentials were used and no request has ever left the machine for `api.bitbucket.org`. Payload shapes come from Bitbucket's OpenAPI file, not from observed responses.
- Phase 1 is unmerged; Phase 2 is stacked on it by the owner's instruction (see `docs/DECISIONS.md`).
- `scanner.import_dependencies` reads every unchanged `.py` file in the tree: over Bitbucket that is one HTTP request per file. Needs a cap or skip before PR scans run on a real repository (task 4).
- HTTP 555 (diff too large) fails the comparison; there is no per-file fallback.
- Pull requests from forks: the head SHA is left unset when the commit cannot be read through the approved repository.
- `get_changes` is a two-dot comparison, as the protocol requires. PR scans must pass the merge base as `base` (Bitbucket `GET /merge-base/{revspec}`) or record a different choice; undecided until task 4.

### Next exact task
- **Goal:** Bitbucket settings — `SHIPSAFE_BITBUCKET_WORKSPACE`, `SHIPSAFE_BITBUCKET_REPOSITORIES` (comma-separated slugs), `SHIPSAFE_BITBUCKET_TOKEN`, optional `SHIPSAFE_BITBUCKET_EMAIL`; build the provider at startup only when configured.
- **Likely files:** `backend/app/config.py`, `backend/app/main.py` (construction only, no routes), `.env.example`, `docs/CONFIGURATION.md`, new tests in `backend/tests/`.
- **Done when:** tests show the app starts unchanged with no Bitbucket variables; a partial configuration raises `ConfigError`; the token never appears in `repr(settings)`, logs, or any API response; full suite passes.
- **Avoid:** adding routes or schema changes (tasks 3–4); rewriting the provider; asking the user to paste a token into chat.

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
| Pull-request discovery | PARTIAL | `BitbucketCloudProvider` implements the protocol; `test_bitbucket_provider.py` (mocked HTTP). Not reachable from the API or UI (2026-11-12, `feat/p2-bitbucket-provider`, uncommitted) | Phase 2 |
| Bitbucket Cloud repository and PR discovery | PARTIAL | Provider class only, mocked HTTP only; no settings, routes, or UI; never run against live Bitbucket | Phase 2 |
| Commit-scoped Bitbucket scans and stale detection | NOT IMPLEMENTED | Reports store 12-character SHAs only | Phase 2 |
| Automated Claude or other model invocation | NOT IMPLEMENTED | By design; handoff is manual | Not planned |
| Secure regression test runner | NOT IMPLEMENTED | No repository code is ever executed | Phase 4 |
| Test patch approval and execution | NOT IMPLEMENTED | | Phase 4 |
| Evidence-based release assessment | NOT IMPLEMENTED | Only the heuristic score and JSON export exist | Phase 5 |
| Authentication, roles, multi-user | NOT IMPLEMENTED | Loopback-only development API | Phase 5 assessment |
| Webhooks and CI gating | NOT IMPLEMENTED | | Not scheduled |

Update this table only after integration and verification.
