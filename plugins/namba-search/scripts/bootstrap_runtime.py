#!/usr/bin/env python3
"""Per-user runtime bootstrap for optional plugin dependencies."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
import venv
from pathlib import Path

MARKER_SCHEMA = 2
BOOTSTRAP_ENV = "INSANE_SEARCH_BOOTSTRAP"
RUNTIME_ACTIVE_ENV = "NAMBA_SEARCH_RUNTIME_ACTIVE"
BROWSER_NAME = "chromium"
BROWSERS_DIRNAME = "playwright-browsers"


def _data_dir() -> Path:
    override = os.environ.get("NAMBA_SEARCH_DATA_DIR") or os.environ.get("INSANE_SEARCH_DATA_DIR")
    if override:
        return Path(override).expanduser()
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "namba-search"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / "namba-search"
    return home / ".local" / "share" / "namba-search"


def _version(plugin_root: Path) -> str:
    manifest = json.loads((plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return str(manifest["version"])


def _venv_python(runtime: Path) -> Path:
    if os.name == "nt":
        return runtime / "Scripts" / "python.exe"
    return runtime / "bin" / "python"


def _browser_path(data_dir: Path | None = None) -> Path:
    return (data_dir or _data_dir()) / BROWSERS_DIRNAME


def _lock_file(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+", encoding="utf-8")
    if os.name != "nt":
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _requirements_have_packages(path: Path) -> bool:
    if not path.exists():
        return False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            return True
    return False


def _requirements_fingerprint(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expected_marker(version: str, requirements_sha256: str, browsers_path: Path) -> dict[str, object]:
    return {
        "schema": MARKER_SCHEMA,
        "plugin_version": version,
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "requirements_sha256": requirements_sha256,
        "playwright_browser": {
            "name": BROWSER_NAME,
            "browsers_path": str(browsers_path),
        },
    }


def _read_marker(marker: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _runtime_complete_reason(marker: Path, python: Path, expected: dict[str, object]) -> tuple[bool, str]:
    if not python.is_file():
        return False, "runtime python missing"
    if not marker.exists():
        return False, "runtime marker missing"
    payload = _read_marker(marker)
    if payload is None:
        return False, "runtime marker invalid"
    for key, value in expected.items():
        if key == "playwright_browser":
            continue
        if payload.get(key) != value:
            return False, f"runtime marker {key} mismatch"
    browser_expected = expected.get("playwright_browser")
    browser = payload.get("playwright_browser")
    if not isinstance(browser_expected, dict) or not isinstance(browser, dict):
        return False, "browser marker missing"
    for key in ("name", "browsers_path"):
        if browser.get(key) != browser_expected.get(key):
            return False, f"browser marker {key} mismatch"
    if browser.get("installed") is not True or browser.get("ok") is not True:
        return False, "browser binary missing"
    executable = browser.get("executable_path")
    if not isinstance(executable, str) or not executable:
        return False, "browser executable missing"
    if not Path(executable).exists():
        return False, "browser binary missing"
    return True, "complete"


def _runtime_complete(marker: Path, python: Path, expected: dict[str, object]) -> bool:
    ok, _reason = _runtime_complete_reason(marker, python, expected)
    return ok


def _browser_env(browsers_path: Path, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)
    return env


def runtime_env(plugin_root: str | Path, base_env: dict[str, str] | None = None) -> dict[str, str]:
    root = Path(plugin_root)
    env = _browser_env(_browser_path(), base_env)
    src = root / "src"
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(src) if not current_pythonpath else str(src) + os.pathsep + current_pythonpath
    env[RUNTIME_ACTIVE_ENV] = "1"
    return env


def _command_text(cmd: list[str], env: dict[str, str] | None = None) -> str:
    prefix = ""
    if env and "PLAYWRIGHT_BROWSERS_PATH" in env:
        prefix = "PLAYWRIGHT_BROWSERS_PATH=" + shlex.quote(env["PLAYWRIGHT_BROWSERS_PATH"]) + " "
    return prefix + " ".join(shlex.quote(part) for part in cmd)


def _playwright_browser_status(python: Path, browsers_path: Path) -> dict[str, object]:
    code = """
from __future__ import annotations

import json
import os
from pathlib import Path

payload = {
    "name": "chromium",
    "browsers_path": os.environ.get("PLAYWRIGHT_BROWSERS_PATH"),
    "installed": False,
    "ok": False,
}
try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        executable = pw.chromium.executable_path
    payload["executable_path"] = executable
    payload["installed"] = Path(executable).exists()
    payload["ok"] = payload["installed"]
except Exception as exc:
    payload["error"] = f"{type(exc).__name__}:{str(exc)[:240]}"
