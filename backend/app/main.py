"""ShipSafe API: local Git scanning, read-only Bitbucket pull request scanning,
heuristic risk findings, persisted scan history."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager, contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, ValidationError

from .ai_handoff import MAX_IMPORT_BYTES, parse_review, review_content_digest, context_digest, handoff_zip, saved_review, validate_review_binding
from .config import load_settings
from .db import BINDING_COLUMNS, binding, insert_scan, migrate, pull_request_scans, scanned_pull_requests, session, sync_stale
from .discovery import discover_tests
from .proposals import (
    MAX_REQUEST_BYTES as MAX_PROPOSAL_REQUEST_BYTES, PROPOSAL_COLUMNS, DecisionRequest, ProposalError, ProposalRequest,
    check_against_tree, insert_decision, insert_proposal, served as served_proposal, validate_content, validate_target_path,
)
from .demo_seed import DEMO_BRANCHES, ensure_demo_repo
from .errors import (
    ChangeTooLarge, ProviderAuthError, ProviderError, ProviderUnavailable, PullRequestNotFound, RefNotFound,
    RepositoryAccessDenied, RepositoryNotFound, ScanError,
)
from .providers import BitbucketCloudProvider, LocalGitProvider
from .scanner import git, scan_change_set


#: Host header values the development API answers to. Port suffixes are
#: ignored by the middleware, so "127.0.0.1:8000" matches "127.0.0.1".
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]")


#: Import analysis over Bitbucket costs one request per file, so it is bounded.
#: A report cut by this bound says so in its summary.
BITBUCKET_IMPORT_READS = 200
# Test files read from Bitbucket for one test discovery (one request each).
BITBUCKET_TEST_READS = 60
#: Listing pull requests refreshes the stale marker of those that already
#: have scans; each refresh is one or more Bitbucket requests, so it is bounded.
STALE_CHECKS_PER_LIST = 20


class BitbucketFailure(Exception):
    """A Bitbucket route could not answer. Rendered as ``{"detail", "code"}``."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def bitbucket_failure(exc: ScanError) -> BitbucketFailure:
    """Map provider errors to HTTP. Most specific first; messages come from
    the provider and never contain the credential.

    A rejected credential is 502, not 401: the browser user did nothing wrong
    and cannot fix it; the server's Bitbucket configuration has to change.
    """
    table: tuple[tuple[type, int, str], ...] = (
        (RepositoryAccessDenied, 403, "repository_not_allowed"),
        (RepositoryNotFound, 404, "repository_not_found"),
        (PullRequestNotFound, 404, "pull_request_not_found"),
        (RefNotFound, 404, "commit_not_found"),
        (ChangeTooLarge, 422, "diff_too_large"),
        (ProviderAuthError, 502, "bitbucket_auth_failed"),
        (ProviderUnavailable, 503, "bitbucket_unavailable"),
        (ProviderError, 502, "bitbucket_error"),
    )
    for kind, status, code in table:
        if isinstance(exc, kind):
            return BitbucketFailure(status, code, str(exc))
    return BitbucketFailure(400, "invalid_request", str(exc))


@contextmanager
def bitbucket_errors():
    try:
        yield
    except ScanError as exc:
        raise bitbucket_failure(exc) from exc


class PullRequestScanRequest(BaseModel):
    #: Optional guard: the full head SHA the caller is looking at. The scan is
    #: refused with 409 if the pull request has moved on since.
    head_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40}$")


class ScanRequest(BaseModel):
    repository_path: str | None = Field(default=None, max_length=1024)
    base_ref: str = Field(default="main", min_length=1, max_length=150)
    head_ref: str = Field(default="feature/release-candidate", min_length=1, max_length=150)


