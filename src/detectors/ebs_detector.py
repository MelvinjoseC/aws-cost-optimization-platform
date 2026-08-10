from src.utils.aws_client import get_aws_client, get_target_regions
from src.utils.logger import get_logger

logger = get_logger(__name__)

# standard EBS GP3 storage price per GB-month in us-east-1
EBS_GB_MONTHLY_PRICE = 0.08


def detect_unattached_ebs_volumes() -> list:
    """
    Scans for EBS volumes in 'available' state (unattached to any EC2 instance).
    Excludes volumes with opt-out tag: CostOptimizerOptOut=true.
    Supports multi-region scanning.
    """
    logger.info("Starting unattached EBS volume detection...")

    unattached_volumes = []
    target_regions = get_target_regions()

    for region in target_regions:
        logger.info(f"Scanning EBS volumes in region: {region}")
        ec2_client = get_aws_client("ec2", region_name=region)

        try:
            paginator = ec2_client.get_paginator("describe_volumes")
            # Filter for volumes in 'available' state (which means they are not attached)
            pages = paginator.paginate(
                Filters=[{"Name": "status", "Values": ["available"]}]
            )

            for page in pages:
                for volume in page.get("Volumes", []):
                    volume_id = volume.get("VolumeId")
                    size_gb = volume.get("Size")
                    volume_type = volume.get("VolumeType")
                    tags = volume.get("Tags", [])

                    tag_dict = {tag["Key"]: tag["Value"] for tag in tags}

                    if tag_dict.get("CostOptimizerOptOut") == "true":
                        logger.info(
                            f"EBS volume {volume_id} opted out of cleanup via tag."
                        )
                        continue

                    name = tag_dict.get("Name", "Unnamed")

                    # Monthly savings calculation: GB * price per GB
                    monthly_savings = round(size_gb * EBS_GB_MONTHLY_PRICE, 2)

                    logger.info(
                        f"[{region}] Detected Unattached EBS Volume: ID={volume_id}, Name={name}, "
                        f"Size={size_gb}GB, Type={volume_type}, Estimated Savings=${monthly_savings}/mo"
                    )

                    unattached_volumes.append(
                        {
                            "resource_id": volume_id,
                            "resource_type": "EBS",
                            "name": name,
                            "details": {
                                "region": region,
                                "size_gb": size_gb,
                                "volume_type": volume_type,
                                "create_time": volume.get("CreateTime").isoformat(),
                            },
                            "estimated_monthly_savings": monthly_savings,
                            "opt_out_tag": False,
                        }
                    )

        except ClientError as e:
            logger.error(f"Error describing EBS volumes in region {region}: {e}")
            # Continue scanning other regions even if one fails
            continue

    logger.info(
        f"EBS scanning completed. Found {len(unattached_volumes)} unattached volumes across all targeted regions."
    )
    return unattached_volumes
