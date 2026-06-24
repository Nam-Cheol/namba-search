"""High-level service contract used by the MCP tools.

The service owns policy, output shaping, sanitation, and trace persistence.
The lower-level engine remains responsible for the public route planner,
HTTP/TLS attempts, WAF detection, and legacy fetch result model.
"""

from __future__ import annotations

import json
import time
from typing import Any

from .engine import fetch
from .extraction.html_to_text import extract_readable_text
from .extraction.injection_signals import detect_instruction_signals
from .persistence.trace_store import load_trace, store_trace
from .security.url_policy import classify_url, redact_url

MIN_DEADLINE_MS = 1_000
MAX_DEADLINE_MS = 180_000
MIN_MAX_BYTES = 8_192
MAX_MAX_BYTES = 5_000_000
MAX_URLS = 10
DEFAULT_TRUST = "untrusted_external_content"


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _content_type_for(content: str) -> str:
    stripped = (content or "").lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "application/json"
    if "<html" in stripped[:500].lower() or "<!doctype html" in stripped[:500].lower():
        return "text/html"
    return "text/plain"


def _metadata_for(content: str, content_type: str) -> dict[str, Any]:
    if "json" in content_type:
        return {"description": None, "published_at": None, "author": None}
    extracted = extract_readable_text(content)
    return {
        "description": extracted.get("description"),
        "published_at": extracted.get("published_at"),
        "author": extracted.get("author"),
    }


def _title_for(content: str, content_type: str) -> str | None:
    if "json" in content_type:
        return None
    return extract_readable_text(content).get("title") or None


def _sanitize_content(content: str, content_type: str, max_bytes: int) -> tuple[str, list[str], bool]:
    warnings: list[str] = []
    if "json" in content_type:
        try:
            parsed = json.loads(content)
            text = json.dumps(parsed, ensure_ascii=False, indent=2)
        except Exception:
            text = content
    elif "html" in content_type:
        extracted = extract_readable_text(content)
        text = extracted.get("text", "")
        warnings.extend(extracted.get("warnings", []))
    else:
        text = content

    signals = detect_instruction_signals(text)
    if signals:
        warnings.extend(f"instruction_signal:{signal}" for signal in signals[:5])

    encoded = text.encode("utf-8", "ignore")
    if len(encoded) > max_bytes:
        text = encoded[:max_bytes].decode("utf-8", "ignore")
        warnings.append("content_truncated_to_max_bytes")
    return text.strip(), warnings, bool(signals)


def _result_template(
    *,
    ok: bool,
    verdict: str,
    source_url: str,
    final_url: str | None = None,
    title: str | None = None,
    content_type: str | None = None,
    content: str = "",
    metadata: dict[str, Any] | None = None,
    access_path: dict[str, Any] | None = None,
    trust: str = DEFAULT_TRUST,
    instructions_detected: bool = False,
    warnings: list[str] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "verdict": verdict,
        "source_url": redact_url(source_url),
        "final_url": redact_url(final_url or source_url),
        "title": title,
        "content_type": content_type,
        "content": content,
        "metadata": metadata or {"description": None, "published_at": None, "author": None},
        "access_path": access_path or {},
        "trust": trust,
        "instructions_detected": instructions_detected,
        "warnings": warnings or [],
        "trace_id": trace_id,
    }


def _map_engine_verdict(raw: str, trace_errors: list[str]) -> str:
    if raw == "suspect_ok":
        return "suspect"
    if raw == "unknown":
        if any(err.startswith("ssrf_") for err in trace_errors):
            return "unsafe_url"
        return "network_error"
    if raw in {"strong_ok", "weak_ok", "suspect", "blocked", "challenge", "rate_limited",
               "auth_required", "login_wall", "paywall", "consent_wall", "captcha_required",
               "not_found", "browser_unavailable", "unsafe_url", "deadline_exceeded",
               "response_too_large", "network_error", "invalid_content", "internal_error"}:
        return raw
    return "internal_error"


def _access_path_from_trace(trace: list[Any]) -> dict[str, Any]:
    for attempt in reversed(trace):
        verdict = getattr(attempt, "verdict", "")
        if verdict in {"strong_ok", "weak_ok"}:
            return {
                "phase": getattr(attempt, "phase", None),
                "executor": getattr(attempt, "executor", None),
                "transform": getattr(attempt, "url_transform", None),
            }
    if trace:
        last = trace[-1]
        return {
            "phase": getattr(last, "phase", None),
            "executor": getattr(last, "executor", None),
            "transform": getattr(last, "url_transform", None),
        }
    return {}


