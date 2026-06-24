"""Convert fetched HTML into bounded readable text without raw markup."""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Any


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self._skip_depth = 0
        self._hidden_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k.lower(): (v or "") for k, v in attrs}
        tag_l = tag.lower()
        if tag_l in {"script", "style", "template", "noscript", "svg", "canvas"}:
            self._skip_depth += 1
            return
        hidden = (
            "hidden" in attr
            or attr.get("aria-hidden", "").lower() == "true"
            or "display:none" in attr.get("style", "").replace(" ", "").lower()
            or "visibility:hidden" in attr.get("style", "").replace(" ", "").lower()
        )
        if hidden:
            self._hidden_depth += 1
            return
        if tag_l == "title":
            self._in_title = True
        if tag_l == "meta":
            name = (attr.get("name") or attr.get("property") or "").lower()
            content = attr.get("content", "")
            if name in {"description", "og:description", "article:published_time", "author", "article:author"} and content:
                self.meta[name] = content
        if tag_l in {"p", "div", "section", "article", "br", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l in {"script", "style", "template", "noscript", "svg", "canvas"} and self._skip_depth:
            self._skip_depth -= 1
        elif self._hidden_depth:
            self._hidden_depth -= 1
        if tag_l == "title":
            self._in_title = False
        if tag_l in {"p", "div", "section", "article", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_comment(self, data: str) -> None:
        del data

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._hidden_depth:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        self.parts.append(text)


def _collapse(text: str) -> str:
    lines = [re.sub(r"[ \t\r\f\v]+", " ", unescape(line)).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def extract_readable_text(html: str) -> dict[str, Any]:
    parser = _TextExtractor()
    warnings: list[str] = []
    try:
        parser.feed(html or "")
    except Exception as exc:
        warnings.append(f"html_parse_error:{type(exc).__name__}")
    text = _collapse(" ".join(parser.parts))
    title = _collapse(" ".join(parser.title_parts)) or None
    description = parser.meta.get("description") or parser.meta.get("og:description")
    published = parser.meta.get("article:published_time")
    author = parser.meta.get("author") or parser.meta.get("article:author")
    return {
        "text": text,
        "title": title,
        "description": description,
        "published_at": published,
        "author": author,
        "warnings": warnings,
    }
