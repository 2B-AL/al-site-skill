---
name: al-site
description: Use al-site to deploy local, Git, OCI, or AL Sandbox handoff source as persistent AL Sites and to manage immutable versions, production releases, blue-green and canary rollout, Header or signed-cookie lanes, promotion, pause, resume, rollback, VMP-backed metrics, Knative scaling, access, domains, and cleanup through the public Site MCP Gateway.
---

# AL Site

Operate AL Site only through `scripts/al_mcp.py`. Do not bypass this client with Kubernetes, Knative, VMP, raw Site Manager HTTP, or hand-written MCP JSON when a strong command exists.

## Establish the live contract

Run these before a release workflow:

```bash
python3 scripts/al_mcp.py tools --names
python3 scripts/al_mcp.py describe GetSitePlatformCapabilities
python3 scripts/al_mcp.py call GetSitePlatformCapabilities
```

Treat `tools/list`, the online schema, and capability `supported/configured/ready` fields as authoritative. A feature implemented in source but reported unready by the environment is unavailable.

For a non-mutating health check, use `python3 scripts/al_mcp.py doctor`. It never starts login, creates a conversation, issues a Grafana link, or calls a mutating Site tool; missing cached authentication or conversation state is reported instead.

The default dev endpoint is the Site MCP Gateway, not the Site Access Gateway or an Ingress placeholder host. Override other environments with `configure --gateway-url` or `AL_SITE_MCP_GATEWAY_URL`.

## Select the resource explicitly

```bash
python3 scripts/al_mcp.py sites
python3 scripts/al_mcp.py sites --relation accessible
python3 scripts/al_mcp.py select SITE_ID
python3 scripts/al_mcp.py current
```

`created` means created by the caller. `accessible` means the caller currently has control-plane access through user/team/org ownership. Public application reachability is not control-plane access. Query the latest UID, owner, status, and resource version before any destructive operation.

## Save an immutable version

Choose exactly one source path:

```bash
python3 scripts/al_mcp.py save-local . --site-id SITE_ID
python3 scripts/al_mcp.py save-git REPOSITORY COMMIT_SHA --site-id SITE_ID
python3 scripts/al_mcp.py save-oci IMAGE@sha256:DIGEST --site-id SITE_ID
python3 scripts/al_mcp.py save-current --handoff @/tmp/al-site-handoff.json --site-id SITE_ID
```

For a remote dependency-free static Git commit, the client cannot inspect source files. Only when the caller has verified that all assets, navigation, fetches, and service-worker scope work below the Site path prefix, use:

```bash
python3 scripts/al_mcp.py save-git REPOSITORY COMMIT_SHA --site-id SITE_ID \
  --build '{"mode":"static"}' --confirm-path-prefix-aware
```

The flag is an explicit assertion, not a source rewrite. Omit it to fail closed when prefix compatibility is unknown.

Every strong save command calls `PlanSiteVersion` before upload or CR creation. Keep `build.dockerfile` relative to `build.context`; use a numeric non-root final `USER`. Never export an entire Sandbox when only a project subdirectory is needed. Read [references/local-source.md](references/local-source.md), [references/local-git.md](references/local-git.md), or [references/versions.md](references/versions.md) when the source or version workflow is relevant.

## Plan, release, and observe

Never call `DeploySiteVersion` without a fresh `PlanSiteDeployment` result. Use the strong commands; they preserve the exact normalized intent, carry `plan_revision`, and retry the same visible intent once if the plan becomes stale.

```bash
python3 scripts/al_mcp.py release-plan VERSION_ID --immediate
python3 scripts/al_mcp.py release VERSION_ID --immediate --wait
python3 scripts/al_mcp.py release VERSION_ID --blue-green --wait-candidate
python3 scripts/al_mcp.py release VERSION_ID \
  --canary 5,25,100 --step-duration 5m \
  --min-requests 100 --max-error-rate 0.01 \
  --failure-action rollback --wait
```

All publishing shortcuts use the same release options:

- `deploy-local`
- `deploy-local-git`
- `test-deploy-local`
- `test-deploy-current`
- `release` (`deploy` is an alias using the same Plan flow)

Use `release-status DEPLOYMENT_ID --watch` for the product status view. It reports stable/candidate targets, percent, sticky routing, gate snapshots, blocking codes, scaling, and next actions. Do not infer state from arbitrary Condition messages. Exit code `3` means the release is safely paused and requires an explicit action; other failures are nonzero.

Read [references/release.md](references/release.md) before choosing Blue-Green, Canary, metric gates, or rollback behavior.

For a bounded platform regression run, use `test-release-matrix PATH --confirm --confirm-public --confirm-path-prefix-aware` after verifying that the application works below a non-root APIG path prefix. The assertion never rewrites source files. The command creates one UID-tracked test Site and verifies Immediate, protected Blue-Green candidate, Promote, Canary, Rollback, current scaling, and public smoke checks. Add `--cleanup` only when the exact test Site should be deleted after success; on failure use the retained run manifest with `cleanup-test-run --confirm`.

## Validate candidate lanes

