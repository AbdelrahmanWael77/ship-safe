# Next Agent — Copy/Paste Continuation Prompt

You are joining **ShipSafe**, an existing project, mid-implementation. The v0.2 baseline and Phase 1 are finished. **Do not restart the project, re-plan its phases, or redo completed work.**

Read `AGENTS.md`, `CLAUDE.md`, and the checkpoint at the top of `docs/IMPLEMENTATION_STATUS.md`. Verify the state below against `git status`, `git log`, and the tests before trusting it.

**Where things stand (2026-11-13):**
- **Phase 2** — code complete and committed; **not complete as a phase**: task 6 (read-only live Bitbucket smoke test) and a browser walk-through are NOT TESTED. Owner-run. The root `.env` (git-ignored) has the empty variable names; never read or print its values; never ask for a token in chat.
- **Phase 3** — all five tasks implemented; five of six gates ticked. Open gate: a review written by a **real Claude Code session** and imported (only synthetic JSON fixtures so far). Owner-run: export the demo scan, follow `REVIEW_INSTRUCTIONS.md` in their own Claude Code, import `claude-review.json`, report what had to be corrected. Handoff: `docs/handoffs/P3-CLAUDE-REVIEW-SESSION_HANDOFF.md`.
- **Phase 4** — started by owner decision on 2026-11-13 with the instruction **"Run stays BLOCKED"**: build discovery, proposals, approval and the runner interface; nothing executes until an isolated runner is verified. Task A (static test discovery) is done.

**Branches (all local, nothing pushed):** `feat/p2-frontend-pr-screens` at `74661f4`. `feat/p3-review-package` at `f0fd75c` (Phase 3 tasks 1–5 committed). `feat/p4-test-discovery`, cut from it: **Phase 4 task A is done and uncommitted in the working tree.** Do not discard it. Commit only when the owner says so. Never push or merge.

**Phase 4 task A (done):** `backend/app/discovery.py` (`discover_tests`, AST only, never imports or runs a test file), route `GET /api/scans/{id}/tests/discovery` in `main.py`, panel `frontend/src/TestDiscoveryPanel.tsx` on the Test intelligence page. Tests: `backend/tests/test_discovery.py`, two in `test_bitbucket_api.py`, `frontend/src/TestDiscoveryPanel.test.tsx`. The module is named `discovery.py`, not `test_discovery.py`, so pytest does not collect it.

**Tests last run (2026-11-13, Windows 11):**
- `cd backend && ..\.venv\Scripts\python -m pytest -q` → 324 passed, 1 warning (about 9 minutes)
- `cd frontend && npm test` → 127 passed (8 files); `npm run build` → ✓

**Next atomic task — Phase 4 task B (proposed test patches + explicit approval), no execution:** (1) safe, additive **migration 3** in `backend/app/db.py` with tests in the style of `test_migration_2.py`: table `test_proposals` (id, scan_id, created_at, finding reference, target path, content, content digest, base and head commit copied from the scan, status) and table `test_proposal_decisions` (proposal id, decision `approved` / `rejected`, decided_at, decided_by, note) — decisions are append-only; never erase history. (2) `POST /api/scans/{id}/tests/proposals`: store a proposed test file as **untrusted text**; size limit; target path must be a relative POSIX path matching `test_*.py` or `*_test.py` under a tests directory, with no `..`, no absolute or drive path, no backslash, no NUL, not `conftest.py`, not a path that already exists at the head commit unless explicitly a replacement (decide and record); content is parsed with `ast` only to check that it is syntactically Python, never run. (3) `POST …/proposals/{pid}/decisions`: explicit approve or reject with a required `decided_by` name; state the honest limitation that ShipSafe has no authentication, so the name is self-declared. (4) A proposal is **stale** when its scan is stale (read from the scan row, as for reviews); stale, rejected or undecided proposals must never be runnable. (5) `GET` routes to list proposals with their decisions. (6) Minimal UI on the Test intelligence page: full content shown as inert text, approve / reject with a name, status. **Nothing is applied to any checkout and nothing runs**; a "Run" control, if shown at all, is disabled and labelled BLOCKED with the reason. Tests: path traversal and symlink-style names, oversized content, non-Python content, decisions required, stale proposals, history preserved, earlier suites still pass.

**If the owner reports test results:** record PASS / FAIL / BLOCKED with their evidence in the checkpoint and `docs/ACCEPTANCE_MATRIX.md`; fix what failed on the branch of the phase it belongs to; add a regression test for each fix.

**Phase 4 rules (`prompts/PHASE-04-REGRESSION-TESTS.md`):** on 2026-11-13 `docker.exe` (Docker Desktop) was installed but its daemon was **not running**; `podman` absent; `wsl.exe` present. **Never run repository tests on the host.** After task B: (C) runner interface that returns `execution_unavailable` and labels the run BLOCKED when no verified isolated runner exists — real execution only inside a container with no network, no credentials, read-only source, CPU / memory / time limits, unprivileged user, and only for the synthetic demo repository, and only after the owner starts Docker and says so; (D) base versus head comparison. No fake logs, ever.

**Decisions to keep:** the context digest covers identity and commits (old packages are refused on import). Stale state is never stored in a package or a review; it is read from the scan row. The echoed identity in a v2 review is `reviewed_source`, never `source` (that key is the provenance marker). Unknown acknowledgement state in the UI means "required". No Claude API key, no Claude subprocess, no automatic patch application.

**NOT TESTED anywhere:** a real Claude Code session, live Bitbucket, any screen in a real browser.

Keep your reply under six lines. Do not claim success without checking.
