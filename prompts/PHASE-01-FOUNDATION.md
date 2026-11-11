# ShipSafe v1.0 — Phase 1 of 5: Audit, Stabilize, Prepare Architecture

> **Use in a new Claude Code session at the repository root. This is Phase 1 ONLY.**
> Fill in team metadata below before asking Claude to code.

- Phase integrator: `[NAME]`
- Backend owner: `[NAME]`
- Frontend owner: `[NAME]`
- QA/security reviewer: `[NAME]`
- Phase branch / tickets: `[BRANCHES / ISSUE LINKS]`
- Agreed handoff date: `[DATE]`

## Opening instruction to Claude
You are the technical lead for **Phase 1 only** of ShipSafe, a full-stack local-first Git risk scanner. Your collaborators are humans working on separately owned branches and may use their own Claude Code sessions. Read `CLAUDE.md`, `docs/TEAM_WORKFLOW.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/PHASE_HANDOFF.md`, and `docs/ACCEPTANCE_MATRIX.md` first. Inspect the actual code and Git status before edits. Verify, rather than assume, baseline claims.

**Do not start Bitbucket integration, automated AI invocation, test patch execution, webhooks, or Phase 2+ features. Do not overwrite teammates' in-progress files.**

## Product baseline to verify
- React + TypeScript + Vite frontend.
- FastAPI backend, SQLite history, Python AST and real Git CLI comparisons.
- Synthetic LedgerLite Git fixture with risky and harmless branches.
- Manual Claude Code ZIP handoff + strict JSON review import (no Claude API key).
- No native Bitbucket integration or sandboxed test runner yet.

## Phase deliverables

### 1. Code and risk audit
Map routes, API endpoints, data contracts, scanner, demo generator, persistence, handoff schema, environment settings, and tests. Identify bugs, brittle areas, security boundaries, and Phase 2 dependency points.

Update `docs/ARCHITECTURE.md` with verified component and data-flow documentation. Update `docs/IMPLEMENTATION_STATUS.md` with accurate NOT IMPLEMENTED / PARTIAL labels.

### 2. Stabilize the baseline
Ensure real local scanning works from API and React and that scanning `main` against `feature/release-candidate` uses actual commits and shows changed lines. Verify the docs-only branch avoids fabricated high-severity findings. Preserve scan history across restarts and the Claude handoff/export-import contract. Fix demonstrated failures only; create regression tests for fixes.

Handle non-existent repo paths, refs, invalid inputs, and predictable API errors. No new untrusted execution.

### 3. Prepare clean provider interfaces
Introduce minimal abstractions/interfaces for repository discovery, PR discovery, change/diff retrieval, and scan orchestration **without connecting to Bitbucket yet**. Preserve the existing local Git provider and API behavior. Keep types well documented so the Phase 2 backend and frontend owners can work in parallel.

### 4. Configuration & migration groundwork
Add or revise a safe `.env.example` and configuration documentation; do not include secrets. Keep local scanning deny-by-default outside authorized roots, enforce path allowlists, and ensure local-only default bind. Prepare a safe migration mechanism or design for adding Bitbucket metadata without resetting scans; only implement migrations if required by actual changes.

### 5. Verification
Run:
```bash
cd backend && python -m pytest -q
cd ../frontend && npm install && npm run build
```
Use existing dependencies where installed and log actual results. If frontend dependencies cannot be installed, record BLOCKED and the exact missing command/error; do not claim success. Test manual Claude export/import contract and persistence.

## Parallel human ticket split (avoid overlapping files)
- **Backend:** audit `backend/app`, introduce provider interfaces, configuration, backend tests.
- **Frontend:** inspect `frontend/src`, fix confirmed API/UI breaks, build validation.
- **QA/security:** independent regression scenarios, path validation, acceptance and evidence; no shared scanner edits without ticket ownership.
- **Integrator:** architecture, API contract decisions, review, merge, handoff.

Cross-boundary API changes must be agreed in a ticket **before** backend and frontend implementation. One person owns each shared schema.

## Phase 1 acceptance gates
- [ ] Existing real demo scans and original manual Claude handoff still work.
- [ ] Backend tests genuinely pass or actual failures are documented.
- [ ] Frontend production build verified or accurately BLOCKED.
- [ ] Provider interfaces are small, usable, and do not change existing behavior.
- [ ] No credentials, fake statuses, accidental repository writes, or history deletion.
- [ ] Docs reflect actual merged code; team PRs reviewed and approved.

## End-of-session handoff — mandatory
Provide changed-file list, actual commands and results, API types, migration decisions, limitations, and recommended Phase 2 ticket boundaries. Every contributor fills `templates/SESSION_HANDOFF.md`. After integrating reviewed changes, **the integrator** updates `docs/PHASE_HANDOFF.md`, `docs/ACCEPTANCE_MATRIX.md`, `docs/IMPLEMENTATION_STATUS.md`, and `docs/DECISIONS.md`. Tag the reviewed checkpoint `shipsafe-phase-1` only with team permission. **Stop. Do not implement Phase 2.**
