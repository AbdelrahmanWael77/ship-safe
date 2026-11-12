"""Regression tests for the Phase 1 remediation findings (A1, B1-B5).

Each test documents the behaviour observed on f8967bc before the fix.
"""
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.demo_seed import BASE_FILES, DEMO_BRANCH_FILES, DEMO_MARKER, INITIAL_COMMIT_SUBJECT, ensure_demo_repo
from app.errors import ConfigError, RepositoryAccessDenied, RepositoryNotFound
from app.main import LOOPBACK_HOSTS, create_app
from app.ai_handoff import handoff_payload
from app.providers import LocalGitProvider
from app.providers.base import MAX_CHANGED_FILES
from app.scanner import PATCH_PREVIEW_LINES, scan_changes


@pytest.fixture()
def client(tmp_path):
    root = ensure_demo_repo(tmp_path / "demo")
    app = create_app(demo_root=root, db_file=tmp_path / "data" / "scans.db", allowed_root=root)
    # The Host check (A1) refuses Starlette's default "testserver" host, as it should.
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


# -- A1: Host header validation (DNS rebinding) ------------------------------

@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.1:8000", "localhost", "localhost:8000", "[::1]", "[::1]:8000"])
def test_loopback_hosts_are_served(client, host):
    assert client.get("/api/health", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", [
    "attacker.example", "attacker.example:8000", "127.0.0.1.attacker.example", "localhost.attacker.example", "",
])
def test_non_loopback_hosts_are_refused_before_any_route_runs(client, host):
    # On f8967bc every one of these returned 200 and could create scans.
    assert client.get("/api/demo", headers={"Host": host}).status_code == 400
    response = client.post(
        "/api/scans", json={"base_ref": "main", "head_ref": "feature/docs-only"},
        headers={"Host": host, "Origin": "http://attacker.example"},
    )
    assert response.status_code == 400
    # Nothing was stored.
    assert client.get("/api/scans").json() == []


def test_browser_cors_from_the_dashboard_origin_still_works(client):
    preflight = client.options(
        "/api/scans", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"
    denied = client.options(
        "/api/scans", headers={"Origin": "http://attacker.example", "Access-Control-Request-Method": "POST"},
    )
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


def test_loopback_host_list_contains_no_wildcard():
    assert "*" not in LOOPBACK_HOSTS and all("." in h or h in ("localhost", "[::1]") for h in LOOPBACK_HOSTS)


# -- B5: the demo directory gets the same drive-root check as the allowlist --

def _drive_root(tmp_path: Path) -> str:
    return tmp_path.anchor  # "C:\\" on Windows, "/" elsewhere


def test_demo_dir_may_not_be_a_drive_root(tmp_path):
    # On f8967bc this was accepted and made the whole drive an allowed root.
    with pytest.raises(ConfigError, match="SHIPSAFE_DEMO_DIR must not be a filesystem or drive root"):
        load_settings({"SHIPSAFE_DEMO_DIR": _drive_root(tmp_path)})
    with pytest.raises(ConfigError, match="SHIPSAFE_DEMO_DIR"):
        load_settings({}, demo_root=Path(_drive_root(tmp_path)))


def test_allowed_root_drive_root_check_is_unchanged(tmp_path):
    with pytest.raises(ConfigError, match="SHIPSAFE_ALLOWED_ROOT must not be a filesystem or drive root"):
        load_settings({"SHIPSAFE_ALLOWED_ROOT": _drive_root(tmp_path)}, demo_root=tmp_path / "demo")


def test_ordinary_demo_and_allowed_roots_still_load(tmp_path):
    settings = load_settings({}, demo_root=tmp_path / "demo", allowed_root=tmp_path / "work")
    assert settings.allowed_roots == ((tmp_path / "demo").resolve(), (tmp_path / "work").resolve())


# -- B1: file names are never read as Git pathspec magic or globs -------------

# Names a clone made on Linux can carry. Windows refuses to check most of them
# out, so the tree is written with plumbing commands instead of a worktree.
HOSTILE_NAMES = ["*", "*.py", "?.py", "[a].py", ":!a.py", "::y.py", ":(top)z.py", "-rf.py", "a.py", "y.py", "z.py", "normal.py"]


def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], input=stdin, capture_output=True, text=True,
        check=True, encoding="utf-8",
    ).stdout.strip()


def _commit_tree(repo: Path, version: str, parent: str | None = None) -> str:
    entries = []
    for name in HOSTILE_NAMES:
        blob = _git(repo, "hash-object", "-w", "--stdin", stdin=f"{version} {name}\n")
        entries.append(f"100644 blob {blob}\t{name}")
    tree = _git(repo, "mktree", "-z", stdin="\0".join(entries) + "\0")
    args = ["commit-tree", tree, "-m", version] + (["-p", parent] if parent else [])
    return _git(repo, *args)


