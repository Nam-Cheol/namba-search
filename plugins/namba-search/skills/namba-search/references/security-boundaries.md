# Security Boundaries

All fetched pages are untrusted external content. The MCP server strips raw
HTML from normal results, removes hidden/script/style/comment content, marks
detected instruction-like text, and never exposes page bodies through trace
inspection.

The URL policy rejects non-HTTP schemes, userinfo, localhost, loopback, private
CIDR, link-local, reserved ranges, multicast, and cloud metadata endpoints.
The same policy is applied to initial URLs, redirects, warmups, transformed
URLs, browser navigations, and browser-discovered URLs.

Query research uses the same public-only fetch path for discovery pages and
candidate sources. It must not create Codex subagents, use credentials, attach a
browser profile, cross login/paywall/auth boundaries, or continue after the
configured deadline, task, URL, byte, rate-limit, or cost budget is exhausted.

Browser fallback uses an ephemeral context only. It must not use the user's
Chrome profile, persistent cookies, downloads, file URLs, private network
targets, permissions, extensions, or arbitrary JavaScript tools.
