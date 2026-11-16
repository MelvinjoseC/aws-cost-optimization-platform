import os
import unittest
from unittest.mock import MagicMock, patch
from src.detectors.cloudwatch_logs_detector import detect_unexpired_or_abandoned_log_groups


class TestCloudWatchLogsDetector(unittest.TestCase):
    def setUp(self):
        os.environ["AWS_REGIONS"] = "us-east-1"
        os.environ["DRY_RUN"] = "true"

    @patch("src.detectors.cloudwatch_logs_detector.get_aws_client")
    def test_detect_unexpired_log_group(self, mock_get_client):
        mock_logs = MagicMock()
        mock_get_client.return_value = mock_logs

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "logGroups": [
                    {
                        "logGroupName": "/aws/lambda/unexpired-fn",
                        "storedBytes": 10 * 1024**3,  # 10 GB
                        "retentionInDays": None,  # Never expire
                        "lastIngestionTime": 1700000000000,
                    }
                ]
            }
        ]
        mock_logs.get_paginator.return_value = mock_paginator

        results = detect_unexpired_or_abandoned_log_groups()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["resource_id"], "/aws/lambda/unexpired-fn")
        self.assertEqual(results[0]["resource_type"], "CloudWatchLogs")
        self.assertIn("Infinite retention", results[0]["details"]["issue"])
        self.assertGreater(results[0]["estimated_monthly_savings"], 0)

    @patch("src.detectors.cloudwatch_logs_detector.get_aws_client")
    def test_detect_abandoned_log_group(self, mock_get_client):
        mock_logs = MagicMock()
        mock_get_client.return_value = mock_logs

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "logGroups": [
                    {
                        "logGroupName": "/aws/ecs/abandoned-task",
                        "storedBytes": 5 * 1024**3,  # 5 GB
                        "retentionInDays": 365,
                        "lastIngestionTime": 1000000000000,  # Old timestamp
                    }
                ]
            }
        ]
        mock_logs.get_paginator.return_value = mock_paginator

        results = detect_unexpired_or_abandoned_log_groups()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["resource_id"], "/aws/ecs/abandoned-task")
        self.assertIn("Abandoned log group", results[0]["details"]["issue"])

    @patch("src.detectors.cloudwatch_logs_detector.get_aws_client")
    def test_skip_empty_log_groups(self, mock_get_client):
        mock_logs = MagicMock()
        mock_get_client.return_value = mock_logs

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "logGroups": [
                    {
                        "logGroupName": "/aws/lambda/empty-fn",
                        "storedBytes": 0,
                        "retentionInDays": None,
                    }
                ]
            }
        ]
        mock_logs.get_paginator.return_value = mock_paginator

        results = detect_unexpired_or_abandoned_log_groups()
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
