# Architecture and Team Decision Log

For each new decision, append:

```text
## YYYY-MM-DD — Decision title
Decision owner:
Problem / tradeoff:
Decision:
Alternatives considered:
Security / product impact:
Related ticket / commit:
```

## Initial agreements to confirm
- Bitbucket Cloud versus Data Center: TBD.
- Who approves sharing proprietary diffs with Claude Code: TBD.
- Who can authorize isolated test execution: TBD.
- Who reviews database migrations: TBD.

## 2026-11-12 — Phase 1 is completed by a single owner
Decision owner: Nour Waled
Problem / tradeoff: No other team members are assigned; waiting would stall Phase 1.
Decision: The project owner manages and integrates Phase 1 alone, with Claude Code as implementation partner. Claude's test results are evidence; the owner approves every commit and the merge.
Alternatives considered: Wait for a roster; assign tickets to unavailable people.
Security / product impact: Independent backend/frontend/QA reviews did not happen; recorded as NOT TESTED in the acceptance matrix rather than claimed.
Related ticket / commit: `feat/p1-foundation`

## 2026-11-12 — The API answers only to loopback Host names
Decision owner: Nour Waled
Problem / tradeoff: The unauthenticated loopback API was reachable from any web page via DNS rebinding; CORS cannot stop a same-origin request.
Decision: `TrustedHostMiddleware` with `127.0.0.1`, `localhost`, `[::1]` (any port), added outermost. Tests create `TestClient(app, base_url="http://127.0.0.1")`.
Alternatives considered: Origin checks only (misses non-browser and no-Origin requests); authentication (Phase 5 scope).
Security / product impact: Closes the rebinding vector; local processes with a loopback Host still have full access (documented).
Related ticket / commit: remediation A1

## 2026-11-12 — Git paths are always literal; repository metadata must be inside the allowlist
Decision owner: Nour Waled
Problem / tradeoff: Tree entries such as `*` or `:!a.py` were interpreted as globs/pathspec magic, mis-attributing diffs; a one-line `.git` file could redirect a scan to any repository on the machine.
Decision: Every scanner Git command runs with `--literal-pathspecs` and per-file diffs use `-- ./<path>`; `get_repository()` also requires `git rev-parse --git-common-dir` to be under an allowed root (worktrees and submodules inside the allowlist keep working).
Alternatives considered: `:(literal)` magic (does not cover `::name`); refusing `.git` files outright (breaks worktrees).
Security / product impact: Report integrity on repositories cloned from Linux/macOS; allowlist cannot be bypassed from inside an allowed directory.
Related ticket / commit: remediation B1, B2

## 2026-11-12 — Demo seeder never destroys work and identifies its own repository
Decision owner: Nour Waled
Problem / tradeoff: Repairing a half-built demo repository used `checkout -f` and `git add .`, discarding uncommitted edits and committing stray files; any repository whose root commit had the demo subject was adopted.
Decision: Repair refuses (startup error naming the files) when a tracked file has a change the seeder did not write; only the demo's own files are added; the generated repository carries `shipsafe.demo=true`, and pre-marker repositories are recognised by root subject plus synthetic author e-mail. `SHIPSAFE_DEMO_DIR` gets the same drive-root check as `SHIPSAFE_ALLOWED_ROOT`.
Alternatives considered: Always refuse repair (reintroduces defect 10); stash user changes (silently moves work).
Security / product impact: A mis-set demo directory cannot be modified or made a drive-wide allowlist.
Related ticket / commit: remediation B4, B5

## 2026-11-12 — Report contract: additive completeness fields
Decision owner: Nour Waled
Problem / tradeoff: The 300-file and 140-line caps were silent; a cut report looked complete to humans and to Claude.
Decision: Add `summary.truncated`, `summary.files_omitted`, `files[].diff_truncated`, `files[].diff_lines_omitted`, a marker line at the end of a cut diff, a UI badge/notice, and dynamic ZIP `limitations`. Keys are optional for readers; stored reports are not rewritten; `docs/example-scan-report.json` and the pinning test were updated. No database migration.
Alternatives considered: Text-only markers (not machine-readable); defer to Phase 2.
Security / product impact: Reviewers can no longer mistake a truncated report for a complete one.
Related ticket / commit: remediation B3

## 2026-11-12 — Decisions carried forward from the Phase 1 session handoff
Decision owner: Nour Waled (confirm or object before merge)
1. The demo repository is always scannable, in addition to `SHIPSAFE_ALLOWED_ROOT`.
2. A drive or filesystem root is rejected as an allowed root (now also as the demo directory).
3. Schema versioning uses `PRAGMA user_version` with additive, forward-only migrations.
4. Full SHAs and provider metadata arrive as new columns in Phase 2, not by rewriting stored reports.
5. Renames are reported as a delete plus an add.
6. The initial repository import was committed directly to `main` as the starting point.
7. The demo seeder may rewrite branches inside the demo directory only when they are missing or carry no commit, and never touches a repository it did not generate.
8. `frontend/package-lock.json` is committed for reproducible builds.
9. Vite 5.4.21 is accepted for Phase 1 (see `docs/ARCHITECTURE.md`, known brittle areas); the toolchain upgrade is Phase 2 work. (Done 2026-11-13: Vite 6.4.6, see the entry of that date.)

