# AWS Cost Optimization Platform

The **AWS Cost Optimization Platform** is an automated, production-grade DevOps solution that identifies idle cloud resources and scales them down or stops them to reduce running costs. Built for AWS Lambda and Kubernetes environment workloads, it scans resources using CloudWatch metrics, enforces safety boundaries with tag-based opt-outs, and exports professional monthly savings reports (HTML and JSON) to S3 while firing alerts to an SNS notification topic.

## Architecture Diagram

```text
                  +-----------------------------------------+
                  |         Amazon CloudWatch Events        |
                  |          (Daily Cron at 2:00 UTC)       |
                  +--------------------+--------------------+
                                       |
                                       v
                  +--------------------+--------------------+
                  |             AWS Lambda Function         |
                  |          (python/lambda/handler.py)     |
                  +-----+--------------+--------------+-----+
                        |              |              |
         +--------------+              |              +-------------+
         |                             v                            |
         v                     +-------+-------+                    v
+--------+--------+            | Kubernetes    |           +--------+--------+
|   AWS SDK       |            | API / Client  |           | AWS S3 & SNS    |
|   (boto3)       |            +-------+-------+           | (Report/Alerts) |
+--------+--------+                    |                   +--------+--------+
         |                             |                            |
         | (Scan & Stop)               | (Scale down to 0)          | (Upload/Email)
         v                             v                            v
  +------+------+               +------+------+              +------+------+
  |  EC2 / RDS  |               | Deployments |              |  S3 reports |
  |  EBS / EIP  |               | in Cluster  |              |  SNS Alerts |
  +-------------+               +-------------+              +-------------+
```

## Key Features

1. **Idle Resource Detection**:
   * **EC2**: Average CPU utilization < 5% for 72 hours via CloudWatch.
   * **RDS**: Maximum database connection count = 0 for 48 hours.
   * **Kubernetes Deployments**: HPAs reporting 0 requests/traffic for 24 hours.
   * **Storage & Networking**: Unattached EBS volumes and unassociated Elastic IPs.
2. **Automated Remediations (Scale-Down)**:
   * Stop idle EC2 instances (with `CostOptimizerOptOut=true` tag override).
   * Create snapshot and stop idle RDS instances.
   * Scale Kubernetes deployment replicas to 0, annotating them with `cost-optimizer/original-replicas` for easy restoration.
3. **Savings Report and Notifications**:
   * Generate interactive HTML and JSON data reports.
   * Save reports to S3 with a date-based folder prefix (`reports/YYYY/MM/DD/`).
   * Deliver email summary/Slack integrations via an SNS topic.

## Dry-Run Mode

The platform runs in **Dry-Run** mode by default (`DRY_RUN=true`). In dry-run mode:
* Detectors run normally and calculate all potential monthly savings.
* Reports and notifications are generated and published, displaying a preview of actions.
* **No resources are modified or stopped.** No EC2 instances are stopped, no RDS instances are stopped, and no Kubernetes replicas are scaled down.
* Toggle the environment variable `DRY_RUN=false` in the Lambda config or CronJob to enable active automated remediation.

## Environment Variables

| Variable Name | Default Value | Description |
| :--- | :--- | :--- |
| `DRY_RUN` | `true` | When `true`, scans resources and outputs reports without stopping or scaling resources. |
| `S3_BUCKET_NAME` | *(Required)* | S3 Bucket name where generated HTML/JSON savings reports are uploaded. |
| `SNS_TOPIC_ARN` | *(Required)* | AWS SNS Topic ARN to publish the execution savings summary alerts. |
| `AWS_DEFAULT_REGION` | `us-east-1` | Target region for scanning and resources. |
| `EC2_CPU_THRESHOLD` | `5.0` | CPU utilization percentage threshold below which EC2 is flagged as idle. |
| `EC2_IDLE_HOURS` | `72` | The timeframe in hours to verify low CPU usage for EC2. |
| `RDS_CONNECTION_THRESHOLD` | `0` | Database connection count threshold below which RDS is flagged as idle. |
| `RDS_IDLE_HOURS` | `48` | The timeframe in hours to verify connection counts for RDS. |
| `K8S_REQUESTS_THRESHOLD` | `0` | Requests rate threshold below which deployment is flagged as idle. |
| `K8S_IDLE_HOURS` | `24` | The timeframe in hours to verify request counts for Kubernetes. |

## Local Setup & Development

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Copy `.env.example` to `.env` and fill in your AWS details.
```bash
cp .env.example .env
```

### 3. Run Tests
Verify detectors, reports, and actions with unit tests using mocked AWS services via `moto`:
```bash
pytest
```

## Infrastructure Deployment (Terraform)

Deploy the platform infrastructure (Lambda, IAM Roles, S3 Bucket, SNS Topic, CloudWatch schedule):
```bash
cd terraform
terraform init
terraform plan -var="s3_bucket_name=my-cost-reports-bucket"
terraform apply -var="s3_bucket_name=my-cost-reports-bucket" -auto-approve
```

## Kubernetes Deployment

Deploy the Kubernetes RBAC policies and CronJob to inspect and scale down workloads inside a cluster:
```bash
kubectl apply -f k8s/rbac.yaml
kubectl apply -f k8s/cronjob.yaml
```

## Example Savings Report Output (JSON)

When scanning executes, the JSON report is generated and saved under `s3://<bucket_name>/reports/YYYY/MM/DD/report_<date>.json`:

```json
{
  "generated_at": "2026-06-23T02:00:00Z",
  "dry_run": true,
  "total_estimated_monthly_savings": 105.20,
  "total_idle_resources_count": 3,
  "resources": [
    {
      "resource_id": "i-0abcd1234efgh5678",
      "resource_type": "EC2",
      "name": "staging-analytics-worker",
      "details": {
        "instance_type": "t3.medium",
        "launch_time": "2026-06-01T08:00:00Z",
        "state": "running"
      },
      "estimated_monthly_savings": 29.95,
      "opt_out_tag": false
    },
    {
      "resource_id": "production-reporting-db",
      "resource_type": "RDS",
      "name": "production-reporting-db",
      "details": {
        "engine": "postgres",
        "engine_version": "15.4",
        "db_instance_class": "db.t3.medium",
        "status": "available",
        "arn": "arn:aws:rds:us-east-1:123456789012:db:production-reporting-db"
      },
      "estimated_monthly_savings": 71.65,
      "opt_out_tag": false
    },
    {
      "resource_id": "vol-0123456789abcdef0",
      "resource_type": "EBS",
      "name": "temp-scratch-disk",
      "details": {
        "size_gb": 45,
        "volume_type": "gp3",
        "create_time": "2026-05-15T10:30:00Z"
      },
      "estimated_monthly_savings": 3.60,
      "opt_out_tag": false
    }
  ]
}
```
