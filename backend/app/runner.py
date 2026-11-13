"""Phase 4 task C: the test-runner boundary. Fails closed.

This build contains **no code that executes a test**. A runner here can only
say whether isolated execution is available; the only implementation says it
is not. A run request is therefore recorded as BLOCKED, with the reason and
without any log, exit code or result, because there is none.

Executing tests on the machine that runs ShipSafe is not an option this module
offers. A real runner must be a separate, verified, resource-limited sandbox
(see prompts/PHASE-04-REGRESSION-TESTS.md, section C) and is added only after
its isolation has been proven with controlled tests.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

EXECUTION_UNAVAILABLE = "execution_unavailable"
NO_RUNNER_REASON = (
    "No verified isolated test runner is configured. ShipSafe never runs repository tests on its own host, "
    "so nothing was executed."
)
NO_ENGINE_REASON = (
    "A runner reported itself available, but this build of ShipSafe contains no execution engine. "
    "Nothing was executed."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Runner(Protocol):
    """What ShipSafe needs to know about a runner before asking it for anything."""

    name: str

    def availability(self) -> dict:
        """``{"available": bool, "status": str, "runner": str, "reason": str, "checked_at": iso}``."""


class UnavailableRunner:
    """The only runner in this build: isolated execution is not available."""

    name = "none"

    def availability(self) -> dict:
        return {"available": False, "status": EXECUTION_UNAVAILABLE, "runner": self.name,
                "reason": NO_RUNNER_REASON, "checked_at": _now()}


def blocked_reason(runner: Runner) -> tuple[dict, str]:
    """The runner's answer and why a run cannot happen. There is no path that returns "go"."""
    try:
        answer = runner.availability()
    except Exception as exc:  # a broken runner is an unavailable runner
        answer = {"available": False, "status": EXECUTION_UNAVAILABLE, "runner": getattr(runner, "name", "unknown"),
                  "reason": f"The runner could not report its availability ({type(exc).__name__}). Nothing was executed.",
                  "checked_at": _now()}
    if answer.get("available") is True:
        return answer, NO_ENGINE_REASON
    return answer, str(answer.get("reason") or NO_RUNNER_REASON)


RUN_COLUMNS = ("id, proposal_id, scan_id, requested_at, requested_by, status, reason, runner, base_commit, head_commit,"
               " started_at, finished_at, exit_code, output")


def record_blocked_run(
    conn: sqlite3.Connection, *, proposal_id: str, scan_id: str, requested_by: str, reason: str, runner_name: str,
    base_commit: str, head_commit: str,
) -> str:
    """Store a run request that did not run. Start, end, exit code and output stay NULL: nothing happened."""
    run_id = str(uuid4())
    conn.execute(
        "INSERT INTO test_runs (id, proposal_id, scan_id, requested_at, requested_by, status, reason, runner,"
        " base_commit, head_commit) VALUES (?, ?, ?, ?, ?, 'blocked', ?, ?, ?, ?)",
        (run_id, proposal_id, scan_id, _now(), requested_by, reason, runner_name, base_commit, head_commit),
    )
    return run_id


def served_run(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "proposal_id": row["proposal_id"], "scan_id": row["scan_id"],
        "requested_at": row["requested_at"], "requested_by": row["requested_by"],
        "status": row["status"], "reason": row["reason"], "runner": row["runner"],
        "base_commit": row["base_commit"], "head_commit": row["head_commit"],
        "started_at": row["started_at"], "finished_at": row["finished_at"],
        "exit_code": row["exit_code"], "output": row["output"],
        "executed": row["started_at"] is not None,
    }


def runs_of(conn: sqlite3.Connection, proposal_id: str) -> list[dict]:
    rows = conn.execute(
        f"SELECT {RUN_COLUMNS} FROM test_runs WHERE proposal_id = ? ORDER BY requested_at DESC, rowid DESC LIMIT 50",
        (proposal_id,),
    ).fetchall()
    return [served_run(row) for row in rows]
