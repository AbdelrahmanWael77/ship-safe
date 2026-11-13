"""Phase 2 task 4: Bitbucket API routes, pull request scans, binding and
stale detection, driven through the real provider over mocked HTTP.

Nothing here talks to the network (``httpx.MockTransport``). Payload shapes
follow Bitbucket's published OpenAPI description, not observed responses.
"""
from __future__ import annotations

import io
import json
import sqlite3
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.ai_handoff import context_digest
from app.errors import ProviderError, RefNotFound, ScanError
from app.main import create_app
from test_bitbucket_provider import LEDGER, TOKEN, FakeBitbucket, js

REPO = "/repositories/acme/ledger"
BASE, TARGET, HEAD, HEAD2 = "a" * 40, "c" * 40, "b" * 40, "d" * 40
ROUTES = "/api/bitbucket/repositories"
PR_URL = f"{ROUTES}/ledger/pull-requests/7"

BEFORE = "def get_invoice(user, invoice):\n    if invoice.owner_id != user.id:\n        raise PermissionError()\n    return invoice\n"
AFTER = "def get_invoice(user, invoice):\n    return invoice\n"
DIFF = (
    "diff --git a/app/auth.py b/app/auth.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/app/auth.py\n"
    "+++ b/app/auth.py\n"
    "@@ -1,4 +1,2 @@\n"
    " def get_invoice(user, invoice):\n"
    "-    if invoice.owner_id != user.id:\n"
    "-        raise PermissionError()\n"
    "     return invoice\n"
)
STAT = {"status": "modified", "lines_added": 0, "lines_removed": 2, "old": {"path": "app/auth.py"}, "new": {"path": "app/auth.py"}}


def pull_request(number=7, head=HEAD, target=TARGET, **extra):
    return {
        "id": number, "title": f"Change {number}", "state": "OPEN",
        "source": {"branch": {"name": f"feature/change-{number}"}, "commit": {"hash": head[:12]}},
        "destination": {"branch": {"name": "main"}, "commit": {"hash": target[:12]}},
        "author": {"display_name": "Dev One"}, "updated_on": "2026-11-12T10:00:00+00:00",
        "links": {"html": {"href": "https://evil.example/pr"}}, **extra,
    }


def scan_routes(head=HEAD, tree=("app/auth.py", "app/views.py", "README.md")):
    """Everything one pull request scan at ``head`` reads."""
    return {
        f"{REPO}/commit/{head[:12]}": js({"hash": head}),
        f"{REPO}/commit/{head}": js({"hash": head}),
        f"{REPO}/merge-base/{TARGET}..{head}": js({"hash": BASE}),
        f"{REPO}/diffstat/{head}..{BASE}": js({"values": [STAT], "size": 1}),
        f"{REPO}/diff/{head}..{BASE}": httpx.Response(200, text=DIFF),
        f"{REPO}/src/{head}/app/auth.py": httpx.Response(200, text=AFTER),
        f"{REPO}/src/{head}/": js({"values": [{"type": "commit_file", "path": path} for path in tree]}),
        **{f"{REPO}/src/{head}/{path}": httpx.Response(200, text="from app.auth import get_invoice\n")
           for path in tree if path.endswith(".py") and path != "app/auth.py"},
    }


def bitbucket(**extra):
    return FakeBitbucket({
        "/repositories/acme": js({"values": [{"slug": "ledger", "name": "Ledger", "mainbranch": {"name": "main"}},
                                             {"slug": "secret", "name": "Secret"}]}),
        REPO: js({"slug": "ledger", "name": "Ledger", "mainbranch": {"name": "main"}}),
        f"{REPO}/pullrequests": js({"values": [pull_request(7), pull_request(8)]}),
        f"{REPO}/pullrequests/7": js(pull_request(7)),
        f"{REPO}/commit/{TARGET[:12]}": js({"hash": TARGET}),
        f"{REPO}/commit/{BASE}": js({"hash": BASE}),
        f"{REPO}/src/{BASE}/app/auth.py": httpx.Response(200, text=BEFORE),
        **scan_routes(), **extra,
    })


