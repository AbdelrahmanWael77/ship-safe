"""Phase 4 task A: static discovery of existing tests. Nothing here, and
nothing in the code under test, imports or runs a discovered test file."""
import ast
import builtins
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import discovery
from app.discovery import discover_tests, is_test_file, module_names
from app.main import create_app
from app.providers.base import RepositoryRef

REPO = RepositoryRef(provider="fake", id="fake/repo", name="repo", location="memory")
COMMIT = "c" * 40


class FakeProvider:
    """Serves files from a dict and records what was read."""

    def __init__(self, files: dict[str, str]):
        self.files, self.read = files, []

    def list_files(self, repository, commit):
        assert (repository, commit) == (REPO, COMMIT)
        return list(self.files)

    def read_file(self, repository, commit, path):
        self.read.append(path)
        return self.files[path]


def report(*files, findings=()):
    return {
        "files": [{"path": path, "changed_functions": list(functions)} for path, functions in files],
        "findings": [{"id": finding_id, "file": path} for finding_id, path in findings],
        "summary": {},
    }


# -- rules --------------------------------------------------------------------

@pytest.mark.parametrize("path,expected", [
    ("tests/test_auth.py", True), ("app/auth_test.py", True), ("test_x.py", True),
    ("tests/conftest.py", False), ("app/testing.py", False), ("tests/test_auth.txt", False),
    ("app/contest.py", False), ("tests/helpers.py", False),
])
def test_test_files_follow_pytest_default_names(path, expected):
    assert is_test_file(path) is expected


@pytest.mark.parametrize("path,expected", [
    ("backend/app/auth.py", {"backend.app.auth", "app.auth"}),
    ("app/auth.py", {"app.auth"}),
    ("auth.py", {"auth"}),
    ("app/__init__.py", {"app"}),
    ("README.md", set()),
])
def test_module_names_never_include_a_bare_nested_name(path, expected):
    assert module_names(path) == expected


def test_candidates_are_tests_whose_file_imports_a_changed_module():
    provider = FakeProvider({
        "app/auth.py": "def check(user): ...\n",
        "app/pricing.py": "def total(): ...\n",
        "tests/test_auth.py": (
            "from app.auth import check\n"
            "def test_owner_can_read():\n    assert check('a')\n"
            "def test_unrelated():\n    assert True\n"
            "def helper():\n    pass\n"
            "class TestAccess:\n"
            "    def test_denied(self):\n        check('b')\n"
            "    def not_a_test(self):\n        pass\n"
            "class Helper:\n    def test_ignored(self):\n        pass\n"
        ),
        "tests/test_pricing.py": "import app.pricing\ndef test_total():\n    assert app.pricing.total() is None\n",
        "tests/test_other.py": "import json\ndef test_json():\n    assert json.dumps({}) == '{}'\n",
    })
    found = discover_tests(provider, REPO, COMMIT, report(("app/auth.py", ["check"]), findings=[("f1", "app/auth.py")]))

    assert [item["test_id"] for item in found["candidates"]] == [
        "tests/test_auth.py::TestAccess::test_denied", "tests/test_auth.py::test_owner_can_read",
        "tests/test_auth.py::test_unrelated",
    ]  # the two that mention the changed function first; the unrelated one still listed, last
    first, _, last = found["candidates"]
    assert {"kind": "mentions_changed_function", "changed_file": "app/auth.py", "function": "check"} in first["reasons"]
    assert last["reasons"] == [{"kind": "imports_changed_module", "changed_file": "app/auth.py"}]
    assert first["related_static_finding_ids"] == ["f1"] and first["line"] == 9
    assert (found["test_files_found"], found["tests_found"], found["candidate_count"]) == (3, 5, 3)
    assert found["coverage_gaps"] == [] and found["incomplete"] is False
    assert found["executed"] is False and found["method"] == "static-ast" and found["commit"] == COMMIT
    assert sorted(provider.read) == ["tests/test_auth.py", "tests/test_other.py", "tests/test_pricing.py"]  # only test files are read


def test_from_package_import_module_and_suffix_paths_are_matched_but_bare_names_are_not():
    provider = FakeProvider({
        "tests/test_a.py": "from app import auth\ndef test_a():\n    auth.check()\n",
        "tests/test_b.py": "from backend.app.auth import check\ndef test_b():\n    check()\n",
        "tests/test_c.py": "import auth\ndef test_c():\n    auth.x()\n",            # some other top-level 'auth'
        "tests/test_d.py": "from . import auth\ndef test_d():\n    auth.x()\n",       # relative: not resolved
    })
    found = discover_tests(provider, REPO, COMMIT, report(("backend/app/auth.py", [])))
    assert [item["file"] for item in found["candidates"]] == ["tests/test_a.py", "tests/test_b.py"]


def test_coverage_gaps_list_untested_modules_and_non_python_files_with_their_findings():
    provider = FakeProvider({"tests/test_auth.py": "from app.auth import check\ndef test_x():\n    check()\n"})
    found = discover_tests(
        provider, REPO, COMMIT,
        report(("app/auth.py", []), ("app/pricing.py", []), ("README.md", []), ("tests/test_auth.py", []),
               findings=[("f-price", "app/pricing.py")]),
        ai_findings=[{"id": "F1", "file": "app/pricing.py"}, {"file": "app/auth.py"}],
    )
    assert found["coverage_gaps"] == [
        {"changed_file": "app/pricing.py", "reason": "No discovered test file imports this module.",
         "static_finding_ids": ["f-price"], "ai_finding_ids": ["F1"]},
        {"changed_file": "README.md", "reason": "Not a Python module; imports cannot be traced to it.",
         "static_finding_ids": [], "ai_finding_ids": []},
    ]  # the changed test file itself is not a gap
    candidate = found["candidates"][0]
    assert candidate["changed_in_this_scan"] is True and candidate["related_ai_finding_ids"] == ["AI-2"]


