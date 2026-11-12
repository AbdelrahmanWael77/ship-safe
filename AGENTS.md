# ShipSafe — Agent Rules: Lean Build & Handoff

These rules apply to every AI coding agent (Claude, Fable, Codex, or any other) working in this repository. The project and its five-phase plan already exist. **The v0.2 baseline ("Phase 0") and Phase 1 are complete. Do not restart or redo them.**

`CLAUDE.md` holds the project's team, security, and evidence rules. They bind every agent, not only Claude. Read both files; where they differ, the stricter rule wins.

## Sources of truth
- Code plus executed tests decide what is actually implemented.
- The existing roadmap decides scope, phase names, and order: `prompts/PHASE-01-FOUNDATION.md` … `PHASE-05-FINAL-VALIDATION.md`, with gates in `docs/ACCEPTANCE_MATRIX.md`. **Do not replace or re-plan it.**
- `docs/IMPLEMENTATION_STATUS.md` is the compact checkpoint (top section) plus the capability table. If it conflicts with code or tests, correct the status.
- `NEXT_AGENT_PROMPT.md` is the handoff to the next agent, not a new specification.

## At the start of each implementation task
1. Read this file, `CLAUDE.md`, and the checkpoint section of `docs/IMPLEMENTATION_STATUS.md`.
2. Read only the active phase prompt in `prompts/` and the code the task touches.
3. If taking over from another agent, read `NEXT_AGENT_PROMPT.md`, run `git status`, and verify any claimed uncommitted work before building on it.
4. Resume the **first unfinished task** named in the checkpoint. Never redo finished work to standardize it.

## Build rules
- One small, independently testable task at a time; prefer an end-to-end useful slice.
- Reuse existing code, style, architecture, and dependencies.
- No unsolicited redesign, broad refactor, verbose documents, speculative features, or later-phase work unless a genuine dependency requires it.
- Security, authorization, data isolation, secrets, and integrity rules in `CLAUDE.md` are never optional shortcuts.
- Verify with focused tests. Keep tested behaviour, mocks, and assumptions visibly separate. Never claim untested code works.
- Work on a `feat/p<phase>-<ticket>` branch. Never commit to `main`, merge, or push without the owner's approval.
- Edit or merge existing roadmap and status content; never blindly overwrite it.

## After EVERY task (mandatory, not only near quota limits)
1. Update the checkpoint in `docs/IMPLEMENTATION_STATUS.md`: active phase, completed task, changed files, commands and results, known issues, exact next task.
2. Tick the active phase prompt's acceptance gates and update `docs/ACCEPTANCE_MATRIX.md` **only** where executed evidence supports it; do not rename or replan phases.
3. Rewrite `NEXT_AGENT_PROMPT.md` as a paste-ready handoff from the *actual* repository state.
4. Record branch, latest commit, and uncommitted edits. Commit only when the owner has authorized it. Never discard another agent's changes.
5. Report in a few lines: done, verified, blocker, next.

## On interruption, quota exhaustion, or model switching
An agent may not know its remaining quota, so hand off continuously. When context or time runs low: stop starting new work, keep unfinished edits in the working tree, mark incomplete tests honestly, and refresh both handoff files. The next agent must be able to continue from repository files alone, without chat history. Do not run concurrent agents on the same files without coordination.
