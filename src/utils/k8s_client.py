import os
from kubernetes import client, config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Global flag to track Kubernetes client configuration initialization
_K8S_INITIALIZED: bool = False


def initialize_k8s_client() -> bool:
    """
    Initializes the Kubernetes client configuration.

    Attempts to load the in-cluster configuration first. If running outside the
    cluster, falls back to the local kubeconfig (respecting the custom path defined
    by the KUBECONFIG environment variable, if set).

    Returns:
        bool: True if initialization succeeded, False otherwise.
    """
    global _K8S_INITIALIZED
    if _K8S_INITIALIZED:
        return True

    try:
        # In-cluster config for pod environment
        config.load_in_cluster_config()
        logger.info("Successfully loaded in-cluster Kubernetes configuration.")
        _K8S_INITIALIZED = True
        return True
    except config.ConfigException:
        logger.info("In-cluster config not found. Trying local kubeconfig...")
        try:
            # Local config (supports custom path via KUBECONFIG env var)
            kubeconfig_path: str = os.environ.get("KUBECONFIG", "")
            if kubeconfig_path:
                config.load_kube_config(config_file=os.path.expanduser(kubeconfig_path))
            else:
                config.load_kube_config()
            logger.info("Successfully loaded local kubeconfig.")
            _K8S_INITIALIZED = True
            return True
        except Exception as e:
            logger.error(f"Failed to load local kubeconfig: {e}")
            return False


def get_apps_v1_api() -> client.AppsV1Api:
    """
    Returns an initialized AppsV1Api client instance.

    Returns:
        client.AppsV1Api: The Kubernetes AppsV1 API client.

    Raises:
        RuntimeError: If the Kubernetes client API could not be initialized.
    """
    if initialize_k8s_client():
        return client.AppsV1Api()
    raise RuntimeError("Kubernetes client API could not be initialized.")


def get_custom_objects_api() -> client.CustomObjectsApi:
    """
    Returns an initialized CustomObjectsApi client instance.

    Returns:
        client.CustomObjectsApi: The Kubernetes CustomObjects API client.

    Raises:
        RuntimeError: If the Kubernetes client CustomObjects API could not be initialized.
    """
    if initialize_k8s_client():
        return client.CustomObjectsApi()
    raise RuntimeError("Kubernetes client CustomObjectsApi could not be initialized.")
