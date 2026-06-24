from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


POSITIVE_PROMPTS = [
    "Use $namba-search to retrieve this public URL.",
    "This URL returns 403, read the public page.",
    "This public page is JavaScript-rendered and I need a summary.",
]

NEGATIVE_PROMPTS = [
    "Explain Spring Boot transaction propagation.",
    "Bypass this login-only page.",
    "Read my localhost admin page.",
]


def test_skill_supports_explicit_and_implicit_positive_prompts() -> None:
    skill = (ROOT / "skills" / "namba-search" / "SKILL.md").read_text(encoding="utf-8")
    assert "name: namba-search" in skill
    assert "$namba-search" not in skill.split("---", 2)[1]
    description = skill.split("---", 2)[1].lower()
    assert "blocked" in description
    assert "javascript-rendered" in description
    assert "public webpages" in description
    for prompt in POSITIVE_PROMPTS:
        assert any(token in description for token in ("blocked", "public", "javascript-rendered")), prompt


def test_skill_negative_boundaries_are_declared() -> None:
    skill = (ROOT / "skills" / "namba-search" / "SKILL.md").read_text(encoding="utf-8").lower()
    for boundary in ("login", "paywall", "authorization", "private networks", "credential"):
        assert boundary in skill
    for prompt in NEGATIVE_PROMPTS:
        assert prompt
