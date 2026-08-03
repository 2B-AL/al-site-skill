# Standalone local SourceBundle deployment

## Data path

```text
local directory
  -> al-site preflight + deterministic tar.gz
  -> Site MCP JSON control: create multipart session
  -> direct exact-part PUT to short-lived TOS presigned URLs
  -> Site MCP JSON control: status / refresh / complete / abort
  -> Site Manager safe extract + canonicalize + secret scan
  -> platform-owned OCI source@sha256:...
  -> SaveSiteVersion(source_bundle + short-lived receipt)
  -> build -> scan -> preview -> deploy
```

Local files do not pass through MCP/APIG and do not enter CRDs, Secrets, or skill state files. MCP forwards only control JSON no larger than 1 MiB. Each part is uploaded directly through an exact, short-lived TOS URL restricted to its object, upload, and part. Requests to TOS do not include Site OAuth, conversation, or trusted identity headers.

Resume state is stored in `~/.al-site-mcp/uploads/<archive-sha256>.json` with mode `0600`. It contains only a caller-bound session token and completed-part ETags, never presigned URLs. A retry reconciles local state with the parts already uploaded to TOS and refreshes URLs only for missing parts. The final receipt is bound to the current user/org/service caller and is passed to `SaveSiteVersion` only within the same process.

## Commands

Upload and save a version only:

```bash
python3 scripts/al_mcp.py save-local . --site-id SITE_ID
```

Save, wait for the Version to become Ready, deploy, and wait for the Deployment to become Ready:

```bash
python3 scripts/al_mcp.py deploy-local . --site-id SITE_ID
```

Override build and runtime configuration:

```bash
python3 scripts/al_mcp.py deploy-local . \
  --site-id SITE_ID \
  --build '{"mode":"dockerfile","dockerfile":"Dockerfile","path_prefix_aware":true}' \
  --runtime '{"port":8080,"health_path":"/healthz"}'
```

Always interpret `build.dockerfile` relative to `build.context`. For a project containing `app/Dockerfile`, use:

```json
{"mode":"dockerfile","context":"app","dockerfile":"Dockerfile","path_prefix_aware":true}
```

Do not combine `context=app` with `dockerfile=app/Dockerfile`; the resolved path would become `app/app/Dockerfile`. The local command verifies that the resolved Dockerfile exists before uploading.

Site workloads enforce `runAsNonRoot`. If the final Dockerfile stage explicitly sets a user, use a numeric UID/GID:

```dockerfile
USER 65532:65532
```

Do not use a named user such as `USER nonroot:nonroot`; kubelet does not read `/etc/passwd` from the image before startup to prove that the user is non-root. The local command rejects an explicit named user or UID 0 early. If the final stage omits `USER` or uses a variable, the client cannot prove the base image's final OCI user, so the caller must still ensure it is a numeric non-root UID.

## Publication boundaries

- Use `.alignore` to exclude dependency caches, test artifacts, and large local files.
- Never upload platform-denied paths such as `.git`, `.env`, `.ssh`, `.aws`, `.kube`, `.docker/config.json`, `.npmrc`, or `.pypirc`.
- Reject high-confidence private keys, AWS keys, GitHub tokens, and Slack tokens on both the client and the server.
- Keep symlinks inside the source directory. Reject sockets, devices, FIFOs, hardlink archives, and other special types.
- Use client preflight to stop sensitive files from leaving the machine early. Treat server normalization and scanning as the authoritative security boundary.
- Preflight the Dockerfile relative path and any determinable final-stage user on the client. Apply the same checks before `SaveSiteVersion` for Sandbox exports and pure remote Git sources.
- Use TOS only for short-lived transfer staging, never as the Site artifact store. After completion, the sole persistent input is the platform OCI SourceBundle digest.
- Produce the same content-addressed OCI digest on the server for identical content. Store only the digest reference, not the archive, in SiteVersion.

## Relationship to other sources

Local, Sandbox export, and Git sources converge on the same OCI SourceBundle. The later build, scan, preview, and deploy flow does not branch. OCI image source is the only explicit path that skips the source build.
