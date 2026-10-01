from unittest.mock import MagicMock, patch
import os
import pytest
from src.detectors.k8s_detector import (
    detect_idle_k8s_deployments,
    calculate_deployment_savings,
)
from src.actions.scale_down import scale_down_k8s_deployments
from src.actions.restore_k8s import restore_k8s_deployments


def make_mock_deployment(
    name="idle-app",
    namespace="default",
    replicas=2,
    cpu="500m",
    mem="512Mi",
    annotations=None,
):
    """Helper to create a mocked V1Deployment object."""
    dep = MagicMock()
    dep.metadata.name = name
    dep.metadata.namespace = namespace
    dep.metadata.annotations = annotations or {}
    dep.metadata.creation_timestamp = None
    dep.spec.replicas = replicas

    container = MagicMock()
    container.resources.requests = {"cpu": cpu, "memory": mem}
    dep.spec.template.spec.containers = [container]
    return dep


def test_calculate_deployment_savings():
    """Test Fargate-based monthly cost estimation calculation."""
    dep = make_mock_deployment(replicas=2, cpu="500m", mem="512Mi")
    savings = calculate_deployment_savings(dep)
    assert savings > 0.0
    assert isinstance(savings, float)


@patch("src.detectors.k8s_detector.get_apps_v1_api")
def test_detect_idle_k8s_deployments(mock_get_api):
    """Test Kubernetes detector filters namespaces and identifies idle workloads."""
    mock_api = MagicMock()
    mock_get_api.return_value = mock_api

    idle_dep = make_mock_deployment(name="idle-worker", namespace="staging")
    system_dep = make_mock_deployment(
        name="coredns", namespace="kube-system"
    )
    opt_out_dep = make_mock_deployment(
        name="critical-service",
        namespace="default",
        annotations={"cost-optimizer/opt-out": "true"},
    )

    deployment_list = MagicMock()
    deployment_list.items = [idle_dep, system_dep, opt_out_dep]
    mock_api.list_deployment_for_all_namespaces.return_value = deployment_list

    results = detect_idle_k8s_deployments()

    assert len(results) == 1
    assert results[0]["resource_id"] == "staging/idle-worker"
    assert results[0]["name"] == "idle-worker"
    assert results[0]["resource_type"] == "KubernetesDeployment"


@patch("src.actions.scale_down.get_apps_v1_api")
def test_scale_down_k8s_deployments(mock_get_api):
    """Test scaling deployment down to 0 replicas and saving original count."""
    mock_api = MagicMock()
    mock_get_api.return_value = mock_api

    dep = make_mock_deployment(name="idle-app", namespace="default", replicas=3)
    mock_api.read_namespaced_deployment.return_value = dep

    deployments_to_scale = [
        {"resource_id": "default/idle-app", "name": "idle-app", "details": {"namespace": "default"}}
    ]

    # Active run
    os.environ["DRY_RUN"] = "false"
    scaled = scale_down_k8s_deployments(deployments_to_scale)

    assert "default/idle-app" in scaled
    assert mock_api.patch_namespaced_deployment.called
    call_args = mock_api.patch_namespaced_deployment.call_args[1]
    body = call_args["body"]
    assert body["spec"]["replicas"] == 0
    annotations = body["metadata"]["annotations"]
    assert annotations["cost-optimizer/original-replicas"] == "3"


@patch("src.actions.restore_k8s.get_apps_v1_api")
def test_restore_k8s_deployments(mock_get_api):
    """Test restoring deployment to original replica count."""
    mock_api = MagicMock()
    mock_get_api.return_value = mock_api

    dep = make_mock_deployment(
        name="idle-app",
        namespace="default",
        replicas=0,
        annotations={"cost-optimizer/original-replicas": "4"},
    )
    mock_api.read_namespaced_deployment.return_value = dep

    deployments_to_restore = [
        {
            "resource_id": "default/idle-app",
            "name": "idle-app",
            "details": {"namespace": "default", "original_replicas": 4},
        }
    ]

    os.environ["DRY_RUN"] = "false"
    restored = restore_k8s_deployments(deployments_to_restore)

    assert "default/idle-app" in restored
    assert mock_api.patch_namespaced_deployment.called
    call_args = mock_api.patch_namespaced_deployment.call_args[1]
    assert call_args["body"]["spec"]["replicas"] == 4
