# ShipSafe v1.0 — Phase 2 of 5: Bitbucket Repositories and Pull Requests

> **New Claude Code session after Phase 1 is reviewed and merged. Phase 2 ONLY.**

- Phase integrator: `[NAME]`
- Backend/Bitbucket owner: `[NAME]`
- Frontend owner: `[NAME]`
- QA/security reviewer: `[NAME]`
- Active branches/tickets: `[BRANCHES / TICKETS]`
- Provider decision: `Bitbucket Cloud` by default — change to Data Center **before coding** if your company uses self-hosted Bitbucket.

## Opening instruction to Claude
Read root `CLAUDE.md`, the team workflow, Phase 1 handoff and acceptance matrix, plus the current codebase. Inspect `git status`. Work on assigned branch/ticket only. **Implement Bitbucket read-only discovery and PR scanning while preserving local Git scans.** Do not start new AI-review logic or test execution.

## Scope
### A. Server-side Bitbucket provider
Implement a real Bitbucket **Cloud** connector through the current documented REST API. Keep a provider interface for future Bitbucket Data Center; don't silently assume their API contracts match.

- Configurable workspace and approved repositories, with server-side scoped read-only credentials, never in frontend or exports.
- Repository discovery, pagination, filters; open PR list, PR metadata, links, authors, source/target refs, exact commit SHA(s).
- Fetch changed-file summary, diff and/or approved local clone at immutable revisions as appropriate. Respect correct PR comparison semantics (merge-base/target snapshot as applicable) and document the choice.
- Handle adds, deletes, renames, truncated/oversized diffs, missing permissions, HTTP errors, timeouts, retries, pagination and rate limits.
- Never auto-clone arbitrary URL or execute repository code. Validate workspace and slug; restrict source hosts and local clone destinations.

### B. Scan orchestration and persistence
Extend scan relationships to provider/repository/PR/base+head commit. Keep old v0.2 local history intact. Associate findings with accurate code evidence; mark incomplete analysis when full context is unavailable. Mark previous assessments/reviews **stale** when PR head SHA changes. Use versioned, tested database migrations.

### C. Real React integration
Implement connected **Repositories**, **Pull Requests**, and **PR Analysis** screens. Use typed API contracts; show actual repository/PR data, loading/errors/empty states, scan progress, diff and findings, source commit and stale badges, "Open in Bitbucket" links. Mock mode must be explicitly identified as mock, never as live company data.

### D. Authentication and policy
Bitbucket credentials are separate from Claude Team sign-in. Keep them in approved server-side environment/secret storage with minimal scopes; do not embed tokens in Git remotes, client bundles, request URLs or logs. Do not request that the user paste credentials into Claude chat. No Bitbucket comments, approvals, PR writes, webhooks, or CI status publishing in this phase.

## Independent tests
- Mock HTTP responses for repository pagination and PR details.
- Verify authentication failures, 429/rate limits, timeouts, malformed payloads, deleted/renamed files and missing diff context.
- Verify commit binding, stale detection, repository allowlist, scan persistence/migration and unchanged local scanner behavior.
- Frontend tests for filters, select PR, scan, loading/errors and navigation. Build production frontend.
- If authorized real credentials are available to the human tester, run a separate **read-only smoke test** against an approved test repo and document results; do not claim live success otherwise.

## Parallel human ticket split
- **Backend owner:** Bitbucket provider + API + migrations.
- **Frontend owner:** Repo/PR screens against agreed typed contract and mock fixtures.
- **QA owner:** provider mock suites, security failure cases, real smoke-test checklist.
- **Integrator:** API contract review, merge order, stale semantics, evidence.

## Acceptance gates
- [ ] Synthetic local scanning preserved; original backend suite passes.
- [ ] Mock-provider repo → PR → scan → findings works end-to-end.
- [ ] Real connector implemented, with live credential verification explicitly PASS or BLOCKED.
- [ ] PR report bound to actual exact commit IDs and marked stale on update.
- [ ] No Git or Bitbucket writes, leaked credentials, fabricated test data, or unsafe clone paths.
- [ ] Migrations, frontend build, tests and handoff reviewed.

## Phase 2 handoff
Each ticket owner completes a `templates/SESSION_HANDOFF.md`. Integrator updates canonical architecture, implementation status, matrix, decisions and handoff with actual results and API contracts. Record specific Bitbucket type and unverified live operations. Checkpoint `shipsafe-phase-2` after human approval. **Stop; Phase 3 is a separate session.**
