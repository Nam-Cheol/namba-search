from __future__ import annotations

from insane_search.security.url_policy import classify_url, domain_matches, redact_url


def test_blocks_private_and_metadata_targets() -> None:
    blocked = [
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://192.168.1.1/admin",
        "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "file:///etc/passwd",
        "data:text/plain,hello",
        "javascript:alert(1)",
    ]
    for url in blocked:
        assert not classify_url(url, resolve_dns=False).ok, url


def test_rejects_url_userinfo() -> None:
    result = classify_url("https://user:pass@example.com/path", resolve_dns=False)
    assert not result.ok
    assert result.reason == "userinfo_blocked"


def test_domain_boundary_matching() -> None:
    assert domain_matches("reddit.com", "reddit.com")
    assert domain_matches("old.reddit.com", "reddit.com")
    assert not domain_matches("reddit.com.attacker.test", "reddit.com")
    assert not domain_matches("notreddit.com", "reddit.com")


def test_redact_url_removes_userinfo_fragment_and_secret_query() -> None:
    redacted = redact_url("https://user:pass@example.com/a?token=abc&id=1#frag")
    assert redacted == "https://example.com/a?token=%3Credacted%3E&id=1#redacted"
    assert "user" not in redacted
    assert "abc" not in redacted
    assert "frag" not in redacted
