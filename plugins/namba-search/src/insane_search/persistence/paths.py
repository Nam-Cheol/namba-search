from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

APP_NAME = "namba-search"


def user_data_dir() -> Path:
    override = os.environ.get("NAMBA_SEARCH_DATA_DIR") or os.environ.get("INSANE_SEARCH_DATA_DIR")
    if override:
        return Path(override).expanduser()
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return root / APP_NAME
    return home / ".local" / "share" / APP_NAME


def ensure_private_dir(path: Path) -> Path:
    def _writable(candidate: Path) -> bool:
        probe = candidate / f".write-test-{os.getpid()}-{uuid.uuid4().hex}"
        try:
            with open(probe, "w", encoding="utf-8") as handle:
                handle.write("ok\n")
            probe.unlink()
            return True
        except OSError:
            try:
                probe.unlink()
            except OSError:
                pass
            return False

    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        fallback = Path(os.environ.get("TMPDIR", "/tmp")) / APP_NAME
        fallback.mkdir(parents=True, exist_ok=True)
        path = fallback
    if not _writable(path):
        fallback = Path(os.environ.get("TMPDIR", "/tmp")) / APP_NAME
        fallback.mkdir(parents=True, exist_ok=True)
        path = fallback
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path
