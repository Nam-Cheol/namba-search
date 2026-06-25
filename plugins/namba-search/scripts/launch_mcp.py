#!/usr/bin/env python3
"""Launch the Namba Search MCP server from a Codex plugin checkout/cache."""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _truthy(value: str | None) -> bool:
    return value is not None and value.lower() in {"1", "true", "yes"}


def _maybe_reexec_runtime(root: Path) -> None:
    if os.environ.get("NAMBA_SEARCH_RUNTIME_ACTIVE") == "1":
        return
    from bootstrap_runtime import BOOTSTRAP_ENV, ensure_runtime, runtime_env, runtime_status

    if _truthy(os.environ.get(BOOTSTRAP_ENV)):
        python = ensure_runtime(root)
    else:
        status = runtime_status(root)
        if not status.get("complete"):
            return
        python = Path(str(status["python"]))
    if python.resolve() == Path(sys.executable).resolve():
        return
    os.execve(str(python), [str(python), "-m", "insane_search.mcp_server", *sys.argv[1:]], runtime_env(root))


def main() -> int:
    root = _plugin_root()
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    _maybe_reexec_runtime(root)
    runpy.run_module("insane_search.mcp_server", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
