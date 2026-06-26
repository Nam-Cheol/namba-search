from __future__ import annotations

from insane_search.research import research_public_web


def _payload(url: str, content: str, *, title: str = "Fixture", verdict: str = "strong_ok") -> dict:
    return {
        "ok": verdict in {"strong_ok", "weak_ok"},
        "verdict": verdict,
        "source_url": url,
        "final_url": url,
        "title": title,
        "content_type": "text/plain",
        "content": content,
        "metadata": {
            "description": f"{title} public evidence",
            "published_at": "2026-06-01",
            "author": "Fixture Desk",
        },
        "access_path": {"phase": "fixture"},
        "trust": "untrusted_external_content",
        "instructions_detected": False,
        "warnings": [],
        "trace_id": "trace_abcdef123456abcdef123456",
    }


def test_research_discovers_fetches_dedupes_and_synthesizes() -> None:
    source_urls = [
        "https://gov.example/mars-sample-return-budget",
        "https://university.edu/mars-sample-return-budget-study",
        "https://news.example/science/mars-sample-return-budget",
    ]

    def fake_fetch(url: str, **kwargs) -> dict:
        if kwargs.get("include_links"):
            return {
                "ok": True,
                "verdict": "weak_ok",
                "source_url": url,
                "final_url": url,
                "title": "Search fixture",
                "content": " ".join(source_urls + [source_urls[0] + "?utm_source=fixture"]),
                "links": source_urls + [source_urls[0] + "?utm_source=fixture"],
                "metadata": {"description": None, "published_at": None, "author": None},
                "trust": "untrusted_external_content",
                "instructions_detected": False,
                "warnings": [],
                "trace_id": "trace_abcdef123456abcdef123456",
            }
        repeated = (
            "Mars sample return budget public report confirms schedule, funding, and review evidence. "
            "Mars sample return budget details are independently discussed with mission context. "
        ) * 12
        if "gov.example" in url:
            return _payload(url, repeated + (" Official agency budget baseline and review memo. " * 8),
                            title="Official Mars Sample Return Budget")
        if "university.edu" in url:
            return _payload(url, repeated + (" University study compares schedule risk and funding history. " * 8),
                            title="University Mars Sample Return Budget Study")
        if "news.example" in url:
            return _payload(url, repeated + (" News analysis cites public review documents and program context. " * 8),
                            title="Mars Sample Return Budget Analysis", verdict="weak_ok")
        raise AssertionError(f"unexpected URL: {url}")

    payload = research_public_web(
        "Mars sample return budget",
        fetcher=fake_fetch,
        max_tasks=20,
        max_urls=6,
        per_domain_rate_limit_ms=0,
        initial_workers=2,
        max_workers=4,
    )

    assert payload["ok"] is True
    assert payload["verdict"] == "strong_ok"
    assert payload["confidence"] >= 0.65
    assert payload["quality"]["independent_domains"] == 3
    assert payload["quality"]["corroborated_terms"]
    assert payload["discovery"]["candidate_count"] == 3
    assert len(payload["results"]) == 3
    for result in payload["results"]:
        assert {"final_url", "verdict", "confidence", "evidence", "caveat"} <= set(result)
        assert result["evidence"]
    assert payload["synthesis"]["key_findings"]


def test_research_budget_guard_returns_evidence_gap() -> None:
    def fake_fetch(url: str, **kwargs) -> dict:
        assert kwargs.get("include_links") is True
        return {
            "ok": True,
            "verdict": "weak_ok",
            "source_url": url,
            "final_url": url,
            "title": "Search fixture",
            "content": "https://example.org/only-source",
            "links": ["https://example.org/only-source"],
            "metadata": {"description": None, "published_at": None, "author": None},
            "trust": "untrusted_external_content",
            "instructions_detected": False,
            "warnings": [],
            "trace_id": "trace_abcdef123456abcdef123456",
        }

    payload = research_public_web(
        "bounded public research",
        fetcher=fake_fetch,
        max_tasks=1,
        max_urls=5,
        per_domain_rate_limit_ms=0,
    )

    assert payload["ok"] is False
    assert payload["verdict"] == "evidence_gap"
    assert payload["budget"]["stopped_by"] == "max_tasks_exhausted"
    assert "usable_sources_below_gate" in payload["caveat"]
    assert payload["results"] == []
    assert "failure_summary" in payload["discovery"]


