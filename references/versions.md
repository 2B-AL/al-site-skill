# Immutable versions and deployment history

## Contents

- Version lifecycle
- History and comparison
- Deletion protection
- Rollback target selection

## Version lifecycle

A SiteVersion pins source identity, normalized build plan, runtime defaults, image digest, scan result, and private preview result. Saving never changes production traffic.

```bash
python3 scripts/al_mcp.py versions
python3 scripts/al_mcp.py version VERSION_ID
python3 scripts/al_mcp.py wait-version VERSION_ID
```

Wait for real `phase=Ready`; do not treat SourceBundle upload or image build completion alone as deployable.

For a terminal transient build failure after `SourceResolved=True`, retry the
same immutable SourceBundle without creating another Version:

```bash
python3 scripts/al_mcp.py retry-version VERSION_ID --confirm --wait
```

The command refreshes UID and resourceVersion before calling the protected
retry tool. The platform persists an exponential `retryAt` gate for automatic
attempts and exposes a non-sensitive `diagnosticCode`, such as
`buildkit.base-image.request-timeout`. A manual retry starts a new bounded
build-only attempt window; it never replays Git or Sandbox source import.

Do not use it for policy, vulnerability, runtime-contract, or preview failures.
Versions that used ephemeral BuildKit secrets must be saved again with fresh
secret material because the original values are deliberately destroyed.

## History and comparison

```bash
python3 scripts/al_mcp.py version-diff VERSION_A VERSION_B

# Permanently remove one unreferenced Version. The command first refreshes
# UID/resourceVersion and the platform still rejects active/history references.
python3 scripts/al_mcp.py delete-version VERSION_ID --confirm
python3 scripts/al_mcp.py deployments
python3 scripts/al_mcp.py deployment DEPLOYMENT_ID
```

Version comparison is read-only and bounded. Deployment history is the source for image/config/binding/runtime/scaling snapshots and rollback targets.

The strong `version`, `versions`, and `version-diff` commands show immutable
source/build/runtime contracts and material artifact differences. Controller
bookkeeping such as managedFields, Job names, condition timestamps, and preview
object references is deliberately omitted so it cannot masquerade as a version
change. Use a generic MCP tool command only when raw debugging data is explicitly
required.

## Deletion protection

`delete-version` fetches the latest UID and resourceVersion itself and sends both as atomic preconditions. The manager remains authoritative for the `VersionInUse` check; the Skill never guesses from a stale list result. Site deletion is separate and permanent. `archive` only clears conversation selection.

## Rollback target selection

Choose a historical Deployment, not merely a Version, because rollback restores the complete release snapshot. Run `rollback DEPLOYMENT --confirm`; review its plan differences and database warning before traffic changes.
