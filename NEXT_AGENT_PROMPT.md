# Next Agent — Copy/Paste Continuation Prompt

You are joining **ShipSafe**, an existing project, mid-implementation. The v0.2 baseline and Phase 1 are finished. **Do not restart the project, re-plan its phases, or redo completed work.**

Read `AGENTS.md`, `CLAUDE.md`, and the checkpoint at the top of `docs/IMPLEMENTATION_STATUS.md`. Verify the state below against `git status`, `git log`, and the tests before trusting it.

**Where things stand (2026-11-13):**
- **Phase 2** — code complete and committed; **not complete as a phase**: task 6 (read-only live Bitbucket smoke test) and a browser walk-through are NOT TESTED. Owner-run. The root `.env` (git-ignored) has the empty variable names; never read or print its values; never ask for a token in chat.
- **Phase 3** — all five tasks implemented; five of six gates ticked. Open gate: a review written by a **real Claude Code session** and imported (only synthetic JSON fixtures so far). Owner-run: export the demo scan, follow `REVIEW_INSTRUCTIONS.md` in their own Claude Code, import `claude-review.json`, report what had to be corrected. Handoff: `docs/handoffs/P3-CLAUDE-REVIEW-SESSION_HANDOFF.md`.
- **Phase 4** — started by owner decision on 2026-11-13 with the instruction **"Run stays BLOCKED"**: build discovery, proposals, approval and the runner interface; nothing executes until an isolated runner is verified. Task A (static test discovery) is done.

**Branches (all local, nothing pushed):** `feat/p2-frontend-pr-screens` at `74661f4`. `feat/p3-review-package` at `f0fd75c` (Phase 3 tasks 1–5 committed). `feat/p4-test-discovery`, cut from it: tasks A and B committed (`e092f9e`, `f70e769`); **Phase 4 task C is done and uncommitted in the working tree.** Do not discard it. Commit only when the owner says so. Never push or merge.

**Phase 4 task C (done):** `backend/app/runner.py` (`Runner` protocol, `UnavailableRunner`, `blocked_reason`, `record_blocked_run`); migration 4 (`test_runs`; schema version is now **4**); `create_app(runner=)` test seam; routes `GET /api/tests/runner`, `GET` / `POST /api/scans/{id}/tests/proposals/{pid}/runs`. A run request is never answered 2xx: after its checks it is stored as `blocked` and answered 503 `execution_unavailable`. **There is no execution code anywhere in the build**, and even a runner that claims to be available is answered "no execution engine". UI: the Run button of an approved, non-stale proposal records a blocked request and shows the reason and the request history. Tests: `backend/tests/test_runner.py`, additions in `frontend/src/TestProposalsPanel.test.tsx`; migration tests in `test_proposals.py` now stop at migration 3 (`V3`).

**Phase 4 task B (done):** migration 3 in `backend/app/db.py` (`test_proposals`, `test_proposal_decisions`; schema version is now **3**); `backend/app/proposals.py` (`validate_target_path`, `check_against_tree`, `validate_content`, request models, `served`); routes in `main.py`: `GET` / `POST /api/scans/{id}/tests/proposals`, `POST …/proposals/{pid}/decisions`; panel `frontend/src/TestProposalsPanel.tsx`. Tests: `backend/tests/test_proposals.py`, `frontend/src/TestProposalsPanel.test.tsx`; `test_migration_2.py` now stops at migration 2 (`V2`). Decisions made: a proposal only ever **adds a new file** (an existing path is refused, no replacements); `conftest.py` is refused; a stale scan takes no new proposal and no approval, but a rejection is still recorded; `eligible_to_run` = approved and not stale; `applied` and `executed` are always false.

**Phase 4 task A (done):** `backend/app/discovery.py` (`discover_tests`, AST only, never imports or runs a test file), route `GET /api/scans/{id}/tests/discovery` in `main.py`, panel `frontend/src/TestDiscoveryPanel.tsx` on the Test intelligence page. Tests: `backend/tests/test_discovery.py`, two in `test_bitbucket_api.py`, `frontend/src/TestDiscoveryPanel.test.tsx`. The module is named `discovery.py`, not `test_discovery.py`, so pytest does not collect it.

**Tests last run (2026-11-13, Windows 11):**
- `cd backend && ..\.venv\Scripts\python -m pytest -q` → 414 passed, 1 warning (**about 11 minutes: longer than a 10-minute command limit; run it in the background or per file**)
- `cd frontend && npm test` → 138 passed (9 files); `npm run build` → ✓

**STOP POINT — the next step needs the owner.** Everything in Phase 4 that can be built without executing code is built (A, B, C). What remains is real execution, and it must not be started by an agent on its own:

1. **Owner decision and environment first.** The owner starts Docker Desktop and says explicitly that a container runner may be built and used for the **synthetic demo repository only**. Until then, do not write any code that starts a process to run tests, on the host or anywhere else.
2. **Then, task C part 2 (container runner), in this order:** (a) a `DockerRunner` whose `availability()` is true only after it has *verified* its own isolation with controlled probes inside a throwaway container: no network (`--network none`; a connection attempt fails), no host credentials or environment passed in, source mounted read-only, a disposable writable workspace, non-root user, `--cap-drop ALL`, `--security-opt no-new-privileges`, CPU / memory / pids / time limits enforced, no Docker socket mounted; (b) commands built from argument arrays in code, never from request text; (c) the approved proposal is written only into the disposable workspace, after re-checking the target path there (including symbolic links); (d) real start and end times, exit code, bounded stdout/stderr, tool versions and image id stored in `test_runs`; timeout and cancellation reported as such. Independent tests must show each restriction actually holds.
3. **Task D:** run the same approved test against base and head in equivalent containers; classify base-pass + head-fail as a confirmed regression and everything else (setup error, flaky, incompatible test, timeout) as what it is. **Task E:** the four LedgerLite challenge cases. **Task F:** logs and timeline UI.

**Useful without the owner (small, safe, optional):** a mocked-Bitbucket test for proposals on a pull request scan (not covered yet); splitting the Claude Review page out of `frontend/src/App.tsx`.

**If the owner reports test results:** record PASS / FAIL / BLOCKED with their evidence in the checkpoint and `docs/ACCEPTANCE_MATRIX.md`; fix what failed on the branch of the phase it belongs to; add a regression test for each fix.

**Phase 4 rules (`prompts/PHASE-04-REGRESSION-TESTS.md`):** on 2026-11-13 `docker.exe` (Docker Desktop) was installed but its daemon was **not running**; `podman` absent; `wsl.exe` present. **Never run repository tests on the host.** After task B: (C) runner interface that returns `execution_unavailable` and labels the run BLOCKED when no verified isolated runner exists — real execution only inside a container with no network, no credentials, read-only source, CPU / memory / time limits, unprivileged user, and only for the synthetic demo repository, and only after the owner starts Docker and says so; (D) base versus head comparison. No fake logs, ever.

**Decisions to keep:** the context digest covers identity and commits (old packages are refused on import). Stale state is never stored in a package or a review; it is read from the scan row. The echoed identity in a v2 review is `reviewed_source`, never `source` (that key is the provenance marker). Unknown acknowledgement state in the UI means "required". No Claude API key, no Claude subprocess, no automatic patch application.

**NOT TESTED anywhere:** a real Claude Code session, live Bitbucket, any screen in a real browser.

Keep your reply under six lines. Do not claim success without checking.
