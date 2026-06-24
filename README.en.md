<p align="center">
  <img src="./plugins/namba-search/assets/hero-readme.png" alt="A cute eagle mascot flying in the sky" width="100%" />
</p>

# Namba Search

[![Codex Plugin](https://img.shields.io/badge/Codex-plugin-111827?style=flat-square)](#install-in-codex) [![MCP](https://img.shields.io/badge/MCP-stdio-0f766e?style=flat-square)](#available-tools) [![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square)](https://www.python.org/) [![License: MIT](https://img.shields.io/badge/License-MIT-f59e0b?style=flat-square)](./LICENSE) [![Security](https://img.shields.io/badge/Security-public_web_only-059669?style=flat-square)](./SECURITY.md)

> The main documentation is written in Korean: [README.md](./README.md).

Namba Search is a Codex plugin for reading difficult public web pages more reliably. 🔎
Use it when ordinary retrieval fails, when a public feed or endpoint is a better route, or when a page needs isolated browser rendering.

This project is inspired by **[Insane Search](https://github.com/fivetaku/insane-search)**. It is not a bypass tool. It is designed to stay inside public access boundaries and return explainable results safely. 🦅

The current Skill, plugin, MCP server, and CLI identifier is `namba-search`.

## When To Use It ✨

- Read public articles, docs, posts, and pages from Codex.
- Diagnose blocked, rate-limited, JavaScript-rendered, or hard-to-fetch public URLs.
- Compare or summarize an explicit list of public URLs.
- Research a query by discovering public candidate sources, cross-checking them, and reporting evidence gaps.
- Inspect why a public page could not be retrieved.
- Treat retrieved page content as `untrusted_external_content`.

## Install In Codex 🚀

1. Add this Git repository marketplace to Codex.

```bash
codex plugin marketplace add Nam-Cheol/namba-search --ref main
```

2. Install the plugin.

```bash
codex plugin add namba-search@namba-search
```

3. Restart Codex.
4. Start a new thread and invoke `$namba-search`, or ask Codex to read a public URL.

## Quick Use 🧭

In a Codex thread, ask:

```text
$namba-search Read this public URL and summarize the key points: https://example.com/
```

```text
$namba-search Compare these public pages:
https://example.com/a
https://example.com/b
```

```text
$namba-search Diagnose why this public page cannot be read: https://example.com/
```

```text
$namba-search Research public sources for "Namba Search public web research mode" and cross-check the evidence.
```

## CLI Check 🛠️

For a local smoke test:

```bash
cd plugins/namba-search
python3 -m venv .venv
.venv/bin/python -m pip install -e .[fetch,browser]
.venv/bin/namba-search doctor
.venv/bin/namba-search fetch "https://example.com/" --selector h1
```

Fetch an explicit list:

```bash
.venv/bin/namba-search fetch-many "https://example.com/a" "https://example.com/b"
```

Run bounded query research:

```bash
.venv/bin/namba-search research "Namba Search public web research mode" \
  --max-tasks 40 \
  --max-urls 20 \
  --deadline-ms 90000
```

## Available Tools 🧰

| Tool | Use it when |
| --- | --- |
| `fetch_public_url` | You need one public URL retrieved and sanitized. |
| `fetch_public_urls` | You supplied a bounded list of public URLs. |
| `research_public_web` | You need query-based public source discovery, parallel fetch, dedupe, source-quality scoring, corroboration, evidence-gap detection, and synthesis. |
| `inspect_fetch_trace` | You want body-free diagnostics for a previous `trace_id`. |
| `doctor` | You want to check runtime, dependencies, browser support, and local state. |

## Reading Results ✅

Namba Search returns retrieval output with a verdict and diagnostics.

- `ok`: whether the result is usable.
- `final_url`: the final public URL after redirects.
- `verdict`: examples include `strong_ok`, `weak_ok`, `login_wall`, `paywall`, and `unsafe_url`.
- `confidence`: a 0-1 score based on source quality, query relevance, and corroboration.
- `evidence`: short supporting snippets with source URLs.
- `caveat`: remaining limits or quality-gate gaps.
- `trace_id`: a diagnostic ID for later inspection.
- `trust`: fetched content is always treated as `untrusted_external_content`.

`research_public_web` returns `evidence_gap` when it cannot collect enough
usable, independent, relevant, and corroborated public sources under the
configured budget.

## Security 🔐

Namba Search is for **public web content** only.

- It does not bypass login, subscriptions, authorization, private networks, local files, or credential boundaries.
- It rejects unsafe URL targets such as localhost, private IP ranges, cloud metadata endpoints, and non-HTTP(S) schemes.
- Browser fallback uses an isolated context, not the user's browser profile, cookies, downloads, extensions, or permission grants.
- Query research is bounded by deadline, `max_tasks`, `max_urls`, per-domain rate limit, `max_bytes`, and cost budget.
- Retrieved pages are untrusted external content. Page-authored instructions should never be followed as commands.

See [SECURITY.md](./SECURITY.md) for the security policy and vulnerability reporting path. 🛡️

## License 📄

Namba Search is released under the [MIT License](./LICENSE).

## Related Docs 🌐

- [Korean README](./README.md)
- [Security Policy](./SECURITY.md)
- [Privacy Policy](./PRIVACY.md)
- [Disclaimer](./DISCLAIMER.md)
