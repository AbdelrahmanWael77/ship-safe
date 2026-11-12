# Contributor Session Handoff — Phase 1 / Foundation (audit, stabilize, provider seams)

- Human owner: **TBD** — `docs/TEAM_ROSTER.md` is unfilled; no ticket or owner was assigned for this session
- Claude session operator: Nour Waled (local Git identity)
- Branch: `feat/p1-foundation` (pushed to GitHub on request; see commit line)
- Commit SHA (if committed): `9726a61` (Phase 1 work) plus the defect 10 follow-up commit, on top of `10f3cee` ("Import ShipSafe v0.2 team starter", on `main`). Pushed to `origin/feat/p1-foundation` at `https://github.com/AbdelrahmanWael77/ship-safe`; `main` not pushed
- Reviewer: **TBD** — no second-person review. On 2026-11-12 the owner ran an independent investigation of this handoff with Claude Code and remediated its findings; see "Remediation after independent review" below
- Date: 2026-11-11 (original session); 2026-11-12 (remediation, commit `d9e7f19` on top of `f8967bc`; documentation in the following commit)
- Environment: Windows 11 Pro, Python 3.12.4, Git 2.43.0.windows.1, Node 24.22.2, npm 11.19.1; fastapi 0.162.4, pydantic 2.14.3, pytest 9.2.0

## Manual interventions and deviations from the plan

1. **The kit folder contained no application source.** `README_TEAM.md` and `docs/TEAM_START_HERE.md` say it includes the v0.2 backend and frontend; it held only `CLAUDE.md`, `README_TEAM.md`, `docs/`, `prompts/`, and `templates/`. The source was found at `C:\Users\Dell\Downloads\shipsafe_v0_2_claude_code_source\shipsafe-project` and copied in without overwriting anything (no path collisions).
2. **The folder was not a Git repository.** Following `docs/TEAM_START_HERE.md`, it was initialised with `git init -b main`, checked for secrets, and the unmodified import committed as `10f3cee`. Work then moved to `feat/p1-foundation`.
3. **One session covered the backend, frontend, and QA file sets** because no owners exist to split them across. No teammate work was present to conflict with.
4. A virtualenv was created at `.venv` (git-ignored) because FastAPI was not installed globally.

## Scope completed

- [x] Audit of routes, contracts, scanner, demo generator, persistence, handoff schema, settings, tests, and Phase 2 dependency points → `docs/ARCHITECTURE.md`
- [x] Baseline verified by execution; ten defects reproduced and fixed (one frontend build break, nine backend)
- [x] Provider interfaces and scan orchestration seam; local Git behaviour preserved
- [x] `.env.example`, configuration reference, allowlist hardening, loopback bind confirmed
- [x] Migration runner (no schema change) and a written design for Bitbucket metadata
- [ ] Human review, merge, canonical doc updates, tag — not done, not mine to do

## Remediation after independent review (2026-11-12)

The owner decided to complete Phase 1 as a single integrator. An investigation of this handoff (actual implementation, not documentation; all reproductions in isolated temp directories) produced six fixes. Each has regression tests in `backend/tests/test_phase1_remediation.py` (30 tests); the 16 that assert fixed behaviour were run against the pre-fix commit `f8967bc` in a detached worktree and fail there.

