# Next Agent — Copy/Paste Continuation Prompt

You are joining **ShipSafe**, an existing project, mid-implementation. The v0.2 baseline and Phase 1 are finished. **Do not restart the project, re-plan its phases, or redo completed work.**

Read `AGENTS.md`, `CLAUDE.md`, and the checkpoint at the top of `docs/IMPLEMENTATION_STATUS.md`. Verify the state below against `git status`, `git log`, and the tests before trusting it.

**Where things stand (2026-11-13):**
- **Phase 2** — code complete and committed; **not complete as a phase**: task 6 (read-only live Bitbucket smoke test) and a browser walk-through are NOT TESTED. Owner-run. The root `.env` (git-ignored) has the empty variable names; never read or print its values; never ask for a token in chat.
- **Phase 3** — all five tasks implemented; five of six gates ticked. Open gate: a review written by a **real Claude Code session** and imported (only synthetic JSON fixtures so far). Owner-run: export the demo scan, follow `REVIEW_INSTRUCTIONS.md` in their own Claude Code, import `claude-review.json`, report what had to be corrected. Handoff: `docs/handoffs/P3-CLAUDE-REVIEW-SESSION_HANDOFF.md`.
- **Phase 4** — **not started.** Needs the owner's explicit approval and a verified isolated runner.

**Branches (all local, nothing pushed):** `feat/p2-frontend-pr-screens` at `74661f4`. `feat/p3-review-package`, cut from it: tasks 1–4 committed (`d0d19d2`, `779932e`, `dd4c6db`, `73a658c`); **task 5 (documentation: operating model, checklist, gates, matrix, session handoff) is uncommitted in the working tree.** Do not discard it. Commit only when the owner says so. Never push or merge.

**Tests last run (2026-11-13, Windows 11):**
- `cd backend && ..\.venv\Scripts\python -m pytest -q` → 299 passed, 1 warning (about 9 minutes)
- `cd frontend && npm test` → 119 passed (7 files); `npm run build` → ✓
- No code changed since those runs (task 5 is documentation only).

**If the owner reports test results:** record PASS / FAIL / BLOCKED with their evidence in the checkpoint and `docs/ACCEPTANCE_MATRIX.md`; fix what failed on the branch of the phase it belongs to; add a regression test for each fix.

**If the owner approves Phase 4 (`prompts/PHASE-04-REGRESSION-TESTS.md`):** cut `feat/p4-…` from `feat/p3-review-package`. First check the runner: on 2026-11-13 `docker.exe` (Docker Desktop) was installed but its daemon was **not running**; `podman` absent; `wsl.exe` present. **Never run repository tests on the host.** Order: (A) test discovery without importing or executing code; (B) proposed test patches stored as untrusted data with path validation and explicit, recorded approval (this needs a safe migration 3 with tests); (C) runner interface that returns `execution_unavailable` and labels the run BLOCKED when no verified isolated runner exists — real execution only inside a container with no network, no credentials, read-only source, CPU / memory / time limits, unprivileged user, and only for the synthetic demo repository; (D) base versus head comparison. No fake logs, ever.

**Decisions to keep:** the context digest covers identity and commits (old packages are refused on import). Stale state is never stored in a package or a review; it is read from the scan row. The echoed identity in a v2 review is `reviewed_source`, never `source` (that key is the provenance marker). Unknown acknowledgement state in the UI means "required". No Claude API key, no Claude subprocess, no automatic patch application.

**NOT TESTED anywhere:** a real Claude Code session, live Bitbucket, any screen in a real browser.

Keep your reply under six lines. Do not claim success without checking.
