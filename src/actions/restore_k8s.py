import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
from kubernetes.client.rest import ApiException
from src.utils.k8s_client import get_apps_v1_api
from src.utils.logger import get_logger

logger = get_logger(__name__)


def find_scaled_down_deployments() -> List[Dict]:
    """
    Finds Kubernetes deployments that were previously scaled down by
    CostOptimizer with 'cost-optimizer/original-replicas' annotation.
    """
    candidates: List[Dict] = []
    try:
        apps_api = get_apps_v1_api()
        deps = apps_api.list_deployment_for_all_namespaces()
        for dep in deps.items:
            annotations = dep.metadata.annotations or {}
            orig_replicas = annotations.get("cost-optimizer/original-replicas")
            curr_replicas = dep.spec.replicas

            if orig_replicas is not None and curr_replicas == 0:
                name = dep.metadata.name
                namespace = dep.metadata.namespace
                candidates.append({
                    "resource_id": f"{namespace}/{name}",
                    "name": name,
                    "details": {
                        "namespace": namespace,
                        "original_replicas": int(orig_replicas),
                    },
                })
    except ApiException as e:
        logger.error(f"Error querying K8s deployments for restore: {e}")
    except Exception as e:
        logger.error(f"Unexpected error querying K8s deployments: {e}")
    return candidates


def restore_k8s_deployments(
    deployments: Optional[List[Dict]] = None
) -> List[str]:
    """
    Restores Kubernetes deployments to their original replica count.
    Respects DRY_RUN environment variable.
    Returns a list of successfully restored deployment IDs (namespace/name).
    """
    dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"
    restored_deployments: List[str] = []

    target_list = (
        deployments if deployments is not None
        else find_scaled_down_deployments()
    )

    if not target_list:
        logger.info("No Kubernetes deployments to restore.")
        return []

    apps_api = get_apps_v1_api()
    timestamp = datetime.now(timezone.utc).isoformat()

    for dep in target_list:
        res_id = dep.get("resource_id", "")
        name = dep.get("name")
        namespace = dep.get("details", {}).get("namespace", "default")
        orig_replicas = dep.get("details", {}).get("original_replicas")

        try:
            current_dep = apps_api.read_namespaced_deployment(
                name=name, namespace=namespace
            )
            annotations = current_dep.metadata.annotations or {}

            if orig_replicas is not None:
                target_count = orig_replicas
            else:
                key = "cost-optimizer/original-replicas"
                raw_val = annotations.get(key, 1)
                target_count = int(raw_val)

            annotations["cost-optimizer/restored-at"] = timestamp
            # Remove original replicas tracking annotation to finish cycle
            annotations.pop("cost-optimizer/original-replicas", None)

            patch_body = {
                "metadata": {"annotations": annotations},
                "spec": {"replicas": target_count},
            }

            if dry_run:
                logger.info(
                    f"[DRY RUN] Would restore deployment {namespace}/{name} "
                    f"to {target_count} replicas."
                )
                restored_deployments.append(res_id)
                continue

            logger.info(
                f"Restoring deployment {namespace}/{name} to {target_count}..."
            )
            apps_api.patch_namespaced_deployment(
                name=name, namespace=namespace, body=patch_body
            )
            restored_deployments.append(res_id)
            logger.info(
                f"Successfully restored deployment {namespace}/{name}."
            )
        except ApiException as e:
            logger.error(
                f"API error restoring deployment {namespace}/{name}: {e}"
            )
        except Exception as e:
            logger.error(
                f"Unexpected error restoring {namespace}/{name}: {e}"
            )

    return restored_deployments