def create_app(
    demo_root: Path | None = None,
    db_file: Path | None = None,
    allowed_root: Path | None = None,
    bitbucket: BitbucketCloudProvider | None = None,
) -> FastAPI:
    """``bitbucket`` overrides the provider built from settings (tests pass one
    with a mocked transport)."""
    settings = load_settings(demo_root=demo_root, db_file=db_file, allowed_root=allowed_root)
    demo_root, db_file = settings.demo_dir, settings.db_path
    # Deny by default: only the synthetic repository is scannable unless
    # SHIPSAFE_ALLOWED_ROOT names a directory you explicitly trust.
    provider = LocalGitProvider(settings.allowed_roots)
    # Built only when SHIPSAFE_BITBUCKET_* is fully configured; no request is
    # sent here. Invalid slugs raise ConfigError, so the API does not start.
    if bitbucket is None and settings.bitbucket:
        bitbucket = BitbucketCloudProvider(
            settings.bitbucket.workspace, settings.bitbucket.repositories,
            token=settings.bitbucket.token.reveal(), email=settings.bitbucket.email,
        )

    def connection():
        return session(db_file)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        ensure_demo_repo(demo_root)
        migrate(db_file)
        yield

    app = FastAPI(title="ShipSafe API", version="0.2.0", lifespan=lifespan)
    app.state.bitbucket = bitbucket
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"], allow_headers=["*"],
    )
    # DNS rebinding defence. The API has no authentication and binds to
    # loopback; a hostile web page can still reach it by pointing its own
    # domain at 127.0.0.1, which makes the request same-origin and bypasses
    # CORS. Such requests carry the attacker's Host header, so refuse every
    # Host that is not a loopback name. Added last so it runs before CORS.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOOPBACK_HOSTS)

    @app.exception_handler(BitbucketFailure)
    async def bitbucket_failure_response(_request: Request, exc: BitbucketFailure):
        # "detail" stays a string, like every other handled error of this API.
        return JSONResponse(status_code=exc.status, content={"detail": exc.message, "code": exc.code})

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
        try:
            # The provider permits an allowed root itself or repositories under it, never unrelated paths.
            repository = provider.get_repository(body.repository_path or str(demo_root))
            report, changes = scan_change_set(provider, repository, body.base_ref, body.head_ref)
        except RepositoryAccessDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ScanError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        with connection() as conn:
            insert_scan(
                conn, report, provider=repository.provider, repository_id=repository.id,
                base_commit=changes.base_sha, head_commit=changes.head_sha,
            )
        return read_scan(report["id"])

    @app.get("/api/scans")
    def list_scans(limit: int = Query(default=12, ge=1, le=100)):
        with connection() as conn:
            rows = conn.execute(
                f"SELECT report_json, {BINDING_COLUMNS} FROM scans ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {**{key: report[key] for key in (
                "id", "created_at", "repo_name", "base_ref", "head_ref", "duration_ms", "summary"
            )}, "binding": binding(row)}
            for row in rows for report in [json.loads(row["report_json"])]
        ]

    def read_report(scan_id: str) -> dict:
        """The report exactly as stored. The Claude handoff and its digest are
        built from this, so nothing may be added to it here."""
        with connection() as conn:
            row = conn.execute("SELECT report_json FROM scans WHERE id = ?", (scan_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Scan report not found")
        return json.loads(row["report_json"])

    def read_scan(scan_id: str, *, stale_checked: bool = False) -> dict:
        """The stored report plus ``binding`` (full SHAs, provider, pull
        request, stale marker) from the columns beside it."""
        with connection() as conn:
            row = conn.execute(f"SELECT report_json, {BINDING_COLUMNS} FROM scans WHERE id = ?", (scan_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Scan report not found")
        return {**json.loads(row["report_json"]), "binding": binding(row, stale_checked=stale_checked)}

    @app.get("/api/scans/{scan_id}")
    def get_scan(scan_id: str):
        return read_scan(scan_id)

    @app.get("/api/scans/{scan_id}/export")
    def export_scan(scan_id: str):
        report = read_scan(scan_id)
        return JSONResponse(
            content=report,
            headers={"Content-Disposition": f'attachment; filename="shipsafe-{scan_id[:8]}.json"'},
        )

    def review_inputs(scan_id: str) -> tuple[dict, dict]:
        """The stored report and its binding: what the Claude package and its
        digest are built from. The binding supplies identity and exact commits."""
        scan = read_scan(scan_id)
        source = scan.pop("binding")
        return scan, source

    def needs_acknowledgement(report: dict, source: dict) -> bool:
        """True unless the scan is of the synthetic demo repository. Exporting
        any other code requires the person to confirm they may share it."""
        if source.get("provider") != "local-git":
            return True
        try:
            return Path(report.get("repository_path") or "").resolve() != Path(demo_root).resolve()
        except OSError:
            return True

    @app.get("/api/scans/{scan_id}/ai/handoff")
    def download_ai_handoff(scan_id: str, acknowledge_source_sharing: bool = False):
        report, source = review_inputs(scan_id)
        if needs_acknowledgement(report, source) and not acknowledge_source_sharing:
            raise HTTPException(
                status_code=428,
                detail="This package contains source code that is not the synthetic demo. Confirm that you are "
                       "allowed to share it with Claude Code (acknowledge_source_sharing=true) to export it.",
            )
        filename = f"shipsafe-handoff-{scan_id[:8]}.zip"
        return Response(
            content=handoff_zip(report, source),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
        )

    @app.get("/api/scans/{scan_id}/ai/context")
    def get_ai_context(scan_id: str):
        report, source = review_inputs(scan_id)
        return {
            "scan_id": scan_id, "context_digest": context_digest(report, source), "review_count": count_reviews(scan_id),
            "acknowledgement_required": needs_acknowledgement(report, source),
        }

    def count_reviews(scan_id: str) -> int:
        with connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM ai_reviews WHERE scan_id = ?", (scan_id,)).fetchone()[0]

    @app.post("/api/scans/{scan_id}/ai/reviews", status_code=201)
    async def import_ai_review(scan_id: str, request: Request):
        report, source = review_inputs(scan_id)
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
            validated = parse_review(data)
        except (ValueError, ValidationError, RecursionError) as exc:
            raise HTTPException(422, detail=f"Invalid Claude review JSON: {str(exc)[:700]}") from exc
        try:
            validate_review_binding(validated, report, source)
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from exc
        review = saved_review(validated)
        digest = review_content_digest(review)
        with connection() as conn:
            # Same connection as the insert, so two identical imports cannot both pass the check.
            existing = conn.execute("SELECT review_json FROM ai_reviews WHERE scan_id = ?", (scan_id,)).fetchall()
            if any(review_content_digest(json.loads(row["review_json"])) == digest for row in existing):
                raise HTTPException(409, detail="This review was already imported for this scan. Nothing was added.")
            conn.execute(
                "INSERT INTO ai_reviews (id, scan_id, imported_at, review_json) VALUES (?, ?, ?, ?)",
                (review["id"], scan_id, review["imported_at"], json.dumps(review)),
            )
        return served_review(review, scan_id, source)

    def served_review(review: dict, scan_id: str, scan_binding: dict) -> dict:
        """A stored review plus the scan it belongs to and that scan's binding.

        ``scan_binding.stale`` is how a review becomes stale: a review is only
        as current as the scan it was made for, and the scan is marked when the
        pull request's head moves. Nothing is written into the stored review.
        """
        return {**review, "scan_id": scan_id, "scan_binding": scan_binding}

    @app.get("/api/scans/{scan_id}/ai/reviews")
    def list_ai_reviews(scan_id: str):
        scan_binding = read_scan(scan_id)["binding"]
        with connection() as conn:
            rows = conn.execute(
                "SELECT review_json FROM ai_reviews WHERE scan_id = ? ORDER BY imported_at DESC, rowid DESC LIMIT 25",
                (scan_id,),
            ).fetchall()
        return [served_review(json.loads(row["review_json"]), scan_id, scan_binding) for row in rows]

    @app.get("/api/scans/{scan_id}/ai/reviews/history")
    def ai_review_history(scan_id: str):
        """Reviews of this scan and, for a pull request scan, of every other
        stored scan of the same pull request, newest first. Each carries its
        own scan's binding, so a review of an outdated head shows as stale."""
        scan_binding = read_scan(scan_id)["binding"]
        if scan_binding["pull_request_id"] is None:
            return [{**review, "current_scan": True} for review in list_ai_reviews(scan_id)]
        with connection() as conn:
            rows = conn.execute(
                f"SELECT r.review_json, s.id AS review_scan_id, {', '.join('s.' + c.strip() for c in BINDING_COLUMNS.split(','))}"
                " FROM ai_reviews r JOIN scans s ON s.id = r.scan_id"
                " WHERE s.provider = ? AND s.repository_id = ? AND s.pull_request_id = ?"
                " ORDER BY r.imported_at DESC, r.rowid DESC LIMIT 50",
                (scan_binding["provider"], scan_binding["repository_id"], scan_binding["pull_request_id"]),
            ).fetchall()
        return [
            {**served_review(json.loads(row["review_json"]), row["review_scan_id"], binding(row)),
             "current_scan": row["review_scan_id"] == scan_id}
            for row in rows
        ]

    @app.get("/api/scans/{scan_id}/tests/discovery")
    def discover_scan_tests(scan_id: str):
        """Existing tests that may exercise this scan's change (Phase 4 task A).

        Static: test files are read at the scan's head commit and parsed, never
        imported or run. Read-only towards the repository and Bitbucket.
        """
        report, source = review_inputs(scan_id)
        commit = source.get("head_commit")
        if not commit:
            raise HTTPException(409, detail="This scan is not bound to a commit, so tests cannot be discovered for it. Scan again.")
        reviews = list_ai_reviews(scan_id)
        ai_findings = reviews[0]["findings"] if reviews else []
        if source["provider"] == "local-git":
            try:
                repository = provider.get_repository(report["repository_path"])
                discovery = discover_tests(provider, repository, commit, report, ai_findings=ai_findings)
            except RepositoryAccessDenied as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            except ScanError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            remote = require_bitbucket()
            with bitbucket_errors():
                repository = remote.get_repository(source["repository_id"])
                discovery = discover_tests(
                    remote, repository, commit, report, ai_findings=ai_findings, max_files=BITBUCKET_TEST_READS)
        return {"scan_id": scan_id, "ai_review_id": reviews[0]["id"] if reviews else None, **discovery}

    # -- Phase 4 task B: proposed tests and human decisions (nothing is applied or run) --

    def scan_tree(report: dict, source: dict) -> list[str]:
        """Paths in the repository at the scan's head commit (read-only)."""
        if source["provider"] == "local-git":
            try:
                repository = provider.get_repository(report["repository_path"])
                return provider.list_files(repository, source["head_commit"])
            except RepositoryAccessDenied as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            except ScanError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        remote = require_bitbucket()
        with bitbucket_errors():
            return remote.list_files(remote.get_repository(source["repository_id"]), source["head_commit"])

    async def limited_json(request: Request, limit: int) -> object:
        received, parts = 0, []
        async for part in request.stream():
            received += len(part)
            if received > limit:
                raise HTTPException(413, detail=f"Request is larger than the {limit // 1024} KiB limit")
            parts.append(part)
        try:
            return json.loads(b"".join(parts))
        except (ValueError, RecursionError) as exc:
            raise HTTPException(422, detail=f"Invalid JSON: {str(exc)[:300]}") from exc

    def proposal_rows(conn, scan_id: str, proposal_id: str | None = None):
        sql = f"SELECT {PROPOSAL_COLUMNS} FROM test_proposals WHERE scan_id = ?"
        args: tuple = (scan_id,)
        if proposal_id is not None:
            sql, args = sql + " AND id = ?", (scan_id, proposal_id)
        return conn.execute(sql + " ORDER BY created_at DESC, rowid DESC LIMIT 100", args).fetchall()

    @app.get("/api/scans/{scan_id}/tests/proposals")
    def list_test_proposals(scan_id: str):
        stale = read_scan(scan_id)["binding"]["stale"]
        with connection() as conn:
            return [served_proposal(conn, row, scan_stale=stale) for row in proposal_rows(conn, scan_id)]

    @app.post("/api/scans/{scan_id}/tests/proposals", status_code=201)
    async def create_test_proposal(scan_id: str, request: Request):
        report, source = review_inputs(scan_id)
        if not source.get("head_commit") or not source.get("base_commit"):
            raise HTTPException(409, detail="This scan is not bound to exact commits, so a test cannot be proposed for it. Scan again.")
        if source["stale"]:
            raise HTTPException(409, detail="The pull request has new commits since this scan. Scan again and propose the test for the new scan.")
        data = await limited_json(request, MAX_PROPOSAL_REQUEST_BYTES)
        try:
            body = ProposalRequest.model_validate(data)
            validate_target_path(body.target_path)
            validate_content(body.content)
        except ValidationError as exc:
            raise HTTPException(422, detail=f"Invalid test proposal: {str(exc)[:700]}") from exc
        except ProposalError as exc:
            raise HTTPException(exc.status, detail=str(exc)) from exc
        if body.finding_ref is not None:
            known = {item["id"] for item in report["findings"]}
            known |= {str(f["id"]) for review in list_ai_reviews(scan_id) for f in review["findings"] if f.get("id")}
            if body.finding_ref not in known:
                raise HTTPException(409, detail=f"Unknown finding for this scan: {body.finding_ref}")
        tree = scan_tree(report, source)
        try:
            check_against_tree(body.target_path, tree)
            with connection() as conn:
                proposal_id = insert_proposal(
                    conn, scan_id=scan_id, request=body, base_commit=source["base_commit"], head_commit=source["head_commit"])
                return served_proposal(conn, proposal_rows(conn, scan_id, proposal_id)[0], scan_stale=False)
        except ProposalError as exc:
            raise HTTPException(exc.status, detail=str(exc)) from exc

    @app.post("/api/scans/{scan_id}/tests/proposals/{proposal_id}/decisions", status_code=201)
    async def decide_test_proposal(scan_id: str, proposal_id: str, request: Request):
        """Record an explicit human decision. Approving does not apply or run anything."""
        stale = read_scan(scan_id)["binding"]["stale"]
        data = await limited_json(request, 16 * 1024)
        try:
            body = DecisionRequest.model_validate(data)
        except ValidationError as exc:
            raise HTTPException(422, detail=f"Invalid decision: {str(exc)[:700]}") from exc
        with connection() as conn:
            rows = proposal_rows(conn, scan_id, proposal_id)
            if not rows:
                raise HTTPException(404, detail="Test proposal not found for this scan")
            if stale and body.decision == "approved":
                raise HTTPException(409, detail="This proposal is stale: the pull request has new commits since its scan. It can be rejected, not approved.")
            try:
                insert_decision(conn, proposal_id=proposal_id, request=body)
            except ProposalError as exc:
                raise HTTPException(exc.status, detail=str(exc)) from exc
            return served_proposal(conn, rows[0], scan_stale=stale)

    @app.get("/api/scans/{scan_id}/ai/reviews/latest")
    def latest_ai_review(scan_id: str):
        reviews = list_ai_reviews(scan_id)
        return reviews[0] if reviews else None

    # -- Bitbucket (read-only) ------------------------------------------------

    def require_bitbucket() -> BitbucketCloudProvider:
        if bitbucket is None:
            raise BitbucketFailure(
                503, "bitbucket_not_configured",
                "Bitbucket is not configured. Set SHIPSAFE_BITBUCKET_WORKSPACE, SHIPSAFE_BITBUCKET_REPOSITORIES "
                "and SHIPSAFE_BITBUCKET_TOKEN on the server, then restart the API.",
            )
        return bitbucket

    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def repository_json(repository) -> dict:
        return {
            "id": repository.id, "slug": repository.id.partition("/")[2], "name": repository.name,
            "url": repository.location, "default_branch": repository.default_branch,
        }

    def refresh_stale(conn, pull_request) -> bool:
        """Record what Bitbucket just told us about this pull request's head.

        Returns whether the check happened: it cannot when the head commit is
        unreadable (fork, deleted branch), and then stored markers are left as
        they were.
        """
        if not pull_request.source_sha:
            return False
        sync_stale(
            conn, provider=pull_request.provider, repository_id=pull_request.repository_id,
            pull_request_id=pull_request.id, current_head=pull_request.source_sha, observed_at=now(),
        )
        return True

    def not_scannable(pull_request) -> tuple[str, str] | None:
        if not pull_request.source_sha:
            return ("head_commit_unavailable",
                    "The pull request's head commit cannot be read through the approved repository "
                    "(for example a pull request from a fork, or a deleted source branch), so a scan "
                    "could not be bound to an exact commit.")
        if not pull_request.target_sha:
            return ("base_commit_unavailable",
                    "The pull request's target branch commit cannot be read, so the comparison base is unknown.")
        return None

    @app.get("/api/bitbucket/status")
    def bitbucket_status():
        """Whether Bitbucket is configured. Never includes the credential."""
        if bitbucket is None:
            return {"configured": False, "provider": None, "workspace": None, "repositories": []}
        return {"configured": True, "provider": bitbucket.name, "workspace": bitbucket.workspace,
                "repositories": list(bitbucket.repositories)}

    @app.get("/api/bitbucket/repositories")
    def bitbucket_repositories():
        provider = require_bitbucket()
        with bitbucket_errors():
            return [repository_json(repository) for repository in provider.list_repositories()]

    @app.get("/api/bitbucket/repositories/{slug}/pull-requests")
    def bitbucket_pull_requests(slug: str, state: str = Query(default="open", pattern="^(open|merged|declined)$")):
        provider = require_bitbucket()
        with bitbucket_errors():
            repository = provider.get_repository(f"{provider.workspace}/{slug}")
            listed, truncated = provider.list_pull_requests_page(repository, state)
            with connection() as conn:
                counts = scanned_pull_requests(conn, provider=provider.name, repository_id=repository.id)
            # The list payload carries abbreviated hashes only. Pull requests
            # that already have scans are looked up individually (bounded) so
            # their full head SHA is known and their stale marker is current.
            budget = STALE_CHECKS_PER_LIST
            items = []
            for pull_request in listed:
                looked_up = False
                if counts.get(pull_request.id) and budget > 0:
                    budget -= 1
                    pull_request = provider.get_pull_request(repository, pull_request.id)
                    looked_up = True
                with connection() as conn:
                    checked = refresh_stale(conn, pull_request) if looked_up else False
                    latest = pull_request_scans(
                        conn, provider=provider.name, repository_id=repository.id,
                        pull_request_id=pull_request.id, limit=1, stale_checked=checked,
                    ) if counts.get(pull_request.id) else []
                items.append({
                    **asdict(pull_request), "scan_count": counts.get(pull_request.id, 0),
                    "latest_scan": latest[0] if latest else None, "stale_checked": checked,
                })
            # "truncated": Bitbucket has more pull requests in this state than the list returns.
            return {"repository": repository_json(repository), "state": state, "pull_requests": items,
                    "truncated": truncated}

    @app.get("/api/bitbucket/repositories/{slug}/pull-requests/{pull_request_id}")
    def bitbucket_pull_request(slug: str, pull_request_id: str):
        provider = require_bitbucket()
        with bitbucket_errors():
            repository = provider.get_repository(f"{provider.workspace}/{slug}")
            pull_request = provider.get_pull_request(repository, pull_request_id)
        blocked = not_scannable(pull_request)
        with connection() as conn:
            checked = refresh_stale(conn, pull_request)
            scans = pull_request_scans(
                conn, provider=provider.name, repository_id=repository.id, pull_request_id=pull_request.id,
                stale_checked=checked,
            )
        return {
            **asdict(pull_request), "repository": repository_json(repository),
            "scannable": blocked is None, "not_scannable_code": blocked[0] if blocked else None,
            "not_scannable_reason": blocked[1] if blocked else None, "stale_checked": checked, "scans": scans,
        }

    @app.post("/api/bitbucket/repositories/{slug}/pull-requests/{pull_request_id}/scans", status_code=201)
    def scan_bitbucket_pull_request(slug: str, pull_request_id: str, body: PullRequestScanRequest | None = None):
        """Scan a pull request from its merge base to its current head commit.

        Reads only. The stored scan is bound to the two full SHAs; earlier
        scans of the same pull request with another head are marked stale.
        """
        provider = require_bitbucket()
        with bitbucket_errors():
            repository = provider.get_repository(f"{provider.workspace}/{slug}")
            pull_request = provider.get_pull_request(repository, pull_request_id)
            with connection() as conn:
                refresh_stale(conn, pull_request)
            blocked = not_scannable(pull_request)
            if blocked:
                raise BitbucketFailure(409, *blocked)
            if body and body.head_commit and body.head_commit != pull_request.source_sha:
                raise BitbucketFailure(
                    409, "head_changed",
                    "The pull request has new commits since it was loaded. Reload it and scan again.",
                )
            base = provider.merge_base(repository, pull_request.target_sha, pull_request.source_sha)
            report, changes = scan_change_set(
                provider, repository, base, pull_request.source_sha, max_import_reads=BITBUCKET_IMPORT_READS,
            )
        # Show branch names like a local scan does; the SHAs carry the binding.
        report["base_ref"], report["head_ref"] = pull_request.target_ref, pull_request.source_ref
        with connection() as conn:
            insert_scan(
                conn, report, provider=provider.name, repository_id=repository.id, pull_request_id=pull_request.id,
                base_commit=changes.base_sha, head_commit=changes.head_sha,
            )
        # Bound to the head Bitbucket reported moments ago, so this one is checked.
        return read_scan(report["id"], stale_checked=True)

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
