# Site MCP tools

Treat the online `tools/list` response as the authoritative contract. The current skill expects and covers the tools below. Call each tool either with `call ToolName` or through its automatically generated kebab-case command.

| Area | Tools |
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

## Dynamic discovery and generic calls

```bash
python3 scripts/al_mcp.py tools --names
python3 scripts/al_mcp.py describe PromoteSiteDeployment
python3 scripts/al_mcp.py call PromoteSiteDeployment --arguments @promote.json
python3 scripts/al_mcp.py promote-site-deployment --arguments @promote.json
```

`--arguments` must be a JSON object. Repeat `--arg` as needed; it overrides fields with the same name:

```bash
python3 scripts/al_mcp.py set-site-access-policy \
  --arg site_id=my-site \
  --arg audience=selected \
  --arg 'users=["user-1"]'
```

## Common strongly typed commands

| Command | MCP tool |
| --- | --- |
| `create` | `CreateSite` |
| `select` | `SelectSite` |
| `current` | `GetCurrentSite` |
| `sites [--relation created\|accessible] [--owner-kind ...] [--phase ...]` | `ListSites`; lists only Sites created by the current user by default and automatically traverses all pages |
| `get [SITE_ID] [--relation created\|accessible]` | `GetSite`; asserts existence under the same relation |
| `save-local` / `deploy-local` | Gateway binary upload + `SaveSiteVersion(source_bundle)` |
| `save-current --handoff @file` | `PlanSiteVersion` + `SaveSiteVersion(sandbox_handoff)` |
| `test-deploy-local` / `test-deploy-current` | Create a dedicated test Site, complete plan/version/deployment/smoke, and write an exact resource manifest |
| `cleanup-test-run RUN_FILE --confirm` | After UID verification, delete only the test Site and controlled child resources recorded in the manifest |
| `save-git` / `save-local-git` | `SaveSiteVersion(git)` |
| `save-oci` | `SaveSiteVersion(oci)` |
| `version` / `versions` / `version-diff` / `wait-version` / `retry-version` / `delete-version` | Immutable Version query, comparison, watch, bounded build retry, and preconditioned deletion |
| `release-plan` / `release` / `deploy` | `PlanSiteDeployment`, then `DeploySiteVersion(plan_revision)` |
| `release-status` | Structured `GetSiteReleaseStatus`; `--watch` exits with code 3 on an actionable pause |
| `open-lane` / `revoke-lane` | Signed candidate session and epoch revocation |
| `promote` / `pause` / `resume` / `cancel` / `rollback` | Current-state-protected release actions; rollback plans first |
| `scaling-status` / `scaling-set-defaults` / `scaling-apply` | Query, future defaults, or a planned current-production change |
| `deployment` / `deployments` / `wait-deployment` | `GetSiteDeployment` / `WatchSiteDeployment`; cursor-based long polling continues to display smoke, traffic, and gate state |
| `archive` | Gateway conversation archive endpoint |

For high-impact tools, do not rely only on a shortcut. Use `describe` first to confirm the online required fields, `resource_version`, and confirmation fields.

`created` is based on the creator identity persisted in the Site and is distinct from the owner, which may be a team or organization. `accessible` is based on current user/team/org owner membership and means that the caller has MCP control-plane management permission. A public or selected audience, public URL, or application access authentication belongs to the data plane and does not grant control-plane access. The server filters both queries by authenticated identity; the client never downloads the full collection and filters it locally. Query results consistently include creator, owner, relations, permissions, status, UID, resource version, time, and details. An update must include the latest `resource_version`. A deletion must include `confirm=true`, the latest `expected_uid`, and `resource_version`. On conflict, run Get again before deciding whether to retry.

`GetSitePlatformCapabilities` determines the audience, release strategy, lane, metric gate, scaling profile, and readiness supported by the current routing mode. The client must reject unsupported combinations before resource creation. In particular, it must never silently change an explicit `owner` audience to `public`. `PlanSiteVersion` is the source preflight. `PlanSiteDeployment` is the mandatory preflight for every production traffic change. When Plan is unavailable, strongly typed release commands must fail closed.
