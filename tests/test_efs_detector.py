import os
import unittest
from unittest.mock import MagicMock, patch
from src.detectors.efs_detector import detect_idle_or_untiered_efs


class TestEFSDetector(unittest.TestCase):
    def setUp(self):
        os.environ["AWS_REGIONS"] = "us-east-1"
        os.environ["DRY_RUN"] = "true"

    @patch("src.detectors.efs_detector.get_aws_client")
    def test_detect_unmounted_efs(self, mock_get_client):
        mock_efs = MagicMock()
        mock_cw = MagicMock()
        mock_get_client.side_effect = lambda s, region_name=None: mock_efs if s == "efs" else mock_cw

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "FileSystems": [
                    {
                        "FileSystemId": "fs-12345678",
                        "Name": "orphaned-efs",
                        "NumberOfMountTargets": 0,
                        "SizeInBytes": {"Value": 10 * 1024**3},  # 10 GB
                        "Tags": [{"Key": "env", "Value": "staging"}],
                    }
                ]
            }
        ]
        mock_efs.get_paginator.return_value = mock_paginator

        results = detect_idle_or_untiered_efs()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["resource_id"], "fs-12345678")
        self.assertIn("Unmounted", results[0]["details"]["issue"])
        self.assertGreater(results[0]["estimated_monthly_savings"], 0)

    @patch("src.detectors.efs_detector.get_aws_client")
    def test_detect_idle_mounted_efs(self, mock_get_client):
        mock_efs = MagicMock()
        mock_cw = MagicMock()
        mock_get_client.side_effect = lambda s, region_name=None: mock_efs if s == "efs" else mock_cw

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "FileSystems": [
                    {
                        "FileSystemId": "fs-87654321",
                        "Name": "idle-efs",
                        "NumberOfMountTargets": 2,
                        "SizeInBytes": {"Value": 20 * 1024**3},  # 20 GB
                        "Tags": [],
                    }
                ]
            }
        ]
        mock_efs.get_paginator.return_value = mock_paginator
        # Zero I/O bytes
        mock_cw.get_metric_statistics.return_value = {"Datapoints": []}

        results = detect_idle_or_untiered_efs()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["resource_id"], "fs-87654321")
        self.assertIn("Zero I/O", results[0]["details"]["issue"])

    @patch("src.detectors.efs_detector.get_aws_client")
    def test_detect_untiered_efs_missing_lifecycle(self, mock_get_client):
        mock_efs = MagicMock()
        mock_cw = MagicMock()
        mock_get_client.side_effect = lambda s, region_name=None: mock_efs if s == "efs" else mock_cw

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "FileSystems": [
                    {
                        "FileSystemId": "fs-99999999",
                        "Name": "untiered-efs",
                        "NumberOfMountTargets": 2,
                        "SizeInBytes": {"Value": 50 * 1024**3},  # 50 GB
                        "Tags": [],
                    }
                ]
            }
        ]
        mock_efs.get_paginator.return_value = mock_paginator
        # Active I/O
        mock_cw.get_metric_statistics.return_value = {"Datapoints": [{"Sum": 1000000.0}]}
        # No IA rule
        mock_efs.describe_lifecycle_configuration.return_value = {"LifecyclePolicies": []}

        results = detect_idle_or_untiered_efs()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["resource_id"], "fs-99999999")
        self.assertIn("Infrequent Access", results[0]["details"]["issue"])

    @patch("src.detectors.efs_detector.get_aws_client")
    def test_skip_opted_out_efs(self, mock_get_client):
        mock_efs = MagicMock()
        mock_cw = MagicMock()
        mock_get_client.side_effect = lambda s, region_name=None: mock_efs if s == "efs" else mock_cw

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "FileSystems": [
                    {
                        "FileSystemId": "fs-protected",
                        "Name": "protected-efs",
                        "NumberOfMountTargets": 0,
                        "SizeInBytes": {"Value": 10 * 1024**3},
                        "Tags": [{"Key": "CostOptimizerOptOut", "Value": "true"}],
                    }
                ]
            }
        ]
        mock_efs.get_paginator.return_value = mock_paginator

        results = detect_idle_or_untiered_efs()
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
