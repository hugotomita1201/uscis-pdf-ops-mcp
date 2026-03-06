from __future__ import annotations

import subprocess
import sys


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "uscis_pdf_ops.cli", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "USCIS PDF Ops MCP server" in result.stdout

