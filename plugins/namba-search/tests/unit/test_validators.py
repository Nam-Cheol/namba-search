from __future__ import annotations

from insane_search.engine.validators import Verdict, validate


class _Cookie:
    def __init__(self, name: str, value: str) -> None:
        self.name = name
        self.value = value


class _Cookies:
    def __init__(self, cookies: dict[str, str] | None = None) -> None:
        self.jar = [_Cookie(k, v) for k, v in (cookies or {}).items()]


class _Resp:
    def __init__(self, status: int = 200, text: str = "", headers: dict[str, str] | None = None) -> None:
        self.status_code = status
        self.text = text
        self.content = text.encode()
        self.headers = headers or {}
        self.cookies = _Cookies()


def test_403_json_is_not_success() -> None:
    result = validate(_Resp(403, '{"ok":true}', {"Content-Type": "application/json"}))
    assert result.verdict == Verdict.BLOCKED
    assert not result.ok


def test_403_large_html_is_not_success() -> None:
    result = validate(_Resp(403, "<html><body>" + ("x" * 6000) + "</body></html>"))
    assert result.verdict == Verdict.BLOCKED
    assert not result.ok


def test_200_login_wall() -> None:
    html = "<html><body><form action='/login'><input type='password'></form></body></html>"
    result = validate(_Resp(200, html))
    assert result.verdict == Verdict.LOGIN_WALL
    assert not result.ok


def test_200_paywall() -> None:
    html = "<html><body><main>Subscribe to continue reading this article.</main></body></html>"
    result = validate(_Resp(200, html))
    assert result.verdict == Verdict.PAYWALL
    assert not result.ok


def test_200_captcha_required() -> None:
    html = "<html><body><div class='g-recaptcha'>check</div></body></html>"
    result = validate(_Resp(200, html))
    assert result.verdict == Verdict.CAPTCHA_REQUIRED
    assert not result.ok


def test_duckduckgo_image_challenge_is_captcha_required() -> None:
    html = (
        "<html><body>Unfortunately, bots use DuckDuckGo too. "
        "Please complete the following challenge to confirm this search was made by a human. "
        "Select all squares containing a duck.</body></html>"
    )
    result = validate(_Resp(202, html))
    assert result.verdict == Verdict.CAPTCHA_REQUIRED
    assert not result.ok


def test_204_with_selector_is_invalid_content() -> None:
    result = validate(_Resp(204, ""), success_selectors=["article"])
    assert result.verdict == Verdict.INVALID_CONTENT
    assert not result.ok


def test_2xx_json_can_succeed() -> None:
    result = validate(_Resp(200, '{"items":[1]}', {"Content-Type": "application/json"}))
    assert result.verdict == Verdict.WEAK_OK
    assert result.ok