| # | Finding (severity) | Behaviour on `f8967bc` | Fix |
|---|---|---|---|
| A1 | No Host-header check: DNS rebinding reaches the loopback API (High) | `Host: attacker.example` → 200 on every route; `POST /api/scans` → 201. CORS cannot help: the rebinding request is same-origin | `TrustedHostMiddleware` outermost, hosts `127.0.0.1`, `localhost`, `[::1]` (any port) → 400 otherwise. Tests use `TestClient(app, base_url="http://127.0.0.1")`. Live: direct 200, spoofed 400, Vite proxy 200 |
| B5 | `SHIPSAFE_DEMO_DIR` had no drive-root check (Low) | `C:\` accepted; `allowed_roots == (C:\,)` (seeder then refused to start, so fail-closed by accident) | Same `_scannable_root()` check as `SHIPSAFE_ALLOWED_ROOT` |
| B1 | File names read as pathspec magic / globs (High, report integrity) | Tree entries `*` → patch of every file; `:!a.py` → every file but `a.py`; `[a].py` → also `a.py`'s lines. Linux-cloned repositories can carry these names | `git --literal-pathspecs` on every scanner command plus `-- ./<path>` (the prefix is what fixes `::name`). Tested on 12 hostile names built with `git mktree -z` |
| B2 | Redirecting `.git` file bypasses the allowlist (Medium) | `redirect/.git` = `gitdir: <outside>/.git` under an allowed root scanned the outside repository and returned its diff | `get_repository()` also requires `git rev-parse --path-format=absolute --git-common-dir` to be under an allowed root. Worktrees/submodules inside the allowlist still work (tested) |
| B4 | Seeder repair discarded uncommitted edits and committed stray files; look-alike repos adopted (Low) | Repair with one branch missing: `checkout -f` wiped an edit to `app/auth.py`, `git add .` committed `stray.txt` into the rebuilt branch and the final checkout deleted it; a foreign repo whose root commit subject matched was accepted | Repair refuses (`ConfigError` naming files) when a tracked file has a change the seeder did not itself write (the real interrupted-seed case still repairs); `git add -- <demo files>` only; `shipsafe.demo=true` marker at creation, legacy repos recognised by root subject + synthetic author e-mail |
| B3 | Truncation invisible in report, UI and ZIP (Medium) | 302 changed files → `files_changed: 300`, `lines_added: 499`, no flag anywhere; 200-line patch stored as 140 lines ending mid-hunk | Additive fields `summary.truncated`, `summary.files_omitted`, `files[].diff_truncated`, `files[].diff_lines_omitted`; marker line at the end of a cut diff; UI badge and notice; dynamic ZIP `limitations`. `ChangeSet.omitted` added to the provider contract. Example JSON and pinning test updated; old stored reports read as not truncated |

Also verified and accepted without change: no repository-defined Git command runs during a scan (18 config keys, 7 hooks, attribute filters armed; all fire on `git add`, none during the scan; now guarded by a test); `..`, UNC admin shares, `\\?\`, 8.3 names, junctions all denied or resolved correctly; migrations idempotent, v0.2 schema byte-identical, rollback and fail-closed confirmed; routes and status codes unchanged apart from the Host check; the two `npm audit` advisories are dev-server-only and unreachable in this setup (no non-breaking fix exists; toolchain upgrade is Phase 2).

Files changed by the remediation: `backend/app/main.py`, `config.py`, `demo_seed.py`, `scanner.py`, `ai_handoff.py`, `providers/base.py`, `providers/local_git.py`; `backend/tests/test_phase1_remediation.py` (new) and the `TestClient` base URL in the four existing test files; `frontend/src/App.tsx`, `types.ts`; `docs/example-scan-report.json`; docs: `ARCHITECTURE.md`, `CONFIGURATION.md`, `IMPLEMENTATION_STATUS.md`, `DECISIONS.md`, `ACCEPTANCE_MATRIX.md`, `CLAUDE-CODE-HANDOFF.md`, `TEAM_START_HERE.md`, `README.md`, `README_TEAM.md`, `.env.example`, this file.

Commands executed on 2026-11-12 (Windows 11, Python 3.12.4, Node 24.22.2, `.venv`):
```text
$ cd backend && python -m pytest -q
101 passed, 1 warning in 235.95s

$ (detached worktree at f8967bc, new test file copied in)
16 failed, 14 passed in 79.29s          # the 16 are the fixed-behaviour assertions

$ cd frontend && npm run build
✓ 1581 modules transformed · dist/assets/index-BP1kdbMN.js 198.79 kB · ✓ built in 7.39s

Live (uvicorn 127.0.0.1:8000, vite 127.0.0.1:5173):
direct 127.0.0.1:8000 /api/health -> 200 · spoofed Host attacker.example -> 400
through Vite proxy 127.0.0.1:5173 and localhost:5173 -> 200 · Vite with spoofed Host -> 403

