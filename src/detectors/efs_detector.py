from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client, get_target_regions
from src.utils.config import get_config
from src.utils.logger import get_logger
from src.utils.pricing import (
    EFS_STANDARD_PER_GB,
    calculate_efs_lifecycle_savings,
)

logger = get_logger(__name__)


def get_efs_io_bytes(
    cw_client, file_system_id: str, days: int
) -> float:
    """Queries CloudWatch for read and write I/O bytes over observation window."""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    total_bytes = 0.0
    for metric in ["DataReadIOBytes", "DataWriteIOBytes"]:
        try:
            response = cw_client.get_metric_statistics(
                Namespace="AWS/EFS",
                MetricName=metric,
                Dimensions=[{"Name": "FileSystemId", "Value": file_system_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=86400,
                Statistics=["Sum"],
            )
            datapoints = response.get("Datapoints", [])
            total_bytes += sum(dp.get("Sum", 0.0) for dp in datapoints)
        except ClientError as e:
            logger.warning(
                f"Could not retrieve metric {metric} for EFS {file_system_id}: {e}"
            )
    return total_bytes


def detect_idle_or_untiered_efs() -> List[Dict]:
    """
    Scans for idle or unmounted EFS file systems, as well as file systems
    without lifecycle policies transitioning aged data to Infrequent Access (IA).
    """
    logger.info("Starting Amazon EFS cost optimization detection...")
    cfg = get_config(reload=True)
    target_regions = get_target_regions()
    detected_efs = []

    for region in target_regions:
        logger.info(f"Scanning EFS file systems in region: {region}")
        efs_client = get_aws_client("efs", region_name=region)
        cw_client = get_aws_client("cloudwatch", region_name=region)

        try:
            paginator = efs_client.get_paginator("describe_file_systems")
            for page in paginator.paginate():
                for fs in page.get("FileSystems", []):
                    fs_id = fs.get("FileSystemId")
                    name = fs.get("Name") or "Unnamed-EFS"
                    num_mounts = fs.get("NumberOfMountTargets", 0)
                    size_in_bytes = fs.get("SizeInBytes", {}).get("Value", 0)
                    size_gb = round(size_in_bytes / (1024**3), 2)
                    tags = {t["Key"]: t["Value"] for t in fs.get("Tags", [])}

                    if tags.get("CostOptimizerOptOut") == "true":
                        logger.info(f"EFS {fs_id} opted out via tag.")
                        continue

                    # Case 1: Completely unmounted file system
                    if num_mounts == 0:
                        monthly_cost = round(size_gb * EFS_STANDARD_PER_GB, 2)
                        # Minimal threshold for reporting
                        monthly_savings = max(monthly_cost, 1.50)
                        logger.info(
                            f"[{region}] Detected Unmounted EFS: {fs_id} ({name}), "
                            f"Size={size_gb}GB, Estimated Savings=${monthly_savings}/mo"
                        )
                        detected_efs.append(
                            {
                                "resource_id": fs_id,
                                "resource_type": "EFS",
                                "name": name,
                                "details": {
                                    "region": region,
                                    "size_gb": size_gb,
                                    "mount_targets": 0,
                                    "issue": "Unmounted file system with zero active mount targets",
                                },
                                "tags": tags,
                                "estimated_monthly_savings": monthly_savings,
                            }
                        )
                        continue

                    # Case 2: Mounted but 0 I/O bytes over observation window
                    io_bytes = get_efs_io_bytes(cw_client, fs_id, cfg.efs_idle_days)
                    if io_bytes == 0.0 and size_gb > 0:
                        monthly_savings = round(size_gb * EFS_STANDARD_PER_GB, 2)
                        logger.info(
                            f"[{region}] Detected Idle EFS: {fs_id} ({name}), "
                            f"0 I/O over {cfg.efs_idle_days}d, Savings=${monthly_savings}/mo"
                        )
                        detected_efs.append(
                            {
                                "resource_id": fs_id,
                                "resource_type": "EFS",
                                "name": name,
                                "details": {
                                    "region": region,
                                    "size_gb": size_gb,
                                    "mount_targets": num_mounts,
                                    "issue": f"Zero I/O bytes consumed in {cfg.efs_idle_days} days",
                                },
                                "tags": tags,
                                "estimated_monthly_savings": monthly_savings,
                            }
                        )
                        continue

                    # Case 3: Check missing lifecycle policy for larger standard file systems (>5 GB)
                    if size_gb >= 5.0:
                        try:
                            lifecycle = efs_client.describe_lifecycle_configuration(
                                FileSystemId=fs_id
                            )
                            rules = lifecycle.get("LifecyclePolicies", [])
                            has_ia_rule = any("TransitionToIA" in r for r in rules)
                            if not has_ia_rule:
                                savings = calculate_efs_lifecycle_savings(size_gb)
                                logger.info(
                                    f"[{region}] Detected Untiered EFS: {fs_id} ({name}), "
                                    f"Size={size_gb}GB without IA tier, Potential Savings=${savings}/mo"
                                )
                                detected_efs.append(
                                    {
                                        "resource_id": fs_id,
                                        "resource_type": "EFS",
                                        "name": name,
                                        "details": {
                                            "region": region,
                                            "size_gb": size_gb,
                                            "mount_targets": num_mounts,
                                            "issue": "No lifecycle rule configured for Infrequent Access tier",
                                        },
                                        "tags": tags,
                                        "estimated_monthly_savings": savings,
                                    }
                                )
                        except ClientError as e:
                            logger.debug(f"Could not inspect lifecycle for {fs_id}: {e}")

        except ClientError as e:
            logger.error(f"Failed scanning EFS in region {region}: {e}")

    logger.info(f"Completed EFS detection. Found {len(detected_efs)} optimization opportunities.")
    return detected_efs
