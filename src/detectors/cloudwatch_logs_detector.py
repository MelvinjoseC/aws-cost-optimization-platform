from datetime import datetime, timezone
from typing import Dict, List, Optional
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client, get_target_regions
from src.utils.config import get_config
from src.utils.logger import get_logger
from src.utils.pricing import calculate_cloudwatch_log_storage_cost

logger = get_logger(__name__)


def get_log_group_tags(logs_client, log_group_name: str) -> Dict[str, str]:
    """Retrieves tags for a CloudWatch log group."""
    try:
        response = logs_client.list_tags_for_resource(
            resourceArn=log_group_name
        ) if hasattr(logs_client, "list_tags_for_resource") else {}
        return response.get("tags", {})
    except Exception:
        return {}


def detect_unexpired_or_abandoned_log_groups() -> List[Dict]:
    """
    Scans for CloudWatch log groups with infinite retention (Never Expire)
    or abandoned log groups with stale ingestion.
    """
    logger.info("Starting CloudWatch Log Groups cost optimization detection...")
    cfg = get_config(reload=True)
    target_regions = get_target_regions()
    detected_logs = []
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    thirty_days_ms = 30 * 86400 * 1000

    for region in target_regions:
        logger.info(f"Scanning CloudWatch log groups in region: {region}")
        logs_client = get_aws_client("logs", region_name=region)

        try:
            paginator = logs_client.get_paginator("describe_log_groups")
            for page in paginator.paginate():
                for lg in page.get("logGroups", []):
                    name = lg.get("logGroupName", "")
                    stored_bytes = lg.get("storedBytes", 0)
                    retention = lg.get("retentionInDays")
                    last_ingestion = lg.get("lastIngestionTime", 0)
                    size_gb = round(stored_bytes / (1024**3), 3)

                    # Skip empty log groups
                    if stored_bytes == 0:
                        continue

                    # Case 1: Infinite retention (Never Expire)
                    if retention is None:
                        monthly_savings = calculate_cloudwatch_log_storage_cost(size_gb)
                        # Minimal threshold: $0.50/mo or > 1GB
                        if size_gb >= 0.5 or monthly_savings >= 0.10:
                            logger.info(
                                f"[{region}] Detected Unexpired Log Group: {name}, "
                                f"Size={size_gb}GB, Retention=None, Savings=${monthly_savings}/mo"
                            )
                            detected_logs.append(
                                {
                                    "resource_id": name,
                                    "resource_type": "CloudWatchLogs",
                                    "name": name,
                                    "details": {
                                        "region": region,
                                        "size_gb": size_gb,
                                        "retention_days": None,
                                        "issue": "Infinite retention period configured (Never Expire)",
                                    },
                                    "tags": {},
                                    "estimated_monthly_savings": monthly_savings,
                                }
                            )
                            continue

                    # Case 2: Abandoned log groups (no ingestion for 30+ days)
                    if last_ingestion and (now_ms - last_ingestion > thirty_days_ms):
                        monthly_cost = calculate_cloudwatch_log_storage_cost(size_gb)
                        if monthly_cost >= 0.10:
                            logger.info(
                                f"[{region}] Detected Abandoned Log Group: {name}, "
                                f"Size={size_gb}GB, Last Ingestion > 30d, Cost=${monthly_cost}/mo"
                            )
                            detected_logs.append(
                                {
                                    "resource_id": name,
                                    "resource_type": "CloudWatchLogs",
                                    "name": name,
                                    "details": {
                                        "region": region,
                                        "size_gb": size_gb,
                                        "retention_days": retention,
                                        "issue": "Abandoned log group with zero ingestion in past 30 days",
                                    },
                                    "tags": {},
                                    "estimated_monthly_savings": monthly_cost,
                                }
                            )

        except ClientError as e:
            logger.error(f"Failed scanning CloudWatch log groups in region {region}: {e}")

    logger.info(
        f"Completed CloudWatch logs detection. Found {len(detected_logs)} optimization candidates."
    )
    return detected_logs
