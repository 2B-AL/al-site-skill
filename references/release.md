# Release workflow

## Contents

- Strategy selection
- Mandatory Plan flow
- Canary gates
- State and actions
- Rollback and migrations
- Waiting semantics

## Strategy selection

Use Immediate for a verified low-risk release that should move to 100% after platform checks. Use Blue-Green when a candidate must remain at 0% until browser or QA acceptance and explicit promotion. Use Canary when real traffic should advance through increasing percentages.

Examples:

```bash
python3 scripts/al_mcp.py release VERSION --immediate --wait
python3 scripts/al_mcp.py release VERSION --blue-green --wait-candidate
python3 scripts/al_mcp.py release VERSION --canary 5,25,100 --step-duration 5m --wait
```

Canary percentages must strictly increase and end at 100. `--step-duration` is the observation duration. `--step-timeout` bounds the whole gate window. `--manual-approval` pauses each step after its automated checks.

## Mandatory Plan flow

Every release follows:

```text
online tools/schema
  -> platform capabilities
  -> PlanSiteDeployment
  -> show normalized plan/findings
  -> DeploySiteVersion(plan_revision)
  -> GetSiteReleaseStatus
```

The plan is bound to the Site, Version, image digest, active Deployment, normalized strategy, platform readiness, and expiry. If it becomes stale, the client repeats the same visible intent once. It must not silently change the strategy.

Plan rejects an unready Version, a conflicting rollout, invalid lane matcher, unavailable required metric gate, unsafe migration rollback, invalid runtime or bindings, and scaling above platform limits.

## Canary gates

Available fixed product inputs are:

- `--min-requests`
- `--max-error-rate`
- `--max-error-rate-increase`
- `--max-p95-ms`
- `--max-p95-ratio`
- `--max-activation-errors`
- `--missing-data wait|fail|pass`

Candidate and stable are measured over the same window through the Site Observability Adapter. The Skill never submits PromQL. Default missing-data behavior is `wait`; VMP outage or insufficient samples preserves stable traffic.

## State and actions

Use `release-status DEPLOYMENT --watch`. Interpret structured fields only:

| State/code | Meaning | Safe next action |
| --- | --- | --- |
| CandidateCreating | Candidate is not ready | Wait; do not create another release |
| ManualApprovalRequired | Blue-Green or step approval | Validate lane, then promote or rollback |
| MetricSamplesInsufficient | Gate lacks traffic | Wait, generate intended traffic, or cancel |
| MetricGateFailed | Candidate crossed a threshold | Follow configured pause/rollback |
| ObservabilityUnavailable | VMP adapter is unavailable | Keep stable; repair observability |
| RollbackBlockedByMigration | DB compatibility was not declared | Review migration and application compatibility |
| ScalingQuotaExceeded | Candidate coexistence exceeds quota | Lower maxScale or finish another rollout |

`promote`, `pause`, `resume`, `cancel`, lane revoke, and rollback all fetch current preconditions before acting. Blue-Green uses `promote`, not `resume`.

Pause does not reset the current observation window. If `release-status` returns `PausedStepTimeoutElapsed`, choose either `resume DEPLOYMENT --extend-timeout 10m` (or another explicit bounded duration) or `rollback --confirm`; a plain resume is rejected.

## Rollback and migrations

`rollback HISTORICAL_DEPLOYMENT --confirm` first creates a read-only plan showing current/target snapshots, image/config/binding/runtime differences, historical Revision reuse, and migration warnings. It then creates a new immutable Deployment.

Rollback changes application traffic only. It never reverses a database migration or Add-on data. Automatic rollback is fail-closed when the Deployment contains a migration unless `application_backward_compatible=true`; unsafe automatic rollback becomes a pause.

## Waiting semantics

- `--wait-candidate` returns after candidate target, projection, and a real lane request are ready. It does not promote.
- `--wait` returns on Ready, Failed, Cancelled, or actionable Paused.
- Paused prints machine-readable status and exits with code 3.
- Network interruption resumes by Deployment ID; never create a replacement release merely because a watch disconnected.
