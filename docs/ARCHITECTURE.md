# ShipSafe Architecture — Baseline v0.2 (pre-Phase 1)

This initial snapshot describes the packaged baseline. Claude and the team must verify it against code during Phase 1.

```text
React + Vite UI :5173
    │ /api proxy
    ▼
FastAPI :8000 ─── local Git CLI read-only comparisons
    │           ├── Python AST heuristics / changed file mapping
    │           └── synthetic LedgerLite Git fixture
    ├── SQLite scan/history and imported Claude review metadata
    └── manual ZIP handoff → developer-controlled Claude Code session
                     ← validated JSON review import
```

- Entry point: `backend/app/main.py`, created via `create_app()`.
- Scanner: `backend/app/scanner.py`.
- Demo repo initializer: `backend/app/demo_seed.py`.
- Manual AI handoff/schema: `backend/app/ai_handoff.py`.
- Frontend: `frontend/src/App.tsx`, `frontend/src/types.ts`, styles.
- Startup helper: `scripts/dev.py`.

**Not baseline features:** native Bitbucket connector, isolated test runner, AI-authenticated API, multi-user authorization, CI gating. These are planned for subsequent phases.