print(json.dumps(payload, sort_keys=True))
"""
    if not python.is_file():
        return {
            "name": BROWSER_NAME,
            "browsers_path": str(browsers_path),
            "installed": False,
            "ok": False,
            "error": "runtime python missing",
        }
    env = _browser_env(browsers_path)
    proc = subprocess.run(
        [str(python), "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    if proc.returncode != 0:
        return {
            "name": BROWSER_NAME,
            "browsers_path": str(browsers_path),
            "installed": False,
            "ok": False,
            "error": (proc.stderr or proc.stdout or "playwright browser probe failed")[:500],
        }
    try:
        payload = json.loads(proc.stdout)
    except Exception as exc:
        return {
            "name": BROWSER_NAME,
            "browsers_path": str(browsers_path),
            "installed": False,
            "ok": False,
            "error": f"invalid probe output:{type(exc).__name__}",
        }
    if not isinstance(payload, dict):
        return {
            "name": BROWSER_NAME,
            "browsers_path": str(browsers_path),
            "installed": False,
            "ok": False,
            "error": "invalid probe payload",
        }
    payload.setdefault("name", BROWSER_NAME)
    payload.setdefault("browsers_path", str(browsers_path))
    payload["ok"] = bool(payload.get("ok"))
    payload["installed"] = bool(payload.get("installed"))
    return payload


def _install_playwright_browser(python: Path, browsers_path: Path) -> dict[str, object]:
    cmd = [str(python), "-m", "playwright", "install", BROWSER_NAME]
    env = _browser_env(browsers_path)
    try:
        subprocess.run(cmd, check=True, stdout=sys.stderr, stderr=sys.stderr, env=env)
    except subprocess.CalledProcessError:
        print("namba-search bootstrap failed.", file=sys.stderr)
        print("Reproduce with:", _command_text(cmd, env), file=sys.stderr)
        raise
    status = _playwright_browser_status(python, browsers_path)
    if not status.get("ok"):
        print("namba-search bootstrap failed.", file=sys.stderr)
        print("Playwright browser binary is missing after install.", file=sys.stderr)
        print("Reproduce with:", _command_text(cmd, env), file=sys.stderr)
        raise RuntimeError("Playwright browser binary missing")
    return status


def _write_marker(marker: Path, expected: dict[str, object], browser_status: dict[str, object]) -> None:
    payload = dict(expected)
    browser = dict(payload.get("playwright_browser", {}))
    browser.update(browser_status)
    browser["name"] = BROWSER_NAME
    browser["browsers_path"] = str(_browser_path())
    payload["playwright_browser"] = browser
    tmp = marker.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, marker)


def runtime_status(plugin_root: str | Path) -> dict[str, object]:
    root = Path(plugin_root)
    version = _version(root)
    data = _data_dir()
    runtime = data / "runtime" / version
    marker = runtime / ".complete"
    python = _venv_python(runtime)
    browsers_path = _browser_path(data)
    expected = _expected_marker(version, _requirements_fingerprint(root / "requirements.lock"), browsers_path)
    complete, reason = _runtime_complete_reason(marker, python, expected)
    payload = _read_marker(marker)
    browser = payload.get("playwright_browser") if isinstance(payload, dict) else None
    if not isinstance(browser, dict):
        browser = {
            "name": BROWSER_NAME,
            "browsers_path": str(browsers_path),
            "installed": False,
            "ok": False,
            "reason": reason,
        }
    return {
        "ok": complete,
        "complete": complete,
        "reason": reason,
        "data_dir": str(data),
        "runtime_dir": str(runtime),
        "python": str(python),
        "python_exists": python.exists(),
        "marker_path": str(marker),
        "marker_exists": marker.exists(),
        "marker": payload,
        "requirements_sha256": expected["requirements_sha256"],
        "playwright_browsers_path": str(browsers_path),
        "playwright_browser": browser,
        "active": os.environ.get(RUNTIME_ACTIVE_ENV) == "1",
    }


def ensure_runtime(plugin_root: str | Path) -> Path:
    root = Path(plugin_root)
    version = _version(root)
    data = _data_dir()
    runtime = data / "runtime" / version
    marker = runtime / ".complete"
    python = _venv_python(runtime)
    req = root / "requirements.lock"
    browsers_path = _browser_path(data)
    expected = _expected_marker(version, _requirements_fingerprint(req), browsers_path)
    if _runtime_complete(marker, python, expected):
        return python

    data.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(data, 0o700)
    except OSError:
        pass

    with _lock_file(data / "runtime.lock"):
        if _runtime_complete(marker, python, expected):
            return python
        runtime.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True, clear=False).create(runtime)
        if _requirements_have_packages(req):
            cmd = [str(python), "-m", "pip", "install", "--require-hashes", "-r", str(req)]
            try:
                subprocess.run(cmd, check=True, stdout=sys.stderr, stderr=sys.stderr)
            except subprocess.CalledProcessError:
                print("namba-search bootstrap failed.", file=sys.stderr)
                print("Reproduce with:", _command_text(cmd), file=sys.stderr)
                raise
        browser_status = _install_playwright_browser(python, browsers_path)
        _write_marker(marker, expected, browser_status)
    return python


def main() -> int:
    python = ensure_runtime(Path(__file__).resolve().parents[1])
    print(python)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
