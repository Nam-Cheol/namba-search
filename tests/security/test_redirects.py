from __future__ import annotations

import pytest

from insane_search.engine import phase0
from insane_search.engine.transport import SessionPool


class _FakeResp:
    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.status_code = status
        self.headers = headers or {}
        self.text = "ok"


def test_public_url_redirect_to_private_ip_blocked() -> None:
    def do_get(url: str):
        if url == "https://public.example/start":
            return _FakeResp(302, {"Location": "http://10.0.0.1/admin"})
        return _FakeResp(200)

    response, error = SessionPool._fetch_following(do_get, "https://public.example/start", False, 5, None)
    assert response is None
    assert error and error.startswith("ssrf_redirect_blocked:ip_blocked:10.0.0.1")


def test_public_url_redirect_to_metadata_blocked() -> None:
    def do_get(url: str):
        if url == "https://public.example/start":
            return _FakeResp(302, {"Location": "http://169.254.169.254/latest/meta-data/"})
        return _FakeResp(200)

    response, error = SessionPool._fetch_following(do_get, "https://public.example/start", False, 5, None)
    assert response is None
    assert error and error.startswith("ssrf_redirect_blocked:ip_blocked:169.254.169.254")


def test_phase0_private_redirect_error_is_not_success(monkeypatch) -> None:
    def fake_request(*args, **kwargs):
        return None, "ssrf_redirect_blocked:ip_blocked:10.0.0.1"

    monkeypatch.setattr(phase0.POOL, "request", fake_request)
    with pytest.raises(RuntimeError, match="ssrf_redirect_blocked"):
        phase0._cffi_get("https://reddit.com/r/example/.rss")
