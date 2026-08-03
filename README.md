# al-site-skill

[Chinese](README.zh-CN.md)

`al-site` is a pure Site MCP client skill. It uses the public Site MCP Gateway through `scripts/al_mcp.py`; it does not install an MCP Server and does not depend on Kubernetes, Knative, VMP, or `al-sandbox`. One skill covers source capture, immutable versions, complete release policies, staged acceptance, rollback, metrics, and scaling.

## Quick start

```bash
python3 scripts/al_mcp.py tools --names
python3 scripts/al_mcp.py call GetSitePlatformCapabilities
python3 scripts/al_mcp.py sites
python3 scripts/al_mcp.py create "My Site"
python3 scripts/al_mcp.py deploy-local . --site-id SITE_ID --immediate
```

On the first call, the Gateway completes OAuth Authorization Code + PKCE through `/login` and caches a short-lived token locally. Override the default dev Gateway with `configure --gateway-url` or `AL_SITE_MCP_GATEWAY_URL`. The Site Access Gateway, a user Site URL, and an APIG Ingress placeholder host cannot substitute for the MCP Gateway.

## Versions and releases

```bash
# Version history and comparison
python3 scripts/al_mcp.py versions --site-id SITE_ID
python3 scripts/al_mcp.py version-diff VERSION_A VERSION_B --site-id SITE_ID
python3 scripts/al_mcp.py retry-version VERSION_ID --site-id SITE_ID --confirm --wait
python3 scripts/al_mcp.py delete-version VERSION_ID --site-id SITE_ID --confirm

# Immediate
python3 scripts/al_mcp.py release VERSION_ID --site-id SITE_ID --immediate --wait

# Blue-Green: keep the candidate at 0%, validate through a real public signed lane, then Promote
python3 scripts/al_mcp.py release VERSION_ID --site-id SITE_ID \
  --blue-green --wait-candidate
python3 scripts/al_mcp.py promote DEPLOYMENT_ID --site-id SITE_ID --confirm

# Canary: 5% -> 25% -> 100%, evaluated automatically with VMP metrics
python3 scripts/al_mcp.py release VERSION_ID --site-id SITE_ID \
  --canary 5,25,100 --step-duration 5m \
  --min-requests 100 --max-error-rate 0.01 \
  --max-p95-ms 1000 --failure-action rollback --wait
```

Every production traffic change first calls `PlanSiteDeployment`, then creates an immutable SiteDeployment with a short-lived `plan_revision`. `deploy-local`, `deploy-local-git`, `test-deploy-local`, `test-deploy-current`, and `release` all use the same release options. There is no separate Immediate shortcut that bypasses Plan.

The client cannot inspect the contents of a remote Git commit. In a path-routed environment, the caller must explicitly assert prefix compatibility for a static project; the client must not guess:

```bash
python3 scripts/al_mcp.py save-git REPOSITORY COMMIT_SHA --site-id SITE_ID \
  --build '{"mode":"static"}' --confirm-path-prefix-aware
```

`--confirm-path-prefix-aware` is a source-contract assertion and does not rewrite HTML, CSS, or JavaScript. If you cannot confirm the contract, omit the flag and let `PlanSiteVersion` fail closed.

## Automated release matrix

```bash
python3 scripts/al_mcp.py test-release-matrix . \
  --confirm --confirm-public --confirm-path-prefix-aware --cleanup
```

This command operates only on a dedicated test Site with a recorded UID. It validates Immediate, Blue-Green with a signed lane, Canary, Promote, Rollback, current scaling changes, and public probes at every stage. On failure, it retains a mode `0600` run manifest for exact recovery with `cleanup-test-run`. It deletes the test Site automatically only after complete success and only when `--cleanup` is supplied.

## Headers and signed lanes

```bash
python3 scripts/al_mcp.py release VERSION_ID --blue-green \
  --signed-lane beta --wait-candidate
python3 scripts/al_mcp.py open-lane DEPLOYMENT_ID beta --open-browser

python3 scripts/al_mcp.py release VERSION_ID --canary 5,25,100 \
  --lane-header X-AL-Site-Lane=beta --wait-candidate
```

