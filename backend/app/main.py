"""ShipSafe API: local Git scanning, heuristic risk findings, persisted scan history."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError

from .ai_handoff import AIReviewImport, MAX_IMPORT_BYTES, context_digest, handoff_zip, saved_review, validate_review_binding
from .demo_seed import DEMO_BRANCHES, ensure_demo_repo
from .scanner import ScanError, git, scan_repository

BACKEND_DIR = Path(__file__).resolve().parents[1]


class ScanRequest(BaseModel):
    repository_path: str | None = Field(default=None, max_length=1024)
    base_ref: str = Field(default="main", min_length=1, max_length=150)
    head_ref: str = Field(default="feature/release-candidate", min_length=1, max_length=150)


def create_app(
    demo_root: Path | None = None,
    db_file: Path | None = None,
    allowed_root: Path | None = None,
) -> FastAPI:
    demo_root = (demo_root or Path(os.environ.get("SHIPSAFE_DEMO_DIR", BACKEND_DIR / "demo-repo"))).resolve()
    db_file = (db_file or Path(os.environ.get("SHIPSAFE_DB_PATH", BACKEND_DIR / ".shipsafe-data" / "scans.db"))).resolve()
    # Default: scan ONLY the synthetic repository. To enable other repos, set
    # SHIPSAFE_ALLOWED_ROOT to a directory you explicitly trust.
    allowed_root = (allowed_root or Path(os.environ.get("SHIPSAFE_ALLOWED_ROOT", str(demo_root)))).resolve()

    def connection():
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        return conn

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        ensure_demo_repo(demo_root)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        with connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, report_json TEXT NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS ai_reviews (
                id TEXT PRIMARY KEY,
                scan_id TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                review_json TEXT NOT NULL,
                FOREIGN KEY(scan_id) REFERENCES scans(id)
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_reviews_scan ON ai_reviews(scan_id, imported_at)")
        yield

    app = FastAPI(title="ShipSafe API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"], allow_headers=["*"],
    )

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.2.0", "mode": "local-first"}

    @app.get("/api/demo")
    def demo():
        return {
            "repository_path": str(demo_root), "name": "LedgerLite (synthetic)",
            "base_ref": "main", "default_head": "feature/release-candidate",
            "branches": DEMO_BRANCHES,
            "note": "All branches and source files are generated locally. No customer or company code is included.",
        }

    @app.post("/api/scans", status_code=201)
    def create_scan(body: ScanRequest):
        repo = Path(body.repository_path).expanduser().resolve() if body.repository_path else demo_root
        # Permit the explicit root itself or repositories under it, never unrelated paths.
        if not repo.is_relative_to(allowed_root):
            raise HTTPException(
                status_code=403,
                detail="Repository is outside SHIPSAFE_ALLOWED_ROOT. Scanning other paths requires explicit local configuration.",
            )
        try:
            report = scan_repository(repo, body.base_ref, body.head_ref)
        except ScanError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        with connection() as conn:
            conn.execute(
                "INSERT INTO scans (id, created_at, report_json) VALUES (?, ?, ?)",
                (report["id"], report["created_at"], json.dumps(report)),
            )
        return report

    @app.get("/api/scans")
    def list_scans(limit: int = Query(default=12, ge=1, le=100)):
        with connection() as conn:
            rows = conn.execute(
                "SELECT report_json FROM scans ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {key: report[key] for key in (
                "id", "created_at", "repo_name", "base_ref", "head_ref", "duration_ms", "summary"
            )}
            for row in rows for report in [json.loads(row["report_json"])]
        ]

    def read_report(scan_id: str) -> dict:
        with connection() as conn:
            row = conn.execute("SELECT report_json FROM scans WHERE id = ?", (scan_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Scan report not found")
        return json.loads(row["report_json"])

    @app.get("/api/scans/{scan_id}")
    def get_scan(scan_id: str):
        return read_report(scan_id)

    @app.get("/api/scans/{scan_id}/export")
    def export_scan(scan_id: str):
        report = read_report(scan_id)
        return JSONResponse(
            content=report,
            headers={"Content-Disposition": f'attachment; filename="shipsafe-{scan_id[:8]}.json"'},
        )

    @app.get("/api/scans/{scan_id}/ai/handoff")
    def download_ai_handoff(scan_id: str):
        report = read_report(scan_id)
        filename = f"shipsafe-handoff-{scan_id[:8]}.zip"
        return Response(
            content=handoff_zip(report),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
        )

    @app.get("/api/scans/{scan_id}/ai/context")
    def get_ai_context(scan_id: str):
        report = read_report(scan_id)
        return {"scan_id": scan_id, "context_digest": context_digest(report), "review_count": count_reviews(scan_id)}

    def count_reviews(scan_id: str) -> int:
        with connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM ai_reviews WHERE scan_id = ?", (scan_id,)).fetchone()[0]

    @app.post("/api/scans/{scan_id}/ai/reviews", status_code=201)
    async def import_ai_review(scan_id: str, request: Request):
        report = read_report(scan_id)
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_IMPORT_BYTES:
            raise HTTPException(413, detail="Review JSON is larger than the 256 KiB import limit")
        parts = []
        length_received = 0
        async for part in request.stream():
            length_received += len(part)
            if length_received > MAX_IMPORT_BYTES:
                raise HTTPException(413, detail="Review JSON is larger than the 256 KiB import limit")
            parts.append(part)
        try:
            data = json.loads(b"".join(parts))
            validated = AIReviewImport.model_validate(data)
        except (ValueError, UnicodeDecodeError, ValidationError) as exc:
            raise HTTPException(422, detail=f"Invalid Claude review JSON: {str(exc)[:700]}") from exc
        try:
            validate_review_binding(validated, report)
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from exc
        review = saved_review(validated)
        with connection() as conn:
            conn.execute(
                "INSERT INTO ai_reviews (id, scan_id, imported_at, review_json) VALUES (?, ?, ?, ?)",
                (review["id"], scan_id, review["imported_at"], json.dumps(review)),
            )
        return review

    @app.get("/api/scans/{scan_id}/ai/reviews")
    def list_ai_reviews(scan_id: str):
        read_report(scan_id)
        with connection() as conn:
            rows = conn.execute(
                "SELECT review_json FROM ai_reviews WHERE scan_id = ? ORDER BY imported_at DESC, rowid DESC LIMIT 25",
                (scan_id,),
            ).fetchall()
        return [json.loads(row["review_json"]) for row in rows]

    @app.get("/api/scans/{scan_id}/ai/reviews/latest")
    def latest_ai_review(scan_id: str):
        reviews = list_ai_reviews(scan_id)
        return reviews[0] if reviews else None

    @app.get("/api/repository/status")
    def repository_status():
        try:
            sha = git(demo_root, "rev-parse", "--short", "main").strip()
            branches = git(demo_root, "branch", "--format=%(refname:short)").splitlines()
            return {"repo": str(demo_root), "main_sha": sha, "branches": branches}
        except ScanError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


app = create_app()