@pytest.fixture()
def hostile_names_repo(tmp_path):
    repo = tmp_path / "hostile"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    for key, value in (("user.name", "t"), ("user.email", "t@t.invalid"), ("commit.gpgsign", "false")):
        _git(repo, "config", key, value)
    base = _commit_tree(repo, "v1")
    head = _commit_tree(repo, "v2", parent=base)
    _git(repo, "update-ref", "refs/heads/base", base)
    _git(repo, "update-ref", "refs/heads/main", head)
    return repo


def test_each_file_patch_covers_exactly_that_file(hostile_names_repo):
    # On f8967bc the patch for "*" contained every file, ":!a.py" contained
    # every file except a.py, and "[a].py" also contained a.py's lines.
    provider = LocalGitProvider([hostile_names_repo])
    repo = provider.get_repository(str(hostile_names_repo))
    report = scan_changes(provider, repo, "base", "main")
    assert sorted(f["path"] for f in report["files"]) == sorted(HOSTILE_NAMES)
    for entry in report["files"]:
        added = [line[1:] for line in entry["diff"].splitlines() if line.startswith("+v2 ")]
        assert added == [f"v2 {entry['path']}"], entry["path"]
        assert (entry["additions"], entry["deletions"]) == (1, 1), entry["path"]
    assert report["summary"]["lines_added"] == len(HOSTILE_NAMES)


def test_scan_does_not_run_commands_named_in_the_repository_config(hostile_names_repo, tmp_path):
    # Belt and braces for defect 2: arm the config keys that can name a
    # command and assert none runs during a scan. Each would create a marker.
    markers = tmp_path / "markers"
    markers.mkdir()
    repo = hostile_names_repo

    def weapon(name: str) -> str:
        script = tmp_path / f"{name}.sh"
        script.write_text(f"#!/bin/sh\n: > '{(markers / name).as_posix()}'\ncat\n")
        return script.as_posix()

    hooks = tmp_path / "hooks"
    hooks.mkdir()
    for hook in ("post-checkout", "pre-commit", "post-index-change", "reference-transaction"):
        (hooks / hook).write_text(f"#!/bin/sh\n: > '{(markers / ('hook-' + hook)).as_posix()}'\n")
    for key, value in {
        "core.fsmonitor": weapon("fsmonitor"), "diff.external": weapon("diff-external"),
        "diff.h.command": weapon("driver-command"), "diff.h.textconv": weapon("textconv"),
        "filter.h.clean": weapon("filter-clean"), "filter.h.smudge": weapon("filter-smudge"),
        "core.hooksPath": hooks.as_posix(), "core.pager": weapon("pager"),
        "alias.diff": "!" + weapon("alias-diff"), "alias.show": "!" + weapon("alias-show"),
    }.items():
        _git(repo, "config", key, value)
    provider = LocalGitProvider([repo])
    scan_changes(provider, provider.get_repository(str(repo)), "base", "main")
    assert sorted(p.name for p in markers.iterdir()) == []


# -- B2: a redirecting ".git" file cannot reach outside the allowlist ---------

