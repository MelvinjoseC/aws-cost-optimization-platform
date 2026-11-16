import os
import unittest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
from src.actions.restore_ec2 import find_stopped_optimizer_instances, restore_ec2_instances


class TestRestoreEC2(unittest.TestCase):
    def setUp(self):
        os.environ["AWS_REGIONS"] = "us-east-1"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

    @patch("src.actions.restore_ec2.get_aws_client")
    def test_find_stopped_optimizer_instances(self, mock_get_client):
        mock_ec2 = MagicMock()
        mock_get_client.return_value = mock_ec2

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-stopped-1",
                                "InstanceType": "t3.medium",
                            }
                        ]
                    }
                ]
            }
        ]
        mock_ec2.get_paginator.return_value = mock_paginator

        results = find_stopped_optimizer_instances(["us-east-1"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["resource_id"], "i-stopped-1")

    @patch("src.actions.restore_ec2.get_aws_client")
    def test_restore_ec2_dry_run(self, mock_get_client):
        os.environ["DRY_RUN"] = "true"
        mock_ec2 = MagicMock()
        mock_get_client.return_value = mock_ec2

        instances = [
            {
                "resource_id": "i-dry-1",
                "details": {"region": "us-east-1"},
            }
        ]

        restored = restore_ec2_instances(instances)
        self.assertEqual(restored, ["i-dry-1"])
        mock_ec2.start_instances.assert_not_called()

    @patch("src.actions.restore_ec2.get_aws_client")
    def test_restore_ec2_live_success(self, mock_get_client):
        os.environ["DRY_RUN"] = "false"
        mock_ec2 = MagicMock()
        mock_get_client.return_value = mock_ec2

        mock_ec2.start_instances.return_value = {
            "StartingInstances": [{"InstanceId": "i-live-1"}]
        }

        instances = [
            {
                "resource_id": "i-live-1",
                "details": {"region": "us-east-1"},
            }
        ]

        restored = restore_ec2_instances(instances)
        self.assertEqual(restored, ["i-live-1"])
        mock_ec2.start_instances.assert_called_once_with(InstanceIds=["i-live-1"])
        mock_ec2.create_tags.assert_called_once()

    def test_restore_ec2_empty_list(self):
        with patch("src.actions.restore_ec2.find_stopped_optimizer_instances", return_value=[]):
            restored = restore_ec2_instances(None)
            self.assertEqual(restored, [])

    @patch("src.actions.restore_ec2.get_aws_client")
    def test_restore_ec2_client_error(self, mock_get_client):
        os.environ["DRY_RUN"] = "false"
        mock_ec2 = MagicMock()
        mock_get_client.return_value = mock_ec2
        mock_ec2.start_instances.side_effect = ClientError(
            {"Error": {"Code": "InstanceLimitExceeded", "Message": "Limit exceeded"}},
            "StartInstances",
        )

        instances = ["i-error-1"]
        restored = restore_ec2_instances(instances)
        self.assertEqual(restored, [])


if __name__ == "__main__":
    unittest.main()
