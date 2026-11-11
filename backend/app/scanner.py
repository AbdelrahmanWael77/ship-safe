"""Deterministic Git/AST analysis. Findings are heuristics, NOT verified defects."""
from __future__ import annotations

import ast
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class ScanError(ValueError):
    pass


def git(repo: Path, *args: str, allow_error: bool = False) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args], text=True,
            capture_output=True, timeout=20, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScanError(f"Git is unavailable or timed out: {exc}") from exc
    if proc.returncode != 0:
        if allow_error:
            return ""
        raise ScanError(proc.stderr.strip()[:350] or "Git command failed")
    return proc.stdout


def valid_ref(ref: str) -> bool:
    return bool(
        ref and len(ref) <= 150 and re.fullmatch(r"[a-zA-Z0-9_./-]+", ref)
        and not ref.startswith("-") and ".." not in ref and "//" not in ref
        and not ref.endswith("/") and not ref.endswith(".lock")
    )


def commit_sha(repo: Path, ref: str) -> str:
    if not valid_ref(ref):
        raise ScanError(f"Invalid Git reference: {ref!r}")
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def tree_file(repo: Path, sha: str, rel_path: str) -> str:
    return git(repo, "show", f"{sha}:{rel_path}", allow_error=True)


def py_functions(text: str, changed_lines: set[int]) -> list[str]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_line = getattr(node, "end_lineno", node.lineno)
            if any(node.lineno <= line <= end_line for line in changed_lines):
                names.add(node.name)
    return sorted(names)


def response_keys(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    keys = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            for k in n.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
    return keys


def import_dependencies(repo: Path, head_sha: str, changed_paths: list[str]) -> list[dict]:
    files = git(repo, "ls-tree", "-r", "--name-only", head_sha).splitlines()
    changed_modules = {
        path[:-3].replace("/", "."): path
        for path in changed_paths if path.endswith(".py")
    }
    direct = []
    for path in files[:250]:
        if not path.endswith(".py") or path in changed_paths:
            continue
        source = tree_file(repo, head_sha, path)
        try:
            tree = ast.parse(source)
        except SyntaxError:
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
    started = time.monotonic()
    repo = repo.resolve()
    if not (repo / ".git").exists():
        raise ScanError("This path is not a local Git repository")
    base_sha = commit_sha(repo, base)
    head_sha = commit_sha(repo, head)
    statuses = git(repo, "diff", "--name-status", "--no-renames", base_sha, head_sha, "--").splitlines()
    numstat = {}
    for row in git(repo, "diff", "--numstat", "--no-renames", base_sha, head_sha, "--").splitlines():
        chunks = row.split("\t", 2)
        if len(chunks) == 3:
            a, d, name = chunks
            numstat[name] = (int(a) if a.isdigit() else 0, int(d) if d.isdigit() else 0)
    files = []
    findings = []
    for row in statuses[:300]:
        status, _, path = row.partition("\t")
        if not path:
            continue
        delta = git(repo, "diff", "--no-ext-diff", "--unified=3", base_sha, head_sha, "--", path)
        before = tree_file(repo, base_sha, path) if status != "A" and path.endswith(".py") else ""
        after = tree_file(repo, head_sha, path) if status != "D" and path.endswith(".py") else ""
        changed = _changed_new_lines(delta)
        functions = py_functions(after, changed) if path.endswith(".py") else []
        additions, deletions = numstat.get(path, (0, 0))
        findings.extend(analyze_risks(path, before, after, delta))
        files.append({
            "path": path, "status": status, "additions": additions, "deletions": deletions,
            "changed_functions": functions, "diff": "\n".join(delta.splitlines()[:140]),
        })
    severities = {"critical": 42, "high": 26, "medium": 12, "low": 4}
    risk_score = min(99, sum(severities[f["severity"]] for f in findings) + (3 if files else 0))
    if findings:
        level = "Critical review required" if any(f["severity"] == "critical" for f in findings) else "Review required"
    elif files:
        level = "No flagged patterns — review still required"
    else:
        level = "No changes detected"
    impacted = import_dependencies(repo, head_sha, [f["path"] for f in files])
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
        "repo_name": repo.name, "repository_path": str(repo), "base_ref": base,
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
