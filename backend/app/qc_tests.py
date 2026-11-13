"""Phase 6: manual QC test cases written from an AI review, and the results testers record.

An AI model (OpenAI or Gemini, through the same clients and consent rules as a
review) turns the findings of one stored AI review into step-by-step manual test
cases a QC engineer can execute. ShipSafe runs nothing: a case is text, and a
result is what a person says happened. Results are append-only; the newest
result of a case is its status.

Everything a model returns is untrusted. Cases that point at a finding the
review does not have, or that lack steps or an expected result, are dropped and
counted; the rest are bounded in size before they are stored.
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .gemini import AITask

PRIORITIES = ("critical", "high", "medium", "low")
STATUSES = ("passed", "failed", "blocked", "not_run")
MAX_CASES = 40
MAX_STEPS = 15
MAX_ITEMS = 8

INSTRUCTION = """You are a senior QC engineer. You receive a code change (diffs) and the findings of an AI
code review of it. Write manual test cases that a tester who does NOT read code can execute on the
running application (mobile app, web app or API) to confirm or rule out each finding.

Rules:
- One or more test cases per finding; reference the finding by its id in finding_id.
- Write from the user's point of view: screens, buttons, inputs, network conditions, API calls.
  Do not ask the tester to read or change source code.
- steps: short imperative steps, in order, each one action. expected: what must happen if the
  change is correct. bug_title_if_fails: a bug title the tester can file if the expected result
  does not happen.
- preconditions and test_data: only what is needed (accounts, settings, sample values, tools such
  as a proxy with an invalid certificate).
