import os
import unittest
from unittest.mock import MagicMock, patch
from src.detectors.dynamodb_detector import (
    detect_idle_dynamodb_tables,
    get_table_consumed_capacity,
)


class TestDynamoDBDetector(unittest.TestCase):
    def setUp(self):
        os.environ["AWS_REGIONS"] = "us-east-1"
        os.environ["DRY_RUN"] = "true"

    @patch("src.detectors.dynamodb_detector.get_aws_client")
    def test_detect_idle_dynamodb_table_success(self, mock_get_client):
        mock_ddb = MagicMock()
        mock_cw = MagicMock()

        def client_side_effect(service, region_name=None):
            if service == "dynamodb":
                return mock_ddb
            return mock_cw

        mock_get_client.side_effect = client_side_effect

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"TableNames": ["idle-table"]}]
        mock_ddb.get_paginator.return_value = mock_paginator

        mock_ddb.describe_table.return_value = {
            "Table": {
                "TableName": "idle-table",
                "TableArn": "arn:aws:dynamodb:us-east-1:123456789012:table/idle-table",
                "BillingModeSummary": {"BillingMode": "PROVISIONED"},
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 10,
                    "WriteCapacityUnits": 10,
                },
                "ItemCount": 100,
                "TableSizeBytes": 1024,
            }
        }
        mock_ddb.list_tags_of_resource.return_value = {"Tags": [{"Key": "env", "Value": "dev"}]}

        mock_cw.get_metric_statistics.return_value = {"Datapoints": []}

        results = detect_idle_dynamodb_tables()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["resource_id"], "idle-table")
        self.assertEqual(results[0]["resource_type"], "DynamoDB")
        self.assertGreater(results[0]["estimated_monthly_savings"], 0)

    @patch("src.detectors.dynamodb_detector.get_aws_client")
    def test_skip_pay_per_request_dynamodb_table(self, mock_get_client):
        mock_ddb = MagicMock()
        mock_cw = MagicMock()
        mock_get_client.side_effect = lambda s, region_name=None: mock_ddb if s == "dynamodb" else mock_cw

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"TableNames": ["ondemand-table"]}]
        mock_ddb.get_paginator.return_value = mock_paginator

        mock_ddb.describe_table.return_value = {
            "Table": {
                "TableName": "ondemand-table",
                "TableArn": "arn:aws:dynamodb:us-east-1:123456789012:table/ondemand-table",
                "BillingModeSummary": {"BillingMode": "PAY_PER_REQUEST"},
            }
        }

        results = detect_idle_dynamodb_tables()
        self.assertEqual(len(results), 0)

    @patch("src.detectors.dynamodb_detector.get_aws_client")
    def test_skip_opted_out_dynamodb_table(self, mock_get_client):
        mock_ddb = MagicMock()
        mock_cw = MagicMock()
        mock_get_client.side_effect = lambda s, region_name=None: mock_ddb if s == "dynamodb" else mock_cw

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"TableNames": ["optout-table"]}]
        mock_ddb.get_paginator.return_value = mock_paginator

        mock_ddb.describe_table.return_value = {
            "Table": {
                "TableName": "optout-table",
                "TableArn": "arn:aws:dynamodb:us-east-1:123456789012:table/optout-table",
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5,
                },
            }
        }
        mock_ddb.list_tags_of_resource.return_value = {
            "Tags": [{"Key": "CostOptimizerOptOut", "Value": "true"}]
        }

        results = detect_idle_dynamodb_tables()
        self.assertEqual(len(results), 0)

    @patch("src.detectors.dynamodb_detector.get_aws_client")
    def test_skip_active_dynamodb_table(self, mock_get_client):
        mock_ddb = MagicMock()
        mock_cw = MagicMock()
        mock_get_client.side_effect = lambda s, region_name=None: mock_ddb if s == "dynamodb" else mock_cw

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [{"TableNames": ["active-table"]}]
        mock_ddb.get_paginator.return_value = mock_paginator

        mock_ddb.describe_table.return_value = {
            "Table": {
                "TableName": "active-table",
                "TableArn": "arn:aws:dynamodb:us-east-1:123456789012:table/active-table",
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5,
                },
            }
        }
        mock_ddb.list_tags_of_resource.return_value = {"Tags": []}

        # Active capacity consumed
        mock_cw.get_metric_statistics.return_value = {"Datapoints": [{"Sum": 150.0}]}

        results = detect_idle_dynamodb_tables()
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
