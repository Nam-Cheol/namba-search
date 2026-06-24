"""Command-line interface for the Codex-oriented Namba Search package."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__
from .doctor import run_doctor
from .service import fetch_public_url, fetch_public_urls, inspect_fetch_trace, research_public_web


def _json_dump(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="namba-search",
        description="Validated public web retrieval for the Namba Search Codex plugin.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    fetch_p = sub.add_parser("fetch", help="Fetch one public URL.")
    fetch_p.add_argument("url")
    fetch_p.add_argument("--selector", action="append", default=None)
    fetch_p.add_argument("--device", choices=("auto", "desktop", "mobile"), default="auto")
    fetch_p.add_argument("--mode", choices=("auto", "http_only", "browser_allowed"), default="auto")
    fetch_p.add_argument("--deadline-ms", type=int, default=45000)
    fetch_p.add_argument("--max-bytes", type=int, default=2_000_000)
    fetch_p.add_argument("--include-trace", action="store_true")

    many_p = sub.add_parser("fetch-many", help="Fetch an explicit list of public URLs.")
    many_p.add_argument("urls", nargs="+")
    many_p.add_argument("--concurrency", type=int, default=3)
    many_p.add_argument("--deadline-ms", type=int, default=90000)
    many_p.add_argument("--per-url-max-bytes", type=int, default=1_000_000)

    research_p = sub.add_parser("research", help="Research a query across bounded public web sources.")
    research_p.add_argument("query")
    research_p.add_argument("--seed-url", action="append", dest="seed_urls", default=None)
    research_p.add_argument("--allow-domain", action="append", dest="allowed_domains", default=None)
    research_p.add_argument("--exclude-domain", action="append", dest="excluded_domains", default=None)
    research_p.add_argument("--deadline-ms", type=int, default=90000)
    research_p.add_argument("--max-tasks", type=int, default=32)
    research_p.add_argument("--max-urls", type=int, default=24)
    research_p.add_argument("--max-bytes", type=int, default=2_000_000)
    research_p.add_argument("--cost-budget", type=int, default=None)
    research_p.add_argument("--per-domain-rate-limit-ms", type=int, default=250)
    research_p.add_argument("--initial-workers", type=int, default=2)
    research_p.add_argument("--max-workers", type=int, default=8)
    research_p.add_argument("--min-sources", type=int, default=3)
    research_p.add_argument("--min-confidence", type=float, default=0.55)
    research_p.add_argument("--mode", choices=("auto", "http_only", "browser_allowed"), default="auto")

    trace_p = sub.add_parser("trace", help="Inspect a sanitized fetch trace.")
    trace_p.add_argument("trace_id")

    sub.add_parser("doctor", help="Check local runtime and plugin health.")
    sub.add_parser("mcp", help="Run the STDIO MCP server.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help(sys.stderr)
        return 2
    if args.command == "fetch":
        _json_dump(fetch_public_url(
            args.url,
            selector=args.selector,
            device=args.device,
            mode=args.mode,
            deadline_ms=args.deadline_ms,
            max_bytes=args.max_bytes,
            include_trace=args.include_trace,
        ))
        return 0
    if args.command == "fetch-many":
        _json_dump(fetch_public_urls(
            args.urls,
            concurrency=args.concurrency,
            deadline_ms=args.deadline_ms,
            per_url_max_bytes=args.per_url_max_bytes,
        ))
        return 0
    if args.command == "research":
        _json_dump(research_public_web(
            args.query,
            seed_urls=args.seed_urls,
            allowed_domains=args.allowed_domains,
            excluded_domains=args.excluded_domains,
            deadline_ms=args.deadline_ms,
            max_tasks=args.max_tasks,
            max_urls=args.max_urls,
            max_bytes=args.max_bytes,
            cost_budget=args.cost_budget,
            per_domain_rate_limit_ms=args.per_domain_rate_limit_ms,
            initial_workers=args.initial_workers,
            max_workers=args.max_workers,
            min_sources=args.min_sources,
            min_confidence=args.min_confidence,
            mode=args.mode,
        ))
        return 0
    if args.command == "trace":
        _json_dump(inspect_fetch_trace(args.trace_id))
        return 0
    if args.command == "doctor":
        _json_dump(run_doctor())
        return 0
    if args.command == "mcp":
        from .mcp_server import main as mcp_main

        return mcp_main()
    parser.print_help(sys.stderr)
    return 2
