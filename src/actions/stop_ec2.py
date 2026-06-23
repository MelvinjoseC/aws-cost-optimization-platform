import os
from datetime import datetime, timezone
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client
from src.utils.logger import get_logger

logger = get_logger(__name__)


def stop_ec2_instances(instance_ids: list) -> list:
    """
    Stops a list of EC2 instances.
    Adds tracking tags: CostOptimizer=true and CostOptimizerStopTimestamp=<timestamp>.
    Respects DRY_RUN environment variable.
    Returns a list of successfully stopped instance IDs.
    """
    if not instance_ids:
        logger.info("No EC2 instances to stop.")
        return []

    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"
    ec2_client = get_aws_client('ec2')
    stopped_instances = []
    
    timestamp = datetime.now(timezone.utc).isoformat()
    tags = [
        {'Key': 'CostOptimizer', 'Value': 'true'},
        {'Key': 'CostOptimizerStopTimestamp', 'Value': timestamp}
    ]
    
    if dry_run:
        logger.info(f"[DRY RUN] Would stop EC2 instances: {instance_ids}")
        logger.info(f"[DRY RUN] Would apply tags to EC2 instances: {tags}")
        return instance_ids

    logger.info(f"Stopping EC2 instances: {instance_ids}")
    
    # Apply tracking tags first
    try:
        ec2_client.create_tags(
            Resources=instance_ids,
            Tags=tags
        )
        logger.info(f"Successfully applied optimizer tags to instances {instance_ids}")
    except ClientError as e:
        logger.error(f"Failed to apply tags to EC2 instances {instance_ids}: {e}")
        # Proceed with stopping even if tagging fails, but log warning
        
    # Stop instances
    try:
        response = ec2_client.stop_instances(InstanceIds=instance_ids)
        for instance in response.get('StoppingInstances', []):
            stopped_instances.append(instance.get('InstanceId'))
        logger.info(f"Successfully triggered stop for EC2 instances: {stopped_instances}")
    except ClientError as e:
        logger.error(f"Error stopping EC2 instances {instance_ids}: {e}")
        
    return stopped_instances
