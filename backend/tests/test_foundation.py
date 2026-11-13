"""Phase 1 groundwork: provider contracts, configuration, and migrations."""
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import load_settings
from app.demo_seed import ensure_demo_repo
from app.errors import ConfigError, RefNotFound, RepositoryAccessDenied, RepositoryNotFound, ScanError
from app.main import create_app
from app.providers import (
    ChangeProvider, ChangeSet, FileDelta, LocalGitProvider, PullRequestProvider,
    PullRequestRef, RepositoryProvider, RepositoryRef,
)
from app.scanner import scan_changes, scan_repository

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def demo(tmp_path):
    return ensure_demo_repo(tmp_path / "workspace" / "demo")


# -- provider contracts ------------------------------------------------------

def test_local_provider_satisfies_the_repository_and_change_contracts(demo):
    provider = LocalGitProvider([demo])
    assert isinstance(provider, RepositoryProvider)
    assert isinstance(provider, ChangeProvider)
    # Honest status: there is no pull-request source in Phase 1.
    assert not isinstance(provider, PullRequestProvider)


def test_local_discovery_lists_only_repositories_under_allowed_roots(demo, tmp_path):
    workspace = demo.parent
    (workspace / "not-a-repo").mkdir()
    ensure_demo_repo(tmp_path / "outside")
    found = LocalGitProvider([workspace]).list_repositories()
    assert [(r.provider, r.name, r.id, r.default_branch) for r in found] == [("local-git", "demo", str(demo), "main")]
    assert LocalGitProvider([demo]).list_repositories()[0].id == str(demo)


def test_local_provider_enforces_the_allowlist_before_anything_else(demo, tmp_path):
    provider = LocalGitProvider([demo])
    outside = ensure_demo_repo(tmp_path / "outside")
    with pytest.raises(RepositoryAccessDenied):
        provider.get_repository(str(outside))
    with pytest.raises(RepositoryAccessDenied):
        provider.get_repository(str(demo / ".." / ".." / "outside"))
    with pytest.raises(RepositoryNotFound):
        provider.get_repository(str(demo / "app"))


def test_change_set_carries_full_shas_and_untruncated_patches(demo):
    provider = LocalGitProvider([demo])
    repository = provider.get_repository(str(demo))
    changes = provider.get_changes(repository, "main", "feature/release-candidate")
    assert len(changes.base_sha) == len(changes.head_sha) == 40
    assert changes.base_sha == provider.resolve_commit(repository, "main")
    # A commit SHA is itself a valid ref, so a scan can be pinned to one.
    assert provider.resolve_commit(repository, changes.head_sha) == changes.head_sha
    assert [f.path for f in changes.files] == ["README.md", "app/api.py", "app/auth.py", "app/pricing.py"]
    assert all(f.status == "M" and f.patch.startswith("diff --git") for f in changes.files)
    assert not changes.truncated
    json.dumps(asdict(changes))  # contract: JSON-serialisable as-is

    limited = provider.get_changes(repository, "main", "feature/release-candidate", max_files=1)
    assert len(limited.files) == 1 and limited.truncated

    assert "app/orders.py" in provider.list_files(repository, changes.head_sha)
    assert "PermissionError" in provider.read_file(repository, changes.base_sha, "app/auth.py")
    assert provider.read_file(repository, changes.head_sha, "no/such/file.py") == ""
    with pytest.raises(RefNotFound):
        provider.resolve_commit(repository, "feature/not-real")
    with pytest.raises(ScanError):
        provider.resolve_commit(repository, "--upload-pack=x")


