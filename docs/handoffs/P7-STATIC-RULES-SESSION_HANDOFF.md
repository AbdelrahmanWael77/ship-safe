# Session handoff — Phase 7 task 1: static pattern rules beyond Python (2026-11-14)

- Branch: `feat/p7-static-rules`, cut from `feat/p6-qc-test-cases` (`31f7fc4`). **One local commit (the one that adds this file), made with the owner's approval; not pushed, nothing merged.** No other branch was touched.
- Operator: Claude Code (Fable 5.2), Windows 11, Python from `.venv`, Node 24.22.2.

## What it does

A change to a Dart, JavaScript/TypeScript, Kotlin or Java file is now read by 8 pattern rules. A match becomes a static finding with file, line, rule id and severity. Before this, such changes were "N/A" for static analysis.

| Rule id (`shipsafe.…`) | Severity | Flags |
|---|---|---|
| `tls-validation-disabled` | critical | Dart `badCertificateCallback` returning true; JS/TS `rejectUnauthorized: false`, `NODE_TLS_REJECT_UNAUTHORIZED=0`; Kotlin/Java trust-all hostname verifier or empty `checkServerTrusted` |
| `payment-status-fails-open` | high | A default / else / `??` / `?:` / catch branch that yields a success status in payment code |
| `return-url-host-check-removed` | high | A host comparison on a return or redirect URL was removed and the file no longer checks the host |
| `idempotency-key-regenerated` | high | Idempotency key built from a fresh UUID or the clock where the request is sent, or a reused key replaced by a fresh one |
| `submit-without-busy-guard` | medium | A busy/disabled guard on a handler was removed, or an async submit handler was added in a file with no busy state |
| `cleartext-endpoint` | medium | An `http://` address that is not local or a placeholder |
| `verification-bypass` | medium | `|| true`, `if (true)`, `skip…Check = true`, `…Enabled = false` |
| `empty-catch-in-sensitive-path` | low | An empty catch in payment or sign-in code |

## Decisions (delegated by the owner on 2026-11-14)

1. **Engine: built-in line patterns, not Semgrep.** Reasons: no new dependency (the backend has five), identical on Windows, no process started, no network, and it works on file text read through the provider, so Bitbucket scans need no checkout. Cost: no syntax awareness. Semgrep CE (own rules only; Registry rules are not licensed for this) remains the option when structural matching is needed; Windows support was documented as beta in late 2025 and Dart support is not GA.
2. **Counting: in the static findings count, not in the risk score.** `summary.finding_count` includes them; `summary.risk_score` is computed from the Python heuristics only, exactly as before. Change this only after the rules have been checked on real pull requests.

## How it works

- `backend/app/pattern_rules.py`: `analyze_patterns(path, before, after, patch)`. Rules look at added lines (with their new-file line numbers) and removed lines (with the line where the removal happened). Comment lines and test paths are ignored. At most one finding per rule per file. Imports only `re`, `dataclasses`, `pathlib`, `uuid`; a test asserts that.
- `backend/app/scanner.py`: for each changed file the rules can read, base and head are read with `provider.read_file` (local Git or Bitbucket API). Limits: 60 files per scan, 400,000 characters per file. A file that cannot be read is counted as skipped and never fails the scan.
- Report: findings gain `source: "pattern-rules"`, `rule_id`, `language`. `summary.pattern_rules = {engine, rule_count, files_analysed, files_skipped, finding_count, in_risk_score: false}` exists only when the change has such files. Python-only reports are byte-for-byte what they were.
- Frontend: `patternRules.ts` (which paths count as read), labels on finding cards, Overview wording and counts. The score stays N/A for a change without Python files.
- Bitbucket cost: up to two extra API reads per changed non-Python file, capped at 60 files.

## Files changed

- New: `backend/app/pattern_rules.py`, `backend/tests/test_pattern_rules.py`, `frontend/src/patternRules.ts`, this file.
- Changed: `backend/app/scanner.py`, `frontend/src/App.tsx`, `App.test.tsx`, `components.tsx`, `types.ts`, `bitbucket/PrAnalysisPage.tsx`, `README.md` ("Current limitations"), `docs/IMPLEMENTATION_STATUS.md`, `NEXT_AGENT_PROMPT.md`.
- No migration (schema stays at version 5), no new route, no new dependency.

## Commands and results (2026-11-14, Windows 11)

```text
$ cd backend && ..\.venv\Scripts\python -m pytest -q tests/test_pattern_rules.py
61 passed in 30.10s
$ cd backend && ..\.venv\Scripts\python -m pytest -q
554 passed, 1 warning in 850.81s (0:14:10)
$ cd frontend && npx vitest run
 Test Files  12 passed (12)
      Tests  198 passed (198)
$ cd frontend && npx tsc -b            -> exit 0
$ cd frontend && npm run build         -> ✓ built (299.41 kB JS)
```
`frontend/package-lock.json` differs from the last `npm ci` on this machine; `npm ci` was not re-run.

## Done-when check

| Criterion | Result |
|---|---|
| A Dart or JS/TS change with a planned pattern gets a finding with file, line, rule id, severity; one without gets none | PASS (`test_a_scan_reports_the_finding…` for Dart and TS, `test_a_change_without_a_pattern…`, on a real throwaway Git repository) |
| Python behaviour unchanged, existing tests pass | PASS (493 earlier backend tests pass; `test_the_python_demo_scan_is_unchanged`) |
| No network, no repository code executed | PASS by construction and by test (module imports checked; a hostile file is only matched) |
| Full backend suite, vitest, `tsc -b`, `npm run build` | PASS (above) |

## Not verified — do not claim

- **PR #48 was not scanned with these rules.** They were written from a description of its issues. Whether they flag it is unknown.
- **Precision on real code is unmeasured.** Expect false alarms (for example `cleartext-endpoint` on a documentation URL in a string, `submit-without-busy-guard` on a handler guarded elsewhere) and misses (anything spread over several lines in a way the pattern does not expect).
- No Bitbucket pull request scan, mocked or live, was run with a Dart or JS/TS file.
- Not viewed in a browser. The commit has not been pushed.

## Suggested next steps (owner decides)

1. Owner: scan PR #48 on this branch, compare the pattern findings with what was found by hand, and report hits, misses and false alarms. Tune the patterns in `pattern_rules.py` with a synthetic fixture for each case.
2. Add a mocked Bitbucket test with a `.dart` change (extend `FakeBitbucket` in `backend/tests/test_bitbucket_provider.py`).
3. Then the remaining tasks from the Phase 6 handoff: QC test cases with real OpenAI, release-level view, multi-model agreement, failed case → Jira, text-only "propose a fix".
