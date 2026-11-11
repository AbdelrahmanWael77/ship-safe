"""Phase 1 regression and baseline-verification tests.

Each test in the "regressions" section failed against the unmodified v0.2
baseline (commit 10f3cee) and documents a fixed defect. Tests in the
"baseline verification" section passed before and after; they pin behaviour
the Phase 1 gate requires us to preserve.

Everything here uses synthetic repositories created under pytest's tmp_path.
No repository code is executed.
"""
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.scanner import ScanError, scan_repository


def run_git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True, encoding="utf-8", timeout=30,
    ).stdout.strip()


def make_repo(path, base_files, head_files, head_branch="feature/change"):
    """Create a two-branch synthetic repository: main, plus one change branch."""
    path.mkdir(parents=True, exist_ok=True)
    run_git(path, "init", "-b", "main")
    run_git(path, "config", "user.name", "ShipSafe Test")
    run_git(path, "config", "user.email", "test@shipsafe.invalid")
    run_git(path, "config", "core.autocrlf", "false")
    for name, content in base_files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "base")
    run_git(path, "checkout", "-b", head_branch)
    for name, content in head_files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
    run_git(path, "add", ".")
    run_git(path, "commit", "-m", "change")
    run_git(path, "checkout", "main")
    return path


@pytest.fixture()
def api(tmp_path):
    root = tmp_path / "demo"
    app = create_app(demo_root=root, db_file=tmp_path / "data" / "scans.db", allowed_root=root)
    with TestClient(app) as client:
        yield client, root


def scan_and_handoff(client):
    report = client.post("/api/scans", json={}).json()
    context = client.get(f"/api/scans/{report['id']}/ai/context").json()
    return report, context["context_digest"]


def review_body(report, digest, **overrides):
    body = {
        "schema_version": "shipsafe.ai-review.v1",
        "scan_id": report["id"],
        "context_digest": digest,
        "summary": "Static review of the supplied diff; nothing was executed.",
        "recommendation": "manual_review",
        "findings": [],
        "test_ideas": [],
        "limitations": ["No tests were executed."],
    }
    body.update(overrides)
    return body


# --------------------------------------------------------------------------
# Regressions: failed on the v0.2 baseline
# --------------------------------------------------------------------------

def test_utf8_source_is_decoded_as_utf8_regardless_of_locale(tmp_path):
    # U+00DD encodes to C3 9D; byte 9D is undefined in Windows cp1252, so
    # locale-default decoding of Git output crashed or produced mojibake.
    repo = make_repo(
        tmp_path / "r",
        {"app/names.py": "LABEL = 'plain'\n"},
        {"app/names.py": "LABEL = 'Ýr — café'\n"},
    )
    report = scan_repository(repo, "main", "feature/change")
    assert "Ýr — café" in report["files"][0]["diff"]


def test_non_ascii_file_names_keep_their_diff_and_counts(tmp_path):
    # Git C-quotes such paths by default ("caf\303\251.py"), which made the
    # per-file diff empty and the line counts zero.
    repo = make_repo(
        tmp_path / "r",
        {"app/café.py": "def total():\n    return 1\n"},
        {"app/café.py": "def total():\n    return 2\n"},
    )
    report = scan_repository(repo, "main", "feature/change")
    changed = report["files"][0]
    assert changed["path"] == "app/café.py"
    assert (changed["additions"], changed["deletions"]) == (1, 1)
    assert "+    return 2" in changed["diff"]
    assert changed["changed_functions"] == ["total"]


def test_repository_configured_textconv_command_is_never_executed(tmp_path):
    # A scanned repository's own .git/config must not be able to make the
    # scanner run a command (diff.<driver>.textconv is run by `git diff`).
    marker = tmp_path / "executed.marker"
    repo = make_repo(
        tmp_path / "r",
        {"app/a.py": "x = 1\n", ".gitattributes": "*.py diff=evil\n"},
        {"app/a.py": "x = 2\n"},
    )
    run_git(repo, "config", "diff.evil.textconv", f"touch '{marker.as_posix()}'; cat")
    report = scan_repository(repo, "main", "feature/change")
    assert report["summary"]["files_changed"] == 1
    assert not marker.exists(), "scanner executed a repository-configured command"


