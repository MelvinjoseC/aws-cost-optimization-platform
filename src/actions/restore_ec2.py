import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Union
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client, get_target_regions
from src.utils.logger import get_logger

logger = get_logger(__name__)


def find_stopped_optimizer_instances(regions: List[str] = None) -> List[Dict]:
    """
    Discovers stopped EC2 instances tagged with CostOptimizer=true
    across target AWS regions.
    """
    target_regions = regions or get_target_regions()
    candidates: List[Dict] = []

    for region in target_regions:
        ec2_client = get_aws_client("ec2", region_name=region)
        try:
            paginator = ec2_client.get_paginator("describe_instances")
            pages = paginator.paginate(
                Filters=[
                    {"Name": "instance-state-name", "Values": ["stopped"]},
                    {"Name": "tag:CostOptimizer", "Values": ["true"]},
                ]
            )
            for page in pages:
                for reservation in page.get("Reservations", []):
                    for inst in reservation.get("Instances", []):
                        candidates.append({
                            "resource_id": inst.get("InstanceId"),
                            "details": {
                                "region": region,
                                "instance_type": inst.get("InstanceType"),
                            },
                        })
        except ClientError as e:
            logger.error(
                f"[{region}] Failed to query stopped instances: {e}"
            )
    return candidates


def restore_ec2_instances(
    instances: List[Union[str, dict]] = None
) -> List[str]:
    """
    Starts stopped EC2 instances that were previously stopped by CostOptimizer.
    Accepts either instance IDs or resource dicts.
    If no instances are passed, automatically discovers candidates.
    Applies CostOptimizer=restored tag.
    Returns a list of successfully started instance IDs.
    """
    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"
    default_region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    restored_instances: List[str] = []

    if instances is None:
        target_list = find_stopped_optimizer_instances()
    else:
        target_list = instances

    if not target_list:
        logger.info("No stopped EC2 instances found for restoration.")
        return []

    timestamp = datetime.now(timezone.utc).isoformat()
    restore_tags = [
        {"Key": "CostOptimizer", "Value": "restored"},
        {"Key": "CostOptimizerRestoredTimestamp", "Value": timestamp},
    ]

    region_map: Dict[str, List[str]] = defaultdict(list)
    for item in target_list:
        if isinstance(item, dict):
            inst_id = item.get("resource_id")
            region = item.get("details", {}).get("region", default_region)
        else:
            inst_id = str(item)
            region = default_region

        if inst_id:
            region_map[region].append(inst_id)

    for region, ids in region_map.items():
        if dry_run:
            logger.info(
                f"[DRY RUN] Would restore EC2 in {region}: {ids}"
            )
            restored_instances.extend(ids)
            continue

        logger.info(f"Restoring EC2 instances in {region}: {ids}")
        ec2_client = get_aws_client("ec2", region_name=region)

        try:
            response = ec2_client.start_instances(InstanceIds=ids)
            for inst in response.get("StartingInstances", []):
                restored_instances.append(inst.get("InstanceId"))

            # Update tags to mark as restored
            ec2_client.create_tags(Resources=ids, Tags=restore_tags)
            logger.info(
                f"[{region}] Successfully restored EC2 instances: {ids}"
            )
        except ClientError as e:
            logger.error(
                f"[{region}] Error restoring EC2 instances {ids}: {e}"
            )

    return restored_instances