@pytest.fixture()
def make_client(tmp_path):
    clients = []

    def build(fake=None, **provider_kwargs):
        provider = fake.provider(**provider_kwargs) if fake else None
        app = create_app(demo_root=tmp_path / "demo", db_file=tmp_path / "scans.db", bitbucket=provider)
        client = TestClient(app, base_url="http://127.0.0.1")
        client.__enter__()
        clients.append(client)
        return client

    yield build
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture()
def no_bitbucket_env(monkeypatch):
    for name in ("WORKSPACE", "REPOSITORIES", "TOKEN", "EMAIL"):
        monkeypatch.delenv(f"SHIPSAFE_BITBUCKET_{name}", raising=False)


def scan_rows(tmp_path):
    conn = sqlite3.connect(tmp_path / "scans.db")
    try:
        return conn.execute(
            "SELECT id, provider, repository_id, pull_request_id, base_commit, head_commit, stale_at FROM scans ORDER BY created_at"
        ).fetchall()
    finally:
        conn.close()


def move_head(fake, head):
    """The pull request gets a new head commit on Bitbucket."""
    fake.routes[f"{REPO}/pullrequests/7"] = js(pull_request(7, head=head))
    fake.routes.update(scan_routes(head))


# -- not configured ----------------------------------------------------------

def test_every_bitbucket_route_answers_503_when_bitbucket_is_not_configured(make_client, no_bitbucket_env):
    client = make_client()
    assert client.get("/api/bitbucket/status").json() == {
        "configured": False, "provider": None, "workspace": None, "repositories": [],
    }
    for response in (client.get(ROUTES), client.get(f"{ROUTES}/ledger/pull-requests"), client.get(PR_URL),
                     client.post(f"{PR_URL}/scans")):
        assert response.status_code == 503
        assert response.json()["code"] == "bitbucket_not_configured"
        assert "SHIPSAFE_BITBUCKET_TOKEN" in response.json()["detail"]  # a string, like every other API error
    assert client.post("/api/scans", json={}).status_code == 201  # local scanning does not need Bitbucket


# -- discovery ---------------------------------------------------------------

def test_status_names_the_workspace_and_allowlist_but_never_the_token(make_client):
    response = make_client(bitbucket(), repositories=("ledger", "billing")).get("/api/bitbucket/status")
    assert response.json() == {
        "configured": True, "provider": "bitbucket-cloud", "workspace": "acme", "repositories": ["ledger", "billing"],
    }
    assert TOKEN not in response.text


def test_repository_list_returns_only_approved_repositories(make_client):
    assert make_client(bitbucket()).get(ROUTES).json() == [{
        "id": "acme/ledger", "slug": "ledger", "name": "Ledger",
        "url": "https://bitbucket.org/acme/ledger", "default_branch": "main",
    }]


def test_pull_request_list_without_scans_makes_no_extra_lookups(make_client):
    fake = bitbucket()
    body = make_client(fake).get(f"{ROUTES}/ledger/pull-requests").json()
    assert body["repository"]["id"] == "acme/ledger" and body["state"] == "open"
    assert [item["id"] for item in body["pull_requests"]] == ["7", "8"]
    first = body["pull_requests"][0]
    assert first == {
        "provider": "bitbucket-cloud", "repository_id": "acme/ledger", "id": "7", "title": "Change 7", "state": "open",
        "source_ref": "feature/change-7", "target_ref": "main", "source_sha": None, "target_sha": None,
        "author": "Dev One", "url": "https://bitbucket.org/acme/ledger/pull-requests/7",  # built locally, not copied
        "updated_at": "2026-11-12T10:00:00+00:00", "scan_count": 0, "latest_scan": None, "stale_checked": False,
    }
    assert fake.paths() == [REPO, f"{REPO}/pullrequests"]


def test_pull_request_state_filter_is_validated(make_client):
    client = make_client(bitbucket())
    assert client.get(f"{ROUTES}/ledger/pull-requests", params={"state": "merged"}).status_code == 200
    assert client.get(f"{ROUTES}/ledger/pull-requests", params={"state": "everything"}).status_code == 422


def test_pull_request_detail_carries_full_shas_and_scannability(make_client):
    body = make_client(bitbucket()).get(PR_URL).json()
    assert (body["source_sha"], body["target_sha"]) == (HEAD, TARGET)
    assert body["scannable"] is True and body["not_scannable_code"] is None
    assert body["scans"] == [] and body["repository"]["slug"] == "ledger"


# -- scan: repository -> pull request -> scan -> findings ---------------------

