"""AI review through the OpenAI Responses API (server side).

Same contract as ``gemini.py``: the key stays on the server (``Authorization``
header only, masked out of error text), the model receives exactly the
secret-redacted review context of the Claude handoff package, and its answer
is untrusted text that ``gemini.build_review`` reshapes and the v2 import rules
validate before it is stored as an unverified AI suggestion.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable

import httpx

from .gemini import ATTEMPTS, BACKOFF_SECONDS, RETRY_STATUSES, SYSTEM_INSTRUCTION, GeminiError, _count

API_BASE = "https://api.openai.com/v1"
TIMEOUT_SECONDS = 120.0
DEFAULT_MODEL = "gpt-6-luna"
SOURCE = "openai_api_generated_unverified"
#: Reasoning effort for reasoning models. "low" keeps latency and hidden
#: reasoning tokens down; set SHIPSAFE_OPENAI_REASONING_EFFORT to change it.
DEFAULT_REASONING_EFFORT = "low"
REASONING_EFFORTS = ("minimal", "low", "medium", "high")

#: USD per 1M tokens (input, cached input, output), standard tier, from
#: https://developers.openai.com/api/docs/pricing as read on 2026-11-13.
#: Used only to show an estimated cost; models not listed show tokens only.
PRICES_PER_MILLION: dict[str, tuple[float, float, float]] = {
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-6-sol": (2.00, 0.20, 10.00),
    "gpt-6.1-sol": (2.00, 0.10, 10.00),
    "gpt-6.1-terra": (1.00, 0.05, 5.00),
    "gpt-6-astra": (10.00, 1.00, 50.00),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
    "gpt-5.6-terra": (2.00, 0.20, 12.00),
    "gpt-5.6-sol": (4.00, 0.40, 20.00),
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
    "gpt-5.4-nano": (0.20, 0.02, 1.25),
    "gpt-5-mini": (0.25, 0.025, 2.00),
    "gpt-5-nano": (0.05, 0.005, 0.40),
    "gpt-4.1-mini": (0.40, 0.10, 1.60),
    "gpt-4o-mini": (0.15, 0.075, 0.60),
}
PRICES_AS_OF = "2026-11-13"


def _nullable(kind: str) -> dict:
    return {"type": [kind, "null"]}


def _strict_object(properties: dict[str, Any]) -> dict:
    """OpenAI strict mode: every property required, nothing extra allowed."""
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


RESPONSE_SCHEMA: dict[str, Any] = _strict_object({
    "summary": {"type": "string"},
    "recommendation": {"type": "string", "enum": ["block_release", "manual_review", "insufficient_evidence"]},
    "findings": {"type": "array", "items": _strict_object({
        "id": {"type": "string"},
        "title": {"type": "string"},
        "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
        "category": {"type": "string"},
        "file": {"type": "string"},
        "line": _nullable("integer"),
        "evidence": {"type": "string"},
        "rationale": {"type": "string"},
        "recommendation": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "related_static_finding_ids": {"type": "array", "items": {"type": "string"}},
        "suggested_validation": {"type": "string"},
        "proposed_patch": _nullable("string"),
    })},
    "test_ideas": {"type": "array", "items": _strict_object({
        "title": {"type": "string"},
        "scenario": {"type": "string"},
        "expected_behavior": {"type": "string"},
        "file": _nullable("string"),
    })},
    "missing_context": {"type": "array", "items": {"type": "string"}},
    "limitations": {"type": "array", "items": {"type": "string"}},
})


class OpenAIError(GeminiError):
    """An OpenAI review could not be produced (same rendering as GeminiError)."""


def estimated_cost_usd(model: str, usage: dict) -> float | None:
    prices = PRICES_PER_MILLION.get(model)
    if prices is None:
        return None
    price_in, price_cached, price_out = prices
    cached = min(usage.get("cached_input_tokens", 0), usage.get("input_tokens", 0))
    fresh = usage.get("input_tokens", 0) - cached
    return round((fresh * price_in + cached * price_cached + usage.get("output_tokens", 0) * price_out) / 1_000_000, 6)


class OpenAIClient:
    """Minimal Responses API client. ``transport`` and ``sleep`` let tests mock HTTP and time."""

    provider = "openai"
    label = "OpenAI"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, *, reasoning_effort: str | None = DEFAULT_REASONING_EFFORT,
                 transport: httpx.BaseTransport | None = None, timeout: float = TIMEOUT_SECONDS,
                 sleep: Callable[[float], None] = time.sleep):
        self.model = model
        self.reasoning_effort = reasoning_effort
        self._timeout = timeout
        self._sleep = sleep
        self._mask = api_key  # only to mask it out of error text
        self._client = httpx.Client(
            base_url=API_BASE, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=timeout, follow_redirects=False, transport=transport,
        )

    def __repr__(self) -> str:  # never show the key
        return f"OpenAIClient(model={self.model!r})"

    def _body(self, context: dict, with_reasoning: bool) -> dict:
        body: dict[str, Any] = {
            "model": self.model,
            "instructions": SYSTEM_INSTRUCTION,
            "input": "Review this change. Input JSON:\n" + json.dumps(context, ensure_ascii=False),
            "text": {"format": {"type": "json_schema", "name": "shipsafe_review", "schema": RESPONSE_SCHEMA, "strict": True}},
            "store": False,
        }
        if with_reasoning and self.reasoning_effort:
            body["reasoning"] = {"effort": self.reasoning_effort}
        return body

    def review(self, context: dict) -> tuple[dict, dict]:
        """Ask the model to review ``context``; returns its JSON object and the token usage."""
        with_reasoning = True
        failure: OpenAIError | None = None
        attempt = 0
        while attempt < ATTEMPTS:
            attempt += 1
            if attempt > 1 and failure is not None:
                self._sleep(BACKOFF_SECONDS[min(attempt - 2, len(BACKOFF_SECONDS) - 1)])
            try:
                response = self._client.post("/responses", json=self._body(context, with_reasoning))
            except httpx.TimeoutException:
                failure = OpenAIError(504, "openai_timeout", f"OpenAI did not answer within {self._timeout:g} seconds.")
                continue
            except httpx.HTTPError as exc:
                failure = OpenAIError(503, "openai_unavailable", f"OpenAI could not be reached ({type(exc).__name__}).")
                continue
            if response.status_code == 400 and with_reasoning and "reasoning" in response.text:
                # A model without reasoning support: ask again without the setting (not a retry).
                with_reasoning, attempt, failure = False, attempt - 1, None
                continue
            if response.status_code in RETRY_STATUSES:
                failure = _http_error(response, self.model, self._mask)
                continue
            if response.status_code != 200:
                raise _http_error(response, self.model, self._mask)
            break
        else:
            assert failure is not None
            failure.message = f"{failure.message} (tried {ATTEMPTS} times)"
            raise failure
        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenAIError(502, "openai_bad_response", "OpenAI answered with something that is not JSON.") from exc
        return _review_json(payload), _usage(payload)


def _message(response: httpx.Response, key: str) -> str:
    try:
        message = str((response.json().get("error") or {}).get("message") or "")
    except ValueError:
        return ""
    if key:
        message = message.replace(key, "[key]")
    return " ".join(message.split())[:400]


def _http_error(response: httpx.Response, model: str, key: str) -> OpenAIError:
    status = response.status_code
    text = _message(response, key)
    detail = f": {text}" if text else "."
    if status == 401:
        return OpenAIError(502, "openai_auth_failed", "OpenAI rejected the server's API key. Check SHIPSAFE_OPENAI_API_KEY and restart the API.")
    if status == 403:
        return OpenAIError(502, "openai_permission_denied", f"OpenAI refused this key's request{detail}")
    if status == 404:
        return OpenAIError(502, "openai_model_not_found",
                           f"OpenAI does not offer the model '{model}' to this key{detail} Set SHIPSAFE_OPENAI_MODEL to an available model.")
    if status == 429:
        return OpenAIError(429, "openai_rate_limited", f"OpenAI's rate limit or quota for this key is exhausted{detail} Try again later.")
    if status >= 500:
        return OpenAIError(503, "openai_unavailable", f"OpenAI is unavailable right now (HTTP {status}{detail}) Try again later.")
    return OpenAIError(502, "openai_request_rejected", f"OpenAI refused the request (HTTP {status}){detail}")


def _usage(payload: dict) -> dict:
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    input_details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    output_details = usage.get("output_tokens_details") if isinstance(usage.get("output_tokens_details"), dict) else {}
    return {
        "input_tokens": _count(usage.get("input_tokens")),
        "cached_input_tokens": _count(input_details.get("cached_tokens")),
        # Includes hidden reasoning tokens, which OpenAI bills as output.
        "output_tokens": _count(usage.get("output_tokens")),
        "reasoning_tokens": _count(output_details.get("reasoning_tokens")),
    }


def _review_json(payload: dict) -> dict:
    if payload.get("status") not in (None, "completed"):
        reason = (payload.get("incomplete_details") or {}).get("reason") if isinstance(payload.get("incomplete_details"), dict) else None
        hint = " The answer was cut off (output limit)." if reason == "max_output_tokens" else ""
        raise OpenAIError(502, "openai_no_answer", f"OpenAI did not complete the review (status {payload.get('status')}{f', {reason}' if reason else ''}).{hint}")
    texts, refusal = [], None
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text":
                texts.append(str(part.get("text") or ""))
            elif isinstance(part, dict) and part.get("type") == "refusal":
                refusal = str(part.get("refusal") or "")[:300]
    if refusal and not "".join(texts).strip():
        raise OpenAIError(502, "openai_no_answer", f"OpenAI declined to review: {refusal}")
    text = "".join(texts)
    if not text.strip():
        raise OpenAIError(502, "openai_no_answer", "OpenAI returned an empty review.")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise OpenAIError(502, "openai_bad_response", "OpenAI's review is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise OpenAIError(502, "openai_bad_response", "OpenAI's review is not a JSON object.")
    return data
