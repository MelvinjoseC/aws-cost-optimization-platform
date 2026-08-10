import os
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client
from src.utils.logger import get_logger

logger = get_logger(__name__)


def release_unused_eips(eips: list) -> list:
    """
    Releases a list of unassociated Elastic IPs.
    Respects DRY_RUN environment variable.
    Returns a list of successfully released allocation IDs.
    """
    if not eips:
        logger.info("No Elastic IPs to release.")
        return []

    dry_run: bool = os.environ.get("DRY_RUN", "true").lower() == "true"
    released_eips: list = []

    for eip in eips:
        allocation_id: str = eip.get("resource_id", "")
        if not allocation_id:
            continue

        region: str = eip.get("details", {}).get(
            "region", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        )
        public_ip: str = eip.get("details", {}).get("public_ip", "N/A")

        if dry_run:
            logger.info(
                f"[DRY RUN] Would release Elastic IP '{public_ip}' (AllocationId: '{allocation_id}') in region '{region}'"
            )
            released_eips.append(allocation_id)
            continue

        logger.info(
            f"Releasing Elastic IP: {public_ip} (AllocationId: {allocation_id}) in region: {region}"
        )
        ec2_client = get_aws_client("ec2", region_name=region)
        try:
            ec2_client.release_address(AllocationId=allocation_id)
            released_eips.append(allocation_id)
            logger.info(f"Successfully released Elastic IP: {public_ip}")
        except ClientError as e:
            logger.error(
                f"Error releasing Elastic IP {public_ip} (AllocationId: {allocation_id}) in region {region}: {e}"
            )

    return released_eips