def test_pull_request_scan_end_to_end_is_bound_to_merge_base_and_head(make_client, tmp_path):
    fake = bitbucket()
    client = make_client(fake)
    assert client.get(ROUTES).json()[0]["slug"] == "ledger"
    assert client.get(f"{ROUTES}/ledger/pull-requests").json()["pull_requests"][0]["id"] == "7"

    response = client.post(f"{PR_URL}/scans")
    assert response.status_code == 201
    report = response.json()

    assert [finding["title"] for finding in report["findings"]] == ["Possible authorization guard removal"]
    assert report["findings"][0]["file"] == "app/auth.py" and report["findings"][0]["status"] == "suspected"
    assert report["affected_modules"] == [{"path": "app/views.py", "imports_changed": ["app.auth"]}]
    assert (report["base_ref"], report["head_ref"]) == ("main", "feature/change-7")
    assert (report["base_sha"], report["head_sha"]) == (BASE[:12], HEAD[:12])
    assert report["repository_path"] == "https://bitbucket.org/acme/ledger"
    assert "import_analysis_truncated" not in report["summary"]
    assert report["binding"] == {
        "provider": "bitbucket-cloud", "repository_id": "acme/ledger", "pull_request_id": "7",
        "base_commit": BASE, "head_commit": HEAD, "comparison": "merge-base", "stale": False, "stale_at": None,
        "stale_checked": True,
    }
    # Compared from the merge base, not from the tip of the target branch.
    assert f"{REPO}/merge-base/{TARGET}..{HEAD}" in fake.paths()
    assert f"{REPO}/diff/{HEAD}..{BASE}" in fake.paths()
    assert not any(TARGET in path and "merge-base" not in path for path in fake.paths())
    # Read-only, Bitbucket API only, credential only in the header.
    assert {request.method for request in fake.requests} == {"GET"}
    assert {request.url.host for request in fake.requests} == {"api.bitbucket.org"}
    assert all(TOKEN not in str(request.url) for request in fake.requests)
    assert TOKEN not in response.text

    assert scan_rows(tmp_path) == [(report["id"], "bitbucket-cloud", "acme/ledger", "7", BASE, HEAD, None)]
    # Stored-scan routes do not ask Bitbucket, so their marker is "last recorded".
    unchecked = {**report, "binding": {**report["binding"], "stale_checked": False}}
    assert client.get(f"/api/scans/{report['id']}").json() == unchecked
    assert client.get(f"/api/scans/{report['id']}/export").json() == unchecked
    assert client.get("/api/scans").json()[0]["binding"] == unchecked["binding"]
    assert client.get(PR_URL).json()["scans"] == [{
        "id": report["id"], "created_at": report["created_at"], "summary": report["summary"], "binding": report["binding"],
    }]


def test_binding_is_served_beside_the_report_and_never_enters_the_stored_report(make_client, tmp_path):
    client = make_client(bitbucket())
    report = client.post(f"{PR_URL}/scans").json()
    conn = sqlite3.connect(tmp_path / "scans.db")
    stored = json.loads(conn.execute("SELECT report_json FROM scans").fetchone()[0])
    conn.close()
    assert "binding" not in stored and "stale_checked" not in json.dumps(stored)
    assert stored == {key: value for key, value in report.items() if key != "binding"}


# -- Phase 3 task 1: the Claude review package of a pull request scan ---------

def review_package(client, scan_id):
    response = client.get(f"/api/scans/{scan_id}/ai/handoff", params={"acknowledge_source_sharing": "true"})
    assert response.status_code == 200, response.text
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    return {name: archive.read(name).decode() for name in archive.namelist()}


def test_pull_request_package_needs_an_acknowledgement_before_source_code_is_exported(make_client):
    client = make_client(bitbucket())
    report = client.post(f"{PR_URL}/scans").json()
    refused = client.get(f"/api/scans/{report['id']}/ai/handoff")
    assert refused.status_code == 428
    assert "acknowledge_source_sharing" in refused.json()["detail"]
    assert client.get(f"/api/scans/{report['id']}/ai/context").json()["acknowledgement_required"] is True
    assert set(review_package(client, report["id"])) == {
        "PACKAGE.json", "REVIEW_INSTRUCTIONS.md", "review-input.json", "response-template.json"}


