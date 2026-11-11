# ShipSafe v1.0 — Phase 5 of 5: Product Integration, Security, Competition Demo

> **Final separate Claude Code session after Phase 4 review. No new major systems before core acceptance.**

- Lead/integrator: `[NAME]`
- Backend owner: `[NAME]`
- Frontend owner: `[NAME]`
- QA/security/demo owner: `[NAME]`
- Active branches/tickets: `[BRANCHES / TICKETS]`

## Opening instruction to Claude
Read `CLAUDE.md`, `docs/TEAM_WORKFLOW.md`, `docs/ARCHITECTURE.md`, `docs/PHASE_HANDOFF.md`, `docs/IMPLEMENTATION_STATUS.md`, and `docs/ACCEPTANCE_MATRIX.md`. Inspect actual merged code. **Do not rebuild functional features or invent metrics**. Prioritize correctness, evidence, security and a coherent end-to-end UI. All teammates work on isolated branches; respect assigned ownership.

## End-to-end product flow to demonstrate
Select authorized Bitbucket repo → list/select PR → analyze exact immutable change → display static risks → export manual Claude Code package → import structured AI review → inspect unverified findings → human-approved isolated regression test → evidence-based release report.

Provide a complete parallel flow using the synthetic demo repository and mock provider fixtures for reproducible presentation, whether or not real Bitbucket credentials are available.

## Tasks
### 1. UX/UI integration
Polish and connect Overview, Repositories, PRs, Diff/Risks, Claude Review, Test Intelligence, Release Assessment and Settings. Real API wiring, accessible labels, responsive layout, proper loading/empty/error/stale states. Never display synthetic numbers as live real-team data.

### 2. Evidence-based assessment
Summarize static SUSPECTED findings, imported UNVERIFIED AI reviews, real executed test results, confirmed vs inconclusive regressions, reviewer decisions and remaining unknowns. Support `review required`, `confirmed regression`, `tests incomplete`, `stale`, and `assessment unavailable` states. Do not claim any PR is guaranteed safe. Export JSON and a readable report, both tied to repository/PR/head SHA.

### 3. Security assessment
Audit authorization status (if no auth, classify as localhost-only single trusted user), Bitbucket secret storage, allowed repo paths, SSRF, Git diff/AI prompt injection, import escaping, webhook boundaries, sandbox policies, output size limits, migrations and local exposure. Fix critical issues without introducing unrelated new features. No automated merge, push, PR approval or Bitbucket writes.

### 4. Complete verification
Run backend tests, frontend build, functional API integration, mock provider PR flow, handoff JSON round-trip, stale commit detection, and synthetic approved regression. If a safe test runner is unavailable, demonstrate blocked controls and state the gap. Record environment and commands for each result.

### 5. Competition evidence and presentation
Create `docs/STUMP_THE_MODEL_RESULTS.md` and `docs/DEMO_SCRIPT.md`. Capture actual first prompt, number and types of human interventions, successes, failed hidden tests, where Claude hallucinated evidence (if it did), and business use case. Use a preprepared hidden change that Claude did not train on; compare against a frozen build. Script a 5-minute demo with a rollback/backup plan. Use only synthetic or approved test-repo content.

### 6. Optional if time remains
Verified, read-only Bitbucket PR webhooks and queue may be considered **only if** all core gates pass and the team explicitly approves a new scoped ticket. Do not silently begin webhooks, CI gating, multi-user auth, or production deployment.

## Independent exit test
1. Start app; select synthetic repo and real Git comparison; inspect changed code.
2. Select mock Bitbucket PR, verify correct head SHA and scan provenance.
3. Export Claude package; review/validate schema; import synthetic or real Claude output with accurate attribution.
4. Present one proposed test; show human approval and *real* isolated base/head output or explicit safe BLOCKED.
5. Export a release assessment with findings, evidence and uncertainty.
6. Change PR head identity; confirm previous scan, AI review and test evidence are marked stale.
7. Build frontend; execute all backend tests; inspect security and secret-scanning checks.

## Team split
- Backend: integration bugs, exported report, security fixes.
- Frontend: connected product UI polish and accessibility.
- QA/security/demo: hidden tests, reproducibility, threat review, demo script.
- Lead: scope freeze, integration/test gate, factual verdict, final merge.

## Final acceptance gates
- [ ] Full manual code-review pipeline works with real data from synthetic fixture.
- [ ] Bitbucket read-only integration is implemented and has verified or clearly unverified live access.
- [ ] AI findings vs actual tests distinguished and commit-bound.
- [ ] Tests run in valid sandbox or are BLOCKED with transparent limitation.
- [ ] No fabricated evidence or credentials in exports.
- [ ] Backend + frontend verification commands/results recorded.
- [ ] Security limitations, business value, hidden-test findings documented.
- [ ] Demo verified; final source checkpoint reviewed by human teammates.

## Final handoff
Update canonical docs, demo script, competition results, and an exact PASS/PARTIAL/BLOCKED/FAIL feature list. Integrator may create tag `shipsafe-v1.0` after human review. **Do not push, deploy or merge without explicit team authorization. Stop and deliver the final evidence-based report.**
