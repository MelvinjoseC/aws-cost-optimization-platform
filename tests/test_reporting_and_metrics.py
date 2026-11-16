import os
import unittest
from unittest.mock import MagicMock, patch
import urllib.error
from botocore.exceptions import ClientError
from src.reports.slack_notifier import send_slack_notification
from src.utils.metrics_publisher import publish_finops_metrics


class TestReportingAndMetrics(unittest.TestCase):
    def setUp(self):
        os.environ["ENVIRONMENT"] = "staging"

    def test_send_slack_missing_webhook(self):
        if "SLACK_WEBHOOK_URL" in os.environ:
            del os.environ["SLACK_WEBHOOK_URL"]
        result = send_slack_notification({"total_savings": 100.0}, dry_run=True)
        self.assertFalse(result)

    @patch("urllib.request.urlopen")
    def test_send_slack_success(self, mock_urlopen):
        os.environ["SLACK_WEBHOOK_URL"] = "https://hooks.slack.com/services/T00/B00/X00"
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        summary = {
            "total_savings": 250.75,
            "total_resources": 5,
            "s3_html_url": "https://s3.amazonaws.com/report.html",
            "report_date": "2026-11-16",
        }

        result = send_slack_notification(summary, dry_run=False)
        self.assertTrue(result)
        mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_send_slack_url_error(self, mock_urlopen):
        os.environ["SLACK_WEBHOOK_URL"] = "https://hooks.slack.com/services/T00/B00/X00"
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        result = send_slack_notification({"total_savings": 50.0}, dry_run=True)
        self.assertFalse(result)

    def test_publish_metrics_disabled(self):
        os.environ["ENABLE_CLOUDWATCH_METRICS"] = "false"
        result = publish_finops_metrics([], {}, 0.0, dry_run=True)
        self.assertFalse(result)

    @patch("src.utils.metrics_publisher.get_aws_client")
    def test_publish_metrics_success(self, mock_get_client):
        os.environ["ENABLE_CLOUDWATCH_METRICS"] = "true"
        mock_cw = MagicMock()
        mock_get_client.return_value = mock_cw

        resources = [
            {"resource_type": "EC2", "estimated_monthly_savings": 120.0},
            {"resource_type": "EBS", "estimated_monthly_savings": 30.0},
        ]
        remediated_counts = {"EC2": 1, "EBS": 1}

        result = publish_finops_metrics(resources, remediated_counts, 150.0, dry_run=False)
        self.assertTrue(result)
        self.assertTrue(mock_cw.put_metric_data.called)

    @patch("src.utils.metrics_publisher.get_aws_client")
    def test_publish_metrics_client_error(self, mock_get_client):
        os.environ["ENABLE_CLOUDWATCH_METRICS"] = "true"
        mock_cw = MagicMock()
        mock_get_client.return_value = mock_cw
        mock_cw.put_metric_data.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Denied"}},
            "PutMetricData",
        )

        resources = [{"resource_type": "EC2", "estimated_monthly_savings": 50.0}]
        result = publish_finops_metrics(resources, {}, 50.0, dry_run=True)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