- priority follows the finding's severity unless the risk is clearly lower.
- area: the feature or screen (for example "Checkout / payment").
- Never claim a test was run. Do not invent features that the diff does not show.
- Write in English."""

PROMPT = "Write manual QC test cases for the findings of this AI code review."

_CASE_PROPERTIES = {
    "finding_id": "string",
    "title": "string",
    "priority": "string",
    "area": "string",
    "preconditions": "array",
    "test_data": "array",
    "steps": "array",
    "expected": "string",
    "bug_title_if_fails": "string",
}


def _openai_schema() -> dict:
    def kind(name: str, value: str) -> dict:
        if value == "array":
            return {"type": "array", "items": {"type": "string"}}
        if name == "priority":
            return {"type": "string", "enum": list(PRIORITIES)}
        return {"type": "string"}
    case = {"type": "object", "additionalProperties": False, "required": list(_CASE_PROPERTIES),
            "properties": {name: kind(name, value) for name, value in _CASE_PROPERTIES.items()}}
    return {"type": "object", "additionalProperties": False, "required": ["test_cases"],
            "properties": {"test_cases": {"type": "array", "items": case}}}


def _gemini_schema() -> dict:
    def kind(name: str, value: str) -> dict:
        if value == "array":
            return {"type": "ARRAY", "items": {"type": "STRING"}}
        if name == "priority":
            return {"type": "STRING", "enum": list(PRIORITIES)}
        return {"type": "STRING"}
    case = {"type": "OBJECT", "properties": {name: kind(name, value) for name, value in _CASE_PROPERTIES.items()},
            "required": ["finding_id", "title", "priority", "steps", "expected"]}
    return {"type": "OBJECT", "properties": {"test_cases": {"type": "ARRAY", "items": case}}, "required": ["test_cases"]}


TASK = AITask(name="shipsafe_qc_test_cases", instruction=INSTRUCTION, prompt=PROMPT,
              gemini_schema=_gemini_schema(), openai_schema=_openai_schema())


def qc_context(review_context: dict, review: dict) -> dict:
    """What the model receives: the (redacted, size-bounded) review context of the scan, plus
    the findings and test ideas of the review the cases are written from."""
    return {
        "change": {key: review_context.get(key) for key in ("source", "repo_name", "base_ref", "head_ref", "files")},
        "review_summary": review.get("summary"),
        "findings": [{key: finding.get(key) for key in (
            "id", "title", "severity", "category", "file", "line", "rationale", "suggested_validation")}
            for finding in review.get("findings", [])],
        "test_ideas": review.get("test_ideas", []),
    }


def _text(value: object, limit: int) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _texts(value: object, limit: int, count: int) -> list[str]:
    items = [_text(item, limit) for item in value] if isinstance(value, list) else []
    return [item for item in items if item][:count]


def build_cases(raw: dict, review: dict) -> tuple[list[dict], int]:
    """Validated cases from a model answer, and how many were dropped."""
    findings = {str(item.get("id")): item for item in review.get("findings", []) if item.get("id")}
    cases, dropped = [], 0
    for item in raw.get("test_cases") if isinstance(raw.get("test_cases"), list) else []:
        if not isinstance(item, dict):
            dropped += 1
            continue
        finding_id = _text(item.get("finding_id"), 40)
        finding = findings.get(finding_id)
        priority = _text(item.get("priority"), 20).lower()
        case = {
            "finding_id": finding_id if finding else None,
            "title": _text(item.get("title"), 200),
            "priority": priority if priority in PRIORITIES else (finding or {}).get("severity", "medium"),
            "area": _text(item.get("area"), 80) or "General",
            "preconditions": _texts(item.get("preconditions"), 300, MAX_ITEMS),
            "test_data": _texts(item.get("test_data"), 300, MAX_ITEMS),
            "steps": _texts(item.get("steps"), 400, MAX_STEPS),
            "expected": _text(item.get("expected"), 600),
            "bug_title_if_fails": _text(item.get("bug_title_if_fails"), 200),
            "file": (finding or {}).get("file"),
        }
        if not finding or len(case["title"]) < 4 or not case["steps"] or len(case["expected"]) < 5:
            dropped += 1
            continue
        if case["priority"] not in PRIORITIES:
            case["priority"] = "medium"
        if not case["bug_title_if_fails"]:
            case["bug_title_if_fails"] = f"{case['title']} fails"
        cases.append({"id": f"TC{len(cases) + 1}", **case})
        if len(cases) == MAX_CASES:
            break
    order = {name: index for index, name in enumerate(PRIORITIES)}
    cases.sort(key=lambda case: order[case["priority"]])
    for index, case in enumerate(cases, start=1):
        case["id"] = f"TC{index}"
    return cases, dropped


def new_suite(scan_id: str, review: dict, cases: list[dict], dropped: int, generator: dict) -> dict:
    limitations = ["Written by an AI model from an unverified AI review. Check each case before executing it.",
                   "ShipSafe executed nothing. A result is what a tester recorded."]
    if dropped:
        limitations.append(f"{dropped} test case{'s were' if dropped != 1 else ' was'} dropped because "
                           f"{'they were' if dropped != 1 else 'it was'} incomplete or pointed at no finding of the review.")
    covered = {case["finding_id"] for case in cases}
    missing = [item.get("id") for item in review.get("findings", []) if item.get("id") and item.get("id") not in covered]
    if missing:
        limitations.append(f"No test case for finding{'s' if len(missing) != 1 else ''} {', '.join(missing)}.")
    return {
        "id": str(uuid4()), "scan_id": scan_id, "review_id": review["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "review_origin": review.get("source"), "cases": cases, "generator": generator, "limitations": limitations,
        "executed_by_shipsafe": False,
    }


class ResultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(min_length=1, max_length=20)
    status: str = Field(pattern="^(passed|failed|blocked|not_run)$")
    tester: str = Field(min_length=2, max_length=80)
    note: str | None = Field(default=None, max_length=1000)


def insert_suite(conn: sqlite3.Connection, suite: dict) -> None:
    conn.execute("INSERT INTO qc_test_suites (id, scan_id, review_id, created_at, suite_json) VALUES (?, ?, ?, ?, ?)",
                 (suite["id"], suite["scan_id"], suite["review_id"], suite["created_at"], json.dumps(suite)))


def insert_result(conn: sqlite3.Connection, suite_id: str, request: ResultRequest, tester: str) -> None:
    conn.execute(
        "INSERT INTO qc_test_results (id, suite_id, case_id, status, tester, note, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid4()), suite_id, request.case_id, request.status, tester, request.note,
         datetime.now(timezone.utc).isoformat()))


def served_suite(conn: sqlite3.Connection, suite: dict) -> dict:
    """A stored suite with each case's latest result and its history, plus counts."""
    rows = conn.execute(
        "SELECT case_id, status, tester, note, recorded_at FROM qc_test_results WHERE suite_id = ?"
        " ORDER BY recorded_at, rowid", (suite["id"],)).fetchall()
    history: dict[str, list[dict]] = {}
    for row in rows:
        history.setdefault(row["case_id"], []).append(
            {"status": row["status"], "tester": row["tester"], "note": row["note"], "recorded_at": row["recorded_at"]})
    cases = []
    for case in suite["cases"]:
        results = history.get(case["id"], [])
        cases.append({**case, "status": results[-1]["status"] if results else "not_run",
                      "result": results[-1] if results else None, "results": results})
    counts = {status: sum(1 for case in cases if case["status"] == status) for status in STATUSES}
    return {**suite, "cases": cases, "counts": counts, "total": len(cases)}