def test_pull_request_package_carries_repository_pull_request_and_exact_commits_under_the_digest(make_client, tmp_path):
    client = make_client(bitbucket())
    report = client.post(f"{PR_URL}/scans").json()
    binding = report["binding"]
    identity = {key: binding[key] for key in (
        "provider", "repository_id", "pull_request_id", "base_commit", "head_commit", "comparison")}
    assert identity["pull_request_id"] == "7" and len(identity["head_commit"]) == 40 and len(identity["base_commit"]) == 40

    files = review_package(client, report["id"])
    payload = json.loads(files["review-input.json"])
    manifest = json.loads(files["PACKAGE.json"])
    assert payload["review_context"]["source"] == identity
    assert manifest["source"] == identity and manifest["scan_id"] == report["id"]
    assert manifest["package_format"] == "shipsafe.review-package.v2"
    assert manifest["context_digest"] == payload["context_digest"]
    assert identity["head_commit"] in files["REVIEW_INSTRUCTIONS.md"] and "acme/ledger" in files["REVIEW_INSTRUCTIONS.md"]
    # Stale state changes over time, so it is not part of the package or its digest.
    assert all("stale" not in text for name, text in files.items() if name != "REVIEW_INSTRUCTIONS.md")

    stored = {key: value for key, value in report.items() if key != "binding"}
    assert payload["context_digest"] == context_digest(stored, binding)
    assert payload["context_digest"] != context_digest(stored, {**binding, "head_commit": "f" * 40})
    assert payload["context_digest"] != context_digest(stored)  # the identity is covered by the digest
    assert client.get(f"/api/scans/{report['id']}/ai/context").json()["context_digest"] == payload["context_digest"]
    # A second export has a new package id and the same content digest.
    again = json.loads(review_package(client, report["id"])["PACKAGE.json"])
    assert again["package_id"] != manifest["package_id"] and again["context_digest"] == manifest["context_digest"]


def test_pull_request_review_round_trip_and_the_digest_survives_the_head_moving(make_client):
    fake = bitbucket()
    client = make_client(fake)
    report = client.post(f"{PR_URL}/scans").json()
    payload = json.loads(review_package(client, report["id"])["review-input.json"])
    review = {
        "schema_version": "shipsafe.ai-review.v1", "scan_id": report["id"], "context_digest": payload["context_digest"],
        "summary": "Synthetic fixture review of the mocked pull request; nothing was executed.",
        "recommendation": "manual_review", "findings": [], "test_ideas": [],
        "limitations": ["Synthetic JSON fixture, not produced by a Claude Code session."],
    }
    url = f"/api/scans/{report['id']}/ai/reviews"
    wrong = client.post(url, json={**review, "context_digest": context_digest(
        {key: value for key, value in report.items() if key != "binding"})})
    assert wrong.status_code == 409  # a digest that does not cover the pull request identity is refused
    saved = client.post(url, json=review)
    assert saved.status_code == 201, saved.text
    assert saved.json()["verification_status"] == "not_independently_verified"
    assert client.get(f"/api/scans/{report['id']}").json()["findings"] == report["findings"]


def test_local_scan_responses_carry_a_direct_binding_with_full_shas(make_client, no_bitbucket_env):
    client = make_client()
    report = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/docs-only"}).json()
    binding = report["binding"]
    assert (binding["provider"], binding["pull_request_id"], binding["comparison"], binding["stale"], binding["stale_checked"]) == (
        "local-git", None, "direct", False, False)
    assert len(binding["base_commit"]) == len(binding["head_commit"]) == 40
    assert binding["head_commit"].startswith(report["head_sha"])
    assert client.get("/api/scans").json()[0]["binding"] == binding


def test_expected_head_guard_refuses_a_scan_after_the_pull_request_moved(make_client, tmp_path):
    client = make_client(bitbucket())
    moved = client.post(f"{PR_URL}/scans", json={"head_commit": HEAD2})
    assert (moved.status_code, moved.json()["code"]) == (409, "head_changed")
    assert scan_rows(tmp_path) == []
    assert client.post(f"{PR_URL}/scans", json={"head_commit": HEAD}).status_code == 201
    assert client.post(f"{PR_URL}/scans", json={"head_commit": HEAD[:12]}).status_code == 422


# -- stale detection ---------------------------------------------------------