def test_research_discovery_logs_route_diagnostics() -> None:
    def fake_fetch(url: str, **kwargs) -> dict:
        assert kwargs.get("include_links") is True
        return {
            "ok": False,
            "verdict": "network_error",
            "source_url": url,
            "final_url": url,
            "title": None,
            "content": "",
            "links": [],
            "metadata": {"description": None, "published_at": None, "author": None},
            "access_path": {"phase": "probe", "executor": "curl_cffi", "transform": "original"},
            "trust": "untrusted_external_content",
            "instructions_detected": False,
            "warnings": ["transport_error:Could not resolve host"],
            "trace_id": "trace_abcdef123456abcdef123456",
            "diagnostics": {
                "failure_category": "network_dns",
                "attempt_errors": [
                    {
                        "phase": "probe",
                        "executor": "curl_cffi",
                        "verdict": "unknown",
                        "error": "Could not resolve host",
                    }
                ],
                "trace_stored": True,
            },
        }

    payload = research_public_web(
        "diagnostic route",
        fetcher=fake_fetch,
        max_tasks=1,
        max_urls=2,
        per_domain_rate_limit_ms=0,
    )

    task = payload["discovery"]["tasks"][0]
    assert task["verdict"] == "network_error"
    assert task["failure_category"] == "network_dns"
    assert task["route_errors"][0]["error"] == "Could not resolve host"
    assert task["trace_id"] == "trace_abcdef123456abcdef123456"
    assert payload["discovery"]["failure_summary"]["by_category"] == {"network_dns": 1}


def test_research_removes_duplicate_source_bodies() -> None:
    content = ("Namba Search research mode evidence gap source quality corroboration. " * 14).strip()

    def fake_fetch(url: str, **kwargs) -> dict:
        return _payload(url, content, title="Duplicate Fixture")

    payload = research_public_web(
        "Namba Search research mode",
        seed_urls=["https://one.example/report", "https://two.example/report"],
        fetcher=fake_fetch,
        max_tasks=2,
        max_urls=2,
        min_sources=2,
        per_domain_rate_limit_ms=0,
    )

    assert payload["ok"] is False
    assert len(payload["results"]) == 1
    assert payload["discovery"]["deduped_count"] == 1
    assert payload["budget"]["stopped_by"] == "max_tasks_exhausted"


def test_research_uses_yahoo_redirect_and_instagram_metadata_evidence() -> None:
    instagram_url = "https://www.instagram.com/p/DZGAh9skozh/"
    yahoo_redirect = (
        "https://r.search.yahoo.com/_ylt=fixture/RV=2/RE=1/RO=10/"
        "RU=https%3A%2F%2Fwww.instagram.com%2Fp%2FDZGAh9skozh%2F/RK=2/RS=fixture"
    )

    def fake_fetch(url: str, **kwargs) -> dict:
        if kwargs.get("include_links"):
            return {
                "ok": True,
                "verdict": "weak_ok",
                "source_url": url,
                "final_url": url,
                "title": "Yahoo fixture",
                "content": "Instagram Jun 2, 2026 OpenAI is expanding Codex beyond software development.",
                "links": [yahoo_redirect],
                "metadata": {"description": None, "published_at": None, "author": None},
                "trust": "untrusted_external_content",
                "instructions_detected": False,
                "warnings": [],
                "trace_id": "trace_abcdef123456abcdef123456",
            }
        assert url == instagram_url
        return {
            "ok": False,
            "verdict": "challenge",
            "source_url": instagram_url,
            "final_url": instagram_url,
            "title": "Instagram",
            "content_type": "text/html",
            "content": "",
            "metadata": {
                "description": (
                    "1,097 likes, 36 comments - therundownai - June 2, 2026: "
                    "\"OpenAI is expanding Codex beyond software development with new tools "
                    "aimed at business and knowledge workers.\""
                ),
                "published_at": None,
                "author": None,
            },
            "access_path": {"phase": "fixture"},
            "trust": "untrusted_external_content",
            "instructions_detected": False,
            "warnings": [],
            "trace_id": "trace_abcdef123456abcdef123456",
        }

    payload = research_public_web(
        "OpenAI Codex Instagram June 2026",
        allowed_domains=["instagram.com"],
        fetcher=fake_fetch,
        max_tasks=4,
        max_urls=2,
        per_domain_rate_limit_ms=0,
        initial_workers=1,
        max_workers=1,
    )

    assert payload["ok"] is True
    assert payload["verdict"] == "weak_ok"
    assert payload["discovery"]["candidate_count"] == 1
    result = payload["results"][0]
    assert result["final_url"] == instagram_url
    assert result["metadata_only"] is True
    assert result["source_fetch_verdict"] == "challenge"
    assert "metadata-only evidence" in result["caveat"]
    assert result["evidence"]