def test_pathologically_nested_python_does_not_crash_the_scan(tmp_path):
    deep = "x = " + "(" * 5000 + "1" + ")" * 5000 + "\n"
    chain = "y = " + " + ".join(["1"] * 60000) + "\n"
    repo = make_repo(
        tmp_path / "r",
        {"app/api.py": "x = 1\n", "app/other.py": "import app.api\n"},
        {"app/api.py": deep + chain, "app/other.py": "import app.api\n" + chain},
    )
    report = scan_repository(repo, "main", "feature/change")
    assert report["summary"]["files_changed"] == 2


@pytest.mark.parametrize("bad_path", ["bad\x00path", "~no-such-shipsafe-user-xyz/repo"])
def test_unresolvable_repository_path_is_a_client_error(api, bad_path):
    client, _ = api
    response = client.post("/api/scans", json={"repository_path": bad_path})
    assert response.status_code in (400, 403), response.text
    assert client.get("/api/scans").json() == []


def test_demo_scan_still_works_when_another_root_is_authorized(tmp_path):
    # Authorising a workspace used to lock out the synthetic demo repository,
    # so the dashboard's default scan returned 403.
    demo, workspace = tmp_path / "demo", tmp_path / "workspace"
    workspace.mkdir()
    app = create_app(demo_root=demo, db_file=tmp_path / "scans.db", allowed_root=workspace)
    with TestClient(app) as client:
        default = client.post("/api/scans", json={})
        assert default.status_code == 201, default.text
        explicit = client.post("/api/scans", json={"repository_path": str(demo)})
        assert explicit.status_code == 201, explicit.text
        outside = client.post("/api/scans", json={"repository_path": str(tmp_path / "elsewhere")})
        assert outside.status_code == 403