The Header Key must come from the platform capability allowlist. Each release supplies a Value that is matched exactly. A public header is only a routing condition, not authentication. A signed lane exchanges a one-time fragment grant for an HttpOnly cookie. `--wait-candidate` sends a request through the real public Site URL and verifies that the Gateway returns `X-AL-Site-Target: candidate`.

## Release actions and rollback

```bash
python3 scripts/al_mcp.py release-status DEPLOYMENT_ID --watch
python3 scripts/al_mcp.py pause DEPLOYMENT_ID
python3 scripts/al_mcp.py resume DEPLOYMENT_ID
# If the original step timeout elapsed during the pause, explicitly extend it or choose rollback
python3 scripts/al_mcp.py resume DEPLOYMENT_ID --extend-timeout 10m
python3 scripts/al_mcp.py cancel DEPLOYMENT_ID --confirm
python3 scripts/al_mcp.py rollback HISTORICAL_DEPLOYMENT_ID --confirm --wait
```

Before acting, the client reads the latest step, phase, routing epoch, UID, and resource version. Rollback first displays the current/target differences, historical Revision, and migration risk, then creates a new immutable Deployment. Database and Add-on data are never rolled back with application traffic.

## Scaling

```bash
python3 scripts/al_mcp.py scaling-status
python3 scripts/al_mcp.py scaling-set-defaults --profile balanced
python3 scripts/al_mcp.py scaling-apply --profile latency --confirm --wait
python3 scripts/al_mcp.py scaling-apply --profile custom \
  --min-scale 1 --max-scale 20 --target-concurrency 20 --confirm --wait

python3 scripts/al_mcp.py observe --dashboard overview --time-range 1h --open-browser
python3 scripts/al_mcp.py observe --dashboard rollout --time-range 6h
```

`observe` first asks Site MCP to revalidate the current caller's access relation to the Site, then requests an AL OAuth-protected Grafana entry point. Read `stable`, `_meta.lifecycle_stable`, and `expires_at` from the response instead of assuming a link TTL. A lifecycle-stable entry point is not a data-plane credential and rechecks current permissions whenever it is opened. Never construct a Grafana URL or tenant query parameters manually. Dashboard unavailability does not change build, release, rollback, or scaling state.

`scaling-set-defaults` affects only future defaults. `scaling-apply` plans against the current active Version and creates a new immutable Deployment. Metric responses distinguish `configured` from `available` and never fabricate missing VMP data as zero. Read-only metric tools retry once with a short backoff only when MCP explicitly classifies a VMP 429/502/503/504 as retryable. Matrix waits remain within the original overall deadline. A persistent failure returns the final error code, request ID, and read attempt without advancing the release.

## Independent and combined use

- Standalone Site: `save-local`, `save-git`, `save-oci`, and every release or scaling command operate without Sandbox.
- Standalone Sandbox: `al-sandbox` operates without Site.
- Combined mode: `al-sandbox handoff` creates a one-time owner-bound descriptor, and `save-current --handoff @file` consumes the exact project SourceBundle. The two skills never read each other's token, conversation, or state.

## Safety and state

- Treat `tools/list` and online capabilities as the only runtime contract.
- Treat SiteVersion and SiteDeployment as immutable. Do not modify history to simulate an update.
- Require explicit intent for public access, 100% promotion, rollback, lane revocation, current scaling changes, and deletion.
- Pause automatic rollback for a migration unless backward compatibility was explicitly declared; do not risk switching traffic back to the old application.
- `archive` clears only the conversation selection and does not delete a Site.
- Print a Paused state requiring manual action as JSON and exit with code `3`; use another nonzero code for failure.

See [SKILL.md](SKILL.md) for the complete Agent instructions. See [references/release.md](references/release.md), [references/lanes.md](references/lanes.md), [references/scaling.md](references/scaling.md), [references/versions.md](references/versions.md), and [references/troubleshooting.md](references/troubleshooting.md) for release policy, lanes, scaling, versions, and troubleshooting.
