import os
from typing import Any, Dict, Optional
import boto3
from botocore.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AWSClientManager:
    """
    Manager for AWS clients to reuse sessions and clients.

    This class implements a thread-safe-like cache for boto3 sessions and clients,
    ensuring configurations such as retries are uniformly configured across
    all API invocations.
    """

    def __init__(self) -> None:
        self._session: Optional[boto3.Session] = None
        self._clients: Dict[str, Any] = {}

    def _get_session(self) -> boto3.Session:
        """
        Retrieves or initializes the global boto3 Session.

        Returns:
            boto3.Session: The active boto3 Session.
        """
        if not self._session:
            region: str = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
            logger.info(f"Initializing AWS Session with region: {region}")
            self._session = boto3.Session(region_name=region)
        return self._session

    def get_client(self, service_name: str, region_name: Optional[str] = None) -> Any:
        """
        Retrieves or creates a boto3 client with standard retry configuration,
        scoped to a specific region.

        Args:
            service_name (str): The AWS service name (e.g. 'ec2', 'rds').
            region_name (Optional[str]): The AWS region name. If not specified,
                                         defaults to the environment region.

        Returns:
            Any: The configured boto3 client instance.
        """
        target_region: str = region_name or os.environ.get(
            "AWS_DEFAULT_REGION", "us-east-1"
        )
        cache_key: str = f"{target_region}:{service_name}"

        if cache_key not in self._clients:
            session: boto3.Session = self._get_session()
            # Production-realistic retry config for boto3 clients
            config: Config = Config(retries={"max_attempts": 5, "mode": "standard"})
            self._clients[cache_key] = session.client(
                service_name, region_name=target_region, config=config
            )
        return self._clients[cache_key]


# Global manager instance
aws_manager: AWSClientManager = AWSClientManager()


def get_aws_client(service_name: str, region_name: Optional[str] = None) -> Any:
    """
    Helper function to get an AWS service client from the global manager instance.

    Args:
        service_name (str): The name of the AWS service.
        region_name (Optional[str]): Optional AWS region name.

    Returns:
        Any: The boto3 client.
    """
    return aws_manager.get_client(service_name, region_name=region_name)


def get_target_regions() -> list:
    """
    Retrieves the list of target AWS regions to scan.

    Parses a comma-separated list from the 'AWS_REGIONS' environment variable.
    Falls back to 'AWS_DEFAULT_REGION' if 'AWS_REGIONS' is not configured.

    Returns:
        list: A list of region names as strings.
    """
    regions_str: str = os.environ.get("AWS_REGIONS", "").strip()
    if regions_str:
        return [r.strip() for r in regions_str.split(",") if r.strip()]
    return [os.environ.get("AWS_DEFAULT_REGION", "us-east-1")]
