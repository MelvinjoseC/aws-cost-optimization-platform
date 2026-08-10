import os
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client
from src.utils.logger import get_logger

logger = get_logger(__name__)


def delete_unattached_ebs_volumes(volumes: list) -> list:
    """
    Deletes a list of unattached EBS volumes.
    Respects DRY_RUN environment variable.
    Returns a list of successfully deleted volume IDs.
    """
    if not volumes:
        logger.info("No EBS volumes to delete.")
        return []

    dry_run: bool = os.environ.get("DRY_RUN", "true").lower() == "true"
    deleted_volumes: list = []

    for vol in volumes:
        volume_id: str = vol.get("resource_id", "")
        if not volume_id:
            continue

        region: str = vol.get("details", {}).get(
            "region", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        )

        if dry_run:
            logger.info(
                f"[DRY RUN] Would delete EBS volume '{volume_id}' in region '{region}'"
            )
            deleted_volumes.append(volume_id)
            continue

        logger.info(f"Deleting EBS volume: {volume_id} in region: {region}")
        ec2_client = get_aws_client("ec2", region_name=region)
        try:
            ec2_client.delete_volume(VolumeId=volume_id)
            deleted_volumes.append(volume_id)
            logger.info(f"Successfully deleted EBS volume: {volume_id}")
        except ClientError as e:
            logger.error(
                f"Error deleting EBS volume {volume_id} in region {region}: {e}"
            )

    return deleted_volumes