def test_scan_goes_stale_when_the_head_moves_and_fresh_again_if_it_returns(make_client, tmp_path):
    fake = bitbucket()
    client = make_client(fake)
    first = client.post(f"{PR_URL}/scans").json()
    assert client.get(PR_URL).json()["scans"][0]["binding"]["stale"] is False

    move_head(fake, HEAD2)
    assert client.get(f"/api/scans/{first['id']}").json()["binding"]["stale"] is False  # not checked yet: last recorded state
    detail = client.get(PR_URL).json()  # looking at the pull request is enough to notice
    assert detail["source_sha"] == HEAD2 and detail["stale_checked"] is True
    assert detail["scans"][0]["binding"]["stale"] is True and detail["scans"][0]["binding"]["stale_checked"] is True
    stale_at = detail["scans"][0]["binding"]["stale_at"]
    served = client.get(f"/api/scans/{first['id']}").json()
    assert served["binding"]["stale"] is True and served["binding"]["head_commit"] == HEAD
    assert served["binding"]["stale_checked"] is False  # recorded by the detail call above, not checked by this one
    assert {key: value for key, value in served.items() if key != "binding"} == {
        key: value for key, value in first.items() if key != "binding"}  # the report itself is untouched
    assert client.get("/api/scans").json()[0]["binding"]["stale"] is True

    second = client.post(f"{PR_URL}/scans").json()
    assert second["binding"]["head_commit"] == HEAD2 and second["binding"]["stale"] is False
    scans = client.get(PR_URL).json()["scans"]
    assert [(scan["id"], scan["binding"]["stale"]) for scan in scans] == [(second["id"], False), (first["id"], True)]
    assert scans[1]["binding"]["stale_at"] == stale_at  # first observation time is kept

    move_head(fake, HEAD)  # force-push back to the commit that was first scanned
    scans = client.get(PR_URL).json()["scans"]
    assert [(scan["id"], scan["binding"]["stale"]) for scan in scans] == [(second["id"], True), (first["id"], False)]


def test_scanning_marks_earlier_scans_stale_without_a_separate_lookup(make_client, tmp_path):
    fake = bitbucket()
    client = make_client(fake)
    first = client.post(f"{PR_URL}/scans").json()
    move_head(fake, HEAD2)
    second = client.post(f"{PR_URL}/scans").json()
    rows = {row[0]: row[6] for row in scan_rows(tmp_path)}
    assert rows[first["id"]] is not None and rows[second["id"]] is None


def test_pull_request_list_refreshes_stale_markers_for_scanned_pull_requests_only(make_client):
    fake = bitbucket()
    client = make_client(fake)
    first = client.post(f"{PR_URL}/scans").json()
    move_head(fake, HEAD2)
    fake.requests.clear()

    items = {item["id"]: item for item in client.get(f"{ROUTES}/ledger/pull-requests").json()["pull_requests"]}
    assert items["7"]["stale_checked"] is True and items["7"]["source_sha"] == HEAD2 and items["7"]["scan_count"] == 1
    assert items["7"]["latest_scan"]["id"] == first["id"] and items["7"]["latest_scan"]["binding"]["stale"] is True
    assert items["7"]["latest_scan"]["binding"]["stale_checked"] is True
    assert items["8"]["stale_checked"] is False and items["8"]["latest_scan"] is None
    assert f"{REPO}/pullrequests/7" in fake.paths() and f"{REPO}/pullrequests/8" not in fake.paths()


def test_pull_request_list_stops_refreshing_at_its_lookup_budget(make_client, monkeypatch):
    fake = bitbucket(**{f"{REPO}/pullrequests/8": js(pull_request(8))})
    client = make_client(fake)
    assert client.post(f"{PR_URL}/scans").status_code == 201
    assert client.post(f"{ROUTES}/ledger/pull-requests/8/scans").status_code == 201
    monkeypatch.setattr(main_module, "STALE_CHECKS_PER_LIST", 1)
    items = client.get(f"{ROUTES}/ledger/pull-requests").json()["pull_requests"]
    assert [(item["id"], item["stale_checked"], item["scan_count"]) for item in items] == [("7", True, 1), ("8", False, 1)]
    # Beyond the budget: no full SHA, and the scan's marker is explicitly "last recorded".
    assert items[1]["source_sha"] is None and items[1]["latest_scan"]["binding"]["stale_checked"] is False


