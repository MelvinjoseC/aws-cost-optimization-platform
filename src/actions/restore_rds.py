import os
from datetime import datetime, timezone
from typing import Dict, List, Union
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client, get_target_regions
from src.utils.logger import get_logger

logger = get_logger(__name__)


def find_stopped_optimizer_rds(regions: List[str] = None) -> List[Dict]:
    """
    Discovers stopped RDS DB instances tagged with CostOptimizer=true
    across target AWS regions.
    """
    target_regions = regions or get_target_regions()
    candidates: List[Dict] = []

    for region in target_regions:
        rds_client = get_aws_client("rds", region_name=region)
        try:
            paginator = rds_client.get_paginator("describe_db_instances")
            for page in paginator.paginate():
                for db in page.get("DBInstances", []):
                    db_id = db.get("DBInstanceIdentifier")
                    status = db.get("DBInstanceStatus")
                    arn = db.get("DBInstanceArn")
                    tags = db.get("TagList", [])
                    tag_map = {t["Key"]: t["Value"] for t in tags}

                    is_opt = tag_map.get("CostOptimizer") == "true"
                    if status == "stopped" and is_opt:
                        candidates.append({
                            "resource_id": db_id,
                            "details": {
                                "region": region,
                                "arn": arn,
                                "engine": db.get("Engine"),
                            },
                        })
        except ClientError as e:
            logger.error(
                f"[{region}] Failed to query stopped RDS instances: {e}"
            )
    return candidates


def restore_rds_instances(
    rds_resources: List[Union[str, dict]] = None
) -> List[str]:
    """
    Starts stopped RDS DB instances previously stopped by CostOptimizer.
    Accepts DB instance identifiers or resource dicts.
    If no instances are passed, automatically discovers candidates.
    Updates tags: CostOptimizer=restored.
    Returns list of successfully restarted DB instance identifiers.
    """
    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"
    default_region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    restarted_dbs: List[str] = []

    if rds_resources is None:
        target_list = find_stopped_optimizer_rds()
    else:
        target_list = rds_resources

    if not target_list:
        logger.info("No stopped RDS DB instances found for restoration.")
        return []

    timestamp = datetime.now(timezone.utc).isoformat()
    restore_tags = [
        {"Key": "CostOptimizer", "Value": "restored"},
        {"Key": "CostOptimizerRestoredTimestamp", "Value": timestamp},
    ]

    for item in target_list:
        if isinstance(item, dict):
            db_id = item.get("resource_id")
            region = item.get("details", {}).get("region", default_region)
            arn = item.get("details", {}).get("arn")
        else:
            db_id = str(item)
            region = default_region
            arn = None

        if not db_id:
            continue

        if dry_run:
            logger.info(
                f"[DRY RUN] Would start stopped RDS DB '{db_id}' in '{region}'"
            )
            restarted_dbs.append(db_id)
            continue

        logger.info(f"Starting RDS DB '{db_id}' in region '{region}'...")
        rds_client = get_aws_client("rds", region_name=region)

        try:
            rds_client.start_db_instance(DBInstanceIdentifier=db_id)
            restarted_dbs.append(db_id)
            logger.info(f"[{region}] Successfully started RDS DB '{db_id}'")

            if arn:
                try:
                    rds_client.add_tags_to_resource(
                        ResourceName=arn, Tags=restore_tags
                    )
                except ClientError as tag_err:
                    logger.warning(
                        f"[{region}] Tag update failed for {db_id}: {tag_err}"
                    )
        except ClientError as e:
            logger.error(
                f"[{region}] Error starting RDS DB '{db_id}': {e}"
            )

    return restarted_dbs