def suite_csv(suite: dict) -> str:
    """One row per case; columns a test management tool (Jira/Xray, TestRail, Excel) can import."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID", "Title", "Priority", "Area", "Finding", "File", "Preconditions", "Test data", "Steps",
                     "Expected result", "Bug title if it fails", "Status", "Tester", "Note"])
    for case in suite["cases"]:
        result = case.get("result") or {}
        writer.writerow([
            case["id"], _cell(case["title"]), case["priority"], _cell(case["area"]), case["finding_id"] or "", case["file"] or "",
            _cell("\n".join(case["preconditions"])), _cell("\n".join(case["test_data"])),
            _cell("\n".join(f"{index}. {step}" for index, step in enumerate(case["steps"], start=1))),
            _cell(case["expected"]), _cell(case["bug_title_if_fails"]), case["status"],
            _cell(result.get("tester") or ""), _cell(result.get("note") or ""),
        ])
    return out.getvalue()


def _cell(value: str) -> str:
    """Spreadsheet formula injection guard: a cell never starts with = + - @."""
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


def suite_markdown(suite: dict, scan: dict) -> str:
    counts = suite["counts"]
    lines = [
        f"# QC test cases — {scan.get('repo_name')} {scan.get('head_ref')}",
        "",
        f"- Scan: {suite['scan_id']} (head {scan.get('head_sha')})",
        f"- Written from AI review {suite['review_id']} by {suite['generator'].get('provider')} "
        f"{suite['generator'].get('model')} on {suite['created_at']}",
        f"- Status: {counts['passed']} passed · {counts['failed']} failed · {counts['blocked']} blocked · "
        f"{counts['not_run']} not run (of {suite['total']})",
        "- ShipSafe executed nothing; results are what testers recorded.",
        "",
    ]
    for case in suite["cases"]:
        lines += [f"## {case['id']} · {case['title']}", "",
                  f"**Priority:** {case['priority']} · **Area:** {case['area']} · **Finding:** {case['finding_id']} "
                  f"(`{case['file']}`) · **Status:** {case['status']}", ""]
        if case["preconditions"]:
            lines += ["**Preconditions**", ""] + [f"- {item}" for item in case["preconditions"]] + [""]
        if case["test_data"]:
            lines += ["**Test data**", ""] + [f"- {item}" for item in case["test_data"]] + [""]
        lines += ["**Steps**", ""] + [f"{index}. {step}" for index, step in enumerate(case["steps"], start=1)] + [""]
        lines += [f"**Expected:** {case['expected']}", "", f"**Bug title if it fails:** {case['bug_title_if_fails']}", ""]
        if case.get("result"):
            result = case["result"]
            lines += [f"_Recorded {result['status']} by {result['tester']} on {result['recorded_at']}"
                      f"{': ' + result['note'] if result.get('note') else ''}_", ""]
    lines += ["## Limitations", ""] + [f"- {item}" for item in suite["limitations"]]
    return "\n".join(lines) + "\n"
