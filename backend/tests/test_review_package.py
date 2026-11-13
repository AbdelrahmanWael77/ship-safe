"""Phase 3 task 1: the Claude review package — identity, digest, redaction,
size limit and the source-sharing acknowledgement. No Claude account, no
network; the demo repository is synthetic."""
import copy
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import ai_handoff
from app.ai_handoff import canonical_json, context_digest, handoff_payload, redact, review_context
from app.main import create_app


@pytest.fixture()
def demo(tmp_path):
    repo = tmp_path / "demo"
    app = create_app(demo_root=repo, db_file=tmp_path / "data" / "scans.db", allowed_root=tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/release-candidate"})
        assert response.status_code == 201, response.text
        yield client, response.json(), tmp_path


def package(client, scan_id, **params):
    response = client.get(f"/api/scans/{scan_id}/ai/handoff", params=params)
    assert response.status_code == 200, response.text
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    return {name: archive.read(name).decode() for name in archive.namelist()}


def stored(report):
    return {key: value for key, value in report.items() if key != "binding"}


# -- identity and digest ------------------------------------------------------

def test_demo_package_needs_no_acknowledgement_and_carries_the_exact_commits(demo):
    client, report, _ = demo
    assert client.get(f"/api/scans/{report['id']}/ai/context").json()["acknowledgement_required"] is False
    files = package(client, report["id"])
    payload, manifest = json.loads(files["review-input.json"]), json.loads(files["PACKAGE.json"])
    source = payload["review_context"]["source"]
    assert source == {
        "provider": "local-git", "repository_id": report["binding"]["repository_id"], "pull_request_id": None,
        "base_commit": report["binding"]["base_commit"], "head_commit": report["binding"]["head_commit"],
        "comparison": "direct",
    }
    assert len(source["head_commit"]) == 40 and source["head_commit"].startswith(report["head_sha"])
    assert manifest["source"] == source and manifest["contains_source_code"] is True
    assert manifest["incomplete"] is False and manifest["patches_omitted"] == 0
    assert payload["context_digest"] == context_digest(stored(report), report["binding"])
    assert json.loads(files["response-template.json"])["context_digest"] == payload["context_digest"]
    assert "Before you share this package" in files["REVIEW_INSTRUCTIONS.md"]
    assert source["head_commit"] in files["REVIEW_INSTRUCTIONS.md"]


def test_a_local_repository_other_than_the_demo_requires_the_acknowledgement(demo):
    client, report, tmp_path = demo
    import shutil
    other = tmp_path / "other"
    shutil.copytree(tmp_path / "demo", other)
    scan = client.post("/api/scans", json={"repository_path": str(other), "base_ref": "main", "head_ref": "feature/release-candidate"})
    assert scan.status_code == 201, scan.text
    scan_id = scan.json()["id"]
    assert client.get(f"/api/scans/{scan_id}/ai/context").json()["acknowledgement_required"] is True
    assert client.get(f"/api/scans/{scan_id}/ai/handoff").status_code == 428
    assert client.get(f"/api/scans/{scan_id}/ai/handoff", params={"acknowledge_source_sharing": "false"}).status_code == 428
    assert "review-input.json" in package(client, scan_id, acknowledge_source_sharing="true")


def test_the_digest_is_stable_and_covers_identity_and_content(demo):
    _, report, _ = demo
    body, binding = stored(report), report["binding"]
    digest = context_digest(body, binding)
    assert digest == context_digest(copy.deepcopy(body), dict(binding))
    assert digest != context_digest(body, {**binding, "base_commit": "0" * 40})
    assert digest != context_digest(body, {**binding, "repository_id": "someone/else"})
    assert digest == context_digest(body, {**binding, "stale": True, "stale_at": "2026-01-01T00:00:00+00:00", "stale_checked": True})
    changed = copy.deepcopy(body)
    changed["files"][0]["diff"] += "\n+extra line"
    assert digest != context_digest(changed, binding)


# -- redaction (best effort) --------------------------------------------------

@pytest.mark.parametrize("text", [
    'API_KEY = "sk_live_51Hxxxxxxxxxxxxxxxx"',
    "db_password: 'correct horse battery'",
    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
    "AKIAIOSFODNN7EXAMPLE",
    "ghp_abcdefghijklmnopqrstuvwxyzABCDEFGHIJ",
    "postgres://app:s3cretpass@db.internal:5432/ledger",
    "-----BEGIN RSA PRIVATE KEY-----\nMIIEow...\n-----END RSA PRIVATE KEY-----",
])
def test_secret_looking_values_are_replaced(text):
    cleaned, count = redact(f"+    {text}\n context line")
    assert count >= 1 and "[REDACTED:" in cleaned
    for secret in ("sk_live_51H", "correct horse", "abcdefghijklmnopqrstuvwxyz012345", "AKIAIOSFODNN7EXAMPLE",
                   "ghp_abcdefghij", "s3cretpass", "MIIEow"):
        assert secret not in cleaned
    assert "context line" in cleaned


@pytest.mark.parametrize("text", [
    "def check_password(user, password):", "token = request.headers.get('X-Token')", "return round(amount, 2)",
    'label = "Password"', "https://example.com/path",
])
def test_ordinary_code_is_left_alone(text):
    assert redact(text) == (text, 0)


def test_package_redacts_patches_and_evidence_says_so_and_keeps_the_stored_report(demo):
    client, report, _ = demo
    body = stored(report)
    secret = 'SERVICE_TOKEN = "tok_live_9f8e7d6c5b4a3f2e1d0c"'
    leaky = copy.deepcopy(body)
    leaky["files"][0]["diff"] += f"\n+{secret}"
    leaky["findings"][0]["evidence"] = secret
    context = review_context(leaky, report["binding"])
    text = json.dumps(context)
    assert "tok_live_9f8e7d6c5b4a3f2e1d0c" not in text and text.count("[REDACTED:assigned-secret]") == 2
    assert any("2 secret-looking values were replaced" in item and "best-effort" in item for item in context["limitations"])
    assert secret in leaky["files"][0]["diff"]  # the input report is not modified
    # The real demo scan is exported unchanged when nothing looks like a secret, or says how much was replaced.
    exported = json.loads(package(client, report["id"])["review-input.json"])["review_context"]
    replaced = json.dumps(exported).count("[REDACTED:")
    assert (replaced == 0) == (exported["files"] == body["files"] and exported["static_findings"] == body["findings"])
    assert client.get(f"/api/scans/{report['id']}").json() == report


# -- size limit ---------------------------------------------------------------

def test_an_oversized_package_drops_the_largest_patches_and_says_so(demo, monkeypatch):
    _, report, _ = demo
    body = stored(report)
    assert len(body["files"]) >= 2
    full = handoff_payload(body, report["binding"])
    limit = len(canonical_json(full["review_context"])) - 1
    monkeypatch.setattr(ai_handoff, "MAX_PACKAGE_BYTES", limit)

    cut = handoff_payload(body, report["binding"])
    files = cut["review_context"]["files"]
    omitted = [item for item in files if item.get("diff_omitted_from_package")]
    largest = max(body["files"], key=lambda item: len(item["diff"]))
    assert omitted and omitted[0]["path"] == largest["path"] and omitted[0]["diff"] == ""
    assert [item["path"] for item in files] == [item["path"] for item in body["files"]]  # the file is still listed
    assert any(item.startswith("INCOMPLETE: the package size limit") for item in cut["review_context"]["limitations"])
    assert ai_handoff.package_manifest(cut)["incomplete"] is True
    assert ai_handoff.package_manifest(cut)["patches_omitted"] == len(omitted)
    assert cut["context_digest"] != full["context_digest"]
    assert cut == handoff_payload(body, report["binding"])  # deterministic


def test_import_still_binds_to_the_exported_digest(demo):
    client, report, _ = demo
    digest = json.loads(package(client, report["id"])["review-input.json"])["context_digest"]
    review = {
        "schema_version": "shipsafe.ai-review.v1", "scan_id": report["id"], "context_digest": digest,
        "summary": "Synthetic fixture review of the demo scan; nothing was executed.", "recommendation": "manual_review",
        "findings": [], "test_ideas": [], "limitations": ["Synthetic JSON fixture, not a Claude Code session."],
    }
    url = f"/api/scans/{report['id']}/ai/reviews"
    assert client.post(url, json={**review, "context_digest": context_digest(stored(report))}).status_code == 409
    assert client.post(url, json=review).status_code == 201
