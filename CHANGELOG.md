# Changelog

## 1.0.1 - Plugin Runtime Re-exec and Browser Bootstrap

- Re-exec plugin CLI and MCP launchers through the complete plugin-owned runtime
  without requiring manual bootstrap on every new Codex session.
- Include Playwright Chromium install state in the runtime marker and install the
  browser under the plugin-owned data directory during bootstrap.
- Expand doctor output to separate current interpreter dependencies from
  plugin-runtime dependencies and browser binary health.

## 1.0.0 - Codex Plugin Migration

Breaking change: Namba Search is now a Codex-only plugin.

- Added `.codex-plugin/plugin.json`, `.mcp.json`, and repo-local marketplace
  metadata.
- Replaced the Claude orchestration-heavy Skill with a short Codex Skill that
  calls high-level MCP tools.
- Added a package root under `src/insane_search` and public Python API
  `from insane_search import fetch`.
- Added stdlib MCP server tools: `fetch_public_url`, `fetch_public_urls`,
  `inspect_fetch_trace`, and `doctor`.
- Added URL policy, sanitized trace store, HTML text extraction, instruction
  signal warnings, and per-user app data paths.
- Hardened validation so non-2xx responses cannot become successful fetches.
- Added explicit verdicts for login walls, paywalls, consent walls, CAPTCHA,
  unsafe URLs, oversized responses, invalid content, and browser unavailability.
- Replaced agent-driven browser instructions with internal isolated browser
  fallback behavior.
- Added release validator, CI workflow, and deterministic test suites.

Claude Code plugin users should use `v0.8.2` or `claude-final-v0.8.2`.