def test_deeply_nested_review_json_is_rejected_not_a_server_error(api):
    client, _ = api
    report, _ = scan_and_handoff(client)
    url = f"/api/scans/{report['id']}/ai/reviews"
    payload = b"[" * 100_000 + b"]" * 100_000
    response = client.post(url, content=payload, headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
    assert client.get(url).json() == []


def test_missing_ref_error_names_the_ref(api):
    client, _ = api
    response = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/not-real"})
    assert response.status_code == 400
    assert "feature/not-real" in response.json()["detail"]


def _refs(repo):
    out = run_git(repo, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads")
    return dict(line.split() for line in out.splitlines())


def test_interrupted_demo_seed_is_repaired_on_next_start(tmp_path):
    """Seen on a workstation: Ctrl+C during the first API start left ``.git``
    plus two branches, and every later start accepted the broken repository."""
    from app.demo_seed import BAD_AUTH, DEMO_BRANCH_FILES, ensure_demo_repo

    repo = ensure_demo_repo(tmp_path / "demo")
    before = _refs(repo)
    # Reproduce the interrupted state: four branches never created, one branch
    # created with its change staged but not committed.
    for branch in list(DEMO_BRANCH_FILES)[2:]:
        run_git(repo, "branch", "-D", branch)
    run_git(repo, "checkout", "-q", "-B", "feature/auth-regression", "main")
    (repo / "app" / "auth.py").write_text(BAD_AUTH, encoding="utf-8")
    run_git(repo, "add", ".")
    assert set(_refs(repo)) == {"main", "feature/release-candidate", "feature/auth-regression"}

    ensure_demo_repo(repo)

    after = _refs(repo)
    assert set(after) == set(before)
    assert after["main"] == before["main"]
    assert after["feature/release-candidate"] == before["feature/release-candidate"]
    assert all(after[b] != after["main"] for b in DEMO_BRANCH_FILES), "every demo branch carries its commit"
    assert run_git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert run_git(repo, "status", "--porcelain") == ""
    report = scan_repository(repo, "main", "feature/auth-regression")
    assert [f["path"] for f in report["files"]] == ["app/auth.py"]


def test_demo_seed_interrupted_before_the_first_commit_is_completed(tmp_path):
    from app.demo_seed import DEMO_BRANCH_FILES, ensure_demo_repo

    repo = tmp_path / "demo"
    repo.mkdir()
    run_git(repo, "init", "-b", "main")
    ensure_demo_repo(repo)
    assert set(_refs(repo)) == {"main", *DEMO_BRANCH_FILES}


def test_complete_demo_repository_is_not_modified_by_a_restart(tmp_path):
    from app.demo_seed import ensure_demo_repo

    repo = ensure_demo_repo(tmp_path / "demo")
    before = _refs(repo)
    ensure_demo_repo(repo)
    assert _refs(repo) == before


def test_demo_seed_refuses_to_write_into_a_repository_it_did_not_generate(tmp_path):
    from app.demo_seed import ensure_demo_repo
    from app.errors import ConfigError

    repo = make_repo(tmp_path / "theirs", {"notes.md": "mine\n"}, {"notes.md": "edited\n"})
    before = _refs(repo)
    with pytest.raises(ConfigError):
        ensure_demo_repo(repo)
    assert _refs(repo) == before
    assert run_git(repo, "status", "--porcelain") == ""


def test_demo_seed_refuses_a_non_empty_directory_that_is_not_a_repository(tmp_path):
    from app.demo_seed import ensure_demo_repo
    from app.errors import ConfigError

    folder = tmp_path / "stuff"
    folder.mkdir()
    (folder / "keep.txt").write_text("do not commit me\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        ensure_demo_repo(folder)
    assert not (folder / ".git").exists()


# --------------------------------------------------------------------------
# Baseline verification: behaviour Phase 1 must preserve
# --------------------------------------------------------------------------

def test_release_candidate_scan_uses_real_commits_and_shows_changed_lines(api):
    client, root = api
    report = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/release-candidate"}).json()
    assert run_git(root, "rev-parse", "main").startswith(report["base_sha"])
    assert run_git(root, "rev-parse", "feature/release-candidate").startswith(report["head_sha"])
    assert report["base_sha"] != report["head_sha"]
    auth = next(f for f in report["files"] if f["path"] == "app/auth.py")
    assert '-    if invoice["owner_id"] != user_id:' in auth["diff"]
    assert "+    # Regression: ownership verification was accidentally removed." in auth["diff"]
    assert auth["changed_functions"] == ["get_invoice_for_user"]
    assert (auth["additions"], auth["deletions"]) == (1, 2)


def test_docs_only_branch_reports_no_findings_through_the_api(api):
    client, _ = api
    report = client.post("/api/scans", json={"base_ref": "main", "head_ref": "feature/docs-only"}).json()
    assert [f["path"] for f in report["files"]] == ["README.md"]
    assert report["findings"] == []
    assert report["test_suggestions"] == []
    assert report["summary"]["risk_score"] <= 5
    assert "Updated setup documentation." in report["files"][0]["diff"]


def test_identical_refs_report_no_changes(api):
    client, _ = api
    report = client.post("/api/scans", json={"base_ref": "main", "head_ref": "main"}).json()
    assert report["summary"]["files_changed"] == 0
    assert report["summary"]["recommendation"] == "No changes detected"


def test_scans_and_reviews_survive_an_application_restart(tmp_path):
    root, db_file = tmp_path / "demo", tmp_path / "data" / "scans.db"
    with TestClient(create_app(demo_root=root, db_file=db_file, allowed_root=root)) as client:
        report, digest = scan_and_handoff(client)
        saved = client.post(f"/api/scans/{report['id']}/ai/reviews", json=review_body(report, digest))
        assert saved.status_code == 201, saved.text
    with TestClient(create_app(demo_root=root, db_file=db_file, allowed_root=root)) as client:
        assert [row["id"] for row in client.get("/api/scans").json()] == [report["id"]]
        assert client.get(f"/api/scans/{report['id']}").json() == report
        assert client.get(f"/api/scans/{report['id']}/ai/context").json()["context_digest"] == digest
        assert client.get(f"/api/scans/{report['id']}/ai/reviews/latest").json()["id"] == saved.json()["id"]


@pytest.mark.parametrize("body,status", [
    ({"base_ref": ""}, 422),
    ({"head_ref": "x" * 151}, 422),
    ({"repository_path": "p" * 1025}, 422),
    ({"base_ref": 7}, 422),
    ({"head_ref": "main..feature/docs-only"}, 400),
    ({"head_ref": "main; rm -rf x"}, 400),
    ({"head_ref": "-n"}, 400),
])
def test_invalid_scan_input_is_rejected_without_persisting(api, body, status):
    client, _ = api
    assert client.post("/api/scans", json=body).status_code == status
    assert client.get("/api/scans").json() == []


def test_path_inside_allowlist_that_is_not_a_repository_is_a_client_error(api):
    client, root = api
    (root / "plain-folder").mkdir()
    for candidate in (root / "plain-folder", root / "does-not-exist"):
        response = client.post("/api/scans", json={"repository_path": str(candidate)})
        assert response.status_code == 400, response.text


def test_traversal_out_of_the_allowlist_is_rejected(api):
    client, root = api
    response = client.post("/api/scans", json={"repository_path": str(root / ".." / "demo-sibling")})
    assert response.status_code == 403


def test_review_with_unencodable_text_is_rejected_and_history_stays_readable(api):
    # A stored lone UTF-16 surrogate would make every later read of this
    # scan's review list fail while encoding the response.
    client, _ = api
    report, digest = scan_and_handoff(client)
    url = f"/api/scans/{report['id']}/ai/reviews"
    raw = (
        '{"schema_version":"shipsafe.ai-review.v1","scan_id":"%s","context_digest":"%s",'
        '"summary":"Lone surrogate \\ud800 inside an otherwise valid summary.",'
        '"recommendation":"manual_review","findings":[],"test_ideas":[],'
        '"limitations":["No tests were executed."]}' % (report["id"], digest)
    ).encode("ascii")
    response = client.post(url, content=raw, headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
    assert client.get(url).status_code == 200
    assert client.get(url).json() == []


def test_non_json_and_non_object_review_bodies_are_rejected(api):
    client, _ = api
    report, _ = scan_and_handoff(client)
    url = f"/api/scans/{report['id']}/ai/reviews"
    for payload in (b"not json", b"[]", b'"text"', b"\xff\xfe", b""):
        response = client.post(url, content=payload, headers={"Content-Type": "application/json"})
        assert response.status_code == 422, (payload, response.text)


def test_unknown_scan_ids_return_404(api):
    client, _ = api
    for path in ("/api/scans/nope", "/api/scans/nope/export", "/api/scans/nope/ai/context", "/api/scans/nope/ai/reviews/latest"):
        assert client.get(path).status_code == 404


def test_scan_does_not_modify_the_scanned_repository(api):
    client, root = api
    before = (run_git(root, "rev-parse", "HEAD"), run_git(root, "status", "--porcelain"), run_git(root, "for-each-ref"))
    client.post("/api/scans", json={})
    after = (run_git(root, "rev-parse", "HEAD"), run_git(root, "status", "--porcelain"), run_git(root, "for-each-ref"))
    assert before == after


def test_direct_scanner_rejects_a_non_repository(tmp_path):
    with pytest.raises(ScanError):
        scan_repository(tmp_path, "main", "main")
