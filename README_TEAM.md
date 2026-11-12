# ShipSafe Team Edition — Five-Phase Claude Code Kit

**Purpose:** Run the ShipSafe v0.2 → v1.0 challenge with a team of up to four people, across five separate Claude Code phases/sessions, preserving working code and independent verification.

## Files to open, in order
1. `docs/TEAM_START_HERE.md` — onboarding and practical setup.
2. `CLAUDE.md` — automatically read by Claude Code at project root; common instructions.
3. `docs/TEAM_WORKFLOW.md` — assignment, branches/worktrees, reviews, security, phase gates.
4. `docs/TEAM_ROSTER.md` — fill actual teammates and Bitbucket provider.
5. `prompts/PHASE-01-FOUNDATION.md` — first standalone session prompt.
6. Then phases 2–5, one new session each, only after review and merge.

## Phase files
| Session | File | Completion gate |
|---|---|---|
| 1 | `prompts/PHASE-01-FOUNDATION.md` | Stable baseline, tests, architecture/interfaces |
| 2 | `prompts/PHASE-02-BITBUCKET.md` | Real connector code + PR scanning + UI |
| 3 | `prompts/PHASE-03-CLAUDE-REVIEW.md` | Authorized manual review handoff/import, no API key |
| 4 | `prompts/PHASE-04-REGRESSION-TESTS.md` | Safe approved test runs or honest BLOCKED |
| 5 | `prompts/PHASE-05-FINAL-VALIDATION.md` | End-to-end demo, security, evidence |

## One-line Claude instruction
Run `claude` from the project root after authenticating using your own approved Team subscription, then paste:

> Read `CLAUDE.md`, `docs/TEAM_WORKFLOW.md`, and `prompts/PHASE-01-FOUNDATION.md`. We are a team; ask me for the active owner, branch and ticket before editing shared files. Execute Phase 1 only and stop for human review.

Claude Code should load root `CLAUDE.md` automatically at session start. The explicit instruction above also draws attention to the phase prompt.

## Existing project code
The kit as distributed held only the planning/team files; the original v0.2 backend/frontend was imported separately from the `shipsafe_v0_2_claude_code_source` package and committed unmodified as `10f3cee` ("Import ShipSafe v0.2 team starter"), which is the baseline every phase builds on. This package does **not** pre-implement v1.0 Bitbucket or test-runner features.

## Safety
The Claude Code Team login does not grant ShipSafe access to Bitbucket. Bitbucket API credentials are separate. Never paste tokens into a Claude prompt, and get organization approval before exporting proprietary source for a model review.

## Baseline verification
`cd backend && python -m pytest -q` → 24 passed in the packaging environment on 2026-11-11. Re-run in your team environment. Frontend dependency installation/build remains to be verified locally.
