# 配置

当前没有内置默认 Gateway。设置一次：

```bash
python3 scripts/al_site.py configure --gateway-url https://<site-mcp-public-host>
python3 scripts/al_site.py config
```

环境变量优先于本地状态：

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

本地状态默认位于：

```text
~/.al-site-mcp/state.json
~/.al-site-mcp/uploads/<archive-sha256>.json
```

`state.json` 缓存 Gateway URL、短期 access token、conversation id，以及最近一次明确选中或返回的 Site id。`uploads/` 只保存可续传 session 和分片 ETag；不保存源码、presigned URL 或最终 receipt。两类文件权限均为 `0600`。Site id 缓存只是 CLI 便利字段，Site Manager 中的 conversation binding 才是权威选择。

`AL_SITE_UPLOAD_WORKERS` 控制本地 TOS 分片并发，范围会被限制为 1～16；`AL_SITE_SOURCE_FINALIZE_TIMEOUT` 只控制 complete 后服务端校验、规范化和 OCI 发布的等待时间。

Gateway URL 必须使用 HTTPS；只有测试用的 `localhost`/`127.0.0.1` 可使用 HTTP。URL 可以带或不带 `/mcp`。
