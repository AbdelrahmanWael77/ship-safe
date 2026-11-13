"""Phase 4 task C: the runner boundary fails closed. A run request is checked,
refused and recorded as BLOCKED; nothing is executed and no log, exit code or
pass/fail result is ever invented. These tests never run a repository test."""
import ast
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, runner as runner_module
from app.main import create_app
from app.runner import EXECUTION_UNAVAILABLE, UnavailableRunner, blocked_reason

V3 = db.MIGRATIONS[:3]
TEST = "def test_other_user_is_refused():\n    assert True\n"
NAME = {"requested_by": "Nour Waled"}


def rows(db_file, sql, *args):
    conn = sqlite3.connect(db_file)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


# -- migration 4 --------------------------------------------------------------

def test_fresh_database_reaches_version_4_with_test_runs(tmp_path):
    db_file = tmp_path / "scans.db"
    assert db.migrate(db_file) == db.LATEST_VERSION >= 4
    assert [row[1] for row in rows(db_file, "PRAGMA table_info(test_runs)")] == [
        "id", "proposal_id", "scan_id", "requested_at", "requested_by", "status", "reason", "runner", "base_commit",
        "head_commit", "started_at", "finished_at", "exit_code", "output"]
    statements = " ".join(db.MIGRATIONS[3].statements).upper()
    assert not any(word in statements for word in ("DROP ", "DELETE ", "UPDATE ", "ALTER "))


def test_version_3_data_survives_migration_4_and_failure_rolls_back(tmp_path):
    db_file = tmp_path / "scans.db"
    assert db.migrate(db_file, V3) == 3
    with db.session(db_file) as conn:
        conn.execute("INSERT INTO scans (id, created_at, report_json, base_commit, head_commit) VALUES ('s1', 't', '{}', ?, ?)", ("a" * 40, "b" * 40))
        conn.execute("INSERT INTO test_proposals VALUES ('p1', 's1', 't', 'tests/test_x.py', 'c', 'd', 'human', NULL, NULL, ?, ?)", ("a" * 40, "b" * 40))
        conn.execute("INSERT INTO test_proposal_decisions VALUES ('d1', 'p1', 'approved', 't', 'Nour', NULL)")
    tables = ("scans", "test_proposals", "test_proposal_decisions")
    before = [rows(db_file, f"SELECT * FROM {table}") for table in tables]

    real = db.MIGRATIONS[3]
    with pytest.raises(sqlite3.OperationalError):
        db.migrate(db_file, V3 + (db.Migration(4, real.description, real.statements + ("THIS IS NOT SQL",)),))
    assert db.schema_version(db_file) == 3
    assert ("test_runs",) not in rows(db_file, "SELECT name FROM sqlite_master WHERE type = 'table'")

    assert db.migrate(db_file, db.MIGRATIONS[:4]) == 4 and db.migrate(db_file, db.MIGRATIONS[:4]) == 4
    assert [rows(db_file, f"SELECT * FROM {table}") for table in tables] == before
    with pytest.raises(db.SchemaVersionError):
        db.migrate(db_file, V3)  # a build that only knows version 3 refuses this database


# -- the runner itself --------------------------------------------------------

def test_the_only_runner_says_execution_is_unavailable():
    answer = UnavailableRunner().availability()
    assert answer["available"] is False and answer["status"] == EXECUTION_UNAVAILABLE == "execution_unavailable"
    assert answer["runner"] == "none" and "never runs repository tests on its own host" in answer["reason"]
    assert blocked_reason(UnavailableRunner())[1] == answer["reason"]


def test_a_runner_that_claims_to_be_available_or_breaks_is_still_blocked():
    class Claims:
        name = "claims"

        def availability(self):
            return {"available": True, "status": "ready", "runner": "claims", "reason": "", "checked_at": "now"}

    class Breaks:
        name = "breaks"

        def availability(self):
            raise RuntimeError("boom")

    assert "no execution engine" in blocked_reason(Claims())[1]
    answer, reason = blocked_reason(Breaks())
    assert answer["available"] is False and "RuntimeError" in reason and "Nothing was executed" in reason


