#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP_VENV="$(mktemp -d)"
python3 -m venv "$TMP_VENV"
source "$TMP_VENV/bin/activate"
python -m pip install -U pip
python -m pip install "$ROOT/dist/"*.whl
uscis-pdf-ops-mcp --help >/dev/null
python - <<'PY'
import subprocess
import time

proc = subprocess.Popen(["uscis-pdf-ops-mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(1)
if proc.poll() is not None:
    raise SystemExit(f"CLI exited early: {proc.stderr.read().decode()}")
proc.terminate()
proc.wait(timeout=5)
PY
deactivate
rm -rf "$TMP_VENV"
