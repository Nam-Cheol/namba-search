"""Convert fetched HTML into bounded readable text without raw markup."""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

from insane_search.security.url_policy import classify_url, redact_url


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


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        if tag_l not in {"a", "area", "link"}:
            return
        attr = {k.lower(): (v or "") for k, v in attrs}
        href = attr.get("href", "").strip()
        if href:
            self.hrefs.append(href)


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


def _unwrap_search_redirect(url: str) -> str:
    try:
        parts = urlsplit(url)
    except Exception:
        return url
    host = (parts.hostname or "").lower()
    path = parts.path or ""
    params = parse_qs(parts.query)
    if host.endswith("duckduckgo.com") and path.startswith("/l/") and params.get("uddg"):
        return unquote(params["uddg"][0])
    if host.endswith("bing.com") and path.startswith("/ck/") and params.get("u"):
        return unquote(params["u"][0])
    return url


def extract_public_links(html: str, base_url: str, *, limit: int = 80) -> list[str]:
    """Extract bounded, policy-screened public links from HTML.

    This returns only redacted HTTP(S) links that pass the URL policy without DNS
    resolution. Final fetches still run the full policy with DNS resolution.
    """
    parser = _LinkExtractor()
    try:
        parser.feed(html or "")
    except Exception:
        return []

    links: list[str] = []
    seen: set[str] = set()
    for href in parser.hrefs:
        if len(links) >= limit:
            break
        if href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
            continue
        absolute = _unwrap_search_redirect(urljoin(base_url, href))
        policy = classify_url(absolute, resolve_dns=False)
        if not policy.ok:
            continue
        redacted = redact_url(policy.normalized_url or absolute)
        if not redacted or redacted in seen:
            continue
        seen.add(redacted)
        links.append(redacted)
    return links
