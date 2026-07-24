# al-site-skill

`al-site` 是一个纯 Site MCP 客户端 Skill。它通过 `scripts/al_mcp.py` 使用公网 Site MCP Gateway，不安装 MCP Server，也不依赖 Kubernetes、Knative、VMP 或 `al-sandbox`。同一个 Skill 覆盖源码保存、不可变版本、完整发布策略、灰度验收、回滚、指标和弹性。

## 快速开始

```bash
python3 scripts/al_mcp.py tools --names
python3 scripts/al_mcp.py call GetSitePlatformCapabilities
python3 scripts/al_mcp.py sites
python3 scripts/al_mcp.py create "My Site"
python3 scripts/al_mcp.py deploy-local . --site-id SITE_ID --immediate
```

首次调用会通过 Gateway `/login` 完成 OAuth Authorization Code + PKCE，并在本机缓存短期 token。默认 dev Gateway 可通过 `configure --gateway-url` 或 `AL_SITE_MCP_GATEWAY_URL` 覆盖。Site Access Gateway、用户 Site URL 和 APIG Ingress 占位 host 都不能代替 MCP Gateway。

## 版本与发布

```bash
# 版本历史与差异
python3 scripts/al_mcp.py versions --site-id SITE_ID
python3 scripts/al_mcp.py version-diff VERSION_A VERSION_B --site-id SITE_ID
python3 scripts/al_mcp.py delete-version VERSION_ID --site-id SITE_ID --confirm

# Immediate
python3 scripts/al_mcp.py release VERSION_ID --site-id SITE_ID --immediate --wait

# Blue-Green：候选 0%，真实公网 signed-lane 验收后再 Promote
python3 scripts/al_mcp.py release VERSION_ID --site-id SITE_ID \
  --blue-green --wait-candidate
python3 scripts/al_mcp.py promote DEPLOYMENT_ID --site-id SITE_ID --confirm

# Canary：5% -> 25% -> 100%，用 VMP 指标自动判定
python3 scripts/al_mcp.py release VERSION_ID --site-id SITE_ID \
  --canary 5,25,100 --step-duration 5m \
  --min-requests 100 --max-error-rate 0.01 \
  --max-p95-ms 1000 --failure-action rollback --wait
```

所有生产流量变化都先调用 `PlanSiteDeployment`，再携带短期 `plan_revision` 创建不可变 SiteDeployment。`deploy-local`、`deploy-local-git`、`test-deploy-local`、`test-deploy-current` 和 `release` 共用同一套 release options，不再有绕过 Plan 的 Immediate 快捷路径。

## Header 与 Signed Lane

```bash
python3 scripts/al_mcp.py release VERSION_ID --blue-green \
  --signed-lane beta --wait-candidate
python3 scripts/al_mcp.py open-lane DEPLOYMENT_ID beta --open-browser

python3 scripts/al_mcp.py release VERSION_ID --canary 5,25,100 \
  --lane-header X-AL-Site-Lane=beta --wait-candidate
```

Header Key 必须来自平台 capability allowlist，Value 由每次发布指定并做 exact match。Public Header 只是路由条件，不是认证。Signed Lane 使用一次性 fragment grant 换取 HttpOnly Cookie。`--wait-candidate` 会通过真实 Site 公网 URL 请求，并验证 Gateway 返回 `X-AL-Site-Target: candidate`。

## 发布动作与回滚

```bash
python3 scripts/al_mcp.py release-status DEPLOYMENT_ID --watch
python3 scripts/al_mcp.py pause DEPLOYMENT_ID
python3 scripts/al_mcp.py resume DEPLOYMENT_ID
# 如果暂停期间原 step timeout 已经过期，必须明确延长或改为 rollback
python3 scripts/al_mcp.py resume DEPLOYMENT_ID --extend-timeout 10m
python3 scripts/al_mcp.py cancel DEPLOYMENT_ID --confirm
python3 scripts/al_mcp.py rollback HISTORICAL_DEPLOYMENT_ID --confirm --wait
```

客户端会先读取最新 step、phase、routing epoch、UID 和 resource version。Rollback 会先返回当前/目标差异、历史 Revision 和 migration 风险，再创建新的不可变 Deployment；数据库和 Add-on 数据永远不会随应用流量回滚。

## 弹性

```bash
python3 scripts/al_mcp.py scaling-status
python3 scripts/al_mcp.py scaling-set-defaults --profile balanced
python3 scripts/al_mcp.py scaling-apply --profile latency --wait
python3 scripts/al_mcp.py scaling-apply --profile custom \
  --min-scale 1 --max-scale 20 --target-concurrency 20 --wait
```

`scaling-set-defaults` 只影响未来默认值；`scaling-apply` 会为当前 active Version 做 Plan，并创建新的不可变 Deployment。指标返回明确区分 `configured` 和 `available`，不会把缺失 VMP 数据伪装成零。

## 独立与组合使用

- 独立 Site：`save-local`、`save-git`、`save-oci` 和全部发布/弹性命令不依赖 Sandbox。
- 独立 Sandbox：`al-sandbox` 不依赖 Site。
- 组合模式：`al-sandbox handoff` 生成一次性 owner-bound 描述符，`save-current --handoff @file` 精确消费项目 SourceBundle。两个 Skill 的 token、conversation 和 state 互不读取。

## 安全与状态

- `tools/list` 和在线 capability 是唯一运行时契约。
- SiteVersion/SiteDeployment 不可变；不要修改历史模拟更新。
- public、100% promote、rollback、lane revoke、当前弹性变化和删除需要明确意图。
- 自动回滚遇到未声明向后兼容的 migration 会暂停，不会冒险切回旧应用。
- `archive` 只清除 conversation 选择，不删除 Site。
- 需要人工动作的 Paused 以 JSON 输出并使用退出码 `3`；失败使用其他非零退出码。

完整 Agent 约定见 [SKILL.md](SKILL.md)。策略、Lane、弹性、版本与排障分别见 [references/release.md](references/release.md)、[references/lanes.md](references/lanes.md)、[references/scaling.md](references/scaling.md)、[references/versions.md](references/versions.md) 和 [references/troubleshooting.md](references/troubleshooting.md)。
