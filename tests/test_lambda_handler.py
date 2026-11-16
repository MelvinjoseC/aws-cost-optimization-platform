import importlib
import os
import unittest
from unittest.mock import MagicMock, patch

lambda_handler_mod = importlib.import_module("lambda.handler")
main_handler = lambda_handler_mod.main_handler
handle_restore_action = lambda_handler_mod.handle_restore_action


class TestLambdaHandler(unittest.TestCase):
    def setUp(self):
        os.environ["AWS_REGIONS"] = "us-east-1"
        os.environ["DRY_RUN"] = "true"

    def test_handle_restore_action(self):
        with patch.object(lambda_handler_mod, "restore_ec2_instances", return_value=["i-1"]), \
             patch.object(lambda_handler_mod, "restore_rds_instances", return_value=["db-1"]), \
             patch.object(lambda_handler_mod, "restore_k8s_deployments", return_value=["dep-1"]):

            response = handle_restore_action({"action": "restore"})
            self.assertEqual(response["statusCode"], 200)
            self.assertEqual(response["body"]["action"], "restore")
            self.assertEqual(response["body"]["restored_resources"]["ec2"], ["i-1"])

    def test_main_handler_optimize_dry_run(self):
        with patch.object(
            lambda_handler_mod,
            "generate_reports",
            return_value={
                "total_savings": 150.0,
                "s3_html_url": "https://s3.amazonaws.com/report.html",
                "s3_json_url": "https://s3.amazonaws.com/report.json",
            },
        ), \
        patch.object(lambda_handler_mod, "publish_finops_metrics"), \
        patch.object(lambda_handler_mod, "send_sns_notification"), \
        patch.object(lambda_handler_mod, "send_slack_notification"), \
        patch.object(lambda_handler_mod, "detect_idle_ec2_instances", return_value=[]), \
        patch.object(lambda_handler_mod, "detect_idle_rds_instances", return_value=[]), \
        patch.object(lambda_handler_mod, "detect_unattached_ebs_volumes", return_value=[]), \
        patch.object(lambda_handler_mod, "detect_unused_eips", return_value=[]), \
        patch.object(lambda_handler_mod, "detect_idle_k8s_deployments", return_value=[]), \
        patch.object(lambda_handler_mod, "detect_idle_elb_instances", return_value=[]), \
        patch.object(lambda_handler_mod, "detect_stale_ebs_snapshots", return_value=[]), \
        patch.object(lambda_handler_mod, "detect_idle_nat_gateways", return_value=[]), \
        patch.object(lambda_handler_mod, "detect_idle_elasticache_clusters", return_value=[]), \
        patch.object(lambda_handler_mod, "detect_idle_dynamodb_tables", return_value=[]), \
        patch.object(lambda_handler_mod, "detect_idle_or_untiered_efs", return_value=[]), \
        patch.object(lambda_handler_mod, "detect_unexpired_or_abandoned_log_groups", return_value=[]):

            response = main_handler({"action": "optimize", "dry_run": True}, None)
            self.assertEqual(response["statusCode"], 200)
            self.assertTrue(response["body"]["dry_run"])
            self.assertEqual(response["body"]["estimated_monthly_savings"], 150.0)


if __name__ == "__main__":
    unittest.main()
