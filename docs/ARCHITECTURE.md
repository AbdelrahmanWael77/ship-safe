# ShipSafe Architecture — verified in Phase 1

Verified against the code and executed tests on branch `feat/p1-foundation` (2026-11-11; updated 2026-11-12 after the independent-review remediation). Where this file and the code disagree, the code wins; fix this file.

**Not built:** Bitbucket or any hosted Git connector, pull-request discovery, a test runner, automated Claude/API invocation, authentication, webhooks, CI gating. See `docs/IMPLEMENTATION_STATUS.md`.

## Runtime layout

```text
Browser ── React SPA (Vite dev server, 127.0.0.1:5173)
              │  fetch /api/*  (Vite proxy → 127.0.0.1:8000)
              ▼
FastAPI app (uvicorn, 127.0.0.1:8000)            backend/app/main.py
  ├─ config.load_settings()      SHIPSAFE_* env → Settings (allowlist, paths)
  ├─ db.migrate() / db.session() SQLite: scans, ai_reviews
  ├─ LocalGitProvider            allowlist check, read-only `git` subprocesses
  ├─ scanner.scan_changes()      provider ChangeSet → AST heuristics → report dict
  ├─ ai_handoff                  ZIP export, strict JSON import validation
  └─ demo_seed                   generates the synthetic LedgerLite repository
```

Both servers bind to loopback. `scripts/dev.py` starts them with `--host 127.0.0.1`; nothing in the repository binds to a public interface.

## Backend components (`backend/app`)

| Module | Responsibility |
|---|---|
| `main.py` | `create_app(demo_root, db_file, allowed_root)` factory, all routes, HTTP error mapping. Module-level `app = create_app()`. |
| `config.py` | `Settings` and `load_settings()`. The demo directory is always an allowed root; `SHIPSAFE_ALLOWED_ROOT` adds one more. Refuses a drive/filesystem root. |
| `errors.py` | `ScanError` → `ProviderError` → `RepositoryAccessDenied`, `RepositoryNotFound`, `RefNotFound`; `ConfigError`. |
| `providers/base.py` | Provider-neutral contracts: `RepositoryRef`, `PullRequestRef`, `FileDelta`, `ChangeSet`; protocols `RepositoryProvider`, `PullRequestProvider`, `ChangeProvider`; `valid_ref()`. |
| `providers/local_git.py` | `LocalGitProvider` (repository discovery + change retrieval) and `run_git()`. The only provider implementation. |
| `scanner.py` | `scan_changes(provider, repository, base, head)` orchestration, `scan_repository(path, base, head)` convenience wrapper, AST helpers, three risk heuristics, report assembly. |
| `ai_handoff.py` | `review_context()`, `context_digest()`, `handoff_zip()`, Pydantic import models, `validate_review_binding()`, `saved_review()`. |
| `db.py` | `session()` context manager and forward-only `migrate()` keyed on `PRAGMA user_version`. |
| `demo_seed.py` | `ensure_demo_repo()` creates or repairs `main` plus six branches; `DEMO_BRANCH_FILES` content, `DEMO_BRANCHES` metadata. |

## HTTP API

All routes are unauthenticated and intended for loopback use only. CORS allows `http://localhost:5173` and `http://127.0.0.1:5173`, methods GET/POST. A `TrustedHostMiddleware` (outermost) refuses with 400 any request whose `Host` is not `127.0.0.1`, `localhost`, or `[::1]`; this is the DNS-rebinding defence.

