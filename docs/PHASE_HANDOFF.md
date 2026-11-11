# Canonical Phase Handoff — Integrated Branch

**Current completed phase:** None (baseline v0.2 packaged; Phase 1 not started)

**Integrator:** TBD
**Integration commit:** TBD
**Next phase:** Phase 1 — Foundation

## Verified baseline
- Backend: 24 pytest tests passed in packaging environment on 2026-11-11.
- Frontend: build has not been run in this packaging environment; verify on a team machine.
- Native Bitbucket integration: not implemented.
- No-key Claude workflow: manual handoff and JSON import only.

## Current architecture
See `docs/ARCHITECTURE.md` and `README.md`.

## Changes merged this phase
- None. This is the starter kit.

## Test commands and factual output
- `cd backend && python -m pytest -q` → `24 passed in 3.07s` (packaging environment).

## Known limitations / blockers
- No isolated test execution and no native Bitbucket PR connector.
- Frontend npm install/build must be performed on a workstation with access to dependencies.

## Review decisions
- None yet. Record decisions in `docs/DECISIONS.md`.

## Start the next session with
`prompts/PHASE-01-FOUNDATION.md`, plus an assigned ticket and branch.

**Maintainer rule:** After each phase, replace this file with *verified integrated state*, not each contributor's unmerged claims. Contributors fill `templates/SESSION_HANDOFF.md` instead.
