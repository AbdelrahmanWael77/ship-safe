# Contributor Session Handoff — Phase 3 / Claude Code review (tasks 1–5)

- Human owner: Nour Waled
- Claude session operator: Nour Waled (Claude Code, Fable 5.2)
- Branch: `feat/p3-review-package` (cut from `feat/p2-frontend-pr-screens` at `74661f4`; local only, not pushed)
- Commit SHA (if committed): `d0d19d2` (task 1), `779932e` (task 2), `dd4c6db` (task 3), `73a658c` (task 4); task 5 (this documentation) in the commit that adds this file
- Reviewer: not assigned
- Date: 2026-11-13

**Read first:** Phase 3 was started by owner decision while Phase 2 was still open. Phase 2 task 6 (live Bitbucket smoke test) and a browser walk-through are NOT TESTED. Nothing in this handoff has been run against live Bitbucket, in a real browser, or with a review written by Claude Code.

## Scope completed
- [x] Task 1 — review package: repository / pull request identity and exact commits under the context digest, `PACKAGE.json` manifest, best-effort secret redaction, 1 MiB limit with marked omissions, source-sharing acknowledgement (HTTP 428) for anything but the synthetic demo. Automated tests pass.
- [x] Task 2 — review schema `shipsafe.ai-review.v2` (finding id, `suspected` status, suggested validation, optional proposed patch, missing context, echoed `reviewed_source`) and review instructions; v1 still accepted. Automated tests pass.
- [x] Task 3 — strict import and history: duplicates refused, reviews served with their scan's binding (stale when the pull request head moved), history across the scans of one pull request. Automated tests pass.
- [x] Task 4 — Claude Review page: previous reviews, selectable review, stale warning, static and imported findings side by side, import result next to the control. Automated tests pass (jsdom).
- [x] Task 5 — operating model and source-export checklist in `docs/CLAUDE-CODE-HANDOFF.md`; gates and matrix updated from executed evidence.
- [ ] A real authenticated Claude Code session producing and importing a review — **NOT TESTED**.

## Files changed
- `backend/app/ai_handoff.py` — package context with `source`, redaction, size limit, manifest, schema v2, `parse_review`, `review_content_digest`, instructions and template
- `backend/app/main.py` — acknowledgement gate, `acknowledgement_required`, version-aware import, duplicate check, `scan_binding` on served reviews, history route
- `backend/tests/test_review_package.py`, `test_review_schema_v2.py`, `test_review_import_history.py` — new
- `backend/tests/test_bitbucket_api.py`, `test_ai_handoff.py`, `test_migration_2.py` — updated for the changed contracts, pull request cases added
- `frontend/src/App.tsx`, `types.ts`, `bitbucket.css`, `App.test.tsx`, `test/setup.ts` — acknowledgement checkbox, v2 fields, stale warning, history, side by side, import status
- `docs/ARCHITECTURE.md`, `docs/CLAUDE-CODE-HANDOFF.md`, `docs/ACCEPTANCE_MATRIX.md`, `docs/IMPLEMENTATION_STATUS.md`, `NEXT_AGENT_PROMPT.md`, `prompts/PHASE-03-CLAUDE-REVIEW.md` (gates)

## API / DB contracts
- **No migration.** Schema version stays 2; `ai_reviews` is unchanged; stored reviews are never modified.
- `GET /api/scans/{id}/ai/handoff`: ZIP now has 4 entries (adds `PACKAGE.json`); 428 without `acknowledge_source_sharing=true` unless the scan is the synthetic demo.
- `GET /api/scans/{id}/ai/context`: adds `acknowledgement_required`.
- **Context digest changed for every scan** (it now covers the identity and commits). A package exported before `d0d19d2` is refused on import with 409; export again.
- `POST /api/scans/{id}/ai/reviews`: accepts v1 and v2; new 409 causes (source mismatch, duplicate finding ids, review already imported). Response and the list / latest routes add `scan_binding` beside the review.
- New: `GET /api/scans/{id}/ai/reviews/history`.
- Compatibility risk: any client that compared review responses exactly, or that reused an old exported package.

## Commands executed and literal results
```text
$ cd backend && ..\.venv\Scripts\python -m pytest -q          (after task 3; no backend change since)
299 passed, 1 warning in 512.34s (0:08:32)

$ cd frontend && npm test                                      (after task 4)
 Test Files  7 passed (7)
      Tests  119 passed (119)

$ cd frontend && npm run build                                 (after task 4)
dist/assets/index-B-OL4GIu.js   240.00 kB │ gzip: 69.54 kB
✓ built in 2.30s

Code search, 2026-11-13, 32 application source files (backend/app, frontend/src without tests,
backend/requirements.txt, frontend/package.json):
  anthropic | api.anthropic | ANTHROPIC_API_KEY | CLAUDE_API      -> no match
  subprocess | os.system | os.popen | eval( | exec( | child_process -> local_git.py and demo_seed.py only
                                                                      (Git commands, present since Phase 1)
  proposed_patch in backend/app                                    -> ai_handoff.py only (schema, instructions, template)
```
The one warning is a Starlette deprecation notice about `httpx` in the test client.

