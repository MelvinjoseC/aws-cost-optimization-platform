import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client, get_target_regions
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Standard AWS EBS snapshot storage price ($0.05 per GB-month standard tier)
SNAPSHOT_GB_MONTHLY_PRICE = 0.05


def detect_stale_ebs_snapshots() -> List[Dict]:
    """
    Scans for EBS snapshots owned by the account older than retention threshold
    (default 30 days) whose source volume no longer exists or is unattached.
    Excludes snapshots tagged with CostOptimizerOptOut=true.
    Supports multi-region scanning.
    """
    logger.info("Starting stale EBS snapshot detection...")

    max_age_days = int(os.environ.get("SNAPSHOT_MAX_AGE_DAYS", 30))
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    stale_snapshots: List[Dict] = []
    target_regions = get_target_regions()

    for region in target_regions:
        logger.info(f"Scanning EBS snapshots in region: {region}")
        ec2_client = get_aws_client("ec2", region_name=region)

        try:
            # 1. Fetch existing active volume IDs for orphan check
            active_volumes = set()
            vol_paginator = ec2_client.get_paginator("describe_volumes")
            for vol_page in vol_paginator.paginate():
                for vol in vol_page.get("Volumes", []):
                    active_volumes.add(vol.get("VolumeId"))

            # 2. Fetch snapshots owned by 'self'
            snap_paginator = ec2_client.get_paginator("describe_snapshots")
            pages = snap_paginator.paginate(OwnerIds=["self"])

            for page in pages:
                for snap in page.get("Snapshots", []):
                    snap_id = snap.get("SnapshotId")
                    vol_id = snap.get("VolumeId")
                    start_time = snap.get("StartTime")
                    size_gb = snap.get("VolumeSize", 0)
                    tags = snap.get("Tags", [])

                    tag_dict = {t["Key"]: t["Value"] for t in tags}
                    if tag_dict.get("CostOptimizerOptOut") == "true":
                        continue

                    # Check if snapshot is older than cutoff
                    if start_time and start_time < cutoff_time:
                        # If source volume is gone, it's an orphaned snapshot
                        is_orphaned = vol_id not in active_volumes

                        monthly_savings = round(
                            size_gb * SNAPSHOT_GB_MONTHLY_PRICE, 2
                        )
                        name = tag_dict.get(
                            "Name", f"snapshot-{snap_id}"
                        )

                        logger.info(
                            f"[{region}] Stale Snapshot: ID={snap_id}, "
                            f"Size={size_gb}GB, Age>{max_age_days}d, "
                            f"Savings=${monthly_savings}/mo"
                        )

                        stale_snapshots.append({
                            "resource_id": snap_id,
                            "resource_type": "EBSSnapshot",
                            "name": name,
                            "details": {
                                "region": region,
                                "volume_id": vol_id,
                                "size_gb": size_gb,
                                "is_orphaned": is_orphaned,
                                "start_time": (
                                    start_time.isoformat()
                                    if start_time else None
                                ),
                            },
                            "estimated_monthly_savings": monthly_savings,
                            "opt_out_tag": False,
                        })

        except ClientError as e:
            logger.error(
                f"Error scanning snapshots in region {region}: {e}"
            )
            continue

    logger.info(
        f"EBS snapshot scan completed. Found {len(stale_snapshots)} "
        f"stale snapshots across targeted regions."
    )
    return stale_snapshots
