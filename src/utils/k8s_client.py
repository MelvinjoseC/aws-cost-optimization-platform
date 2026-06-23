import os
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from src.utils.logger import get_logger

logger = get_logger(__name__)

def initialize_k8s_client() -> bool:
    """
    Initializes the Kubernetes client config.
    Tries in-cluster config first, then falls back to kubeconfig.
    Returns True if successfully initialized.
    """
    try:
        # In-cluster config for pod environment
        config.load_in_cluster_config()
        logger.info("Successfully loaded in-cluster Kubernetes configuration.")
        return True
    except config.ConfigException:
        logger.info("In-cluster config not found. Trying local kubeconfig...")
        try:
            # Local config (supports custom path via KUBECONFIG env var)
            kubeconfig_path = os.environ.get("KUBECONFIG")
            if kubeconfig_path:
                config.load_kube_config(config_file=os.path.expanduser(kubeconfig_path))
            else:
                config.load_kube_config()
            logger.info("Successfully loaded local kubeconfig.")
            return True
        except Exception as e:
            logger.error(f"Failed to load local kubeconfig: {e}")
            return False

def get_apps_v1_api() -> client.AppsV1Api:
    """
    Returns initialized AppsV1Api client.
    """
    if initialize_k8s_client():
        return client.AppsV1Api()
    raise RuntimeError("Kubernetes client API could not be initialized.")

def get_custom_objects_api() -> client.CustomObjectsApi:
    """
    Returns initialized CustomObjectsApi client.
    """
    if initialize_k8s_client():
        return client.CustomObjectsApi()
    raise RuntimeError("Kubernetes client CustomObjectsApi could not be initialized.")
