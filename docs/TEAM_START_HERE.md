# ShipSafe Team — Start Here

## What you're receiving
This is the existing **ShipSafe v0.2 source** with a **five-phase Claude Code execution kit**, not an already completed v1.0 implementation. The project has the real local Git scanner, manual Claude review handoff, frontend, backend, and tests. The new prompts describe work still to be done.

## First 15 minutes (team lead)
1. Extract this package into a team-owned Git repository. Confirm company policy permits the chosen hosting and access.
2. Read `CLAUDE.md` and `docs/TEAM_WORKFLOW.md` together. Assign up to four people and record actual owners in `docs/TEAM_ROSTER.md`.
3. Run the baseline backend tests; verify the frontend install/build on a team workstation. Record *actual* results in `docs/ACCEPTANCE_MATRIX.md`.
4. Agree on Bitbucket **Cloud vs Data Center** before starting Phase 2; the starter prompt defaults to Cloud.
5. Create Phase 1 tickets and branches; designate one **integrator** who alone updates the canonical phase checkpoint after review/merge.

## Suggested four-person allocation
| Role | Owns | Reviews |
|---|---|---|
| Lead / Integrator | Scope, architecture, Git integration, merges, phase handoffs | All cross-cutting changes |
| Backend / Bitbucket | FastAPI, connector, persistence, migrations | API contracts and security |
| Frontend / UX | React screens, typed API integration, loading/errors | Accessibility, UX, build |
| QA / Security / Demo | Independent tests, isolation, fixtures, acceptance evidence | Threats, regressions, demo |

With 1–3 people, combine roles. **One human remains accountable** for each ticket.

## One session per phase
1. The lead starts `claude` at the project root (signed in via their *own* approved Claude Code Team account).
2. Claude automatically reads the root `CLAUDE.md`; paste the content of `prompts/PHASE-01-FOUNDATION.md` or ask it to read that file and work only on that phase.
3. Teammates can work on separate tickets in separate branches/worktrees. Don't let two sessions modify the same files.
4. Human review + automated acceptance gate + integrator merge. Only then start the next phase in a fresh Claude session.
5. Update `docs/PHASE_HANDOFF.md`, `docs/ACCEPTANCE_MATRIX.md`, and `docs/DECISIONS.md` after integration.

## Initialize version control (only if this folder is not already a Git repository)
```bash
git status  # if this says "not a git repository", initialize it below
git init -b main
# Review .gitignore and files for secrets before the first commit.
git add .
git diff --cached --check
git commit -m "Import ShipSafe v0.2 team starter"
```

If your team imports into an existing repository, use its normal branch policy instead of initializing again. Do not add remotes or push company source without authorization.

## Example safe branch workflow (after `main` exists)
```bash
git switch main
# If a shared remote/tracking branch has been configured: git pull --ff-only
# replace 1/connector with your actual approved ticket
# (Git worktrees are optional, useful for concurrent contributors)
git switch -c feat/p1-api-foundation
claude
# perform work, verify it, inspect diffs and staged files
git status
git diff --check
# commit / push only after human review and with authorized access
```

Claude Code may also provide a `--worktree` mode in supported versions; verify via `claude --help` and your administrator's policy. Each user signs in separately. **Do not share session cookies, tokens, or personal login files.**

## Run the existing app locally
```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
python scripts/dev.py
```
App: http://127.0.0.1:5173 · API docs: http://127.0.0.1:8000/docs

## Gates before continuing
- **Phase 1:** verified current app + architecture + provider abstraction.
- **Phase 2:** Bitbucket read-only repository/PR flow (real integration or clearly blocked credential verification), current-commit scan, tests.
- **Phase 3:** export → reviewed Claude Code session → validated import → stale status; no automated Claude API.
- **Phase 4:** approval-gated isolated execution; baseline/head evidence; no unsafe host fallback.
- **Phase 5:** cohesive UI, release report, security review, end-to-end test evidence, demo.

## Suggested short competition schedule
- **11 Nov:** team kickoff, Phase 1 baseline and architecture.
- **12 Nov:** Phase 2 mocked/live read-only Bitbucket connector.
- **13 Nov:** Phase 3 manual Claude handoff and strict import.
- **14–15 Nov:** Phase 4 isolated regression proof, Phase 5 integration and hidden test.
- **16 Nov:** freeze, review, backup demo, competition entry.

If a phase fails its gate, record the limitation. A smaller working pipeline is preferable to declaring unfinished work complete.

## Critical guardrails
- Use synthetic demo data until source-sharing permissions are explicitly approved.
- Bitbucket needs its *own* scoped credentials; the Claude Team login doesn't grant Bitbucket access.
- A failed or blocked test must not be marked complete to satisfy a deadline.
- No teammate or AI agent directly merges or pushes into company repositories without authorized approval.

## Next file
Start with **`prompts/PHASE-01-FOUNDATION.md`** after the team lead assigns owners.
