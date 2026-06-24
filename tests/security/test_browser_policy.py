from __future__ import annotations

from insane_search.adapters.browser_transport import classify_browser_request, is_same_origin_api_candidate


def test_browser_iframe_localhost_blocked() -> None:
    decision = classify_browser_request("http://localhost/admin", "iframe")
    assert not decision.ok
    assert decision.reason == "iframe:localhost_blocked"


def test_browser_xhr_private_ip_blocked() -> None:
    decision = classify_browser_request("http://10.0.0.5/api/data", "xhr")
    assert not decision.ok
    assert decision.reason.startswith("xhr:ip_blocked:")


def test_browser_popup_private_ip_blocked() -> None:
    decision = classify_browser_request("http://192.168.1.2/popup", "popup")
    assert not decision.ok
    assert decision.reason.startswith("popup:ip_blocked:")


def test_browser_public_request_allowed() -> None:
    decision = classify_browser_request("https://example.com/app.js", "script")
    assert decision.ok
    assert decision.reason == "script:public"


def test_browser_api_candidate_requires_same_origin_public_url() -> None:
    assert is_same_origin_api_candidate("https://example.com/page", "https://example.com/api/items", "xhr")
    assert is_same_origin_api_candidate("https://example.com/page", "https://example.com/graphql", "fetch")
    assert not is_same_origin_api_candidate("https://example.com/page", "https://api.example.com/api/items", "xhr")
    assert not is_same_origin_api_candidate("https://example.com/page", "http://127.0.0.1/api/items", "xhr")
