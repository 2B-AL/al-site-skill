# Site MCP 工具

在线 `tools/list` 是权威契约。当前 Skill 预期并覆盖以下工具；每个工具既可通过 `call ToolName` 调用，也有自动生成的 kebab-case 命令。

| 领域 | 工具 |
| --- | --- |
| Site | `CreateSite`, `SelectSite`, `GetCurrentSite`, `GetSite`, `ListSites`, `UpdateSite`, `DeleteSite` |
| Version | `SaveSiteVersion`, `GetSiteVersion`, `ListSiteVersions`, `DeleteSiteVersion` |
| Deployment | `DeploySiteVersion`, `GetSiteDeployment`, `ListSiteDeployments`, `PromoteSiteDeployment`, `RollbackSite`, `CancelSiteDeployment`, `PauseSiteDeployment` |
| Access/Governance | `GetSiteAccessPolicy`, `SetSiteAccessPolicy`, `SetSiteGovernance`, `SubmitSiteAppeal` |
| Domain | `SetSiteDomain`, `ListSiteDomains`, `VerifySiteDomain`, `DeleteSiteDomain` |
| Observability | `GetSiteLogs`, `GetSiteEvents`, `GetSiteMetrics`, `GetSiteUsage` |
| Add-on | `AttachSiteAddonBinding`, `DetachSiteAddonBinding` |
| Conversation | `ArchiveConversationSite` |

## 动态发现与通用调用

```bash
python3 scripts/al_site.py tools --names
python3 scripts/al_site.py describe PromoteSiteDeployment
python3 scripts/al_site.py call PromoteSiteDeployment --arguments @promote.json
python3 scripts/al_site.py promote-site-deployment --arguments @promote.json
```

`--arguments` 必须是 JSON object。`--arg` 可重复并覆盖同名字段：

```bash
python3 scripts/al_site.py set-site-access-policy \
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
| `save-current` | `SaveSiteVersion(current_conversation)` |
| `save-git` / `save-local-git` | `SaveSiteVersion(git)` |
| `save-oci` | `SaveSiteVersion(oci)` |
| `version` / `versions` / `wait-version` | Version read tools |
| `deploy` | `DeploySiteVersion` |
| `deployment` / `deployments` / `wait-deployment` | Deployment read tools |
| `archive` | Gateway conversation archive endpoint |

高影响工具不要只依赖快捷入口；调用前使用 `describe` 确认在线 required fields、`resource_version` 和确认字段。
