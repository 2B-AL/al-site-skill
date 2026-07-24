# Site MCP 工具

在线 `tools/list` 是权威契约。当前 Skill 预期并覆盖以下工具；每个工具既可通过 `call ToolName` 调用，也有自动生成的 kebab-case 命令。

| 领域 | 工具 |
| --- | --- |
| Site | `CreateSite`, `SelectSite`, `GetCurrentSite`, `GetSite`, `ListSites`, `UpdateSite`, `DeleteSite` |
| Capability/Plan | `GetSitePlatformCapabilities`, `PlanSiteVersion`, `PlanSiteDeployment`, `PlanSiteScaling` |
| Version | `SaveSiteVersion`, `GetSiteVersion`, `WatchSiteVersion`, `GetSiteVersionLogs`, `CancelSiteVersion`, `ListSiteVersions`, `CompareSiteVersions`, `DeleteSiteVersion` |
| Release | `DeploySiteVersion`, `GetSiteDeployment`, `GetSiteReleaseStatus`, `WatchSiteDeployment`, `ListSiteDeployments`, `CreateSiteLaneSession`, `RevokeSiteLaneSessions`, `PromoteSiteDeployment`, `PauseSiteDeployment`, `ResumeSiteDeployment`, `CancelSiteDeployment`, `RollbackSite` |
| Scaling | `GetSiteScaling`, `PlanSiteScaling`, `UpdateSiteScaling` |
| Access/Governance | `GetSiteAccessPolicy`, `SetSiteAccessPolicy`, `SetSiteGovernance`, `SubmitSiteAppeal` |
| Domain | `SetSiteDomain`, `ListSiteDomains`, `VerifySiteDomain`, `DeleteSiteDomain` |
| Observability | `GetSiteLogs`, `GetSiteEvents`, `GetSiteMetrics`, `GetSiteUsage` |
| Add-on | `AttachSiteAddonBinding`, `DetachSiteAddonBinding` |
| Conversation | `ArchiveConversationSite` |

## 动态发现与通用调用

```bash
python3 scripts/al_mcp.py tools --names
python3 scripts/al_mcp.py describe PromoteSiteDeployment
python3 scripts/al_mcp.py call PromoteSiteDeployment --arguments @promote.json
python3 scripts/al_mcp.py promote-site-deployment --arguments @promote.json
```

`--arguments` 必须是 JSON object。`--arg` 可重复并覆盖同名字段：

```bash
python3 scripts/al_mcp.py set-site-access-policy \
  --arg site_id=my-site \
  --arg audience=selected \
  --arg 'users=["user-1"]'
```

## 常用强类型入口

| 命令 | MCP 工具 |
| --- | --- |
| `create` | `CreateSite` |
| `select` | `SelectSite` |
| `current` | `GetCurrentSite` |
| `sites [--relation created\|accessible] [--owner-kind ...] [--phase ...]` | `ListSites`；默认只列出当前用户创建的 Site，并自动遍历分页 |
| `get [SITE_ID] [--relation created\|accessible]` | `GetSite`；按同一关系做存在性断言 |
| `save-local` / `deploy-local` | Gateway binary upload + `SaveSiteVersion(source_bundle)` |
| `save-current --handoff @file` | `PlanSiteVersion` + `SaveSiteVersion(sandbox_handoff)` |
| `test-deploy-local` / `test-deploy-current` | 创建专用测试 Site，完成 plan/version/deployment/smoke，并写入精确资源清单 |
| `cleanup-test-run RUN_FILE --confirm` | UID 复核后仅删除该清单创建的测试 Site 及其受控子资源 |
| `save-git` / `save-local-git` | `SaveSiteVersion(git)` |
| `save-oci` | `SaveSiteVersion(oci)` |
| `version` / `versions` / `version-diff` / `wait-version` / `delete-version` | immutable Version query, comparison, watch, and preconditioned deletion |
| `release-plan` / `release` / `deploy` | `PlanSiteDeployment` then `DeploySiteVersion(plan_revision)` |
| `release-status` | structured `GetSiteReleaseStatus`; `--watch` exits 3 on actionable pause |
| `open-lane` / `revoke-lane` | signed candidate session and epoch revocation |
| `promote` / `pause` / `resume` / `cancel` / `rollback` | current-state protected release actions; rollback plans first |
| `scaling-status` / `scaling-set-defaults` / `scaling-apply` | query, future defaults, or planned current-production change |
| `deployment` / `deployments` / `wait-deployment` | `GetSiteDeployment` / `WatchSiteDeployment`; cursor 长轮询持续显示 smoke、traffic 和 gate 状态 |
| `archive` | Gateway conversation archive endpoint |

高影响工具不要只依赖快捷入口；调用前使用 `describe` 确认在线 required fields、`resource_version` 和确认字段。

`created` 依据 Site 中持久化的创建者身份，和可为 team/org 的 owner 分离；
`accessible` 依据当前 user/team/org owner 成员关系，表示调用者拥有 MCP 控制面管理权限。
public/selected audience、公网 URL 或应用侧访问认证属于数据面，不会授予控制面访问权限。
两种查询都由服务端按认证身份过滤，客户端不在本地下载全集后筛选。
查询统一返回 creator、owner、relations、permissions、status、UID、resource version、时间和 details。
更新必须携带最新 `resource_version`；删除必须携带 `confirm=true`、最新 `expected_uid` 和
`resource_version`，发生冲突时重新 Get 后再决定是否重试。

`GetSitePlatformCapabilities` 决定当前路由模式允许的 audience、release strategy、lane、metric gate、scaling profile 和 readiness。客户端必须在创建资源前拒绝不支持的组合，尤其不能把显式 `owner` 静默改成 `public`。`PlanSiteVersion` 是源码 preflight，`PlanSiteDeployment` 是所有生产流量变化的强制 preflight；没有 plan 能力时，强类型发布命令 fail closed。