def test_the_runner_module_contains_no_way_to_execute_anything():
    tree = ast.parse(Path(runner_module.__file__).read_text(encoding="utf-8"))
    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    called |= {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not called & {"exec", "eval", "compile", "__import__", "open", "run", "Popen", "system", "call", "check_output"}
    assert not imported & {"subprocess", "importlib", "runpy", "os", "shutil", "pathlib", "tempfile", "pytest", "docker", "multiprocessing"}


# -- API ----------------------------------------------------------------------

@pytest.fixture()
def demo(tmp_path):
    repo = tmp_path / "demo"
    db_file = tmp_path / "data" / "scans.db"
    app = create_app(demo_root=repo, db_file=db_file, allowed_root=tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        report = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/auth-regression"}).json()
        yield client, report, db_file, repo


def propose(client, report, approve=True, path="tests/test_auth_regression.py"):
    proposal = client.post(f"/api/scans/{report['id']}/tests/proposals", json={"target_path": path, "content": TEST, "origin": "human"}).json()
    if approve:
        proposal = client.post(f"/api/scans/{report['id']}/tests/proposals/{proposal['id']}/decisions",
                               json={"decision": "approved", "decided_by": "Nour Waled"}).json()
    return proposal


def runs_url(report, proposal):
    return f"/api/scans/{report['id']}/tests/proposals/{proposal['id']}/runs"


def test_runner_status_route_reports_unavailable(demo):
    client, _, _, _ = demo
    status = client.get("/api/tests/runner").json()
    assert status["available"] is False and status["status"] == "execution_unavailable" and status["runner"] == "none"


def test_an_approved_run_request_is_recorded_as_blocked_with_no_output_and_starts_no_process(demo, monkeypatch, tmp_path):
    client, report, db_file, repo = demo
    marker = tmp_path / "executed"
    hostile = f"open({str(marker)!r}, 'w').write('x')\n\ndef test_evil():\n    assert True\n"
    proposal = client.post(f"/api/scans/{report['id']}/tests/proposals", json={"target_path": "tests/test_evil.py", "content": hostile, "origin": "human"}).json()
    client.post(f"/api/scans/{report['id']}/tests/proposals/{proposal['id']}/decisions", json={"decision": "approved", "decided_by": "Nour Waled"})

    def forbidden(*_args, **_kwargs):
        raise AssertionError("a run request must not start a process")

    for name in ("run", "Popen", "call", "check_output"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    blocked = client.post(runs_url(report, proposal), json=NAME)
    monkeypatch.undo()

    assert blocked.status_code == 503, blocked.text
    body = blocked.json()
    assert body["code"] == "execution_unavailable" and "nothing was executed" in body["detail"].lower()
    run = body["run"]
    assert run["status"] == "blocked" and run["executed"] is False and run["runner"] == "none"
    assert run["started_at"] is None and run["finished_at"] is None and run["exit_code"] is None and run["output"] is None
    assert run["requested_by"] == "Nour Waled" and run["reason"] == body["detail"]
    assert (run["base_commit"], run["head_commit"]) == (report["binding"]["base_commit"], report["binding"]["head_commit"])
    assert not any(key in run for key in ("passed", "failed", "result", "verdict", "tests"))
    assert not marker.exists() and not (repo / "tests" / "test_evil.py").exists()

    assert client.get(runs_url(report, proposal)).json() == [run]
    again = client.post(runs_url(report, proposal), json=NAME).json()["run"]
    assert [item["id"] for item in client.get(runs_url(report, proposal)).json()] == [again["id"], run["id"]]  # history kept
    assert rows(db_file, "SELECT status, started_at, finished_at, exit_code, output FROM test_runs") == [("blocked", None, None, None, None)] * 2
    assert client.get(f"/api/scans/{report['id']}").json()["summary"]["test_status"] == "not_run"


def test_refusals_come_before_the_runner_and_record_nothing(demo):
    client, report, db_file, _ = demo
    pending = propose(client, report, approve=False)
    refused = client.post(runs_url(report, pending), json=NAME)
    assert refused.status_code == 409 and "'pending', not 'approved'" in refused.json()["detail"]

    client.post(f"/api/scans/{report['id']}/tests/proposals/{pending['id']}/decisions", json={"decision": "rejected", "decided_by": "Nour"})
    assert client.post(runs_url(report, pending), json=NAME).status_code == 409

    assert client.post(f"/api/scans/{report['id']}/tests/proposals/nope/runs", json=NAME).status_code == 404
    assert client.get(f"/api/scans/{report['id']}/tests/proposals/nope/runs").status_code == 404
    assert client.post("/api/scans/12345678-1111-2222-3333-444444444444/tests/proposals/x/runs", json=NAME).status_code == 404

    approved = propose(client, report, path="tests/test_second.py")
    for bad in ({}, {"requested_by": ""}, {"requested_by": "x"}, {"requested_by": "Nour", "force": True}, {"requested_by": "Nour\x07"}):
        assert client.post(runs_url(report, approved), json=bad).status_code == 422, bad

    with db.session(db_file) as conn:  # the pull request's head moved
        conn.execute("UPDATE scans SET stale_at = '2026-11-13T10:00:00+00:00' WHERE id = ?", (report["id"],))
    stale = client.post(runs_url(report, approved), json=NAME)
    assert stale.status_code == 409 and "stale" in stale.json()["detail"]
    assert rows(db_file, "SELECT COUNT(*) FROM test_runs") == [(0,)]


def test_only_the_synthetic_demo_repository_may_even_request_a_run(demo, tmp_path):
    client, _, db_file, _ = demo
    other = tmp_path / "other"
    shutil.copytree(tmp_path / "demo", other)
    report = client.post("/api/scans", json={"repository_path": str(other), "base_ref": "main", "head_ref": "feature/auth-regression"}).json()
    proposal = propose(client, report)
    refused = client.post(runs_url(report, proposal), json=NAME)
    assert refused.status_code == 403 and "synthetic demo repository" in refused.json()["detail"]
    assert rows(db_file, "SELECT COUNT(*) FROM test_runs") == [(0,)]


def test_a_runner_claiming_availability_still_cannot_make_anything_run(tmp_path):
    class Claims:
        name = "claims"

        def availability(self):
            return {"available": True, "status": "ready", "runner": "claims", "reason": "", "checked_at": "now"}

    repo = tmp_path / "demo"
    app = create_app(demo_root=repo, db_file=tmp_path / "scans.db", allowed_root=repo, runner=Claims())
    with TestClient(app, base_url="http://127.0.0.1") as client:
        report = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/auth-regression"}).json()
        proposal = propose(client, report)
        status = client.get("/api/tests/runner").json()
        assert status["available"] is False and status["status"] == "execution_unavailable"
        blocked = client.post(runs_url(report, proposal), json=NAME)
        assert blocked.status_code == 503 and "no execution engine" in blocked.json()["detail"]
        assert blocked.json()["run"]["status"] == "blocked" and blocked.json()["run"]["runner"] == "claims"
        assert blocked.json()["run"]["executed"] is False
