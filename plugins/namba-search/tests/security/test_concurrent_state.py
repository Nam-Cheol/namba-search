from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from insane_search.engine import learning
from insane_search.persistence.trace_store import load_trace, store_trace


def test_concurrent_trace_writes(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("INSANE_SEARCH_DATA_DIR", str(tmp_path))

    def write_one(i: int) -> str:
        return store_trace(f"https://example.com/{i}", f"https://example.com/{i}", [], reason="test")

    with ThreadPoolExecutor(max_workers=8) as pool:
        trace_ids = list(pool.map(write_one, range(40)))

    assert len(set(trace_ids)) == 40
    assert all(load_trace(trace_id) is not None for trace_id in trace_ids)


def test_concurrent_learning_writes(tmp_path) -> None:
    path = str(tmp_path / "learned.json")
    route = {"transform": "original", "impersonate": "chrome", "referer": "self_root", "phase": "grid"}

    def write_one(i: int) -> None:
        learning.record_success(f"https://host{i % 4}.example/path?token=secret", "desktop", route, path=path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write_one, range(40)))

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    assert set(data) == {f"host{i}.example::desktop" for i in range(4)}
    assert "secret" not in json.dumps(data)
