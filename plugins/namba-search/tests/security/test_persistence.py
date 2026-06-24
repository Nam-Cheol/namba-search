from __future__ import annotations

from insane_search.engine import learning
from insane_search.engine.fetch_chain import Attempt, FetchResult
from insane_search.persistence.trace_store import load_trace, store_trace
from insane_search.service import fetch_public_url


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


def test_trace_store_permission_error_does_not_fail_fetch(monkeypatch) -> None:
    def fake_fetch(url: str, **kwargs) -> FetchResult:
        return FetchResult(
            ok=True,
            content="<html><title>Example</title><body><h1>Example Domain</h1></body></html>",
            final_url=url,
            verdict="strong_ok",
            trace=[
                Attempt(
                    phase="probe",
                    executor="curl_cffi",
                    url=url,
                    url_transform="original",
                    impersonate="safari",
                    referer="self_root",
                    status=200,
                    body_size=72,
                    verdict="strong_ok",
                )
            ],
            stop_reason="success",
        )

    def fail_store(*args, **kwargs) -> str:
        raise PermissionError("Operation not permitted")

    monkeypatch.setattr("insane_search.service.fetch", fake_fetch)
    monkeypatch.setattr("insane_search.service.store_trace", fail_store)

    payload = fetch_public_url("https://example.com/", mode="http_only", include_trace=True)

    assert payload["ok"] is True
    assert payload["trace_id"] is None
    assert "trace_store_unavailable:PermissionError" in payload["warnings"]
    assert "trace_unavailable" in payload["warnings"]
    assert payload["diagnostics"]["trace_stored"] is False
