"""Start ShipSafe API and Vite UI together after installing dependencies."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env_file(path: Path) -> list[str]:
    """Apply SHIPSAFE_* entries from a local .env file to this process.

    Only plain ``SHIPSAFE_NAME=value`` lines are read. Values are taken
    literally (no shell expansion, no command substitution). Variables already
    set in the real environment win. Returns the names that were applied.
    """
    applied = []
    if not path.is_file():
        return applied
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if name.startswith("SHIPSAFE_") and name not in os.environ:
            os.environ[name] = value
            applied.append(name)
    return applied


def main() -> None:
    npm = shutil.which('npm.cmd' if sys.platform == 'win32' else 'npm')
    if not npm:
        raise SystemExit('Node/npm not found. Install Node.js 20.19+ or 22+ first.')
    if not (ROOT / 'frontend' / 'node_modules').exists():
        raise SystemExit('Frontend packages missing. Run: cd frontend && npm install')
    applied = load_env_file(ROOT / '.env')
    if applied:
        print(f"Loaded from .env: {', '.join(applied)}", flush=True)
    # Both servers bind to loopback only. Do not change these hosts to expose
    # the unauthenticated development API on a network interface.
    commands = [
        ([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--reload'], ROOT / 'backend', 'API'),
        ([npm, 'run', 'dev'], ROOT / 'frontend', 'UI'),
    ]
    children = []
    try:
        for args, cwd, label in commands:
            process = subprocess.Popen(args, cwd=cwd)
            children.append(process)
            print(f'{label} started (pid={process.pid})', flush=True)
        print('ShipSafe UI: http://127.0.0.1:5173', flush=True)
        print('FastAPI docs: http://127.0.0.1:8000/docs', flush=True)
        while all(proc.poll() is None for proc in children):
            time.sleep(.5)
    except KeyboardInterrupt:
        print('\nStopping ShipSafe…', flush=True)
    finally:
        for proc in children:
            if proc.poll() is None:
                proc.terminate()
        for proc in children:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

if __name__ == '__main__':
    main()
