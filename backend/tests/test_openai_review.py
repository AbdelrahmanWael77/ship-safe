"""OpenAI AI review: settings, the generic route, consent, usage/cost and failures.

OpenAI is always mocked with ``httpx.MockTransport``; no test talks to OpenAI.
"""
from __future__ import annotations

import json
import shutil

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_OPENAI_MODEL, load_settings
from app.errors import ConfigError
from app.main import create_app
from app.openai_review import OpenAIClient, estimated_cost_usd

KEY = "sk-test-openai-key-not-real-0123456789"


class FakeOpenAI:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


USAGE = {"input_tokens": 3400, "input_tokens_details": {"cached_tokens": 0},
         "output_tokens": 2600, "output_tokens_details": {"reasoning_tokens": 700}, "total_tokens": 6000}


def answer(review: dict, usage: dict = USAGE) -> httpx.Response:
    return httpx.Response(200, json={"status": "completed", "usage": usage, "output": [
        {"type": "reasoning", "summary": []},
        {"type": "message", "content": [{"type": "output_text", "text": json.dumps(review)}]},
    ]})


def review_for(file: str) -> dict:
    return {
        "summary": "The change removes an ownership check before returning an invoice.",
        "recommendation": "block_release",
        "findings": [{
            "id": "F1", "title": "Ownership check removed", "severity": "high", "category": "Authorization",
            "file": file, "line": 3, "evidence": "- require_owner(user, invoice)",
            "rationale": "Any signed-in user could read another user's invoice.",
            "recommendation": "Restore the ownership check.", "confidence": "high",
            "related_static_finding_ids": [], "suggested_validation": "Request another user's invoice; expect a refusal.",
            "proposed_patch": None,
        }],
        "test_ideas": [{"title": "Cross-user read", "scenario": "User B requests user A's invoice.", "expected_behavior": "403", "file": None}],
        "missing_context": [], "limitations": ["Only the diff was available."],
    }


