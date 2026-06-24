#!/usr/bin/env python3
"""Local release-readiness checks that do not push or publish."""

from __future__ import annotations

import json
import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE_ROOT = PLUGIN_ROOT.parent.parent if PLUGIN_ROOT.parent.name == "plugins" else PLUGIN_ROOT
FORBIDDEN = [
    "CLAUDE_PLUGIN_ROOT",
    "CLAUDE_CONFIG_DIR",
    "AskUserQuestion",
    "mcp__playwright__",
    "run_in_background",
    "~/.claude/settings.json",
]
ALLOWLIST = {
    "docs/CODEX_PLUGIN_MIGRATION_PLAN.md",
    "docs/legacy-claude.md",
    "CHANGELOG.md",
    "CODEX_PLUGIN_IMPLEMENTATION_PROMPT.md",
    "CODEX_PLUGIN_MIGRATION_PLAN.md",
    "scripts/validate_release.py",
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _version_from_pyproject() -> str | None:
    text = (PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"^version\s*=\s*\"([^\"]+)\"", text, re.M)
    return match.group(1) if match else None


def _scan_forbidden() -> list[str]:
    hits: list[str] = []
    for path in PLUGIN_ROOT.rglob("*"):
        if path.is_dir() or ".git" in path.parts:
            continue
        rel = path.relative_to(PLUGIN_ROOT).as_posix()
        if rel in ALLOWLIST or rel.endswith(".png") or rel.endswith(".zip") or rel == ".DS_Store":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for token in FORBIDDEN:
            if token in text:
                hits.append(f"{rel}:{token}")
    return hits


def main() -> int:
    manifest = _load(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    marketplace = _load(MARKETPLACE_ROOT / ".agents" / "plugins" / "marketplace.json")
    mcp = _load(PLUGIN_ROOT / ".mcp.json")
    version = _version_from_pyproject()
    errors: list[str] = []
    if manifest.get("version") != version:
        errors.append("manifest and pyproject versions differ")
    if manifest.get("version") != "1.0.0":
        errors.append("manifest version is not 1.0.0")
    for pointer in ("composerIcon", "logo", "logoDark"):
        rel = manifest.get("interface", {}).get(pointer)
        if rel and not (PLUGIN_ROOT / rel).exists():
            errors.append(f"missing asset {pointer}:{rel}")
    if "namba-search" not in mcp:
        errors.append("missing namba-search MCP config")
    else:
        server = mcp["namba-search"]
        for arg in server.get("args", []):
            if isinstance(arg, str) and arg.startswith("./") and not (PLUGIN_ROOT / arg).exists():
                errors.append(f"missing MCP arg path:{arg}")
        if server.get("cwd") != ".":
            errors.append("MCP cwd must be '.' for plugin cache launches")
    if not marketplace.get("plugins"):
        errors.append("marketplace has no plugins")
    elif marketplace.get("name") != "namba-search":
        errors.append("marketplace name must be namba-search")
    elif marketplace["plugins"][0].get("source", {}).get("path") != "./plugins/namba-search":
        errors.append("repository marketplace must point at './plugins/namba-search'")
    skill = PLUGIN_ROOT / "skills" / "namba-search" / "SKILL.md"
    agent = PLUGIN_ROOT / "skills" / "namba-search" / "agents" / "openai.yaml"
    if not skill.exists():
        errors.append("missing namba-search Skill")
    if not agent.exists():
        errors.append("missing agents/openai.yaml")
    else:
        text = agent.read_text(encoding="utf-8")
        for rel in re.findall(r'icon_(?:small|large):\s+"?([^"\n]+)"?', text):
            if not (agent.parent.parent / rel).resolve().exists():
                errors.append(f"missing Skill metadata asset:{rel}")
    forbidden = _scan_forbidden()
    if forbidden:
        errors.extend(f"forbidden reference {hit}" for hit in forbidden)
    payload = {"ok": not errors, "version": version, "errors": errors}
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
