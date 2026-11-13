"""Phase 4 task A: find existing tests (pytest or Dart/Flutter) that may exercise a change.

Static only. Test files are read as text and parsed with ``ast``; nothing is
imported, collected or executed, so a hostile test file cannot run code here.
Everything this module returns is a suggestion: a test that imports a changed
module is not known to cover the change, and no test here has been run.
"""
from __future__ import annotations

import ast
import posixpath
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
#: Dart/Flutter convention (``flutter test`` / ``dart test`` defaults): files named *_test.dart.
_DART_TEST_FILE = re.compile(r"^.+_test\.dart$")
#: ``import '...';`` / ``export '...';`` directives of a Dart file.
_DART_IMPORT = re.compile(r"""^\s*(?:import|export)\s+['"]([^'"]+)['"]""", re.M)
#: test('name', ...), testWidgets("name", ...), blocTest<C, S>('name', ...).
_DART_TEST = re.compile(r"""\b(test|testWidgets|blocTest(?:<[^>()]*>)?)\s*\(\s*(['"])(.+?)\2""")
#: ``name: my_app`` in pubspec.yaml.
_PUBSPEC_NAME = re.compile(r"^name:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", re.M)
#: pubspec.yaml files read to learn package names (one read each).
MAX_PUBSPECS = 10

HEURISTICS = [
    "A file is a test file when its name matches pytest's defaults (test_*.py or *_test.py) "
    "or the Dart/Flutter default (*_test.dart).",
    "Python tests are module-level functions named test_* and test_* methods of classes named Test*. "
    "Parametrized cases and tests generated at run time are not expanded.",
    "Dart tests are calls to test(), testWidgets() or blocTest() with a literal name. A Dart test file is a "
    "candidate when it imports a changed .dart file, by a relative path or as package:<name>/... where "
    "<name> comes from a pubspec.yaml in the repository.",
    "A test is a candidate when its file imports a changed Python module (matched on the module's "
    "dotted path or a suffix of it with at least two segments, or the bare name for a top-level module).",
    "A candidate ranks higher when the test's own body mentions a function that the change touched.",
    "A changed file is a coverage gap when no discovered test file imports it. Files that are neither "
    "Python nor Dart are always listed as gaps because imports cannot be traced to them.",
    "A test file that cannot be read (for example larger than the read limit, or stored in Git LFS) or "
    "parsed is listed as not parsed, so the discovery is marked incomplete.",
    "Test files are parsed, never imported or run. Indirect imports, fixtures in conftest.py and "
    "dynamic imports are not followed, so both false candidates and missed tests are possible.",
]


def is_test_file(path: str) -> bool:
    name = PurePosixPath(path).name
    return bool(_TEST_FILE.match(name) or _DART_TEST_FILE.match(name))


def _dart_packages(provider: ChangeProvider, repository: RepositoryRef, commit: str, paths: list[str]) -> dict[str, str]:
    """Package name -> directory that holds its ``lib/`` (\"\" for the repository root)."""
    packages: dict[str, str] = {}
    pubspecs = sorted((path for path in paths if PurePosixPath(path).name == "pubspec.yaml"),
                      key=lambda path: (path.count("/"), path))[:MAX_PUBSPECS]
    for path in pubspecs:
        match = _PUBSPEC_NAME.search(provider.read_file(repository, commit, path) or "")
        if match:
            packages.setdefault(match.group(1), posixpath.dirname(path))
    return packages


def _dart_imports(source: str, test_path: str, packages: dict[str, str]) -> set[str]:
    """Repository paths of the Dart files a Dart file imports (only those that can be resolved)."""
    found: set[str] = set()
    for uri in _DART_IMPORT.findall(source):
        if uri.startswith("package:"):
            name, _, rest = uri[len("package:"):].partition("/")
            if name in packages and rest:
                found.add(posixpath.normpath(posixpath.join(packages[name], "lib", rest)))
        elif ":" not in uri:
            found.add(posixpath.normpath(posixpath.join(posixpath.dirname(test_path), uri)))
    return found


def _dart_tests(source: str) -> list[tuple[str, int]]:
    return [(match.group(3), source.count("\n", 0, match.start()) + 1) for match in _DART_TEST.finditer(source)]


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
    dart_changed = {path for path in changed_paths if path.endswith(".dart") and not is_test_file(path)}

    static_by_file: dict[str, list[str]] = {}
    for finding in report.get("findings", []):
        static_by_file.setdefault(finding["file"], []).append(finding["id"])
    ai_by_file: dict[str, list[str]] = {}
    for index, finding in enumerate(ai_findings or []):
        ai_by_file.setdefault(finding.get("file", ""), []).append(str(finding.get("id") or f"AI-{index + 1}"))

    paths = provider.list_files(repository, commit)
    all_test_files = sorted(path for path in paths if is_test_file(path))
    test_files, unread = all_test_files[:max_files], max(0, len(all_test_files) - max_files)
    packages = _dart_packages(provider, repository, commit, paths) if dart_changed and any(
        path.endswith(".dart") for path in test_files) else {}

    candidates, unparsed, tests_found = [], [], 0
    covered: set[str] = set()
    for path in test_files:
        source = provider.read_file(repository, commit, path)
        if not source or len(source) > MAX_TEST_FILE_CHARS:
            # Empty here also means unreadable (too large, LFS, gone): never count it as "no tests".
            unparsed.append(path)
            continue
        if path.endswith(".dart"):
            dart_tests = _dart_tests(source)
            tests_found += len(dart_tests)
            imported_changed = sorted(_dart_imports(source, path, packages) & dart_changed)
            if not imported_changed:
                continue
            covered.update(imported_changed)
            for name, line in dart_tests:
                candidates.append({
                    "test_id": f"{path}::{name}", "file": path, "name": name, "line": line,
                    "changed_in_this_scan": path in changed_paths,
                    "reasons": [{"kind": "imports_changed_module", "changed_file": changed_file} for changed_file in imported_changed],
                    "related_static_finding_ids": sorted({i for f in imported_changed for i in static_by_file.get(f, [])}),
                    "related_ai_finding_ids": sorted({i for f in imported_changed for i in ai_by_file.get(f, [])}),
                })
            continue
        tree = _parse(source)
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
        traceable = path.endswith((".py", ".dart"))
        gaps.append({
            "changed_file": path,
            "reason": ("No discovered test file imports this module." if traceable
                       else "Not a Python or Dart file; imports cannot be traced to it."),
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
