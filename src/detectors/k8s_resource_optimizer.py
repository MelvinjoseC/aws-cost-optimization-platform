from typing import Dict, List
from kubernetes.client.rest import ApiException
from src.utils.k8s_client import get_apps_v1_api
from src.utils.logger import get_logger
from src.detectors.k8s_detector import (
    parse_cpu_to_cores,
    parse_mem_to_gb,
    FARGATE_CPU_HOURLY,
    FARGATE_MEM_HOURLY,
)

logger = get_logger(__name__)

SYSTEM_NAMESPACES = {
    "kube-system",
    "kube-public",
    "kube-node-lease",
    "kubernetes-dashboard",
}


def analyze_container_resources(
    container, replicas: int
) -> Dict[str, float]:
    """
    Evaluates container CPU/Memory requests against baseline recommendations.
    Returns potential monthly savings if overprovisioned.
    """
    res = container.resources
    requests = res.requests if res and res.requests else {}
    cpu_cores = parse_cpu_to_cores(requests.get("cpu"))
    mem_gb = parse_mem_to_gb(requests.get("memory"))

    # Baseline recommended sizing for standard web/microservice pods:
    # 0.25 Cores, 0.5 GB RAM
    rec_cpu = 0.25
    rec_mem = 0.50

    delta_cpu = max(0.0, cpu_cores - rec_cpu)
    delta_mem = max(0.0, mem_gb - rec_mem)

    # If container is requesting more than 1.5x baseline
    if delta_cpu > 0.5 or delta_mem > 1.0:
        hourly_waste = (
            (delta_cpu * FARGATE_CPU_HOURLY) + (delta_mem * FARGATE_MEM_HOURLY)
        )
        monthly_waste = round(hourly_waste * 24 * 30 * replicas, 2)
        return {
            "waste_monthly": monthly_waste,
            "current_cpu": cpu_cores,
            "current_mem": mem_gb,
            "rec_cpu": rec_cpu,
            "rec_mem": rec_mem,
        }
    return {}


def detect_overprovisioned_k8s_workloads() -> List[Dict]:
    """
    Analyzes Kubernetes deployments to identify containers with
    disproportionate CPU and Memory requests compared to standard baselines.
    """
    logger.info("Starting Kubernetes workload rightsizing analysis...")
    recommendations: List[Dict] = []

    try:
        apps_api = get_apps_v1_api()
        deployments = apps_api.list_deployment_for_all_namespaces()

        for dep in deployments.items:
            ns = dep.metadata.namespace
            name = dep.metadata.name

            if ns in SYSTEM_NAMESPACES:
                continue

            annotations = dep.metadata.annotations or {}
            if annotations.get("cost-optimizer/opt-out") == "true":
                continue

            replicas = dep.spec.replicas or 1
            if replicas == 0:
                continue

            containers = dep.spec.template.spec.containers
            dep_savings = 0.0
            container_details = []

            for c in containers:
                eval_res = analyze_container_resources(c, replicas)
                if eval_res:
                    dep_savings += eval_res["waste_monthly"]
                    container_details.append({
                        "container": c.name,
                        "current_cpu": eval_res["current_cpu"],
                        "current_mem_gb": eval_res["current_mem"],
                        "recommended_cpu": eval_res["rec_cpu"],
                        "recommended_mem_gb": eval_res["rec_mem"],
                    })

            if dep_savings > 0:
                logger.info(
                    f"K8s Rightsizing: {ns}/{name} (Replicas={replicas}) "
                    f"could save est. ${dep_savings:.2f}/mo"
                )
                recommendations.append({
                    "resource_id": f"{ns}/{name}",
                    "resource_type": "KubernetesRightsizing",
                    "name": name,
                    "details": {
                        "namespace": ns,
                        "replicas": replicas,
                        "containers": container_details,
                    },
                    "estimated_monthly_savings": round(dep_savings, 2),
                    "opt_out_tag": False,
                })

    except ApiException as e:
        logger.error(f"K8s API error during workload rightsizing: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in K8s rightsizing: {e}")

    logger.info(
        f"K8s rightsizing completed. Found {len(recommendations)} "
        f"overprovisioned deployments."
    )
    return recommendations
