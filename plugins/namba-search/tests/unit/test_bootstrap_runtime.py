from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
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
    (root / ".codex-plugin" / "plugin.json").write_text('{"version":"1.0.1"}\n', encoding="utf-8")
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


def _fake_browser_status(module, data_dir: Path) -> dict[str, object]:
    executable = data_dir / "playwright-browsers" / "chromium-test" / "chrome"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    return {
        "name": module.BROWSER_NAME,
        "browsers_path": str(data_dir / "playwright-browsers"),
        "installed": True,
        "ok": True,
        "executable_path": str(executable),
    }


def _patch_bootstrap(monkeypatch, module, data_dir: Path, calls: dict[str, int]) -> None:
    monkeypatch.setenv("NAMBA_SEARCH_DATA_DIR", str(data_dir))
    monkeypatch.setattr(module.venv, "EnvBuilder", _fake_env_builder(module, calls))
    monkeypatch.setattr(
        module,
        "_install_playwright_browser",
        lambda python, browsers_path: _fake_browser_status(module, data_dir),
    )


def _write_runtime_python(path: Path, output: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    script = (
        f"#!{sys.executable}\n"
        "from __future__ import annotations\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        f"payload = {output!r}\n"
        "payload['argv'] = sys.argv\n"
        "payload['env'] = {\n"
        "    'NAMBA_SEARCH_RUNTIME_ACTIVE': os.environ.get('NAMBA_SEARCH_RUNTIME_ACTIVE'),\n"
        "    'PLAYWRIGHT_BROWSERS_PATH': os.environ.get('PLAYWRIGHT_BROWSERS_PATH'),\n"
        "    'PYTHONPATH': os.environ.get('PYTHONPATH'),\n"
        "}\n"
        "print(json.dumps(payload, sort_keys=True))\n"
    )
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def _write_complete_marker(module, root: Path, data_dir: Path) -> Path:
    version = module._version(root)
    runtime = data_dir / "runtime" / version
    python = module._venv_python(runtime)
    modules = {
        "curl_cffi": True,
        "bs4": True,
        "yaml": True,
        "playwright": True,
    }
    _write_runtime_python(
        python,
        {
            "runtime_python_used": True,
            "ok": True,
            "executable": str(python),
            "version": ".".join(str(part) for part in sys.version_info[:3]),
            "modules": modules,
            **modules,
        },
    )
    expected = module._expected_marker(
        version,
        module._requirements_fingerprint(root / "requirements.lock"),
        data_dir / "playwright-browsers",
    )
    module._write_marker(runtime / ".complete", expected, _fake_browser_status(module, data_dir))
    return python


def _frame(message: dict[str, object]) -> bytes:
    raw = json.dumps(message).encode("utf-8")
    return f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw


def test_bootstrap_marker_records_lockfile_and_browser_fingerprint(monkeypatch, tmp_path) -> None:
    module = _load_bootstrap_runtime()
    root = _plugin_root(tmp_path)
    data_dir = tmp_path / "data"
    calls = {"count": 0}
    _patch_bootstrap(monkeypatch, module, data_dir, calls)

    python = module.ensure_runtime(root)
    marker = data_dir / "runtime" / "1.0.1" / ".complete"
    payload = json.loads(marker.read_text(encoding="utf-8"))

    assert python == module._venv_python(data_dir / "runtime" / "1.0.1")
    assert payload["schema"] == module.MARKER_SCHEMA
    assert payload["plugin_version"] == "1.0.1"
    assert payload["requirements_sha256"] == module._requirements_fingerprint(root / "requirements.lock")
    assert payload["playwright_browser"]["name"] == "chromium"
    assert payload["playwright_browser"]["installed"] is True
    assert payload["playwright_browser"]["ok"] is True
    assert Path(payload["playwright_browser"]["executable_path"]).exists()

    assert module.ensure_runtime(root) == python
    assert calls["count"] == 1


def test_bootstrap_replaces_legacy_complete_marker(monkeypatch, tmp_path) -> None:
    module = _load_bootstrap_runtime()
    root = _plugin_root(tmp_path)
    data_dir = tmp_path / "data"
    runtime = data_dir / "runtime" / "1.0.1"
    python = module._venv_python(runtime)
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    marker = runtime / ".complete"
    marker.write_text("ok\n", encoding="utf-8")
    calls = {"count": 0}
    _patch_bootstrap(monkeypatch, module, data_dir, calls)

    assert module.ensure_runtime(root) == python

    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["requirements_sha256"] == module._requirements_fingerprint(root / "requirements.lock")
    assert payload["playwright_browser"]["ok"] is True
    assert calls["count"] == 1


def test_bootstrap_refreshes_incomplete_browser_marker(monkeypatch, tmp_path) -> None:
    module = _load_bootstrap_runtime()
    root = _plugin_root(tmp_path)
    data_dir = tmp_path / "data"
    runtime = data_dir / "runtime" / "1.0.1"
    python = module._venv_python(runtime)
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    expected = module._expected_marker(
        "1.0.1",
        module._requirements_fingerprint(root / "requirements.lock"),
        data_dir / "playwright-browsers",
    )
    marker = runtime / ".complete"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(expected), encoding="utf-8")
    calls = {"count": 0}
    _patch_bootstrap(monkeypatch, module, data_dir, calls)

    assert module.ensure_runtime(root) == python

    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["playwright_browser"]["ok"] is True
    assert calls["count"] == 1


