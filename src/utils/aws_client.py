import os
from typing import Any, Dict, Optional
import boto3
from botocore.config import Config
from src.utils.config import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AWSClientManager:
    """
    Manager for AWS clients to reuse sessions and clients.

    Thread-safe cache for boto3 sessions and clients with uniform retries.
    """

    def __init__(self) -> None:
        self._session: Optional[boto3.Session] = None
        self._clients: Dict[str, Any] = {}

    def _get_session(self) -> boto3.Session:
        """Retrieves or initializes the global boto3 Session."""
        if not self._session:
            region: str = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
            logger.info(f"Initializing AWS Session with region: {region}")
            self._session = boto3.Session(region_name=region)
        return self._session

    def get_client(
        self, service_name: str, region_name: Optional[str] = None
    ) -> Any:
        """
        Retrieves or creates a boto3 client with standard retry configuration.
        """
        target_region: str = region_name or os.environ.get(
            "AWS_DEFAULT_REGION", "us-east-1"
        )
        cache_key: str = f"{target_region}:{service_name}"

        if cache_key not in self._clients:
            session: boto3.Session = self._get_session()
            config: Config = Config(
                retries={"max_attempts": 5, "mode": "standard"}
            )
            self._clients[cache_key] = session.client(
                service_name, region_name=target_region, config=config
            )
        return self._clients[cache_key]


# Global manager instance
aws_manager: AWSClientManager = AWSClientManager()


def get_aws_client(
    service_name: str, region_name: Optional[str] = None
) -> Any:
    """Helper function to get an AWS service client from manager."""
    return aws_manager.get_client(service_name, region_name=region_name)


def get_target_regions() -> list:
    """Retrieves the list of target AWS regions to scan from config."""
    cfg = get_config(reload=True)
    return cfg.regions
