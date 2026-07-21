---
name: al-site-skill
description: Use when deploying local code or operating persistent AL Sites through the public Site MCP Gateway, including direct local SourceBundle upload, optional Sandbox composition, Git or OCI sources, Site creation, immutable versions, deployment, rollout, access policy, domains, observability, add-ons, and cleanup.
---

# AL Site MCP Client

使用这个 skill 调用 AL Site 系统。它是独立客户端，不安装 MCP Server，也不依赖 `al-sandbox-skill`。所有调用都经过公网 `al-site-mcp-gateway`，由 Gateway 完成 OAuth 身份解析并转发到内网 `al-site-tools-mcp`。

## 开始前

dev 环境尚未为 Site MCP 分配并启用独立公网 Gateway，因此当前没有可安全内置的默认地址。首次使用先配置实际 Gateway：

```bash
python3 scripts/al_site.py configure --gateway-url https://<site-mcp-public-host>
python3 scripts/al_site.py login
```

也可以只对当前进程设置：

```bash
export AL_SITE_MCP_GATEWAY_URL=https://<site-mcp-public-host>
```

不要使用 Site Access Gateway、Site 应用域名或 APIG Ingress 的占位 host 代替 Site MCP Gateway。它们是不同的流量和信任边界。

## 默认行为

- 首次工具调用时自动打开 Gateway `/login`，通过 OAuth Authorization Code + PKCE 登录，并由 loopback 回调缓存短期 access token。
- 首次使用自动生成并缓存 conversation id。conversation 只保存当前 Site 选择，不拥有或控制 Site 生命周期。
- Site 是持久资源。`archive` 只删除 conversation 到 Site 的选择，不停止、不删除 Site。
- `DeleteSite` 是永久删除操作，必须由用户明确要求并传 `confirm=true`。
- 工具调用失败或 MCP 返回 `isError=true` 时，脚本非零退出，不能把业务错误当成成功。

## 动态工具发现

MCP Server 的 `tools/list` 是唯一完整契约。先发现，再调用：

```bash
python3 scripts/al_site.py tools
python3 scripts/al_site.py tools --names
python3 scripts/al_site.py tools --filter deployment
python3 scripts/al_site.py describe SaveSiteVersion
python3 scripts/al_site.py call GetCurrentSite
python3 scripts/al_site.py call SetSiteAccessPolicy \
  --arguments '{"site_id":"example","audience":"owner"}'
```

脚本为当前每个 Site MCP 工具都生成 kebab-case 入口，例如：

```bash
python3 scripts/al_site.py get-site-events --arg site_id=example
python3 scripts/al_site.py set-site-domain \
  --arg site_id=example --arg hostname=www.example.org --arg verification_method=dns-txt
```

这些入口和 `call` 都接受 `--arguments` JSON object 或 `@file.json`，以及可重复的 `--arg key=value`。value 会尽量解析为 JSON scalar/object/array。

## 常用生命周期

创建、选择和查看 Site：

```bash
python3 scripts/al_site.py create "My Site"
python3 scripts/al_site.py select SITE_ID
python3 scripts/al_site.py current
python3 scripts/al_site.py sites
```

保存不可变版本：

```bash
# 独立 Site：直接把本地目录规范化、上传并保存为不可变 SourceBundle
python3 scripts/al_site.py save-local . --site-id SITE_ID

# 从当前 conversation 的 Sandbox 导出；这是唯一依赖 Sandbox 的来源
python3 scripts/al_site.py save-current --site-id SITE_ID

# 独立 Site：从远端不可变 Git commit 构建
python3 scripts/al_site.py save-git REPOSITORY COMMIT_SHA --site-id SITE_ID

# 独立 Site：部署已固定 digest 的 OCI image
python3 scripts/al_site.py save-oci REGISTRY/REPOSITORY@sha256:DIGEST --site-id SITE_ID
```

等待构建并部署：

```bash
python3 scripts/al_site.py wait-version VERSION_ID --site-id SITE_ID
python3 scripts/al_site.py deploy VERSION_ID --site-id SITE_ID
python3 scripts/al_site.py wait-deployment DEPLOYMENT_ID --site-id SITE_ID
```

## 独立部署本地目录

`deploy-local` 是独立 Site 的默认开发路径。它不要求项目是 Git 仓库，也不调用 Sandbox：

```bash
python3 scripts/al_site.py deploy-local . --site-id SITE_ID
```

