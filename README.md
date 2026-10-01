# AWS Cost Optimization & FinOps Platform

The **AWS Cost Optimization Platform** is an enterprise-grade, bidirectional FinOps automation solution engineered for cloud infrastructure and Kubernetes workloads. It continuously audits multi-region AWS environments for underutilized, orphaned, and oversized resources, executes safe automated remediations with tag-based governance guardrails, supports scheduled weekday morning restorations, and delivers executive dashboards, S3 reports (HTML/JSON/CSV), SNS alerts, and Slack notifications.

---

## 🏛 Architecture Diagram

```text
                  +-----------------------------------------------+
                  |         Amazon EventBridge Schedules          |
                  |  - Nightly Optimize (Daily at 02:00 UTC)      |
                  |  - Morning Restore  (Mon-Fri at 07:00 UTC)    |
                  +-----------------------+-----------------------+
                                          |
                                          v
                  +-----------------------+-----------------------+
                  |              AWS Lambda Function              |
                  |      (lambda/handler.py | Dual Mode)          |
                  +---+---------------+---------------+-------+---+
                      |               |               |       |
      +---------------+               |               |       +---------------+
      |                               |               |                       |
      v                               v               v                       v
+-----+-------+                 +-----+-------+ +-----+-------+         +-----+-------+
|  Detectors  |                 |  Governance | | Remediations|         |Observability|
| (Multi-Reg) |                 |  Guardrails | | & Restores  |         | & Reporting |
+-----+-------+                 +-----+-------+ +-----+-------+         +-----+-------+
      |                               |               |                       |
      |-- EC2 Idle / Rightsizing      |-- Protected   |-- EC2 Stop / Start    |-- CloudWatch
      |-- RDS DB Idle                 |   Environments|-- RDS Stop / Start    |   Custom Metrics
      |-- Unattached EBS Volumes      |   (prod/live) |-- K8s Scale Down/Up   |-- FinOps
      |-- Unassociated Elastic IPs    |-- Tag Checks  |-- EBS Delete          |   Dashboard
      |-- Idle Classic & App ELBs     |   (OptOut/    |-- EIP Release         |-- S3 Reports
      |-- Stale EBS Snapshots         |    DoNotStop) |                       |   (HTML/JSON/CSV)
      |-- Idle NAT Gateways           |               |                       |-- Slack & SNS
      |-- Idle ElastiCache Nodes      |               |                       |   Alerts
      |-- K8s Deployments / Pods      |               |                       |
```

---

## 🚀 Key Capabilities

### 1. Multi-Service Resource Detection
* **EC2 Instances**: Identifies instances with average CPU < 5% over 72 hours.
* **EC2 Rightsizing**: Flags overprovisioned instances whose 7-day peak CPU remains below 20%, proposing downsized instance tiers.
* **RDS Databases**: Flags DB instances with 0 connections over 48 hours.
* **Unattached EBS Volumes**: Discovers volumes in `available` (unattached) status.
* **Stale EBS Snapshots**: Identifies orphaned snapshots older than 30 days whose parent volume no longer exists.
* **Unassociated Elastic IPs**: Finds unattached public IPv4 addresses incurring hourly idle charges.
* **Idle NAT Gateways**: Identifies VPC NAT Gateways with 0 active connections over 7 days (~$32.40/mo per gateway).
* **Idle ElastiCache**: Scans Redis and Memcached clusters with 0 client connections over 72 hours.
* **Idle Load Balancers**: Flags ALBs and Classic ELBs with 0 requests over 7 days.
* **Kubernetes Workloads**: Detects idle deployments via HPA metrics and flags pods with disproportionate CPU/Memory requests.

### 2. Bidirectional Remediation & Restoration
* **Stateful Stopping**: Stops idle EC2 instances and creates a timestamped safety snapshot before stopping RDS DBs.
* **Kubernetes Scale-to-Zero**: Saves original replica counts to annotation `cost-optimizer/original-replicas` before scaling down.
* **Automated Morning Restoration**: Built-in `restore` mode automatically restarts stopped instances and scales deployments back up before working hours.

