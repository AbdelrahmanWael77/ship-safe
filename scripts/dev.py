"""Start ShipSafe API and Vite UI together after installing dependencies."""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    npm = shutil.which('npm.cmd' if sys.platform == 'win32' else 'npm')
    if not npm:
        raise SystemExit('Node/npm not found. Install Node.js 20.19+ or 22+ first.')
    if not (ROOT / 'frontend' / 'node_modules').exists():
        raise SystemExit('Frontend packages missing. Run: cd frontend && npm install')
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
