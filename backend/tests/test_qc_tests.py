"""Phase 6: QC test cases written by an AI model from an AI review, and tester results.

OpenAI is mocked with ``httpx.MockTransport``; no test talks to OpenAI, and nothing is executed.
"""
from __future__ import annotations

import csv
import io
import json
import shutil

from app import db, qc_tests
from tests.test_openai_review import FakeOpenAI, answer, demo_scan, make_client, review_for  # noqa: F401 (fixture)


def cases_answer(finding_id: str = "F1", extra: list | None = None) -> dict:
    return {"test_cases": [{
        "finding_id": finding_id, "title": "Another user's invoice is refused", "priority": "high",
        "area": "Invoices", "preconditions": ["Two accounts: A and B", "A owns invoice 42"], "test_data": ["Invoice id 42"],
        "steps": ["Sign in as B", "Open /invoices/42"], "expected": "Access is refused (403) and no invoice data is shown.",
        "bug_title_if_fails": "User can read another user's invoice",
    }] + (extra or [])}


def reviewed_scan(client, fake):
    scan = demo_scan(client)
    fake.answers = [answer(review_for(scan["files"][0]["path"]))]
    review = client.post(f"/api/scans/{scan['id']}/ai/model-reviews", json={"provider": "openai"})
    assert review.status_code == 201, review.text
    return scan, review.json()


def create(client, scan_id, **body):
    return client.post(f"/api/scans/{scan_id}/qc/test-suites", json={"provider": "openai", **body})


def test_test_cases_are_written_from_the_review_stored_and_never_executed(make_client):
    fake = FakeOpenAI()
    client = make_client(fake)
    scan, review = reviewed_scan(client, fake)
    junk = [{"finding_id": "NOPE", "title": "Points at nothing", "priority": "low", "area": "", "preconditions": [],
             "test_data": [], "steps": ["x"], "expected": "something", "bug_title_if_fails": ""},
            {"finding_id": "F1", "title": "No steps", "priority": "high", "area": "", "preconditions": [], "test_data": [],
             "steps": [], "expected": "something", "bug_title_if_fails": ""}]
    fake.answers = [answer(cases_answer(extra=junk))]
    created = create(client, scan["id"])
    assert created.status_code == 201, created.text
    suite = created.json()
    assert suite["review_id"] == review["id"] and suite["executed_by_shipsafe"] is False
    assert suite["total"] == 1 and suite["counts"] == {"passed": 0, "failed": 0, "blocked": 0, "not_run": 1}
    case = suite["cases"][0]
    assert (case["id"], case["finding_id"], case["priority"], case["status"]) == ("TC1", "F1", "high", "not_run")
    assert case["steps"] == ["Sign in as B", "Open /invoices/42"] and case["file"] == scan["files"][0]["path"]
    assert any("2 test cases were dropped" in item for item in suite["limitations"])
    assert suite["generator"]["provider"] == "openai" and suite["generator"]["estimated_cost_usd"] > 0
    # The model got the review's findings and the change, with the QC instructions and schema.
    sent = json.loads(fake.requests[-1].content)
    assert sent["text"]["format"]["name"] == "shipsafe_qc_test_cases"
    assert "QC engineer" in sent["instructions"] and '"F1"' in sent["input"]
    assert client.get(f"/api/scans/{scan['id']}/qc/test-suites").json()[0]["id"] == suite["id"]


def test_results_are_append_only_and_the_newest_is_the_status(make_client):
    fake = FakeOpenAI()
    client = make_client(fake)
    scan, _ = reviewed_scan(client, fake)
    fake.answers = [answer(cases_answer())]
    suite = create(client, scan["id"]).json()
    url = f"/api/scans/{scan['id']}/qc/test-suites/{suite['id']}/results"
    assert client.post(url, json={"case_id": "TC1", "status": "failed", "tester": "Mona", "note": "403 not returned"}).status_code == 201
    after = client.post(url, json={"case_id": "TC1", "status": "passed", "tester": "Mona"}).json()
    case = after["cases"][0]
    assert case["status"] == "passed" and [item["status"] for item in case["results"]] == ["failed", "passed"]
    assert after["counts"]["passed"] == 1
    assert client.post(url, json={"case_id": "TC9", "status": "passed", "tester": "Mona"}).status_code == 404
    assert client.post(url, json={"case_id": "TC1", "status": "great", "tester": "Mona"}).status_code == 422
    assert client.post(url, json={"case_id": "TC1", "status": "passed", "tester": "M"}).status_code == 422
    assert client.post(f"/api/scans/{scan['id']}/qc/test-suites/unknown/results",
                       json={"case_id": "TC1", "status": "passed", "tester": "Mona"}).status_code == 404


