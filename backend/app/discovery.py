"""Phase 4 task A: find existing pytest tests that may exercise a change.

Static only. Test files are read as text and parsed with ``ast``; nothing is
imported, collected or executed, so a hostile test file cannot run code here.
Everything this module returns is a suggestion: a test that imports a changed
module is not known to cover the change, and no test here has been run.
"""
from __future__ import annotations

import ast
import re
from pathlib import PurePosixPath

from .providers.base import ChangeProvider, RepositoryRef

#: Test files read per discovery. Every file is one read (one HTTP request for
#: a remote provider); files beyond the limit are reported, never silently dropped.
MAX_TEST_FILES = 200
#: A test file larger than this is not parsed.
MAX_TEST_FILE_CHARS = 400_000
#: Candidates returned; the rest are counted.
MAX_CANDIDATES = 300

_TEST_FILE = re.compile(r"^(test_.+|.+_test)\.py$")

HEURISTICS = [
    "A file is a test file when its name matches pytest's defaults: test_*.py or *_test.py.",
    "Tests are module-level functions named test_* and test_* methods of classes named Test*. "
    "Parametrized cases and tests generated at run time are not expanded.",
    "A test is a candidate when its file imports a changed Python module (matched on the module's "
    "dotted path or a suffix of it with at least two segments, or the bare name for a top-level module).",
    "A candidate ranks higher when the test's own body mentions a function that the change touched.",
    "A changed file is a coverage gap when no discovered test file imports it. Non-Python files are "
    "always listed as gaps because imports cannot be traced to them.",
    "Test files are parsed, never imported or run. Indirect imports, fixtures in conftest.py and "
    "dynamic imports are not followed, so both false candidates and missed tests are possible.",
]


def is_test_file(path: str) -> bool:
    return bool(_TEST_FILE.match(PurePosixPath(path).name))


def _parse(source: str) -> ast.AST | None:
    """Parse untrusted source; None when it cannot be parsed safely."""
    if len(source) > MAX_TEST_FILE_CHARS:
        return None
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def module_names(path: str) -> set[str]:
    """Dotted names under which a changed file may be imported.

    ``backend/app/auth.py`` -> ``backend.app.auth`` and ``app.auth``. A bare
    last segment (``auth``) is accepted only for a file at the repository
    root, where it is the real module name; otherwise it would match any
    unrelated module of the same name.
    """
    if not path.endswith(".py"):
        return set()
    parts = path[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return set()
    names = {".".join(parts[index:]) for index in range(len(parts) - 1)}
    if len(parts) == 1:
        names.add(parts[0])
    return names


def _imports(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            module = node.module or ""
            if module:
                found.add(module)
                found.update(f"{module}.{alias.name}" for alias in node.names)
    return found


def _mentioned_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def _tests(tree: ast.AST) -> list[tuple[str, int, ast.AST]]:
    """``(qualified name, line, node)`` for each statically visible test."""
    tests = []
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            tests.append((node.name, node.lineno, node))
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name.startswith("test_"):
                    tests.append((f"{node.name}::{member.name}", member.lineno, member))
    return tests


def discover_tests(
    provider: ChangeProvider, repository: RepositoryRef, commit: str, report: dict,
    *, ai_findings: list[dict] | None = None, max_files: int = MAX_TEST_FILES,
) -> dict:
    """Candidate existing tests for the change in ``report``, at ``commit``.

    ``report`` is a stored scan report (its ``files`` and ``findings``).
    ``ai_findings`` are findings of an imported, unverified review; they are
    only used to say which candidates sit next to them.
    """
    changed = [item for item in report.get("files", [])]
    changed_paths = [item["path"] for item in changed]
    changed_functions = {item["path"]: set(item.get("changed_functions") or []) for item in changed}
    modules = {path: module_names(path) for path in changed_paths if path.endswith(".py") and not is_test_file(path)}

    static_by_file: dict[str, list[str]] = {}
    for finding in report.get("findings", []):
        static_by_file.setdefault(finding["file"], []).append(finding["id"])
    ai_by_file: dict[str, list[str]] = {}
    for index, finding in enumerate(ai_findings or []):
        ai_by_file.setdefault(finding.get("file", ""), []).append(str(finding.get("id") or f"AI-{index + 1}"))

    all_test_files = sorted(path for path in provider.list_files(repository, commit) if is_test_file(path))
    test_files, unread = all_test_files[:max_files], max(0, len(all_test_files) - max_files)

    candidates, unparsed, tests_found = [], [], 0
    covered: set[str] = set()
    for path in test_files:
        tree = _parse(provider.read_file(repository, commit, path))
        if tree is None:
            unparsed.append(path)
            continue
        imports = _imports(tree)
        imported_changed = sorted(changed for changed, names in modules.items() if names & imports)
        tests = _tests(tree)
        tests_found += len(tests)
        if not imported_changed:
            continue
        covered.update(imported_changed)
        for name, line, node in tests:
            mentioned = _mentioned_names(node)
            reasons = []
            for changed_file in imported_changed:
                reasons.append({"kind": "imports_changed_module", "changed_file": changed_file})
                for function in sorted(changed_functions.get(changed_file, set()) & mentioned):
                    reasons.append({"kind": "mentions_changed_function", "changed_file": changed_file, "function": function})
            candidates.append({
                "test_id": f"{path}::{name}", "file": path, "name": name, "line": line,
                "changed_in_this_scan": path in changed_paths,
                "reasons": reasons,
                "related_static_finding_ids": sorted({i for f in imported_changed for i in static_by_file.get(f, [])}),
                "related_ai_finding_ids": sorted({i for f in imported_changed for i in ai_by_file.get(f, [])}),
            })

    # Strongest signal first; stable order after that.
    candidates.sort(key=lambda item: (
        -sum(1 for reason in item["reasons"] if reason["kind"] == "mentions_changed_function"), item["test_id"]))

    gaps = []
    for path in changed_paths:
        if is_test_file(path) or path in covered:
            continue
        python = path.endswith(".py")
        gaps.append({
            "changed_file": path,
            "reason": ("No discovered test file imports this module." if python
                       else "Not a Python module; imports cannot be traced to it."),
            "static_finding_ids": static_by_file.get(path, []),
            "ai_finding_ids": ai_by_file.get(path, []),
        })

    return {
        "commit": commit,
        "method": "static-ast",
        "executed": False,
        "test_files_found": len(all_test_files),
        "test_files_read": len(test_files),
        "test_files_unread": unread,
        "unparsed_test_files": unparsed,
        "tests_found": tests_found,
        "candidate_count": len(candidates),
        "candidates": candidates[:MAX_CANDIDATES],
        "coverage_gaps": gaps,
        "incomplete": bool(unread or unparsed or len(candidates) > MAX_CANDIDATES
                           or report.get("summary", {}).get("truncated")),
        "heuristics": HEURISTICS,
        "disclaimer": "Suggestions from static analysis. No test was collected or run, and a listed test is "
                      "not known to cover the change.",
    }
