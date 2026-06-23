import os
from datetime import datetime, timezone
from kubernetes import client
from kubernetes.client.rest import ApiException
from src.utils.k8s_client import get_apps_v1_api
from src.utils.logger import get_logger

logger = get_logger(__name__)


def scale_down_k8s_deployments(deployments: list) -> list:
    """
    Scales Kubernetes deployments down to 0 replicas.
    Saves original replica count in annotations ('cost-optimizer/original-replicas')
    and scaling timestamp ('cost-optimizer/scaled-at') for restore operations.
    Respects DRY_RUN environment variable.
    Returns a list of successfully scaled deployment resource IDs.
    """
    if not deployments:
        logger.info("No Kubernetes deployments to scale down.")
        return []

    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"
    apps_api = get_apps_v1_api()
    scaled_deployments = []
    
    timestamp = datetime.now(timezone.utc).isoformat()
    
    for dep in deployments:
        resource_id = dep.get('resource_id')  # "namespace/deployment_name"
        name = dep.get('name')
        namespace = dep.get('details', {}).get('namespace')
        
        try:
            # 1. Fetch current deployment to get exact replica count and annotations
            deployment = apps_api.read_namespaced_deployment(name=name, namespace=namespace)
            current_replicas = deployment.spec.replicas
            
            # If already 0, skip
            if current_replicas == 0:
                logger.info(f"Deployment {namespace}/{name} is already at 0 replicas.")
                continue
                
            annotations = deployment.metadata.annotations or {}
            
            # Save original replicas in annotations if not already present
            # This protects against overwriting the original size if run multiple times
            if 'cost-optimizer/original-replicas' not in annotations:
                annotations['cost-optimizer/original-replicas'] = str(current_replicas)
                
            annotations['cost-optimizer/scaled-at'] = timestamp
            annotations['cost-optimizer/scaled-by'] = 'aws-cost-optimizer'
            
            patch_body = {
                "metadata": {
                    "annotations": annotations
                },
                "spec": {
                    "replicas": 0
                }
            }
            
            if dry_run:
                logger.info(
                    f"[DRY RUN] Would scale deployment {namespace}/{name} to 0 replicas. "
                    f"Original Replicas: {current_replicas}. Annotations: {annotations}"
                )
                scaled_deployments.append(resource_id)
                continue
                
            logger.info(f"Scaling deployment {namespace}/{name} from {current_replicas} to 0 replicas...")
            
            apps_api.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=patch_body
            )
            
            scaled_deployments.append(resource_id)
            logger.info(f"Successfully scaled deployment {namespace}/{name} to 0.")
            
        except ApiException as e:
            logger.error(f"Kubernetes API error scaling deployment {namespace}/{name}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error scaling deployment {namespace}/{name}: {e}")
            
    return scaled_deployments
