import os
from datetime import datetime, timezone
from typing import Dict, List
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client
from src.utils.logger import get_logger

logger = get_logger(__name__)


def stop_rds_instances(rds_resources: List[Dict]) -> List[str]:
    """
    Snapshots and stops a list of idle RDS DB instances across regions.
    Adds tracking tags: CostOptimizer=true and CostOptimizerStopTimestamp.
    Creates a snapshot before stopping: snapshot-<db-id>-<timestamp>.
    Respects DRY_RUN environment variable.
    Returns a list of successfully stopped DB instance identifiers.
    """
    if not rds_resources:
        logger.info("No RDS DB instances to stop.")
        return []

    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"
    default_region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    stopped_dbs: List[str] = []

    timestamp_raw = datetime.now(timezone.utc)
    snapshot_suffix = timestamp_raw.strftime("%Y-%m-%d-%H-%M-%S")
    timestamp_iso = timestamp_raw.isoformat()

    tags = [
        {"Key": "CostOptimizer", "Value": "true"},
        {"Key": "CostOptimizerStopTimestamp", "Value": timestamp_iso},
    ]

    for rds in rds_resources:
        db_id = rds.get("resource_id")
        if not db_id:
            continue

        region = rds.get("details", {}).get("region", default_region)
        arn = rds.get("details", {}).get("arn")
        rds_client = get_aws_client("rds", region_name=region)

        # Max length of RDS snapshot identifier is 255 characters
        snapshot_id = f"snapshot-{db_id}-{snapshot_suffix}"[:255]

        if dry_run:
            logger.info(
                f"[DRY RUN] Would snapshot & stop RDS '{db_id}' in "
                f"'{region}'. Snapshot: '{snapshot_id}'"
            )
            stopped_dbs.append(db_id)
            continue

        logger.info(
            f"Stopping RDS '{db_id}' in {region}. Snapshot: {snapshot_id}"
        )

        # 1. Apply tags to the RDS instance
        if arn:
            try:
                rds_client.add_tags_to_resource(ResourceName=arn, Tags=tags)
                logger.info(f"[{region}] Applied tags to RDS instance {db_id}")
            except ClientError as e:
                logger.error(
                    f"[{region}] Failed to apply tags to RDS {db_id}: {e}"
                )
        else:
            logger.warning(
                f"[{region}] No ARN for RDS {db_id}. Skipping tagging."
            )

        # 2. Stop instance with snapshot
        try:
            rds_client.stop_db_instance(
                DBInstanceIdentifier=db_id, DBSnapshotIdentifier=snapshot_id
            )
            stopped_dbs.append(db_id)
            logger.info(f"[{region}] Successfully stopped RDS DB: {db_id}")
        except ClientError as e:
            logger.error(f"[{region}] Error stopping RDS DB {db_id}: {e}")

    return stopped_dbs
