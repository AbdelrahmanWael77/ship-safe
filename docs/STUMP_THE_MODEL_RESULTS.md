# Stump-the-model results (Phase 5 task 5)

Date: 2026-11-13. Covers **one Claude Code session** (model Fable 5.2, with one short switch to Sonnet 5.5) that carried the project from Phase 2 task 5 to Phase 5. Earlier sessions (Phase 1, Phase 2 tasks 1–4) are described in `docs/handoffs/` and the checkpoint, not here. Every number below is counted from that session or from an executed command; nothing is estimated.

## What was NOT done (read first)

- **No hidden-change test against a frozen build.** No prepared change unknown to the model was scanned, and no frozen build was compared. This section of the competition evidence is empty.
- **No hidden tests were run**, so there are no "failed hidden tests" to report.
- **No real Claude Code review** was produced from a ShipSafe package. Only synthetic JSON fixtures were imported.
- **No live Bitbucket request** and **no repository test execution** happened.
- **No screen was viewed in a browser** by the agent; all UI evidence is jsdom tests.

## First prompt of the session (verbatim opening)

> CLAUDE — ENGINEERING EXECUTION MODE. You are the senior software engineer responsible for implementing this project. Your primary responsibility is to WRITE, TEST, FIX and DELIVER working code — not continuously plan development. This project already has an implementation roadmap, and Phase 0 is completed. […] Find the first unfinished task after the completed Phase 0. Start writing and modifying code immediately.

(The full prompt has eight numbered sections: execution over planning, before starting work, implementation rules, token efficiency, phase management, multi-agent continuity, communication, start now.)

## Human interventions in the session

15 messages after the first prompt's start, plus 2 question dialogs:

| Type | Count | What |
|---|---|---|
| Direction with content | 3 | Fix demo labels on Bitbucket scans + prepare commit + guide the live test; add the Bitbucket variable names to `.env`; "continue the other phases until all done, then tell me what you need and how to test" |
| Question | 2 | "Is all of Phase 2 finished?"; "Can we continue the next phase while I prepare the data?" |
| Go-ahead only | 10 | "commit", "continue", "commit and continue" |
| Dialog answers | 2 dialogs, 3 answers | Commit Phase 2 then start Phase 3; commit Phase 3 docs; start Phase 4 with Run kept BLOCKED |
| Error report pasted by the human | 1 (inside a direction message) | Vite proxy `ECONNREFUSED 127.0.0.1:8000` (backend not started) |

No human wrote or corrected code. The human never ran the application's screens or tests during the session.

## Where the model was wrong, and how it was caught

| What | Caught by | Reached a commit? |
|---|---|---|
| In review schema v2 the echoed identity was named `source` and overwrote the saved review's provenance marker (`user_imported_json_unverified_provenance`). The first backend test asserted the wrong behaviour and passed | TypeScript type check on the frontend type | No. Renamed to `reviewed_source`; tests now assert the marker survives |
| A documentation edit inserted a paragraph in the middle of a Markdown table in `docs/ARCHITECTURE.md` | The model, while editing the same table later | **Yes**, in `d0d19d2`; repaired in `dd4c6db` |
| A scripted multi-replace silently dropped the second line of three replacements (PowerShell operator precedence) | Failing tests | No |
| A "hostile test file" test replaced Python's `compile` and `__import__` and crashed the test runner | The crash itself | No. Rewritten to check side effects |
| A stray empty file `frontend/NEXT_AGENT_PROMPT.md` created by a relative-path slip | `git status` | No. Deleted before commit |
| An older test pinned the previous review response shape and failed after a deliberate contract change | Full backend run | No. Test updated; the change is recorded |
| A weak assertion (`… or True`) written into a new test | The model on re-reading | No |
| Status files said "uncommitted" inside the commit that committed the work | The model | **Yes**, twice; corrected in the following commit each time |

No test result, build result, scan result or review outcome was invented. Where something was not run, the status files say NOT TESTED.

## What worked

- Five commits of Phase 3 and three of Phase 4 landed with the suites passing: the full backend suite was run for every commit that changed backend code and the frontend suite for every commit that changed frontend code. Over the session the backend suite grew from 236 to 424 tests and the frontend suite from 63 to 150.
- Fail-closed behaviour held under tests written to break it: a run request starts no process; a hostile proposal is stored and approved without being written or run; discovery parses a hostile test file without executing it.
- The agent stopped at the points the rules require: it did not push or merge, did not read or request the Bitbucket token, and did not run repository tests on the host. When starting a container was refused by the session's permission settings, it did not work around the refusal.

## Business use case

A team that reviews pull requests wants, before merge, one page per change that separates three things people routinely blur: what a static scan suspects, what an AI reviewer suggested, and what a test actually proved, each tied to the exact commit and marked stale when the pull request moves. ShipSafe does the first two and the bookkeeping for the third on a developer's machine, without sending code anywhere on its own and without holding an AI credential. The third (executed regression evidence) is designed, gated by human approval, and blocked until an isolated runner exists.

## Verdict

Useful as a **local review aid with honest labelling**. Not yet a release gate: no executed test evidence, no authentication, nothing verified against live Bitbucket, and no independent hidden-change evaluation.