def test_no_tests_at_all_makes_every_changed_file_a_gap():
    found = discover_tests(FakeProvider({"app/auth.py": ""}), REPO, COMMIT, report(("app/auth.py", [])))
    assert found["candidates"] == [] and found["tests_found"] == 0
    assert [gap["changed_file"] for gap in found["coverage_gaps"]] == ["app/auth.py"]


def test_read_limit_unparsable_and_oversized_files_are_reported_as_incomplete(monkeypatch):
    files = {f"tests/test_{n:02}.py": "from app.auth import check\ndef test_it():\n    check()\n" for n in range(5)}
    files["tests/test_broken.py"] = "def test_(:\n"
    files["tests/test_nul.py"] = "x = 1\x00"
    provider = FakeProvider(files)
    found = discover_tests(provider, REPO, COMMIT, report(("app/auth.py", [])), max_files=6)
    assert (found["test_files_found"], found["test_files_read"], found["test_files_unread"]) == (7, 6, 1)
    assert found["unparsed_test_files"] == ["tests/test_broken.py"] and found["incomplete"] is True
    assert len(provider.read) == 6

    monkeypatch.setattr(discovery, "MAX_TEST_FILE_CHARS", 10)
    big = discover_tests(FakeProvider({"tests/test_big.py": "def test_a():\n    pass\n" * 5}), REPO, COMMIT, report())
    assert big["unparsed_test_files"] == ["tests/test_big.py"] and big["tests_found"] == 0


def test_a_hostile_test_file_is_parsed_but_never_executed(monkeypatch, tmp_path):
    marker = tmp_path / "executed"
    hostile = (
        f"import os\nopen({str(marker)!r}, 'w').write('x')\n"
        "raise SystemExit(1)\n"
        "from app.auth import check\n"
        "def test_evil():\n    __import__('os').system('echo pwned')\n    check()\n"
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("discovery must not execute code or start a process")

    # exec / eval would run the file; a process could run it elsewhere. (compile and
    # __import__ cannot be blocked: ast.parse and the interpreter itself use them.)
    for name in ("exec", "eval"):
        monkeypatch.setattr(builtins, name, forbidden)
    for name in ("run", "Popen", "call", "check_output"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    modules_before = set(sys.modules)
    try:
        # Module-level code of the file would write the marker and raise SystemExit if it ran.
        found = discover_tests(FakeProvider({"tests/test_evil.py": hostile}), REPO, COMMIT, report(("app/auth.py", ["check"])))
    finally:
        monkeypatch.undo()
    assert [item["test_id"] for item in found["candidates"]] == ["tests/test_evil.py::test_evil"]
    assert not marker.exists()
    assert not any("test_evil" in name for name in set(sys.modules) - modules_before)  # never imported


def test_the_discovery_module_has_no_way_to_execute_what_it_reads():
    source = Path(discovery.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not called & {"exec", "eval", "compile", "__import__"}
    assert not imported & {"subprocess", "importlib", "runpy", "os", "pytest", "multiprocessing"}


# -- through the API, on the synthetic demo repository -------------------------

@pytest.fixture()
def demo(tmp_path):
    repo = tmp_path / "demo"
    app = create_app(demo_root=repo, db_file=tmp_path / "data" / "scans.db", allowed_root=repo)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def scan(client, head):
    response = client.post("/api/scans", json={"base_ref": "main", "head_ref": head})
    assert response.status_code == 201, response.text
    return response.json()


def test_demo_auth_regression_finds_the_happy_path_test_and_says_nothing_ran(demo):
    scanned = scan(demo, "feature/auth-regression")
    found = demo.get(f"/api/scans/{scanned['id']}/tests/discovery").json()
    assert found["scan_id"] == scanned["id"] and found["commit"] == scanned["binding"]["head_commit"]
    assert found["executed"] is False and "No test was collected or run" in found["disclaimer"]
    assert found["test_files_found"] == 1 and found["tests_found"] == 3
    ids = [item["test_id"] for item in found["candidates"]]
    assert ids[0] == "tests/test_smoke.py::test_own_invoice_is_accessible"  # mentions the changed function
    assert set(ids) == {f"tests/test_smoke.py::{name}" for name in (
        "test_own_invoice_is_accessible", "test_normal_invoice_total", "test_response_contains_status")}
    static_ids = {finding["id"] for finding in scanned["findings"]}
    assert set(found["candidates"][0]["related_static_finding_ids"]) == static_ids and static_ids
    assert found["coverage_gaps"] == [] and found["ai_review_id"] is None and len(found["heuristics"]) >= 5
    # Discovery stores nothing and changes nothing.
    assert demo.get(f"/api/scans/{scanned['id']}").json() == scanned
    assert demo.get(f"/api/scans/{scanned['id']}/tests/discovery").json() == found


def test_demo_docs_only_change_has_no_candidates_and_one_honest_gap(demo):
    scanned = scan(demo, "feature/docs-only")
    found = demo.get(f"/api/scans/{scanned['id']}/tests/discovery").json()
    assert found["candidates"] == [] and found["candidate_count"] == 0
    assert [gap["reason"] for gap in found["coverage_gaps"]] == ["Not a Python module; imports cannot be traced to it."] * len(scanned["files"])
    assert all(gap["static_finding_ids"] == [] for gap in found["coverage_gaps"])


def test_unknown_scan_is_404(demo):
    assert demo.get("/api/scans/12345678-1111-2222-3333-444444444444/tests/discovery").status_code == 404