Headless Chrome, scratch demo + database, all six branches via the Run analysis button:
release-candidate 3 · auth-regression 1 · pricing-regression 1 · api-breaking 1 · docs-only 0 · safe-cleanup 0  (all as expected)
per scan: Code changes renders, no truncation badge, export JSON 200 (truncated=false), handoff ZIP 200 with 3 entries and digest == /ai/context
SUMMARY 33 passed, 0 failed · no uncaught page errors
```

Linux / Python 3.11 (Docker `python:3.11-slim`, Git 2.47.3): `101 passed in 19.10s`; Linux `node:24-slim` `npm ci && npm run build`: ✓ built, same bundle hash as Windows.

Still not done after remediation: a macOS run; a human visual pass over the dashboard; a real Claude Code export → review → import round trip; second-person review of the Bitbucket interfaces and of the migration runner.

## Defects reproduced on the v0.2 baseline and fixed

Defects 2–9 each have a test in `backend/tests/test_phase1_regressions.py` that failed on `10f3cee` and passes now. Defect 1 is covered by `npm run build` itself; there is no frontend test suite. Defect 10 was found after the first push; its test fails on the baseline seeder at import (`DEMO_BRANCH_FILES` did not exist), and the underlying early return was observed live on the workstation, not only in the test.

| # | Defect | Baseline behaviour | Fix |
|---|---|---|---|
| 1 | Frontend production build | `tsc` error TS2550: `replaceAll` not in the ES2020 lib (`App.tsx:300`, twice) | Use `replace(/\//g, '.')`; tsconfig untouched |
| 2 | Scanned repository can run a command | A repo's `.git/config` `diff.<driver>.textconv` was executed by `git diff` during a scan | `--no-textconv` on every diff call |
| 3 | Non-UTF-8 locale decoding | Git output decoded as cp1252: `UnicodeDecodeError` in the reader thread, scan failed | Decode as UTF-8 with replacement |
| 4 | Non-ASCII file names | Path came back C-quoted (`"app/caf\303\251.py"`), giving an empty diff and zero line counts | `-z` output, unquoted paths |
| 5 | Pathological Python source | `RecursionError` from `ast.parse` escaped, HTTP 500 | One guarded `_parse()` helper |
| 6 | Unresolvable `repository_path` | NUL byte raised `ValueError`, HTTP 500 | 400 `RepositoryNotFound` |
| 7 | Authorizing a workspace locked out the demo | With `SHIPSAFE_ALLOWED_ROOT` set elsewhere, the dashboard's default scan returned 403 | Demo directory is always an allowed root |
| 8 | Deeply nested review JSON | `RecursionError` from `json.loads`, HTTP 500 | Mapped to 422 |
| 9 | Unknown ref message | `fatal: Needed a single revision` | `Git reference not found in this repository: '<ref>'` |
| 10 | Interrupted demo seed is never repaired | Seen on the workstation after the first push: a Ctrl+C during the first API start (Git exit 130 on `commit`) left `.git` with two of six branches; every later start returned early because `.git` existed, and the dashboard failed on the other four branches | `ensure_demo_repo` is idempotent and rebuilds missing or uncommitted branches from `main`; refuses non-demo directories; sets `commit.gpgsign=false` in the demo repo |

Also changed without a failing test first, and flagged for the reviewer: an empty `SHIPSAFE_ALLOWED_ROOT` is now treated as unset (it previously resolved to the process working directory), a drive root is refused, the frontend renders list-shaped 422 details instead of `[object Object]`, and SQLite connections are now closed after each use.

## Files changed

Modified:
- `backend/app/main.py` — settings, migrations, and provider wiring; 403/400 mapping; `RecursionError` on import. Routes and response shapes unchanged
- `backend/app/scanner.py` — `scan_changes()` orchestration over a `ChangeProvider`; `scan_repository()` kept as a wrapper; guarded AST parsing. Heuristics untouched
- `backend/app/demo_seed.py` — idempotent seeding and repair (defect 10); branch content moved to module-level `DEMO_BRANCH_FILES`. Generated files and commits are unchanged
- `frontend/src/App.tsx` — build fix; `describeError()` for API error details
- `scripts/dev.py` — loads `SHIPSAFE_*` lines from a root `.env`
- `.gitignore` — ignores `.env`, `.env.*`, keeps `.env.example`
- `README.md` — removed the stale `cd shipsafe-project`, configuration pointers, duplicate step number
- `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_STATUS.md` — rewritten from verified code

Added:
- `backend/app/errors.py`, `backend/app/config.py`, `backend/app/db.py`
- `backend/app/providers/__init__.py`, `base.py`, `local_git.py`
- `backend/tests/test_phase1_regressions.py` (32 tests), `backend/tests/test_foundation.py` (15 tests)
- `.env.example`, `docs/CONFIGURATION.md`, `docs/MIGRATIONS.md`, this file
- `frontend/package-lock.json` — generated by `npm install`; the baseline shipped none

Not touched in the original session: `backend/app/ai_handoff.py`, the two original test files, `frontend/src/types.ts`, `docs/PHASE_HANDOFF.md`, `docs/ACCEPTANCE_MATRIX.md`, `docs/DECISIONS.md`, `docs/TEAM_ROSTER.md`. The 2026-11-12 remediation later changed `ai_handoff.py` (dynamic limitations), the two original test files (`TestClient` base URL only), `types.ts` (optional fields), and filled `ACCEPTANCE_MATRIX.md` and `DECISIONS.md` with the owner acting as integrator. Still untouched: `docs/PHASE_HANDOFF.md` (rewritten after merge) and `docs/TEAM_ROSTER.md`.

## API / DB contracts

- **HTTP API:** no route, request field, response field, or success status changed. `frontend/src/types.ts` is unchanged. Two status changes, both 500 → 4xx (defects 6 and 8). One behaviour change: defect 7.
- **Error text:** the unknown-ref 400 message changed (defect 9).
- **Report and review schema:** unchanged in the original session. The remediation added four additive report fields (`summary.truncated`, `summary.files_omitted`, `files[].diff_truncated`, `files[].diff_lines_omitted`) and the ZIP `limitations` text is now computed from them; `docs/example-scan-report.json` and the pinning test were updated. The review import schema is unchanged. The API now also refuses non-loopback `Host` headers with 400.
- **Database:** schema unchanged. `PRAGMA user_version` goes from 0 to 1 on first start; no rows are read or written by that step.
- **New internal types** (`backend/app/providers/base.py`, not exposed over HTTP):

```text
RepositoryRef(provider, id, name, location, default_branch=None)
PullRequestRef(provider, repository_id, id, title, state, source_ref, target_ref,
               source_sha=None, target_sha=None, author=None, url=None, updated_at=None)
FileDelta(path, status, additions, deletions, patch)
ChangeSet(repository, base_ref, head_ref, base_sha, head_sha, files, truncated=False)

RepositoryProvider:  list_repositories(), get_repository(repository_id)
PullRequestProvider: list_pull_requests(repository, state="open"), get_pull_request(repository, pull_request_id)
ChangeProvider:      resolve_commit(repository, ref), get_changes(repository, base_ref, head_ref, max_files=300),
                     list_files(repository, commit), read_file(repository, commit, path)
scanner.scan_changes(provider, repository, base, head) -> Report dict
```

- **Migration decision:** runner implemented, no migration beyond the baseline. The Bitbucket metadata migration is design only (`docs/MIGRATIONS.md`).

## Commands executed and literal results

Baseline, unmodified source at `10f3cee`:
```text
$ cd backend && python -m pytest -q
24 passed, 1 warning in 41.37s

$ cd frontend && npm install && npm run build
added 69 packages, and audited 70 packages in 48s
2 vulnerabilities (1 moderate, 1 high)
> tsc -b && vite build
src/App.tsx(300,714): error TS2550: Property 'replaceAll' does not exist on type 'string'. ...
src/App.tsx(300,922): error TS2550: Property 'replaceAll' does not exist on type 'string'. ...
```

New regression tests against the unmodified baseline:
```text
$ python -m pytest -q tests/test_phase1_regressions.py
8 failed, 19 passed, 3 warnings in 36.46s
```

After the changes:
```text
$ cd backend && python -m pytest -q
66 passed, 1 warning in 89.43s (0:01:29)

$ cd backend && python -m pytest -q        # after the defect 10 follow-up
71 passed, 1 warning in 122.94s (0:02:02)

$ cd frontend && npm run build
✓ 1581 modules transformed.
dist/index.html                   0.57 kB
dist/assets/index-DSqquSvF.css   33.71 kB
dist/assets/index-DwTo36tS.js   197.85 kB
✓ built in 2.34s

$ git diff --check
(no output)
```
`python` here is `.venv/Scripts/python`. The one warning is Starlette's `httpx` deprecation notice.

Live run: uvicorn on 127.0.0.1:8000 and `npm run dev` on 127.0.0.1:5173, scratch database and demo directory, all requests through the Vite `/api` proxy:
```text
scan rc          201 19a598e951c7 -> 6196158a9c8f {'files_changed': 4, 'lines_added': 8, 'lines_removed': 9, 'finding_count': 3, 'risk_score': 97, 'recommendation': 'Critical review required', 'test_status': 'not_run'}
auth.py diff     ['-    if invoice["owner_id"] != user_id:', '-        raise PermissionError("Invoice does not belong to this user")', '+    # Regression: ownership verification was accidentally removed.']
scan docs-only   201 ['README.md'] findings: [] 3
error: missing ref   400 Git reference not found in this repository: 'feature/nope'
error: bad ref       400 Invalid Git reference: '--x'
error: outside root  403 Repository is outside SHIPSAFE_ALLOWED_ROOT. ...
error: no such path  400 This path is not a local Git repository
error: empty ref     422
handoff zip      200 ['REVIEW_INSTRUCTIONS.md', 'response-template.json', 'review-input.json']
import template  409 Review finding references a file not present in this scan: REPLACE: ...
import review    201 not_independently_verified False user_imported_json_unverified_provenance
wrong-scan import 409
scan unchanged   True
--- API process killed and restarted ---
history after restart 200 [('feature/docs-only', 0), ('feature/release-candidate', 3)]
report identical      True
digest identical      True reviews: 1
review persisted      True
--- netstat ---
TCP    127.0.0.1:5173    LISTENING
TCP    127.0.0.1:8000    LISTENING
```
The imported review in that run was hand-written JSON, not produced by a Claude Code session.

Browser run: headless Google Chrome 157.0.8103.50 driven over the DevTools protocol by a throwaway script (kept outside the repository), against the same two loopback servers with a fresh scratch database and demo directory. Clicks and the file upload went through the real page, not the API:
```text
PASS | first load on empty history runs the default demo scan and renders 3 findings
PASS | overview shows real changed files with line counts
PASS | all seven sidebar pages open and render
PASS | Code changes shows the real removed line from app/auth.py
PASS | Test intelligence states tests were not run
PASS | Run analysis on docs-only from the UI creates a scan with zero findings | history=[('feature/docs-only', 0), ('feature/release-candidate', 3)]
PASS | docs-only view shows no CRITICAL or HIGH finding
PASS | Scan history lists both scans
PASS | reopening the release-candidate scan from history restores its findings
PASS | Download handoff ZIP link targets the open scan and returns a ZIP | 200 application/zip
PASS | importing a review for another scan shows an error and no review | 'Review scan ID or context digest does not match this scan. Export a fresh handoff bundle.'
PASS | importing a valid review file shows it, labelled unverified
PASS | static report unchanged by the import
PASS | no uncaught exceptions or console errors (other than expected 4xx fetch logs)
SUMMARY 14 passed, 0 failed
--- API process killed and restarted on the same database ---
PASS | after API restart the page loads and history still has both scans (no new auto-scan)
PASS | Scan history page lists both stored scans after restart
PASS | imported review is still shown for the release-candidate scan after restart
PASS | no uncaught exceptions or console errors (other than expected 4xx fetch logs)
SUMMARY 4 passed, 0 failed
```
A first attempt reported 3 failures; they came from the script clicking a table row instead of its **Open** button, and the corrected script was rerun from an empty database. The only console entries were the expected 409 from the rejected import and a 404 for `/favicon.ico` (the frontend ships no favicon). This run checks text and behaviour only: nobody looked at the rendered page, so layout, styling, and responsiveness are unchecked, and only the release-candidate and docs-only branches were scanned through the UI. The imported review was again hand-written JSON.

## Tests / acceptance

Proposed results for the integrator. The canonical `docs/ACCEPTANCE_MATRIX.md` was not edited.

| Check | Result | Actual evidence |
|---|---|---|
| Baseline: original backend tests | PASS | 24 passed on this machine at `10f3cee` |
| Baseline: frontend production build | **FAIL** | TS2550 at `App.tsx:300` on unmodified v0.2 |
| P1: real demo scans still work | PASS | Original 24 tests still pass; live run above |
| P1: `main` → `feature/release-candidate` uses real commits and shows changed lines | PASS | `test_release_candidate_scan_uses_real_commits_and_shows_changed_lines`; live run |
| P1: docs-only branch has no fabricated findings | PASS | `test_docs_only_branch_reports_no_findings_through_the_api`; live run |
| P1: scan history survives restart | PASS | `test_scans_and_reviews_survive_an_application_restart`; live restart |
| P1: Claude handoff export and import contract | PASS | `test_ai_handoff.py` unchanged and passing; live round trip |
| P1: handoff reviewed by a real Claude Code session | NOT TESTED | Only hand-written and template JSON were imported |
| P1: invalid paths, refs, inputs give predictable errors | PASS | `test_phase1_regressions.py`; live run |
| P1: backend suite | PASS | 101 passed after the remediation (71 at `f8967bc` + 30 in `test_phase1_remediation.py`) |
| P1: independent-review fixes A1, B1–B5 | PASS | 30 remediation tests pass; the 16 fixed-behaviour assertions fail on `f8967bc` |
| P1: all six demo branches through the dashboard, export and ZIP per scan | PASS | Scripted headless Chrome, 33 checks, 2026-11-12 |
| P1: frontend production build | PASS | After the fix; output above |
| P1: dashboard behaviour in a browser (scripted) | PASS | Headless Chrome run above: 14 + 4 checks |
| P1: dashboard checked by a person (layout) | NOT TESTED | No human click-through; no frontend tests in the repository |
| P1: provider interfaces small, usable, behaviour-preserving | PASS | `test_foundation.py`; report shape pinned to the v0.2 example |
| P1: config, allowlist, loopback bind, Host-header check | PASS | `test_foundation.py`, `test_phase1_remediation.py`; netstat above; live spoofed-Host check 400 |
| P1: migration readiness | PASS | v0.2 database adopted with rows intact; rollback and fail-closed tests |
| P1: no credentials, fake statuses, repository writes, history deletion | PASS | Secret grep clean; `test_scan_does_not_modify_the_scanned_repository`; no DELETE/UPDATE in code |
| P1: on Python 3.11 and Linux | PASS | Docker `python:3.11-slim` (3.11.18, Git 2.47.3): 101 passed in 19 s; `node:24-slim` build ✓ (2026-11-12). macOS NOT TESTED |
| P1: docs reflect merged code; PRs reviewed and approved | **BLOCKED** | Nothing is merged or reviewed; needs human owners |

## Security / privacy review

- Allowed repository/data access: synthetic LedgerLite and synthetic repositories under pytest temp directories only. No client or private code was read. The source import came from the user's own Downloads folder.
- Secrets exposed in logs or files? No. None exist in the project; `.env.example` has no values.
- Untrusted input handled: repository paths, refs, file names, file contents, repository Git config (textconv), review JSON size, depth, and schema.
- Test execution isolation: not applicable. No repository code or tests are executed by ShipSafe. The only suites run on the host were ShipSafe's own backend tests.
- No merges, tags, or Bitbucket calls were made. On the user's request, `origin` was added and `feat/p1-foundation` alone was pushed, with their own GitHub credentials; no credential was read or stored by this session.

## Blockers and known defects

Not fixed, because they were not reproduced or are out of Phase 1 scope. Details in `docs/ARCHITECTURE.md`.

- No authentication on the API. The `Host` header is limited to loopback names since 2026-11-12, which closes DNS rebinding; any local process with a loopback `Host` still has full access.
- UNC, `\\?\`, 8.3 and junction paths: tested 2026-11-12, all denied or resolved to the real path. A UNC `repository_path` is still resolved (a network touch) before it is denied.
- File names read as pathspec magic or globs: fixed 2026-11-12 (`--literal-pathspecs`, `-- ./path`).
- Repository-defined Git commands: tested 2026-11-12 with 18 config keys, hooks and attribute filters armed; none runs during a scan. Guarded by a test.
- Reports keep 12-character SHAs (resolve uniquely; full SHAs arrive with Phase 2). The 300-file cap and 140-line cut are now reported in the JSON, the UI and the ZIP.
- `npm audit`: 2 advisories, assessed 2026-11-12 as dev-server-only and not reachable in this loopback setup; `launch-editor` lines do not apply (not installed); no non-breaking fix exists. Toolchain upgrade is Phase 2 work.
- Scans have per-command timeouts but no overall budget and no cap on a single Git command's output size (local resource use only).
- The local provider compares the two commits directly, not from their merge base. Correct for the demo branches; Phase 2 must choose pull-request comparison semantics (`docs/ARCHITECTURE.md`, "Phase 2 dependency points").
- The frontend has no favicon (one 404 per page load).
- `README_TEAM.md` and `docs/TEAM_START_HERE.md` claim the kit ships the source. It did not. Those files were left as they are.

## Conflicts or coordination needed

- `backend/app/main.py`, `backend/app/scanner.py`, and `frontend/src/App.tsx` are shared files that any parallel Phase 1 ticket would also touch. If teammates have work on other machines, reconcile before merging this branch.
- `frontend/package-lock.json` is new. Decide whether the team commits it (recommended for reproducible builds).
- The canonical baseline in `docs/PHASE_HANDOFF.md` and `docs/ACCEPTANCE_MATRIX.md` says the frontend build is untested. It fails on v0.2; the integrator should record that.

## Decisions for the team to confirm (proposed entries for `docs/DECISIONS.md`)

1. The demo repository is always scannable, in addition to `SHIPSAFE_ALLOWED_ROOT`.
2. A drive or filesystem root is rejected as an allowed root.
3. Schema versioning uses `PRAGMA user_version` with additive, forward-only migrations.
4. The report JSON shape is frozen for Phase 1; full SHAs and provider metadata arrive as new columns in Phase 2, not by rewriting stored reports.
5. Renames are reported as a delete plus an add (existing behaviour, now part of the `FileDelta` contract).
6. The initial repository import was committed directly to `main` as the starting point.
7. The demo seeder may rewrite branches inside the demo directory only when they are missing or carry no commit, and never touches a repository it did not generate.

## Reviewer instructions

Check independently; do not rely on the results above.

1. `git diff 10f3cee -- backend/app/scanner.py backend/app/main.py`: confirm the heuristics and routes are unchanged and that every `git diff` call goes through `_SAFE_DIFF`.
2. Check out `10f3cee`, copy in `backend/tests/test_phase1_regressions.py`, and confirm 8 tests fail there.
3. Run both verification commands on a second machine, ideally Python 3.11 and a non-Windows OS.
4. Open the dashboard in a browser yourself: default scan, each demo branch, Code changes diff, Claude Review export and import, Scan history after a restart. The scripted run covered behaviour for two branches only and nothing visual.
5. Do one real handoff: export the ZIP, review it in your own Claude Code session, import the result.
6. Read `providers/base.py` as the Phase 2 backend and frontend owners: is anything missing for Bitbucket Cloud?
7. Review `db.migrate` and `docs/MIGRATIONS.md` as the migration reviewer.

## NOT DONE / do not claim

- No Bitbucket code, settings, or network calls. No pull-request discovery implementation.
- No test runner, no AI invocation, no webhooks, no authentication.
- No new API endpoints; repository discovery is not exposed over HTTP.
- No human or visual check of the dashboard, and no frontend tests in the repository; the headless-Chrome scripts were one-offs and are not committed.
- No macOS run. No real Claude Code export → review → import round trip.
- No second-person review of anything. Not merged, not tagged `shipsafe-phase-1`. The remediation is committed as `d9e7f19` (code and tests) plus a documentation commit; not pushed at the time of writing; `main` is not on the remote.
- Canonical `PHASE_HANDOFF.md` (rewritten after merge) and `TEAM_ROSTER.md` not updated. `ACCEPTANCE_MATRIX.md` and `DECISIONS.md` were filled by the owner on 2026-11-12.

## Suggested next ticket

Before Phase 2 starts: fill the roster, review and merge this branch, and run reviewer steps 3–5. Recommended Phase 2 ticket boundaries, so owners do not share files:

| Ticket | Owner | Files |
|---|---|---|
| Bitbucket provider implementing the three protocols against mocked HTTP | Backend | new `backend/app/providers/bitbucket.py`, new tests and fixtures |
| Bitbucket settings and credential handling | Backend | `backend/app/config.py`, `.env.example`, `docs/CONFIGURATION.md` |
| Migration 2 and commit-bound scan storage | Backend, with the migration reviewer | `backend/app/db.py`, `docs/MIGRATIONS.md` |
| API contract for repositories, pull requests, and scan-by-PR, agreed first as sample JSON | Integrator, then backend | `backend/app/main.py`, `docs/ARCHITECTURE.md` |
| Typed client and repository/PR picker UI | Frontend | `frontend/src/**` |
| Independent connector, stale-scan, and credential-leak tests | QA/security | new test files only |
