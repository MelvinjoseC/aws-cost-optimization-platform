from typing import Dict, List
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client
from src.utils.config import get_config
from src.utils.governance import filter_actionable_resources
from src.utils.logger import get_logger

logger = get_logger(__name__)


def enforce_cloudwatch_log_retention(
    resources: List[Dict], default_retention_days: int = 90
) -> List[str]:
    """
    Enforces retention policies on CloudWatch log groups with infinite (Never Expire) retention.
    Updates retention period to default_retention_days (e.g. 90 days) to curb unbounded storage costs.
    """
    if not resources:
        logger.info("No CloudWatch log groups provided for remediation.")
        return []

    cfg = get_config(reload=True)
    target_retention = cfg.cloudwatch_log_retention_days or default_retention_days
    actionable, protected = filter_actionable_resources(resources)

    if protected:
        logger.info(
            f"Skipped {len(protected)} log groups due to governance protection."
        )

    if not actionable:
        logger.info("No actionable CloudWatch log groups to remediate.")
        return []

    remediated = []

    for res in actionable:
        log_group_name = res.get("resource_id")
        region = res.get("details", {}).get("region", "us-east-1")
        logs_client = get_aws_client("logs", region_name=region)

        if cfg.dry_run:
            logger.info(
                f"[DRY RUN] Would set {target_retention}-day retention policy on "
                f"CloudWatch log group '{log_group_name}' in {region}."
            )
            remediated.append(log_group_name)
            continue

        try:
            logger.info(
                f"Applying {target_retention}-day retention policy on '{log_group_name}'..."
            )
            logs_client.put_retention_policy(
                logGroupName=log_group_name,
                retentionInDays=target_retention,
            )
            remediated.append(log_group_name)
            logger.info(
                f"Successfully updated retention on log group '{log_group_name}'."
            )
        except ClientError as e:
            logger.error(
                f"Failed setting retention policy on '{log_group_name}': {e}"
            )

    return remediated
