# Configuration

The dev environment includes this default Gateway:

```text
https://skr0bjcv434ri5v3bqdlq.apigateway-cn-beijing.volceapi.com
```

Configure another environment once:

```bash
python3 scripts/al_mcp.py configure --gateway-url https://<site-mcp-public-host>
python3 scripts/al_mcp.py config
```

Environment variables take precedence over local state:

```bash
AL_SITE_MCP_GATEWAY_URL=https://<site-mcp-public-host>
AL_SITE_MCP_TOKEN=<override AL OAuth access token>
AL_SITE_CONVERSATION_ID=<override conversation id>
AL_SITE_ID=<override selected Site id>
AL_SITE_ORG_ID=<organization id>
AL_SITE_TOOL_CALL_ID=<idempotent tool call id>
AL_SITE_MCP_TIMEOUT=180
AL_SITE_SOURCE_FINALIZE_TIMEOUT=900
AL_SITE_UPLOAD_WORKERS=4
AL_SITE_STATE_DIR=~/.al-site-mcp
AL_SITE_LOGIN_CALLBACK_URL=http://127.0.0.1:8766/oauth/callback
```

Local state is stored by default at:

```text
~/.al-site-mcp/state.json
~/.al-site-mcp/uploads/<archive-sha256>.json
```

`state.json` caches the Gateway URL, short-lived access token, conversation ID, and the most recently explicitly selected or returned Site ID. `uploads/` stores only a resumable session and part ETags; it does not store source code, presigned URLs, or the final receipt. Both file types use mode `0600`. The cached Site ID is only a CLI convenience field; the conversation binding in Site Manager remains the authoritative selection.

`AL_SITE_UPLOAD_WORKERS` controls local TOS multipart concurrency and is clamped to a range of 1 through 16. `AL_SITE_SOURCE_FINALIZE_TIMEOUT` controls only the wait for server-side validation, normalization, and OCI publication after completion.

The Gateway URL must use HTTPS. Only `localhost` or `127.0.0.1` may use HTTP for testing. The URL may include or omit `/mcp`.
