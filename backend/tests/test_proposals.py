"""Phase 4 task B: migration 3, proposed tests as untrusted text, and explicit
human decisions. Nothing in this phase applies a proposal to a checkout or
runs it; several tests here exist to pin exactly that."""
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db, proposals
from app.demo_seed import ensure_demo_repo
from app.main import create_app
from app.proposals import MAX_PROPOSAL_BYTES, ProposalError, check_against_tree, validate_content, validate_target_path

V2 = db.MIGRATIONS[:2]
# The migration tests here are about migration 3 itself, so they stop there.
V3 = db.MIGRATIONS[:3]
GOOD_TEST = (
    "from app.auth import get_invoice_for_user\n\n\n"
    "def test_other_user_is_refused():\n"
    "    invoice = {'id': 'inv-1', 'owner_id': 'alice'}\n"
    "    assert get_invoice_for_user('mallory', invoice) is None\n"
)


def rows(db_file, sql, *args):
    conn = sqlite3.connect(db_file)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


# -- migration 3 --------------------------------------------------------------

def test_fresh_database_reaches_version_3_with_both_tables(tmp_path):
    db_file = tmp_path / "scans.db"
    assert db.migrate(db_file, V3) == 3
    tables = {name for (name,) in rows(db_file, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"scans", "ai_reviews", "test_proposals", "test_proposal_decisions"} <= tables
    assert [row[1] for row in rows(db_file, "PRAGMA table_info(test_proposals)")] == [
        "id", "scan_id", "created_at", "target_path", "content", "content_digest", "origin", "finding_ref", "rationale",
        "base_commit", "head_commit"]
    assert [row[1] for row in rows(db_file, "PRAGMA table_info(test_proposal_decisions)")] == [
        "id", "proposal_id", "decision", "decided_at", "decided_by", "note"]


def test_version_2_data_survives_migration_3_byte_for_byte_and_it_is_idempotent(tmp_path):
    db_file = tmp_path / "scans.db"
    assert db.migrate(db_file, V2) == 2
    with db.session(db_file) as conn:
        conn.execute(
            "INSERT INTO scans (id, created_at, report_json, provider, repository_id, pull_request_id, base_commit, head_commit, stale_at)"
            " VALUES ('s1', '2026-01-01T00:00:00+00:00', ?, 'bitbucket-cloud', 'acme/ledger', '7', ?, ?, '2026-01-02T00:00:00+00:00')",
            ('{"k":  "v"}', "a" * 40, "b" * 40))
        conn.execute("INSERT INTO ai_reviews VALUES ('r1', 's1', '2026-01-03T00:00:00+00:00', ?)", ('{"summary": "x"}',))
    before = (rows(db_file, "SELECT * FROM scans"), rows(db_file, "SELECT * FROM ai_reviews"))

    assert db.migrate(db_file, V3) == 3
    assert (rows(db_file, "SELECT * FROM scans"), rows(db_file, "SELECT * FROM ai_reviews")) == before
    assert rows(db_file, "SELECT COUNT(*) FROM test_proposals") == [(0,)]
    assert db.migrate(db_file, V3) == 3
    assert (rows(db_file, "SELECT * FROM scans"), rows(db_file, "SELECT * FROM ai_reviews")) == before


def test_migration_3_failure_rolls_back_to_version_2(tmp_path):
    db_file = tmp_path / "scans.db"
    db.migrate(db_file, V2)
    real = db.MIGRATIONS[2]
    broken = V2 + (db.Migration(3, real.description, real.statements + ("THIS IS NOT SQL",)),)
    with pytest.raises(sqlite3.OperationalError):
        db.migrate(db_file, broken)
    assert db.schema_version(db_file) == 2
    assert ("test_proposals",) not in rows(db_file, "SELECT name FROM sqlite_master WHERE type = 'table'")
    assert db.migrate(db_file, V3) == 3


def test_a_build_that_only_knows_version_2_refuses_a_version_3_database(tmp_path):
    db_file = tmp_path / "scans.db"
    db.migrate(db_file, V3)
    with pytest.raises(db.SchemaVersionError):
        db.migrate(db_file, V2)
    assert db.schema_version(db_file) == 3


def test_migration_3_only_adds(tmp_path):
    statements = " ".join(db.MIGRATIONS[2].statements).upper()
    assert not any(word in statements for word in ("DROP ", "DELETE ", "UPDATE ", "ALTER "))


# -- target path --------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "tests/test_refunds.py", "tests/unit/test_auth.py", "backend/tests/test_api.py", "test/pricing_test.py",
    "pkg/tests/sub-dir/test_a.b.py",
])
def test_plain_test_paths_inside_a_tests_directory_are_accepted(path):
    assert validate_target_path(path) == path


