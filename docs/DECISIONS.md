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
9. Vite 5.4.21 is accepted for Phase 1 (see `docs/ARCHITECTURE.md`, known brittle areas); the toolchain upgrade is Phase 2 work.

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
