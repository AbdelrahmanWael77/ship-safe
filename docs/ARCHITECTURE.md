# ShipSafe Architecture — verified in Phase 1

Verified against the code and executed tests on branch `feat/p1-foundation` (2026-11-11). Where this file and the code disagree, the code wins; fix this file.

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

All routes are unauthenticated and intended for loopback use only. CORS allows `http://localhost:5173` and `http://127.0.0.1:5173`, methods GET/POST.

| Method and path | Success | Errors |
|---|---|---|
| `GET /api/health` | 200 `{status, version, mode}` | |
| `GET /api/demo` | 200 `DemoInfo` | |
| `POST /api/scans` | 201 `Report` (persisted) | 403 outside allowlist · 400 invalid path, not a repository, invalid or unknown ref, Git failure · 422 body validation |
| `GET /api/scans?limit=1..100` (default 12) | 200 `ScanHistory[]`, newest first | 422 |
| `GET /api/scans/{id}` | 200 `Report` | 404 |
| `GET /api/scans/{id}/export` | 200 `Report` as attachment | 404 |
| `GET /api/scans/{id}/ai/handoff` | 200 `application/zip` | 404 |
| `GET /api/scans/{id}/ai/context` | 200 `{scan_id, context_digest, review_count}` | 404 |
| `POST /api/scans/{id}/ai/reviews` | 201 saved `AIReview` | 404 · 413 over 256 KiB · 422 malformed or schema-invalid · 409 wrong scan, digest, file, or static finding ID |
| `GET /api/scans/{id}/ai/reviews` | 200 `AIReview[]`, newest first, max 25 | 404 |
| `GET /api/scans/{id}/ai/reviews/latest` | 200 `AIReview` or `null` | 404 |
| `GET /api/repository/status` | 200 `{repo, main_sha, branches}` for the demo repository | 500 |

Request body for `POST /api/scans` (`ScanRequest`): `repository_path` (optional, ≤1024 chars; omitted means the demo repository), `base_ref` (default `main`), `head_ref` (default `feature/release-candidate`), each ref 1–150 chars.

Error bodies are `{"detail": string}` except FastAPI request-validation 422s, where `detail` is a list of `{loc, msg, type}` objects. The frontend handles both.

## Data contracts

The TypeScript mirror of every response is `frontend/src/types.ts`. The backend has no response models; the report is a plain dict built in `scanner.scan_changes`. `backend/tests/test_foundation.py::test_report_shape_matches_the_published_v0_2_example` pins its key set to `docs/example-scan-report.json`.

**Report** (stored verbatim as `scans.report_json`):
`id` (UUID4), `created_at` (UTC ISO 8601), `repo_name`, `repository_path`, `base_ref`, `head_ref`, `base_sha`, `head_sha` (first 12 hex chars), `duration_ms`, `summary{files_changed, lines_added, lines_removed, finding_count, risk_score, recommendation, test_status}`, `files[]{path, status, additions, deletions, changed_functions[], diff}`, `findings[]{id, category, severity, title, file, line, status, evidence, explanation, recommendation}`, `affected_modules[]{path, imports_changed[]}`, `test_suggestions[]{category, file, scenario}`, `disclaimer`.

Constants that shape it: at most 300 changed files, each `diff` cut to 140 lines, at most 250 head-commit files inspected for imports, `findings[].status` always `"suspected"`, `summary.test_status` always `"not_run"`. Risk score is `min(99, Σ severity weight + 3 if any file changed)` with weights critical 42, high 26, medium 12, low 4. It is a prioritisation number, not a probability.

**Handoff and review schema** (`shipsafe.ai-review.v1`): unchanged from v0.2 and documented in `docs/CLAUDE-CODE-HANDOFF.md`. `context_digest` is SHA-256 over canonical JSON of `review_context(report)`. Because the digest is recomputed from the stored report on every import, **changing which report keys `review_context` reads would invalidate reviews for existing scans**; that needs a new schema version, not an edit.

**Provider types** (`providers/base.py`, not exposed over HTTP yet): see "Provider interfaces" below.

## Scan data flow