def test_bootstrap_refreshes_marker_when_lockfile_changes(monkeypatch, tmp_path) -> None:
    module = _load_bootstrap_runtime()
    root = _plugin_root(tmp_path)
    data_dir = tmp_path / "data"
    calls = {"count": 0}
    _patch_bootstrap(monkeypatch, module, data_dir, calls)

    module.ensure_runtime(root)
    (root / "requirements.lock").write_text("# changed lockfile\n", encoding="utf-8")
    module.ensure_runtime(root)

    marker = data_dir / "runtime" / "1.0.1" / ".complete"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert payload["requirements_sha256"] == module._requirements_fingerprint(root / "requirements.lock")
    assert calls["count"] == 2


def test_run_cli_reexecs_complete_runtime(monkeypatch, tmp_path) -> None:
    module = _load_bootstrap_runtime()
    cache_root = tmp_path / "plugin-cache" / "namba-search"
    shutil.copytree(ROOT, cache_root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    data_dir = tmp_path / "data"
    monkeypatch.setenv("NAMBA_SEARCH_DATA_DIR", str(data_dir))
    python = _write_complete_marker(module, cache_root, data_dir)

    proc = subprocess.run(
        [sys.executable, "scripts/run_cli.py", "doctor"],
        cwd=cache_root,
        capture_output=True,
        text=True,
        env={**os.environ, "NAMBA_SEARCH_DATA_DIR": str(data_dir)},
        timeout=10,
    )

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["runtime_python_used"] is True
    assert payload["argv"] == [str(python), "-m", "insane_search", "doctor"]
    assert payload["env"]["NAMBA_SEARCH_RUNTIME_ACTIVE"] == "1"
    assert payload["env"]["PLAYWRIGHT_BROWSERS_PATH"] == str(data_dir / "playwright-browsers")
    assert str(cache_root / "src") in payload["env"]["PYTHONPATH"]


def test_activate_runtime_in_process_adds_runtime_paths(monkeypatch, tmp_path) -> None:
    module = _load_bootstrap_runtime()
    cache_root = tmp_path / "plugin-cache" / "namba-search"
    shutil.copytree(ROOT, cache_root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    data_dir = tmp_path / "data"
    monkeypatch.setenv("NAMBA_SEARCH_DATA_DIR", str(data_dir))
    monkeypatch.delenv(module.RUNTIME_ACTIVE_ENV, raising=False)
    _write_complete_marker(module, cache_root, data_dir)
    site_packages = (
        data_dir
        / "runtime"
        / "1.0.1"
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    site_packages.mkdir(parents=True, exist_ok=True)
    original_path = list(sys.path)
    old_runtime_active = os.environ.get(module.RUNTIME_ACTIVE_ENV)
    old_browser_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    old_pythonpath = os.environ.get("PYTHONPATH")
    monkeypatch.setattr(sys, "path", original_path.copy())

    try:
        assert module.activate_runtime_in_process(cache_root) is True

        assert os.environ[module.RUNTIME_ACTIVE_ENV] == "1"
        assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(data_dir / "playwright-browsers")
        assert str(cache_root / "src") in sys.path
        assert str(site_packages) in sys.path
        assert str(site_packages) in os.environ["PYTHONPATH"]
    finally:
        for key, value in (
            (module.RUNTIME_ACTIVE_ENV, old_runtime_active),
            ("PLAYWRIGHT_BROWSERS_PATH", old_browser_path),
            ("PYTHONPATH", old_pythonpath),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_launch_mcp_activates_complete_runtime_without_reexec(monkeypatch, tmp_path) -> None:
    module = _load_bootstrap_runtime()
    cache_root = tmp_path / "plugin-cache" / "namba-search"
    shutil.copytree(ROOT, cache_root, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__"))
    data_dir = tmp_path / "data"
    monkeypatch.setenv("NAMBA_SEARCH_DATA_DIR", str(data_dir))
    _write_complete_marker(module, cache_root, data_dir)

    proc = subprocess.run(
        [sys.executable, "scripts/launch_mcp.py"],
        cwd=cache_root,
        input=_frame({
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "doctor", "arguments": {}},
        }),
        capture_output=True,
        env={**os.environ, "NAMBA_SEARCH_DATA_DIR": str(data_dir)},
        timeout=10,
    )

    assert proc.returncode == 0
    header, raw = proc.stdout.split(b"\r\n\r\n", 1)
    assert b"Content-Length:" in header
    response = json.loads(raw)
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["plugin_runtime"]["active"] is True
    assert payload["current_python"]["executable"] == sys.executable
