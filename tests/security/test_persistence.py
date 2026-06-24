from __future__ import annotations

from insane_search.engine import learning
from insane_search.engine.fetch_chain import Attempt
from insane_search.persistence.trace_store import load_trace, store_trace


def test_trace_store_redacts_and_excludes_body(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("INSANE_SEARCH_DATA_DIR", str(tmp_path))
    trace_id = store_trace(
        "https://example.com/a?token=secret",
        "https://example.com/a?token=secret#fragment",
        [
            Attempt(
                phase="grid",
                executor="curl_cffi",
                url="https://example.com/a?token=secret",
                url_transform="original",
                impersonate="safari",
                referer="self_root",
                status=200,
                body_size=123,
                verdict="weak_ok",
                error="request failed for https://example.com/a?token=secret",
            )
        ],
    )
    payload = load_trace(trace_id)
    assert payload is not None
    encoded = str(payload)
    assert "token=secret" not in encoded
    assert "token=<redacted>" in encoded
    assert "content" not in payload["trace"][0]


def test_learning_key_uses_hostname_not_userinfo() -> None:
    key = learning.key_for("https://user:pass@example.com/path?token=secret", "desktop")
    assert key == "example.com::desktop"
    assert "user" not in key
    assert "secret" not in key
