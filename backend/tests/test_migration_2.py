"""Phase 2 task 3: migration 2 (provider, repository, pull request, full
commit SHAs, stale marker) and the storage helpers that use it.

No Bitbucket request is made; pull request identifiers here are plain data.
"""
from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import db
from app.demo_seed import ensure_demo_repo
from app.main import create_app
from app.scanner import git, scan_repository

V1 = db.MIGRATIONS[:1]
OLD_COLUMNS = ["id", "created_at", "report_json"]
NEW_COLUMNS = ["provider", "repository_id", "pull_request_id", "base_commit", "head_commit", "stale_at"]
SHA_A, SHA_B, SHA_C = "a" * 40, "b" * 40, "c" * 40
PR = {"provider": "bitbucket-cloud", "repository_id": "acme/ledger", "pull_request_id": "7"}


@pytest.fixture()
def demo(tmp_path):
    repo = tmp_path / "demo"
    ensure_demo_repo(repo)
    return repo


def query(db_file, sql, *args):
    conn = sqlite3.connect(db_file)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def columns(db_file, table="scans"):
    return [row[1] for row in query(db_file, f"PRAGMA table_info({table})")]


def v1_database_with_history(tmp_path, demo):
    """A version-1 database holding a real scan and an imported review."""
    db_file = tmp_path / "data" / "scans.db"
    assert db.migrate(db_file, V1) == 1
    report = scan_repository(demo, "main", "feature/release-candidate")
    with db.session(db_file) as conn:
        conn.execute("INSERT INTO scans VALUES (?, ?, ?)", (report["id"], report["created_at"], json.dumps(report)))
        conn.execute("INSERT INTO scans VALUES ('legacy', '2026-01-01T00:00:00+00:00', ?)", ('{"k":  "v"}',))
        conn.execute("INSERT INTO ai_reviews VALUES ('r1', ?, '2026-01-02T00:00:00+00:00', ?)", (report["id"], '{"summary": "x"}'))
    return db_file, report


def stored(db_file):
    return (query(db_file, "SELECT id, created_at, report_json FROM scans ORDER BY id"),
            query(db_file, "SELECT * FROM ai_reviews ORDER BY id"))


# -- the migration itself ----------------------------------------------------

def test_fresh_database_reaches_version_2_with_the_new_columns(tmp_path):
    db_file = tmp_path / "scans.db"
    assert db.migrate(db_file) == db.LATEST_VERSION == 2
    assert columns(db_file) == OLD_COLUMNS + NEW_COLUMNS
    assert ("idx_scans_pull_request",) in query(db_file, "SELECT name FROM sqlite_master WHERE type = 'index'")


def test_version_1_rows_survive_migration_2_byte_for_byte(tmp_path, demo):
    db_file, _report = v1_database_with_history(tmp_path, demo)
    before = stored(db_file)
    assert columns(db_file) == OLD_COLUMNS

    assert db.migrate(db_file) == 2

    assert stored(db_file) == before
    assert columns(db_file, "ai_reviews") == ["id", "scan_id", "imported_at", "review_json"]
    # Old rows are local scans that are not commit-bound, and not stale.
    assert query(db_file, "SELECT DISTINCT provider, repository_id, pull_request_id, base_commit, head_commit, stale_at FROM scans") == [
        ("local-git", None, None, None, None, None)
    ]
    assert db.migrate(db_file) == 2  # idempotent
    assert stored(db_file) == before