def test_the_assessment_reports_tester_results_as_self_declared(make_client):
    fake = FakeOpenAI()
    client = make_client(fake)
    scan, _ = reviewed_scan(client, fake)
    fake.answers = [answer(cases_answer())]
    suite = create(client, scan["id"]).json()
    client.post(f"/api/scans/{scan['id']}/qc/test-suites/{suite['id']}/results",
                json={"case_id": "TC1", "status": "failed", "tester": "Mona"})
    assessment = client.get(f"/api/scans/{scan['id']}/assessment").json()
    manual = assessment["manual_tests"]
    assert manual["counts"]["failed"] == 1 and manual["failed"][0]["tester"] == "Mona"
    assert manual["label"].startswith("RECORDED BY TESTERS")
    assert assessment["tests"]["runs"]["executed"] == 0  # a tester's result is not a ShipSafe execution
    assert any("what testers recorded" in item for item in assessment["unknowns"])
    report = client.get(f"/api/scans/{scan['id']}/assessment/report").text
    assert "## Manual QC tests" in report and "FAILED TC1" in report


def test_exports_are_csv_and_markdown_and_csv_cells_cannot_be_formulas(make_client):
    fake = FakeOpenAI()
    client = make_client(fake)
    scan, _ = reviewed_scan(client, fake)
    hostile = cases_answer()
    hostile["test_cases"][0]["title"] = "=HYPERLINK(\"http://x\")"
    fake.answers = [answer(hostile)]
    suite = create(client, scan["id"]).json()
    base = f"/api/scans/{scan['id']}/qc/test-suites/{suite['id']}/export"
    response = client.get(base, params={"format": "csv"})
    assert response.status_code == 200 and "attachment" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text.lstrip("﻿"))))
    assert rows[0][:3] == ["ID", "Title", "Priority"] and rows[1][1].startswith("'=")
    assert "1. Sign in as B" in rows[1][8]
    markdown = client.get(base, params={"format": "markdown"}).text
    assert "## TC1" in markdown and "ShipSafe executed nothing" in markdown
    assert client.get(base, params={"format": "xlsx"}).status_code == 422


def test_refusals_come_before_anything_is_sent(make_client, tmp_path):
    fake = FakeOpenAI()
    client = make_client(fake)
    scan = demo_scan(client)
    assert create(client, scan["id"]).status_code == 409  # no AI review yet
    assert fake.requests == []
    assert client.post(f"/api/scans/{scan['id']}/qc/test-suites", json={"provider": "gemini"}).status_code == 503
    assert create(client, "12345678-1111-2222-3333-444444444444").status_code == 404


def test_non_demo_code_needs_acknowledgement(make_client, tmp_path):
    fake = FakeOpenAI()
    other = tmp_path / "approved" / "repo"
    client = make_client(fake, allowed_root=tmp_path / "approved")
    shutil.copytree(tmp_path / "demo", other)
    scan = client.post("/api/scans", json={"repository_path": str(other), "base_ref": "main", "head_ref": "feature/auth-regression"}).json()
    fake.answers = [answer(review_for(scan["files"][0]["path"]))]
    assert client.post(f"/api/scans/{scan['id']}/ai/model-reviews",
                       json={"provider": "openai", "acknowledge_source_sharing": True}).status_code == 201
    sent_before = len(fake.requests)
    fake.answers = [answer(cases_answer())]
    assert create(client, scan["id"]).status_code == 428
    assert len(fake.requests) == sent_before
    assert create(client, scan["id"], acknowledge_source_sharing=True).status_code == 201


def test_a_model_answer_with_no_usable_case_stores_nothing(make_client):
    fake = FakeOpenAI()
    client = make_client(fake)
    scan, _ = reviewed_scan(client, fake)
    fake.answers = [answer({"test_cases": []})]
    refused = create(client, scan["id"])
    assert refused.status_code == 502 and refused.json()["code"] == "openai_no_test_cases"
    assert client.get(f"/api/scans/{scan['id']}/qc/test-suites").json() == []


def test_migration_5_only_adds_tables(tmp_path):
    db_file = tmp_path / "scans.db"
    assert db.migrate(db_file) == db.LATEST_VERSION == 5
    statements = " ".join(db.MIGRATIONS[4].statements).upper()
    assert not any(word in statements for word in ("DROP ", "DELETE ", "UPDATE ", "ALTER "))


def test_the_qc_module_cannot_execute_anything():
    source = open(qc_tests.__file__, encoding="utf-8").read()
    for forbidden in ("subprocess", "os.system", "exec(", "eval(", "importlib"):
        assert forbidden not in source


def test_gemini_receives_the_qc_task_and_its_schema():
    import httpx
    from app.gemini import GeminiClient
    seen = []

    def reply(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(cases_answer())}]},
                                                          "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 10}})
    client = GeminiClient("gemini-test-key-not-real", "gemini-flash-latest", transport=httpx.MockTransport(reply), sleep=lambda _s: None)
    raw, usage = client.review({"findings": []}, qc_tests.TASK)
    assert raw["test_cases"][0]["finding_id"] == "F1" and usage["input_tokens"] == 10
    body = seen[0]
    assert "QC engineer" in body["systemInstruction"]["parts"][0]["text"]
    assert body["generationConfig"]["responseSchema"] == qc_tests.TASK.gemini_schema
    assert body["contents"][0]["parts"][0]["text"].startswith(qc_tests.PROMPT)
