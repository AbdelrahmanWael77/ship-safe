# ShipSafe v1.0 — Phase 3 of 5: Team-Authenticated Claude Code Review

> **New Claude Code session after reviewed Phase 2 integration. Phase 3 ONLY.**

- Phase integrator: `[NAME]`
- Backend/review schema owner: `[NAME]`
- Frontend review UI owner: `[NAME]`
- QA/security reviewer: `[NAME]`
- Active branches/tickets: `[BRANCHES / TICKETS]`

## Opening instruction to Claude
Read `CLAUDE.md`, `docs/TEAM_WORKFLOW.md`, `docs/PHASE_HANDOFF.md`, `docs/ACCEPTANCE_MATRIX.md`, the Phase 2 API contracts and existing `backend/app/ai_handoff.py`. Validate prior tests. Your mission is **manual, developer-controlled Claude Code review of a specific scan/Bitbucket PR**. **No Anthropic API key in ShipSafe, no token extraction, no unofficial subscription API, no autonomous Claude subprocess on the server.**

## Tasks
### 1. Trusted identity + minimal review package
For local scans and Bitbucket PR scans, export a versioned ZIP that includes only approved code context, actual diff/changed functions/static risks, repository/PR identity, exact base/head commits, package identifier, cryptographic digest of the exported context, instructions and a strict JSON output template. Limit size and detect truncation. Warn before exporting potentially proprietary diffs; require explicit local user acknowledgement where appropriate. Make secret redaction best-effort, not a guarantee, and document review before sharing.

### 2. Claude Code review prompt/schema
Have Claude analyze code changes for security, authorization, API compatibility, money/data integrity, missing validation, exception handling, affected modules, and missing tests. Findings must contain ID, file/line evidence, category, severity, confidence, suspected status, suggested validation and optional proposed patch, plus uncertain or missing context. Claude must not claim it ran commands/tests unless logs are independently supplied.

### 3. Strict import and history
Validate schema version, JSON size/types, known scan/repository/PR/head SHA, package digest and file references. Reject mismatch, malformed fields, unknown changed-file references, oversized content and unsupported fabricated verified-test status. Do not execute imported code or treat it as authoritative. Preserve original static results, imported history, and timestamps. New PR head makes prior Claude review stale, not current.

### 4. Functional UX
In React, show **Export review package**, exact local usage instructions, **Import result**, import status, per-finding cards, source references, test proposals, limitations, AI vs static side-by-side, previous reviews and stale-warning state. Clearly distinguish mock fixtures, static findings, imported unverified AI assessments and real test evidence.

### 5. Operating model for company Team subscription
Each reviewer signs into their **own approved** Claude Code installation and runs the review from an extracted package, after source-sharing approval. ShipSafe itself requires no Claude API key. Bitbucket read-only auth remains separate. Never share session files, credentials, or subscription access among team members.

## Tests
- Round-trip handoff and import for local and mock Bitbucket scans.
- Correct source commit digest and stale detection.
- Wrong scan, wrong SHA, bad digest, missing/extra fields, unknown paths, duplicate imports and size limits rejected as intended.
- Secret-like content redaction and clear warnings; imported markdown/text escaped in UI.
- React flow for download, upload, history, stale label and source evidence.
- Original scanning and Phase 2 connectors still pass.

## Team ticket split
- Backend: handoff schema and persistence.
- Frontend: import/export/review display.
- QA/security: adversarial JSON fixtures, source-export review checklist, no-execution guard.
- Integrator: schema coordination, diff review, commit binding.

## Acceptance gates
- [x] Selected scan/PR yields correct commit-scoped review ZIP. *(2026-11-13: automated tests, local scan and mocked Bitbucket pull request scan. Evidence: `docs/handoffs/P3-CLAUDE-REVIEW-SESSION_HANDOFF.md`.)*
- [ ] A developer can import a well-formed review from their Claude Code session. *(NOT TESTED: only synthetic JSON fixtures were imported. Needs one real run by a person in their own Claude Code.)*
- [x] Imported findings are visibly UNVERIFIED and never overwrite static evidence. *(Automated tests; not viewed in a real browser.)*
- [x] Invalid/wrong-commit imports are rejected; older reviews marked stale. *(Automated tests; stale with mocked Bitbucket only.)*
- [x] No Claude API key, session-token extraction, automatic code execution, unauthorized source sharing. *(Code search of the application sources on 2026-11-13 plus tests; the acknowledgement gate reduces, and cannot prevent, unauthorized sharing by a person who confirms falsely.)*
- [x] Automated tests and frontend build actually run or are documented BLOCKED. *(Backend 299 passed, frontend 119 passed, build passed.)*

## Phase 3 handoff
Contributors fill the session template; integrator merges and updates canonical handoff, status, matrix and decisions. Record whether a **real authenticated Claude Code session** was executed or only synthetic JSON fixtures were tested. Checkpoint `shipsafe-phase-3` with approval. **Stop; do not add test execution until Phase 4.**
