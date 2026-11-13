# ShipSafe — security assessment (Phase 5 task 3)

Date: 2026-11-13. Branch `feat/p5-final-validation`. Scope: the application sources in `backend/app`, `frontend/src`, `scripts`. Method: code reading, the searches listed under "Checks executed", and the automated tests named in each row. **Not done:** penetration testing, dependency audit of Python packages, review by a second person, any test against live Bitbucket.

## Classification

**ShipSafe is a localhost-only tool for a single trusted user.** It has no authentication and no authorization. Anyone who can reach the API can read every stored scan (including source-code patches), import reviews, record decisions under any name, and export packages. It must not be exposed on a network, shared between users, or deployed.

## Findings

| Area | Status | Evidence | Residual risk |
|---|---|---|---|
| Authentication / authorization | **None (by design, documented)** | No auth code exists. Names on decisions and run requests are self-declared and labelled so in the API and UI | Any local process or user on the machine can act as anyone. Blocks multi-user or networked use |
| Local exposure | Mitigated | API binds `127.0.0.1` (`scripts/dev.py`); `TrustedHostMiddleware` allows only loopback host names (DNS-rebinding defence); CORS allows only `http://localhost:5173` and `http://127.0.0.1:5173`, methods GET and POST | A user who starts uvicorn with `--host 0.0.0.0` removes the bind protection; the host check still refuses non-loopback Host headers |
| Bitbucket credential | Mitigated | Token only in server environment / git-ignored `.env`; wrapped in `config.Secret`; absent from `repr`, JSON, logs and API responses (`test_bitbucket_settings.py`); `VITE_API_BASE` is the only `VITE_` variable in the bundle | A token with more than read scope would still only be used for GET, but should not be issued |
| Bitbucket writes | None possible | Provider issues only GET requests (`test_bitbucket_provider.py` asserts the method set is `{"GET"}`); no merge, approve, comment or webhook route exists | — |
| SSRF | Mitigated | Requests go only to the fixed Bitbucket API host with validated workspace and repository slugs from an allowlist; redirects are not followed (`follow_redirects=False`) | Relies on slug validation in the provider; live behaviour unverified |
| Allowed repository paths | Mitigated | Local scans only inside the demo repository or `SHIPSAFE_ALLOWED_ROOT` (`RepositoryAccessDenied`, tests in `test_foundation.py`, `test_phase1_*`) | A broad `SHIPSAFE_ALLOWED_ROOT` exposes everything under it to the unauthenticated API |
| Command injection | Mitigated | Git is called with argument arrays; no `shell=True`; refs validated (`valid_ref`) | — |
| Prompt injection through diffs | Partly mitigated | Review instructions declare all repository text untrusted; imported reviews are schema-checked, bound to scan / digest / commit, cannot claim verification or test results, and never change static findings | A model can still be steered by hostile text in a diff; the output is advice only and labelled unverified. Not tested with a real Claude Code session |
| Imported content rendering | Mitigated | No `dangerouslySetInnerHTML` / `innerHTML` in the frontend; React escapes text; tests render `<img onerror>` payloads as text (`App.test.tsx`, `TestProposalsPanel.test.tsx`); the Markdown report neutralises pipes, backticks, line breaks and `<` (`test_assessment.py`) | The exported Markdown is opened in the user's own viewer, outside ShipSafe |
| Source code leaving the machine | Partly mitigated | Review packages need an explicit acknowledgement for anything but the synthetic demo; best-effort secret redaction; size limit; checklist in `docs/CLAUDE-CODE-HANDOFF.md` | Redaction is pattern-based and will miss secrets; the acknowledgement is a human statement, not a control |
| Test execution / sandbox | **Not present: BLOCKED** | No code executes a test (`runner.py`; `test_runner.py` shows a run request starts no process). Proposals are stored as text and never written to a repository | When a runner is added, its isolation must be proven before first use (no network, no credentials, read-only source, unprivileged, limits, no Docker socket) |
| Input and output size limits | Mitigated | Review import 256 KiB; proposal 64 KiB; package context 1 MiB; diff 140 lines per file; 300 files per scan; Bitbucket reads capped | A scan of a very large pull request is slow (many sequential requests, no progress) |
| Database migrations | Mitigated | Forward-only, additive, transactional; newer database refused by older code; tests for versions 2, 3, 4 | A database opened by this code cannot be used by an older branch |
| Webhooks, CI gating, automatic merge | Not implemented | No such route (`main.py` search) | — |
| Secrets in the repository | None found | Pattern search of tracked files: the only hits are the synthetic placeholder strings in `backend/tests/test_review_package.py` (redaction test inputs). `.env` is git-ignored and untracked | Pattern search only |
| Dependencies | Frontend checked | `npm audit` → 0 vulnerabilities (2026-11-13) | **Python dependencies not audited** (no `pip-audit` run) |

## Checks executed (2026-11-13, Windows 11)

```text
tracked files matching AKIA…/ghp_…/ATATT…/PRIVATE KEY/xox…   -> backend/tests/test_review_package.py only (synthetic test inputs)
.env tracked?                                                -> False (ignored by .gitignore)
HTTP methods in backend/app/providers/bitbucket.py           -> get, stream("GET", …)
follow_redirects                                             -> False
dangerouslySetInnerHTML | innerHTML | document.write | eval( in frontend/src -> 0
VITE_ variables in frontend/src                              -> VITE_API_BASE
shell=True in backend/app, scripts                           -> 0
webhook | /merge | /approve | .put( | .delete( in main.py    -> 0
uvicorn bind (scripts/dev.py)                                -> --host 127.0.0.1
npm audit                                                    -> found 0 vulnerabilities
```

## No critical issue was found that needed a code change in this phase

Open items, in order of importance: (1) no authentication, which limits ShipSafe to single-user localhost use; (2) nothing verified against live Bitbucket; (3) no isolated test runner; (4) Python dependencies not audited; (5) redaction is best-effort.
