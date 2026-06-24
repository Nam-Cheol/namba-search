#!/usr/bin/env python3
"""Per-user runtime bootstrap for optional plugin dependencies."""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path


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
    import json

    manifest = json.loads((plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    return str(manifest["version"])


def _venv_python(runtime: Path) -> Path:
    if os.name == "nt":
        return runtime / "Scripts" / "python.exe"
    return runtime / "bin" / "python"


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


def ensure_runtime(plugin_root: str | Path) -> Path:
    root = Path(plugin_root)
    version = _version(root)
    runtime = _data_dir() / "runtime" / version
    marker = runtime / ".complete"
    python = _venv_python(runtime)
    if marker.exists() and python.exists():
        return python

    data = _data_dir()
    data.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(data, 0o700)
    except OSError:
        pass

    with _lock_file(data / "runtime.lock"):
        if marker.exists() and python.exists():
            return python
        runtime.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True, clear=False).create(runtime)
        req = root / "requirements.lock"
        if _requirements_have_packages(req):
            cmd = [str(python), "-m", "pip", "install", "--require-hashes", "-r", str(req)]
            try:
                subprocess.run(cmd, check=True, stdout=sys.stderr, stderr=sys.stderr)
            except subprocess.CalledProcessError:
                print("namba-search bootstrap failed.", file=sys.stderr)
                print("Reproduce with:", " ".join(cmd), file=sys.stderr)
                raise
        tmp = runtime / ".complete.tmp"
        tmp.write_text("ok\n", encoding="utf-8")
        os.replace(tmp, marker)
    return python


def main() -> int:
    python = ensure_runtime(Path(__file__).resolve().parents[1])
    print(python)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
