"""Gemini AI review: settings, the route, consent, validation and failures.

Gemini is always mocked with ``httpx.MockTransport``; no test talks to Google.
"""
from __future__ import annotations

import json
import shutil

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_GEMINI_MODEL, load_settings
from app.errors import ConfigError
from app.gemini import GeminiClient
from app.main import create_app

KEY = "AIza-test-key-not-real-0123456789"


class FakeGemini:
    """Answers generateContent from a list of responses; records every request."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


def model_answer(review: dict) -> httpx.Response:
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(review)}]}, "finishReason": "STOP"}]})


def good_review(file: str, static_id: str | None = None) -> dict:
    return {
        "summary": "The change removes an ownership check before returning an invoice.",
        "recommendation": "block_release",
        "findings": [{
            "id": "F1", "title": "Ownership check removed", "severity": "high", "category": "Authorization",
            "file": file, "line": 3, "evidence": "- require_owner(user, invoice)",
            "rationale": "Any signed-in user could read another user's invoice.",
            "recommendation": "Restore the ownership check.", "confidence": "high",
            "related_static_finding_ids": [static_id] if static_id else [],
            "suggested_validation": "Request another user's invoice; expect a refusal.",
            "proposed_patch": "+    require_owner(user, invoice)",
        }],
        "test_ideas": [{"title": "Cross-user invoice read", "scenario": "User B requests user A's invoice.",
                        "expected_behavior": "403 refusal", "file": file}],
        "missing_context": ["Callers of the endpoint were not included."],
        "limitations": ["Only the diff was available."],
    }


@pytest.fixture()
def make_client(tmp_path):
    clients = []

    def build(fake: FakeGemini | None, **kwargs):
        gemini = GeminiClient(KEY, "gemini-test", transport=httpx.MockTransport(fake), sleep=lambda _s: None) if fake else None
        client = TestClient(create_app(demo_root=tmp_path / "demo", db_file=tmp_path / "scans.db", gemini=gemini, **kwargs),
                            base_url="http://127.0.0.1")
        client.__enter__()
        clients.append(client)
        return client

    yield build
    for client in clients:
        client.__exit__(None, None, None)


def demo_scan(client) -> dict:
    response = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/auth-regression"})
    assert response.status_code == 201, response.text
    return response.json()


# -- settings ----------------------------------------------------------------

def test_settings_absent_without_key():
    assert load_settings({}).gemini is None


def test_settings_default_model_and_secret_key():
    gemini = load_settings({"SHIPSAFE_GEMINI_API_KEY": KEY}).gemini
    assert gemini.model == DEFAULT_GEMINI_MODEL
    assert gemini.api_key.reveal() == KEY
    assert KEY not in repr(gemini) and KEY not in str(gemini)


def test_settings_model_prefix_is_removed():
    gemini = load_settings({"SHIPSAFE_GEMINI_API_KEY": KEY, "SHIPSAFE_GEMINI_MODEL": "models/gemini-2.5-pro"}).gemini
    assert gemini.model == "gemini-2.5-pro"


@pytest.mark.parametrize("env, message", [
    ({"SHIPSAFE_GEMINI_MODEL": "gemini-2.5-pro"}, "SHIPSAFE_GEMINI_API_KEY is not"),
    ({"SHIPSAFE_GEMINI_API_KEY": "has space"}, "whitespace"),
    ({"SHIPSAFE_GEMINI_API_KEY": KEY, "SHIPSAFE_GEMINI_MODEL": "../evil?x=1"}, "plain model name"),
])
def test_settings_refuse_bad_values_without_echoing_them(env, message):
    with pytest.raises(ConfigError, match=message) as error:
        load_settings(env)
    assert KEY not in str(error.value)


def test_client_repr_hides_key():
    assert KEY not in repr(GeminiClient(KEY, "gemini-test"))


# -- routes ------------------------------------------------------------------

def test_not_configured(make_client):
    client = make_client(None)
    assert client.get("/api/ai/gemini/status").json() == {"configured": False, "model": None}
    scan = demo_scan(client)
    response = client.post(f"/api/scans/{scan['id']}/ai/gemini-reviews")
    assert response.status_code == 503
    assert response.json()["code"] == "gemini_not_configured"


def test_review_of_demo_scan_is_stored_as_unverified(make_client):
    fake = FakeGemini()
    client = make_client(fake)
    assert client.get("/api/ai/gemini/status").json() == {"configured": True, "model": "gemini-test"}
    scan = demo_scan(client)
    static_id = scan["findings"][0]["id"] if scan["findings"] else None
    fake.answers = [model_answer(good_review(scan["files"][0]["path"], static_id))]

    response = client.post(f"/api/scans/{scan['id']}/ai/gemini-reviews")
    assert response.status_code == 201, response.text
    review = response.json()
    assert review["source"] == "gemini_api_generated_unverified"
    assert review["verification_status"] == "not_independently_verified"
    assert review["tests_executed"] is False
    generator = review["generator"]
    assert (generator["provider"], generator["model"]) == ("gemini", "gemini-test")
    assert generator["usage"] == {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}  # the fake reports no usageMetadata
    assert isinstance(generator["duration_ms"], int)
    assert "estimated_cost_usd" not in generator  # no Gemini price table
    assert review["schema_version"] == "shipsafe.ai-review.v2"
    assert review["scan_id"] == scan["id"]
    assert [item["status"] for item in review["findings"]] == ["suspected"]
    assert review["limitations"][0].startswith("Generated automatically by the Gemini API")
    # Identity is ShipSafe's, so the stored review matches this scan's context.
    assert review["context_digest"] == client.get(f"/api/scans/{scan['id']}/ai/context").json()["context_digest"]
    assert [item["id"] for item in client.get(f"/api/scans/{scan['id']}/ai/reviews").json()] == [review["id"]]

    request = fake.requests[0]
    assert request.url.path.endswith("/models/gemini-test:generateContent")
    assert request.headers["x-goog-api-key"] == KEY
    assert KEY not in str(request.url)
    body = json.loads(request.content)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "UNTRUSTED DATA" in body["systemInstruction"]["parts"][0]["text"]
    assert scan["id"] in body["contents"][0]["parts"][0]["text"]
    assert KEY not in response.text


def test_model_output_is_sanitised_not_trusted(make_client):
    fake = FakeGemini()
    client = make_client(fake)
    scan = demo_scan(client)
    path = scan["files"][0]["path"]
    answer = good_review(path)
    answer.update({
        "scan_id": "f" * 36, "context_digest": "0" * 64, "recommendation": "ship_it",
        "findings": [
            {**answer["findings"][0], "id": "bad id!", "related_static_finding_ids": ["made-up"], "severity": "HIGH"},
            {**answer["findings"][0], "file": "../../etc/passwd"},
            {**answer["findings"][0], "severity": "catastrophic"},
            {**answer["findings"][0], "title": "x"},
            "not an object",
        ],
    })
    answer["test_ideas"][0]["file"] = "elsewhere.py"
    fake.answers = [model_answer(answer)]

    review = client.post(f"/api/scans/{scan['id']}/ai/gemini-reviews").json()
    assert review["scan_id"] == scan["id"]
    assert review["context_digest"] != "0" * 64
    assert review["recommendation"] == "manual_review"
    assert [(item["id"], item["severity"], item["related_static_finding_ids"]) for item in review["findings"]] == [("G1", "high", [])]
    assert review["test_ideas"][0]["file"] is None
    assert "4 proposed finding(s) were discarded" in review["limitations"][1]


def test_no_findings_is_a_valid_review(make_client):
    fake = FakeGemini()
    client = make_client(fake)
    scan = demo_scan(client)
    fake.answers = [model_answer({"summary": "No problems found in this change.", "recommendation": "manual_review",
                                  "findings": [], "test_ideas": [], "missing_context": [], "limitations": []})]
    response = client.post(f"/api/scans/{scan['id']}/ai/gemini-reviews")
    assert response.status_code == 201
    assert response.json()["findings"] == []


def test_non_demo_code_needs_acknowledgement(make_client, tmp_path):
    fake = FakeGemini()
    other = tmp_path / "approved" / "repo"
    client = make_client(fake, allowed_root=tmp_path / "approved")
    shutil.copytree(tmp_path / "demo", other)
    scan = client.post("/api/scans", json={"repository_path": str(other), "base_ref": "main", "head_ref": "feature/auth-regression"}).json()
    fake.answers = [model_answer(good_review(scan["files"][0]["path"]))]

    refused = client.post(f"/api/scans/{scan['id']}/ai/gemini-reviews")
    assert refused.status_code == 428
    refused_explicit = client.post(f"/api/scans/{scan['id']}/ai/gemini-reviews", json={"acknowledge_source_sharing": False})
    assert refused_explicit.status_code == 428
    assert fake.requests == []  # nothing was sent to Gemini

    accepted = client.post(f"/api/scans/{scan['id']}/ai/gemini-reviews", json={"acknowledge_source_sharing": True})
    assert accepted.status_code == 201
    assert len(fake.requests) == 1


@pytest.mark.parametrize("answer, status, code", [
    (httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT", "message": f"API_KEY_INVALID {KEY}"}}), 502, "gemini_auth_failed"),
    (httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED"}}), 502, "gemini_permission_denied"),
    (httpx.Response(404, json={"error": {"status": "NOT_FOUND"}}), 502, "gemini_model_not_found"),
    (httpx.Response(429, json={"error": {"status": "RESOURCE_EXHAUSTED"}}), 429, "gemini_rate_limited"),
    (httpx.Response(500, text="oops"), 503, "gemini_unavailable"),
    (httpx.ReadTimeout("slow"), 504, "gemini_timeout"),
    (httpx.ConnectError("down"), 503, "gemini_unavailable"),
    (httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}), 502, "gemini_no_answer"),
    (httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "not json"}]}, "finishReason": "MAX_TOKENS"}]}), 502, "gemini_bad_response"),
    (httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "[1, 2]"}]}}]}), 502, "gemini_bad_response"),
])
def test_failures_are_reported_and_store_nothing(make_client, answer, status, code):
    client = make_client(FakeGemini(answer))
    scan = demo_scan(client)
    response = client.post(f"/api/scans/{scan['id']}/ai/gemini-reviews")
    assert (response.status_code, response.json()["code"]) == (status, code)
    assert KEY not in response.text
    assert client.get(f"/api/scans/{scan['id']}/ai/reviews").json() == []


def test_permission_denied_passes_googles_reason_with_key_masked(make_client):
    reason = f"The Gemini API free tier is not available for this project (key {KEY}). Set up billing."
    client = make_client(FakeGemini(httpx.Response(403, json={"error": {"status": "PERMISSION_DENIED", "message": reason}})))
    scan = demo_scan(client)
    response = client.post(f"/api/scans/{scan['id']}/ai/gemini-reviews")
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "free tier is not available for this project (key [key]). Set up billing." in detail
    assert KEY not in response.text


def test_unknown_scan_is_404(make_client):
    client = make_client(FakeGemini(model_answer({})))
    assert client.post("/api/scans/00000000-0000-0000-0000-000000000000/ai/gemini-reviews").status_code == 404


def test_temporary_failure_is_retried_then_succeeds(make_client):
    fake = FakeGemini()
    client = make_client(fake)
    scan = demo_scan(client)
    busy = httpx.Response(503, json={"error": {"status": "UNAVAILABLE", "message": "This model is currently experiencing high demand."}})
    fake.answers = [busy, httpx.ReadTimeout("slow"), model_answer(good_review(scan["files"][0]["path"]))]
    response = client.post(f"/api/scans/{scan['id']}/ai/gemini-reviews")
    assert response.status_code == 201
    assert len(fake.requests) == 3


def test_persistent_overload_reports_googles_reason_after_three_attempts(make_client):
    busy = httpx.Response(503, json={"error": {"status": "UNAVAILABLE", "message": "This model is currently experiencing high demand."}})
    fake = FakeGemini(busy)
    client = make_client(fake)
    scan = demo_scan(client)
    response = client.post(f"/api/scans/{scan['id']}/ai/gemini-reviews")
    assert (response.status_code, response.json()["code"]) == (503, "gemini_unavailable")
    assert "experiencing high demand" in response.json()["detail"]
    assert "(tried 3 times)" in response.json()["detail"]
    assert len(fake.requests) == 3


def test_permanent_errors_are_not_retried(make_client):
    fake = FakeGemini(httpx.Response(404, json={"error": {"status": "NOT_FOUND"}}))
    client = make_client(fake)
    scan = demo_scan(client)
    assert client.post(f"/api/scans/{scan['id']}/ai/gemini-reviews").status_code == 502
    assert len(fake.requests) == 1
