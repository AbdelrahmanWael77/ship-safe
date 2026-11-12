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
`id` (UUID4), `created_at` (UTC ISO 8601), `repo_name`, `repository_path`, `base_ref`, `head_ref`, `base_sha`, `head_sha` (first 12 hex chars), `duration_ms`, `summary{files_changed, lines_added, lines_removed, finding_count, risk_score, recommendation, test_status, truncated, files_omitted}`, `files[]{path, status, additions, deletions, changed_functions[], diff, diff_truncated, diff_lines_omitted}`, `findings[]{id, category, severity, title, file, line, status, evidence, explanation, recommendation}`, `affected_modules[]{path, imports_changed[]}`, `test_suggestions[]{category, file, scenario}`, `disclaimer`.

The four completeness fields (`summary.truncated`, `summary.files_omitted`, `files[].diff_truncated`, `files[].diff_lines_omitted`) were added in the Phase 1 remediation; everything else is the v0.2 shape. Reports stored before then lack them, and every reader (frontend types, ZIP limitations) treats absence as "not truncated".

Constants that shape it: at most 300 changed files (`summary.files_omitted` counts the rest), each `diff` cut to 140 lines plus a final `... [N more diff lines not shown; ...]` marker line when cut, at most 250 head-commit files inspected for imports, `findings[].status` always `"suspected"`, `summary.test_status` always `"not_run"`. `summary.lines_added` / `lines_removed` cover the listed files only. Risk score is `min(99, Σ severity weight + 3 if any file changed)` with weights critical 42, high 26, medium 12, low 4. It is a prioritisation number, not a probability.

**Handoff and review schema** (`shipsafe.ai-review.v1`): unchanged from v0.2 and documented in `docs/CLAUDE-CODE-HANDOFF.md`. `context_digest` is SHA-256 over canonical JSON of `review_context(report)`. Because the digest is recomputed from the stored report on every import, **changing which report keys `review_context` reads would invalidate reviews for existing scans**; that needs a new schema version, not an edit.

**Provider types** (`providers/base.py`, not exposed over HTTP yet): see "Provider interfaces" below.

## Scan data flow

1. `POST /api/scans` validates the body with Pydantic.
2. `LocalGitProvider.get_repository()` resolves the path (symlinks and `..` included), checks it against the allowed roots, checks for `.git`, then asks Git for the directory that actually holds the objects (`git rev-parse --git-common-dir`) and checks that against the allowed roots too, so a redirecting `.git` file cannot reach outside.
3. `scan_changes()` calls `provider.get_changes()`: resolve both refs to full SHAs (`git rev-parse --verify`), list changed files (`git diff --name-status -z`), count lines (`--numstat -z`), fetch each file's patch (`-- ./<path>`). Every Git command runs with `--literal-pathspecs`, so a file name is never read as a glob or pathspec magic.
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

