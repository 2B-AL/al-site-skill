# Site MCP 工具

在线 `tools/list` 是权威契约。当前 Skill 预期并覆盖以下工具；每个工具既可通过 `call ToolName` 调用，也有自动生成的 kebab-case 命令。

| 领域 | 工具 |
| --- | --- |
| Site | `CreateSite`, `SelectSite`, `GetCurrentSite`, `GetSite`, `ListSites`, `UpdateSite`, `DeleteSite` |
| Capability/Plan | `GetSitePlatformCapabilities`, `PlanSiteVersion` |
| Version | `SaveSiteVersion`, `GetSiteVersion`, `WatchSiteVersion`, `GetSiteVersionLogs`, `CancelSiteVersion`, `ListSiteVersions`, `DeleteSiteVersion` |
| Deployment | `DeploySiteVersion`, `GetSiteDeployment`, `WatchSiteDeployment`, `ListSiteDeployments`, `PromoteSiteDeployment`, `RollbackSite`, `CancelSiteDeployment`, `PauseSiteDeployment` |
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
| `sites` | `ListSites` |
| `save-local` / `deploy-local` | Gateway binary upload + `SaveSiteVersion(source_bundle)` |
| `save-current --handoff @file` | `PlanSiteVersion` + `SaveSiteVersion(sandbox_handoff)` |
| `test-deploy-local` / `test-deploy-current` | 创建专用测试 Site，完成 plan/version/deployment/smoke，并写入精确资源清单 |
| `cleanup-test-run RUN_FILE --confirm` | UID 复核后仅删除该清单创建的测试 Site 及其受控子资源 |
| `save-git` / `save-local-git` | `SaveSiteVersion(git)` |
| `save-oci` | `SaveSiteVersion(oci)` |
| `version` / `versions` / `wait-version` | `GetSiteVersion` / `WatchSiteVersion`; failure diagnostics use `GetSiteVersionLogs` including Preview runtime details |
| `deploy` | `DeploySiteVersion` |
| `deployment` / `deployments` / `wait-deployment` | `GetSiteDeployment` / `WatchSiteDeployment`; cursor 长轮询持续显示 smoke、traffic 和 gate 状态 |
| `archive` | Gateway conversation archive endpoint |

高影响工具不要只依赖快捷入口；调用前使用 `describe` 确认在线 required fields、`resource_version` 和确认字段。

`GetSitePlatformCapabilities` 决定当前路由模式允许的 audience、public publishing 和 identity forwarding 组合。客户端必须在创建资源前拒绝不支持的组合，尤其不能把显式 `owner` 静默改成 `public`。`PlanSiteVersion` 是所有源码后端共用的强制 preflight；没有 plan 能力时，强类型发布命令 fail closed。