def test_v0_2_database_goes_straight_to_version_2_and_stays_usable_through_the_api(tmp_path, demo):
    db_file, report = v1_database_with_history(tmp_path, demo)
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA user_version = 0")  # exactly what a v0.2 build leaves behind
    conn.commit()
    conn.close()
    before = stored(db_file)

    with TestClient(create_app(demo_root=demo, db_file=db_file), base_url="http://127.0.0.1") as client:
        # A row from before migration 2 is served with an empty binding beside the unchanged report.
        legacy = {"provider": "local-git", "repository_id": None, "pull_request_id": None, "base_commit": None,
                  "head_commit": None, "comparison": "direct", "stale": False, "stale_at": None, "stale_checked": False}
        assert client.get(f"/api/scans/{report['id']}").json() == {**report, "binding": legacy}
        assert client.get(f"/api/scans/{report['id']}/export").json() == {**report, "binding": legacy}
        assert client.get(f"/api/scans/{report['id']}/ai/handoff").status_code == 200
        assert client.get(f"/api/scans/{report['id']}/ai/reviews").json() == [{"summary": "x"}]
        assert client.get(f"/api/scans/{report['id']}/ai/reviews/latest").json() == {"summary": "x"}
    assert db.schema_version(db_file) == 2
    assert stored(db_file) == before


def test_migration_2_failure_rolls_back_to_version_1(tmp_path, demo):
    db_file, _report = v1_database_with_history(tmp_path, demo)
    before = stored(db_file)
    real = db.MIGRATIONS[1]
    broken = V1 + (db.Migration(2, real.description, real.statements + ("THIS IS NOT SQL",)),)
    with pytest.raises(sqlite3.OperationalError):
        db.migrate(db_file, broken)
    assert db.schema_version(db_file) == 1
    assert columns(db_file) == OLD_COLUMNS
    assert stored(db_file) == before
    assert db.migrate(db_file) == 2  # the real migration still applies afterwards
    assert stored(db_file) == before


def test_database_newer_than_version_2_is_still_refused(tmp_path):
    db_file = tmp_path / "scans.db"
    db.migrate(db_file)
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()
    with pytest.raises(db.SchemaVersionError):
        db.migrate(db_file)
    assert db.schema_version(db_file) == 3


def test_a_build_that_only_knows_version_1_refuses_a_version_2_database(tmp_path):
    db_file = tmp_path / "scans.db"
    db.migrate(db_file)
    with pytest.raises(db.SchemaVersionError):
        db.migrate(db_file, V1)
    assert columns(db_file) == OLD_COLUMNS + NEW_COLUMNS


# -- local scans fill the new columns ----------------------------------------

def test_local_scan_is_stored_with_provider_repository_and_full_shas(tmp_path, demo):
    db_file = tmp_path / "scans.db"
    with TestClient(create_app(demo_root=demo, db_file=db_file), base_url="http://127.0.0.1") as client:
        report = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/auth-regression"}).json()
        assert client.get(f"/api/scans/{report['id']}").json() == report
    base = git(demo, "rev-parse", "main").strip()
    head = git(demo, "rev-parse", "feature/auth-regression").strip()
    assert query(db_file, "SELECT provider, repository_id, pull_request_id, base_commit, head_commit, stale_at FROM scans") == [
        ("local-git", str(demo.resolve()), None, base, head, None)
    ]
    assert len(base) == len(head) == 40
    assert (report["base_sha"], report["head_sha"]) == (base[:12], head[:12])
    stored_report = json.loads(query(db_file, "SELECT report_json FROM scans")[0][0])
    assert stored_report == {key: value for key, value in report.items() if key != "binding"}  # binding is not stored in the report


# -- storage helpers ---------------------------------------------------------

def scan(scan_id, created="2026-11-12T10:00:00+00:00"):
    return {"id": scan_id, "created_at": created, "summary": {}}


def test_insert_scan_stores_the_report_as_given_beside_its_binding(tmp_path):
    db_file = tmp_path / "scans.db"
    db.migrate(db_file)
    with db.session(db_file) as conn:
        db.insert_scan(conn, scan("s1"), **PR, base_commit=SHA_A, head_commit=SHA_B)
        db.insert_scan(conn, scan("s2"))
    assert query(db_file, "SELECT * FROM scans ORDER BY id") == [
        ("s1", "2026-11-12T10:00:00+00:00", json.dumps(scan("s1")), "bitbucket-cloud", "acme/ledger", "7", SHA_A, SHA_B, None),
        ("s2", "2026-11-12T10:00:00+00:00", json.dumps(scan("s2")), "local-git", None, None, None, None, None),
    ]


