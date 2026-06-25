"""Runtime and release health checks."""

from __future__ import annotations

import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .persistence.paths import ensure_private_dir, user_data_dir

DEPENDENCIES = {
    "curl_cffi": "curl_cffi",
    "bs4": "bs4",
    "yaml": "yaml",
    "playwright": "playwright",
}


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _dependency_payload(modules: dict[str, bool], executable: str, version: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": all(modules.values()),
        "executable": executable,
        "version": version,
        "modules": modules,
    }
    payload.update(modules)
    return payload


def _current_dependency_status() -> dict[str, Any]:
    modules = {name: _module_available(module) for name, module in DEPENDENCIES.items()}
    return _dependency_payload(modules, sys.executable, platform.python_version())


def _python_dependency_status(python: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    if not python.is_file():
        modules = {name: False for name in DEPENDENCIES}
        payload = _dependency_payload(modules, str(python), "")
        payload["available"] = False
        payload["error"] = "runtime python missing"
        return payload
    code = """
from __future__ import annotations

import importlib.util
import json
import platform
import sys

deps = {
    "curl_cffi": "curl_cffi",
    "bs4": "bs4",
    "yaml": "yaml",
    "playwright": "playwright",
}
modules = {name: importlib.util.find_spec(module) is not None for name, module in deps.items()}
payload = {
    "ok": all(modules.values()),
    "executable": sys.executable,
    "version": platform.python_version(),
    "modules": modules,
}
payload.update(modules)
print(json.dumps(payload, sort_keys=True))
"""
    try:
        proc = subprocess.run(
            [str(python), "-c", code],
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )
    except Exception as exc:
        modules = {name: False for name in DEPENDENCIES}
        payload = _dependency_payload(modules, str(python), "")
        payload["available"] = False
        payload["error"] = f"{type(exc).__name__}:{str(exc)[:240]}"
        return payload
    if proc.returncode != 0:
        modules = {name: False for name in DEPENDENCIES}
        payload = _dependency_payload(modules, str(python), "")
        payload["available"] = False
        payload["error"] = (proc.stderr or proc.stdout or "dependency probe failed")[:500]
        return payload
    try:
        payload = json.loads(proc.stdout)
    except Exception as exc:
        modules = {name: False for name in DEPENDENCIES}
        payload = _dependency_payload(modules, str(python), "")
        payload["available"] = False
        payload["error"] = f"invalid dependency probe output:{type(exc).__name__}"
        return payload
    if isinstance(payload, dict):
        payload["available"] = True
        return payload
    modules = {name: False for name in DEPENDENCIES}
    payload = _dependency_payload(modules, str(python), "")
    payload["available"] = False
    payload["error"] = "invalid dependency probe payload"
    return payload


def _load_bootstrap_runtime(root: Path):
    path = root / "scripts" / "bootstrap_runtime.py"
    spec = importlib.util.spec_from_file_location("namba_search_bootstrap_runtime_doctor", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _runtime_status(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    module = _load_bootstrap_runtime(root)
    if module is None:
        return (
            {
                "ok": False,
                "complete": False,
                "reason": "bootstrap runtime helper missing",
                "python": "",
                "python_exists": False,
                "marker_path": "",
                "marker_exists": False,
                "playwright_browser": {"ok": False, "installed": False, "reason": "bootstrap runtime helper missing"},
            },
            {},
        )
    status = module.runtime_status(root)
    env = module.runtime_env(root)
    return status, env


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
    requested_state_dir = user_data_dir()
    state_dir = ensure_private_dir(user_data_dir())
    runtime, runtime_env = _runtime_status(root)
    runtime_python = Path(str(runtime.get("python") or ""))
    current_python = {
        "ok": sys.version_info >= (3, 11),
        "version": platform.python_version(),
        "executable": sys.executable,
        "runtime_active": bool(runtime.get("active")),
    }
    current_deps = _current_dependency_status()
    runtime_deps = _python_dependency_status(runtime_python, runtime_env)
    runtime_complete = bool(runtime.get("complete"))
    plugin_runtime_ok = runtime_complete and bool(runtime_deps.get("ok"))
    playwright_browser = runtime.get("playwright_browser")
    if not isinstance(playwright_browser, dict):
        playwright_browser = {"ok": False, "installed": False, "reason": runtime.get("reason")}
    browser_ok = runtime_complete and bool(playwright_browser.get("ok"))
    dependencies: dict[str, Any] = {name: current_deps[name] for name in DEPENDENCIES}
    dependencies.update({
        "ok": plugin_runtime_ok,
        "current": current_deps,
        "plugin_runtime": runtime_deps,
    })
    checks = {
        "python": current_python,
        "current_python": current_python,
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
        "plugin_runtime": {
            "ok": plugin_runtime_ok,
            "complete": runtime_complete,
            "reason": runtime.get("reason"),
            "active": runtime.get("active"),
            "data_dir": runtime.get("data_dir"),
            "runtime_dir": runtime.get("runtime_dir"),
            "python": runtime.get("python"),
            "python_exists": runtime.get("python_exists"),
            "playwright_browsers_path": runtime.get("playwright_browsers_path"),
        },
        "runtime_marker": {
            "ok": runtime_complete,
            "path": runtime.get("marker_path"),
            "exists": runtime.get("marker_exists"),
            "reason": runtime.get("reason"),
            "payload": runtime.get("marker"),
            "requirements_sha256": runtime.get("requirements_sha256"),
        },
        "dependencies": dependencies,
        "browser": {
            "ok": browser_ok,
            "chrome": shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome"),
            "node": shutil.which("node"),
            "playwright_browser": playwright_browser,
        },
        "state_dir": {
            "ok": state_dir.exists(),
            "path": str(state_dir),
            "requested_path": str(requested_state_dir),
            "fallback_used": state_dir != requested_state_dir,
        },
    }
    ok = all(v.get("ok", True) for v in checks.values() if isinstance(v, dict))
    return {
        "ok": ok,
        "version": __version__,
        "checks": checks,
        "current_python": checks["current_python"],
        "plugin_runtime": checks["plugin_runtime"],
        "runtime_marker": checks["runtime_marker"],
        "dependencies": checks["dependencies"],
        "browser": checks["browser"],
    }


def main() -> int:
    print(json.dumps(run_doctor(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0
