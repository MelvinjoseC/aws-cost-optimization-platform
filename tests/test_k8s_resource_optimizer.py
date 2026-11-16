import unittest
from unittest.mock import MagicMock, patch
from kubernetes.client.rest import ApiException
from src.detectors.k8s_resource_optimizer import (
    analyze_container_resources,
    detect_overprovisioned_k8s_workloads,
)


class TestK8sResourceOptimizer(unittest.TestCase):
    def test_analyze_container_resources_oversized(self):
        mock_container = MagicMock()
        mock_container.name = "heavy-app"
        mock_container.resources.requests = {
            "cpu": "2000m",  # 2.0 cores
            "memory": "4Gi",  # 4.0 GB
        }

        result = analyze_container_resources(mock_container, replicas=2)
        self.assertIn("waste_monthly", result)
        self.assertGreater(result["waste_monthly"], 0)
        self.assertEqual(result["current_cpu"], 2.0)
        self.assertEqual(result["current_mem"], 4.0)

    def test_analyze_container_resources_standard(self):
        mock_container = MagicMock()
        mock_container.name = "light-app"
        mock_container.resources.requests = {
            "cpu": "250m",  # 0.25 cores
            "memory": "512Mi",  # 0.5 GB
        }

        result = analyze_container_resources(mock_container, replicas=1)
        self.assertEqual(result, {})

    @patch("src.detectors.k8s_resource_optimizer.get_apps_v1_api")
    def test_detect_overprovisioned_k8s_workloads_success(self, mock_get_apps_api):
        mock_apps = MagicMock()
        mock_get_apps_api.return_value = mock_apps

        mock_dep = MagicMock()
        mock_dep.metadata.namespace = "default"
        mock_dep.metadata.name = "web-api"
        mock_dep.metadata.annotations = {}
        mock_dep.spec.replicas = 3

        mock_container = MagicMock()
        mock_container.name = "web"
        mock_container.resources.requests = {"cpu": "2", "memory": "4Gi"}
        mock_dep.spec.template.spec.containers = [mock_container]

        mock_dep_list = MagicMock()
        mock_dep_list.items = [mock_dep]
        mock_apps.list_deployment_for_all_namespaces.return_value = mock_dep_list

        results = detect_overprovisioned_k8s_workloads()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["resource_id"], "default/web-api")
        self.assertEqual(results[0]["resource_type"], "KubernetesRightsizing")
        self.assertGreater(results[0]["estimated_monthly_savings"], 0)

    @patch("src.detectors.k8s_resource_optimizer.get_apps_v1_api")
    def test_skip_system_namespaces(self, mock_get_apps_api):
        mock_apps = MagicMock()
        mock_get_apps_api.return_value = mock_apps

        mock_dep = MagicMock()
        mock_dep.metadata.namespace = "kube-system"
        mock_dep.metadata.name = "coredns"
        mock_dep.metadata.annotations = {}
        mock_dep.spec.replicas = 2

        mock_container = MagicMock()
        mock_container.name = "coredns"
        mock_container.resources.requests = {"cpu": "2", "memory": "4Gi"}
        mock_dep.spec.template.spec.containers = [mock_container]

        mock_dep_list = MagicMock()
        mock_dep_list.items = [mock_dep]
        mock_apps.list_deployment_for_all_namespaces.return_value = mock_dep_list

        results = detect_overprovisioned_k8s_workloads()
        self.assertEqual(len(results), 0)

    @patch("src.detectors.k8s_resource_optimizer.get_apps_v1_api")
    def test_skip_zero_replicas(self, mock_get_apps_api):
        mock_apps = MagicMock()
        mock_get_apps_api.return_value = mock_apps

        mock_dep = MagicMock()
        mock_dep.metadata.namespace = "default"
        mock_dep.metadata.name = "scaled-down"
        mock_dep.metadata.annotations = {}
        mock_dep.spec.replicas = 0

        mock_dep_list = MagicMock()
        mock_dep_list.items = [mock_dep]
        mock_apps.list_deployment_for_all_namespaces.return_value = mock_dep_list

        results = detect_overprovisioned_k8s_workloads()
        self.assertEqual(len(results), 0)

    @patch("src.detectors.k8s_resource_optimizer.get_apps_v1_api")
    def test_skip_opted_out_k8s_deployment(self, mock_get_apps_api):
        mock_apps = MagicMock()
        mock_get_apps_api.return_value = mock_apps

        mock_dep = MagicMock()
        mock_dep.metadata.namespace = "default"
        mock_dep.metadata.name = "optout-app"
        mock_dep.metadata.annotations = {"cost-optimizer/opt-out": "true"}
        mock_dep.spec.replicas = 2

        mock_dep_list = MagicMock()
        mock_dep_list.items = [mock_dep]
        mock_apps.list_deployment_for_all_namespaces.return_value = mock_dep_list

        results = detect_overprovisioned_k8s_workloads()
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
