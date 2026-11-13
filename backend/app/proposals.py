"""Phase 4 task B: proposed regression tests and the human decisions on them.

A proposal is a test file somebody (a person, or an imported AI review via a
person) suggests adding. It is stored as untrusted text, bound to the scan and
its exact commits. ShipSafe parses it to check that it is Python containing a
pytest test; it never imports, applies or runs it here. Decisions are
append-only rows: nothing about a proposal or an earlier decision is rewritten.

There is no authentication in ShipSafe, so ``decided_by`` is a self-declared
name, recorded as such.
"""
from __future__ import annotations

import ast
import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .discovery import is_test_file

MAX_PROPOSAL_BYTES = 64 * 1024
MAX_REQUEST_BYTES = MAX_PROPOSAL_BYTES + 16 * 1024
MAX_PATH_CHARS = 300
IDENTITY_NOTE = ("ShipSafe has no authentication: the name recorded with a decision is typed by the person "
                 "and is not verified.")

_PART = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-.]*$")
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{n}" for n in range(1, 10)), *(f"lpt{n}" for n in range(1, 10))}
_TEST_DIRECTORIES = {"tests", "test"}


class ProposalError(ValueError):
    """The proposal or decision is not acceptable. ``status`` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def validate_target_path(path: object) -> str:
    """Return ``path`` if it is a safe place for a new test file, else raise.

    Accepted: a relative POSIX path of plain name segments, inside a directory
    named ``tests`` or ``test``, whose file name pytest would collect. Refused:
    anything absolute, with a drive or scheme, backslashes, ``.`` / ``..`` or
    empty segments, hidden or reserved names, ``conftest.py`` (it changes how
    every other test runs) and non-test files.
    """
    if not isinstance(path, str) or not path:
        raise ProposalError("Target path is required.")
    if len(path) > MAX_PATH_CHARS:
        raise ProposalError(f"Target path is longer than {MAX_PATH_CHARS} characters.")
    if any(ord(char) < 32 or ord(char) == 127 for char in path):
        raise ProposalError("Target path contains control characters.")
    if "\\" in path or ":" in path or path.startswith("/") or path.startswith("~"):
        raise ProposalError("Target path must be a relative path with forward slashes (no drive, scheme, backslash or leading slash).")
    parts = path.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise ProposalError("Target path must not contain empty, '.' or '..' segments.")
        if not _PART.match(part) or part.endswith("."):
            raise ProposalError(f"Target path segment {part!r} is not a plain name (letters, digits, '_', '-', '.'; no leading dot).")
        if part.split(".")[0].lower() in _WINDOWS_RESERVED:
            raise ProposalError(f"Target path segment {part!r} is a reserved device name.")
    if not _TEST_DIRECTORIES & set(parts[:-1]):
        raise ProposalError("Target path must be inside a directory named 'tests' or 'test'.")
    if parts[-1] == "conftest.py" or not is_test_file(path):
        raise ProposalError("Target file must be named test_*.py or *_test.py (conftest.py is not allowed).")
    return path


def check_against_tree(path: str, existing_files: list[str]) -> None:
    """Refuse a path that collides with the repository at the scanned commit.

    Git lists a symbolic link as a file. So if any directory of the target
    path is a *file* in the tree, writing there would go through a link (or
    replace a file with a directory); and an existing target would be
    overwritten. Both are refused: a proposal only ever adds a new file.
    """
    existing = set(existing_files)
    if path in existing:
        raise ProposalError(f"{path} already exists at the scanned commit. A proposal can only add a new test file.", 409)
    parts = path.split("/")
    for index in range(1, len(parts)):
        prefix = "/".join(parts[:index])
        if prefix in existing:
            raise ProposalError(
                f"{prefix} is a file or symbolic link at the scanned commit, not a directory. Refusing to write through it.", 409)


def validate_content(content: object) -> str:
    """Return ``content`` if it is parseable Python holding at least one pytest test. Never runs it."""
    if not isinstance(content, str) or not content.strip():
        raise ProposalError("Proposed test content is required.")
    if len(content.encode("utf-8", errors="replace")) > MAX_PROPOSAL_BYTES:
        raise ProposalError(f"Proposed test is larger than {MAX_PROPOSAL_BYTES // 1024} KiB.", 413)
    if "\x00" in content:
        raise ProposalError("Proposed test contains NUL bytes.")
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        raise ProposalError(f"Proposed test is not valid Python: {str(exc)[:200]}") from exc
    has_test = any(
        (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"))
        or (isinstance(node, ast.ClassDef) and node.name.startswith("Test") and any(
            isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name.startswith("test_")
            for member in node.body))
        for node in tree.body
    )
    if not has_test:
        raise ProposalError("Proposed test contains no pytest test (a test_* function, or a Test* class with test_* methods).")
    return content


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class ProposalRequest(StrictModel):
    target_path: str = Field(max_length=MAX_PATH_CHARS)
    content: str = Field(max_length=MAX_PROPOSAL_BYTES)
    #: Who wrote the test text. An AI-written test is still entered by a person.
    origin: Literal["human", "imported_ai_review"]
    #: Id of the static or imported-AI finding this test targets, if any.
    finding_ref: str | None = Field(default=None, min_length=1, max_length=120)
    rationale: str | None = Field(default=None, max_length=2000)


class DecisionRequest(StrictModel):
    decision: Literal["approved", "rejected"]
    decided_by: str = Field(min_length=2, max_length=80)
    note: str | None = Field(default=None, max_length=1000)


def clean_name(value: str) -> str:
    name = " ".join(value.split())
    if len(name) < 2 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ProposalError("decided_by must be the name of the person deciding (at least 2 characters, no control characters).")
    return name


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_proposal(
    conn: sqlite3.Connection, *, scan_id: str, request: ProposalRequest, base_commit: str, head_commit: str,
) -> str:
    digest = hashlib.sha256(request.content.encode("utf-8")).hexdigest()
    duplicate = conn.execute(
        "SELECT 1 FROM test_proposals WHERE scan_id = ? AND target_path = ? AND content_digest = ?",
        (scan_id, request.target_path, digest),
    ).fetchone()
    if duplicate:
        raise ProposalError("The same test was already proposed for this scan at this path.", 409)
    proposal_id = str(uuid4())
    conn.execute(
        "INSERT INTO test_proposals (id, scan_id, created_at, target_path, content, content_digest, origin,"
        " finding_ref, rationale, base_commit, head_commit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (proposal_id, scan_id, now(), request.target_path, request.content, digest, request.origin,
         request.finding_ref, request.rationale, base_commit, head_commit),
    )
    return proposal_id


def insert_decision(conn: sqlite3.Connection, *, proposal_id: str, request: DecisionRequest) -> None:
    conn.execute(
        "INSERT INTO test_proposal_decisions (id, proposal_id, decision, decided_at, decided_by, note)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid4()), proposal_id, request.decision, now(), clean_name(request.decided_by), request.note),
    )


def served(conn: sqlite3.Connection, row: sqlite3.Row, *, scan_stale: bool) -> dict:
    """A stored proposal with its decision history and what follows from it.

    ``status`` is the latest decision, or ``pending``. ``eligible_to_run`` is
    true only for an approved proposal of a scan that is not stale; it says
    the human gate is passed, not that anything can or did run.
    """
    decisions = [
        {"id": d["id"], "decision": d["decision"], "decided_at": d["decided_at"], "decided_by": d["decided_by"], "note": d["note"]}
        for d in conn.execute(
            "SELECT id, decision, decided_at, decided_by, note FROM test_proposal_decisions"
            " WHERE proposal_id = ? ORDER BY decided_at, rowid", (row["id"],))
    ]
    status = decisions[-1]["decision"] if decisions else "pending"
    return {
        "id": row["id"], "scan_id": row["scan_id"], "created_at": row["created_at"],
        "target_path": row["target_path"], "content": row["content"], "content_digest": row["content_digest"],
        "origin": row["origin"], "finding_ref": row["finding_ref"], "rationale": row["rationale"],
        "base_commit": row["base_commit"], "head_commit": row["head_commit"],
        "decisions": decisions, "status": status, "stale": scan_stale,
        "eligible_to_run": status == "approved" and not scan_stale,
        "applied": False, "executed": False,
        "identity_note": IDENTITY_NOTE,
    }


PROPOSAL_COLUMNS = ("id, scan_id, created_at, target_path, content, content_digest, origin, finding_ref, rationale,"
                    " base_commit, head_commit")
