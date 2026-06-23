import os
import boto3
from botocore.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)

class AWSClientManager:
    """
    Manager for AWS clients to reuse sessions and clients.
    """
    def __init__(self):
        self._session = None
        self._clients = {}

    def _get_session(self) -> boto3.Session:
        if not self._session:
            region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
            logger.info(f"Initializing AWS Session with region: {region}")
            self._session = boto3.Session(region_name=region)
        return self._session

    def get_client(self, service_name: str):
        """
        Gets or creates a boto3 client with standard retry configuration.
        """
        if service_name not in self._clients:
            session = self._get_session()
            # Production-realistic retry config for boto3 clients
            config = Config(
                retries={
                    'max_attempts': 5,
                    'mode': 'standard'
                }
            )
            self._clients[service_name] = session.client(service_name, config=config)
        return self._clients[service_name]

# Global manager instance
aws_manager = AWSClientManager()

def get_aws_client(service_name: str):
    return aws_manager.get_client(service_name)