`demo_seed.ensure_demo_repo()` runs at API startup. It writes the LedgerLite files, commits them on `main`, and creates six branches, each one commit on top of `main`: `feature/release-candidate`, `feature/auth-regression`, `feature/pricing-regression`, `feature/api-breaking`, `feature/docs-only`, `feature/safe-cleanup`. It is idempotent: a complete repository is left untouched, and a branch that is missing or has no commit of its own (a seed interrupted part way) is rebuilt from `main`. Repair never discards work: if a tracked file carries an uncommitted change that the seeder itself did not write, startup fails with a `ConfigError` naming the file; untracked files are neither removed nor committed (only the demo's own files are ever `git add`ed). It refuses, with `ConfigError`, to touch a non-empty directory that is not a repository or a repository it did not generate; a generated repository is recognised by the `shipsafe.demo=true` marker in its config, or, for repositories seeded before the marker existed, by the root commit's subject *and* synthetic author e-mail. Demo commits are made with `commit.gpgsign=false` in the repository's own config. These are the only Git writes ShipSafe ever makes, and only inside the demo directory. `GET /api/demo` serves `DEMO_BRANCHES` as the branch picker's data.

Settings are three optional `SHIPSAFE_*` environment variables plus the frontend's `VITE_API_BASE`; see `docs/CONFIGURATION.md`. No setting holds a secret.

## Tests

Backend only, under `backend/tests` (101 tests). Each test builds its own demo repository and database in a pytest temp directory; none touches `backend/demo-repo` or the real `scans.db`. Every `TestClient` is created with `base_url="http://127.0.0.1"` because the Host check refuses Starlette's default `testserver` host.

| File | Tests | Covers |
|---|---|---|
| `test_scanner.py`, `test_ai_handoff.py` | 24 | The original v0.2 suite (only the `TestClient` base URL changed): demo branches, findings per branch, allowlist, export, handoff ZIP, review import and rejection cases |
| `test_phase1_regressions.py` | 32 | The Phase 1 defect fixes (textconv, encoding, file names, parser exhaustion, error codes, interrupted demo seed), real commits and changed lines, docs-only, restart persistence, the scan leaves the repository unmodified |
| `test_foundation.py` | 15 | Provider protocol conformance, orchestration over an in-memory provider, report shape pinned to the example, settings and allowlist rules, CORS, migrations |
| `test_phase1_remediation.py` | 30 | The independent-review fixes: Host-header refusal, demo-dir drive root, literal pathspecs (tree built with `git mktree` so Linux-only names are covered on Windows), repository-config commands never run during a scan, redirecting `.git` files, seeder safety, truncation reporting. 16 of these fail on the pre-fix commit `f8967bc`; the other 14 guard behaviour that must keep working |

There are no frontend unit tests and no lint step. The dashboard has been exercised in headless Chrome by throwaway scripts (recorded in the session handoff: all six demo branches, export and ZIP per scan); those scripts are not part of the repository.

## Phase 2 dependency points

Where Bitbucket work attaches, and what each point still lacks:

| Phase 2 need | Attach here | Gap today |
|---|---|---|
| Bitbucket connector | New `providers/bitbucket.py` implementing the three protocols | `PullRequestProvider` has no implementation or test double; `main.py` constructs exactly one provider |
| Scan a pull request | `scanner.scan_changes()` already takes any `ChangeProvider` | `POST /api/scans` accepts only a local path and two refs; a PR scan needs an agreed request shape |
| Merge-base comparison | `ChangeProvider.get_changes()` | The local provider diffs the two commits directly (`git diff base head`), not from the merge base; Phase 2 must choose and document PR semantics |
| Renames | `FileDelta.status` | Renames are reported as a delete plus an add |
| Truncated or oversized diffs | `ChangeSet.truncated` / `ChangeSet.omitted` | Surfaced in the report, UI, and ZIP since the Phase 1 remediation. A remote provider must fill `omitted` itself |
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
- Reports keep only 12-character SHAs. Phase 2 commit binding needs the full SHA, which `ChangeSet` already carries.
- A failure inside `ensure_demo_repo` (for example Git missing from `PATH`) aborts startup with a raw traceback rather than a one-line message.
- Heuristics are tuned to the demo: three rules, Python only, absolute imports only.
- `GET /api/scans` parses every full report to build the summary list.
- The API version string (`0.2.0`) is hard-coded in `main.py` and again in `App.tsx`.
- No frontend tests or lint. `npm audit` reports 2 advisories (1 moderate, 1 high) in the build toolchain. Assessed 2026-11-12: every listed Vite advisory requires the dev server to be exposed with `--host`/`server.host` or run in middleware mode, which this project never does (loopback only, Vite's own `allowedHosts` rejects spoofed hosts); the esbuild advisory concerns esbuild's own serve mode, which Vite does not use; four of the advisory lines are for `launch-editor`, which is not in the dependency tree; the production bundle contains no Vite or esbuild code. No non-breaking update exists (5.4.21 is the newest 5.x; fixes start at Vite 6.4.4 and `@vitejs/plugin-react` 6 requires Vite 8). Accepted for Phase 1; upgrade scheduled with the Phase 2 toolchain work.
- The backend test suite emits a Starlette deprecation warning about `httpx`.
- The frontend has no favicon; the browser logs one 404 for `/favicon.ico` on each load.
