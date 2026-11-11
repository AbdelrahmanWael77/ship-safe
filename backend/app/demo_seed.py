"""Generate a disposable, completely synthetic Git repository for ShipSafe demos."""
from __future__ import annotations

import subprocess
from pathlib import Path

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


def ensure_demo_repo(root: Path) -> Path:
    root = root.resolve()
    if (root / ".git").exists():
        return root
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "ShipSafe Demo")
    _git(root, "config", "user.email", "demo@shipsafe.invalid")
    for name, content in BASE_FILES.items():
        _put(root, name, content)
    _git(root, "add", ".")
    _git(root, "commit", "-m", "Initial secure invoice service")

    branches = {
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
    for branch, changes in branches.items():
        _git(root, "checkout", "-b", branch, "main")
        for name, content in changes.items():
            _put(root, name, content)
        _git(root, "add", ".")
        _git(root, "commit", "-m", f"Demo: {branch.split('/')[-1].replace('-', ' ')}")
    _git(root, "checkout", "main")
    return root


DEMO_BRANCHES = [
    {"ref": "feature/release-candidate", "label": "Release candidate · 3 injected risks", "kind": "risk"},
    {"ref": "feature/auth-regression", "label": "Authorization regression", "kind": "risk"},
    {"ref": "feature/pricing-regression", "label": "Pricing precision regression", "kind": "risk"},
    {"ref": "feature/api-breaking", "label": "Breaking API contract", "kind": "risk"},
    {"ref": "feature/docs-only", "label": "Documentation only", "kind": "safe"},
    {"ref": "feature/safe-cleanup", "label": "Safe code cleanup", "kind": "safe"},
]