@pytest.fixture()
def make_client(tmp_path):
    clients = []

    def build(fake: FakeOpenAI | None, model: str = "gpt-6-luna", **kwargs):
        openai = OpenAIClient(KEY, model, transport=httpx.MockTransport(fake), sleep=lambda _s: None) if fake else None
        client = TestClient(create_app(demo_root=tmp_path / "demo", db_file=tmp_path / "scans.db", openai=openai, **kwargs),
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


def post(client, scan_id: str, **body):
    return client.post(f"/api/scans/{scan_id}/ai/model-reviews", json={"provider": "openai", **body})


# -- settings ----------------------------------------------------------------

def test_settings_default_model_effort_and_secret():
    settings = load_settings({"SHIPSAFE_OPENAI_API_KEY": KEY}).openai
    assert (settings.model, settings.reasoning_effort) == (DEFAULT_OPENAI_MODEL, "low")
    assert KEY not in repr(settings)


@pytest.mark.parametrize("env, message", [
    ({"SHIPSAFE_OPENAI_MODEL": "gpt-6-luna"}, "SHIPSAFE_OPENAI_API_KEY is not"),
    ({"SHIPSAFE_OPENAI_API_KEY": "has space"}, "whitespace"),
    ({"SHIPSAFE_OPENAI_API_KEY": KEY, "SHIPSAFE_OPENAI_MODEL": "../x?y"}, "plain model name"),
    ({"SHIPSAFE_OPENAI_API_KEY": KEY, "SHIPSAFE_OPENAI_REASONING_EFFORT": "extreme"}, "REASONING_EFFORT"),
])
def test_settings_refuse_bad_values(env, message):
    with pytest.raises(ConfigError, match=message) as error:
        load_settings(env)
    assert KEY not in str(error.value)


def test_cost_estimate_uses_published_prices():
    usage = {"input_tokens": 1_000_000, "cached_input_tokens": 0, "output_tokens": 1_000_000}
    assert estimated_cost_usd("gpt-6-luna", usage) == pytest.approx(0.60)
    assert estimated_cost_usd("some-unknown-model", usage) is None


# -- routes ------------------------------------------------------------------

def test_providers_lists_configured_models_without_keys(make_client):
    client = make_client(FakeOpenAI(answer({})))
    providers = {item["provider"]: item for item in client.get("/api/ai/providers").json()}
    assert providers["openai"] == {"provider": "openai", "label": "OpenAI", "configured": True, "model": "gpt-6-luna", "pricing_known": True}
    assert providers["gemini"]["configured"] is False
    assert KEY not in client.get("/api/ai/providers").text


def test_not_configured(make_client):
    client = make_client(None)
    scan = demo_scan(client)
    response = post(client, scan["id"])
    assert (response.status_code, response.json()["code"]) == (503, "openai_not_configured")


def test_review_is_stored_with_usage_cost_and_unverified_status(make_client):
    fake = FakeOpenAI()
    client = make_client(fake)
    scan = demo_scan(client)
    fake.answers = [answer(review_for(scan["files"][0]["path"]))]

    response = post(client, scan["id"])
    assert response.status_code == 201, response.text
    review = response.json()
    assert review["source"] == "openai_api_generated_unverified"
    assert review["verification_status"] == "not_independently_verified"
    assert review["tests_executed"] is False
    generator = review["generator"]
    assert (generator["provider"], generator["model"]) == ("openai", "gpt-6-luna")
    assert generator["usage"] == {"input_tokens": 3400, "cached_input_tokens": 0, "output_tokens": 2600, "reasoning_tokens": 700}
    assert generator["estimated_cost_usd"] == pytest.approx((3400 * 0.10 + 2600 * 0.50) / 1_000_000)
    assert generator["prices_as_of"] == "2026-11-13"
    assert isinstance(generator["duration_ms"], int)
    assert review["limitations"][0].startswith("Generated automatically by the OpenAI API (model gpt-6-luna)")
    assert [item["id"] for item in client.get(f"/api/scans/{scan['id']}/ai/reviews").json()] == [review["id"]]

    request = fake.requests[0]
    assert request.url.path == "/v1/responses"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(request.content)
    assert body["model"] == "gpt-6-luna"
    assert body["reasoning"] == {"effort": "low"}
    assert body["store"] is False
    assert body["text"]["format"]["strict"] is True
    assert "UNTRUSTED DATA" in body["instructions"]
    assert KEY not in response.text


def test_unknown_model_price_shows_tokens_only(make_client):
    fake = FakeOpenAI()
    client = make_client(fake, model="gpt-future-x")
    scan = demo_scan(client)
    fake.answers = [answer(review_for(scan["files"][0]["path"]))]
    generator = post(client, scan["id"]).json()["generator"]
    assert "estimated_cost_usd" not in generator
    assert generator["usage"]["output_tokens"] == 2600


def test_model_without_reasoning_support_is_asked_again_without_it(make_client):
    fake = FakeOpenAI()
    client = make_client(fake)
    scan = demo_scan(client)
    rejected = httpx.Response(400, json={"error": {"message": "Unsupported parameter: 'reasoning.effort' is not supported with this model."}})
    fake.answers = [rejected, answer(review_for(scan["files"][0]["path"]))]
    assert post(client, scan["id"]).status_code == 201
    assert "reasoning" in json.loads(fake.requests[0].content)
    assert "reasoning" not in json.loads(fake.requests[1].content)


def test_non_demo_code_needs_acknowledgement(make_client, tmp_path):
    fake = FakeOpenAI()
    other = tmp_path / "approved" / "repo"
    client = make_client(fake, allowed_root=tmp_path / "approved")
    shutil.copytree(tmp_path / "demo", other)
    scan = client.post("/api/scans", json={"repository_path": str(other), "base_ref": "main", "head_ref": "feature/auth-regression"}).json()
    fake.answers = [answer(review_for(scan["files"][0]["path"]))]
    refused = post(client, scan["id"])
    assert refused.status_code == 428
    assert "OpenAI" in refused.json()["detail"]
    assert fake.requests == []
    assert post(client, scan["id"], acknowledge_source_sharing=True).status_code == 201


def test_unknown_provider_is_rejected(make_client):
    client = make_client(FakeOpenAI(answer({})))
    scan = demo_scan(client)
    assert client.post(f"/api/scans/{scan['id']}/ai/model-reviews", json={"provider": "other"}).status_code == 422


@pytest.mark.parametrize("reply, status, code, attempts", [
    (httpx.Response(401, json={"error": {"message": f"Incorrect API key provided: {KEY}"}}), 502, "openai_auth_failed", 1),
    (httpx.Response(404, json={"error": {"message": "The model does not exist"}}), 502, "openai_model_not_found", 1),
    (httpx.Response(429, json={"error": {"message": "You exceeded your current quota"}}), 429, "openai_rate_limited", 3),
    (httpx.Response(503, json={"error": {"message": "Overloaded"}}), 503, "openai_unavailable", 3),
    (httpx.ReadTimeout("slow"), 504, "openai_timeout", 3),
    (httpx.Response(200, json={"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output": []}), 502, "openai_no_answer", 1),
    (httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No."}]}]}), 502, "openai_no_answer", 1),
    (httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "not json"}]}]}), 502, "openai_bad_response", 1),
])
def test_failures_are_reported_and_store_nothing(make_client, reply, status, code, attempts):
    fake = FakeOpenAI(reply)
    client = make_client(fake)
    scan = demo_scan(client)
    response = post(client, scan["id"])
    assert (response.status_code, response.json()["code"]) == (status, code)
    assert KEY not in response.text
    assert len(fake.requests) == attempts
    assert client.get(f"/api/scans/{scan['id']}/ai/reviews").json() == []


def test_transient_failure_then_success(make_client):
    fake = FakeOpenAI()
    client = make_client(fake)
    scan = demo_scan(client)
    fake.answers = [httpx.Response(503, json={"error": {"message": "Overloaded"}}), answer(review_for(scan["files"][0]["path"]))]
    assert post(client, scan["id"]).status_code == 201
    assert len(fake.requests) == 2
