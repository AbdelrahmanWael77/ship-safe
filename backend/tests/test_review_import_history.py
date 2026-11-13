"""Phase 3 task 3: strict import and history for a local scan — duplicate
imports, preserved history and timestamps, untouched static results, and the
scan binding served with every review. Synthetic JSON fixtures only.
(Pull request cases, including stale-on-head-move: test_bitbucket_api.py.)"""
import io
import json
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.ai_handoff import MAX_IMPORT_BYTES, review_content_digest
from app.main import create_app


@pytest.fixture()
def demo(tmp_path):
    repo = tmp_path / "demo"
    db_file = tmp_path / "data" / "scans.db"
    app = create_app(demo_root=repo, db_file=db_file, allowed_root=repo)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        report = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/release-candidate"}).json()
        archive = zipfile.ZipFile(io.BytesIO(client.get(f"/api/scans/{report['id']}/ai/handoff").content))
        template = json.loads(archive.read("response-template.json"))
        review = {**template, "summary": "Synthetic fixture review of the demo scan; nothing was executed.",
                  "findings": [], "test_ideas": [], "missing_context": []}
        yield client, report, review, db_file


def url(report):
    return f"/api/scans/{report['id']}/ai/reviews"


def test_the_same_review_cannot_be_imported_twice_but_a_changed_one_can(demo):
    client, report, review, _ = demo
    first = client.post(url(report), json=review)
    assert first.status_code == 201, first.text
    again = client.post(url(report), json=review)
    assert again.status_code == 409 and "already imported" in again.json()["detail"]
    # Key order and whitespace do not make it a different review.
    reordered = json.dumps(dict(reversed(list(review.items()))), indent=4)
    assert client.post(url(report), content=reordered, headers={"Content-Type": "application/json"}).status_code == 409
    assert len(client.get(url(report)).json()) == 1

    changed = {**review, "summary": review["summary"] + " Second pass."}
    assert client.post(url(report), json=changed).status_code == 201
    assert client.post(url(report), json=changed).status_code == 409
    assert len(client.get(url(report)).json()) == 2


def test_content_digest_ignores_what_shipsafe_adds_on_import(demo):
    client, report, review, _ = demo
    saved = client.post(url(report), json=review).json()
    stored = {key: value for key, value in saved.items() if key not in ("scan_binding",)}
    assert review_content_digest(stored) == review_content_digest({**stored, "id": "other", "imported_at": "2000-01-01"})
    assert review_content_digest(stored) != review_content_digest({**stored, "summary": "A different summary text."})


def test_history_keeps_every_import_with_its_timestamp_and_never_touches_the_scan(demo):
    client, report, review, db_file = demo
    saved = [client.post(url(report), json={**review, "summary": f"{review['summary']} Pass {n}."}).json() for n in range(3)]
    listed = client.get(url(report)).json()
    assert [item["id"] for item in listed] == [item["id"] for item in reversed(saved)]  # newest first
    assert [item["imported_at"] for item in listed] == [item["imported_at"] for item in reversed(saved)]
    assert listed == sorted(listed, key=lambda item: item["imported_at"], reverse=True)
    assert all(item["verification_status"] == "not_independently_verified" and item["tests_executed"] is False for item in listed)
    assert client.get(url(report) + "/latest").json()["id"] == saved[-1]["id"]

    # The static scan is exactly what it was, in the API and in the database row.
    assert client.get(f"/api/scans/{report['id']}").json() == report
    conn = sqlite3.connect(db_file)
    stored_report = json.loads(conn.execute("SELECT report_json FROM scans WHERE id = ?", (report["id"],)).fetchone()[0])
    stored_reviews = [json.loads(row[0]) for row in conn.execute("SELECT review_json FROM ai_reviews")]
    conn.close()
    assert stored_report == {key: value for key, value in report.items() if key != "binding"}
    assert stored_report["summary"]["test_status"] == "not_run"
    # Stale state and binding are served beside a review, never stored in it.
    assert all("scan_binding" not in item and "stale" not in json.dumps(item) for item in stored_reviews)


def test_every_served_review_names_its_scan_and_that_scans_binding(demo):
    client, report, review, _ = demo
    posted = client.post(url(report), json=review).json()
    expected = {**report["binding"], "stale_checked": False}
    for served in (posted, client.get(url(report)).json()[0], client.get(url(report) + "/latest").json()):
        assert served["scan_id"] == report["id"]
        assert served["scan_binding"] == expected
        assert served["scan_binding"]["stale"] is False and served["scan_binding"]["pull_request_id"] is None
    history = client.get(url(report) + "/history").json()
    assert [item["id"] for item in history] == [posted["id"]] and history[0]["current_scan"] is True


def test_a_local_scans_history_does_not_include_reviews_of_other_scans(demo):
    client, report, review, _ = demo
    client.post(url(report), json=review)
    other = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/release-candidate"}).json()
    assert other["id"] != report["id"]
    assert client.get(url(other) + "/history").json() == []
    assert client.post(url(other), json=review).status_code == 409  # a review of one scan is not valid for another
    assert len(client.get(url(report) + "/history").json()) == 1


@pytest.mark.parametrize("name,mutate,status", [
    ("wrong scan", lambda r: r.update(scan_id="12345678-1111-2222-3333-444444444444"), 409),
    ("bad digest", lambda r: r.update(context_digest="0" * 64), 409),
    ("wrong sha", lambda r: r["reviewed_source"].update(head_commit="e" * 40), 409),
    ("missing field", lambda r: r.pop("limitations"), 422),
    ("extra field", lambda r: r.update(approved=True), 422),
    ("unknown path", lambda r: r.update(test_ideas=[{"title": "Path check", "scenario": "A scenario long enough.",
                                                    "expected_behavior": "Refused.", "file": "../../etc/passwd"}]), 409),
    ("wrong type", lambda r: r.update(findings="none"), 422),
])
def test_rejected_imports_leave_no_trace(demo, name, mutate, status):
    client, report, review, _ = demo
    body = json.loads(json.dumps(review))
    mutate(body)
    result = client.post(url(report), json=body)
    assert result.status_code == status, f"{name}: {result.text}"
    assert client.get(url(report)).json() == [] and client.get(url(report) + "/history").json() == []


def test_oversized_and_non_json_imports_are_rejected(demo):
    client, report, review, _ = demo
    headers = {"Content-Type": "application/json"}
    big = json.dumps({**review, "summary": "x" * (MAX_IMPORT_BYTES + 10)})
    assert client.post(url(report), content=big, headers=headers).status_code == 413
    assert client.post(url(report), content=b"not json", headers=headers).status_code == 422
    assert client.post(url(report), content=b"[" * 100000, headers=headers).status_code == 422
    assert client.get(url(report)).json() == []


def test_unknown_scan_has_no_history(demo):
    client, _, _, _ = demo
    assert client.get("/api/scans/12345678-1111-2222-3333-444444444444/ai/reviews/history").status_code == 404