# -- refusals ----------------------------------------------------------------

def test_pull_request_whose_head_cannot_be_read_is_not_scannable(make_client, tmp_path):
    fork = pull_request(7, head="e" * 40)  # no /commit/eeee... route: not readable through the approved repository
    client = make_client(bitbucket(**{f"{REPO}/pullrequests/7": js(fork)}))
    detail = client.get(PR_URL).json()
    assert detail["source_sha"] is None and detail["target_sha"] == TARGET
    assert (detail["scannable"], detail["not_scannable_code"]) == (False, "head_commit_unavailable")
    assert detail["stale_checked"] is False
    refused = client.post(f"{PR_URL}/scans")
    assert (refused.status_code, refused.json()["code"]) == (409, "head_commit_unavailable")
    assert "fork" in refused.json()["detail"]
    assert scan_rows(tmp_path) == []


def test_pull_request_whose_target_cannot_be_read_is_not_scannable(make_client, tmp_path):
    gone = pull_request(7, target="f" * 40)
    client = make_client(bitbucket(**{f"{REPO}/pullrequests/7": js(gone)}))
    refused = client.post(f"{PR_URL}/scans")
    assert (refused.status_code, refused.json()["code"]) == (409, "base_commit_unavailable")
    assert scan_rows(tmp_path) == []


@pytest.mark.parametrize("method,url,override,status,code", [
    ("get", f"{ROUTES}/secret/pull-requests", {}, 403, "repository_not_allowed"),
    ("post", f"{ROUTES}/secret/pull-requests/7/scans", {}, 403, "repository_not_allowed"),
    ("get", f"{ROUTES}/..%2Fx/pull-requests", {}, 404, None),
    ("get", f"{ROUTES}/ledger/pull-requests", {REPO: js({"type": "error"}, 404)}, 404, "repository_not_found"),
    ("get", f"{ROUTES}/ledger/pull-requests/99", {}, 404, "pull_request_not_found"),
    ("get", f"{ROUTES}/ledger/pull-requests/abc", {}, 400, "invalid_request"),
    ("post", f"{PR_URL}/scans", {f"{REPO}/merge-base/{TARGET}..{HEAD}": js({"type": "error"}, 404)}, 404, "commit_not_found"),
    ("post", f"{PR_URL}/scans", {f"{REPO}/diff/{HEAD}..{BASE}": httpx.Response(555)}, 422, "diff_too_large"),
    ("get", ROUTES, {"/repositories/acme": js({"type": "error"}, 401)}, 502, "bitbucket_auth_failed"),
    ("get", PR_URL, {f"{REPO}/pullrequests/7": js({"type": "error"}, 403)}, 502, "bitbucket_auth_failed"),
    ("get", ROUTES, {"/repositories/acme": js({}, 429)}, 503, "bitbucket_unavailable"),
    ("post", f"{PR_URL}/scans", {f"{REPO}/diffstat/{HEAD}..{BASE}": httpx.Response(503)}, 503, "bitbucket_unavailable"),
    ("get", ROUTES, {"/repositories/acme": js({"values": "nope"})}, 502, "bitbucket_error"),
    ("post", f"{PR_URL}/scans", {f"{REPO}/merge-base/{TARGET}..{HEAD}": js({"hash": "short"})}, 502, "bitbucket_error"),
    ("get", PR_URL, {f"{REPO}/pullrequests/7": js({}, 500)}, 502, "bitbucket_error"),
])
def test_bitbucket_failures_map_to_http_statuses_without_leaking_the_token(make_client, tmp_path, method, url, override, status, code):
    client = make_client(bitbucket(**override))
    response = getattr(client, method)(url)
    assert response.status_code == status
    if code:
        assert response.json()["code"] == code
        assert isinstance(response.json()["detail"], str) and response.json()["detail"]
    assert TOKEN not in response.text
    assert scan_rows(tmp_path) == []  # a failed scan stores nothing


# -- bounded import analysis -------------------------------------------------

