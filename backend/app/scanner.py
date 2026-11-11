"""Deterministic Git/AST analysis. Findings are heuristics, NOT verified defects."""
from __future__ import annotations

import ast
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .errors import ScanError
from .providers.base import MAX_CHANGED_FILES, ChangeProvider, RepositoryRef, valid_ref
from .providers.local_git import LocalGitProvider, run_git as git

__all__ = ["ScanError", "git", "valid_ref", "scan_changes", "scan_repository", "analyze_risks"]

#: Lines of each file's patch kept in a stored report.
PATCH_PREVIEW_LINES = 140
#: Files at the head commit inspected for imports of changed modules.
MAX_IMPORT_SCAN_FILES = 250


def _parse(source: str) -> ast.AST | None:
    """Parse untrusted Python source; None if it cannot be parsed safely.

    Besides syntax errors, hostile or generated input can exhaust the parser
    (RecursionError/MemoryError) or contain NUL bytes (ValueError on 3.11).
    """
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def py_functions(text: str, changed_lines: set[int]) -> list[str]:
    tree = _parse(text)
    if tree is None:
        return []
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_line = getattr(node, "end_lineno", node.lineno)
            if any(node.lineno <= line <= end_line for line in changed_lines):
                names.add(node.name)
    return sorted(names)


def response_keys(source: str) -> set[str]:
    tree = _parse(source)
    if tree is None:
        return set()
    keys = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            for k in n.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
    return keys


def import_dependencies(
    provider: ChangeProvider, repository: RepositoryRef, head_sha: str, changed_paths: list[str],
) -> list[dict]:
    files = provider.list_files(repository, head_sha)
    changed_modules = {
        path[:-3].replace("/", "."): path
        for path in changed_paths if path.endswith(".py")
    }
    direct = []
    for path in files[:MAX_IMPORT_SCAN_FILES]:
        if not path.endswith(".py") or path in changed_paths:
            continue
        tree = _parse(provider.read_file(repository, head_sha, path))
        if tree is None:
            continue
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                imports.add(mod)
                imports.update(f"{mod}.{a.name}" for a in node.names)
        matched = sorted(mod for mod in changed_modules if mod in imports)
        if matched:
            direct.append({"path": path, "imports_changed": matched})
    return direct


def _changed_new_lines(diff: str) -> set[int]:
    lines = set()
    for line in diff.splitlines():
        match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if match:
            start = int(match.group(1))
            count = int(match.group(2) or 1)
            lines.update(range(start, start + count))
    return lines