1. `POST /api/scans` validates the body with Pydantic.
2. `LocalGitProvider.get_repository()` resolves the path (symlinks and `..` included), checks it against the allowed roots, then checks for `.git`.
3. `scan_changes()` calls `provider.get_changes()`: resolve both refs to full SHAs (`git rev-parse --verify`), list changed files (`git diff --name-status -z`), count lines (`--numstat -z`), fetch each file's patch.
4. For each `.py` file it reads the before and after text (`git show sha:path`), maps changed hunks to enclosing functions with `ast`, and runs the three heuristics in `analyze_risks()`.
5. `import_dependencies()` lists the head tree and parses up to 250 Python files for direct imports of changed modules.
6. The report dict is inserted into `scans` and returned.

Nothing in this path checks out, builds, imports, or executes repository code.

## Persistence

SQLite file at `SHIPSAFE_DB_PATH` (default `backend/.shipsafe-data/scans.db`, git-ignored).

| Table | Columns |
|---|---|
| `scans` | `id` TEXT PK, `created_at` TEXT, `report_json` TEXT |
| `ai_reviews` | `id` TEXT PK, `scan_id` TEXT → `scans.id`, `imported_at` TEXT, `review_json` TEXT; index `(scan_id, imported_at)` |

Schema version is `PRAGMA user_version` (currently 1, identical to the v0.2 schema). Mechanism, rules, and the proposed Bitbucket-metadata migration are in `docs/MIGRATIONS.md`. Rows are never updated or deleted by any code path.

## Frontend (`frontend/src`)

A single component file, `App.tsx`, with `useState` page switching and no router. Pages: Overview, Code changes, Risk findings, Test intelligence, Claude Review, Scan history, Configuration. `api<T>()` is the only fetch wrapper. On load it fetches `/api/demo` and `/api/scans`, opens the newest stored scan, or runs the default demo scan if history is empty. Export and handoff are plain download links.

The UI can only choose among the demo repository's branches. Scanning another authorized repository is possible through the API but has no UI.

## Demo generator and settings

`demo_seed.ensure_demo_repo()` runs at API startup. It writes the LedgerLite files, commits them on `main`, and creates six branches, each one commit on top of `main`: `feature/release-candidate`, `feature/auth-regression`, `feature/pricing-regression`, `feature/api-breaking`, `feature/docs-only`, `feature/safe-cleanup`. It is idempotent: a complete repository is left untouched, and a branch that is missing or has no commit of its own (a seed interrupted part way) is rebuilt from `main`. It refuses, with `ConfigError`, to touch a non-empty directory that is not a repository or a repository whose `main` does not start with the generated root commit, so a mis-set `SHIPSAFE_DEMO_DIR` cannot be written to. Demo commits are made with `commit.gpgsign=false` in the repository's own config. These are the only Git writes ShipSafe ever makes, and only inside the demo directory. `GET /api/demo` serves `DEMO_BRANCHES` as the branch picker's data.

Settings are three optional `SHIPSAFE_*` environment variables plus the frontend's `VITE_API_BASE`; see `docs/CONFIGURATION.md`. No setting holds a secret.

## Tests

Backend only, under `backend/tests` (71 tests). Each test builds its own demo repository and database in a pytest temp directory; none touches `backend/demo-repo` or the real `scans.db`.

| File | Tests | Covers |
|---|---|---|
| `test_scanner.py`, `test_ai_handoff.py` | 24 | The original v0.2 suite, unmodified: demo branches, findings per branch, allowlist, export, handoff ZIP, review import and rejection cases |
| `test_phase1_regressions.py` | 32 | The Phase 1 defect fixes (textconv, encoding, file names, parser exhaustion, error codes, interrupted demo seed), real commits and changed lines, docs-only, restart persistence, the scan leaves the repository unmodified |
| `test_foundation.py` | 15 | Provider protocol conformance, orchestration over an in-memory provider, report shape pinned to the v0.2 example, settings and allowlist rules, CORS, migrations |

There are no frontend unit tests and no lint step. The dashboard was exercised once in headless Chrome during Phase 1 (recorded in the session handoff); that script is not part of the repository.

## Phase 2 dependency points

Where Bitbucket work attaches, and what each point still lacks:

| Phase 2 need | Attach here | Gap today |
|---|---|---|
| Bitbucket connector | New `providers/bitbucket.py` implementing the three protocols | `PullRequestProvider` has no implementation or test double; `main.py` constructs exactly one provider |
| Scan a pull request | `scanner.scan_changes()` already takes any `ChangeProvider` | `POST /api/scans` accepts only a local path and two refs; a PR scan needs an agreed request shape |
| Merge-base comparison | `ChangeProvider.get_changes()` | The local provider diffs the two commits directly (`git diff base head`), not from the merge base; Phase 2 must choose and document PR semantics |
| Renames | `FileDelta.status` | Renames are reported as a delete plus an add |
| Truncated or oversized diffs | `ChangeSet.truncated` | Set by the provider but not copied into the report or shown in the UI |
| Commit binding and stale detection | `ChangeSet.base_sha` / `head_sha` (full SHAs) | The report and database keep 12 characters; proposed migration 2 in `docs/MIGRATIONS.md` |
| Credentials and workspace settings | `config.Settings` | No credential fields exist; nothing reads a token |
| Repository and PR screens | `frontend/src/types.ts`, `api<T>()` | One single-file component (`App.tsx`), no router, no test harness; no repository or PR endpoints to call |
| HTTP calls to Bitbucket | — | No application code makes outbound HTTP calls; `httpx` is in `requirements.txt` but is used only by the test client |

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

`LocalGitProvider` implements `RepositoryProvider` and `ChangeProvider`. Nothing implements `PullRequestProvider`. `test_scan_orchestration_works_with_a_non_git_provider` runs the orchestration against an in-memory provider to show the seam does not depend on Git or the filesystem. Field-level documentation is in the dataclass docstrings.

## Security boundaries

| Boundary | How it is enforced | Residual risk |
|---|---|---|
| Which repositories can be read | Resolved path must be an allowed root or beneath one; default is the demo repository only; a drive root is refused at startup | On Windows a UNC `repository_path` is resolved (touching the network) before the allowlist check. Not tested. |
| Git argument injection | Argument arrays, no shell; refs must match `valid_ref`; paths follow `--` | File names beginning with `:` could be read as pathspec magic. Not reproducible on Windows; not tested. |
| Repository-controlled command execution | `git diff` always runs with `--no-ext-diff --no-textconv` | Other Git config in a scanned repository is still honoured by Git itself. Only scan repositories you trust to that extent. |
| Hostile source text | Parsed with `ast` only, never imported; parser exhaustion is caught; Git output decoded as UTF-8 with replacement | Heuristics are shallow and can be evaded or over-triggered. |
| Imported AI review | 256 KiB cap, `extra="forbid"` schema, scan ID + digest + file + static-ID binding; stored separately; labelled unverified | Authorship cannot be verified. The digest is not a signature. |
| Network exposure | Loopback bind, CORS limited to the local dashboard origin | No authentication and no Host-header check, so DNS rebinding is not mitigated. Do not expose the port. |
| Secrets | None are needed or read | |

## Known brittle areas (not changed in Phase 1)

- Scans run synchronously in the request and spawn several `git` processes per changed file plus one per inspected Python file. About 0.5 s for the four-file demo scan on the Phase 1 Windows workstation; it will not scale to large diffs.
- The 300-file cap is silent in the report (`ChangeSet.truncated` exists but is not surfaced), and patches are cut at 140 lines.
- Reports keep only 12-character SHAs. Phase 2 commit binding needs the full SHA, which `ChangeSet` already carries.
- A failure inside `ensure_demo_repo` (for example Git missing from `PATH`) aborts startup with a raw traceback rather than a one-line message.
- Heuristics are tuned to the demo: three rules, Python only, absolute imports only.
- `GET /api/scans` parses every full report to build the summary list.
- The API version string (`0.2.0`) is hard-coded in `main.py` and again in `App.tsx`.
- No frontend tests or lint. `npm install` reports 2 advisories (1 moderate, 1 high) in the build toolchain, including an esbuild development-server advisory (GHSA-67mh-4wv8-2f99). Their impact on this project has not been assessed.
- The backend test suite emits a Starlette deprecation warning about `httpx`.
- The frontend has no favicon; the browser logs one 404 for `/favicon.ico` on each load.
