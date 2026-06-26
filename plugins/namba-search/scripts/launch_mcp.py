#!/usr/bin/env python3
"""Launch the Namba Search MCP server from a Codex plugin checkout/cache."""

from __future__ import annotations

import json
import os
import runpy
import sys
from datetime import datetime, timezone
from pathlib import Path


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _trace_launch(event: str, **fields) -> None:
    path = os.environ.get("NAMBA_SEARCH_MCP_TRACE_PATH")
    if not path:
        return
    try:
        payload = {
            "event": event,
            "ts": datetime.now(timezone.utc).isoformat(),
            **fields,
        }
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except Exception:
        pass


def main() -> int:
    root = _plugin_root()
    _trace_launch("launch_start", executable=sys.executable, root=str(root))
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    _trace_launch("launch_run_module", src=str(src))
    runpy.run_module("insane_search.mcp_server", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