客户端会先执行与服务端一致的关键安全预检：平台 denylist、`.alignore`、大小/文件数/路径限制、symlink 边界和高置信凭据扫描；随后生成确定性的 tar.gz。Site MCP 只代理小型上传控制 JSON，客户端使用 Site Manager 签发的精确短期 URL 将归档分片直接上传到 TOS；源码字节不经过 MCP 或 APIG。服务端完成后会重新校验归档长度和 SHA-256、安全解包、执行完整规范化和扫描，发布到平台自有 OCI `source@sha256:...`，再进入与 Sandbox/Git 完全相同的 build、scan、preview、deploy 状态机。

分片 ETag 和 caller-bound session token 只写入权限为 `0600` 的 `~/.al-site-mcp/uploads/<archive-sha256>.json`，中断后会先向 TOS 查询已完成分片再续传；presigned URL、OAuth token 和最终 receipt 都不写入该文件。上传返回的短期 receipt 只在当前进程内交给 `SaveSiteVersion`，不会写入 `~/.al-site-mcp/state.json`，也不会打印。若保存版本前失败，平台 orphan GC 会回收未引用的 OCI 制品，TOS staging 则由短 TTL 与 multipart GC 回收。

`.alignore` 用于排除不应发布的构建缓存和本地文件；平台 denylist（如 `.git`、`.env`、`.ssh`、`.aws`、`.kube`、Docker/npm/pypi 凭据文件）不可通过 negation 重新包含。详见 `references/local-source.md`。

## 可选的本地 Git 发布

`deploy-local-git` 不使用 Sandbox。它验证工作区干净、HEAD 是 40～64 位 commit、当前分支的远端 ref 正好指向该 commit，然后调用 `SaveSiteVersion(source=git)`，等待版本 Ready，再调用 `DeploySiteVersion`：

```bash
python3 scripts/al_site.py deploy-local-git . --site-id SITE_ID
```

私有 HTTPS Git 凭据只能从环境变量读取，避免写入命令行历史：

```bash
export MY_GIT_AUTH='Bearer <token>'
python3 scripts/al_site.py deploy-local-git . \
  --site-id SITE_ID \
  --credential-env MY_GIT_AUTH
```

SSH 来源的环境变量值必须是 Site source importer 支持的 JSON，包含 `sshPrivateKey` 与固定的 `knownHosts`。不要使用 `--skip-remote-check`，除非调用方已经用其他权威方式验证 commit 可从 Site 构建网络访问。

本命令不会自动 commit、push 或复制本地凭据。需要发布未提交内容或非 Git 目录时使用 `save-local` / `deploy-local`。

## 独立与组合模式

- Site 独立模式：`save-local`、`save-git`、`save-oci` 以及全部 Site 生命周期工具不依赖 Sandbox，部署 Site MCP 时可以完全关闭 Sandbox integration。
- Sandbox 独立模式：`al-sandbox-skill` 与 Sandbox MCP 不依赖 Site，保留原有开发、文件、Bash、浏览器和部署能力。
- 组合模式：只有 `save-current` 会请求 Sandbox MCP 为当前 conversation 签发一次性 SourceBundle export grant；Site 随后仍把产物落为自己的不可变 OCI SourceBundle，并独立完成生产构建和发布。
- 两个 skill 的 token、conversation 和本地状态互不读取。组合关系发生在服务端的窄契约上，而不是让一个 skill 调另一个 skill。

## 生命周期与安全约定

- `al-site-skill` 和 `al-sandbox-skill` 分别保存 token、conversation 和状态目录，互不读取。
- `current_conversation` 只在用户明确要求从当前 Sandbox 保存版本时使用；local、Git 和 OCI 路径独立于 Sandbox。
- SiteVersion、SiteDeployment 和 OCI digest 都是不可变发布输入。不要通过重复调用伪造更新。
- 发布前读取 `GetSiteVersion` 的真实 `phase=Ready`；部署后读取 `GetSiteDeployment` 的真实 `phase=Ready` 和返回 URL。
- public、rollback、governance、domain delete、version delete 和 Site delete 等高影响操作，先读取动态 schema 和当前资源版本，再按用户明确意图调用。
- 认证见 `references/auth.md`，配置见 `references/config.md`，完整工具映射见 `references/tools.md`，本地上传见 `references/local-source.md`，Git 发布见 `references/local-git.md`，排障见 `references/troubleshooting.md`。
