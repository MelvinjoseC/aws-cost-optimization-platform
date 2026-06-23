import os
from datetime import datetime, timezone
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client
from src.utils.logger import get_logger

logger = get_logger(__name__)


def stop_rds_instances(rds_resources: list) -> list:
    """
    Snapshots and stops a list of idle RDS DB instances.
    Adds tracking tags: CostOptimizer=true and CostOptimizerStopTimestamp.
    Creates a snapshot before stopping: snapshot-<db-id>-<timestamp>.
    Respects DRY_RUN environment variable.
    Returns a list of successfully stopped DB instance identifiers.
    """
    if not rds_resources:
        logger.info("No RDS DB instances to stop.")
        return []

    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"
    rds_client = get_aws_client('rds')
    stopped_dbs = []
    
    # RDS snapshot and tag timestamp formatting
    # Note: RDS Snapshot identifier cannot contain colons or periods.
    timestamp_raw = datetime.now(timezone.utc)
    snapshot_suffix = timestamp_raw.strftime("%Y-%m-%d-%H-%M-%S")
    timestamp_iso = timestamp_raw.isoformat()
    
    tags = [
        {'Key': 'CostOptimizer', 'Value': 'true'},
        {'Key': 'CostOptimizerStopTimestamp', 'Value': timestamp_iso}
    ]
    
    for rds in rds_resources:
        db_id = rds.get('resource_id')
        arn = rds.get('details', {}).get('arn')
        
        snapshot_id = f"snapshot-{db_id}-{snapshot_suffix}"
        
        # Max length of RDS snapshot identifier is 255 characters
        snapshot_id = snapshot_id[:255]
        
        if dry_run:
            logger.info(f"[DRY RUN] Would snapshot & stop RDS instance '{db_id}'. Snapshot Name: '{snapshot_id}'")
            if arn:
                logger.info(f"[DRY RUN] Would apply tags to RDS resource '{arn}': {tags}")
            continue
            
        logger.info(f"Stopping RDS DB instance: {db_id}. Creating snapshot: {snapshot_id}")
        
        # 1. Apply tags to the RDS instance
        if arn:
            try:
                rds_client.add_tags_to_resource(
                    ResourceName=arn,
                    Tags=tags
                )
                logger.info(f"Successfully applied tags to RDS instance {db_id}")
            except ClientError as e:
                logger.error(f"Failed to apply tags to RDS instance {db_id} (ARN: {arn}): {e}")
                # Continue with stopping even if tagging fails
        else:
            logger.warning(f"No ARN found in details for RDS instance {db_id}. Tagging skipped.")
            
        # 2. Stop instance with snapshot
        try:
            rds_client.stop_db_instance(
                DBInstanceIdentifier=db_id,
                DBSnapshotIdentifier=snapshot_id
            )
            stopped_dbs.append(db_id)
            logger.info(f"Successfully triggered stop for RDS DB: {db_id}")
        except ClientError as e:
            logger.error(f"Error stopping RDS DB {db_id}: {e}")
            
    return stopped_dbs
