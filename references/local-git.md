# Standalone local Git deployment

## Supported boundaries

Site MCP supports only these native source types:

- `source_bundle`: the public Gateway uploads a local directory and returns a platform OCI digest plus a short-lived receipt; this is independent of Sandbox.
- `sandbox_handoff`: explicitly consume the one-time SourceBundle export grant returned by `al-sandbox handoff`; Site MCP does not hold a long-lived Sandbox endpoint or token.
- `git`: the Site source importer fetches a fixed commit; this is independent of Sandbox.
- `oci`: validate and deploy a fixed image digest; this is independent of Sandbox.

`deploy-local-git` uses the Git path and is appropriate when a remote commit must be the authoritative audit record. For ordinary local development, use `deploy-local`; large files go through a separate binary upload endpoint rather than MCP JSON.

## Prerequisites

- Use a Git working tree.
- Leave no tracked or untracked changes.
- Point HEAD at a fixed commit on a named local branch.
- Ensure the corresponding remote branch ref exactly matches local HEAD.
- Ensure the Site build network can reach the repository.
- For a private repository, provide a short-lived credential supported by the importer through `--credential-env`.

## Commands

Save a version only:

```bash
python3 scripts/al_mcp.py save-local-git . --site-id SITE_ID
```

Save, wait for Ready, deploy, and wait for Ready:

```bash
python3 scripts/al_mcp.py deploy-local-git . --site-id SITE_ID
```

Supply build/runtime overrides:

```bash
python3 scripts/al_mcp.py deploy-local-git . \
  --site-id SITE_ID \
  --build '{"mode":"dockerfile","dockerfile":"Dockerfile","path_prefix_aware":true}' \
  --runtime '{"port":8080,"health_path":"/healthz"}'
```

`--build` and `--runtime` also accept `@file.json`.

## Why Git mode rejects a dirty working tree

Git mode declares that the remote commit is the input fact, so it must fail closed. Commit and push first, then publish the exact SHA. To publish current working tree contents, use `save-local`. It uploads through a separate streaming endpoint and produces the same kind of immutable OCI SourceBundle on the server without putting files into the 1 MiB MCP JSON payload.
