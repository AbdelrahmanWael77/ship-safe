"""Generate a disposable, completely synthetic Git repository for ShipSafe demos."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import ConfigError

BASE_FILES = {
    "README.md": """# LedgerLite (synthetic demo)

A tiny invoice service used only for ShipSafe security and regression demos.
No real customers, invoices, credentials, or payments exist here.
""",
    "app/__init__.py": "",
    "app/auth.py": '''"""Authorization helpers for synthetic invoices."""


def get_invoice_for_user(user_id: str, invoice: dict) -> dict:
    if invoice["owner_id"] != user_id:
        raise PermissionError("Invoice does not belong to this user")
    return invoice
''',
    "app/pricing.py": '''"""Precise monetary calculations."""
from decimal import Decimal, ROUND_HALF_UP


def invoice_total(unit_price: str, quantity: int) -> Decimal:
    amount = Decimal(unit_price) * Decimal(quantity)
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
''',
    "app/api.py": '''"""Stable client-facing response schema."""


def invoice_payload(invoice_id: str, total_cents: int) -> dict:
    return {"invoice_id": invoice_id, "total_cents": total_cents, "status": "ready"}
''',
    "app/orders.py": '''"""Downstream module affected by changes to auth, pricing and API."""
from app.auth import get_invoice_for_user
from app.pricing import invoice_total
from app.api import invoice_payload


def summarize_invoice(user_id: str, invoice: dict) -> dict:
    allowed = get_invoice_for_user(user_id, invoice)
    total = invoice_total(allowed["unit_price"], allowed["quantity"])
    return invoice_payload(allowed["id"], int(total * 100))
''',
    "tests/test_smoke.py": '''"""Happy-path tests intentionally miss regression edge cases."""
from app.auth import get_invoice_for_user
from app.pricing import invoice_total
from app.api import invoice_payload


def test_own_invoice_is_accessible():
    invoice = {"id": "inv-1", "owner_id": "alice"}
    assert get_invoice_for_user("alice", invoice)["id"] == "inv-1"


def test_normal_invoice_total():
    assert float(invoice_total("10.00", 2)) == 20.0


def test_response_contains_status():
    assert invoice_payload("inv-1", 1000)["status"] == "ready"
''',
}

BAD_AUTH = '''"""Authorization helpers for synthetic invoices."""


def get_invoice_for_user(user_id: str, invoice: dict) -> dict:
    # Regression: ownership verification was accidentally removed.
    return invoice
'''
BAD_PRICING = '''"""Refactored monetary calculations (contains a deliberate regression)."""


def invoice_total(unit_price: str, quantity: int) -> float:
    return round(float(unit_price) * quantity, 2)
'''
BAD_API = '''"""Changed client-facing response schema (contains a deliberate regression)."""


def invoice_payload(invoice_id: str, total_cents: int) -> dict:
    return {"invoice_id": invoice_id, "total": total_cents, "status": "ready"}
'''


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        check=True, timeout=15,
    )
    return result.stdout.strip()


def _put(root: Path, rel_path: str, data: str) -> None:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


INITIAL_COMMIT_SUBJECT = "Initial secure invoice service"

# Each demo branch is exactly one commit on top of ``main`` that writes these files.
DEMO_BRANCH_FILES = {
    "feature/release-candidate": {
        "app/auth.py": BAD_AUTH,
        "app/pricing.py": BAD_PRICING,
        "app/api.py": BAD_API,
        "README.md": BASE_FILES["README.md"] + "\nRelease candidate: simplified invoice processing.\n",
    },
    "feature/auth-regression": {"app/auth.py": BAD_AUTH},
    "feature/pricing-regression": {"app/pricing.py": BAD_PRICING},
    "feature/api-breaking": {"app/api.py": BAD_API},
    "feature/docs-only": {"README.md": BASE_FILES["README.md"] + "\nUpdated setup documentation.\n"},
    "feature/safe-cleanup": {
        "app/auth.py": BASE_FILES["app/auth.py"].replace(
            "    return invoice\n", "    # Return only after the authorization guard passes.\n    return invoice\n"
        )
    },
}


def _commit_of(root: Path, ref: str) -> str | None:
    """Full SHA of ``ref`` if it names a commit in this repository, else None."""
    try:
        return _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    except subprocess.CalledProcessError:
        return None


DEMO_AUTHOR_EMAIL = "demo@shipsafe.invalid"
#: Written into .git/config when this module creates the repository.
DEMO_MARKER = "shipsafe.demo"


def _is_generated_demo(root: Path) -> bool:
    """True when this module created the repository.

    New repositories carry the ``shipsafe.demo`` marker. Repositories seeded
    before the marker existed are recognised by their root commit: the
    subject *and* the synthetic author e-mail this module writes.
    """
    try:
        if _git(root, "config", "--get", DEMO_MARKER) == "true":
            return True
    except subprocess.CalledProcessError:
        pass
    first = _git(root, "log", "--reverse", "--format=%s%n%ae", "main").splitlines()
    return len(first) >= 2 and first[0] == INITIAL_COMMIT_SUBJECT and first[1] == DEMO_AUTHOR_EMAIL


def _foreign_changes(root: Path) -> list[str]:
    """Uncommitted changes to tracked files that this module did not make.

    An interrupted seed can leave the current demo branch with its own change
    written or staged but not committed. That change is recognised (right
    branch, right file, identical content) and is not "foreign". Anything
    else is someone's work. Untracked files are ignored: repair never removes
    or commits them.
    """
    try:
        head = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    except subprocess.CalledProcessError:
        head = ""
    expected = DEMO_BRANCH_FILES.get(head, {})
    foreign = []
    # Tracked files whose index or working tree differs from HEAD; untracked
    # files are not listed. Plain paths, one per line.
    for path in _git(root, "diff", "--name-only", "HEAD", "--").splitlines():
        try:
            ours = expected.get(path) is not None and (root / path).read_text(encoding="utf-8") == expected[path]
        except (OSError, UnicodeDecodeError):
            ours = False
        if not ours:
            foreign.append(path)
    return foreign


def ensure_demo_repo(root: Path) -> Path:
    """Create the synthetic LedgerLite repository, or repair a half-created one.

    Seeding runs several ``git`` commands; if the process is interrupted part
    way (for example Ctrl+C during the first API start), the directory is left
    with ``.git`` present but branches missing. This function is idempotent:
    a complete repository is not modified, missing or uncommitted demo
    branches are rebuilt from ``main``, and a directory that is not the
    generated demo is refused rather than written to.
    """
    root = root.resolve()
    if not (root / ".git").exists():
        if root.exists() and any(root.iterdir()):
            raise ConfigError(
                f"Demo directory is not empty and is not a Git repository; refusing to initialise it: {root}"
            )
        root.mkdir(parents=True, exist_ok=True)
        _git(root, "init", "-b", "main")
        _git(root, "config", DEMO_MARKER, "true")
    _git(root, "config", "user.name", "ShipSafe Demo")
    _git(root, "config", "user.email", DEMO_AUTHOR_EMAIL)
    # Demo commits are synthetic; never let an inherited global setting ask for a signing key.
    _git(root, "config", "commit.gpgsign", "false")

    main_sha = _commit_of(root, "main")
    if main_sha is None:
        if _git(root, "rev-list", "--all", "--max-count=1"):
            raise ConfigError(f"Demo directory holds a repository without the generated 'main'; refusing to modify it: {root}")
        for name, content in BASE_FILES.items():
            _put(root, name, content)
        _git(root, "add", "--", *BASE_FILES)
        _git(root, "commit", "-q", "-m", INITIAL_COMMIT_SUBJECT)
        main_sha = _commit_of(root, "main")
    elif not _is_generated_demo(root):
        raise ConfigError(f"Demo directory holds a repository that is not the generated demo; refusing to modify it: {root}")

    missing = [
        branch for branch in DEMO_BRANCH_FILES
        if (tip := _commit_of(root, branch)) is None or tip == main_sha  # absent, or carries no commit
    ]
    if not missing:
        return root
    # Repair rewrites the working tree. Never discard someone's edits to do it.
    dirty = _foreign_changes(root)
    if dirty:
        raise ConfigError(
            f"Demo repository needs repair (missing branches: {', '.join(missing)}) but has uncommitted "
            f"changes to {', '.join(dirty)}. Commit or discard them, or delete the directory: {root}"
        )
    for branch in missing:
        changes = DEMO_BRANCH_FILES[branch]
        _git(root, "checkout", "-q", "-f", "-B", branch, "main")
        for name, content in changes.items():
            _put(root, name, content)
        _git(root, "add", "--", *changes)  # only the demo's own files; stray files are left alone
        _git(root, "commit", "-q", "-m", f"Demo: {branch.split('/')[-1].replace('-', ' ')}")
    _git(root, "checkout", "-q", "-f", "main")
    return root


DEMO_BRANCHES = [
    {"ref": "feature/release-candidate", "label": "Release candidate · 3 injected risks", "kind": "risk"},
    {"ref": "feature/auth-regression", "label": "Authorization regression", "kind": "risk"},
    {"ref": "feature/pricing-regression", "label": "Pricing precision regression", "kind": "risk"},
    {"ref": "feature/api-breaking", "label": "Breaking API contract", "kind": "risk"},
    {"ref": "feature/docs-only", "label": "Documentation only", "kind": "safe"},
    {"ref": "feature/safe-cleanup", "label": "Safe code cleanup", "kind": "safe"},
]
