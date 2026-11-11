# Acceptance matrix — team-owned

Allowed status values: `PASS`, `FAIL`, `BLOCKED`, `NOT TESTED`. Only the integrator updates the canonical matrix after human review and integration.

| Phase | Gate | Status | Evidence / commands / commit | Reviewer |
|---|---|---|---|---|
| Baseline | Original backend tests | PASS | `cd backend && python -m pytest -q` → 24 passed (2026-11-11, packaging environment) | Initial package check; team reverify |
| Baseline | Frontend production build | NOT TESTED | Run `cd frontend && npm install && npm run build` locally | TBD |
| 1 | Local Git scanning + imports preserved | NOT TESTED | | |
| 1 | Architecture, provider interfaces, config, migration readiness | NOT TESTED | | |
| 1 | Frontend build and backend suites | NOT TESTED | | |
| 2 | Bitbucket repository + PR list (mock) | NOT TESTED | | |
| 2 | Read-only live Bitbucket (approved credentials) | NOT TESTED | | |
| 2 | Immutable commit-bound PR scan + stale detection | NOT TESTED | | |
| 3 | Scan/PR handoff package + strict JSON import | NOT TESTED | | |
| 3 | Correct commit binding; stale AI review warning | NOT TESTED | | |
| 4 | Explicit approval + isolated pytest execution | NOT TESTED | | |
| 4 | Baseline/head regression verification | NOT TESTED | | |
| 5 | End-to-end demo + release assessment export | NOT TESTED | | |
| 5 | Security review + regression suite + demo evidence | NOT TESTED | | |

Never change a gate to PASS based on a model's claim without actual executed evidence. A `BLOCKED` gate must contain the blocker and safe fallback decision.
