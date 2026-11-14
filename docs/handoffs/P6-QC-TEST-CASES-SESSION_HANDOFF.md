# Session handoff — PR #48 fixes and QC test cases (2026-11-14)

Branches, on top of `Test-Branch` (`2e2b4a4`), each one stacked on the previous:

| Branch | Head | What it holds |
|---|---|---|
| `fix/p5-feature-check` | `ff2311e` | 6 commits: fixes found by testing every feature and PR #48 (liwan_elsokan_app, Flutter) in the browser |
| `feat/p6-qc-test-cases` | this commit | `fix/p5-feature-check` + AI-written manual QC test cases with tester results + this handoff |

Nothing is merged into `Test-Branch`, `feat/p1-foundation` or anything else. There is no `main` in the workflow.

## 1. `fix/p5-feature-check` — fixes (commits `e49d357` … `ff2311e`)

- **Mock mode** keeps the demo dashboard (`e49d357`).
- **Claude Review**: copy button works; re-importing the same file works (`853a747`).
- **Docs**: OpenAI settings in `docs/CONFIGURATION.md`; README states the static rules are Python-only (`66cbab1`, `9c57eb8`).
- **Wording**: AI review and test-run texts say what really happens; the assessment counts `model_generated` vs `manually_imported` reviews (`9c57eb8`).
- **PR #48 findings** (`ae0766a`): the dashboard follows the scan opened from PR analysis; scan history loads 100 (was 20); Dart/Flutter `*_test.dart` discovery (through relative and `package:` imports, `pubspec.yaml`); readiness and Run wording; source → target arrows; "already scanned" warning; discovery results cached per scan.
- **Overview numbers** (`ff2311e`): an "At a glance" line answers "are there problems?" from static + AI findings; an AI findings card; static score shows **N/A** when the change has no Python file; the risk list combines static and AI findings (AI marked unverified); sidebar badge counts both; fake mini-graphs removed. Risk scoring logic and the static findings count are **unchanged**: AI findings are never added to the score.

## 2. `feat/p6-qc-test-cases` — QC test cases (commit `7a955a4`)

Why: an AI review gives suspicions. A QC team needs something it can execute and report: step-by-step manual test cases, a pass/fail per case, and a bug title when it fails. Rovo-style PR review does not give that.

- **Flow** (Test intelligence page, panel "QC test cases"): pick the model → "Write test cases with OpenAI/Gemini" → the model receives the newest AI review's findings + the redacted review context and returns cases → each case has preconditions, test data, steps, expected result, bug title if it fails, linked finding id and file → a tester types their name and marks Passed / Failed / Blocked with a note → CSV (Excel/Jira/TestRail, formula-injection safe) or Markdown export.
- **Release assessment** has a "Manual QC tests" section labelled *RECORDED BY TESTERS (self-declared; not observed by ShipSafe)*. Tester results are **never** counted as executed tests (`tests.runs.executed` stays 0).
- **Safety**: same rules as model reviews — 428 without `acknowledge_source_sharing` for non-demo code, 503 when the provider is not configured, 409 with no review / no findings, nothing sent before those checks. Cases without a known finding, steps or expected result are dropped and counted; 0 usable cases → 502 `{provider}_no_test_cases`, nothing stored. Results are append-only. The module cannot execute anything (a test checks it).
- **Code**:
  - backend: `app/qc_tests.py` (new: prompt, schemas, validation, storage, CSV/Markdown), `app/gemini.py` + `app/openai_review.py` (an `AITask` lets one client run a different prompt/schema), `app/db.py` (**Migration 5**: tables `qc_test_suites`, `qc_test_results`; adds only), `app/main.py` (4 routes below), `app/assessment.py` (`manual_tests`).
  - frontend: `src/QcTestCasesPanel.tsx` (new), `src/App.tsx` (renders it on Test intelligence), `src/ReleaseAssessmentPanel.tsx`, `src/types.ts`, `src/bitbucket.css`.
  - tests: `backend/tests/test_qc_tests.py` (10), `frontend/src/QcTestCasesPanel.test.tsx` (6), 2 in `ReleaseAssessmentPanel.test.tsx`.
- **Routes**:
  - `POST /api/scans/{id}/qc/test-suites` `{provider, review_id?, acknowledge_source_sharing}` → 201 suite
  - `GET /api/scans/{id}/qc/test-suites` → newest 20
  - `POST /api/scans/{id}/qc/test-suites/{suite_id}/results` `{case_id, status: passed|failed|blocked|not_run, tester (2–80), note?}` → 201 suite
  - `GET /api/scans/{id}/qc/test-suites/{suite_id}/export?format=csv|markdown`

## 3. Verified — and not verified

- Linux container, 2026-11-14: backend `pytest -q` → **493 passed**; frontend `vitest run` → **196 passed** (12 files); `tsc -b` ✓; `vite build` ✓.
- Browser (Playwright) against the real app with **fake** OpenAI/Bitbucket: demo scan → AI review → 2 cases written → TC1 failed, TC2 passed → CSV → assessment section. No page errors.
- The owner installed and tested `fix/p5-feature-check` on Windows with PR #48 and real OpenAI.
- **Not verified yet**: the QC feature with a **real** OpenAI/Gemini call; the QC feature on Windows; the full backend suite on Windows (it is slow there: run per file or in the background).

## 4. Known limits (do not claim otherwise)

- Static rules: Python only, 3 patterns. Non-Python changes rely on the AI review.
- Test proposals: Python (pytest) only. Every run is BLOCKED: there is no isolated runner. ShipSafe executes no repository code.
- AI output (reviews and test cases) is unverified. Tester names are self-declared (no authentication).
- Bitbucket access is read-only. No patch application.

## 5. Suggested next work (owner decides the order)

1. **Try QC test cases on PR #48 with real OpenAI**; check whether a case covers the `app_button` double-press change the review missed. Tune `INSTRUCTION` in `app/qc_tests.py` from what the cases look like.
2. **Language-independent static checks**: Semgrep (or similar) rules for Dart/JS/TS/Kotlin/Java, so non-Python PRs are not "N/A".
3. **Release-level view**: group the PRs of one release, show their findings, QC results and open failures together.
4. **Multi-model agreement**: run OpenAI and Gemini on the same scan and highlight findings both report.
5. **Failed case → bug**: one click from a failed case to a Jira issue (needs the owner's approval for any write integration).
6. **"Propose a fix"** for a confirmed finding (text only, never applied automatically).
