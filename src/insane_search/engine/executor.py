"""Capability-matched executor for fallback attempts.

The fetch_chain's probe/grid phase uses curl_cffi directly. When curl can't
punch through (JS challenge, real-TLS detection), this module routes to the
right browser executor based on the profile's `capabilities_needed` tags:

    needs_real_tls_stack + needs_js_exec  → internal isolated browser
    needs_js_exec only                    → internal isolated browser
    needs_mobile_context (+ real_tls)     → internal isolated mobile browser

The browser path uses a request-scoped ephemeral context, public URL policy on
top-level and subresource requests, and no user browser profile.
"""
from __future__ import annotations

import tempfile
import time
from typing import Optional

from insane_search.adapters.browser_transport import classify_browser_request, is_same_origin_api_candidate
from insane_search.security.url_policy import classify_url

from .validators import Verdict, validate
from .waf_detector import load_profile
from .fetch_chain import Attempt


def _profile_dir_for(url: str, choice: str) -> str:
    """Return a request-scoped ephemeral profile directory."""
    del url, choice
    return tempfile.mkdtemp(prefix="namba-search-browser-")


def _pick_executor(capabilities: list[str], device_class: str) -> str:
    caps = set(capabilities or [])
    if device_class == "mobile" or "needs_mobile_context" in caps:
        if "needs_real_tls_stack" in caps:
            return "playwright_mobile_chrome"
        return "playwright_mcp_mobile"
    if "needs_real_tls_stack" in caps:
        return "playwright_real_chrome"
    if "needs_js_exec" in caps:
        return "playwright_mcp"
    return "playwright_real_chrome"  # safest general fallback


class _FakeResp:
    """Minimal response shim so validators.validate() works on Playwright HTML."""
    def __init__(self, html: str, status: int = 200, final_url: str = ""):
        self.text = html
        self.status_code = status
        self.url = final_url
        self.cookies = _FakeCookies()
        self.headers = {}


class _FakeCookies:
    class _Jar:
        def __iter__(self):
            return iter([])
    def __init__(self):
        self.jar = self._Jar()
    def __iter__(self):
        return iter([])


def run_playwright_fallback(
    url: str,
    *,
    profile_id: str,
    success_selectors: Optional[list[str]] = None,
    device_class: str = "auto",
    timeout: int = 90,
    profile_dir: Optional[str] = None,
    force_executor: Optional[str] = None,
) -> tuple[Attempt, str]:
    """Invoke the appropriate Playwright executor.

    force_executor: caller-specified executor name (from a profile's
    `fallback_when_challenge` list). When set, it overrides capability-based
    inference. Recognized values: "playwright_real_chrome",
    "playwright_mobile_chrome", "playwright_mcp".

    Returns (Attempt, html_content). Attempt.verdict reflects validation.
    """
    profile = load_profile(profile_id)
    capabilities = profile.get("capabilities_needed") or []
    choice = force_executor or _pick_executor(capabilities, device_class)

    t0 = time.time()
    att = Attempt(
        phase="fallback",
        executor=choice,
        url=url,
        url_transform="original",
        impersonate=None,
        referer="",
    )

    if choice.startswith("playwright_mcp"):
        choice = "playwright_internal"
        att.executor = choice

    policy = classify_url(url)
    if not policy.ok:
        att.error = f"unsafe_url:{policy.reason}"
        att.verdict = Verdict.UNSAFE_URL.value
        att.elapsed_s = round(time.time() - t0, 3)
        return att, ""

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        att.error = f"playwright_unavailable:{type(exc).__name__}"
        att.verdict = Verdict.BROWSER_UNAVAILABLE.value
        att.elapsed_s = round(time.time() - t0, 3)
        return att, ""

    html = ""
    final_url = url
    status = 0
    api_candidates: set[str] = set()
    tmp_profile = profile_dir or _profile_dir_for(url, choice)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context_args = {
                "accept_downloads": False,
                "ignore_https_errors": False,
            }
            if choice == "playwright_mobile_chrome" or device_class == "mobile":
                context_args.update(pw.devices.get("iPhone 13 Pro", {}))
            context = browser.new_context(**context_args)
            context.set_default_timeout(timeout * 1000)

            def _route(route):
                req_url = route.request.url
                resource_type = route.request.resource_type
                req_policy = classify_browser_request(req_url, resource_type)
                if not req_policy.ok:
                    route.abort()
                    return
                if is_same_origin_api_candidate(url, req_url, resource_type):
                    api_candidates.add(req_url)
                route.continue_()

            context.route("**/*", _route)
            page = context.new_page()

            def _close_unsafe_popup(popup):
                decision = classify_browser_request(popup.url or "about:blank", "popup")
                if not decision.ok:
                    popup.close()

            page.on("popup", _close_unsafe_popup)
            response = page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            status = response.status if response is not None else 0
            final_url = page.url
            final_policy = classify_url(final_url)
            if not final_policy.ok:
                att.error = f"unsafe_url:{final_policy.reason}"
                att.verdict = Verdict.UNSAFE_URL.value
                att.elapsed_s = round(time.time() - t0, 3)
                context.close()
                browser.close()
                return att, ""
            html = page.content()
            context.close()
            browser.close()
    except PlaywrightError as exc:
        att.error = f"browser_error:{str(exc)[:240]}"
        att.verdict = Verdict.BROWSER_UNAVAILABLE.value
        att.elapsed_s = round(time.time() - t0, 3)
        return att, ""
    except Exception as exc:
        att.error = f"{type(exc).__name__}:{str(exc)[:240]}"
        att.verdict = Verdict.UNKNOWN.value
        att.elapsed_s = round(time.time() - t0, 3)
        return att, ""
    finally:
        try:
            import shutil

            shutil.rmtree(tmp_profile, ignore_errors=True)
        except Exception:
            pass

    resp = _FakeResp(html, status=status, final_url=final_url)
    vr = validate(resp, success_selectors=success_selectors)
    att.status = status
    att.body_size = len(html)
    att.verdict = vr.verdict.value
    att.reasons = list(vr.reasons)
    if api_candidates:
        att.reasons.append(f"same_origin_api_candidates:{min(len(api_candidates), 20)}")
    att.url = final_url or url

    return att, html


def _parse_envelope(stdout: str, url: str):
    """Return (html, final_url, status, cookies, user_agent) from a JSON
    envelope, or treat stdout as raw HTML if it isn't JSON."""
    import json
    s = stdout.lstrip()
    if s[:1] == "{":
        try:
            env = json.loads(s)
            html = env.get("html", "") or ""
            final_url = env.get("finalUrl", "") or url
            status = int(env.get("status") or 0) or 200
            cookies = env.get("cookies") or []
            user_agent = env.get("userAgent") or None
            automation = env.get("automation") or None
            return html, final_url, status, cookies, user_agent, automation
        except Exception:
            pass
    return stdout, url, 200, [], None, None


def _bridge_cookies_to_pool(url: str, cookies: list, user_agent: Optional[str]) -> None:
    try:
        from .transport import POOL, pool_enabled, _host_of
        if not pool_enabled():
            return
        # Browser is real Chrome → seed the "chrome" curl identity for this host.
        POOL.inject_cookies(_host_of(url), "chrome", cookies, user_agent=user_agent)
    except Exception:
        pass
