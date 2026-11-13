# ShipSafe — 5-minute demo script

Uses only the synthetic LedgerLite repository and invented mock data. **This script has not been rehearsed in a browser**; run through it once before presenting and correct anything that differs.

## Before the demo (10 minutes)

1. Two terminals in the repository root.
   - Terminal 1: `cd backend` then `..\.venv\Scripts\python -m uvicorn app.main:app --port 8000`
   - Terminal 2: `cd frontend` then `npm run dev:mock`
2. Open `http://127.0.0.1:5173`. The orange **MOCK DATA** banner must be visible: it means the Bitbucket screens show invented data.
3. Use a fresh database so the history is clean: set `SHIPSAFE_DB_PATH` to a new file before starting terminal 1.
4. Keep a second browser tab on `http://127.0.0.1:8000/docs` in case the dashboard fails.

## Script

| Time | Do | Say |
|---|---|---|
| 0:00 | Overview page | "ShipSafe looks at a code change before release and tells you what to check. It runs on your machine. This is a synthetic repository." |
| 0:30 | Compare branch → `feature/auth-regression` → **Run analysis** | "A real Git comparison between two commits. Nothing is executed." |
| 1:00 | **Risk findings**, open one, click its file link | "Static findings are suspicions, labelled as such. Here an ownership check was removed. This is the diff it came from." |
| 1:40 | **Claude Review** → Download handoff ZIP | "A developer reviews the change in their own Claude Code, with their own sign-in. ShipSafe has no API key. The package names the exact commits." |
| 2:10 | Import a prepared `claude-review.json` (see backup) | "The import is checked against the scan and commit. It is shown as unverified and never changes the static findings. Importing it twice is refused." |
| 2:50 | **Test intelligence** → existing tests panel | "ShipSafe finds existing tests that touch the change by reading them, not running them. These are happy-path tests; the fixture was written so that they do not cover the removed check." |
| 3:20 | Proposals: open "Propose a new test file", paste the prepared test, **Store proposal**, type a name, **Approve**, then **Run** | "A proposed test is stored as text. A person approves it by name. Run is blocked: there is no isolated runner, and ShipSafe will not run tests on this machine. It records the blocked request and invents no result." |
| 4:10 | **Release assessment** → Export report | "One page: suspicions, unverified AI suggestions, executed tests — zero — and what is not known. It never says 'safe'. The export carries the commits." |
| 4:40 | Sidebar → **Pull requests** (mock) → Analyze #106 → Scan | "The same flow for a Bitbucket pull request, read-only. This one's head moves while you look: the scan is refused and reloaded, and older scans and reviews go stale." |

## Prepared inputs

- Proposed test (paste as test source, target path `tests/test_auth_regression.py`):

  ```python
  from app.auth import get_invoice_for_user


  def test_other_user_is_refused():
      invoice = {"id": "inv-1", "owner_id": "alice"}
      assert get_invoice_for_user("mallory", invoice) is None
  ```

- `claude-review.json`: produce it before the demo from the handoff ZIP of the `feature/auth-regression` scan, in your own Claude Code session, following `REVIEW_INSTRUCTIONS.md`. A review is valid only for the scan it was exported from, so use the same database for preparation and demo, and open that scan from **Scan history** instead of scanning again at 0:30.

## Backup plan

- **Dashboard does not load:** show the same steps through `http://127.0.0.1:8000/docs` (`POST /api/scans`, `GET /api/scans/{id}/assessment`).
- **No prepared review file:** skip 2:10 and say so; show the import control and the "UNVERIFIED" labels on an empty state.
- **Backend not running** (`ECONNREFUSED 127.0.0.1:8000` in terminal 2): start terminal 1. Mock mode only fakes the Bitbucket screens.
- **Anything else:** `git stash` is not needed; restart both terminals. To return to a known state, delete the demo database file and restart.

## Do not claim

- That any test was run, or that a regression was confirmed. Execution is blocked.
- That Bitbucket was contacted. The demo uses mock data; live access is unverified.
- That a change is safe. The assessment never says so.