def _make_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    for key, value in (("user.name", "t"), ("user.email", "t@t.invalid"), ("commit.gpgsign", "false")):
        _git(path, "config", key, value)
    (path / "secret.py").write_text("SECRET = 1\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "one")
    _git(path, "branch", "b0")
    (path / "secret.py").write_text("SECRET = 2\n", encoding="utf-8")
    _git(path, "commit", "-q", "-am", "two")
    return path


def test_gitdir_file_pointing_outside_the_allowlist_is_refused(tmp_path):
    # On f8967bc this scanned the outside repository and returned its diff.
    allowed = tmp_path / "allowed"
    outside = _make_repo(tmp_path / "outside")
    redirect = allowed / "redirect"
    redirect.mkdir(parents=True)
    (redirect / ".git").write_text(f"gitdir: {(outside / '.git').as_posix()}\n", encoding="utf-8")
    provider = LocalGitProvider([allowed])
    with pytest.raises(RepositoryAccessDenied, match="points outside SHIPSAFE_ALLOWED_ROOT"):
        provider.get_repository(str(redirect))
    app = create_app(demo_root=tmp_path / "demo", db_file=tmp_path / "scans.db", allowed_root=allowed)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post("/api/scans", json={"repository_path": str(redirect), "base_ref": "b0", "head_ref": "main"})
    assert response.status_code == 403
    assert "SECRET" not in response.text


def test_gitdir_file_pointing_nowhere_is_not_a_repository(tmp_path):
    allowed = tmp_path / "allowed"
    broken = allowed / "broken"
    broken.mkdir(parents=True)
    (broken / ".git").write_text("gitdir: /nonexistent/.git\n", encoding="utf-8")
    with pytest.raises(RepositoryNotFound):
        LocalGitProvider([allowed]).get_repository(str(broken))


def test_worktree_and_submodule_style_gitdir_files_inside_the_allowlist_still_work(tmp_path):
    allowed = tmp_path / "allowed"
    main_repo = _make_repo(allowed / "main-repo")
    _git(main_repo, "worktree", "add", "-q", str(allowed / "wt"), "b0")
    provider = LocalGitProvider([allowed])
    assert (allowed / "wt" / ".git").is_file()
    ref = provider.get_repository(str(allowed / "wt"))
    report = scan_changes(provider, ref, "b0", "main")
    assert [f["path"] for f in report["files"]] == ["secret.py"]


# -- B4: demo seeder never destroys work and never adopts a look-alike ---------

def _branch_tips(repo: Path) -> dict[str, str]:
    """Tip SHA of every demo branch that currently exists."""
    out = _git(repo, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads/")
    return dict(line.split() for line in out.splitlines())


def test_repair_refuses_to_discard_uncommitted_edits(tmp_path):
    # On f8967bc the edit was silently thrown away by `checkout -f`.
    demo = ensure_demo_repo(tmp_path / "demo")
    tips = _branch_tips(demo)
    _git(demo, "branch", "-D", "feature/docs-only")
    (demo / "app" / "auth.py").write_text("# my edit\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="uncommitted changes to app/auth.py"):
        ensure_demo_repo(demo)
    assert (demo / "app" / "auth.py").read_text(encoding="utf-8") == "# my edit\n"
    assert _git(demo, "branch", "--list", "feature/docs-only") == ""  # still missing; nothing was rewritten
    assert {b: t for b, t in _branch_tips(demo).items() if b != "feature/docs-only"} == {b: t for b, t in tips.items() if b != "feature/docs-only"}


def test_repair_leaves_untracked_files_alone_and_out_of_demo_commits(tmp_path):
    # On f8967bc `git add .` committed stray.txt into the rebuilt branch and the
    # final checkout of main then deleted it.
    demo = ensure_demo_repo(tmp_path / "demo")
    tips = _branch_tips(demo)
    _git(demo, "branch", "-D", "feature/docs-only")
    (demo / "stray.txt").write_text("mine\n", encoding="utf-8")
    ensure_demo_repo(demo)
    assert (demo / "stray.txt").read_text(encoding="utf-8") == "mine\n"
    assert "stray.txt" not in _git(demo, "ls-tree", "-r", "--name-only", "feature/docs-only")
    rebuilt = _branch_tips(demo)
    assert {b: t for b, t in rebuilt.items() if b != "feature/docs-only"} == {b: t for b, t in tips.items() if b != "feature/docs-only"}
    assert _git(demo, "ls-tree", "-r", "--name-only", "feature/docs-only").split() == sorted(BASE_FILES)


def test_complete_demo_is_never_modified_even_with_local_edits(tmp_path):
    demo = ensure_demo_repo(tmp_path / "demo")
    tips = _branch_tips(demo)
    (demo / "app" / "auth.py").write_text("# my edit\n", encoding="utf-8")
    (demo / "stray.txt").write_text("mine\n", encoding="utf-8")
    ensure_demo_repo(demo)
    assert _branch_tips(demo) == tips
    assert (demo / "app" / "auth.py").read_text(encoding="utf-8") == "# my edit\n"
    assert (demo / "stray.txt").exists()


def test_look_alike_repository_with_the_demo_commit_subject_is_refused(tmp_path):
    # On f8967bc the subject alone was enough to adopt and modify a foreign repository.
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    _git(foreign, "init", "-q", "-b", "main")
    for key, value in (("user.name", "someone"), ("user.email", "someone@example.invalid"), ("commit.gpgsign", "false")):
        _git(foreign, "config", key, value)
    (foreign / "work.py").write_text("w = 1\n", encoding="utf-8")
    _git(foreign, "add", "-A")
    _git(foreign, "commit", "-q", "-m", INITIAL_COMMIT_SUBJECT)
    with pytest.raises(ConfigError, match="not the generated demo"):
        ensure_demo_repo(foreign)
    assert _git(foreign, "branch", "--format=%(refname:short)").split() == ["main"]


def test_demo_seeded_before_the_marker_existed_is_still_recognised(tmp_path):
    demo = ensure_demo_repo(tmp_path / "demo")
    assert _git(demo, "config", "--get", DEMO_MARKER) == "true"
    _git(demo, "config", "--unset", DEMO_MARKER)
    _git(demo, "branch", "-D", "feature/docs-only")
    ensure_demo_repo(demo)  # recognised by root-commit subject + synthetic author
    assert _git(demo, "branch", "--list", "feature/docs-only").strip() == "feature/docs-only"


# -- B3: a cut report says so, in the JSON, the summary, and the ZIP ----------

@pytest.fixture()
def oversized_repo(tmp_path):
    """302 changed files (limit 300) and one 200-line patch (limit 140)."""
    repo = tmp_path / "big"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    for key, value in (("user.name", "t"), ("user.email", "t@t.invalid"), ("commit.gpgsign", "false")):
        _git(repo, "config", key, value)
    for version in ("1", "2"):
        for i in range(301):
            (repo / f"f{i:03}.txt").write_text(f"{version}\n", encoding="utf-8")
        (repo / "a_long.py").write_text("".join(f"line{i} = {int(version) + i}\n" for i in range(200)), encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", version)
        if version == "1":
            _git(repo, "branch", "b0")
    return repo


def test_truncated_scan_is_labelled_everywhere(oversized_repo):
    # On f8967bc: files_changed=300, lines_added=499, no flag anywhere, and the
    # 200-line patch was stored as 140 lines ending mid-hunk.
    provider = LocalGitProvider([oversized_repo])
    report = scan_changes(provider, provider.get_repository(str(oversized_repo)), "b0", "main")
    assert report["summary"]["files_changed"] == MAX_CHANGED_FILES
    assert report["summary"]["truncated"] is True
    assert report["summary"]["files_omitted"] == 2
    long = next(f for f in report["files"] if f["path"] == "a_long.py")
    assert long["diff_truncated"] is True
    stored = long["diff"].splitlines()
    assert len(stored) == PATCH_PREVIEW_LINES + 1
    assert stored[-1].startswith("... [") and f"{long['diff_lines_omitted']} more diff lines not shown" in stored[-1]
    assert long["diff_lines_omitted"] > 0 and long["diff_lines_omitted"] + PATCH_PREVIEW_LINES == int(stored[-1].rsplit("has ", 1)[1].split()[0])
    assert all(not f["diff_truncated"] and f["diff_lines_omitted"] == 0 for f in report["files"] if f["path"] != "a_long.py")
    limitations = handoff_payload(report)["review_context"]["limitations"]
    assert limitations[0].startswith("INCOMPLETE: 2 changed files beyond the first 300")
    assert "1 included file is cut" in limitations[1]


def test_complete_scan_is_not_labelled_truncated(tmp_path):
    demo = ensure_demo_repo(tmp_path / "demo")
    provider = LocalGitProvider([demo])
    report = scan_changes(provider, provider.get_repository(str(demo)), "main", "feature/release-candidate")
    assert (report["summary"]["truncated"], report["summary"]["files_omitted"]) == (False, 0)
    assert all((f["diff_truncated"], f["diff_lines_omitted"]) == (False, 0) for f in report["files"])
    assert not any("... [" in f["diff"] for f in report["files"])
    limitations = handoff_payload(report)["review_context"]["limitations"]
    assert limitations[0] == "Git patches are limited to the first 140 lines per file; no included patch was cut."
    assert not any(item.startswith("INCOMPLETE") for item in limitations)


def test_reports_stored_before_the_truncation_fields_still_export(tmp_path):
    # A v0.2-era report (no new keys) must still produce a handoff package.
    import json
    example = json.loads((Path(__file__).resolve().parents[2] / "docs" / "example-scan-report.json").read_text(encoding="utf-8"))
    for entry in example["files"]:
        entry.pop("diff_truncated"), entry.pop("diff_lines_omitted")
    example["summary"].pop("truncated"), example["summary"].pop("files_omitted")
    limitations = handoff_payload(example)["review_context"]["limitations"]
    assert limitations[0].startswith("Git patches are limited to the first 140 lines")


def test_tree_listing_and_file_reads_use_literal_names(hostile_names_repo):
    provider = LocalGitProvider([hostile_names_repo])
    repo = provider.get_repository(str(hostile_names_repo))
    head = provider.resolve_commit(repo, "main")
    assert sorted(provider.list_files(repo, head)) == sorted(HOSTILE_NAMES)
    for name in HOSTILE_NAMES:
        assert provider.read_file(repo, head, name) == f"v2 {name}\n"
