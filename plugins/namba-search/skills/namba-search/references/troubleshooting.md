# Troubleshooting

Run `doctor` first when the MCP server fails to start or returns
`browser_unavailable`.

Common outcomes:

- `unsafe_url`: the URL, redirect, or discovered resource crossed a blocked
  scheme, userinfo, private network, localhost, or metadata boundary.
- `browser_unavailable`: HTTP retrieval still works, but no usable isolated
  browser runtime is available.
- `response_too_large`: lower requested scope or use a smaller public page.
- `invalid_content`: the response was 2xx but empty, selector-mismatched, or
  sanitation removed the usable body.
