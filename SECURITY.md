# Security

Report vulnerabilities through GitHub security advisories for this repository
or by opening a private maintainer communication channel.

## Scope

Namba Search retrieves public web content. It is not designed to cross login,
subscription, authorization, private network, local file, or credential
boundaries.

## SSRF Protection

The shared URL policy rejects:

- Non-HTTP(S) schemes.
- URL userinfo.
- localhost and loopback.
- Private CIDR ranges.
- Link-local, multicast, reserved, and unspecified addresses.
- Cloud metadata endpoints.

The policy is applied before initial fetches and again across redirects,
warmups, transformed URLs, browser navigation, subresources, and discovered
candidate URLs.

## Query Research Boundaries

`research_public_web` is a bounded public-web orchestration mode. It may use
public discovery pages and public candidate URLs, but every discovery URL and
candidate source still flows through the same URL policy and fetch service. It
does not create Codex subagents, log in, use credentials, attach a browser
profile, bypass paywalls, or continue past its configured deadline, task, URL,
byte, per-domain rate-limit, or cost budget.

## Prompt Injection

Fetched pages are untrusted external data. Normal MCP results return sanitized
text or JSON, never raw HTML. Script, style, template, noscript, comment, SVG,
canvas, hidden DOM, and aria-hidden content are removed from text extraction.
Instruction-like text is surfaced as warning metadata.

## Browser Isolation

Browser fallback must use an ephemeral context. It must not use a user's
existing browser profile, persistent cookies, downloads, extensions, permission
grants, file URLs, or private network targets. If no isolated browser runtime is
available, the MCP server returns `browser_unavailable`.

## Dependency Installation

The plugin launcher is stdlib-first. Optional dependency bootstrap, when
enabled, installs only into a versioned per-user virtualenv under the plugin's
application data directory. It does not perform global `pip install`, global
`npm install -g`, shell profile edits, or Codex config edits.
