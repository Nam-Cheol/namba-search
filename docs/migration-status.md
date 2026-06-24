# Migration Status

Updated: 2026-06-24

## Baseline

- Local starting directory `/Users/namba/Documents/ai/namba-search` was not a
  Git worktree and initially contained only migration documents plus a zip that
  duplicated those documents.
- The legacy upstream source was cloned read-only into a temporary directory
  to preserve the 0.8.2 engine during migration.
- Local `.git` metadata was restored from that upstream clone after the
  migration files were materialized, so final Git status and diff checks now
  run locally. No remote operation was performed.
- After validation, the dirty migration working tree was moved from `main` to
  a local-only `feat/codex-plugin` branch.
- Upstream branch at clone time: `main...origin/main`.
- Upstream `.claude-plugin/plugin.json` version: `0.8.2`.
- Legacy test attempt: `python3 -m pytest <legacy-skill>/engine/tests`
  failed because `pytest` was not installed in the ambient Python environment.
- Legacy CLI help worked from the old Skill directory with
  `python3 -m engine --help`.

## Phase 0 - Baseline

Status: complete with workspace caveat.

Inventory:

- Claude manifest: `.claude-plugin/plugin.json`.
- Claude setup scripts and legacy update helper.
- Claude-heavy legacy Skill directory.
- Legacy engine under the old Skill directory.
- Claude side effects: settings edits, update hook registration, star prompt,
  transcript-language inference.

Rollback commands for maintainers:

```bash
git fetch origin
git switch -c legacy/claude v0.8.2
```

## Phase 1 - Codex Plugin Skeleton

Status: complete locally.

Created:

- `.codex-plugin/plugin.json`
- `.mcp.json`
- `.agents/plugins/marketplace.json`
- `skills/namba-search/SKILL.md`
- `skills/namba-search/agents/openai.yaml`
- Skill assets and Codex references

Decision:

- Official Codex manual confirms plugin manifests live at
  `.codex-plugin/plugin.json`, plugins can bundle skills and MCP servers, repo
  marketplaces can live at `.agents/plugins/marketplace.json`, and skills can
  use `agents/openai.yaml` metadata.

## Phase 2 - Python Package

Status: complete locally.

Created:

- `src/insane_search/**`
- `pyproject.toml`
- package CLI and public API

The legacy engine was copied into `src/insane_search/engine` and then patched
for Codex security and packaging. The old Skill-local engine copy was removed.

## Phase 3 - MCP Server

Status: complete locally.

Created:

- `src/insane_search/mcp_server.py`
- `src/insane_search/service.py`
- `scripts/launch_mcp.py`

Tools:

- `fetch_public_url`
- `fetch_public_urls`
- `inspect_fetch_trace`
- `doctor`

## Phase 4 - Orchestration Internalization

Status: complete locally, live-browser rendering skipped.

Completed:

- Removed Skill instructions that tell Codex to compose shell, curl, WebFetch,
  WebSearch, or Playwright MCP calls.
- Added internal browser fallback path that returns `browser_unavailable` when
  Playwright is unavailable.
- Applied URL policy to browser navigation and subresources.
- Added same-origin/public validation for browser-discovered API-like URLs.
- Clamped browser fallback timeout to the caller-controlled per-attempt timeout
  instead of the old 90-second default.

Remaining:

- No Chrome/Chromium binary was available, so live rendered-page validation was
  skipped. Deterministic browser policy tests cover iframe, XHR, popup,
  private IP, and same-origin API candidate classification.

## Phase 5 - Security P0

Status: complete for deterministic local tests, pending live/browser runtime
verification.

Completed:

- Non-2xx cannot become success.
- URL userinfo is rejected.
- Exact/dot-boundary platform host matching replaces substring matching.
- Private, loopback, link-local, reserved, multicast, localhost, and metadata
  endpoints are blocked.
- Login, paywall, consent, and CAPTCHA verdicts were added.
- Raw HTML is not returned by the MCP service.
- Instruction-like fetched text is warning metadata.
- Trace store redacts URLs and excludes bodies.
- Learning store moved to app data and no longer keys by full netloc with
  userinfo.

## Phase 6 - Runtime Bootstrap

Status: complete locally for macOS arm64 / CPython 3.11.

Completed:

- `scripts/launch_mcp.py` is stdlib-first.
- `scripts/bootstrap_runtime.py` creates a versioned per-user virtualenv when
  explicitly enabled with `INSANE_SEARCH_BOOTSTRAP=1`.
- Runtime markers are written atomically.
- `scripts/doctor.py` is standalone.
- `requirements.lock` contains hash-pinned optional runtime dependencies for
  the local macOS arm64 / CPython 3.11 validation environment.
- `python3 -m pip install --require-hashes -r requirements.lock` passed in a
  disposable virtualenv.
- `INSANE_SEARCH_BOOTSTRAP=1 INSANE_SEARCH_DATA_DIR=/private/tmp/insane-bootstrap python3 scripts/launch_mcp.py`
  passed after redirecting pip bootstrap output to stderr; stdout stayed
  protocol-clean.

## Phase 7 - Skill And Docs

Status: complete locally.

Updated:

- README
- PRIVACY
- SECURITY
- CHANGELOG
- architecture
- legacy Claude doc
- Skill references

## Phase 8 - CI, Release, Legacy Removal

Status: partial.

Completed:

- CI workflow added.
- Release validator added.
- Claude runtime directories removed from the Codex plugin payload.

Remaining:

- No remote push, tag push, GitHub release, or marketplace publish was
  performed.
- Work remains as a dirty local `feat/codex-plugin` branch. It has not been
  committed or pushed.

## Final Local Validation

Passed:

```bash
PYTHONPATH=src /private/tmp/insane-lock-venv/bin/python -m pytest tests/unit tests/integration tests/security tests/mcp_contract tests/plugin_e2e
# 34 passed

PYTHONPATH=src /private/tmp/insane-lock-venv/bin/python -m ruff check .
# All checks passed

python3 scripts/validate_release.py
# {"ok": true, "version": "1.0.0", "errors": []}

PYTHONPATH=src /private/tmp/insane-lock-venv/bin/python -m compileall -q src scripts tests

PYTHONPATH=src /private/tmp/insane-lock-venv/bin/python scripts/doctor.py
# ok=true; bs4/curl_cffi/yaml/playwright=true; chrome=null

python3 -m pip install --require-hashes -r requirements.lock
# passed in /private/tmp/insane-lock-venv

git diff --check
# passed
```

MCP stdio smoke:

```text
initialize + tools/list through scripts/launch_mcp.py returned
fetch_public_url and untrusted-content initialization instructions with no
stderr output.
```

Whitespace:

- `git diff --check` passed.
- A text-only whitespace scan passed after excluding binary assets and the
  preserved migration plan copies.

Live/browser tests:

- Skipped. Playwright Python package is installed in the validation venv, but
  no Chrome/Chromium browser binary was available in doctor output. Live
  external endpoint success is not a release gate.
