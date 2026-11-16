import os
import unittest
from unittest.mock import MagicMock, patch
import cli


class TestCLI(unittest.TestCase):
    def setUp(self):
        os.environ["AWS_REGIONS"] = "us-east-1"
        os.environ["DRY_RUN"] = "true"

    def test_parser_defaults(self):
        parser = cli.build_parser()
        args = parser.parse_args([])
        self.assertEqual(args.action, "scan")
        self.assertTrue(args.dry_run)
        self.assertEqual(args.format, "table")

    def test_parser_custom_args(self):
        parser = cli.build_parser()
        args = parser.parse_args([
            "--action", "remediate",
            "--no-dry-run",
            "--regions", "us-west-2",
            "--services", "ec2,rds,dynamodb",
            "--format", "json",
            "--include-rightsizing",
        ])
        self.assertEqual(args.action, "remediate")
        self.assertFalse(args.dry_run)
        self.assertEqual(args.regions, "us-west-2")
        self.assertEqual(args.services, "ec2,rds,dynamodb")
        self.assertEqual(args.format, "json")
        self.assertTrue(args.include_rightsizing)

    @patch("cli.restore_ec2_instances")
    @patch("cli.restore_rds_instances")
    @patch("cli.restore_k8s_deployments")
    def test_main_restore_action(self, mock_k8s, mock_rds, mock_ec2):
        mock_ec2.return_value = ["i-1"]
        mock_rds.return_value = ["db-1"]
        mock_k8s.return_value = ["dep-1"]

        ret = cli.main(["--action", "restore"])
        self.assertEqual(ret, 0)
        mock_ec2.assert_called_once()
        mock_rds.assert_called_once()
        mock_k8s.assert_called_once()

    @patch("cli.get_service_detectors")
    @patch("cli.generate_reports")
    def test_main_scan_filtered_service(self, mock_reports, mock_get_detectors):
        mock_detector_func = MagicMock()
        mock_detector_func.__name__ = "mock_scanner"
        mock_detector_func.return_value = [
            {
                "resource_id": "i-test",
                "resource_type": "EC2",
                "name": "test",
                "details": {"region": "us-east-1"},
                "estimated_monthly_savings": 50.0,
            }
        ]
        mock_get_detectors.return_value = [mock_detector_func]
        mock_reports.return_value = {"report_date": "2026-11-16"}

        ret = cli.main(["--action", "scan", "--services", "ec2", "--format", "json"])
        self.assertEqual(ret, 0)
        mock_detector_func.assert_called_once()

    @patch("cli.get_service_detectors")
    @patch("cli.convert_dynamodb_to_ondemand")
    @patch("cli.generate_reports")
    def test_main_remediate_dynamodb(self, mock_reports, mock_convert_ddb, mock_get_detectors):
        mock_detector_func = MagicMock()
        mock_detector_func.__name__ = "mock_ddb_scanner"
        mock_detector_func.return_value = [
            {
                "resource_id": "idle-table",
                "resource_type": "DynamoDB",
                "name": "idle-table",
                "details": {"region": "us-east-1"},
                "estimated_monthly_savings": 25.0,
            }
        ]
        mock_get_detectors.return_value = [mock_detector_func]
        mock_reports.return_value = {"report_date": "2026-11-16"}

        ret = cli.main([
            "--action", "remediate",
            "--no-dry-run",
            "--services", "dynamodb",
        ])
        self.assertEqual(ret, 0)
        mock_convert_ddb.assert_called_once()


if __name__ == "__main__":
    unittest.main()
