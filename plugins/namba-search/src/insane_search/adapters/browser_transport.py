"""Policy helpers for the isolated browser adapter."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from insane_search.security.url_policy import classify_url


@dataclass(frozen=True)
class BrowserRequestDecision:
    ok: bool
    reason: str
    resource_type: str


def classify_browser_request(url: str, resource_type: str = "document") -> BrowserRequestDecision:
    """Apply the shared public URL policy to every browser-discovered URL."""
    policy = classify_url(url)
    if not policy.ok:
        return BrowserRequestDecision(False, f"{resource_type}:{policy.reason}", resource_type)
    return BrowserRequestDecision(True, f"{resource_type}:public", resource_type)


def is_same_origin_api_candidate(source_url: str, discovered_url: str, resource_type: str = "") -> bool:
    """Return true for same-origin public JSON/API browser-discovered URLs."""
    source = urlsplit(source_url)
    discovered = urlsplit(discovered_url)
    if source.scheme != discovered.scheme or source.hostname != discovered.hostname:
        return False
    if (source.port or _default_port(source.scheme)) != (discovered.port or _default_port(discovered.scheme)):
        return False
    decision = classify_browser_request(discovered_url, resource_type or "api")
    if not decision.ok:
        return False
    path = (discovered.path or "").lower()
    return resource_type in {"xhr", "fetch"} or "/api/" in path or "/graphql" in path or path.endswith(".json")


def _default_port(scheme: str) -> int | None:
    if scheme == "https":
        return 443
    if scheme == "http":
        return 80
    return None