## 2026-11-12 — Phase 2 starts on a branch stacked on unmerged Phase 1; Bitbucket Cloud
Decision owner: Nour Waled (confirm or object before merge)
Problem / tradeoff: The Phase 2 prompt expects Phase 1 to be reviewed and merged first. No reviewer is assigned, and the owner asked to continue with the next unfinished task.
Decision: Phase 2 work goes on `feat/p2-bitbucket-provider`, branched from `feat/p1-foundation`. `main` is untouched; Phase 1 still needs its human review and merge. The provider targets Bitbucket **Cloud** (the prompt's default); Data Center would be a separate provider. Agents follow `AGENTS.md` and hand off through `docs/IMPLEMENTATION_STATUS.md` and `NEXT_AGENT_PROMPT.md`.
Alternatives considered: Wait for the Phase 1 merge (stalls); commit Phase 2 onto the Phase 1 branch (mixes reviews).
Security / product impact: A Phase 1 review finding may require rebasing Phase 2. No live Bitbucket access has been configured or used.
Related ticket / commit: `feat/p2-bitbucket-provider`, commit `08b3b1b`

## 2026-11-12 — Bitbucket settings: all-or-nothing, token wrapped in `Secret`
Decision owner: Nour Waled (confirm or object before merge)
Problem / tradeoff: The token is the first secret in `Settings`. A plain string field would show in `repr(settings)` and in any dump of the settings; a half-set configuration could start the API silently without the integration.
Decision: `SHIPSAFE_BITBUCKET_WORKSPACE`, `_REPOSITORIES`, `_TOKEN` are required together (`_EMAIL` optional); anything partial or malformed raises `ConfigError` at startup, naming variables only. The token is held in `config.Secret`, which hides itself in `repr`/`str` and refuses copy, `asdict`, JSON, and pickle. `create_app` builds the provider into `app.state.bitbucket` and sends no request at startup.
Alternatives considered: `field(repr=False)` on a string (still leaks through `asdict`/JSON); validating credentials against Bitbucket at startup (network call on every start, and the demo must start offline).
Security / product impact: A wrong token is discovered on first use, not at startup. No route exposes the provider yet.
Related ticket / commit: P2 task 2, `feat/p2-bitbucket-settings`

## 2026-11-12 — Migration 2: stored stale marker, no backfill, PR metadata fetched live
Decision owner: Mohamed Elsayed (approved 2026-11-12); Nour Waled as migration reviewer before merge
Problem / tradeoff: Phase 2 needs scans bound to provider, repository, pull request and exact commits, and a way to show that a scan no longer matches the pull request head. `docs/MIGRATIONS.md` left three points open.
Decision:
1. Stale is a **stored marker** (`scans.stale_at`, NULL = not known stale), written by `db.sync_stale` from a comparison of `head_commit` with the pull request's current head. The comparison stays the source of truth: the marker is cleared if the head returns to the scanned commit. Stored rather than only computed so history and review screens can show the badge without a Bitbucket request, and so the first observation time is kept.
2. Existing local rows are **not backfilled** (`repository_id` and commits stay NULL). A migration that parsed `report_json` would break the additive-only rule, and 12-character SHAs cannot be turned into full ones.
3. Pull request title, URL and author are **not stored** in columns; they are fetched live.
4. The report JSON gains no key; full SHAs live only in the new columns. Local scans fill them now.
5. `ai_reviews` gets no stale column; a review's staleness is its scan's.
Alternatives considered: Computed-only staleness (every list view would need a live call per pull request); a boolean flag (loses when it was noticed); adding full SHAs to the report (changes the pinned report contract and the review digest input).
Security / product impact: Stored reports and imported reviews are untouched. A database migrated to version 2 is refused by older builds. Until task 4 calls `sync_stale`, no scan is ever marked stale.
Related ticket / commit: P2 task 3, `feat/p2-migration-2`

## 2026-11-12 — Bitbucket API (P2 task 4): comparison, stale rule, limits, error contract
Decision owner: Mohamed Elsayed (approved 2026-11-12 before implementation; contract accepted 2026-11-12 as the initial contract for task 5, subject to frontend integration validation)
Problem / tradeoff: Ten open points had to be settled before pull request scans could be exposed (see the task 3 checkpoint).
Decision:
1. A pull request is compared **merge base → head** (`GET /merge-base/{target}..{head}`), matching Bitbucket's own view. `base_commit` stores the merge base.
2. A scan is stale when the pull request **head** commit differs from the scanned one. The target branch moving does not make it stale.
3. Import analysis over Bitbucket reads at most **200** files. A cut report gains `summary.import_analysis_truncated` and `summary.import_files_skipped`, and the handoff ZIP lists an `INCOMPLETE` limitation.
4. HTTP 555 (diff too large) fails the scan with 422 `diff_too_large`; there is no per-file fallback.
5. A pull request whose head (or target) commit cannot be read through the approved repository is refused with 409; fork pull requests are therefore not scannable.
6. Routes and shapes are those in `docs/ARCHITECTURE.md` ("Bitbucket routes").
7. Full SHAs and the rest of the binding are served as `binding` beside the report in scan responses and the export. The stored report, the handoff ZIP and the review digest do not contain it.
8. The stale marker is refreshed on pull request list (only pull requests that already have scans, at most 20 lookups per request), on detail, and on scan.
9. Bitbucket not configured → 503 `bitbucket_not_configured`.
10. Provider errors map as tabled in `docs/ARCHITECTURE.md`; a rejected server credential is 502, not 401.
Approved by Mohamed Elsayed on 2026-11-12: point 3 adds two summary keys to a report **only when the analysis was cut**. Every other report keeps its exact shape (the pinned example and digest inputs are unchanged). This was chosen so the incompleteness travels with the report, as the Phase 2 prompt requires, while keeping "report JSON unchanged" true for all complete reports (guarded by `test_report_summary_keeps_the_pinned_shape_unless_import_analysis_was_actually_cut`).
Alternatives considered: target tip → head comparison (would show target-branch changes reversed); resolving every listed pull request (one or more requests per pull request on every list).
Security / product impact: All Bitbucket traffic is GET to `api.bitbucket.org`; no write, clone, or code execution. Verified against mocked HTTP only; the merge-base endpoint and all payload shapes are unconfirmed against the live service. The local scan's older silent cap (first 250 tree entries for import analysis) is unchanged and still unreported.
Related ticket / commit: P2 task 4, `feat/p2-bitbucket-api`

## 2026-11-12 — `stale_checked`: a scan's stale state says whether it was just checked
Decision owner: Mohamed Elsayed (asked that the UI can tell checked from unchecked stale status, 2026-11-12)
Problem / tradeoff: `binding.stale: false` was ambiguous: "compared with Bitbucket just now and current" or "never compared". The pull request list checks at most 20 scanned pull requests, the detail cannot check a pull request whose head is unreadable, and the stored-scan routes never contact Bitbucket.
Decision: every `binding` carries `stale_checked`, true only when the route that built the response compared that pull request with Bitbucket's current head. The detail response also carries a top-level `stale_checked`. No schema change: it describes the response, not the row.
Alternatives considered: a stored `stale_checked_at` column (migration 3; would let history screens say "last checked at"), or always re-checking every scanned pull request (unbounded requests).
Security / product impact: none on data. The UI must show `stale: false, stale_checked: false` as "not checked", never as "current". Documented with a reading table in `docs/ARCHITECTURE.md`.
Related ticket / commit: P2 task 4, `feat/p2-bitbucket-api`

## 2026-11-13 — Frontend toolchain: Vite 6.4.6 and Vitest 5.1.0; Node 22.12+
Decision owner: Mohamed Elsayed (approved 2026-11-13)
Problem / tradeoff: Task 5 needs frontend tests. The only Vitest line that works with Vite 5 (3.2.7) is unmaintained and adds three advisories, two rated critical, that will not be fixed. Patched Vitest needs Vite 6 or newer.
Decision: Upgrade `vite` from 5.4 to `^6.4.6` (one major) and add `vitest ^5.1.0`, `jsdom`, and Testing Library (`dom`, `react`, `user-event`, `jest-dom`) as dev dependencies. `@vitejs/plugin-react` stays at 4.7. `engines.node` is `^22.12.0 || >=24.0.0` because Vitest 5 requires it. Done as its own commit before any Task 5 feature work. No application source, proxy, or build setting changed.
Alternatives considered: Vitest 3.2.7 on Vite 5 (rejected: critical advisories, unmaintained). Vitest 4.1.12 (supports Node 20, but npm 10.9.9 crashes while resolving it from scratch, so the lock file would have to be made with npm 11). Vite 8 with plugin-react 6 (installed only with `--legacy-peer-deps`). Jest with ts-jest (477 packages and 22 advisories against about 200 and 0; no support for `import.meta.env` without a workaround).
Security / product impact: `npm audit` goes from 2 advisories (1 moderate, 1 high) to 0. Node 20 is no longer supported for the frontend. The bundle grows from 198.79 kB to 200.11 kB. The demo behaves the same in a scripted browser run on both versions. Not verified on Windows or with `vite preview`.
Related ticket / commit: P2 task 5, milestone 1, `feat/p2-frontend-screens`
