"""Detect instruction-like text in fetched untrusted content."""

from __future__ import annotations

import re

SIGNALS = {
    "tool_instruction": re.compile(r"\b(use|call|invoke|run)\s+(the\s+)?(tool|shell|bash|python|browser|mcp)\b", re.I),
    "secret_request": re.compile(r"\b(api[_ -]?key|password|credential|token|secret|authorization|cookie)\b", re.I),
    "local_file_request": re.compile(r"\b(/etc/passwd|ssh key|local file|read file|home directory)\b", re.I),
    "role_override": re.compile(r"\b(ignore (all )?(previous|prior) instructions|system prompt|developer message)\b", re.I),
}


def detect_instruction_signals(text: str) -> list[str]:
    hits: list[str] = []
    for name, pattern in SIGNALS.items():
        if pattern.search(text or ""):
            hits.append(name)
    return hits