@pytest.mark.parametrize("path", [
    "", None, 7,
    "../tests/test_x.py", "tests/../../etc/test_x.py", "tests/./test_x.py", "tests//test_x.py", "tests/test_x.py/",
    "/tests/test_x.py", "/etc/tests/test_x.py", "~/tests/test_x.py",
    "C:/tests/test_x.py", "c:tests/test_x.py", "tests\\test_x.py", "..\\tests\\test_x.py", "file:///tests/test_x.py",
    "tests/test_x.py\x00.txt", "tests/test_\nx.py", "tests/test_x.py\r",
    "tests/.hidden/test_x.py", ".git/tests/test_x.py", "tests/.test_x.py", "tests/test_x.py.", "tests /test_x.py",
    "tests/con/test_x.py", "tests/NUL.d/test_x.py",
    "test_x.py", "app/test_x.py", "src/app/auth_test.py",                      # not inside a tests directory
    "tests/conftest.py", "tests/helpers.py", "tests/test_x.txt", "tests/test_x.py.txt", "tests/__init__.py",
    "tests/test_x.pyc", "app/auth.py", "tests/setup.py",
    "tests/" + "a" * 300 + "/test_x.py",
])
def test_unsafe_or_non_test_paths_are_refused(path):
    with pytest.raises(ProposalError):
        validate_target_path(path)


def test_paths_that_collide_with_the_tree_are_refused():
    tree = ["app/auth.py", "tests/test_smoke.py", "tests/linked", "vendor"]
    check_against_tree("tests/test_new.py", tree)
    check_against_tree("tests/unit/test_new.py", tree)
    with pytest.raises(ProposalError, match="already exists") as existing:
        check_against_tree("tests/test_smoke.py", tree)
    assert existing.value.status == 409
    # Git lists a symbolic link as a file: a directory of the target that is a file is a link (or a file).
    with pytest.raises(ProposalError, match="file or symbolic link"):
        check_against_tree("tests/linked/test_new.py", tree)
    with pytest.raises(ProposalError, match="file or symbolic link"):
        check_against_tree("vendor/tests/test_new.py", tree)


# -- content ------------------------------------------------------------------

def test_content_must_be_python_with_a_test_and_within_the_size_limit():
    assert validate_content(GOOD_TEST) == GOOD_TEST
    assert validate_content("class TestX:\n    def test_a(self):\n        assert True\n")
    for bad in ("", "   \n", None, "def test_(:\n", "x = 1\n", "def helper():\n    pass\n",
                "class Helper:\n    def test_a(self):\n        pass\n", "def test_a():\n    pass\n\x00"):
        with pytest.raises(ProposalError):
            validate_content(bad)
    with pytest.raises(ProposalError) as too_big:
        validate_content("def test_a():\n    pass\n" + "# pad\n" * MAX_PROPOSAL_BYTES)
    assert too_big.value.status == 413


def test_the_proposals_module_cannot_execute_or_write_files():
    import ast
    tree = ast.parse(Path(proposals.__file__).read_text(encoding="utf-8"))
    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not called & {"exec", "eval", "compile", "__import__", "open"}
    assert not imported & {"subprocess", "importlib", "runpy", "os", "shutil", "pathlib", "tempfile", "pytest"}


