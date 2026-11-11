import subprocess

import pytest
from fastapi.testclient import TestClient

from app.demo_seed import ensure_demo_repo
from app.main import create_app
from app.scanner import scan_repository, ScanError


@pytest.fixture()
def demo(tmp_path):
    path = tmp_path / "demo"
    ensure_demo_repo(path)
    return path


def test_real_git_repo_has_six_demo_branches(demo):
    branches = subprocess.check_output(["git", "-C", str(demo), "branch", "--list"], text=True)
    assert "feature/release-candidate" in branches
    assert "feature/docs-only" in branches
    assert "feature/safe-cleanup" in branches


def test_release_candidate_flags_three_distinct_risks(demo):
    report = scan_repository(demo, "main", "feature/release-candidate")
    assert report["summary"]["files_changed"] == 4
    assert report["summary"]["finding_count"] == 3
    assert {finding["category"] for finding in report["findings"]} == {
        "Security", "Data integrity", "API contract"
    }
    assert report["summary"]["recommendation"] == "Critical review required"
    assert report["affected_modules"]
    assert report["summary"]["test_status"] == "not_run"
    assert all(f["status"] == "suspected" for f in report["findings"])


@pytest.mark.parametrize("branch,expected", [
    ("feature/auth-regression", "Security"),
    ("feature/pricing-regression", "Data integrity"),
    ("feature/api-breaking", "API contract"),
])
def test_individual_risks(demo, branch, expected):
    report = scan_repository(demo, "main", branch)
    assert [f["category"] for f in report["findings"]] == [expected]


@pytest.mark.parametrize("branch", ["feature/docs-only", "feature/safe-cleanup"])
def test_harmless_changes_are_not_high_risk(demo, branch):
    report = scan_repository(demo, "main", branch)
    assert report["summary"]["finding_count"] == 0
    assert report["summary"]["risk_score"] <= 5


def test_git_refs_must_exist(demo):
    with pytest.raises(ScanError):
        scan_repository(demo, "main", "feature/not-real")


def test_git_ref_injection_is_rejected(demo):
    with pytest.raises(ScanError):
        scan_repository(demo, "main", "--output=/tmp/wrong")


def test_api_persists_scan_and_exports_json(tmp_path):
    root = tmp_path / "demo"
    app = create_app(demo_root=root, db_file=tmp_path / "db" / "scans.db", allowed_root=root)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        demo = client.get("/api/demo").json()
        assert len(demo["branches"]) == 6
        scanned = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/release-candidate"})
        assert scanned.status_code == 201, scanned.text
        report = scanned.json()
        assert report["summary"]["finding_count"] == 3
        assert len(client.get("/api/scans").json()) == 1
        assert client.get(f"/api/scans/{report['id']}").json()["id"] == report["id"]
        exported = client.get(f"/api/scans/{report['id']}/export")
        assert exported.status_code == 200
        assert exported.json()["id"] == report["id"]
        assert "attachment" in exported.headers["content-disposition"]


def test_path_outside_allowlist_is_rejected(tmp_path):
    root = tmp_path / "demo"
    app = create_app(demo_root=root, db_file=tmp_path / "scans.db", allowed_root=root)
    with TestClient(app) as client:
        response = client.post("/api/scans", json={"repository_path": str(tmp_path / "outside")})
        assert response.status_code == 403
