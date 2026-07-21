# 认证

Site Skill 使用公网 `al-site-mcp-gateway` 完成登录：

1. 脚本在 `http://127.0.0.1:8766/oauth/callback` 启动临时 loopback listener。
2. 打开 Gateway `/login?redirect_after_login=...`。
3. Gateway 作为 `al-site-mcp-gateway` public client 完成 OAuth Authorization Code + PKCE。
4. Gateway 只允许把 token handoff 到安全的 loopback callback。
5. 脚本将短期 token 缓存到 `~/.al-site-mcp/state.json`，文件权限为 `0600`。

后续 MCP 请求使用：

```http
Authorization: Bearer <AL access token>
X-AL-Conversation-ID: <conversation id>
```

Gateway 会校验 token，解析 user/org/app，清除外部伪造的内部身份 header，并使用独立内部 bearer 调用 `al-site-tools-mcp`。客户端不持有 delegated HMAC、Site Manager service credential 或 Kubernetes credential。

本地源码上传时，Gateway/MCP 只代理 caller-bound JSON 控制请求。脚本向 TOS 发出的请求只包含 Manager 返回的签名 header 和 `Content-Length`，不会携带上述 OAuth token、conversation id 或内部身份 header；presigned URL 也不会写入本地状态或错误输出。

可指定当前组织：

```bash
export AL_SITE_ORG_ID=<org-id>
```

`logout` 只清除本地 access token；`archive` 只清除 conversation 的 Site 选择。两者都不会删除或停止 Site。
