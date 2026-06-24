#!/usr/bin/env python3
"""Run the Namba Search CLI from a Codex plugin checkout/cache."""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    root = _plugin_root()
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    if os.environ.get("INSANE_SEARCH_BOOTSTRAP", "0") in {"1", "true", "yes"}:
        from bootstrap_runtime import ensure_runtime

        python = ensure_runtime(root)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(src) + os.pathsep + env.get("PYTHONPATH", "")
        os.execve(str(python), [str(python), "-m", "insane_search", *sys.argv[1:]], env)
    runpy.run_module("insane_search", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