class InMemoryProvider:
    """A stand-in for a hosted provider: no Git, no filesystem, no network."""

    name = "in-memory"
    repo = RepositoryRef(provider="in-memory", id="team/ledger", name="ledger", location="memory://team/ledger")
    trees = {
        "a" * 40: {"svc/auth.py": "def read(user, doc):\n    require_role(user)\n    return doc\n"},
        "b" * 40: {"svc/auth.py": "def read(user, doc):\n    return doc\n", "svc/view.py": "from svc.auth import read\n"},
    }
    refs = {"main": "a" * 40, "pr-7": "b" * 40}

    def list_repositories(self):
        return [self.repo]

    def get_repository(self, repository_id):
        if repository_id != self.repo.id:
            raise RepositoryNotFound("unknown repository")
        return self.repo

    def list_pull_requests(self, repository, state="open"):
        return [PullRequestRef(
            provider=self.name, repository_id=repository.id, id="7", title="Simplify read", state="open",
            source_ref="pr-7", target_ref="main", source_sha="b" * 40, target_sha="a" * 40,
        )]

    def get_pull_request(self, repository, pull_request_id):
        return self.list_pull_requests(repository)[0]

    def resolve_commit(self, repository, ref):
        return self.refs.get(ref, ref)

    def get_changes(self, repository, base_ref, head_ref, *, max_files=300):
        patch = "--- a/svc/auth.py\n+++ b/svc/auth.py\n@@ -1,3 +1,2 @@\n def read(user, doc):\n-    require_role(user)\n     return doc\n"
        return ChangeSet(
            repository=repository, base_ref=base_ref, head_ref=head_ref,
            base_sha=self.resolve_commit(repository, base_ref), head_sha=self.resolve_commit(repository, head_ref),
            files=(FileDelta(path="svc/auth.py", status="M", additions=0, deletions=1, patch=patch),),
        )

    def list_files(self, repository, commit):
        return sorted(self.trees[commit])

    def read_file(self, repository, commit, path):
        return self.trees[commit].get(path, "")


def test_scan_orchestration_works_with_a_non_git_provider(demo):
    provider = InMemoryProvider()
    assert isinstance(provider, RepositoryProvider)
    assert isinstance(provider, PullRequestProvider)
    assert isinstance(provider, ChangeProvider)
    repository = provider.get_repository("team/ledger")
    pull_request = provider.list_pull_requests(repository)[0]

    report = scan_changes(provider, repository, pull_request.target_sha, pull_request.source_sha)

    assert (report["base_sha"], report["head_sha"]) == ("a" * 12, "b" * 12)
    assert [f["category"] for f in report["findings"]] == ["Security"]
    assert report["files"][0]["changed_functions"] == ["read"]
    assert report["affected_modules"] == [{"path": "svc/view.py", "imports_changed": ["svc.auth"]}]
    assert report["repository_path"] == "memory://team/ledger"
    # Same report shape whichever provider supplied the changes.
    assert report.keys() == scan_repository(demo, "main", "feature/auth-regression").keys()


def test_report_shape_matches_the_published_v0_2_example(demo):
    example = json.loads((REPO_ROOT / "docs" / "example-scan-report.json").read_text(encoding="utf-8"))
    report = scan_repository(demo, "main", "feature/release-candidate")
    assert list(report) == list(example)
    assert list(report["summary"]) == list(example["summary"])
    assert list(report["files"][0]) == list(example["files"][0])
    assert list(report["findings"][0]) == list(example["findings"][0])
    assert report["summary"] == {**example["summary"]}
    assert len(report["base_sha"]) == len(example["base_sha"]) == 12


# -- configuration -----------------------------------------------------------

def test_default_settings_authorize_only_the_demo_repository():
    settings = load_settings(env={})
    assert settings.allowed_roots == (settings.demo_dir,)
    assert settings.demo_dir.name == "demo-repo"
    assert settings.db_path.name == "scans.db"


def test_empty_environment_values_do_not_widen_the_allowlist(tmp_path):
    settings = load_settings(env={"SHIPSAFE_ALLOWED_ROOT": "", "SHIPSAFE_DEMO_DIR": str(tmp_path / "d"), "SHIPSAFE_DB_PATH": ""})
    assert settings.allowed_roots == (tmp_path / "d",)


def test_configured_root_is_added_alongside_the_demo_repository(tmp_path):
    settings = load_settings(env={"SHIPSAFE_ALLOWED_ROOT": str(tmp_path / "ws"), "SHIPSAFE_DEMO_DIR": str(tmp_path / "d")})
    assert settings.allowed_roots == (tmp_path / "d", tmp_path / "ws")


def test_filesystem_root_is_refused_as_an_allowlist(tmp_path):
    with pytest.raises(ConfigError):
        load_settings(env={"SHIPSAFE_ALLOWED_ROOT": Path(tmp_path.anchor).as_posix()})


