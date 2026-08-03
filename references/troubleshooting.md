# Troubleshooting

## Structured release errors

Start release troubleshooting with:

```bash
python3 scripts/al_mcp.py release-status DEPLOYMENT_ID --watch
```

Make decisions only from `state`, `blockedBy[].code`, `gate`, and `nextActions`; do not parse free-form Condition text. Common responses:

- `DeploymentPlanStale`: the client replans the exact same visible intent only once. If that also fails, recheck the active rollout.
- `ManualApprovalRequired`: validate the candidate through a signed or header lane, then use `promote --confirm` or rollback.
- `MetricSamplesInsufficient`: display the current sample count, continue waiting or generate the intended traffic, and never force the result to pass.
- `ObservabilityUnavailable`: keep stable unchanged. Read-only metric tools first perform one bounded retry, while workflow waits continue within the original deadline. If the failure persists, use the returned request ID to inspect the VMP workspace, prometheus-agent, ServiceMonitor, and Adapter readiness. Do not use stale metrics or force the release to advance.
- `RollbackBlockedByMigration`: the database is not rolled back. Require an application and migration compatibility review and use `failureAction=pause`.
- `ScalingQuotaExceeded`: reduce the candidate maxScale based on capability quota/headroom.

## Candidate lane does not match

`--wait-candidate` requires the public response header `X-AL-Site-Target: candidate`. If it fails, confirm that the Deployment candidate, routing epoch, and lanes appear in `release-status`; do not request a private Knative URL directly. For a Header Lane, also confirm that the Key is in the capability allowlist and the Value matches exactly. A Signed Lane grant can be consumed only once; run `open-lane` again after it expires.

## Metrics are configured but unavailable

`configured=true, available=false` does not mean zero traffic. Check, in order, the Provider's VMP query output, the Adapter VMP Secret, Adapter `/readyz`, the prometheus-agent add-on, ServiceMonitor labels, and actual series freshness. Skill/MCP must not submit arbitrary PromQL.

## Switch the Site MCP Gateway

The current dev environment includes a dedicated Site MCP Gateway. Configure a Gateway only for another environment or when explicitly clearing or overriding configuration:

```bash
python3 scripts/al_mcp.py configure --gateway-url https://<site-mcp-public-host>
```

The Site Access Gateway and a user Site URL cannot substitute for the MCP Gateway.

## OAuth login is not configured

The Gateway is deployed, but `oauthRedirectURI` is unset or the OAuth static client does not register the exact same callback. Read the real public APIG domain first, then configure:

```text
https://<site-mcp-public-host>/oauth/callback
```

in both the Gateway and the OAuth client. The Ingress `spec.rules[].host` must still use only a placeholder host; never put this real domain there.

## conversation id is required

The script generates one automatically. To pin it explicitly:

```bash
export AL_SITE_CONVERSATION_ID=<uuid>
```

## No current Site is selected

```bash
python3 scripts/al_mcp.py sites
python3 scripts/al_mcp.py select SITE_ID
```

After `archive`, the Site still exists; the conversation simply no longer selects it.

## local Git working tree is not clean

`save-local-git` and `deploy-local-git` accept only an immutable commit. Commit or remove every tracked and untracked change, then retry. Do not bypass the check to publish content that differs from the commit.

If the goal is to publish the current working tree contents, use:

```bash
python3 scripts/al_mcp.py save-local . --site-id SITE_ID
```

## high-confidence credential material detected

The source directory contains a suspected private key, AWS key, GitHub token, or Slack token. Remove the file, or add it to `.alignore` only when it is genuinely outside the Site build input. Platform-denied credential directories require no manual configuration and cannot be re-included.

## source archive exceeds the configured upload limit

Use `.alignore` to exclude dependency caches, build outputs, and large files. Both the client and server default to a 256 MiB compressed transfer limit. Do not bypass it by putting an archive into MCP JSON.

## source upload part failed after retries

Confirm that the local machine can reach the TOS regional endpoint in the response, then rerun the same `save-local` or `deploy-local` command. The skill resumes the caller-bound session from `~/.al-site-mcp/uploads/<archive-sha256>.json`, queries the server for completed parts, and retransmits only missing parts. Never copy or print a presigned URL.

If the session expired, the skill discards the local resume record and creates a new session. Platform staging GC collects the old TOS multipart upload.

## remote branch does not point at local HEAD

Push the current commit, then retry. The skill does not push automatically and does not implicitly pass local Git credentials to Site.

## GitCommitNotFound

Common causes include an unpushed commit, a repository URL reachable only from the local machine, missing importer credentials for a private repository, SSH without fixed `knownHosts`, or a remote repository unreachable from the Site build network.

## DockerfileNotFound

Interpret `build.dockerfile` relative to `build.context`, not relative to the SourceBundle root a second time. For source at `app/Dockerfile`, use:

```json
{"mode":"dockerfile","context":"app","dockerfile":"Dockerfile"}
```

If both `context=app` and `dockerfile=app/Dockerfile` are configured, Build Executor looks for `app/app/Dockerfile`. Every strongly typed save command now calls `PlanSiteVersion` first. For sources with a handoff or local manifest, the plan returns the resolved missing path before creating an immutable Version.

## image has non-numeric user

When a Preview Pod reports:

```text
container has runAsNonRoot and image has non-numeric user (nonroot), cannot verify user is non-root
```

Change the final Dockerfile stage from a named user to a numeric non-root UID/GID, for example:

```dockerfile
USER 65532:65532
```

Do not relax Site `runAsNonRoot`. Client lint rejects an explicit named `USER` or UID 0 in the final stage. Before Preview, the platform also validates the final OCI configuration, entry-point mode and owner, architecture, and ELF interpreter, returning an exact runtime contract error.

## A Version or Deployment never becomes Ready

```bash
python3 scripts/al_mcp.py wait-version VERSION_ID --site-id SITE_ID
python3 scripts/al_mcp.py get-site-version-logs \
  --arg site_id=SITE_ID --arg version_id=VERSION_ID --arg stage=build --arg tail_lines=200
python3 scripts/al_mcp.py get-site-events --arg site_id=SITE_ID
python3 scripts/al_mcp.py deployment DEPLOYMENT_ID --site-id SITE_ID
```

`wait-version` uses cursor-based long polling. Even without state changes, it returns periodic heartbeats instead of leaving the Agent to wait blindly. On failure, use the owner-scoped `GetSiteVersionLogs`, which does not accept a caller-provided namespace, Pod, or container. Rely on the returned `phase`, stage, attempt, conditions, error code, and real URL. Do not substitute Pod readiness or a client HTTP timeout for product state.

When `build.errorClass=Transient` and the source is already immutable, inspect `build.diagnosticCode` and `build.retryAt`. Automatic retries wait for the persisted backoff gate. After the budget is exhausted, run this only with explicit user confirmation:

```bash
python3 scripts/al_mcp.py retry-version VERSION_ID --site-id SITE_ID --confirm --wait
```

Do not use build retry for `PolicyDenied`, `InvalidInput`, vulnerability scan, runtime contract, or preview failures. Do not amplify the same transient failure by creating multiple new Versions.
