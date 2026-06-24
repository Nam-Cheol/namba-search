# Architecture

```text
Codex Skill
  -> namba-search MCP server
    -> service policy and result shaping
      -> public-web research orchestration
      -> Python fetch engine
        -> Phase 0 public routes
        -> HTTP/TLS strategy grid
        -> WAF detector and validator
        -> optional isolated browser fallback
```

## Skill

The Skill decides when to use Namba Search, which high-level tool to call, and
how to treat returned content. It does not instruct Codex to run shell, curl,
raw browser, arbitrary JavaScript, or low-level Playwright tools.

## MCP Server

The MCP server owns tool schemas, initialization instructions, URL policy,
deadline and size clamps, result sanitation, structured verdicts, and trace
storage. `stdout` is reserved for JSON-RPC protocol output; diagnostics go to
`stderr` through the launcher or doctor path.

## Research Orchestration

`research_public_web` is a query-based orchestration layer. It does not spawn
Codex subagents or use browser profiles. It builds public discovery tasks,
fetches candidates through the existing `fetch_public_url` service path,
deduplicates final URLs and similar bodies, scores source quality and relevance,
checks corroboration across independent domains, records evidence gaps, and
returns a synthesis with `final_url`, `verdict`, `confidence`, `evidence`, and
`caveat` fields on source results.

The fanout is adaptive: it starts with a small worker count and expands only
when the quality gate is not met. The run is bounded by deadline, task count,
URL count, per-domain rate limit, byte budget, and cost budget.

## Engine

The engine preserves the legacy public route planner, WAF detector, HTTP/TLS
grid, URL transforms, validators, and learning concept. It is packaged under
`src/insane_search/engine`.

## Browser

Browser fallback is internal and isolated. It uses a request-scoped browser
context when Playwright is available and returns `browser_unavailable` when it
is not.

## Runtime And State

Runtime state lives under the user's application data directory, not plugin
root. Trace and learning stores are bounded, owner-only, and body-free.
