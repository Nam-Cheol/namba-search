from __future__ import annotations

import json

from insane_search.cli import main


def test_cli_doctor_marks_plugin_backed_fallback(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("INSANE_SEARCH_DATA_DIR", str(tmp_path))

    assert main(["doctor"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["fallback_used"] is True
    assert payload["mcp_tools_exposed"] is False
    assert payload["fallback_transport"] == "plugin_backed_cli"
    assert "current_python" in payload
    assert "plugin_runtime" in payload
    assert "runtime_marker" in payload
    assert "current" in payload["dependencies"]
    assert "plugin_runtime" in payload["dependencies"]
    assert "playwright_browser" in payload["browser"]
    assert payload["plugin_runtime"]["complete"] is False
    assert payload["runtime_marker"]["ok"] is False
    assert payload["browser"]["playwright_browser"]["ok"] is False
