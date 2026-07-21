# al-site-skill

AL Site 的独立客户端 Skill。仓库根目录可直接安装为 Codex skill，通过公网 `al-site-mcp-gateway` 调用全部 Site MCP 工具。

```bash
python3 scripts/al_site.py tools
python3 scripts/al_site.py create "My Site"
python3 scripts/al_site.py deploy-local . --site-id SITE_ID
```

所有 MCP 工具都可通过 `call` 或同名 kebab-case 命令调用；常见 Site、Version、Deployment 操作另有强类型 shortcut。工具契约以在线 `tools/list` 为准。

Skill 与 `al-sandbox-skill` 完全独立。`save-local` 会通过 Site MCP 创建短期上传会话，再把本地归档分片直传 TOS，最终由 Site Manager 校验并发布为平台 OCI SourceBundle；`save-git`、`save-oci` 也不依赖 Sandbox。只有 `save-current` 显式使用当前 Sandbox 的一次性 SourceBundle export grant。所有来源最终进入同一套 Site build、scan、preview、deploy 状态机。

当前 dev 默认使用独立 Site MCP 公网 Gateway `https://skr0bjcv434ri5v3bqdlq.apigateway-cn-beijing.volceapi.com`。其他环境通过 `configure --gateway-url https://<site-mcp-public-host>` 或 `AL_SITE_MCP_GATEWAY_URL` 覆盖。

详见 `SKILL.md` 与 `references/`。
