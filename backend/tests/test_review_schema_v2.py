"""Phase 3 task 2: review schema v2 (finding id, suspected status, suggested
validation, optional proposed patch, missing context, echoed source) and the
instructions given to Claude. Synthetic JSON fixtures only: no Claude Code
session produced these reviews."""
import copy
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.ai_handoff import REVIEW_SCHEMA_V2, SCHEMA_VERSION
from app.main import create_app


@pytest.fixture()
def demo(tmp_path):
    repo = tmp_path / "demo"
    app = create_app(demo_root=repo, db_file=tmp_path / "data" / "scans.db", allowed_root=repo)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/release-candidate"})
        assert response.status_code == 201, response.text
        report = response.json()
        archive = zipfile.ZipFile(io.BytesIO(client.get(f"/api/scans/{report['id']}/ai/handoff").content))
        files = {name: archive.read(name).decode() for name in archive.namelist()}
        yield client, report, files


def filled(template: dict, report: dict) -> dict:
    """The response template with every placeholder replaced, as a reviewer would."""
    review = copy.deepcopy(template)
    review["summary"] = "Synthetic fixture: an ownership check appears to be removed; nothing was executed."
    review["findings"][0].update({
        "title": "Ownership guard appears removed", "file": report["files"][0]["path"],
        "evidence": "A permission-related guard is absent from the changed code.",
        "rationale": "The diff appears to remove an ownership check; runtime behaviour was not tested.",
        "recommendation": "Restore the check or show where it moved.",
        "suggested_validation": "Request another user's invoice as a second synthetic user; expect a refusal.",
        "proposed_patch": "--- a/x.py\n+++ b/x.py\n@@\n+    require_owner(user, invoice)",
        "related_static_finding_ids": [report["findings"][0]["id"]],
    })
    review["test_ideas"][0].update({
        "title": "Reject another user's read", "scenario": "Second synthetic user reads the first user's invoice.",
        "expected_behavior": "The API refuses and reveals nothing.",
    })
    review["missing_context"] = ["Callers of the changed function were not included."]
    return review


def post(client, report, review):
    return client.post(f"/api/scans/{report['id']}/ai/reviews", json=review)


def test_the_template_asks_for_v2_and_already_carries_the_binding(demo):
    _, report, files = demo
    template, payload = json.loads(files["response-template.json"]), json.loads(files["review-input.json"])
    assert template["schema_version"] == REVIEW_SCHEMA_V2 == "shipsafe.ai-review.v2"
    assert template["scan_id"] == report["id"] and template["context_digest"] == payload["context_digest"]
    binding = report["binding"]
    assert template["reviewed_source"] == {
        "provider": "local-git", "repository_id": binding["repository_id"], "pull_request_id": None,
        "head_commit": binding["head_commit"],
    }
    finding = template["findings"][0]
    assert finding["status"] == "suspected" and finding["id"] == "F1" and finding["proposed_patch"] is None
    assert {"suggested_validation", "missing_context"} <= set(finding) | set(template)


def test_instructions_cover_the_review_areas_and_forbid_execution_claims(demo):
    _, _, files = demo
    text = files["REVIEW_INSTRUCTIONS.md"]
    for phrase in ("authorization", "API compatibility", "money and data-integrity", "input validation",
                   "exception handling", "affected_modules", "has no test", "suggested_validation",
                   "missing_context", "proposed_patch", "never applies it", "untrusted data"):
        assert phrase in text, phrase
    assert "Never state that you ran commands, tests or the code" in text
    assert 'There is no "verified" status' in text


def test_v2_round_trip_keeps_the_new_fields_marks_them_unverified_and_leaves_the_scan_alone(demo):
    client, report, files = demo
    review = filled(json.loads(files["response-template.json"]), report)
    saved = post(client, report, review)
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert body["schema_version"] == REVIEW_SCHEMA_V2
    assert body["verification_status"] == "not_independently_verified" and body["tests_executed"] is False
    assert body["reviewed_source"] == review["reviewed_source"] and body["missing_context"] == review["missing_context"]
    assert body["source"] == "user_imported_json_unverified_provenance"  # the provenance marker is not overwritten
    finding = body["findings"][0]
    assert (finding["id"], finding["status"]) == ("F1", "suspected")
    assert finding["suggested_validation"] == review["findings"][0]["suggested_validation"]
    assert finding["proposed_patch"] == review["findings"][0]["proposed_patch"]  # stored as text, never applied
    assert client.get(f"/api/scans/{report['id']}/ai/reviews/latest").json() == body
    assert client.get(f"/api/scans/{report['id']}").json() == report


def test_v1_reviews_are_still_accepted(demo):
    client, report, files = demo
    digest = json.loads(files["review-input.json"])["context_digest"]
    v1 = {
        "schema_version": SCHEMA_VERSION, "scan_id": report["id"], "context_digest": digest,
        "summary": "Synthetic v1 fixture review; nothing was executed.", "recommendation": "manual_review",
        "findings": [], "test_ideas": [], "limitations": ["Synthetic JSON fixture."],
    }
    saved = post(client, report, v1)
    assert saved.status_code == 201, saved.text
    assert saved.json()["schema_version"] == SCHEMA_VERSION and "missing_context" not in saved.json()
    # v2-only fields are not smuggled into a v1 review.
    assert post(client, report, {**v1, "missing_context": []}).status_code == 422


def change(review, path, value):
    target = review
    for key in path[:-1]:
        target = target[key]
    if value is ...:
        target.pop(path[-1])
    else:
        target[path[-1]] = value


@pytest.mark.parametrize("path,value,status", [
    (("findings", 0, "status"), "verified", 422),          # no way to claim verification
    (("findings", 0, "status"), "confirmed", 422),
    (("findings", 0, "verified"), True, 422),
    (("findings", 0, "test_result"), "passed", 422),
    (("tests_executed",), True, 422),
    (("commands_run",), ["pytest -q"], 422),
    (("verification_status",), "verified", 422),
    (("findings", 0, "id"), ..., 422),
    (("findings", 0, "id"), "has spaces", 422),
    (("findings", 0, "suggested_validation"), ..., 422),
    (("findings", 0, "proposed_patch"), "x" * 8001, 422),
    (("reviewed_source",), ..., 422),
    (("source",), "claude_code_verified", 422),             # the provenance marker cannot be supplied
    (("reviewed_source", "extra"), "x", 422),
    (("missing_context",), "not a list", 422),
    (("schema_version",), "shipsafe.ai-review.v3", 422),
    (("reviewed_source", "head_commit"), "f" * 40, 409),            # made for another commit
    (("reviewed_source", "repository_id"), "someone/else", 409),
    (("reviewed_source", "pull_request_id"), "7", 409),
    (("reviewed_source", "provider"), "bitbucket-cloud", 409),
    (("missing_context",), ["x" * 701], 409),
])
def test_v2_rejects_fabricated_status_malformed_fields_and_a_wrong_source(demo, path, value, status):
    client, report, files = demo
    review = filled(json.loads(files["response-template.json"]), report)
    change(review, path, value)
    result = post(client, report, review)
    assert result.status_code == status, result.text
    assert client.get(f"/api/scans/{report['id']}/ai/reviews").json() == []


def test_duplicate_finding_ids_are_rejected(demo):
    client, report, files = demo
    review = filled(json.loads(files["response-template.json"]), report)
    review["findings"].append(copy.deepcopy(review["findings"][0]))
    result = post(client, report, review)
    assert result.status_code == 409 and "Duplicate review finding IDs: F1" in result.json()["detail"]
    review["findings"][1]["id"] = "F2"
    assert post(client, report, review).status_code == 201
