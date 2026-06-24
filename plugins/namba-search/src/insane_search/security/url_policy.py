"""Public URL policy and trace-safe URL redaction."""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ALLOWED_SCHEMES = {"http", "https"}
SECRET_QUERY_RE = re.compile(r"(token|key|secret|password|passwd|auth|sig|signature|session|cookie)", re.I)
METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
}


@dataclass(frozen=True)
class PolicyResult:
    ok: bool
    reason: str
    normalized_url: str | None = None


def _canonical_host(host: str) -> str:
    host = (host or "").strip().rstrip(".").lower()
    try:
        return host.encode("idna").decode("ascii")
    except Exception:
        return host


def _ip_blocked(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    return (
        ip in METADATA_IPS
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def domain_matches(host: str, allowed_domain: str) -> bool:
    """Exact or dot-boundary suffix match."""
    h = _canonical_host(host)
    d = _canonical_host(allowed_domain)
    return h == d or h.endswith("." + d)


def classify_url(url: str, *, allow_private: bool = False, resolve_dns: bool = True) -> PolicyResult:
    try:
        parts = urlsplit(url)
    except Exception as exc:
        return PolicyResult(False, f"parse_error:{type(exc).__name__}")
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        return PolicyResult(False, f"scheme_blocked:{parts.scheme or 'none'}")
    if parts.username or parts.password:
        return PolicyResult(False, "userinfo_blocked")
    if not parts.hostname:
        return PolicyResult(False, "missing_host")

    host = _canonical_host(parts.hostname)
    if host in {"localhost", "localhost.localdomain"}:
        return PolicyResult(False, "localhost_blocked")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not allow_private and resolve_dns:
            try:
                port = parts.port or (443 if parts.scheme == "https" else 80)
                infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
            except Exception:
                infos = []
            for info in infos:
                ip_text = str(info[4][0])
                if _ip_blocked(ip_text):
                    return PolicyResult(False, f"resolved_internal:{host}->{ip_text}")
    else:
        if not allow_private and _ip_blocked(host):
            return PolicyResult(False, f"ip_blocked:{host}")

    netloc = host
    if parts.port:
        netloc = f"{host}:{parts.port}"
    normalized = urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))
    return PolicyResult(True, "public", normalized)


def redact_url(url: str | None) -> str | None:
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except Exception:
        return "<invalid-url>"
    host = _canonical_host(parts.hostname or "")
    netloc = host
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    kept: list[tuple[str, str]] = []
    redacted = False
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if SECRET_QUERY_RE.search(key):
            kept.append((key, "<redacted>"))
            redacted = True
        else:
            kept.append((key, value))
    query = urlencode(kept, doseq=True) if kept else ""
    if parts.username or parts.password:
        redacted = True
    path = parts.path or "/"
    result = urlunsplit((parts.scheme.lower(), netloc, path, query, ""))
    return result + ("#redacted" if redacted else "")
