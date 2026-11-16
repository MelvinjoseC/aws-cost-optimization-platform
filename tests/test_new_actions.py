import os
import unittest
from unittest.mock import MagicMock, patch
from src.actions.convert_dynamodb import convert_dynamodb_to_ondemand
from src.actions.enforce_log_retention import enforce_cloudwatch_log_retention


class TestNewActions(unittest.TestCase):
    def setUp(self):
        os.environ["AWS_REGIONS"] = "us-east-1"

    @patch("src.actions.convert_dynamodb.get_aws_client")
    def test_convert_dynamodb_dry_run(self, mock_get_client):
        os.environ["DRY_RUN"] = "true"
        mock_ddb = MagicMock()
        mock_get_client.return_value = mock_ddb

        resources = [
            {
                "resource_id": "idle-table",
                "resource_type": "DynamoDB",
                "details": {"region": "us-east-1", "table_arn": "arn:aws:dynamodb:us-east-1:123:table/idle-table"},
                "tags": {},
            }
        ]

        converted = convert_dynamodb_to_ondemand(resources)
        self.assertEqual(len(converted), 1)
        # In dry run, update_table should NOT be called
        mock_ddb.update_table.assert_not_called()

    @patch("src.actions.convert_dynamodb.get_aws_client")
    def test_convert_dynamodb_live_execution(self, mock_get_client):
        os.environ["DRY_RUN"] = "false"
        mock_ddb = MagicMock()
        mock_get_client.return_value = mock_ddb

        resources = [
            {
                "resource_id": "idle-table",
                "resource_type": "DynamoDB",
                "details": {"region": "us-east-1", "table_arn": "arn:aws:dynamodb:us-east-1:123:table/idle-table"},
                "tags": {},
            }
        ]

        converted = convert_dynamodb_to_ondemand(resources)
        self.assertEqual(len(converted), 1)
        mock_ddb.update_table.assert_called_once_with(
            TableName="idle-table",
            BillingMode="PAY_PER_REQUEST",
        )

    @patch("src.actions.convert_dynamodb.get_aws_client")
    def test_convert_dynamodb_governance_skip(self, mock_get_client):
        os.environ["DRY_RUN"] = "false"
        mock_ddb = MagicMock()
        mock_get_client.return_value = mock_ddb

        resources = [
            {
                "resource_id": "protected-table",
                "resource_type": "DynamoDB",
                "details": {"region": "us-east-1"},
                "tags": {"CostOptimizerOptOut": "true"},
            }
        ]

        converted = convert_dynamodb_to_ondemand(resources)
        self.assertEqual(len(converted), 0)
        mock_ddb.update_table.assert_not_called()

    @patch("src.actions.enforce_log_retention.get_aws_client")
    def test_enforce_log_retention_dry_run(self, mock_get_client):
        os.environ["DRY_RUN"] = "true"
        mock_logs = MagicMock()
        mock_get_client.return_value = mock_logs

        resources = [
            {
                "resource_id": "/aws/lambda/test-log",
                "resource_type": "CloudWatchLogs",
                "details": {"region": "us-east-1"},
                "tags": {},
            }
        ]

        remediated = enforce_cloudwatch_log_retention(resources, default_retention_days=90)
        self.assertEqual(len(remediated), 1)
        mock_logs.put_retention_policy.assert_not_called()

    @patch("src.actions.enforce_log_retention.get_aws_client")
    def test_enforce_log_retention_live_execution(self, mock_get_client):
        os.environ["DRY_RUN"] = "false"
        mock_logs = MagicMock()
        mock_get_client.return_value = mock_logs

        resources = [
            {
                "resource_id": "/aws/lambda/test-log",
                "resource_type": "CloudWatchLogs",
                "details": {"region": "us-east-1"},
                "tags": {},
            }
        ]

        remediated = enforce_cloudwatch_log_retention(resources, default_retention_days=60)
        self.assertEqual(len(remediated), 1)
        mock_logs.put_retention_policy.assert_called_once_with(
            logGroupName="/aws/lambda/test-log",
            retentionInDays=90,  # cfg default
        )


if __name__ == "__main__":
    unittest.main()