# -- API ----------------------------------------------------------------------

@pytest.fixture()
def demo(tmp_path):
    repo = tmp_path / "demo"
    db_file = tmp_path / "data" / "scans.db"
    app = create_app(demo_root=repo, db_file=db_file, allowed_root=repo)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        report = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/auth-regression"}).json()
        yield client, report, db_file, repo


def body(**change):
    return {"target_path": "tests/test_auth_regression.py", "content": GOOD_TEST, "origin": "human", **change}


def url(report, suffix=""):
    return f"/api/scans/{report['id']}/tests/proposals{suffix}"


def test_a_proposal_is_stored_as_text_bound_to_the_scans_commits_and_starts_pending(demo):
    client, report, db_file, repo = demo
    finding = report["findings"][0]["id"]
    created = client.post(url(report), json=body(finding_ref=finding, rationale="The ownership check was removed."))
    assert created.status_code == 201, created.text
    proposal = created.json()
    assert proposal["content"] == GOOD_TEST and proposal["target_path"] == "tests/test_auth_regression.py"
    assert (proposal["base_commit"], proposal["head_commit"]) == (report["binding"]["base_commit"], report["binding"]["head_commit"])
    assert len(proposal["head_commit"]) == 40 and len(proposal["content_digest"]) == 64
    assert proposal["status"] == "pending" and proposal["decisions"] == []
    assert proposal["eligible_to_run"] is False and proposal["applied"] is False and proposal["executed"] is False
    assert proposal["stale"] is False and proposal["finding_ref"] == finding and proposal["origin"] == "human"
    assert "not verified" in proposal["identity_note"]
    assert client.get(url(report)).json() == [proposal]
    # Nothing was written into the repository and its commits did not move.
    assert not (repo / "tests" / "test_auth_regression.py").exists()
    assert subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True).stdout == ""
    assert client.get(f"/api/scans/{report['id']}").json() == report
    assert rows(db_file, "SELECT COUNT(*) FROM test_proposals") == [(1,)]


@pytest.mark.parametrize("change,status", [
    ({"target_path": "../outside/tests/test_x.py"}, 422),
    ({"target_path": "tests/conftest.py"}, 422),
    ({"target_path": "app/auth.py"}, 422),
    ({"target_path": "C:/tests/test_x.py"}, 422),
    ({"target_path": "tests/test_smoke.py"}, 409),                 # exists at the scanned commit
    ({"target_path": "app/auth.py/tests/test_x.py"}, 409),         # a file where a directory is needed
    ({"content": "this is not python ("}, 422),
    ({"content": "import os\nos.system('echo hi')\n"}, 422),        # no test in it
    ({"origin": "claude"}, 422),
    ({"finding_ref": "made-up-finding"}, 409),
    ({"approved": True}, 422),
    ({"status": "approved"}, 422),
    ({"decisions": [{"decision": "approved", "decided_by": "x"}]}, 422),
])
def test_unacceptable_proposals_are_refused_and_leave_no_row(demo, change, status):
    client, report, db_file, _ = demo
    result = client.post(url(report), json=body(**change))
    assert result.status_code == status, result.text
    assert rows(db_file, "SELECT COUNT(*) FROM test_proposals") == [(0,)]
    assert client.get(url(report)).json() == []


def test_oversized_and_malformed_requests_are_refused(demo):
    client, report, db_file, _ = demo
    headers = {"Content-Type": "application/json"}
    huge = json.dumps(body(content="def test_a():\n    pass\n" + "#" * (2 * MAX_PROPOSAL_BYTES)))
    assert client.post(url(report), content=huge, headers=headers).status_code == 413
    assert client.post(url(report), content=b"not json", headers=headers).status_code == 422
    assert client.post(url(report), json=["a", "list"]).status_code == 422
    assert rows(db_file, "SELECT COUNT(*) FROM test_proposals") == [(0,)]