def _diff_evidence(diff: str) -> tuple[list[str], list[str]]:
    removed = [line[1:] for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")]
    added = [line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
    return removed, added


def _first_new_line(diff: str) -> int | None:
    m = re.search(r"@@ -\d+(?:,\d+)? \+(\d+)", diff)
    return int(m.group(1)) if m else None


def _finding(category: str, severity: str, title: str, path: str, line: int | None,
             evidence: str, explanation: str, action: str) -> dict:
    return {
        "id": str(uuid4())[:8], "category": category, "severity": severity,
        "title": title, "file": path, "line": line, "status": "suspected",
        "evidence": evidence[:400], "explanation": explanation,
        "recommendation": action,
    }


def analyze_risks(path: str, before: str, after: str, diff: str) -> list[dict]:
    removed, added = _diff_evidence(diff)
    deleted_text = "\n".join(removed)
    added_text = "\n".join(added)
    findings = []
    line = _first_new_line(diff)

    auth_patterns = (r"owner_id", r"PermissionError", r"is_authorized", r"require_role", r"check_permission")
    removed_guard = any(re.search(p, deleted_text, re.I) for p in auth_patterns)
    after_has_guard = any(re.search(p, after, re.I) for p in auth_patterns)
    if path.endswith(".py") and removed_guard and not after_has_guard:
        findings.append(_finding(
            "Security", "critical", "Possible authorization guard removal", path, line,
            next((x.strip() for x in removed if any(re.search(p, x, re.I) for p in auth_patterns)), "Removed a permission-related check"),
            "A permission or ownership check appears to have disappeared. This is a static suspicion, not an exploited vulnerability.",
            "Add a cross-user access regression test and verify unauthorized reads are rejected.",
        ))

    if path.endswith(".py") and "Decimal" in before and "Decimal" not in after and (
        "float(" in after or "round(" in added_text
    ):
        findings.append(_finding(
            "Data integrity", "high", "Precision-sensitive calculation refactored", path, line,
            next((x.strip() for x in added if "float" in x or "round(" in x), "Decimal replaced"),
            "A decimal-based operation was replaced by floating-point arithmetic. Specific incorrect outputs are not verified.",
            "Compare monetary boundary values and assert exact rounding behavior using Decimal.",
        ))

    if path.endswith(".py") and ("api" in path.lower() or "schema" in path.lower()):
        lost = response_keys(before) - response_keys(after)
        introduced = response_keys(after) - response_keys(before)
        if lost:
            findings.append(_finding(
                "API contract", "high", "Possible breaking response schema change", path, line,
                f"Removed keys: {', '.join(sorted(lost))}; added: {', '.join(sorted(introduced)) or 'none'}",
                "Literal response dictionary keys changed. Consumers may depend on removed fields.",
                "Run contract tests against the previous response schema or version the API.",
            ))

    return findings


def scan_repository(repo: Path, base: str, head: str) -> dict:
    """Scan a local Git repository the caller has already authorized.

    Kept for scripts and tests. The API goes through ``LocalGitProvider``
    built from the configured allowlist and then calls :func:`scan_changes`.
    """
    repo = repo.resolve()
    provider = LocalGitProvider([repo])
    return scan_changes(provider, provider.get_repository(str(repo)), base, head)


def scan_changes(provider: ChangeProvider, repository: RepositoryRef, base: str, head: str) -> dict:
    """Scan orchestration: fetch a change set from any provider, run the static
    heuristics, and build the report. Reads only; executes nothing.

    The returned dict is the persisted report and the public ``Report`` API
    type; its shape is unchanged from v0.2.
    """
    started = time.monotonic()
    changes = provider.get_changes(repository, base, head, max_files=MAX_CHANGED_FILES)
    base_sha, head_sha = changes.base_sha, changes.head_sha
    files = []
    findings = []
    for delta in changes.files:
        path, status = delta.path, delta.status
        is_python = path.endswith(".py")
        before = provider.read_file(repository, base_sha, path) if status != "A" and is_python else ""
        after = provider.read_file(repository, head_sha, path) if status != "D" and is_python else ""
        functions = py_functions(after, _changed_new_lines(delta.patch)) if is_python else []
        findings.extend(analyze_risks(path, before, after, delta.patch))
        files.append({
            "path": path, "status": status, "additions": delta.additions, "deletions": delta.deletions,
            "changed_functions": functions, "diff": "\n".join(delta.patch.splitlines()[:PATCH_PREVIEW_LINES]),
        })
    severities = {"critical": 42, "high": 26, "medium": 12, "low": 4}
    risk_score = min(99, sum(severities[f["severity"]] for f in findings) + (3 if files else 0))
    if findings:
        level = "Critical review required" if any(f["severity"] == "critical" for f in findings) else "Review required"
    elif files:
        level = "No flagged patterns — review still required"
    else:
        level = "No changes detected"
    impacted = import_dependencies(provider, repository, head_sha, [f["path"] for f in files])
    test_suggestions = []
    suggestions = {
        "Security": "Verify a different user cannot access another user's invoice.",
        "Data integrity": "Compare Decimal-based pricing against boundary values and rounding cases.",
        "API contract": "Assert all previously required response fields remain available.",
    }
    for finding in findings:
        test_suggestions.append({
            "category": finding["category"], "file": finding["file"],
            "scenario": suggestions.get(finding["category"], "Exercise changed behavior and affected consumers."),
        })
    return {
        "id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
        "repo_name": repository.name, "repository_path": repository.location, "base_ref": base,
        "head_ref": head, "base_sha": base_sha[:12], "head_sha": head_sha[:12],
        "duration_ms": round((time.monotonic() - started) * 1000),
        "summary": {
            "files_changed": len(files), "lines_added": sum(f["additions"] for f in files),
            "lines_removed": sum(f["deletions"] for f in files), "finding_count": len(findings),
            "risk_score": risk_score, "recommendation": level,
            "test_status": "not_run",
        },
        "files": files, "findings": findings, "affected_modules": impacted,
        "test_suggestions": test_suggestions,
        "disclaimer": "Heuristic static analysis only. Findings are suspected risks, not confirmed failures. No repository code or tests were executed.",
    }
