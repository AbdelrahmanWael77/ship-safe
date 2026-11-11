"""Optional standalone script to generate the synthetic Git fixture."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.demo_seed import ensure_demo_repo  # noqa: E402

path = ensure_demo_repo(ROOT / 'backend' / 'demo-repo')
print(f'Demo repository ready: {path}')
