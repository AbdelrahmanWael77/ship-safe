"""Phase 5 task 2: the release assessment only arranges stored evidence. It
never calls a change safe, never counts a blocked run as a result, and every
figure in it can be traced to a stored row."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import db
from app.assessment import NEVER_SAFE, assess, render_markdown
from app.main import create_app

TEST = "def test_other_user_is_refused():\n    assert True\n"
SAFE_WORDS = ("is safe", "safe to release", "safe to merge", "approved for release", "no risk", "guaranteed", "verified safe")


@pytest.fixture()
def demo(tmp_path):
    repo = tmp_path / "demo"
    db_file = tmp_path / "data" / "scans.db"
    app = create_app(demo_root=repo, db_file=db_file, allowed_root=repo)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, db_file


def scan(client, head="feature/auth-regression"):
    return client.post("/api/scans", json={"base_ref": "main", "head_ref": head}).json()


def assessment(client, report):
    response = client.get(f"/api/scans/{report['id']}/assessment")
    assert response.status_code == 200, response.text
    return response.json()


def import_review(client, report):
    archive = zipfile.ZipFile(io.BytesIO(client.get(f"/api/scans/{report['id']}/ai/handoff").content))
    template = json.loads(archive.read("response-template.json"))
    template["findings"][0].update({"file": report["files"][0]["path"], "title": "Synthetic AI finding"})
    review = {**template, "summary": "Synthetic fixture review; nothing was executed.", "test_ideas": [], "missing_context": []}
    saved = client.post(f"/api/scans/{report['id']}/ai/reviews", json=review)
    assert saved.status_code == 201, saved.text
    return saved.json()


def test_a_fresh_scan_is_tests_incomplete_with_static_findings_labelled_suspected(demo):
    client, _ = demo
    report = scan(client)
    result = assessment(client, report)
    assert result["state"] == "tests_incomplete" and result["states"] == ["tests_incomplete", "review_required"]
    assert result["statement"] == NEVER_SAFE
    identity = result["identity"]
    assert (identity["base_commit"], identity["head_commit"]) == (report["binding"]["base_commit"], report["binding"]["head_commit"])
    assert identity["provider"] == "local-git" and identity["pull_request_id"] is None and identity["stale"] is False
    static = result["static"]
    assert static["label"].startswith("SUSPECTED") and static["finding_count"] == len(report["findings"]) > 0
    assert sum(static["by_severity"].values()) == len(report["findings"])
    assert [item["id"] for item in static["findings"]] == [item["id"] for item in report["findings"]]
    assert result["ai_reviews"] == {"label": result["ai_reviews"]["label"], "count": 0, "latest": None}
    assert result["ai_reviews"]["label"].startswith("UNVERIFIED")
    tests = result["tests"]
    assert tests["repository_test_status"] == "not_run"
    assert tests["runs"] == {"requested": 0, "blocked": 0, "executed": 0, "confirmed_regressions": 0, "items": []}
    assert any("No test was executed" in item for item in result["unknowns"])
    assert any("No AI review was imported" in item for item in result["unknowns"])
    assert client.get(f"/api/scans/{report['id']}").json() == report  # reading an assessment changes nothing


def test_reviews_decisions_and_blocked_runs_are_reported_as_what_they_are(demo):
    client, _ = demo
    report = scan(client)
    review = import_review(client, report)
    base = f"/api/scans/{report['id']}/tests/proposals"
    approved = client.post(base, json={"target_path": "tests/test_a.py", "content": TEST, "origin": "human"}).json()
    client.post(f"{base}/{approved['id']}/decisions", json={"decision": "approved", "decided_by": "Nour Waled"})
    rejected = client.post(base, json={"target_path": "tests/test_b.py", "content": TEST, "origin": "imported_ai_review"}).json()
    client.post(f"{base}/{rejected['id']}/decisions", json={"decision": "rejected", "decided_by": "Nour Waled", "note": "Duplicate."})
    client.post(base, json={"target_path": "tests/test_c.py", "content": TEST, "origin": "human"})
    assert client.post(f"{base}/{approved['id']}/runs", json={"requested_by": "Nour Waled"}).status_code == 503

    result = assessment(client, report)
    assert result["state"] == "tests_incomplete"  # a blocked run is not a test result
    ai = result["ai_reviews"]
    assert ai["count"] == 1 and ai["latest"]["id"] == review["id"] and ai["latest"]["finding_count"] == 1
    assert ai["latest"]["findings"][0]["title"] == "Synthetic AI finding"
    tests = result["tests"]
    assert tests["proposals"]["count"] == 3 and tests["proposals"]["by_status"] == {"pending": 1, "approved": 1, "rejected": 1}
    decided = {item["target_path"]: item for item in tests["proposals"]["items"]}
    assert decided["tests/test_a.py"]["decisions"][0]["decided_by"] == "Nour Waled"
    assert decided["tests/test_b.py"]["decisions"][0]["note"] == "Duplicate."
    assert tests["runs"]["requested"] == 1 and tests["runs"]["blocked"] == 1
    assert tests["runs"]["executed"] == 0 and tests["runs"]["confirmed_regressions"] == 0
    run = tests["runs"]["items"][0]
    assert run["status"] == "blocked" and run["executed"] is False and run["exit_code"] is None and run["started_at"] is None
    assert any("requested and blocked" in item for item in result["unknowns"])
    assert any("self-declared" in item for item in result["unknowns"])
    assert any("unverified text" in item for item in result["unknowns"])


def test_a_stale_scan_is_stale_first_and_an_unbound_scan_is_unavailable(demo):
    client, db_file = demo
    report = scan(client)
    with db.session(db_file) as conn:
        conn.execute("UPDATE scans SET stale_at = '2026-11-13T10:00:00+00:00', provider = 'bitbucket-cloud',"
                     " repository_id = 'acme/ledger', pull_request_id = '7' WHERE id = ?", (report["id"],))
    stale = assessment(client, report)
    assert stale["state"] == "stale" and stale["states"] == ["stale", "tests_incomplete", "review_required"]
    assert stale["identity"]["stale_at"] == "2026-11-13T10:00:00+00:00" and stale["identity"]["pull_request_id"] == "7"
    assert stale["unknowns"][0].startswith("The pull request has new commits")

    with db.session(db_file) as conn:
        conn.execute("UPDATE scans SET base_commit = NULL, head_commit = NULL, stale_at = NULL WHERE id = ?", (report["id"],))
    unbound = assessment(client, report)
    assert unbound["state"] == "assessment_unavailable" and unbound["states"][0] == "assessment_unavailable"
    assert unbound["unknowns"][0].startswith("The scan is not bound to exact commits")


def test_only_an_executed_confirmed_regression_can_produce_that_state():
    report = {"id": "s", "findings": [], "files": [], "summary": {}}
    binding = {"provider": "local-git", "base_commit": "a" * 40, "head_commit": "b" * 40, "stale": False}
    run = {"id": "r", "status": "confirmed_regression", "executed": True}
    confirmed = assess(report, binding, [], [{"id": "p", "status": "approved", "decisions": [], "runs": [run]}])
    assert confirmed["state"] == "confirmed_regression" and "tests_incomplete" not in confirmed["states"]
    # The same status on a run that did not execute is not evidence of anything.
    claimed = assess(report, binding, [], [{"id": "p", "status": "approved", "decisions": [], "runs": [{**run, "executed": False}]}])
    assert claimed["state"] == "tests_incomplete" and claimed["tests"]["runs"]["confirmed_regressions"] == 0
    clean = assess(report, binding, [], [])
    assert clean["state"] == "tests_incomplete" and "review_required" in clean["states"]


@pytest.mark.parametrize("head", ["feature/auth-regression", "feature/docs-only", "feature/safe-cleanup"])
def test_no_assessment_or_report_ever_calls_a_change_safe(demo, head):
    client, _ = demo
    report = scan(client, head)
    result = assessment(client, report)
    assert "review_required" in result["states"]
    text = (json.dumps(result) + client.get(f"/api/scans/{report['id']}/assessment/report").text).lower()
    assert "does not say the change is safe" in text
    assert not [word for word in SAFE_WORDS if word in text.replace("does not say the change is safe", "")]


def test_the_readable_report_carries_the_same_identity_and_figures(demo):
    client, _ = demo
    report = scan(client)
    import_review(client, report)
    response = client.get(f"/api/scans/{report['id']}/assessment/report")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"] and report["id"][:8] in response.headers["content-disposition"]
    text = response.text
    assert text.startswith("# ShipSafe release assessment") and "**State: Tests incomplete** (also: Review required)" in text
    for expected in (report["id"], report["binding"]["base_commit"], report["binding"]["head_commit"],
                     "SUSPECTED", "UNVERIFIED", "Run requests: 0 (blocked 0, executed 0)", "Confirmed regressions: 0",
                     "## What is not known"):
        assert expected in text, expected
    for finding in report["findings"]:
        assert finding["title"].replace("|", "\\|").replace("`", "'") in text


def test_untrusted_text_cannot_break_the_report_structure():
    report = {"id": "s", "repo_name": "x | y\n# Injected heading", "created_at": "t", "summary": {},
              "files": [], "findings": [{"id": "f", "severity": "high", "category": "c|d", "file": "a.py", "line": 1,
                                         "title": "Title | with pipe `code`\n## Fake section <script>alert(1)</script>"}]}
    binding = {"provider": "local-git", "base_commit": "a" * 40, "head_commit": "b" * 40, "stale": False}
    text = render_markdown(assess(report, binding, [], []))
    assert "\n# Injected heading" not in text and "\n## Fake section" not in text and "<script>" not in text
    row = next(line for line in text.splitlines() if line.startswith("| high"))
    assert row.count(" | ") == 3 and "\\|" in row  # still four cells


def test_unknown_scan_has_no_assessment(demo):
    client, _ = demo
    unknown = "12345678-1111-2222-3333-444444444444"
    assert client.get(f"/api/scans/{unknown}/assessment").status_code == 404
    assert client.get(f"/api/scans/{unknown}/assessment/report").status_code == 404
