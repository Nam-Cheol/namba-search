from __future__ import annotations

import os
import sys
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
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        fallback = Path(os.environ.get("TMPDIR", "/tmp")) / APP_NAME
        fallback.mkdir(parents=True, exist_ok=True)
        path = fallback
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path