def test_the_same_proposal_twice_is_refused_but_a_different_path_or_content_is_not(demo):
    client, report, _, _ = demo
    assert client.post(url(report), json=body()).status_code == 201
    assert client.post(url(report), json=body()).status_code == 409
    assert client.post(url(report), json=body(target_path="tests/test_other.py")).status_code == 201
    assert client.post(url(report), json=body(content=GOOD_TEST + "\n# variant\n")).status_code == 201
    assert len(client.get(url(report)).json()) == 3


def test_a_hostile_proposal_is_stored_but_never_run_or_written(demo, tmp_path, monkeypatch):
    client, report, _, repo = demo
    marker = tmp_path / "executed"
    hostile = f"open({str(marker)!r}, 'w').write('x')\nimport os\nos.system('echo pwned')\n\ndef test_evil():\n    assert True\n"
    calls = []
    real_run = subprocess.run
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (calls.append(a[0]), real_run(*a, **k))[1])
    monkeypatch.setattr(os, "system", lambda *_a: (_ for _ in ()).throw(AssertionError("os.system must not be called")))

    created = client.post(url(report), json=body(content=hostile, target_path="tests/test_evil.py"))
    assert created.status_code == 201, created.text
    approved = client.post(url(report, f"/{created.json()['id']}/decisions"), json={"decision": "approved", "decided_by": "Nour"})
    assert approved.status_code == 201 and approved.json()["eligible_to_run"] is True
    assert approved.json()["applied"] is False and approved.json()["executed"] is False

    assert not marker.exists() and not (repo / "tests" / "test_evil.py").exists()
    # The only processes started are read-only git commands; never python or pytest.
    assert calls and all(command[0] == "git" for command in calls)
    assert not any(word in command for command in calls for word in ("apply", "commit", "checkout", "am", "pytest", "python"))


# -- decisions ----------------------------------------------------------------

def decide(client, report, proposal, **request):
    return client.post(url(report, f"/{proposal['id']}/decisions"), json=request)


def test_approval_is_explicit_named_and_recorded_and_history_is_append_only(demo):
    client, report, db_file, _ = demo
    proposal = client.post(url(report), json=body()).json()

    first = decide(client, report, proposal, decision="rejected", decided_by="  Nour   Waled ", note="Needs a clearer name.")
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "rejected" and first.json()["eligible_to_run"] is False
    assert first.json()["decisions"][0]["decided_by"] == "Nour Waled"

    second = decide(client, report, proposal, decision="approved", decided_by="Nour Waled").json()
    assert second["status"] == "approved" and second["eligible_to_run"] is True
    assert [item["decision"] for item in second["decisions"]] == ["rejected", "approved"]  # oldest first, nothing rewritten
    assert second["decisions"][0] == first.json()["decisions"][0]
    assert second["decisions"][0]["decided_at"] <= second["decisions"][1]["decided_at"]
    assert second["applied"] is False and second["executed"] is False

    third = decide(client, report, proposal, decision="rejected", decided_by="Someone Else").json()
    assert third["status"] == "rejected" and third["eligible_to_run"] is False and len(third["decisions"]) == 3
    assert rows(db_file, "SELECT COUNT(*) FROM test_proposal_decisions") == [(3,)]
    assert client.get(url(report)).json()[0] == third
    # The proposal row itself is never modified by a decision.
    assert rows(db_file, "SELECT content, target_path FROM test_proposals") == [(GOOD_TEST, "tests/test_auth_regression.py")]


