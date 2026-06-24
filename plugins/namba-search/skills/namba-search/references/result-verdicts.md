# Result Verdicts

`strong_ok` and `weak_ok` are the only success verdicts. `strong_ok` means the
MCP server found positive proof such as a caller selector or a trusted public
endpoint response. `weak_ok` means no positive proof was requested, but the
response passed status, content, wall, challenge, size, and sanitation checks.

Terminal failures are `auth_required`, `login_wall`, `paywall`, `not_found`,
and `unsafe_url`. Do not ask the server to cross credential, subscription,
private network, or authorization boundaries.

Non-terminal failures can be retried through public routes while respecting the
server deadline: `blocked`, `challenge`, `rate_limited`,
`browser_unavailable`, `network_error`, `suspect`, `deadline_exceeded`,
`response_too_large`, and `invalid_content`.
