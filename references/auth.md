# Authentication

The Site Skill signs in through the public `al-site-mcp-gateway`:

1. Start a temporary loopback listener at `http://127.0.0.1:8766/oauth/callback`.
2. Open the Gateway at `/login?redirect_after_login=...`.
3. Let the Gateway complete OAuth Authorization Code + PKCE as the `al-site-mcp-gateway` public client.
4. Allow the Gateway to hand off the token only to a safe loopback callback.
5. Cache the short-lived token in `~/.al-site-mcp/state.json` with mode `0600`.

Subsequent MCP requests use:

```http
Authorization: Bearer <AL access token>
X-AL-Conversation-ID: <conversation id>
```

The Gateway validates the token, resolves the user, organization, and application, removes externally forged internal identity headers, and calls `al-site-tools-mcp` with a separate internal bearer token. The client does not hold a delegated HMAC, a Site Manager service credential, or a Kubernetes credential.

For local source uploads, the Gateway/MCP proxies only caller-bound JSON control requests. Requests sent by the script to TOS contain only the signed headers returned by the Manager and `Content-Length`; they never include the OAuth token, conversation ID, or internal identity headers described above. Presigned URLs are not written to local state or error output.

To select the current organization:

```bash
export AL_SITE_ORG_ID=<org-id>
```

`logout` clears only the local access token. `archive` clears only the Site selection for the conversation. Neither command deletes or stops a Site.