@pytest.mark.parametrize("bad", ["main", SHA_A[:12], SHA_A.upper(), SHA_A + "0", ""])
def test_insert_scan_refuses_anything_but_a_full_commit_sha(tmp_path, bad):
    db_file = tmp_path / "scans.db"
    db.migrate(db_file)
    for binding in ({"base_commit": bad, "head_commit": SHA_B}, {"base_commit": SHA_A, "head_commit": bad}):
        with pytest.raises(ValueError), db.session(db_file) as conn:
            db.insert_scan(conn, scan("s1"), **PR, **binding)
    assert query(db_file, "SELECT COUNT(*) FROM scans") == [(0,)]


def stale(db_file):
    return dict(query(db_file, "SELECT id, stale_at FROM scans"))


def pull_request_history(tmp_path):
    db_file = tmp_path / "scans.db"
    db.migrate(db_file)
    with db.session(db_file) as conn:
        db.insert_scan(conn, scan("old-head"), **PR, base_commit=SHA_A, head_commit=SHA_B)
        db.insert_scan(conn, scan("new-head"), **PR, base_commit=SHA_A, head_commit=SHA_C)
        db.insert_scan(conn, scan("other-pr"), **{**PR, "pull_request_id": "8"}, base_commit=SHA_A, head_commit=SHA_B)
        db.insert_scan(conn, scan("other-repo"), **{**PR, "repository_id": "acme/billing"}, base_commit=SHA_A, head_commit=SHA_B)
        db.insert_scan(conn, scan("other-provider"), **{**PR, "provider": "local-git"}, base_commit=SHA_A, head_commit=SHA_B)
        db.insert_scan(conn, scan("unbound"), **PR)
    return db_file


def test_sync_stale_marks_only_scans_of_that_pull_request_with_a_different_head(tmp_path):
    db_file = pull_request_history(tmp_path)
    reports = query(db_file, "SELECT id, report_json FROM scans ORDER BY id")
    with db.session(db_file) as conn:
        marked = db.sync_stale(conn, **PR, current_head=SHA_C, observed_at="2026-11-12T12:00:00+00:00")
    assert marked == 1
    assert stale(db_file) == {
        "old-head": "2026-11-12T12:00:00+00:00", "new-head": None,
        "other-pr": None, "other-repo": None, "other-provider": None, "unbound": None,
    }
    assert query(db_file, "SELECT id, report_json FROM scans ORDER BY id") == reports


def test_sync_stale_keeps_the_first_observation_time(tmp_path):
    db_file = pull_request_history(tmp_path)
    with db.session(db_file) as conn:
        db.sync_stale(conn, **PR, current_head=SHA_C, observed_at="2026-11-12T12:00:00+00:00")
        assert db.sync_stale(conn, **PR, current_head=SHA_C, observed_at="2026-11-13T09:00:00+00:00") == 0
    assert stale(db_file)["old-head"] == "2026-11-12T12:00:00+00:00"


def test_sync_stale_clears_the_marker_when_the_head_returns_to_the_scanned_commit(tmp_path):
    db_file = pull_request_history(tmp_path)
    with db.session(db_file) as conn:
        db.sync_stale(conn, **PR, current_head=SHA_C, observed_at="2026-11-12T12:00:00+00:00")
        marked = db.sync_stale(conn, **PR, current_head=SHA_B, observed_at="2026-11-12T13:00:00+00:00")
    assert marked == 1
    assert (stale(db_file)["old-head"], stale(db_file)["new-head"]) == (None, "2026-11-12T13:00:00+00:00")


def test_sync_stale_refuses_an_abbreviated_head(tmp_path):
    db_file = pull_request_history(tmp_path)
    with pytest.raises(ValueError), db.session(db_file) as conn:
        db.sync_stale(conn, **PR, current_head=SHA_C[:12], observed_at="2026-11-12T12:00:00+00:00")
    assert set(stale(db_file).values()) == {None}
