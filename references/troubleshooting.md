# 排障

## 切换 Site MCP Gateway

当前 dev 已内置独立 Site MCP Gateway。只有使用其他环境或显式清空/覆盖配置时，才需要配置 Gateway：

```bash
python3 scripts/al_site.py configure --gateway-url https://<site-mcp-public-host>
```

Site Access Gateway 和用户 Site URL 不能替代 MCP Gateway。

## OAuth login is not configured

Gateway 已部署但 `oauthRedirectURI` 尚未设置，或 OAuth static client 未注册完全相同的回调。先读取真实 APIG 公网域名，再把：

```text
https://<site-mcp-public-host>/oauth/callback
```

同时写入 Gateway 配置和 OAuth client。Ingress `spec.rules[].host` 仍只能使用占位 host，不能写这个真实域名。

## conversation id is required

脚本会自动生成。若需要固定：

```bash
export AL_SITE_CONVERSATION_ID=<uuid>
```

## 没有当前 Site

```bash
python3 scripts/al_site.py sites
python3 scripts/al_site.py select SITE_ID
```

`archive` 后 Site 仍然存在，只是 conversation 不再选择它。

## local Git working tree is not clean

`save-local-git` 和 `deploy-local-git` 只接受不可变 commit。提交或移除 tracked/untracked 改动后重试。不要用忽略检查的方式发布与 commit 不一致的内容。

如果目标就是发布当前工作区内容，改用：

```bash
python3 scripts/al_site.py save-local . --site-id SITE_ID
```

## high-confidence credential material detected

源目录包含疑似 private key、AWS key、GitHub token 或 Slack token。删除该文件，或在确实不属于 Site 构建输入时加入 `.alignore`。平台 denylist 下的凭据目录无需手工配置，且不能被重新包含。

## source archive exceeds the configured upload limit

先用 `.alignore` 排除依赖缓存、构建产物和大文件。客户端默认与服务端均按 256 MiB 压缩传输上限处理；不要通过把 archive 塞入 MCP JSON 绕过限制。

## source upload part failed after retries

检查本机是否可访问响应中的 TOS 区域端点，然后直接重跑同一个 `save-local` / `deploy-local` 命令。Skill 会从 `~/.al-site-mcp/uploads/<archive-sha256>.json` 恢复 caller-bound session，向服务端查询已完成 part，并只重传缺失分片。不要复制或打印 presigned URL。

若 session 已过期，Skill 会丢弃本地续传记录并创建新 session；旧 TOS multipart 由平台 staging GC 回收。

## remote branch does not point at local HEAD

先 push 当前 commit，再重试。Skill 不会自动 push，也不会把本地 Git credential 隐式传入 Site。

## GitCommitNotFound

常见原因：commit 未 push、repository URL 只在本机可达、私有仓库没有 importer credential、SSH 缺少固定 `knownHosts`，或 Site 构建网络无法访问远端。

## 版本或部署一直未 Ready

```bash
python3 scripts/al_site.py version VERSION_ID --site-id SITE_ID
python3 scripts/al_site.py get-site-logs --arg site_id=SITE_ID
python3 scripts/al_site.py get-site-events --arg site_id=SITE_ID
python3 scripts/al_site.py deployment DEPLOYMENT_ID --site-id SITE_ID
```

以返回的 `phase`、conditions、错误 code 和真实 URL 为准，不用 Pod Ready 或客户端 HTTP timeout 代替业务状态。