| Method and path | Success | Errors |
|---|---|---|
| `GET /api/health` | 200 `{status, version, mode}` | |
| `GET /api/demo` | 200 `DemoInfo` | |
| `POST /api/scans` | 201 `Report` + `binding` (persisted) | 403 outside allowlist · 400 invalid path, not a repository, invalid or unknown ref, Git failure · 422 body validation |
| `GET /api/scans?limit=1..100` (default 12) | 200 `ScanHistory[]` (each with `binding`), newest first | 422 |
| `GET /api/scans/{id}` | 200 `Report` + `binding` | 404 |
| `GET /api/scans/{id}/export` | 200 `Report` + `binding` as attachment | 404 |
| `GET /api/scans/{id}/ai/handoff` | 200 `application/zip` | 404 |
| `GET /api/scans/{id}/ai/context` | 200 `{scan_id, context_digest, review_count}` | 404 |
| `POST /api/scans/{id}/ai/reviews` | 201 saved `AIReview` | 404 · 413 over 256 KiB · 422 malformed or schema-invalid · 409 wrong scan, digest, file, or static finding ID |
| `GET /api/scans/{id}/ai/reviews` | 200 `AIReview[]`, newest first, max 25 | 404 |
| `GET /api/scans/{id}/ai/reviews/latest` | 200 `AIReview` or `null` | 404 |
| `GET /api/repository/status` | 200 `{repo, main_sha, branches}` for the demo repository | 500 |
| `GET /api/bitbucket/status` | 200 `{configured, provider, workspace, repositories}`; never the credential | |
| `GET /api/bitbucket/repositories` | 200 `BitbucketRepository[]` (approved repositories only) | Bitbucket errors, below |
| `GET /api/bitbucket/repositories/{slug}/pull-requests?state=open\|merged\|declined` | 200 `{repository, state, pull_requests: PullRequestListItem[], truncated}` | 422 bad state · Bitbucket errors |
| `GET /api/bitbucket/repositories/{slug}/pull-requests/{id}` | 200 `PullRequestDetail` | Bitbucket errors |
| `POST /api/bitbucket/repositories/{slug}/pull-requests/{id}/scans` | 201 `Report` with `binding` (persisted) | 409 `head_commit_unavailable`, `base_commit_unavailable`, `head_changed` · 422 body · Bitbucket errors |

Request body for `POST /api/scans` (`ScanRequest`): `repository_path` (optional, ≤1024 chars; omitted means the demo repository), `base_ref` (default `main`), `head_ref` (default `feature/release-candidate`), each ref 1–150 chars.

Error bodies are `{"detail": string}` except FastAPI request-validation 422s, where `detail` is a list of `{loc, msg, type}` objects. The frontend handles both.

### Bitbucket routes (Phase 2 task 4; mocked HTTP only, never run against live Bitbucket)

Real example responses, captured from the mocked fixtures: `docs/example-bitbucket-responses.json`. `test_published_example_responses_match_the_current_contract` fails if a response gains or loses a key without that file being regenerated.

All routes are read-only towards Bitbucket (GET requests to `api.bitbucket.org` only). The backend declares no Pydantic response models, so Swagger (`/docs`) shows the routes but not these shapes; this section and the example file are the contract.

**Error shapes** (three kinds; a client should read `detail` and, when present, `code`):

| Source | Body | Where |
|---|---|---|
| Bitbucket routes, handled errors | `{"detail": string, "code": string}` | every row of the table below |
| Request validation (FastAPI) | `{"detail": [{"loc", "msg", "type", ...}]}`, status 422, no `code` | bad `state` query, malformed `head_commit` |
| No matching route | `{"detail": "Not Found"}`, status 404, no `code` | e.g. a slug containing `/` |
| Local scan and review routes | `{"detail": string}`, no `code` (unchanged from v0.2) | `/api/scans*` |

