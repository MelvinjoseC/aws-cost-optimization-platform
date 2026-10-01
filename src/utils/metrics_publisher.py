import os
from typing import Dict, List
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client
from src.utils.logger import get_logger

logger = get_logger(__name__)

METRICS_NAMESPACE = "CostOptimization/Metrics"


def publish_finops_metrics(
    detected_resources: List[Dict],
    remediated_counts: Dict[str, int],
    total_savings: float,
    dry_run: bool,
) -> bool:
    """
    Publishes FinOps metrics to CloudWatch for dashboarding and alerting.
    Dimensions include Environment and DryRun mode.
    """
    enabled = os.environ.get("ENABLE_CLOUDWATCH_METRICS", "true").lower()
    if enabled != "true":
        logger.info("CloudWatch metrics publishing is disabled.")
        return False

    env = os.environ.get("ENVIRONMENT", "production")
    mode_str = "DryRun" if dry_run else "Active"
    cw_client = get_aws_client("cloudwatch")

    metric_data = [
        {
            "MetricName": "EstimatedMonthlySavings",
            "Dimensions": [
                {"Name": "Environment", "Value": env},
                {"Name": "ExecutionMode", "Value": mode_str},
            ],
            "Value": float(total_savings),
            "Unit": "None",
        },
        {
            "MetricName": "IdleResourcesDetected",
            "Dimensions": [
                {"Name": "Environment", "Value": env},
                {"Name": "ExecutionMode", "Value": mode_str},
            ],
            "Value": float(len(detected_resources)),
            "Unit": "Count",
        },
        {
            "MetricName": "RemediatedResourcesCount",
            "Dimensions": [
                {"Name": "Environment", "Value": env},
                {"Name": "ExecutionMode", "Value": mode_str},
            ],
            "Value": float(sum(remediated_counts.values())),
            "Unit": "Count",
        },
    ]

    # Category-level breakdown metrics
    type_savings: Dict[str, float] = {}
    for res in detected_resources:
        rtype = res.get("resource_type", "Unknown")
        savings = res.get("estimated_monthly_savings", 0.0)
        type_savings[rtype] = type_savings.get(rtype, 0.0) + savings

    for rtype, savings_val in type_savings.items():
        metric_data.append({
            "MetricName": "SavingsByCategory",
            "Dimensions": [
                {"Name": "Environment", "Value": env},
                {"Name": "ResourceType", "Value": rtype},
            ],
            "Value": float(round(savings_val, 2)),
            "Unit": "None",
        })

    # CloudWatch allows max 20 metric data points per call
    batch_size = 20
    try:
        for i in range(0, len(metric_data), batch_size):
            batch = metric_data[i: i + batch_size]
            cw_client.put_metric_data(
                Namespace=METRICS_NAMESPACE, MetricData=batch
            )
        logger.info(
            f"Successfully published {len(metric_data)} FinOps metric points."
        )
        return True
    except ClientError as e:
        logger.error(f"Failed to publish CloudWatch metrics: {e}")
        return False
