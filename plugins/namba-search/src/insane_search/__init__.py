"""Namba Search public Python API."""

from __future__ import annotations

from .engine import Attempt, FetchResult, fetch

__version__ = "1.0.1"

__all__ = ["Attempt", "FetchResult", "fetch", "__version__"]
