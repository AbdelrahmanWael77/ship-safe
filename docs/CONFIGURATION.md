# Configuration

ShipSafe needs no configuration and no secrets to run the synthetic demo. Every setting below is optional.

## How settings are read

- The backend reads `SHIPSAFE_*` variables from its process environment at startup (`backend/app/config.py`). Restart the API after changing one.
- `python scripts/dev.py` first loads `SHIPSAFE_*` lines from a `.env` file in the repository root, if one exists. Real environment variables take precedence. Values are used literally; there is no shell expansion.
- If you start uvicorn yourself, `.env` is **not** read. Export the variables in your shell.
- Copy `.env.example` to `.env` to begin. `.env` is git-ignored; `.env.example` must never contain real values.

## Backend settings

| Variable | Default | Meaning |
|---|---|---|
| `SHIPSAFE_ALLOWED_ROOT` | unset | One extra directory whose repositories may be scanned. The repository path must be this directory or lie beneath it. |
| `SHIPSAFE_DB_PATH` | `backend/.shipsafe-data/scans.db` | SQLite file for scans and imported reviews. |
| `SHIPSAFE_DEMO_DIR` | `backend/demo-repo` | Where the synthetic LedgerLite repository is generated. |

An unset variable and an empty one behave the same.

### Scanning scope

- With nothing configured, only the synthetic demo repository can be scanned. Every other path returns 403.
- The demo repository is always scannable, whatever `SHIPSAFE_ALLOWED_ROOT` is.
- `SHIPSAFE_ALLOWED_ROOT` accepts a single directory. Paths are resolved (symlinks and `..`) before the check.
- A drive root or filesystem root (`C:\`, `/`) is refused and the API will not start.
- Only authorize a directory of repositories you are permitted to scan and whose contents you trust. Scanning runs `git` against the repository, and exported handoff ZIPs contain its diffs.

```powershell
# Windows PowerShell
$env:SHIPSAFE_ALLOWED_ROOT = 'C:\work\approved-repos'
```
```bash
# macOS / Linux
export SHIPSAFE_ALLOWED_ROOT=/home/me/approved-repos
```

Then `POST /api/scans` with `repository_path`, `base_ref`, and `head_ref`. The dashboard has no control for choosing a non-demo repository.

## Network binding

Not configurable, on purpose.

- `scripts/dev.py` starts uvicorn with `--host 127.0.0.1 --port 8000`.
- `npm run dev` and `npm run preview` pass `--host 127.0.0.1`; the dev server uses port 5173 with `strictPort`.
- CORS allows only `http://localhost:5173` and `http://127.0.0.1:5173`.

The API has no authentication. Do not start it with `--host 0.0.0.0` or put it behind a public proxy.

## Frontend setting

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_BASE` | empty | Base URL prefixed to API calls. Empty uses the dev-server `/api` proxy. Set it in `frontend/.env.local`. It is compiled into the browser bundle, so it must never hold a secret. |

## Not implemented

There are no Bitbucket, Claude, or other credential settings, and no code that would read them. Phase 2 defines the Bitbucket variables; they must be read-only credentials kept in a local `.env` or an approved secret store, never committed, logged, or sent to the browser.