### 3. Enterprise Governance & Safety Guardrails
* **Protected Environments**: Automatically shields resources in `production`, `prod`, `live`, or `critical` environments unless explicitly overridden by `ALLOW_PRODUCTION_REMEDIATION=true`.
* **Tag Opt-Out**: Respects tags `CostOptimizerOptOut=true`, `DoNotStop=true`, and `Protected=true`.
* **Dry-Run by Default**: Runs in simulation mode (`DRY_RUN=true`) out of the box to prevent accidental downtime.

### 4. Observability & Reporting
* **Executive Reports**: Generates interactive HTML dashboards, structured JSON, and CSV exports uploaded to S3.
* **CloudWatch Custom Metrics**: Emits `EstimatedMonthlySavings`, `IdleResourcesDetected`, and `SavingsByCategory` under namespace `CostOptimization/Metrics`.
* **CloudWatch FinOps Dashboard**: Built-in Terraform module provisioning real-time savings graphs.
* **Multi-Channel Notifications**: Real-time alerts via Amazon SNS and rich interactive Slack Block Kit webhooks.

---

## 💻 CLI Usage

The platform includes a first-class CLI (`cli.py`) for local audits, CI/CD pipelines, and scheduled cron jobs.

```bash
# Audit idle resources across multiple regions (Dry-Run preview)
python cli.py --action scan --regions us-east-1,us-west-2

# Perform active remediation (stop/delete non-production resources)
python cli.py --action remediate --no-dry-run --regions us-east-1

# Restore all previously stopped EC2, RDS, and Kubernetes workloads
python cli.py --action restore
```

---

## ⚙️ Configuration Reference

| Environment Variable | Default | Purpose |
| :--- | :--- | :--- |
| `DRY_RUN` | `true` | When true, previews all savings without modifying infrastructure |
| `ALLOW_PRODUCTION_REMEDIATION` | `false` | Safety barrier preventing automated stop/deletion in prod environments |
| `PROTECTED_ENVIRONMENTS` | `prod,production,live` | Comma-separated list of protected environment tag values |
| `AWS_REGIONS` | `us-east-1` | Comma-separated list of target AWS regions to audit |
| `DELETE_UNUSED_EBS` | `false` | Actively deletes unattached EBS volumes when DRY_RUN=false |
| `RELEASE_UNUSED_EIP` | `false` | Actively releases unassociated Elastic IPs when DRY_RUN=false |
| `SNAPSHOT_MAX_AGE_DAYS` | `30` | Minimum age (days) before orphaned EBS snapshots are flagged |
| `NAT_GW_IDLE_HOURS` | `168` | Window in hours to verify 0 connections for NAT Gateways |
| `ELASTICACHE_IDLE_HOURS` | `72` | Window in hours to verify 0 connections for ElastiCache |
| `EC2_CPU_THRESHOLD` | `5.0` | Maximum average CPU % to flag an EC2 instance as idle |
| `S3_BUCKET_NAME` | *(Optional)* | S3 bucket destination for HTML/JSON/CSV reports |
| `SNS_TOPIC_ARN` | *(Optional)* | AWS SNS topic for alert notifications |
| `SLACK_WEBHOOK_URL` | *(Optional)* | Incoming Slack Webhook URL for rich Block Kit alerts |
| `LOG_FORMAT` | `text` | Set to `json` for structured CloudWatch Logs Insights ingestion |

---

## 🏗 Infrastructure Deployment

### 1. Terraform Deployment

Deploy the serverless Lambda function, IAM roles, KMS encryption, CloudWatch FinOps dashboard, and EventBridge schedules:

```bash
cd terraform
terraform init
terraform plan -var="s3_bucket_name=my-company-finops-reports"
terraform apply -var="s3_bucket_name=my-company-finops-reports" -auto-approve
```

### 2. Kubernetes Helm Deployment

Deploy the Kubernetes CronJob and RBAC permissions using Helm:

```bash
helm install aws-cost-optimizer ./helm/aws-cost-optimizer \
  --namespace finops \
  --create-namespace \
  --set config.dryRun="true" \
  --set config.s3BucketName="my-company-finops-reports"
```

---

## 🧪 Testing & Verification

Run the full automated test suite with unit tests and mocks:

```bash
# Run all unit tests
python -m pytest

# Run flake8 lint check
python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
```
