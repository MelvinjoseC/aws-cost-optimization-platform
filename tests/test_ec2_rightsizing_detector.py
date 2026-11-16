import os
import unittest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
from src.detectors.ec2_rightsizing_detector import (
    get_rightsizing_target,
    get_instance_max_cpu,
    detect_overprovisioned_ec2_instances,
)


class TestEC2RightsizingDetector(unittest.TestCase):
    def setUp(self):
        os.environ["AWS_REGIONS"] = "us-east-1"
        os.environ["RIGHTSIZING_CPU_MAX"] = "20.0"

    def test_get_rightsizing_target_valid(self):
        result = get_rightsizing_target("m5.2xlarge", 10.0)
        self.assertIsNotNone(result)
        rec_type, delta_savings = result
        self.assertEqual(rec_type, "m5.large")
        self.assertGreater(delta_savings, 0)

    def test_get_rightsizing_target_unknown_type(self):
        result = get_rightsizing_target("unknown.metal", 5.0)
        self.assertIsNone(result)

    def test_get_instance_max_cpu_success(self):
        mock_cw = MagicMock()
        mock_cw.get_metric_statistics.return_value = {
            "Datapoints": [{"Maximum": 12.5}, {"Maximum": 18.2}]
        }
        max_cpu = get_instance_max_cpu(mock_cw, "i-12345", 7)
        self.assertEqual(max_cpu, 18.2)

    def test_get_instance_max_cpu_empty(self):
        mock_cw = MagicMock()
        mock_cw.get_metric_statistics.return_value = {"Datapoints": []}
        max_cpu = get_instance_max_cpu(mock_cw, "i-12345", 7)
        self.assertIsNone(max_cpu)

    def test_get_instance_max_cpu_client_error(self):
        mock_cw = MagicMock()
        mock_cw.get_metric_statistics.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Denied"}},
            "GetMetricStatistics",
        )
        max_cpu = get_instance_max_cpu(mock_cw, "i-12345", 7)
        self.assertIsNone(max_cpu)

    @patch("src.detectors.ec2_rightsizing_detector.get_aws_client")
    def test_detect_overprovisioned_ec2_instances_success(self, mock_get_client):
        mock_ec2 = MagicMock()
        mock_cw = MagicMock()
        mock_get_client.side_effect = lambda s, region_name=None: mock_ec2 if s == "ec2" else mock_cw

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-overprov",
                                "InstanceType": "m5.xlarge",
                                "Tags": [{"Key": "Name", "Value": "api-worker"}],
                            }
                        ]
                    }
                ]
            }
        ]
        mock_ec2.get_paginator.return_value = mock_paginator

        # Peak CPU is 12% (below 20% threshold)
        mock_cw.get_metric_statistics.return_value = {
            "Datapoints": [{"Maximum": 12.0}]
        }

        results = detect_overprovisioned_ec2_instances()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["resource_id"], "i-overprov")
        self.assertEqual(results[0]["resource_type"], "EC2Rightsizing")
        self.assertEqual(results[0]["details"]["recommended_type"], "m5.large")
        self.assertGreater(results[0]["estimated_monthly_savings"], 0)

    @patch("src.detectors.ec2_rightsizing_detector.get_aws_client")
    def test_detect_skip_high_cpu_instance(self, mock_get_client):
        mock_ec2 = MagicMock()
        mock_cw = MagicMock()
        mock_get_client.side_effect = lambda s, region_name=None: mock_ec2 if s == "ec2" else mock_cw

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-busy",
                                "InstanceType": "m5.xlarge",
                                "Tags": [],
                            }
                        ]
                    }
                ]
            }
        ]
        mock_ec2.get_paginator.return_value = mock_paginator

        # Peak CPU is 75% (well above 20% threshold)
        mock_cw.get_metric_statistics.return_value = {
            "Datapoints": [{"Maximum": 75.0}]
        }

        results = detect_overprovisioned_ec2_instances()
        self.assertEqual(len(results), 0)

    @patch("src.detectors.ec2_rightsizing_detector.get_aws_client")
    def test_detect_skip_opted_out_instance(self, mock_get_client):
        mock_ec2 = MagicMock()
        mock_cw = MagicMock()
        mock_get_client.side_effect = lambda s, region_name=None: mock_ec2 if s == "ec2" else mock_cw

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-optout",
                                "InstanceType": "m5.xlarge",
                                "Tags": [{"Key": "CostOptimizerOptOut", "Value": "true"}],
                            }
                        ]
                    }
                ]
            }
        ]
        mock_ec2.get_paginator.return_value = mock_paginator

        results = detect_overprovisioned_ec2_instances()
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
