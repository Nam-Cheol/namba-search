"""Runtime and release health checks."""

from __future__ import annotations

import importlib
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .persistence.paths import ensure_private_dir, user_data_dir


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _module_available(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


def _mcp_server_config(mcp: dict[str, Any] | None) -> dict[str, Any] | None:
    if not mcp:
        return None
    servers = mcp.get("mcpServers")
    if not isinstance(servers, dict):
        return None
    server = servers.get("namba-search")
    return server if isinstance(server, dict) else None


def run_doctor() -> dict[str, Any]:
    root = _root()
    manifest = _load_json(root / ".codex-plugin" / "plugin.json")
    mcp = _load_json(root / ".mcp.json")
    mcp_server = _mcp_server_config(mcp)
    state_dir = ensure_private_dir(user_data_dir())
    checks = {
        "python": {
            "ok": sys.version_info >= (3, 11),
            "version": platform.python_version(),
            "executable": sys.executable,
        },
        "version": {
            "ok": bool(manifest and manifest.get("version") == __version__),
            "package": __version__,
            "manifest": manifest.get("version") if manifest else None,
        },
        "manifest": {"ok": manifest is not None, "path": str(root / ".codex-plugin" / "plugin.json")},
        "mcp_config": {
            "ok": bool(mcp_server and mcp_server.get("cwd") == "."),
            "path": str(root / ".mcp.json"),
        },
        "dependencies": {
            "curl_cffi": _module_available("curl_cffi"),
            "bs4": _module_available("bs4"),
            "yaml": _module_available("yaml"),
            "playwright": _module_available("playwright"),
        },
        "browser": {
            "chrome": shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome"),
            "node": shutil.which("node"),
        },
        "state_dir": {"ok": state_dir.exists(), "path": str(state_dir)},
    }
    ok = all(v.get("ok", True) for v in checks.values() if isinstance(v, dict))
    return {"ok": ok, "version": __version__, "checks": checks}


def main() -> int:
    print(json.dumps(run_doctor(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0