def fetch_public_url(
    url: str,
    *,
    selector: str | list[str] | None = None,
    device: str = "auto",
    mode: str = "auto",
    deadline_ms: int = 45_000,
    max_bytes: int = 2_000_000,
    include_trace: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    deadline_ms = _clamp(deadline_ms, MIN_DEADLINE_MS, MAX_DEADLINE_MS)
    max_bytes = _clamp(max_bytes, MIN_MAX_BYTES, MAX_MAX_BYTES)
    policy = classify_url(url)
    if not policy.ok:
        trace_id = store_trace(url, url, [], reason=policy.reason)
        return _result_template(
            ok=False,
            verdict="unsafe_url",
            source_url=url,
            warnings=[policy.reason],
            trace_id=trace_id,
        )

    selectors = [selector] if isinstance(selector, str) else list(selector or [])
    timeout_s = max(2, min(25, deadline_ms // 1000))
    max_attempts = max(1, min(12, deadline_ms // max(1000, timeout_s * 1000)))
    enable_playwright = mode != "http_only"

    try:
        result = fetch(
            url,
            success_selectors=selectors or None,
            device_class=device,
            timeout=timeout_s,
            max_attempts=max_attempts,
            enable_playwright=enable_playwright,
            enable_phase0=True,
        )
    except Exception as exc:
        trace_id = store_trace(url, url, [], reason=f"{type(exc).__name__}:{str(exc)[:160]}")
        return _result_template(
            ok=False,
            verdict="internal_error",
            source_url=url,
            warnings=[f"engine_exception:{type(exc).__name__}"],
            trace_id=trace_id,
        )

    trace_errors = [getattr(a, "error", "") or "" for a in result.trace]
    verdict = _map_engine_verdict(result.verdict or result.stop_reason, trace_errors)
    final_url = result.final_url or url
    trace_id = store_trace(url, final_url, result.trace, reason=result.stop_reason)

    if (time.monotonic() - started) * 1000 > deadline_ms:
        return _result_template(
            ok=False,
            verdict="deadline_exceeded",
            source_url=url,
            final_url=final_url,
            access_path=_access_path_from_trace(result.trace),
            warnings=["deadline exceeded after engine returned"],
            trace_id=trace_id,
        )

    content = result.content or ""
    if len(content.encode("utf-8", "ignore")) > max_bytes:
        return _result_template(
            ok=False,
            verdict="response_too_large",
            source_url=url,
            final_url=final_url,
            content_type=_content_type_for(content),
            access_path=_access_path_from_trace(result.trace),
            warnings=["response body exceeded max_bytes"],
            trace_id=trace_id,
        )

    content_type = _content_type_for(content)
    sanitized, warnings, instructions_detected = _sanitize_content(content, content_type, max_bytes)
    if result.ok and not sanitized:
        verdict = "invalid_content"

    ok = result.ok and verdict in {"strong_ok", "weak_ok"} and bool(sanitized)
    if include_trace:
        warnings.append("bounded_trace_available_via_inspect_fetch_trace")

    return _result_template(
        ok=ok,
        verdict=verdict,
        source_url=url,
        final_url=final_url,
        title=_title_for(content, content_type),
        content_type=content_type,
        content=sanitized if ok else "",
        metadata=_metadata_for(content, content_type),
        access_path=_access_path_from_trace(result.trace),
        instructions_detected=instructions_detected,
        warnings=warnings,
        trace_id=trace_id,
    )


def fetch_public_urls(
    urls: list[str],
    *,
    concurrency: int = 3,
    deadline_ms: int = 90_000,
    per_url_max_bytes: int = 1_000_000,
) -> dict[str, Any]:
    del concurrency  # Reserved for a future bounded async worker pool.
    if len(urls) > MAX_URLS:
        return {
            "ok": False,
            "verdict": "invalid_content",
            "results": [],
            "warnings": [f"url_count_exceeds_limit:{MAX_URLS}"],
        }
    per_url_deadline = max(MIN_DEADLINE_MS, _clamp(deadline_ms, MIN_DEADLINE_MS, MAX_DEADLINE_MS) // max(1, len(urls)))
    results = [
        fetch_public_url(url, deadline_ms=per_url_deadline, max_bytes=per_url_max_bytes)
        for url in urls
    ]
    return {
        "ok": all(r.get("ok") for r in results),
        "verdict": "strong_ok" if all(r.get("ok") for r in results) else "suspect",
        "results": results,
        "warnings": [],
    }


def inspect_fetch_trace(trace_id: str) -> dict[str, Any]:
    payload = load_trace(trace_id)
    if payload is None:
        return {"ok": False, "verdict": "not_found", "trace_id": trace_id, "trace": []}
    return {"ok": True, "verdict": "strong_ok", **payload}
