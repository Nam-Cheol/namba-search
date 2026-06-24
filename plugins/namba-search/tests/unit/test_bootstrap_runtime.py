from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_bootstrap_runtime():
    path = ROOT / "scripts" / "bootstrap_runtime.py"
    spec = importlib.util.spec_from_file_location("namba_search_bootstrap_runtime", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _plugin_root(tmp_path: Path) -> Path:
    root = tmp_path / "plugin"
    (root / ".codex-plugin").mkdir(parents=True)
    (root / ".codex-plugin" / "plugin.json").write_text('{"version":"1.0.0"}\n', encoding="utf-8")
    (root / "requirements.lock").write_text("# no packages for this test\n", encoding="utf-8")
    return root


def _fake_env_builder(module, calls: dict[str, int]):
    class FakeEnvBuilder:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        def create(self, runtime):
            calls["count"] += 1
            python = module._venv_python(Path(runtime))
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("#!/bin/sh\n", encoding="utf-8")

    return FakeEnvBuilder


def test_bootstrap_marker_records_lockfile_fingerprint(monkeypatch, tmp_path) -> None:
    module = _load_bootstrap_runtime()
    root = _plugin_root(tmp_path)
    data_dir = tmp_path / "data"
    calls = {"count": 0}
    monkeypatch.setenv("NAMBA_SEARCH_DATA_DIR", str(data_dir))
    monkeypatch.setattr(module.venv, "EnvBuilder", _fake_env_builder(module, calls))

    python = module.ensure_runtime(root)
    marker = data_dir / "runtime" / "1.0.0" / ".complete"
    payload = json.loads(marker.read_text(encoding="utf-8"))

    assert python == module._venv_python(data_dir / "runtime" / "1.0.0")
    assert payload["schema"] == module.MARKER_SCHEMA
    assert payload["plugin_version"] == "1.0.0"
    assert payload["requirements_sha256"] == module._requirements_fingerprint(root / "requirements.lock")

    assert module.ensure_runtime(root) == python
    assert calls["count"] == 1


def test_bootstrap_replaces_legacy_complete_marker(monkeypatch, tmp_path) -> None:
    module = _load_bootstrap_runtime()
    root = _plugin_root(tmp_path)
    data_dir = tmp_path / "data"
    runtime = data_dir / "runtime" / "1.0.0"
    python = module._venv_python(runtime)
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    marker = runtime / ".complete"
    marker.write_text("ok\n", encoding="utf-8")
    calls = {"count": 0}
    monkeypatch.setenv("NAMBA_SEARCH_DATA_DIR", str(data_dir))
    monkeypatch.setattr(module.venv, "EnvBuilder", _fake_env_builder(module, calls))

    assert module.ensure_runtime(root) == python

    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["requirements_sha256"] == module._requirements_fingerprint(root / "requirements.lock")
    assert calls["count"] == 1


def test_bootstrap_refreshes_marker_when_lockfile_changes(monkeypatch, tmp_path) -> None:
    module = _load_bootstrap_runtime()
    root = _plugin_root(tmp_path)
    data_dir = tmp_path / "data"
    calls = {"count": 0}
    monkeypatch.setenv("NAMBA_SEARCH_DATA_DIR", str(data_dir))
    monkeypatch.setattr(module.venv, "EnvBuilder", _fake_env_builder(module, calls))

    module.ensure_runtime(root)
    (root / "requirements.lock").write_text("# changed lockfile\n", encoding="utf-8")
    module.ensure_runtime(root)

    marker = data_dir / "runtime" / "1.0.0" / ".complete"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["requirements_sha256"] == module._requirements_fingerprint(root / "requirements.lock")
    assert calls["count"] == 2
