# FinOps Foundation Framework Alignment

The **AWS Cost Optimization Platform** adheres to the core principles and phases established by the **FinOps Foundation**:

```text
       +-------------------------------------------------------+
       |               FinOps Lifecycle Phases                 |
       +-------------------------------------------------------+
       |                                                       |
       |    [ 1. INFORM ] ---------> [ 2. OPTIMIZE ]           |
       |          ^                           |                |
       |          |                           v                |
       |          +------------------- [ 3. OPERATE ]          |
       +-------------------------------------------------------+
```

---

## Phase 1: Inform (Visibility & Allocation)
* **Near Real-time Discovery**: Audits idle EC2, RDS, EBS, EIP, ELB, NAT Gateways, ElastiCache, DynamoDB, EFS, and CloudWatch log groups across target regions.
* **Tag Governance & Attribution**: Extracts environment tags (`env`, `Environment`), workload owners, and opt-out statuses.
* **Observability & Dashboards**:
  - Emits CloudWatch custom metrics under `CostOptimization/Metrics`.
  - Provisions real-time CloudWatch Executive Dashboard via Terraform.
  - Generates executive HTML dashboards and structured JSON/CSV reports archived to Amazon S3.
* **Automated Notifications**: Delivers summary alerts to team channels via Amazon SNS and Slack Block Kit.

---

## Phase 2: Optimize (Usage & Rate Reduction)
* **Rightsizing Recommendations**:
  - EC2: Analyzes 7-day peak CPU utilization and recommends downsized instance families (e.g., `m5.2xlarge` -> `m5.large`).
  - Kubernetes: Evaluates pod CPU/Memory requests against baseline requirements to eliminate resource reservation waste.
* **Storage Optimization**:
  - Unattached EBS cleanup.
  - Stale snapshot discovery (snapshots older than 30 days without parent volumes).
  - Amazon EFS lifecycle policy enforcement (transitioning unaccessed files to Infrequent Access tier).
  - CloudWatch Log retention policy enforcement (capping indefinite retention to 90 days).
* **Throughput Optimization**:
  - Detects provisioned DynamoDB tables with zero read/write consumed units and converts them to On-Demand (PAY_PER_REQUEST) billing.

---

## Phase 3: Operate (Continuous Automated Operations)
* **Bidirectional Nightly & Morning Automation**:
  - **Nightly Stop**: EventBridge triggers automated shutdowns of non-production idle EC2 and RDS instances at 02:00 UTC.
  - **Morning Restore**: Built-in restoration schedule starts stopped instances at 07:00 UTC before business hours.
  - **Kubernetes Scaling**: Scales idle development deployments down to 0 replicas with annotations preserving original replica counts.
* **Safety Guardrails**:
  - **Protected Environments**: Automatically excludes `prod`, `production`, `live`, and `critical` environments unless explicitly allowed via `ALLOW_PRODUCTION_REMEDIATION=true`.
  - **Tag-based Opt-Out**: Respects `CostOptimizerOptOut=true`, `DoNotStop=true`, and `Protected=true`.
  - **Dry-Run by Default**: Simulation mode enabled out of the box (`DRY_RUN=true`).
