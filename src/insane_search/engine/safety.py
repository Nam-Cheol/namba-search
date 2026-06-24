"""SSRF / redirect safety guard for an agent-facing fetcher.

curl_cffi follows redirects but does NOT validate the destination (confirmed
against the official docs: there is no built-in private-IP/safe-redirect
option). Since this engine fetches attacker-influenced URLs and follows their
redirects, a hostile page could redirect to loopback, RFC-1918, link-local, or
the cloud metadata endpoint (169.254.169.254) to exfiltrate internal data.

This module provides a pure, deterministic classifier and a redirect resolver.
Default-deny for private/internal targets; opt in with allow_private=True
(env INSANE_ALLOW_PRIVATE=1) for local testing.
"""
from __future__ import annotations

import os
from urllib.parse import urljoin

from insane_search.security.url_policy import classify_url as _classify_url

ALLOWED_SCHEMES = {"http", "https"}
DEFAULT_MAX_REDIRECTS = 10


def allow_private_default() -> bool:
    return os.environ.get("INSANE_ALLOW_PRIVATE", "") in ("1", "true", "yes")


def classify_url(url: str, allow_private: bool = False) -> tuple[bool, str]:
    """(is_safe, reason). Blocks non-http(s) schemes and hosts that are — or
    DNS-resolve to — private/loopback/link-local/reserved/metadata addresses."""
    result = _classify_url(url, allow_private=allow_private)
    return result.ok, result.reason


def location_of(resp) -> str | None:
    """Case-insensitive Location header from a curl_cffi/requests response."""
    try:
        headers = {k.lower(): v for k, v in dict(getattr(resp, "headers", {}) or {}).items()}
        return headers.get("location")
    except Exception:
        return None


def is_redirect(resp) -> bool:
    try:
        return int(getattr(resp, "status_code", 0) or 0) in (301, 302, 303, 307, 308)
    except Exception:
        return False


def resolve_redirect(base_url: str, location: str) -> str:
    return urljoin(base_url, location)
