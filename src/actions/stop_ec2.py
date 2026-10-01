import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Union
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client
from src.utils.logger import get_logger

logger = get_logger(__name__)


def stop_ec2_instances(instances: List[Union[str, dict]]) -> List[str]:
    """
    Stops a list of EC2 instances across targeted AWS regions.
    Accepts either instance ID strings or resource dictionaries with region.
    Adds tracking tags: CostOptimizer=true and CostOptimizerStopTimestamp.
    Respects DRY_RUN environment variable.
    Returns a list of successfully stopped instance IDs.
    """
    if not instances:
        logger.info("No EC2 instances to stop.")
        return []

    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"
    default_region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    stopped_instances: List[str] = []

    timestamp = datetime.now(timezone.utc).isoformat()
    tags = [
        {"Key": "CostOptimizer", "Value": "true"},
        {"Key": "CostOptimizerStopTimestamp", "Value": timestamp},
    ]

    # Group instances by region
    region_map: Dict[str, List[str]] = defaultdict(list)
    for item in instances:
        if isinstance(item, dict):
            instance_id = item.get("resource_id")
            region = item.get("details", {}).get("region", default_region)
        else:
            instance_id = str(item)
            region = default_region

        if instance_id:
            region_map[region].append(instance_id)

    for region, instance_ids in region_map.items():
        if dry_run:
            logger.info(
                f"[DRY RUN] Would stop EC2 in {region}: {instance_ids}"
            )
            logger.info(
                f"[DRY RUN] Would apply tags to EC2 in {region}: {tags}"
            )
            stopped_instances.extend(instance_ids)
            continue

        logger.info(
            f"Stopping EC2 instances in region {region}: {instance_ids}"
        )
        ec2_client = get_aws_client("ec2", region_name=region)

        # Apply tracking tags first
        try:
            ec2_client.create_tags(Resources=instance_ids, Tags=tags)
            logger.info(
                f"[{region}] Applied optimizer tags to {instance_ids}"
            )
        except ClientError as e:
            logger.error(
                f"[{region}] Failed to apply tags to {instance_ids}: {e}"
            )

        # Stop instances
        try:
            response = ec2_client.stop_instances(InstanceIds=instance_ids)
            for inst in response.get("StoppingInstances", []):
                stopped_instances.append(inst.get("InstanceId"))
            logger.info(
                f"[{region}] Successfully stopped EC2: {instance_ids}"
            )
        except ClientError as e:
            logger.error(
                f"[{region}] Error stopping EC2 instances {instance_ids}: {e}"
            )

    return stopped_instances
