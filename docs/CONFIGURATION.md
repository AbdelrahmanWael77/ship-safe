# Configuration

ShipSafe needs no configuration and no secrets to run the synthetic demo. Every setting below is optional. The only secret is the Bitbucket token, needed only if you turn Bitbucket on.

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
| `SHIPSAFE_DEMO_DIR` | `backend/demo-repo` | Where the synthetic LedgerLite repository is generated. It is always an allowed scanning root, so it gets the same drive-root check as `SHIPSAFE_ALLOWED_ROOT`. |

An unset variable and an empty one behave the same.

### Scanning scope

- With nothing configured, only the synthetic demo repository can be scanned. Every other path returns 403.
- The demo repository is always scannable, whatever `SHIPSAFE_ALLOWED_ROOT` is.
- `SHIPSAFE_ALLOWED_ROOT` accepts a single directory. Paths are resolved (symlinks and `..`) before the check.
- A drive root or filesystem root (`C:\`, `/`) is refused for both `SHIPSAFE_ALLOWED_ROOT` and `SHIPSAFE_DEMO_DIR`, and the API will not start.
- A `.git` *file* that redirects to another repository (as Git worktrees and submodules use) is accepted only when the repository it points to is also under an allowed root. Otherwise the scan is refused with 403.
- Only authorize a directory of repositories you are permitted to scan. Scanning runs read-only `git` commands against the repository with every path treated literally and with repository-defined diff drivers, text converters, hooks, filters and aliases verified not to run; exported handoff ZIPs contain its diffs.

```powershell
# Windows PowerShell
$env:SHIPSAFE_ALLOWED_ROOT = 'C:\work\approved-repos'
```
```bash
# macOS / Linux
export SHIPSAFE_ALLOWED_ROOT=/home/me/approved-repos
```

Then `POST /api/scans` with `repository_path`, `base_ref`, and `head_ref`. The dashboard has no control for choosing a non-demo repository.

## Bitbucket Cloud settings

Optional. With none of these set, Bitbucket is off and ShipSafe behaves exactly as before.

| Variable | Required | Meaning |
|---|---|---|
| `SHIPSAFE_BITBUCKET_WORKSPACE` | yes | Workspace slug. |
| `SHIPSAFE_BITBUCKET_REPOSITORIES` | yes | Comma-separated repository slugs ShipSafe may read. This is an allowlist: no other repository in the workspace is reachable. |
| `SHIPSAFE_BITBUCKET_TOKEN` | yes | **Secret.** Alone, it is sent as `Authorization: Bearer` (repository, project, or workspace access token). With the e-mail below, it is sent as Basic auth (Atlassian API token). |
| `SHIPSAFE_BITBUCKET_EMAIL` | no | Atlassian account e-mail. Set only when the token is a scoped API token. |

- **All or nothing.** If any of the four is set, the three required ones must all be set. A partial configuration (for example a workspace without a token), an invalid slug, an empty repository list, or a token that cannot be sent in a header raises `ConfigError` and the API does not start. Error messages name the variable, never its value.
- **Scope.** Give the credential read access to repositories and pull requests only. ShipSafe makes no Bitbucket writes.
- **Where the token lives.** Only in your local `.env` (git-ignored) or an approved secret store. Never commit it, paste it into a chat or prompt, or put it in a `VITE_*` variable.
- **Where it does not appear.** The token is wrapped in `config.Secret`: it is absent from `repr(settings)`, cannot be copied by `dataclasses.asdict`, serialised to JSON, or pickled, and is not in any log line or API response (`backend/tests/test_bitbucket_settings.py`). Only the HTTP client that talks to `api.bitbucket.org` receives it.
- **Current limit.** At startup the API builds the read-only connector from these settings and sends no request. No API route or dashboard screen uses it yet, and it has never been run against live Bitbucket.

## Network binding

Not configurable, on purpose.

- `scripts/dev.py` starts uvicorn with `--host 127.0.0.1 --port 8000`.
- `npm run dev` and `npm run preview` pass `--host 127.0.0.1`; the dev server uses port 5173 with `strictPort`.
- CORS allows only `http://localhost:5173` and `http://127.0.0.1:5173`.
- The API answers only to requests whose `Host` header is `127.0.0.1`, `localhost`, or `[::1]` (any port). Any other `Host` gets HTTP 400 before a route runs. This stops a web page from reaching the loopback API through DNS rebinding, which CORS alone does not prevent. The Vite proxy sets `changeOrigin`, so the dashboard is unaffected.

The API has no authentication. Do not start it with `--host 0.0.0.0` or put it behind a public proxy.

## Frontend setting

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_BASE` | empty | Base URL prefixed to API calls. Empty uses the dev-server `/api` proxy. Set it in `frontend/.env.local`. It is compiled into the browser bundle, so it must never hold a secret. |

## Not implemented

There are no Claude or other credential settings besides the Bitbucket token above, and no code that would read them.