## Tests / acceptance
| Check | PASS / FAIL / BLOCKED / NOT TESTED | Actual evidence |
|---|---|---|
| Commit-scoped review ZIP for a local scan | PASS | `test_review_package.py`, `test_ai_handoff.py` |
| Commit-scoped review ZIP for a pull request scan | PASS (mocked Bitbucket) | `test_bitbucket_api.py`, three package tests |
| Round trip export → import, local and pull request | PASS (synthetic JSON fixtures) | `test_review_schema_v2.py`, `test_bitbucket_api.py` |
| Wrong scan, wrong commit, bad digest, missing / extra fields, unknown paths, duplicates, size limit rejected | PASS | `test_review_schema_v2.py`, `test_review_import_history.py`, `test_ai_handoff.py` |
| Fabricated verified / test-result fields rejected | PASS | `test_review_schema_v2.py` (parametrized) |
| Older review stale after the pull request head moves | PASS (mocked Bitbucket) | `test_a_review_goes_stale_with_its_scan_…` |
| Secret-looking values redacted, with a stated limitation | PASS for the 7 tested shapes | `test_review_package.py`; pattern-based, will miss other shapes |
| Imported text rendered as text (no markup executed) | PASS (jsdom) | `App.test.tsx`, proposed patch containing an `<img onerror>` |
| React flow: download, acknowledgement, upload, history, stale label, source link | PASS (jsdom, stubbed API) | `App.test.tsx` |
| Original scanning and Phase 2 connector tests | PASS | part of the 299 |
| Review produced by a real Claude Code session and imported | NOT TESTED | needs the owner |
| Screens viewed in a real browser | NOT TESTED | |
| Live Bitbucket | NOT TESTED | Phase 2 task 6 |

## Security / privacy review
- Allowed repository/data access: the synthetic demo repository and mocked Bitbucket fixtures only. No client code was used.
- Secrets exposed in logs or files? (must be no): no. The root `.env` was given empty variable names only; its values were never read or printed by the agent.
- Untrusted input handled: imported review JSON is size-limited, schema-validated with unknown fields forbidden, bound to scan / digest / commit, stored as data and rendered as text. Repository text in a package is declared untrusted in the instructions.
- Test execution isolation (if applicable): not applicable; Phase 3 executes no repository code. A proposed patch is stored as text and never applied.
- Residual risks: redaction is best-effort; the acknowledgement is a confirmation by the person, not a technical control; the API is unauthenticated and must stay on localhost.

## Blockers and known defects
- No real Claude Code review has been imported, so it is unknown whether Claude follows the v2 template and instructions without correction.
- A review shows as stale only after something looked at the pull request (list, detail or a new scan); the review routes never contact Bitbucket.
- The duplicate check reads all reviews of a scan on each import (no limit).
- The per-export `package_id` is not stored, so an import cannot be traced to a specific export.
- `frontend/src/App.tsx` holds the whole Claude Review page; it was not split out.

## Conflicts or coordination needed
- Stacked on the unmerged Phase 2 branches. `backend/app/main.py`, `ai_handoff.py` and `frontend/src/App.tsx` are shared files; merge Phase 2 first.
- Frontend owner: the review response gained `scan_binding`; `AIReview` in `types.ts` changed.

## Reviewer instructions
- Check `redact()` patterns in `ai_handoff.py` against the kinds of secrets your repositories actually contain.
- Check `needs_acknowledgement()` in `main.py`: only the synthetic demo is exempt.
- Confirm that `saved_review()` keeps `source: user_imported_json_unverified_provenance` for v2 reviews (a bug of this kind was found and fixed during task 2).
- Run one real review: export the demo scan, follow `REVIEW_INSTRUCTIONS.md` in your own Claude Code, import `claude-review.json`, and record what had to be corrected by hand.
- View the Claude Review page in a browser, including a narrow window.

## NOT DONE / do not claim
- Not run with a real Claude Code session. Not run against live Bitbucket. Not viewed in a browser.
- Phase 2 is not complete; no phase is tagged.
- No test execution of repository code exists (Phase 4).

## Suggested next ticket
- Owner runs the real Claude Code round trip and the Phase 2 live Bitbucket smoke test, then reviews Phase 2 and Phase 3 for merge. Phase 4 (isolated test runner) needs explicit approval and an available isolated runner.