def test_import_analysis_is_bounded_and_the_report_says_when_it_was_cut(make_client, monkeypatch):
    tree = ("app/auth.py", "README.md", *(f"app/mod{n}.py" for n in range(5)))
    fake = bitbucket(**scan_routes(tree=tree))
    client = make_client(fake)
    monkeypatch.setattr(main_module, "BITBUCKET_IMPORT_READS", 2)

    report = client.post(f"{PR_URL}/scans").json()

    assert report["summary"]["import_analysis_truncated"] is True
    assert report["summary"]["import_files_skipped"] == 3
    assert [module["path"] for module in report["affected_modules"]] == ["app/mod0.py", "app/mod1.py"]
    assert [path for path in fake.paths() if "/app/mod" in path] == [f"{REPO}/src/{HEAD}/app/mod0.py", f"{REPO}/src/{HEAD}/app/mod1.py"]
    limitations = json.loads(review_package(client, report["id"])["review-input.json"])["review_context"]["limitations"]
    assert any(item.startswith("INCOMPLETE: affected_modules") and "3 Python files" in item for item in limitations)


def test_default_import_bound_is_200_files():
    assert main_module.BITBUCKET_IMPORT_READS == 200


# -- provider: merge base ----------------------------------------------------

def test_merge_base_returns_the_full_sha_of_the_common_ancestor():
    fake = FakeBitbucket({f"{REPO}/merge-base/{TARGET}..{HEAD}": js({"hash": BASE})})
    assert fake.provider().merge_base(LEDGER, TARGET, HEAD) == BASE
    assert fake.requests[0].method == "GET"


def test_merge_base_failures_are_reported_precisely():
    with pytest.raises(RefNotFound):
        FakeBitbucket().provider().merge_base(LEDGER, TARGET, HEAD)
    with pytest.raises(ProviderError):
        FakeBitbucket({f"{REPO}/merge-base/{TARGET}..{HEAD}": js({"hash": BASE[:12]})}).provider().merge_base(LEDGER, TARGET, HEAD)
    fake = FakeBitbucket()
    with pytest.raises(ScanError):
        fake.provider().merge_base(LEDGER, "main", HEAD)
    assert fake.requests == []


def test_scans_of_a_pull_request_whose_head_became_unreadable_are_reported_as_unchecked(make_client):
    """A fork or a deleted source branch: stored markers stay as they were and
    every response says they were not checked."""
    fake = bitbucket()
    client = make_client(fake)
    first = client.post(f"{PR_URL}/scans").json()
    fake.routes[f"{REPO}/pullrequests/7"] = js(pull_request(7, head="e" * 40))  # head no longer readable
    detail = client.get(PR_URL).json()
    assert detail["stale_checked"] is False and detail["source_sha"] is None
    assert detail["scans"][0]["id"] == first["id"]
    assert (detail["scans"][0]["binding"]["stale"], detail["scans"][0]["binding"]["stale_checked"]) == (False, False)
    items = client.get(f"{ROUTES}/ledger/pull-requests").json()["pull_requests"]
    assert (items[0]["stale_checked"], items[0]["latest_scan"]["binding"]["stale_checked"]) == (False, False)


def _pinned_summary_keys():
    from pathlib import Path
    example = json.loads((Path(__file__).resolve().parents[2] / "docs" / "example-scan-report.json").read_text())
    return set(example["summary"])


@pytest.mark.parametrize("python_files,limit,cut", [
    (2, 200, False),   # far below the limit
    (3, 3, False),     # exactly at the limit: nothing skipped, so nothing added
    (4, 3, True),      # one file over the limit
])
def test_report_summary_keeps_the_pinned_shape_unless_import_analysis_was_actually_cut(make_client, monkeypatch, python_files, limit, cut):
    tree = ("app/auth.py", "README.md", *(f"app/mod{n}.py" for n in range(python_files)))
    client = make_client(bitbucket(**scan_routes(tree=tree)))
    monkeypatch.setattr(main_module, "BITBUCKET_IMPORT_READS", limit)
    summary = client.post(f"{PR_URL}/scans").json()["summary"]
    extra = {"import_analysis_truncated", "import_files_skipped"}
    if cut:
        assert set(summary) == _pinned_summary_keys() | extra
        assert summary["import_files_skipped"] == python_files - limit
    else:
        assert set(summary) == _pinned_summary_keys()


def test_local_scans_never_gain_the_import_truncation_keys(make_client, no_bitbucket_env):
    client = make_client()
    for head in ("feature/release-candidate", "feature/docs-only", "feature/safe-cleanup"):
        summary = client.post("/api/scans", json={"base_ref": "main", "head_ref": head}).json()["summary"]
        assert set(summary) == _pinned_summary_keys()


