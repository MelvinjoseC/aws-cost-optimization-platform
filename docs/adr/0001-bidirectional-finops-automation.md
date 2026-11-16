# ADR 0001: Bidirectional FinOps Automation Architecture

## Status
Accepted

## Context
Cloud infrastructure costs frequently suffer from non-production resources left running outside business hours (nights, weekends, holidays). In a typical engineering organization, non-production environments (dev, test, staging) are actively utilized during roughly 50 hours of a 168-hour week (~30% utilization). 

Previous automated cost solutions suffered from two severe flaws:
1. **Destructive Termination**: Irreversibly terminating instances or resources destroyed developers' debugging state and transient data.
2. **One-Way Stops**: Stopping instances without an automated restoration mechanism created friction, leading engineers to disable the automation via opt-out tags.

## Decision
We architected a **bidirectional, non-destructive lifecycle automation**:
1. **Stateful Nightly Stop (02:00 UTC)**:
   - Stops idle non-production EC2 instances and tags them with `CostOptimizer=true` and an audit timestamp.
   - Creates a point-in-time snapshot before stopping RDS instances.
   - Scales Kubernetes deployments to 0 replicas while saving original counts to annotation `cost-optimizer/original-replicas`.
2. **Automated Morning Restore (07:00 UTC, Mon-Fri)**:
   - Queries resources tagged with `CostOptimizer=true` and starts them automatically before working hours.
   - Reads the Kubernetes replica annotation and restores deployments to their exact previous state.
3. **Enterprise Governance Guardrails**:
   - Production workloads are strictly shielded by default.
   - Individual resource opt-out is supported via `CostOptimizerOptOut=true`.

## Consequences
- **Positive**:
  - Achieves 65-70% reduction in non-production compute and database costs.
  - Frictionless developer experience: dev environments are ready every morning.
  - Zero accidental production outages due to hardcoded guardrails.
- **Negative**:
  - Minor storage costs remain while EBS volumes and RDS storage are detached/stopped.
  - Requires EventBridge cron schedules and IAM permissions for both stop and start actions.
