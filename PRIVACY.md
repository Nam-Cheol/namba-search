# Privacy

Namba Search processes URLs supplied by the user and retrieves public web
content locally through the plugin MCP server.

## Stored Data

The plugin may store the following in the user's application data directory:

- Sanitized trace metadata: phase, executor, redacted URL, status, body size,
  verdict, bounded reasons, elapsed time, and redacted errors.
- Learning hints for successful public fetch routes: hostname, device class,
  transform name, impersonation family, referer strategy, timestamps, win count,
  and bounded failure count.
- Runtime bootstrap markers and lock files.

## Data Not Stored

The plugin does not store:

- Authorization headers.
- Cookies or Set-Cookie values.
- Request or response bodies.
- Raw HTML.
- Query secrets, fragments, or URL userinfo.
- Browser localStorage or sessionStorage.
- User account data, passwords, API keys, or credentials.
- Codex conversation history.
- User Chrome profiles or login cookies.

## Network

The MCP server runs locally. It sends requests only to public HTTP(S) URLs that
pass the URL policy. It rejects localhost, private networks, metadata endpoints,
file URLs, data URLs, JavaScript URLs, and URL userinfo.