def test_published_example_responses_match_the_current_contract(make_client):
    """docs/example-bitbucket-responses.json is what the frontend builds
    against; fail when a response gains or loses a key without it."""
    from pathlib import Path
    example = json.loads((Path(__file__).resolve().parents[2] / "docs" / "example-bitbucket-responses.json").read_text())
    fake = bitbucket()
    client = make_client(fake)
    scan = client.post(f"{PR_URL}/scans", json={"head_commit": HEAD}).json()
    move_head(fake, HEAD2)
    listed = client.get(f"{ROUTES}/ledger/pull-requests").json()
    detail = client.get(PR_URL).json()

    def keys(value):
        return set(value) if isinstance(value, dict) else None

    documented_detail = example["GET /api/bitbucket/repositories/ledger/pull-requests/7 (after the head moved)"]
    documented_list = example["GET /api/bitbucket/repositories/ledger/pull-requests (after the head moved)"]
    documented_scan = next(v for k, v in example.items() if k.startswith("POST /api/bitbucket/"))
    assert keys(detail) == keys(documented_detail)
    assert keys(detail["scans"][0]) == keys(documented_detail["scans"][0])
    assert keys(detail["scans"][0]["binding"]) == keys(documented_detail["scans"][0]["binding"]) == keys(scan["binding"])
    assert keys(listed) == keys(documented_list)
    assert keys(listed["pull_requests"][0]) == keys(documented_list["pull_requests"][0])
    assert set(documented_scan["report_keys"]) == set(scan) - {"binding"}
    assert keys(client.get("/api/bitbucket/status").json()) == keys(example["GET /api/bitbucket/status"])
    assert keys(client.get(ROUTES).json()[0]) == keys(example["GET /api/bitbucket/repositories"][0])
    assert keys(client.get("/api/scans").json()[0]) == keys(example["GET /api/scans (history item, after the head moved, before any check)"])


# -- pull request list: truncated flag ---------------------------------------

def test_pull_request_list_is_not_truncated_when_everything_fits(make_client):
    body = make_client(bitbucket()).get(f"{ROUTES}/ledger/pull-requests").json()
    assert body["truncated"] is False
    assert set(body) == {"repository", "state", "pull_requests", "truncated"}  # existing fields are still there
    assert [item["id"] for item in body["pull_requests"]] == ["7", "8"]


def test_pull_request_list_is_not_truncated_at_exactly_the_limit(make_client, monkeypatch):
    from app.providers import bitbucket as provider_module
    monkeypatch.setattr(provider_module, "MAX_PULL_REQUESTS", 2)
    body = make_client(bitbucket()).get(f"{ROUTES}/ledger/pull-requests").json()
    assert body["truncated"] is False and len(body["pull_requests"]) == 2


def test_pull_request_list_is_truncated_only_when_the_limit_leaves_items_out(make_client, monkeypatch):
    from app.providers import bitbucket as provider_module
    monkeypatch.setattr(provider_module, "MAX_PULL_REQUESTS", 2)
    three = js({"values": [pull_request(7), pull_request(8), pull_request(9)], "size": 3})
    body = make_client(bitbucket(**{f"{REPO}/pullrequests": three})).get(f"{ROUTES}/ledger/pull-requests").json()
    assert body["truncated"] is True
    assert [item["id"] for item in body["pull_requests"]] == ["7", "8"]  # the first 200 in Bitbucket's order, here 2
    # Every item keeps the fields it had before the flag existed.
    assert {"id", "title", "state", "source_ref", "target_ref", "scan_count", "latest_scan", "stale_checked"} <= set(body["pull_requests"][0])


def test_pull_request_list_follows_pages_and_reports_a_complete_result(make_client):
    path = f"{REPO}/pullrequests"
    first = js({"values": [pull_request(7)], "size": 2, "next": f"https://api.bitbucket.org/2.0{path}?page=2"})
    fake = bitbucket()
    pages = iter([first, js({"values": [pull_request(8)], "size": 2})])
    fake.routes[path] = lambda request: next(pages)
    body = make_client(fake).get(f"{ROUTES}/ledger/pull-requests").json()
    assert ([item["id"] for item in body["pull_requests"]], body["truncated"]) == (["7", "8"], False)
