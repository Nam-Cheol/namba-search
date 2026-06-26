"""Bounded public-web research orchestration.

This module is intentionally a coordinator, not an agent runtime. It discovers
candidate public sources, fetches them through the existing service fetcher,
deduplicates results, scores evidence quality, checks corroboration, and returns
a conservative synthesis with explicit evidence gaps.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import parse_qsl, quote_plus, unquote, urlencode, urlsplit, urlunsplit

from insane_search.security.url_policy import classify_url, domain_matches, redact_url

DEFAULT_TRUST = "untrusted_external_content"

MIN_DEADLINE_MS = 1_000
MAX_DEADLINE_MS = 180_000
MIN_MAX_BYTES = 8_192
MAX_MAX_BYTES = 5_000_000
MAX_RESEARCH_TASKS = 200
MAX_RESEARCH_URLS = 100
DEFAULT_MIN_SOURCES = 3

DISCOVERY_DOMAINS = frozenset({
    "duckduckgo.com",
    "bing.com",
    "search.yahoo.com",
    "r.search.yahoo.com",
    "hn.algolia.com",
    "api.crossref.org",
    "export.arxiv.org",
})
SOCIAL_SINGLE_SOURCE_DOMAINS = frozenset({
    "instagram.com",
    "threads.net",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "youtube.com",
})

TRACKING_QUERY_KEYS = frozenset({
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "msclkid",
    "igshid",
    "mc_cid",
    "mc_eid",
})

STOPWORDS = frozenset({
    "about",
    "after",
    "also",
    "and",
    "are",
    "from",
    "how",
    "into",
    "news",
    "official",
    "report",
    "source",
    "that",
    "the",
    "their",
    "this",
    "what",
    "when",
    "where",
    "with",
})
URL_RE = re.compile(r"https?://[^\s<>'\"\])}]+", re.I)
METADATA_EVIDENCE_VERDICTS = frozenset({
    "blocked",
    "captcha_required",
    "challenge",
    "consent_wall",
    "login_wall",
    "rate_limited",
})
MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
QUERY_CONTEXT_TOKENS = frozenset({
    "day",
    "latest",
    "month",
    "past",
    "recent",
    "site",
    "today",
    "week",
    "yesterday",
    "instagram",
    "instagram.com",
    "twitter",
    "twitter.com",
    "x.com",
    "com",
    *MONTHS.keys(),
})

FetchPublicUrl = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ResearchTask:
    kind: str
    url: str
    label: str


class DomainRateLimiter:
    def __init__(self, interval_ms: int) -> None:
        self.interval_s = max(0.0, interval_ms / 1000.0)
        self._next_allowed: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, url: str, deadline_at: float) -> bool:
        if self.interval_s <= 0:
            return True
        host = _host(url)
        if not host:
            return True
        with self._lock:
            now = time.monotonic()
            allowed_at = self._next_allowed.get(host, now)
            sleep_s = max(0.0, allowed_at - now)
            self._next_allowed[host] = max(now, allowed_at) + self.interval_s
        if sleep_s <= 0:
            return True
        if time.monotonic() + sleep_s >= deadline_at:
            return False
        time.sleep(sleep_s)
        return True


def _clamp(value: int | None, low: int, high: int, default: int) -> int:
    try:
        raw = int(default if value is None else value)
    except (TypeError, ValueError):
        raw = default
    return max(low, min(high, raw))


def _host(url: str) -> str:
    try:
        host = (urlsplit(url).hostname or "").strip(".").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def _matches_any_domain(host: str, domains: list[str] | None) -> bool:
    return bool(host and domains and any(domain_matches(host, domain) for domain in domains))


def _normalized_domains(domains: list[str] | None) -> set[str]:
    normalized: set[str] = set()
    for domain in domains or []:
        host = str(domain or "").strip().lower().strip(".")
        if host.startswith("www."):
            host = host[4:]
        if host:
            normalized.add(host)
    return normalized


def _is_discovery_domain(host: str) -> bool:
    return any(domain_matches(host, domain) for domain in DISCOVERY_DOMAINS)


def _unwrap_search_redirect_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except Exception:
        return url
    host = _host(url)
    if host == "r.search.yahoo.com":
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if key.upper() == "RU" and value.lower().startswith(("http://", "https://")):
                return value
        match = re.search(r"(?:^|/)RU=([^/]+)", parts.path)
        if match:
            target = unquote(match.group(1))
            if target.lower().startswith(("http://", "https://")):
                return target
    return url


def _canonicalize_url(url: str) -> str | None:
    url = _unwrap_search_redirect_url(url)
    policy = classify_url(url, resolve_dns=False)
    if not policy.ok:
        return None
    try:
        parts = urlsplit(policy.normalized_url or url)
    except Exception:
        return None
    host = (parts.hostname or "").lower().strip(".")
    if not host:
        return None
    netloc = host
    if parts.port:
        netloc = f"{host}:{parts.port}"
    query = urlencode(
        sorted((key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
               if key.lower() not in TRACKING_QUERY_KEYS),
        doseq=True,
    )
    path = (parts.path or "/").rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for token in re.findall(r"[\w][\w.-]{1,}", (text or "").lower()):
        cleaned = token.strip("._-")
        if len(cleaned) < 2 or cleaned in STOPWORDS:
            continue
        if cleaned.isdigit():
            continue
        tokens.append(cleaned)
    return tokens


def _query_tokens(query: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for token in _tokenize(query):
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= 14:
            break
    return tokens


def _core_query_terms(tokens: list[str]) -> list[str]:
    return [
        token
        for token in tokens
        if token not in QUERY_CONTEXT_TOKENS
        and not token.endswith(".com")
        and not token.startswith("site")
    ]


def _core_terms_satisfied(tokens: list[str], matched_terms: list[str]) -> tuple[bool, str | None]:
    core_terms = _core_query_terms(tokens)
    if not core_terms:
        return True, None
    matched = set(matched_terms)
    matched_core = [token for token in core_terms if token in matched]
    required = len(core_terms) if len(core_terms) <= 2 else max(1, math.ceil(len(core_terms) * 0.5))
    if len(matched_core) >= required:
        return True, None
    return False, f"core_query_terms_below_gate:{len(matched_core)}/{required}"


def _query_variants(query: str) -> list[str]:
    base = re.sub(r"\s+", " ", query).strip()
    variants = [base]
    if len(base) <= 120 and '"' not in base:
        variants.append(f'"{base}"')
    for suffix in ("official", "documentation", "report", "analysis", "news"):
        if suffix not in base.lower():
            variants.append(f"{base} {suffix}")
    seen: set[str] = set()
    unique: list[str] = []
    for variant in variants:
        key = variant.lower()
        if key not in seen:
            seen.add(key)
            unique.append(variant)
    return unique


def _query_has_recency_intent(query: str) -> bool:
    lowered = query.lower()
    markers = (
        "after:",
        "before:",
        "latest",
        "recent",
        "past day",
        "past week",
        "past month",
        "last day",
        "last week",
        "last month",
        "this month",
        "최근",
        "지난",
        "이번 달",
        "한 달",
        "1개월",
    )
    return any(marker in lowered for marker in markers)


def _query_recency_days(query: str) -> int | None:
    lowered = query.lower()
    if any(marker in lowered for marker in ("past day", "last day", "today", "yesterday", "오늘", "어제")):
        return 2
    if any(marker in lowered for marker in ("past week", "last week", "this week", "최근 일주일", "지난주", "이번 주")):
        return 8
    if any(
        marker in lowered
        for marker in (
            "past month",
            "last month",
            "this month",
            "recent month",
            "최근 한 달",
            "한 달",
            "1개월",
            "지난달",
            "이번 달",
        )
    ):
        return 31
    return None


def _parse_public_date(text: str) -> date | None:
    collapsed = _collapse_text(text)
    iso_match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", collapsed)
    if iso_match:
        try:
            return date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
        except ValueError:
            pass
    month_match = re.search(
        r"\b("
        + "|".join(re.escape(month) for month in sorted(MONTHS, key=len, reverse=True))
        + r")\.?\s+(\d{1,2}),\s+(20\d{2})\b",
        collapsed,
        re.I,
    )
    if month_match:
        try:
            return date(
                int(month_match.group(3)),
                MONTHS[month_match.group(1).lower().rstrip(".")],
                int(month_match.group(2)),
            )
        except ValueError:
            return None
    return None


def _recency_caveat(query: str, content: str) -> tuple[bool, str | None, str | None]:
    days = _query_recency_days(query)
    if days is None:
        return True, None, None
    published = _parse_public_date(content)
    if published is None:
        return True, None, "recency_requested_but_no_parseable_public_date"
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    if published < cutoff:
        return False, published.isoformat(), f"outside_recency_window:{published.isoformat()}<{cutoff.isoformat()}"
    return True, published.isoformat(), None


def _discovery_url(provider: str, query: str, page: int) -> str | None:
    encoded = quote_plus(query)
    if provider == "yahoo":
        suffix = f"&b={page * 7 + 1}" if page else ""
        return f"https://search.yahoo.com/search?p={encoded}{suffix}"
    if provider == "yahoo_recent":
        suffix = f"&b={page * 7 + 1}" if page else ""
        return f"https://search.yahoo.com/search?p={encoded}&btf=m{suffix}"
    if provider == "duckduckgo":
        suffix = f"&s={page * 30}" if page else ""
        return f"https://duckduckgo.com/html/?q={encoded}{suffix}"
    if provider == "bing":
        return f"https://www.bing.com/search?q={encoded}&first={page * 10 + 1}"
    if provider == "wikipedia":
        if page:
            return None
        return (
            "https://en.wikipedia.org/w/api.php?action=opensearch"
            f"&search={encoded}&limit=10&namespace=0&format=json"
        )
    if provider == "hn_algolia":
        return f"https://hn.algolia.com/api/v1/search?query={encoded}&tags=story&page={page}"
    if provider == "reddit_rss":
        if page:
            return None
        return f"https://www.reddit.com/search.rss?q={encoded}&sort=relevance"
    if provider == "arxiv":
        return f"https://export.arxiv.org/api/query?search_query=all:{encoded}&start={page * 10}&max_results=10"
    if provider == "crossref":
        return f"https://api.crossref.org/works?query={encoded}&rows=10&offset={page * 10}"
    return None


def _build_discovery_tasks(query: str, max_tasks: int) -> deque[ResearchTask]:
    providers = ["yahoo", "duckduckgo", "bing", "wikipedia", "hn_algolia", "reddit_rss", "arxiv", "crossref"]
    if _query_has_recency_intent(query):
        providers.insert(0, "yahoo_recent")
    variants = _query_variants(query)
    tasks: deque[ResearchTask] = deque()
    page = 0
    while len(tasks) < max_tasks and page < 25:
        for variant in variants:
            for provider in providers:
                url = _discovery_url(provider, variant, page)
                if not url:
                    continue
                tasks.append(ResearchTask("discovery", url, provider))
                if len(tasks) >= max_tasks:
                    return tasks
        page += 1
    return tasks


def _extract_urls_from_json(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for child in value.values():
            found.extend(_extract_urls_from_json(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_extract_urls_from_json(child))
    elif isinstance(value, str):
        found.extend(URL_RE.findall(value))
    return found


def _extract_urls_from_text(text: str) -> list[str]:
    urls = URL_RE.findall(text or "")
    stripped = [url.rstrip(".,;:!?") for url in urls]
    try:
        parsed = json.loads(text)
    except Exception:
        return stripped
    stripped.extend(_extract_urls_from_json(parsed))
    return stripped


def _candidate_allowed(
    url: str,
    *,
    allowed_domains: list[str] | None,
    excluded_domains: list[str] | None,
    allow_discovery_domains: bool = False,
) -> str | None:
    url = _unwrap_search_redirect_url(url)
    policy = classify_url(url, resolve_dns=False)
    if not policy.ok:
        return None
    normalized = policy.normalized_url or url
    host = _host(normalized)
    if not host:
        return None
    if not allow_discovery_domains and _is_discovery_domain(host):
        return None
    if allowed_domains and not _matches_any_domain(host, allowed_domains):
        return None
    if _matches_any_domain(host, excluded_domains):
        return None
    return normalized


def _extract_candidate_urls(
    payload: dict[str, Any],
    *,
    allowed_domains: list[str] | None,
    excluded_domains: list[str] | None,
) -> list[str]:
    raw: list[str] = []
    raw.extend(str(url) for url in payload.get("links") or [])
    raw.extend(_extract_urls_from_text(str(payload.get("content") or "")))
    candidates: list[str] = []
    seen: set[str] = set()
    for url in raw:
        allowed = _candidate_allowed(url, allowed_domains=allowed_domains, excluded_domains=excluded_domains)
        if not allowed:
            continue
        canonical = _canonicalize_url(allowed)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        candidates.append(allowed)
    return candidates


def _collapse_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _content_fingerprint(content: str) -> str | None:
    collapsed = _collapse_text(content).lower()
    if len(collapsed) < 200:
        return None
    return hashlib.sha256(collapsed[:5000].encode("utf-8", "ignore")).hexdigest()


def _source_quality(payload: dict[str, Any], content: str) -> float:
    verdict = str(payload.get("verdict") or "")
    if verdict not in {"strong_ok", "weak_ok"}:
        return 0.0
    final_url = str(payload.get("final_url") or payload.get("source_url") or "")
    host = _host(final_url)
    score = 0.32
    suffix_parts = host.split(".")
    if any(part in {"gov", "edu", "mil", "int"} for part in suffix_parts[-3:]):
        score += 0.25
    elif host.endswith(".org"):
        score += 0.12
    path = (urlsplit(final_url).path or "").lower()
    if any(part in path for part in ("/docs", "/documentation", "/research", "/press", "/news", "/blog")):
        score += 0.06
    if payload.get("title"):
        score += 0.05
    metadata = payload.get("metadata") or {}
    if metadata.get("author"):
        score += 0.04
    if metadata.get("published_at"):
        score += 0.05
    byte_len = len(content.encode("utf-8", "ignore"))
    if byte_len >= 800:
        score += 0.08
    if byte_len >= 2400:
        score += 0.08
    if verdict == "strong_ok":
        score += 0.08
    return round(max(0.0, min(1.0, score)), 3)


def _relevance(query: str, tokens: list[str], payload: dict[str, Any], content: str) -> tuple[float, list[str]]:
    text = " ".join([
        str(payload.get("title") or ""),
        str((payload.get("metadata") or {}).get("description") or ""),
        content,
    ]).lower()
    if not tokens:
        return 0.0, []
    matched = [token for token in tokens if token in text]
    coverage = len(matched) / max(1, len(tokens))
    exact = 0.18 if query.lower() in text else 0.0
    density = min(0.12, sum(text.count(token) for token in matched) / 120.0)
    return round(max(0.0, min(1.0, coverage * 0.70 + exact + density)), 3), matched


def _snippets(content: str, matched_terms: list[str], *, limit: int = 3) -> list[dict[str, Any]]:
    collapsed = _collapse_text(content)
    lowered = collapsed.lower()
    snippets: list[dict[str, Any]] = []
    seen: set[str] = set()
    terms = matched_terms or _tokenize(collapsed)[:3]
    for term in terms:
        idx = lowered.find(term.lower())
        if idx < 0:
            continue
        start = max(0, idx - 140)
        end = min(len(collapsed), idx + 260)
        snippet = collapsed[start:end].strip()
        if start:
            snippet = "..." + snippet
        if end < len(collapsed):
            snippet += "..."
        key = snippet.lower()
        if key in seen:
            continue
        seen.add(key)
        snippets.append({"snippet": snippet, "matched_terms": [term]})
        if len(snippets) >= limit:
            break
    if not snippets and collapsed:
        snippets.append({"snippet": collapsed[:360], "matched_terms": []})
    return snippets


def _source_caveat(payload: dict[str, Any], relevance: float, quality: float, evidence: list[dict[str, Any]]) -> str:
    verdict = str(payload.get("verdict") or "internal_error")
    caveats: list[str] = []
    if verdict not in {"strong_ok", "weak_ok"}:
        caveats.append(f"source fetch verdict is {verdict}")
    if relevance < 0.35:
        caveats.append("low query-term coverage")
    if quality < 0.45 and verdict in {"strong_ok", "weak_ok"}:
        caveats.append("moderate or weak source-quality signals")
    if not evidence:
        caveats.append("no extractable evidence snippet")
    if payload.get("instructions_detected"):
        caveats.append("instruction-like text was detected and treated as untrusted")
    warnings = payload.get("warnings") or []
    if warnings:
        caveats.append(str(warnings[0])[:120])
    return "; ".join(caveats) if caveats else "none"


def _metadata_evidence_content(payload: dict[str, Any]) -> str:
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        return ""
    description = _collapse_text(str(metadata.get("description") or ""))
    if len(description) < 40:
        return ""
    lowered = description.lower()
    generic_failures = (
        "something went wrong",
        "try again later",
        "login",
        "log in",
        "sign up",
        "sign in",
    )
    if any(marker in lowered for marker in generic_failures) and len(description) < 160:
        return ""
    return description


def _result_from_payload(query: str, tokens: list[str], task: ResearchTask, payload: dict[str, Any]) -> dict[str, Any]:
    body_content = str(payload.get("content") or "")
    source_verdict = str(payload.get("verdict") or "internal_error")
    metadata_content = _metadata_evidence_content(payload)
    metadata_only = False
    content = body_content
    effective_payload = payload
    if not content and metadata_content and source_verdict in METADATA_EVIDENCE_VERDICTS:
        content = metadata_content
        metadata_only = True
        effective_payload = dict(payload)
        effective_payload["ok"] = True
        effective_payload["verdict"] = "weak_ok"

    quality = _source_quality(effective_payload, content)
    relevance, matched_terms = _relevance(query, tokens, effective_payload, content)
    verdict = "weak_ok" if metadata_only else source_verdict
    recency_ok, parsed_date, recency_warning = _recency_caveat(query, content)
    core_ok, core_warning = _core_terms_satisfied(tokens, matched_terms)
    ok = (
        bool(payload.get("ok")) and source_verdict in {"strong_ok", "weak_ok"} and bool(content)
    ) or (
        metadata_only and bool(matched_terms) and relevance >= 0.15
    )
    if ok and (not recency_ok or not core_ok):
        ok = False
    verdict_score = 1.0 if verdict == "strong_ok" else 0.84 if verdict == "weak_ok" else 0.0
    confidence = 0.0
    evidence: list[dict[str, Any]] = []
    if ok:
        evidence = _snippets(content, matched_terms)
        confidence = max(0.05, min(1.0, 0.10 + relevance * 0.43 + quality * 0.37 + verdict_score * 0.10))
    caveat = _source_caveat(effective_payload, relevance, quality, evidence)
    if metadata_only:
        prefix = f"metadata-only evidence from public page metadata; source fetch verdict was {source_verdict}"
        caveat = prefix if caveat == "none" else f"{prefix}; {caveat}"
    if recency_warning:
        caveat = recency_warning if caveat == "none" else f"{caveat}; {recency_warning}"
    if core_warning:
        caveat = core_warning if caveat == "none" else f"{caveat}; {core_warning}"
    metadata = payload.get("metadata") or {"description": None, "published_at": None, "author": None}
    if isinstance(metadata, dict) and parsed_date and not metadata.get("published_at"):
        metadata = dict(metadata)
        metadata["published_at"] = parsed_date
    return {
        "ok": ok,
        "source_url": payload.get("source_url") or redact_url(task.url),
        "final_url": payload.get("final_url") or redact_url(task.url),
        "title": payload.get("title"),
        "verdict": verdict,
        "source_fetch_verdict": source_verdict,
        "metadata_only": metadata_only,
        "confidence": round(confidence, 3),
        "source_quality": quality,
        "relevance": relevance,
        "matched_terms": matched_terms,
        "evidence": evidence,
        "caveat": caveat,
        "trace_id": payload.get("trace_id"),
        "metadata": metadata,
        "trust": payload.get("trust") or DEFAULT_TRUST,
    }


def _failure_payload(url: str, verdict: str, warning: str) -> dict[str, Any]:
    redacted = redact_url(url)
    return {
        "ok": False,
        "verdict": verdict,
        "source_url": redacted,
        "final_url": redacted,
        "title": None,
        "content": "",
        "metadata": {"description": None, "published_at": None, "author": None},
        "trust": DEFAULT_TRUST,
        "instructions_detected": False,
        "warnings": [warning],
        "trace_id": None,
        "diagnostics": {
            "failure_category": _classify_failure(verdict, [warning]),
            "attempt_errors": [],
            "trace_stored": False,
        },
    }


def _classify_failure(verdict: str, messages: list[Any]) -> str:
    text = " ".join([verdict] + [str(message) for message in messages]).lower()
    if verdict == "unsafe_url" or "ssrf_" in text or "private" in text:
        return "url_policy"
    if "allowed_domain" in text or "excluded_domain" in text:
        return "domain_policy"
    if "operation not permitted" in text or "permissionerror" in text or "sandbox" in text:
        return "sandbox"
    if "curl_cffi not installed" in text or "modulenotfounderror" in text or "importerror" in text:
        return "dependency"
    if verdict == "deadline_exceeded" or "timeout" in text or "timed out" in text:
        return "network_timeout" if verdict == "network_error" else "deadline"
    if "could not resolve" in text or "name or service not known" in text or "nodename nor servname" in text:
        return "network_dns"
    if verdict == "browser_unavailable":
        return "browser_unavailable"
    if verdict in {"auth_required", "login_wall", "paywall", "not_found"}:
        return "terminal_access"
    if verdict == "network_error":
        return "network_transport"
    if verdict in {"blocked", "challenge", "rate_limited", "captcha_required", "consent_wall"}:
        return "remote_policy"
    if verdict in {"invalid_content", "response_too_large"}:
        return "content_policy"
    if verdict == "internal_error":
        return "internal"
    return "none"


def _payload_messages(payload: dict[str, Any]) -> list[Any]:
    messages: list[Any] = []
    messages.extend(payload.get("warnings") or [])
    diagnostics = payload.get("diagnostics") or {}
    if isinstance(diagnostics, dict):
        for item in diagnostics.get("attempt_errors") or []:
            if isinstance(item, dict):
                messages.append(item.get("error"))
            else:
                messages.append(item)
    return [message for message in messages if message]


def _failure_category_from_payload(payload: dict[str, Any]) -> str:
    diagnostics = payload.get("diagnostics") or {}
    if isinstance(diagnostics, dict) and diagnostics.get("failure_category"):
        return str(diagnostics["failure_category"])
    return _classify_failure(str(payload.get("verdict") or "internal_error"), _payload_messages(payload))


def _discovery_route_errors(payload: dict[str, Any]) -> list[Any]:
    diagnostics = payload.get("diagnostics") or {}
    errors: list[Any] = []
    if isinstance(diagnostics, dict):
        errors.extend(diagnostics.get("attempt_errors") or [])
    if not errors:
        errors.extend(payload.get("warnings") or [])
    return errors[:6]


def _failure_summary(discovery_log: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, int] = {}
    by_provider: dict[str, dict[str, int]] = {}
    for item in discovery_log:
        if item.get("ok"):
            continue
        category = str(item.get("failure_category") or "unknown")
        label = str(item.get("label") or "unknown")
        by_category[category] = by_category.get(category, 0) + 1
        provider_counts = by_provider.setdefault(label, {})
        provider_counts[category] = provider_counts.get(category, 0) + 1
    return {"by_category": by_category, "by_provider": by_provider}


def _call_fetcher(
    fetcher: FetchPublicUrl,
    task: ResearchTask,
    *,
    deadline_at: float,
    per_url_max_bytes: int,
    mode: str,
    limiter: DomainRateLimiter,
) -> tuple[ResearchTask, dict[str, Any]]:
    if not limiter.wait(task.url, deadline_at):
        return task, _failure_payload(task.url, "deadline_exceeded", "per-domain rate limit would exceed deadline")
    remaining_ms = int(max(0.0, deadline_at - time.monotonic()) * 1000)
    if remaining_ms < MIN_DEADLINE_MS:
        return task, _failure_payload(task.url, "deadline_exceeded", "deadline exhausted before fetch")
    per_call_deadline = min(60_000 if task.kind == "source" else 30_000, remaining_ms)
    try:
        payload = fetcher(
            task.url,
            deadline_ms=per_call_deadline,
            max_bytes=per_url_max_bytes,
            mode=mode,
            include_links=(task.kind == "discovery"),
        )
    except TypeError:
        payload = fetcher(task.url, deadline_ms=per_call_deadline, max_bytes=per_url_max_bytes, mode=mode)
    except Exception as exc:
        return task, _failure_payload(task.url, "internal_error", f"fetcher_exception:{type(exc).__name__}")
    if not isinstance(payload, dict):
        return task, _failure_payload(task.url, "internal_error", "fetcher returned non-dict payload")
    return task, payload


def _run_wave(
    tasks: list[ResearchTask],
    *,
    worker_count: int,
    fetcher: FetchPublicUrl,
    deadline_at: float,
    per_url_max_bytes: int,
    mode: str,
    limiter: DomainRateLimiter,
) -> list[tuple[ResearchTask, dict[str, Any]]]:
    if not tasks:
        return []
    max_workers = max(1, min(worker_count, len(tasks)))
    results: list[tuple[ResearchTask, dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="namba-research") as pool:
        futures = [
            pool.submit(
                _call_fetcher,
                fetcher,
                task,
                deadline_at=deadline_at,
                per_url_max_bytes=per_url_max_bytes,
                mode=mode,
                limiter=limiter,
            )
            for task in tasks
        ]
        for future in as_completed(futures):
            results.append(future.result())
    return results


def _evaluate_quality(
    results: list[dict[str, Any]],
    tokens: list[str],
    *,
    min_sources: int,
    min_confidence: float,
    max_urls: int,
    allowed_domains: list[str] | None = None,
) -> dict[str, Any]:
    usable = [r for r in results if r.get("ok") and r.get("evidence")]
    domains = sorted({_host(str(r.get("final_url") or "")) for r in usable if _host(str(r.get("final_url") or ""))})
    coverage_tokens = _core_query_terms(tokens) or tokens
    token_domains: dict[str, set[str]] = {token: set() for token in coverage_tokens}
    for result in usable:
        host = _host(str(result.get("final_url") or ""))
        for token in result.get("matched_terms") or []:
            if token in token_domains and host:
                token_domains[token].add(host)
    covered_terms = sorted(token for token, hosts in token_domains.items() if hosts)
    corroborated_terms = sorted(token for token, hosts in token_domains.items() if len(hosts) >= 2)
    coverage = len(covered_terms) / max(1, len(coverage_tokens)) if coverage_tokens else 0.0
    avg_conf = sum(float(r.get("confidence") or 0.0) for r in usable) / max(1, len(usable))
    high_quality = sum(1 for r in usable if float(r.get("source_quality") or 0.0) >= 0.65)
    source_target = max(1, min(min_sources, max_urls))
    single_domain_scope = len(_normalized_domains(allowed_domains)) == 1
    domain_target = 1 if source_target == 1 or single_domain_scope else 2
    gaps: list[str] = []
    if len(usable) < source_target:
        gaps.append(f"usable_sources_below_gate:{len(usable)}/{source_target}")
    if len(domains) < domain_target:
        gaps.append(f"independent_domains_below_gate:{len(domains)}/{domain_target}")
    if coverage_tokens and coverage < 0.50:
        gaps.append(f"query_coverage_below_gate:{coverage:.2f}/0.50")
    if usable and avg_conf < min_confidence:
        gaps.append(f"confidence_below_gate:{avg_conf:.2f}/{min_confidence:.2f}")
    if len(domains) >= 2 and tokens and not corroborated_terms:
        gaps.append("no_query_terms_corroborated_across_domains")

    domain_score = min(1.0, len(domains) / max(1, domain_target + 1))
    corroboration_score = min(1.0, len(corroborated_terms) / max(1, math.ceil(max(1, len(coverage_tokens)) / 3)))
    confidence = max(
        0.0,
        min(1.0, avg_conf * 0.45 + coverage * 0.25 + domain_score * 0.18 + corroboration_score * 0.12),
    )
    sufficient = not gaps
    strong = (
        sufficient
        and len(domains) >= 3
        and avg_conf >= max(0.68, min_confidence)
        and coverage >= 0.65
        and high_quality >= 1
        and bool(corroborated_terms)
    )
    verdict = "strong_ok" if strong else "weak_ok" if sufficient else "evidence_gap"
    return {
        "sufficient": sufficient,
        "verdict": verdict,
        "confidence": round(confidence, 3),
        "usable_sources": len(usable),
        "independent_domains": len(domains),
        "domains": domains,
        "query_coverage": round(coverage, 3),
        "average_source_confidence": round(avg_conf, 3),
        "high_quality_sources": high_quality,
        "covered_terms": covered_terms,
        "corroborated_terms": corroborated_terms,
        "gaps": gaps,
    }


def _top_evidence(results: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    usable = [r for r in results if r.get("ok") and r.get("evidence")]
    ranked = sorted(
        usable,
        key=lambda r: (float(r.get("confidence") or 0.0), float(r.get("source_quality") or 0.0)),
        reverse=True,
    )
    evidence: list[dict[str, Any]] = []
    for result in ranked:
        for item in result.get("evidence") or []:
            evidence.append({
                "final_url": result.get("final_url"),
                "title": result.get("title"),
                "verdict": result.get("verdict"),
                "confidence": result.get("confidence"),
                "evidence": [item],
                "caveat": result.get("caveat"),
            })
            if len(evidence) >= limit:
                return evidence
    return evidence


def _synthesis(query: str, quality: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    if quality.get("sufficient"):
        answer = (
            f"Public evidence for '{query}' is sufficient under the configured gate: "
            f"{quality['usable_sources']} usable sources across {quality['independent_domains']} independent domains."
        )
    else:
        answer = (
            f"Public evidence for '{query}' is insufficient under the configured gate. "
            "Use the evidence snippets as partial context only."
        )
    key_findings = []
    for item in evidence[:5]:
        snippet = ""
        if item.get("evidence"):
            snippet = str(item["evidence"][0].get("snippet") or "")
        key_findings.append({
            "final_url": item.get("final_url"),
            "title": item.get("title"),
            "snippet": snippet,
            "confidence": item.get("confidence"),
            "caveat": item.get("caveat"),
        })
    return {
        "answer": answer,
        "key_findings": key_findings,
        "cross_checks": {
            "covered_terms": quality.get("covered_terms", []),
            "corroborated_terms": quality.get("corroborated_terms", []),
            "independent_domains": quality.get("domains", []),
            "query_coverage": quality.get("query_coverage", 0.0),
        },
        "evidence_gaps": quality.get("gaps", []),
    }


def _empty_result(query: str, verdict: str, warning: str) -> dict[str, Any]:
    return {
        "ok": False,
        "verdict": verdict,
        "confidence": 0.0,
        "final_url": None,
        "query": query,
        "evidence": [],
        "caveat": warning,
        "synthesis": {
            "answer": warning,
            "key_findings": [],
            "cross_checks": {},
            "evidence_gaps": [warning],
        },
        "results": [],
        "discovery": {"tasks": [], "candidate_count": 0, "deduped_count": 0, "failure_summary": {}},
        "budget": {},
        "warnings": [warning],
        "trust": DEFAULT_TRUST,
    }


def research_public_web(
    query: str,
    *,
    seed_urls: list[str] | None = None,
    allowed_domains: list[str] | None = None,
    excluded_domains: list[str] | None = None,
    deadline_ms: int = 90_000,
    max_tasks: int = 32,
    max_urls: int = 24,
    max_bytes: int = 2_000_000,
    cost_budget: int | None = None,
    per_domain_rate_limit_ms: int = 250,
    initial_workers: int = 2,
    max_workers: int = 8,
    min_sources: int = DEFAULT_MIN_SOURCES,
    min_confidence: float = 0.55,
    mode: str = "auto",
    fetcher: FetchPublicUrl | None = None,
) -> dict[str, Any]:
    """Run bounded public-web research for a query."""
    query = re.sub(r"\s+", " ", str(query or "")).strip()
    if not query:
        return _empty_result(query, "invalid_content", "query is required")
    if fetcher is None:
        return _empty_result(query, "internal_error", "no fetcher configured")

    deadline_ms = _clamp(deadline_ms, MIN_DEADLINE_MS, MAX_DEADLINE_MS, 90_000)
    max_tasks = _clamp(max_tasks, 1, MAX_RESEARCH_TASKS, 32)
    max_urls = _clamp(max_urls, 1, MAX_RESEARCH_URLS, 24)
    max_bytes = _clamp(max_bytes, MIN_MAX_BYTES, MAX_MAX_BYTES, 2_000_000)
    cost_budget = _clamp(cost_budget, 1, max_tasks, max_tasks)
    per_domain_rate_limit_ms = _clamp(per_domain_rate_limit_ms, 0, 10_000, 250)
    max_workers = _clamp(max_workers, 1, 16, 8)
    initial_workers = _clamp(initial_workers, 1, max_workers, 2)
    normalized_allowed_domains = _normalized_domains(allowed_domains)
    single_social_domain_scope = (
        len(normalized_allowed_domains) == 1
        and next(iter(normalized_allowed_domains)) in SOCIAL_SINGLE_SOURCE_DOMAINS
    )
    min_sources = _clamp(min_sources, 1, 10, DEFAULT_MIN_SOURCES)
    if min_sources == DEFAULT_MIN_SOURCES and single_social_domain_scope:
        min_sources = 1
    try:
        min_confidence = max(0.0, min(1.0, float(min_confidence)))
    except (TypeError, ValueError):
        min_confidence = 0.55
    if min_confidence == 0.55 and single_social_domain_scope:
        min_confidence = 0.40
    if mode not in {"auto", "http_only", "browser_allowed"}:
        mode = "auto"

    started = time.monotonic()
    deadline_at = started + deadline_ms / 1000.0
    limiter = DomainRateLimiter(per_domain_rate_limit_ms)
    tokens = _query_tokens(query)
    discovery_queue = _build_discovery_tasks(query, max_tasks)
    candidate_queue: deque[ResearchTask] = deque()
    candidate_seen: set[str] = set()
    final_seen: set[str] = set()
    fingerprints_seen: set[str] = set()
    discovery_log: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    warnings: list[str] = []

    def add_candidate(url: str, label: str) -> bool:
        if len(candidate_seen) >= max(max_urls * 4, max_urls):
            return False
        allowed = _candidate_allowed(
            url,
            allowed_domains=allowed_domains,
            excluded_domains=excluded_domains,
            allow_discovery_domains=False,
        )
        if not allowed:
            return False
        canonical = _canonicalize_url(allowed)
        if not canonical or canonical in candidate_seen:
            return False
        candidate_seen.add(canonical)
        candidate_queue.append(ResearchTask("source", allowed, label))
        return True

    for seed_url in seed_urls or []:
        add_candidate(str(seed_url), "seed")

    tasks_started = 0
    source_fetches = 0
    bytes_used = 0
    deduped_count = 0
    worker_count = initial_workers
    stage = 0
    stop_reason = "quality_gate_satisfied"
    quality = _evaluate_quality(
        results,
        tokens,
        min_sources=min_sources,
        min_confidence=min_confidence,
        max_urls=max_urls,
        allowed_domains=allowed_domains,
    )

    while not quality["sufficient"]:
        now = time.monotonic()
        if now >= deadline_at:
            stop_reason = "deadline_exceeded"
            warnings.append("deadline_exceeded")
            break
        if tasks_started >= max_tasks:
            stop_reason = "max_tasks_exhausted"
            warnings.append(f"max_tasks_exhausted:{max_tasks}")
            break
        if tasks_started >= cost_budget:
            stop_reason = "cost_budget_exhausted"
            warnings.append(f"cost_budget_exhausted:{cost_budget}")
            break
        if source_fetches >= max_urls:
            stop_reason = "max_urls_exhausted"
            warnings.append(f"max_urls_exhausted:{max_urls}")
            break
        if bytes_used >= max_bytes:
            stop_reason = "max_bytes_exhausted"
            warnings.append(f"max_bytes_exhausted:{max_bytes}")
            break

        stage += 1
        wave: list[ResearchTask] = []
        remaining_tasks = min(max_tasks - tasks_started, cost_budget - tasks_started)
        if candidate_queue and source_fetches < max_urls:
            take = min(len(candidate_queue), max_urls - source_fetches, worker_count * 2, remaining_tasks)
            for _ in range(take):
                wave.append(candidate_queue.popleft())
            source_fetches += len(wave)
        elif discovery_queue:
            take = min(len(discovery_queue), worker_count, remaining_tasks)
            for _ in range(take):
                wave.append(discovery_queue.popleft())
        else:
            stop_reason = "candidate_pool_exhausted"
            warnings.append("candidate_pool_exhausted")
            break
        if not wave:
            stop_reason = "budget_exhausted"
            warnings.append("no_budget_for_next_wave")
            break

        tasks_started += len(wave)
        per_url_max_bytes = max(MIN_MAX_BYTES, min(MAX_MAX_BYTES, max_bytes - bytes_used))
        outcomes = _run_wave(
            wave,
            worker_count=worker_count,
            fetcher=fetcher,
            deadline_at=deadline_at,
            per_url_max_bytes=per_url_max_bytes,
            mode=mode,
            limiter=limiter,
        )
        for task, payload in outcomes:
            content = str(payload.get("content") or "")
            bytes_used += len(content.encode("utf-8", "ignore"))
            if task.kind == "discovery":
                candidates = _extract_candidate_urls(
                    payload,
                    allowed_domains=allowed_domains,
                    excluded_domains=excluded_domains,
                )
                added = sum(1 for url in candidates if add_candidate(url, task.label))
                warnings_for_route = [str(warning) for warning in payload.get("warnings") or []]
                discovery_log.append({
                    "ok": bool(payload.get("ok")),
                    "url": redact_url(task.url),
                    "label": task.label,
                    "final_url": payload.get("final_url") or redact_url(task.url),
                    "verdict": payload.get("verdict") or "internal_error",
                    "failure_category": _failure_category_from_payload(payload),
                    "route_errors": _discovery_route_errors(payload),
                    "warnings": warnings_for_route,
                    "trace_id": payload.get("trace_id"),
                    "access_path": payload.get("access_path") or {},
                    "confidence": 0.0,
                    "evidence": [],
                    "caveat": f"candidate_urls_found:{len(candidates)}; candidate_urls_added:{added}",
                    "candidates_found": len(candidates),
                    "candidates_added": added,
                })
                continue

            result = _result_from_payload(query, tokens, task, payload)
            final_key = _canonicalize_url(str(result.get("final_url") or "")) or str(result.get("final_url") or "")
            fingerprint = _content_fingerprint(content)
            if result.get("ok") and (final_key in final_seen or (fingerprint and fingerprint in fingerprints_seen)):
                deduped_count += 1
                continue
            if final_key:
                final_seen.add(final_key)
            if fingerprint:
                fingerprints_seen.add(fingerprint)
            results.append(result)

        if bytes_used >= max_bytes:
            stop_reason = "max_bytes_exhausted"
            warnings.append(f"max_bytes_exhausted:{max_bytes}")
            break
        quality = _evaluate_quality(
            results,
            tokens,
            min_sources=min_sources,
            min_confidence=min_confidence,
            max_urls=max_urls,
            allowed_domains=allowed_domains,
        )
        if not quality["sufficient"]:
            worker_count = min(max_workers, worker_count * 2)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    evidence = _top_evidence(results)
    synthesis = _synthesis(query, quality, evidence)
    caveats = list(quality.get("gaps") or [])
    if warnings:
        caveats.extend(warnings)
    verdict = str(quality.get("verdict") or "evidence_gap")
    ok = verdict in {"strong_ok", "weak_ok"}
    if not ok and stop_reason == "deadline_exceeded" and not results:
        verdict = "deadline_exceeded"
    budget = {
        "deadline_ms": deadline_ms,
        "elapsed_ms": elapsed_ms,
        "max_tasks": max_tasks,
        "tasks_started": tasks_started,
        "max_urls": max_urls,
        "source_fetches": source_fetches,
        "max_bytes": max_bytes,
        "bytes_used": bytes_used,
        "cost_budget": cost_budget,
        "cost_units_used": tasks_started,
        "per_domain_rate_limit_ms": per_domain_rate_limit_ms,
        "initial_workers": initial_workers,
        "last_worker_count": worker_count,
        "max_workers": max_workers,
        "stopped_by": stop_reason,
    }
    return {
        "ok": ok,
        "verdict": verdict,
        "confidence": quality.get("confidence", 0.0),
        "final_url": None,
        "query": query,
        "evidence": evidence,
        "caveat": "; ".join(caveats) if caveats else "none",
        "synthesis": synthesis,
        "results": results,
        "quality": quality,
        "discovery": {
            "tasks": discovery_log,
            "candidate_count": len(candidate_seen),
            "deduped_count": deduped_count,
            "adaptive_stages": stage,
            "failure_summary": _failure_summary(discovery_log),
        },
        "budget": budget,
        "warnings": warnings,
        "trust": DEFAULT_TRUST,
    }
