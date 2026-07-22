# al-site-skill

`al-site` 是 AL Site 系统的客户端 skill。仓库根目录就是可安装 skill，安装后通过 `scripts/al_mcp.py` 调用公网 `al-site-mcp-gateway`，覆盖 Site、不可变 Version、Deployment、访问策略、域名、日志、指标、Add-on 和清理等能力。

## 快速开始

```bash
python3 scripts/al_mcp.py tools
python3 scripts/al_mcp.py describe CreateSite
python3 scripts/al_mcp.py call GetCurrentSite
python3 scripts/al_mcp.py create "My Site"
python3 scripts/al_mcp.py deploy-local . --site-id SITE_ID
python3 scripts/al_mcp.py wait-version VERSION_ID --site-id SITE_ID
python3 scripts/al_mcp.py wait-deployment DEPLOYMENT_ID --site-id SITE_ID
python3 scripts/al_mcp.py archive
```

## 示例 Prompt

复制任意一条使用：

```text
$al-site 列出我的 Sites。
$al-site 创建一个名为 "My Site" 的 Site。
$al-site 把当前目录部署到我选中的 Site。
$al-site 查看当前版本的构建、扫描和预览状态。
$al-site 把指定的 Ready Version 部署到生产流量。
$al-site 查看 Site 的日志、事件和指标。
$al-site 使用 al-sandbox 生成的一次性 handoff 发布当前项目。
$al-site 删除这个 Site；执行前再次确认资源身份。
```

工具面以 MCP Server 的 `tools/list` 为准。脚本保留常见生命周期 shortcut，同时允许通过 `describe <tool>` 和 `call <tool> --arguments ...` 或 `--arg key=value` 调用任意动态工具；当前内置的 Site MCP 工具另有同名 kebab-case 命令。服务端新增工具不要求同步客户端，直接通过通用 `call` 即可使用。

`al-site` 与 `al-sandbox` 可以分别独立使用。`save-local` 通过 Site MCP 创建短期上传会话，并由客户端把本地归档分片直传 TOS；`save-git` 和 `save-oci` 同样不依赖 Sandbox。只有 `save-current` 显式消费 `al-sandbox handoff` 生成的一次性、owner-bound 描述符。

Site 是持久资源。`archive` 只清除当前 conversation 的 Site 选择，不会暂停或删除 Site；永久删除必须显式调用 `DeleteSite` 并确认。构建和部署完成状态以 MCP 返回的真实 Version/Deployment phase 为准。

默认使用 dev 公网 Gateway `https://skr0bjcv434ri5v3bqdlq.apigateway-cn-beijing.volceapi.com`。首次调用会自动打开 Gateway `/login`，通过 OAuth PKCE 把短期 token 回传到本机客户端缓存；conversation id 也会自动生成并缓存。其他环境可通过 `configure --gateway-url` 或 `AL_SITE_MCP_GATEWAY_URL` 覆盖。

详细说明见 `SKILL.md` 和 `references/`。
