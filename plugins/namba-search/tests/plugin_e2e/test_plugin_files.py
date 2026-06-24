from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKETPLACE_ROOT = ROOT.parent.parent if ROOT.parent.name == "plugins" else ROOT


def test_manifest_marketplace_and_assets_exist() -> None:
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    marketplace = json.loads((MARKETPLACE_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
    mcp = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "1.0.0"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert marketplace["name"] == "namba-search"
    assert marketplace["interface"]["displayName"] == "Namba Search"
    assert marketplace["plugins"][0]["source"]["path"] == "./plugins/namba-search"
    assert (MARKETPLACE_ROOT / marketplace["plugins"][0]["source"]["path"]).resolve() == ROOT.resolve()
    assert mcp["namba-search"]["cwd"] == "."
    for key in ("composerIcon", "logo", "logoDark"):
        assert (ROOT / manifest["interface"][key]).exists()


def test_skill_metadata_points_to_mcp() -> None:
    skill = (ROOT / "skills" / "namba-search" / "SKILL.md").read_text(encoding="utf-8")
    yaml = (ROOT / "skills" / "namba-search" / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert "fetch_public_url" in skill
    assert "value: \"namba-search\"" in yaml
    forbidden_playwright_tool = "mcp__" + "playwright__"
    assert forbidden_playwright_tool not in skill
