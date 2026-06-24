"""Secret-free bounded trace persistence."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from .paths import ensure_private_dir, user_data_dir
from .locks import file_lock
from ..security.url_policy import redact_url

TRACE_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_TRACE_FILES = 200
SECRET_FRAGMENT_RE = re.compile(
    r"(?i)\b(token|key|secret|password|passwd|auth|authorization|cookie|session)=([^&\s]+)"
)


def _trace_dir() -> Path:
    return ensure_private_dir(user_data_dir() / "traces")


def _sanitize_attempt(attempt: Any) -> dict[str, Any]:
    error = getattr(attempt, "error", None)
    if error:
        error = str(error).replace(str(Path.home()), "~")
        error = SECRET_FRAGMENT_RE.sub(lambda m: f"{m.group(1)}=<redacted>", error)
        error = error[:300]
    return {
        "phase": getattr(attempt, "phase", None),
        "executor": getattr(attempt, "executor", None),
        "url": redact_url(getattr(attempt, "url", None)),
        "url_transform": getattr(attempt, "url_transform", None),
        "impersonate": getattr(attempt, "impersonate", None),
        "referer": getattr(attempt, "referer", None),
        "status": getattr(attempt, "status", 0),
        "body_size": getattr(attempt, "body_size", 0),
        "verdict": getattr(attempt, "verdict", None),
        "reasons": list(getattr(attempt, "reasons", []) or [])[:10],
        "elapsed_s": getattr(attempt, "elapsed_s", 0),
        "error": error,
    }


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    if path.exists() and path.is_symlink():
        raise OSError("refusing to overwrite symlink")
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _prune() -> None:
    directory = _trace_dir()
    now = time.time()
    files = sorted(directory.glob("trace_*.json"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for path in files:
        try:
            if now - path.stat().st_mtime > TRACE_TTL_SECONDS:
                path.unlink()
        except OSError:
            pass
    files = sorted(directory.glob("trace_*.json"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for path in files[MAX_TRACE_FILES:]:
        try:
            path.unlink()
        except OSError:
            pass


def store_trace(source_url: str, final_url: str, attempts: list[Any], *, reason: str = "") -> str:
    trace_id = "trace_" + uuid.uuid4().hex[:24]
    payload = {
        "trace_id": trace_id,
        "source_url": redact_url(source_url),
        "final_url": redact_url(final_url),
        "reason": reason,
        "created_at": int(time.time()),
        "trace": [_sanitize_attempt(attempt) for attempt in attempts],
    }
    directory = _trace_dir()
    with file_lock(directory / "trace-store"):
        _prune()
        _atomic_write(directory / f"{trace_id}.json", payload)
    return trace_id


def load_trace(trace_id: str) -> dict[str, Any] | None:
    if not trace_id.startswith("trace_") or "/" in trace_id or "\\" in trace_id:
        return None
    path = _trace_dir() / f"{trace_id}.json"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload
