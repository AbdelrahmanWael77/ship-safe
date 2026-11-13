# ShipSafe v1.0 — Phase 4 of 5: Approved, Isolated Regression Verification

> **New Claude Code session after approved Phase 3 integration. Phase 4 ONLY.**

- Integrator: `[NAME]`
- Test-runner backend owner: `[NAME]`
- Frontend approval/logs owner: `[NAME]`
- Independent QA/security reviewer: `[NAME]`
- Active branches/tickets: `[BRANCHES / TICKETS]`

## Opening instruction to Claude
Read team rules, the latest handoff and acceptance matrix, review the actual runner environment and current code. This is the project's highest-risk phase: **do not execute arbitrary repository tests on the host**. If a verified restricted execution environment cannot be provided, implement the review/approval interface but make the Run action fail closed, label it BLOCKED and explain what is missing. Do not mask this limitation with a fake test log.

## Requirements
### A. Test discovery
For Python/pytest, discover candidate existing tests without executing imported code; map them to changed modules and AI/static findings, identify coverage gaps, and explain selection heuristics. Claims remain suggestions until actual execution.

### B. Proposed test patches + explicit human approval
Store proposed regression tests as untrusted data with finding ID, target path and commit identity. Show full diff. Validate paths; reject traversal/symlink escapes and dangerous target destinations. Approval must be explicit and durable, recorded with human identity in local mode or with an honest limitation if authentication is absent. Apply approved patches only to **disposable isolated workspaces**, never to a real developer checkout or Bitbucket.

### C. Hardened execution engine
Use a configured isolated, resource-limited runner for **explicitly trusted synthetic demo repos** first. Verify CPU/memory/time restrictions, network isolation, unprivileged identity, credential-free environment, mount restrictions and no write access to host source or Docker control sockets. Capture real start/end, exit code, stdout/stderr, test identifiers, tool versions and environment identity. Cancel and report failures correctly.

Do not expose a shell-command injection surface; choose allowed runner commands via controlled code and argument arrays. If Docker/container sandbox is absent or unsafe, return an honest `execution_unavailable` status. No unrestricted `pytest` as FastAPI's child process for arbitrary repos.

### D. Compare baseline and changed commit
Run approved, immutable test code against the known-good base and candidate head using equivalent isolated environments. Record exact SHAs and diffs. A valid confirmed regression generally needs **baseline passes + changed commit fails for the target behavior**; distinguish setup error, flaky test, test patch incompatibility, timeout and inconclusive evidence. Do not label every failing test a proven regression.

### E. Synthetic challenge cases
Use LedgerLite fixture and extend only as needed:
- Ownership/auth check removed while old happy-path tests pass.
- Money precision/calculation difference with exact representative expected values.
- Breaking API response field rename with a consumer contract test.
- Harmless README change without fabricated severe findings.

### F. UI and persistence
Show: discovered tests, proposals, reviewable diff, approve/reject, execution permissions, logs, status timeline, base/head comparisons, and evidence-based verified labels. Store proposals, decisions, run metadata, outputs and commit bindings in migrations that preserve history. Old proposals become stale after PR commits change.

## Independent tests and threat model
- Approval is required; rejects/expired/stale requests cannot run.
- Invalid paths, symlink escape, malicious test content, oversized output and untrusted commands handled safely.
- Sandbox constraints can be verified, including denial of network, credentials, privileged mounts and host writes, with controlled tests.
- Real pytest outcome logs and exit codes for synthetic cases, plus baseline/head comparison.
- Timeouts/limits correctly reported; no fake success when runner is unavailable.
- All previous phase suites and frontend build remain functional.

## Team ticket split
- Backend: runner interface, policies, persistence and isolation.
- Frontend: proposals, approvals, execution logs UI.
- QA/security: independent sandbox escape tests, semantic regression assertions, fake-log detection.
- Integrator: reviews execution model, approves testing boundary, coordinates migrations/API.

## Acceptance gates
- [x] Suggested tests never auto-execute; visible, logged human approval first. *(2026-11-13: nothing executes at all in this build; a run request is refused unless the proposal has a recorded approval and is not stale. `backend/tests/test_proposals.py`, `test_runner.py`. Names on decisions are self-declared: there is no authentication.)*
- [x] Test execution occurs only in verified isolation or is explicitly BLOCKED. *(2026-11-13: **BLOCKED**. No isolated runner exists; every run request is stored as `blocked` and answered 503 `execution_unavailable`, with no log and no result. `test_runner.py`.)*
- [ ] One real regression test demonstrates base pass/head fail on synthetic code. *(NOT TESTED: needs real execution in a verified isolated runner.)*
- [ ] Output, logs, errors, timestamps and SHAs come from real execution. *(NOT TESTED: no execution exists. Blocked runs carry real request timestamps and SHAs and no output.)*
- [ ] No host secrets/mounts/network leak, unapproved patch application, or Bitbucket mutations.
- [x] No regressions to Phase 1–3 functionality. *(2026-11-13: full backend suite 414 passed, frontend 138 passed, build passed.)*

## Phase 4 handoff
Each owner fills session handoff. Integrator verifies the actual sandbox environment, merges reviewed code, updates canonical docs and records whether execution was PASS or BLOCKED. Create approved checkpoint `shipsafe-phase-4`. **Stop; Phase 5 is separate.**