```bash
python3 scripts/al_mcp.py release VERSION_ID --blue-green --signed-lane beta --wait-candidate
python3 scripts/al_mcp.py release VERSION_ID --canary 5,25,100 \
  --lane-header X-AL-Site-Lane=beta --sticky --wait-candidate
python3 scripts/al_mcp.py open-lane DEPLOYMENT_ID beta --open-browser
python3 scripts/al_mcp.py revoke-lane DEPLOYMENT_ID beta --confirm
```

`--wait-candidate` performs a real request through the public Site URL and requires the Gateway to report `X-AL-Site-Target: candidate`. Blue-Green automatically creates a protected `preview` signed lane when none is supplied.

Header Lane keys come only from the platform allowlist; the exact value belongs to the release. A public header is a route selector, never authentication. Signed lanes use a short-lived one-time activation grant and HttpOnly path-scoped cookie. Never log or persist activation fragments or cookies. Read [references/lanes.md](references/lanes.md) for the exact trust boundary.

## Perform release actions

```bash
python3 scripts/al_mcp.py promote DEPLOYMENT_ID --confirm
python3 scripts/al_mcp.py pause DEPLOYMENT_ID
python3 scripts/al_mcp.py resume DEPLOYMENT_ID
python3 scripts/al_mcp.py resume DEPLOYMENT_ID --extend-timeout 10m
python3 scripts/al_mcp.py cancel DEPLOYMENT_ID --confirm
python3 scripts/al_mcp.py rollback HISTORICAL_DEPLOYMENT_ID --confirm --wait
```

The client first reads current step, phase, routing epoch, UID, and resource version. MCP maps them to Manager preconditions; do not hand-edit these values. Rollback always plans first, creates a new immutable Deployment, and never rolls back database or Add-on data. Review any migration warning before confirmation.

## Manage versions and scaling

```bash
python3 scripts/al_mcp.py versions
python3 scripts/al_mcp.py version VERSION_ID
python3 scripts/al_mcp.py version-diff VERSION_A VERSION_B
python3 scripts/al_mcp.py retry-version VERSION_ID --confirm --wait
python3 scripts/al_mcp.py delete-version VERSION_ID --confirm

python3 scripts/al_mcp.py scaling-status
python3 scripts/al_mcp.py scaling-set-defaults --profile balanced
python3 scripts/al_mcp.py scaling-apply --profile latency --confirm --wait
python3 scripts/al_mcp.py scaling-apply --profile custom \
  --min-scale 1 --max-scale 20 --target-concurrency 20 --confirm --wait

python3 scripts/al_mcp.py observe --dashboard overview --time-range 1h --open-browser
python3 scripts/al_mcp.py observe --dashboard rollout --time-range 6h
```

`observe` first asks Site MCP to re-authorize the selected Site and then requests an AL OAuth protected Grafana launch URL. Inspect `stable`, `_meta.lifecycle_stable`, and `expires_at` instead of assuming a TTL: a lifecycle-stable locator is not a data-plane credential and revalidates current access whenever it is opened. This does not mutate the Site. Never construct Grafana URLs or tenant query parameters manually. Dashboard-link failure is diagnostic only and must not change build, release, rollback, or scaling state.

`GetSiteScaling`, `GetSiteMetrics`, and `GetSiteUsage` are read-only and may consume one bounded MCP retry when the Manager explicitly reports a retryable observability 429/502/503/504. Workflow waits continue within their existing deadline after that budget is exhausted. Never extend this behavior to release, promotion, rollback, scaling apply, or any other mutating tool, and never turn unavailable metrics into a passing gate.

Resume never resets the observation window. If structured status reports `PausedStepTimeoutElapsed`, require the user to choose `resume --extend-timeout DURATION` or rollback. `retry-version` is only for a terminal transient build after SourceBundle resolution; it reuses the same immutable source, consumes a bounded retry budget, and refuses versions that used expired build secrets. It is not a way to retry source, policy, scan, or runtime-contract failures. `delete-version` first reads the latest Version UID and resourceVersion, then forwards both with explicit confirmation; the platform refuses active or otherwise referenced Versions. `scaling-set-defaults` changes future defaults only. `scaling-apply --confirm` plans and creates a new immutable Deployment for the active Version. Never describe a defaults update as changing current production. Read [references/scaling.md](references/scaling.md) and [references/versions.md](references/versions.md).

## Preserve safety boundaries

- SiteVersion and SiteDeployment are immutable records; create a new one instead of mutating history.
- Immediate, 100% promote, rollback, public publishing, lane revoke, current scaling changes, governance, and deletion require explicit user intent.
- Automatic rollback with a migration is allowed only when `application_backward_compatible=true`; otherwise use `failureAction=pause` and request review.
- Metric data missing or VMP unavailable must not silently pass. Prefer `missing-data=wait`; use `pass` only on explicit instruction.
- `archive` removes only the conversation selection. It does not stop or delete a Site.
- Test cleanup uses the recorded 0600 run manifest and exact Site UID; never clean by prefix.
- Never print OAuth tokens, HMAC values, lane grants, cookies, TOS receipts, presigned URLs, build secrets, or VMP credentials.

Read [references/troubleshooting.md](references/troubleshooting.md) for structured failure handling, [references/tools.md](references/tools.md) for tool mappings, [references/auth.md](references/auth.md) for login, and [references/config.md](references/config.md) for endpoint configuration.
