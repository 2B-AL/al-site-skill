# Scaling

## Contents

- Defaults versus current production
- Profiles and custom policies
- Status and metrics
- Release interaction

## Defaults versus current production

`scaling-set-defaults` patches the mutable Site defaults and affects only future Version/Deployment fields that do not override them.

`scaling-apply` takes the current active immutable Version and runtime snapshot, applies the requested policy, calls `PlanSiteScaling`, and creates a new Immediate SiteDeployment. It is the command for changing current production.

```bash
python3 scripts/al_mcp.py scaling-set-defaults --profile balanced
python3 scripts/al_mcp.py scaling-apply --profile latency --wait
```

## Profiles and custom policies

Online capabilities are the source of truth for profile values and `maxScalePerSite`. Do not hardcode profile numbers when deciding safety.

Custom requires all three:

```bash
python3 scripts/al_mcp.py scaling-apply --profile custom \
  --min-scale 1 --max-scale 20 --target-concurrency 20 --wait
```

Optional custom fields are `--initial-scale` and `--scale-down-delay-seconds`. `min-scale=0` enables scale-to-zero when the environment reports support.

## Status and metrics

```bash
python3 scripts/al_mcp.py scaling-status
```

The response distinguishes `configured` from `available`. When available it includes the active profile/policy and bounded VMP/Knative values such as desired/current/ready replicas, concurrency, queue depth, scale events, cold-start latency, activation errors, scale-to-zero, and quota headroom. Missing backend data must be shown as unavailable, not fabricated as zero.

## Release interaction

Candidate scaling is fixed in that Deployment's runtime snapshot. Plan must account for stable and candidate worst-case coexistence. A rollback restores the historical Deployment scaling snapshot. A 0% Blue-Green candidate may scale from zero when a signed lane request arrives.