def test_cors_is_limited_to_the_local_dashboard(tmp_path):
    app = create_app(demo_root=tmp_path / "demo", db_file=tmp_path / "scans.db")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        allowed = client.options("/api/scans", headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "POST"})
        assert allowed.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
        denied = client.options("/api/scans", headers={"Origin": "https://example.invalid", "Access-Control-Request-Method": "POST"})
        assert "access-control-allow-origin" not in denied.headers


# -- migrations --------------------------------------------------------------

V0_2_SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, report_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_reviews (id TEXT PRIMARY KEY, scan_id TEXT NOT NULL, imported_at TEXT NOT NULL,
    review_json TEXT NOT NULL, FOREIGN KEY(scan_id) REFERENCES scans(id));
CREATE INDEX IF NOT EXISTS idx_ai_reviews_scan ON ai_reviews(scan_id, imported_at);
"""


def rows(db_file):
    conn = sqlite3.connect(db_file)
    try:
        return conn.execute("SELECT id, created_at, report_json FROM scans ORDER BY id").fetchall()
    finally:
        conn.close()


def test_existing_v0_2_database_is_adopted_without_touching_history(tmp_path, demo):
    db_file = tmp_path / "data" / "scans.db"
    db_file.parent.mkdir()
    report = scan_repository(demo, "main", "feature/release-candidate")
    conn = sqlite3.connect(db_file)
    conn.executescript(V0_2_SCHEMA)
    conn.execute("INSERT INTO scans VALUES (?, ?, ?)", (report["id"], report["created_at"], json.dumps(report)))
    conn.commit()
    conn.close()
    before = rows(db_file)
    assert db.schema_version(db_file) == 0

    with TestClient(create_app(demo_root=demo, db_file=db_file), base_url="http://127.0.0.1") as client:
        served = client.get(f"/api/scans/{report['id']}").json()
        # Since Phase 2 task 4 the API adds "binding" beside the stored report.
        assert served.pop("binding")["provider"] == "local-git"
        assert served == report
        assert client.get(f"/api/scans/{report['id']}/ai/handoff").status_code == 200

    assert db.schema_version(db_file) == db.LATEST_VERSION
    assert rows(db_file) == before
    assert db.migrate(db_file) == db.LATEST_VERSION  # idempotent
    assert rows(db_file) == before


def test_database_from_a_newer_build_is_refused_and_left_untouched(tmp_path):
    db_file = tmp_path / "scans.db"
    db.migrate(db_file)
    conn = sqlite3.connect(db_file)
    conn.execute("INSERT INTO scans (id, created_at, report_json) VALUES ('s1', '2026-01-01T00:00:00+00:00', '{}')")
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()
    with pytest.raises(db.SchemaVersionError):
        db.migrate(db_file)
    assert db.schema_version(db_file) == 99
    assert [row[0] for row in rows(db_file)] == ["s1"]


def test_failed_migration_rolls_back_completely(tmp_path):
    db_file = tmp_path / "scans.db"
    baseline = db.MIGRATIONS[:1]  # version 1; the real migration 2 is covered in test_migration_2.py
    db.migrate(db_file, baseline)
    broken = baseline + (db.Migration(2, "broken", (
        "ALTER TABLE scans ADD COLUMN provider TEXT",
        "THIS IS NOT SQL",
    )),)
    with pytest.raises(sqlite3.OperationalError):
        db.migrate(db_file, broken)
    assert db.schema_version(db_file) == 1
    conn = sqlite3.connect(db_file)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(scans)")]
    conn.close()
    assert columns == ["id", "created_at", "report_json"]


def test_additive_migration_preserves_rows(tmp_path):
    db_file = tmp_path / "scans.db"
    db.migrate(db_file)
    with db.session(db_file) as conn:
        conn.execute("INSERT INTO scans (id, created_at, report_json) VALUES ('s1', '2026-01-01T00:00:00+00:00', '{}')")
    following = db.LATEST_VERSION + 1
    additive = db.MIGRATIONS + (db.Migration(following, "example additive column", ("ALTER TABLE scans ADD COLUMN example TEXT",)),)
    assert db.migrate(db_file, additive) == following
    assert [row[0] for row in rows(db_file)] == ["s1"]
