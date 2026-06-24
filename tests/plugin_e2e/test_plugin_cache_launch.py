from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _frame(message: dict) -> bytes:
    raw = json.dumps(message).encode("utf-8")
    return f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw


def test_plugin_cache_path_launch(tmp_path) -> None:
    cache_root = tmp_path / "plugin-cache" / "namba-search"
    ignore = shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache")
    shutil.copytree(ROOT, cache_root, ignore=ignore)
    payload = _frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    proc = subprocess.run(
        [sys.executable, "scripts/launch_mcp.py"],
        cwd=cache_root,
        input=payload,
        capture_output=True,
        timeout=10,
    )
    assert proc.returncode == 0
    assert b"untrusted external data" in proc.stdout
    assert proc.stderr == b""