| Situation | Status | `code` |
|---|---|---|
| Bitbucket not configured on the server | 503 | `bitbucket_not_configured` |
| Repository not on the allowlist | 403 | `repository_not_allowed` |
| Repository, pull request, or commit (merge base) not found | 404 | `repository_not_found`, `pull_request_not_found`, `commit_not_found` |
| Malformed pull request id (not digits) | 400 | `invalid_request` |
| Diff too large for Bitbucket (HTTP 555) | 422 | `diff_too_large` |
| Bitbucket rejected the server's credential (401/403) | 502 | `bitbucket_auth_failed` |
| Timeout, unreachable, rate limit, 502/503/504 after retries | 503 | `bitbucket_unavailable` |
| Any other unexpected Bitbucket response | 502 | `bitbucket_error` |
| Head or target commit unreadable (fork, deleted branch) | 409 | `head_commit_unavailable`, `base_commit_unavailable` |
| `head_commit` in the request differs from the current head | 409 | `head_changed` |

**Shapes** (`?` = may be null):

- `BitbucketStatus`: `{configured: bool, provider: "bitbucket-cloud"?, workspace: string?, repositories: string[]}`. Never contains the credential. Always 200, also when not configured.
- `BitbucketRepository`: `{id: "workspace/slug", slug, name, url, default_branch?}`. `url` is built by ShipSafe from the validated slug.
- `PullRequest` (the `PullRequestRef` fields): `{provider, repository_id, id: string, title, state: "open"|"merged"|"declined", source_ref, target_ref, source_sha?, target_sha?, author?, url, updated_at?}`. `url` is built by ShipSafe, never copied from Bitbucket's payload. SHAs are full 40-character lowercase hex or null.
- `PullRequestList` (`GET …/pull-requests?state=open|merged|declined`, default `open`, at most 200 items in Bitbucket's order): `{repository: BitbucketRepository, state, pull_requests: PullRequestListItem[], truncated: bool}`. `truncated` is true only when Bitbucket has more pull requests in that state than the list returns (more than `MAX_PULL_REQUESTS = 200`); a list of exactly 200 with nothing after it is `false`. There is no paging parameter: when `truncated` is true the remaining pull requests cannot be listed through ShipSafe, so the UI should say that only the first 200 are shown. Added 2026-11-13; older clients that ignore the key are unaffected.
- `PullRequestListItem`: `PullRequest` + `{scan_count: int, latest_scan: PullRequestScan?, stale_checked: bool}`.
- `PullRequestDetail`: `PullRequest` + `{repository, scannable: bool, not_scannable_code?, not_scannable_reason?, stale_checked: bool, scans: PullRequestScan[]}` (newest first, at most 25).
- `PullRequestScan`: `{id, created_at, summary, binding}`. `summary` is the report's summary.
- `ScanHistory` item: the v0.2 fields `{id, created_at, repo_name, base_ref, head_ref, duration_ms, summary}` + `binding`.
- `Report` responses (`POST` of either scan route, `GET /api/scans/{id}`, export): the stored report (`docs/example-scan-report.json`) + `binding`.
- Pull request scan request: optional body `{"head_commit": "<40 lowercase hex>"}`. Send the `source_sha` the user is looking at; the scan is then refused with 409 `head_changed` if the pull request has moved. Without a body the current head is scanned.

**`binding`** (every scan response): `{provider: "local-git"|"bitbucket-cloud", repository_id?, pull_request_id?, base_commit?, head_commit?, comparison: "direct"|"merge-base", stale: bool, stale_at?, stale_checked: bool}`. Full SHAs live here. It is read from the `scans` columns and is **not** part of the stored report, the Claude handoff ZIP, or the review `context_digest`. Rows from before migration 2 have null `repository_id` and commits ("not commit-bound"). Local scans have `pull_request_id: null` and `comparison: "direct"`; stale never applies to them.

**Comparison.** A pull request is compared from the merge base of target and head (`GET /merge-base/{target}..{head}`) to the head, which is what Bitbucket's pull request view shows. `binding.base_commit` is the merge base, not the target tip. In the report, `base_ref`/`head_ref` are the branch names, `base_sha`/`head_sha` the 12-character forms, and `repository_path` the repository's Bitbucket web URL.

**Stale state — how to read it.** A pull request scan is stale when its `head_commit` differs from the pull request's current head. The target branch moving does not make a scan stale.

| `stale` | `stale_checked` | Meaning | Suggested UI |
|---|---|---|---|
| true | true | Compared with Bitbucket's head in this response: outdated | "Stale" badge |
| false | true | Compared in this response: matches the current head | "Current" |
| true | false | Recorded stale at `stale_at`; not re-checked now (it can only become current again if the head returns to this commit) | "Stale (as of `stale_at`)" |
| false | false | Not known to be stale; **not checked** in this response | "Not checked" — never "Current" |

Where `stale_checked` is true:

| Response | Checked? |
|---|---|
| `POST …/pull-requests/{id}/scans` (the new scan) | Always true; the scan is refused unless the head is readable |
| `GET …/pull-requests/{id}` (detail and every scan in it) | True unless the head commit is unreadable (fork, deleted branch) |
| `GET …/pull-requests` (list) | True only for pull requests that already have scans, within the first 20 such pull requests, and whose head is readable. False otherwise |
| `GET /api/scans`, `GET /api/scans/{id}`, export | Always false: these never contact Bitbucket |

**The 20-lookup limit on the list and its impact.** Bitbucket's list payload carries abbreviated hashes only, so knowing a pull request's current head needs one more lookup per pull request (one detail request plus up to two commit requests to expand short hashes). The list does this only for pull requests that already have scans, and for at most `STALE_CHECKS_PER_LIST = 20` of them per request, in Bitbucket's order. Consequences:

- A list call costs at most 2 Bitbucket requests plus up to 60 for stale checks. Each request has a 15 s timeout and up to 2 retries, so a slow Bitbucket makes the list slow; there is no overall time budget.
- Beyond the 20th scanned pull request, items show `source_sha: null`, `target_sha: null` and `stale_checked: false`; their `latest_scan.binding` shows the last recorded state.
- Unscanned pull requests always show null SHAs in the list; this is not an error. Open the detail for full SHAs.
- Nothing is lost: opening the detail, or scanning, always checks that pull request.
- Raising the limit is a one-line constant change in `main.py`, at the cost of more requests per list.

**Import analysis** over Bitbucket reads at most `BITBUCKET_IMPORT_READS = 200` files (one request each). When cut, the report's `summary` gains `import_analysis_truncated: true` and `import_files_skipped: int`, and the handoff ZIP lists an `INCOMPLETE` limitation. These two keys exist **only** on a report that was cut; every other report has exactly the pinned summary keys (tested for local scans, Bitbucket scans under the limit, and exactly at the limit).

## Data contracts

The TypeScript mirror of every response is `frontend/src/types.ts`. The backend has no response models; the report is a plain dict built in `scanner.scan_changes`. `backend/tests/test_foundation.py::test_report_shape_matches_the_published_v0_2_example` pins its key set to `docs/example-scan-report.json`.

**Report** (stored verbatim as `scans.report_json`):
`id` (UUID4), `created_at` (UTC ISO 8601), `repo_name`, `repository_path` (local path, or the Bitbucket web URL for a pull request scan), `base_ref`, `head_ref`, `base_sha`, `head_sha` (first 12 hex chars), `duration_ms`, `summary{files_changed, lines_added, lines_removed, finding_count, risk_score, recommendation, test_status, truncated, files_omitted}`, `files[]{path, status, additions, deletions, changed_functions[], diff, diff_truncated, diff_lines_omitted}`, `findings[]{id, category, severity, title, file, line, status, evidence, explanation, recommendation}`, `affected_modules[]{path, imports_changed[]}`, `test_suggestions[]{category, file, scenario}`, `disclaimer`.

The four completeness fields (`summary.truncated`, `summary.files_omitted`, `files[].diff_truncated`, `files[].diff_lines_omitted`) were added in the Phase 1 remediation; everything else is the v0.2 shape. Reports stored before then lack them, and every reader (frontend types, ZIP limitations) treats absence as "not truncated".

Constants that shape it: at most 300 changed files (`summary.files_omitted` counts the rest), each `diff` cut to 140 lines plus a final `... [N more diff lines not shown; ...]` marker line when cut, for local scans the first 250 head-tree entries (files of any type) inspected for imports, silently; for Bitbucket scans at most 200 Python files read, reported when cut (two optional summary keys, see "Bitbucket routes"), `findings[].status` always `"suspected"`, `summary.test_status` always `"not_run"`. `summary.lines_added` / `lines_removed` cover the listed files only. Risk score is `min(99, Σ severity weight + 3 if any file changed)` with weights critical 42, high 26, medium 12, low 4. It is a prioritisation number, not a probability.

**Handoff and review schema** (`shipsafe.ai-review.v1`): unchanged from v0.2 and documented in `docs/CLAUDE-CODE-HANDOFF.md`. `context_digest` is SHA-256 over canonical JSON of `review_context(report)`. Because the digest is recomputed from the stored report on every import, **changing which report keys `review_context` reads would invalidate reviews for existing scans**; that needs a new schema version, not an edit.

**Provider types** (`providers/base.py`; `RepositoryRef` and `PullRequestRef` are served by the Bitbucket routes): see "Provider interfaces" below.

## Scan data flow

1. `POST /api/scans` validates the body with Pydantic.
2. `LocalGitProvider.get_repository()` resolves the path (symlinks and `..` included), checks it against the allowed roots, checks for `.git`, then asks Git for the directory that actually holds the objects (`git rev-parse --git-common-dir`) and checks that against the allowed roots too, so a redirecting `.git` file cannot reach outside.
3. `scan_changes()` calls `provider.get_changes()`: resolve both refs to full SHAs (`git rev-parse --verify`), list changed files (`git diff --name-status -z`), count lines (`--numstat -z`), fetch each file's patch (`-- ./<path>`). Every Git command runs with `--literal-pathspecs`, so a file name is never read as a glob or pathspec magic.
4. For each `.py` file it reads the before and after text (`git show sha:path`), maps changed hunks to enclosing functions with `ast`, and runs the three heuristics in `analyze_risks()`.
5. `import_dependencies()` lists the head tree and parses the Python files among its first 250 entries for direct imports of changed modules (Bitbucket scans instead read at most 200 Python files and report a cut).
6. The report dict is inserted into `scans` and returned.

Nothing in this path checks out, builds, imports, or executes repository code.

## Persistence

SQLite file at `SHIPSAFE_DB_PATH` (default `backend/.shipsafe-data/scans.db`, git-ignored).

| Table | Columns |
|---|---|
| `scans` | `id` TEXT PK, `created_at` TEXT, `report_json` TEXT; since version 2: `provider` TEXT (default `local-git`), `repository_id`, `pull_request_id`, `base_commit`, `head_commit` (full SHAs), `stale_at`; index `(provider, repository_id, pull_request_id, created_at)` |
| `ai_reviews` | `id` TEXT PK, `scan_id` TEXT → `scans.id`, `imported_at` TEXT, `review_json` TEXT; index `(scan_id, imported_at)` |

Schema version is `PRAGMA user_version` (currently 2; version 1 is identical to the v0.2 schema). Mechanism, rules, and version 2 are in `docs/MIGRATIONS.md`. Rows are never deleted and `report_json` is never rewritten; the only update is `db.sync_stale` setting or clearing `scans.stale_at`, called by the Bitbucket pull request routes.

## Frontend (`frontend/src`)

A single component file, `App.tsx`, with `useState` page switching and no router. Pages: Overview, Code changes, Risk findings, Test intelligence, Claude Review, Scan history, Configuration. `api<T>()` is the only fetch wrapper. On load it fetches `/api/demo` and `/api/scans`, opens the newest stored scan, or runs the default demo scan if history is empty. Export and handoff are plain download links.

The UI can only choose among the demo repository's branches. Scanning another authorized repository is possible through the API but has no UI.

## Demo generator and settings

`demo_seed.ensure_demo_repo()` runs at API startup. It writes the LedgerLite files, commits them on `main`, and creates six branches, each one commit on top of `main`: `feature/release-candidate`, `feature/auth-regression`, `feature/pricing-regression`, `feature/api-breaking`, `feature/docs-only`, `feature/safe-cleanup`. It is idempotent: a complete repository is left untouched, and a branch that is missing or has no commit of its own (a seed interrupted part way) is rebuilt from `main`. Repair never discards work: if a tracked file carries an uncommitted change that the seeder itself did not write, startup fails with a `ConfigError` naming the file; untracked files are neither removed nor committed (only the demo's own files are ever `git add`ed). It refuses, with `ConfigError`, to touch a non-empty directory that is not a repository or a repository it did not generate; a generated repository is recognised by the `shipsafe.demo=true` marker in its config, or, for repositories seeded before the marker existed, by the root commit's subject *and* synthetic author e-mail. Demo commits are made with `commit.gpgsign=false` in the repository's own config. These are the only Git writes ShipSafe ever makes, and only inside the demo directory. `GET /api/demo` serves `DEMO_BRANCHES` as the branch picker's data.

Settings are three optional `SHIPSAFE_*` environment variables, four optional `SHIPSAFE_BITBUCKET_*` variables (all-or-nothing), plus the frontend's `VITE_API_BASE`; see `docs/CONFIGURATION.md`. The Bitbucket token is the only secret; `config.Secret` keeps it out of `repr`, JSON, and logs.

## Tests

Backend only, under `backend/tests` (236 tests on 2026-11-13). Each test builds its own demo repository and database in a pytest temp directory; none touches `backend/demo-repo` or the real `scans.db`. Every `TestClient` is created with `base_url="http://127.0.0.1"` because the API refuses other `Host` headers. No test contacts Bitbucket: Bitbucket tests use `httpx.MockTransport`.

| File | Tests | Covers |
|---|---|---|
| `test_scanner.py`, `test_ai_handoff.py` | 24 | The original v0.2 suite (only the `TestClient` base URL changed): demo branches, findings per branch, allowlist, export, handoff ZIP, review import and rejection cases |
| `test_phase1_regressions.py` | 32 | The Phase 1 defect fixes (textconv, encoding, file names, parser exhaustion, error codes, interrupted demo seed), real commits and changed lines, docs-only, restart persistence, the scan leaves the repository unmodified |
| `test_foundation.py` | 15 | Provider protocol conformance, orchestration over an in-memory provider, report shape pinned to the example, settings and allowlist rules, CORS, migration runner |
| `test_phase1_remediation.py` | 30 | The independent-review fixes: Host-header refusal, demo-dir drive root, literal pathspecs, repository-config commands never run during a scan, redirecting `.git` files, seeder safety, truncation reporting |
| `test_bitbucket_provider.py` | 41 | P2 task 1: Bitbucket Cloud provider against mocked HTTP (allowlist, pagination, pull requests, comparisons, auth, retries, caps) |
| `test_bitbucket_settings.py` | 32 | P2 task 2: `SHIPSAFE_BITBUCKET_*` loading, partial configuration refused, token never in `repr`, logs, or responses |
| `test_migration_2.py` | 17 | P2 task 3: schema version 2, row preservation, rollback, `insert_scan`, `sync_stale` |
| `test_bitbucket_api.py` | 45 | P2 task 4: Bitbucket routes end to end over mocked HTTP, merge-base comparison, stale marking and `stale_checked`, error mapping, import-analysis bound, report-shape guard, example-file drift guard |

Frontend: `frontend/src/App.test.tsx` (2 tests, `npm test`) is a smoke test of the existing demo dashboard with `fetch` stubbed; it uses `docs/example-scan-report.json` as its fixture. There is no lint step. The dashboard has also been exercised in headless Chrome by throwaway scripts (recorded in the session handoff: all six demo branches, export and ZIP per scan; re-run on 2026-11-13 against Vite 5 and Vite 6 with identical results); those scripts are not part of the repository.

## Phase 2 dependency points

Where Bitbucket work attaches, and what each point still lacks:

| Phase 2 need | Attach here | Gap today |
|---|---|---|
| Bitbucket connector | New `providers/bitbucket.py` implementing the three protocols | `PullRequestProvider` has no implementation or test double; `main.py` constructs exactly one provider |
| Scan a pull request | `POST /api/bitbucket/repositories/{slug}/pull-requests/{id}/scans` | Done in P2 task 4 (backend, mocked HTTP). No dashboard screen calls it |
| Merge-base comparison | `BitbucketCloudProvider.merge_base()` then `get_changes(merge base, head)` | Done in P2 task 4 for pull request scans. Local branch scans still diff the two commits directly |
| Renames | `FileDelta.status` | Renames are reported as a delete plus an add |
| Truncated or oversized diffs | `ChangeSet.truncated` / `ChangeSet.omitted` | Surfaced in the report, UI, and ZIP since the Phase 1 remediation. A remote provider must fill `omitted` itself |
| Commit binding and stale detection | `scans.base_commit` / `head_commit` / `stale_at`, `db.insert_scan`, `db.sync_stale`, `binding` in responses | Done in P2 task 4: pull request scans are bound to full SHAs and marked stale when the head moves. The Claude handoff ZIP does not carry the binding yet (Phase 3) |
| Credentials and workspace settings | `config.Settings.bitbucket` | Done (P2 task 2): settings load and `create_app` builds the provider into `app.state.bitbucket`; the Bitbucket routes use it |
| Repository and PR screens | `frontend/src/types.ts`, `api<T>()` | The endpoints exist (P2 task 4). One single-file component (`App.tsx`), no router, no test harness; no screen calls them yet (task 5) |
| HTTP calls to Bitbucket | `providers/bitbucket.py` | The Bitbucket routes make outbound GET requests to `api.bitbucket.org` when configured. Never exercised against the live service |

## Provider interfaces (Phase 2 seam)

```text
RepositoryProvider   list_repositories() -> [RepositoryRef]
                     get_repository(repository_id) -> RepositoryRef
PullRequestProvider  list_pull_requests(repository, state="open") -> [PullRequestRef]
                     get_pull_request(repository, pull_request_id) -> PullRequestRef
ChangeProvider       resolve_commit(repository, ref) -> full SHA
                     get_changes(repository, base_ref, head_ref, max_files=300) -> ChangeSet
                     list_files(repository, commit) -> [path]
                     read_file(repository, commit, path) -> text ("" if absent)
Scan orchestration   scanner.scan_changes(provider: ChangeProvider, repository, base, head) -> Report
```

`LocalGitProvider` implements `RepositoryProvider` and `ChangeProvider`. Since 2026-11-12 (Phase 2, unmerged) `providers/bitbucket.py` holds `BitbucketCloudProvider`, which implements all three protocols and is tested against mocked HTTP only; `create_app` constructs it when `SHIPSAFE_BITBUCKET_*` is configured (`app.state.bitbucket`, otherwise `None`), and the `/api/bitbucket/*` routes call it. `test_scan_orchestration_works_with_a_non_git_provider` runs the orchestration against an in-memory provider to show the seam does not depend on Git or the filesystem. Field-level documentation is in the dataclass docstrings.

## Security boundaries

| Boundary | How it is enforced | Residual risk |
|---|---|---|
| Which repositories can be read | Resolved path must be an allowed root or beneath one, and so must the directory `git rev-parse --git-common-dir` reports; default is the demo repository only; a drive root is refused at startup for both roots | Tested 2026-11-12: `..`, UNC admin shares, `\\?\` prefixes, 8.3 short names, junctions and a redirecting `.git` file are all denied or resolved to the real path. A UNC `repository_path` is still resolved (touching the network) before being denied. |
| Git argument injection | Argument arrays, no shell; refs must match `valid_ref`; every Git command runs with `--literal-pathspecs`; per-file diffs use `-- ./<path>` | Tested with tree entries `*`, `*.py`, `?.py`, `[a].py`, `:!a.py`, `::y.py`, `:(top)z.py`, `-rf.py`: each patch covers exactly its own file. |
| Repository-controlled command execution | Scans run only `rev-parse`, `diff --no-ext-diff --no-textconv --no-renames`, `show`, `ls-tree`; none touches the index or working tree | Tested 2026-11-12 with `core.fsmonitor`, `diff.external`, driver `command`/`textconv`, `filter.*.clean/smudge`, `core.hooksPath` hooks, `core.pager`, aliases, `gpg.program`, `core.sshCommand`, `credential.helper`, `core.editor`, merge drivers all armed: none ran during a scan (they do run on `git add`, which ShipSafe never issues outside the demo directory). Guarded by `test_scan_does_not_run_commands_named_in_the_repository_config`. |
| Hostile source text | Parsed with `ast` only, never imported; parser exhaustion is caught; Git output decoded as UTF-8 with replacement | Heuristics are shallow and can be evaded or over-triggered. |
| Imported AI review | 256 KiB cap, `extra="forbid"` schema, scan ID + digest + file + static-ID binding; stored separately; labelled unverified | Authorship cannot be verified. The digest is not a signature. |
| Network exposure | Loopback bind, CORS limited to the local dashboard origin, `Host` header limited to loopback names (400 otherwise) | No authentication: anything that can reach 127.0.0.1:8000 with a loopback `Host` (other local users, local malware) has full access. Do not expose the port. A simple cross-origin POST (`text/plain`) still reaches `/ai/reviews` without a CORS preflight, but a blind write needs the scan ID and context digest. |
| Secrets | None are needed or read | |

## Known brittle areas (not changed in Phase 1)

- Scans run synchronously in the request and spawn several `git` processes per changed file plus one per inspected Python file (up to roughly 850 per scan, each with a 20 s timeout but no overall budget, and no cap on a single command's output size). About 0.5 s for the four-file demo scan on the Phase 1 Windows workstation; it will not scale to large diffs.
- The 300-file cap and the 140-line patch cut are now reported (`summary.truncated`, `files_omitted`, per-file `diff_truncated`), but the caps themselves are fixed constants.
- Reports keep only 12-character SHAs. Since Phase 2 task 4 the full SHAs are served in `binding` beside the report, but the Claude handoff ZIP still carries only the 12-character form (Phase 3).
- A failure inside `ensure_demo_repo` (for example Git missing from `PATH`) aborts startup with a raw traceback rather than a one-line message.
- Heuristics are tuned to the demo: three rules, Python only, absolute imports only.
- `GET /api/scans` parses every full report to build the summary list.
- The API version string (`0.2.0`) is hard-coded in `main.py` and again in `App.tsx`.
- No lint step. Frontend tests exist since 2026-11-13 (`npm test`: Vitest 5 with Testing Library in jsdom), so far only a smoke test of the demo dashboard. Toolchain: Vite 6.4.6, `@vitejs/plugin-react` 4.7, Vitest 5.1.0; `npm audit` reports 0 advisories (2026-11-13). The two advisories recorded for Vite 5.4.21 in Phase 1 are cleared by this upgrade. Node 22.12+ (or 24+) is required; Node 20 is unsupported and was not tested.
- The backend test suite emits a Starlette deprecation warning about `httpx`.
- The frontend has no favicon; the browser logs one 404 for `/favicon.ico` on each load.