@pytest.mark.parametrize("request_body,status", [
    ({"decision": "approved"}, 422),                                  # a name is required
    ({"decision": "approved", "decided_by": ""}, 422),
    ({"decision": "approved", "decided_by": " "}, 422),
    ({"decision": "approved", "decided_by": "x"}, 422),
    ({"decision": "approved", "decided_by": "Nour\x07"}, 422),
    ({"decision": "maybe", "decided_by": "Nour"}, 422),
    ({"decision": "approved", "decided_by": "Nour", "run": True}, 422),
    ({"decided_by": "Nour"}, 422),
])
def test_a_decision_needs_a_valid_choice_and_a_name(demo, request_body, status):
    client, report, db_file, _ = demo
    proposal = client.post(url(report), json=body()).json()
    assert decide(client, report, proposal, **request_body).status_code == status
    assert rows(db_file, "SELECT COUNT(*) FROM test_proposal_decisions") == [(0,)]
    assert client.get(url(report)).json()[0]["status"] == "pending"


def test_decisions_are_scoped_to_the_scan_and_unknown_ids_are_404(demo):
    client, report, _, _ = demo
    proposal = client.post(url(report), json=body()).json()
    other = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/pricing-regression"}).json()
    request = {"decision": "approved", "decided_by": "Nour"}
    assert client.post(url(other, f"/{proposal['id']}/decisions"), json=request).status_code == 404
    assert client.post(url(report, "/no-such-proposal/decisions"), json=request).status_code == 404
    unknown = "12345678-1111-2222-3333-444444444444"
    assert client.get(f"/api/scans/{unknown}/tests/proposals").status_code == 404
    assert client.post(f"/api/scans/{unknown}/tests/proposals", json=body()).status_code == 404
    assert client.get(url(other)).json() == [] and client.get(url(report)).json()[0]["status"] == "pending"


def test_a_stale_scan_takes_no_new_proposal_or_approval_and_approved_ones_stop_being_eligible(demo):
    client, report, db_file, _ = demo
    pending = client.post(url(report), json=body()).json()
    approved = client.post(url(report), json=body(target_path="tests/test_second.py")).json()
    assert decide(client, report, approved, decision="approved", decided_by="Nour").json()["eligible_to_run"] is True

    with db.session(db_file) as conn:  # what happens when a pull request's head is seen to have moved
        conn.execute("UPDATE scans SET stale_at = '2026-11-13T10:00:00+00:00' WHERE id = ?", (report["id"],))

    listed = {item["id"]: item for item in client.get(url(report)).json()}
    assert listed[approved["id"]]["status"] == "approved" and listed[approved["id"]]["stale"] is True
    assert listed[approved["id"]]["eligible_to_run"] is False       # approved, but for commits that are no longer current
    assert listed[pending["id"]]["stale"] is True and listed[pending["id"]]["eligible_to_run"] is False

    refused = decide(client, report, pending, decision="approved", decided_by="Nour")
    assert refused.status_code == 409 and "stale" in refused.json()["detail"]
    assert decide(client, report, pending, decision="rejected", decided_by="Nour").status_code == 201  # rejecting is still possible
    assert client.post(url(report), json=body(target_path="tests/test_third.py")).status_code == 409
    assert len(listed[approved["id"]]["decisions"]) == 1  # history kept


def test_a_scan_without_commits_takes_no_proposal(tmp_path):
    repo = tmp_path / "demo"
    ensure_demo_repo(repo)
    db_file = tmp_path / "scans.db"
    db.migrate(db_file)
    with db.session(db_file) as conn:  # a row from before migration 2: not commit-bound
        conn.execute("INSERT INTO scans (id, created_at, report_json) VALUES ('12345678-aaaa-bbbb-cccc-444444444444', '2026-01-01T00:00:00+00:00', ?)",
                     (json.dumps({"id": "12345678-aaaa-bbbb-cccc-444444444444", "files": [], "findings": [], "repository_path": str(repo)}),))
    with TestClient(create_app(demo_root=repo, db_file=db_file), base_url="http://127.0.0.1") as client:
        refused = client.post("/api/scans/12345678-aaaa-bbbb-cccc-444444444444/tests/proposals", json=body())
    assert refused.status_code == 409 and "not bound to exact commits" in refused.json()["detail"]
