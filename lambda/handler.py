import os
import sys

# Ensure parent directory is in sys.path so src.* imports resolve inside Lambda
_parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from src.utils.logger import get_logger, set_correlation_id  # noqa: E402
from src.utils.governance import filter_actionable_resources  # noqa: E402
from src.utils.metrics_publisher import publish_finops_metrics  # noqa: E402
from src.detectors.ec2_detector import detect_idle_ec2_instances  # noqa: E402
from src.detectors.rds_detector import detect_idle_rds_instances  # noqa: E402
from src.detectors.ebs_detector import detect_unattached_ebs_volumes  # noqa: E402
from src.detectors.eip_detector import detect_unused_eips  # noqa: E402
from src.detectors.k8s_detector import detect_idle_k8s_deployments  # noqa: E402
from src.detectors.elb_detector import detect_idle_elb_instances  # noqa: E402
from src.detectors.snapshot_detector import detect_stale_ebs_snapshots  # noqa: E402
from src.detectors.nat_gateway_detector import detect_idle_nat_gateways  # noqa: E402
from src.detectors.elasticache_detector import detect_idle_elasticache_clusters  # noqa: E402
from src.detectors.dynamodb_detector import detect_idle_dynamodb_tables  # noqa: E402
from src.detectors.efs_detector import detect_idle_or_untiered_efs  # noqa: E402
from src.detectors.cloudwatch_logs_detector import detect_unexpired_or_abandoned_log_groups  # noqa: E402

from src.actions.stop_ec2 import stop_ec2_instances  # noqa: E402
from src.actions.stop_rds import stop_rds_instances  # noqa: E402
from src.actions.scale_down import scale_down_k8s_deployments  # noqa: E402
from src.actions.delete_ebs import delete_unattached_ebs_volumes  # noqa: E402
from src.actions.release_eip import release_unused_eips  # noqa: E402
from src.actions.convert_dynamodb import convert_dynamodb_to_ondemand  # noqa: E402
from src.actions.enforce_log_retention import enforce_cloudwatch_log_retention  # noqa: E402
from src.actions.restore_ec2 import restore_ec2_instances  # noqa: E402
from src.actions.restore_rds import restore_rds_instances  # noqa: E402
from src.actions.restore_k8s import restore_k8s_deployments  # noqa: E402
from src.reports.generator import generate_reports  # noqa: E402
from src.reports.notifier import send_sns_notification  # noqa: E402
from src.reports.slack_notifier import send_slack_notification  # noqa: E402

logger = get_logger("cost-optimizer-handler")


def handle_restore_action(event: dict) -> dict:
    """Handles resource restoration workflow."""
    logger.info("Executing restore action across services...")
    restored_ec2 = restore_ec2_instances()
    restored_rds = restore_rds_instances()
    restored_k8s = restore_k8s_deployments()

    return {
        "statusCode": 200,
        "body": {
            "message": "Resource restoration finished.",
            "action": "restore",
            "restored_resources": {
                "ec2": restored_ec2,
                "rds": restored_rds,
                "kubernetes": restored_k8s,
            },
        },
    }


def main_handler(event: dict, context) -> dict:
    """
    AWS Lambda entrypoint. Supports optimize and restore actions.
    Coordinates scanning, governance filtering, actions, reports, and metrics.
    """
    req_id = getattr(context, "aws_request_id", None) if context else None
    set_correlation_id(req_id)

    action = (event or {}).get("action", "optimize").lower()
    if action == "restore":
        return handle_restore_action(event or {})

    logger.info("Starting AWS Cost Optimization Platform run...")

    # 1. Determine execution mode (Dry Run / Active Execution)
    dry_run_env = os.environ.get("DRY_RUN", "true").lower() == "true"
    if event and "dry_run" in event:
        dry_run = str(event.get("dry_run")).lower() == "true"
    elif event and "DRY_RUN" in event:
        dry_run = str(event.get("DRY_RUN")).lower() == "true"
    else:
        dry_run = dry_run_env

    os.environ["DRY_RUN"] = str(dry_run).lower()
    logger.info(f"Execution mode configured: DRY_RUN={dry_run}")

    # 2. Run Resource Detectors across all supported FinOps domains
    all_detected_resources = []
    scanners = [
        ("EC2", detect_idle_ec2_instances),
        ("RDS", detect_idle_rds_instances),
        ("EBS", detect_unattached_ebs_volumes),
        ("EIP", detect_unused_eips),
        ("K8S", detect_idle_k8s_deployments),
        ("ELB", detect_idle_elb_instances),
        ("Snapshot", detect_stale_ebs_snapshots),
        ("NATGateway", detect_idle_nat_gateways),
        ("ElastiCache", detect_idle_elasticache_clusters),
        ("DynamoDB", detect_idle_dynamodb_tables),
        ("EFS", detect_idle_or_untiered_efs),
        ("CloudWatchLogs", detect_unexpired_or_abandoned_log_groups),
    ]

    for service_name, scanner_fn in scanners:
        try:
            results = scanner_fn()
            all_detected_resources.extend(results)
        except Exception as e:
            logger.error(f"Failed to scan {service_name}: {e}")

    logger.info(
        f"Scanning complete. Total idle resources found: "
        f"{len(all_detected_resources)}"
    )

    # 3. Apply Governance Guardrails
    actionable_resources, protected_resources = filter_actionable_resources(
        all_detected_resources
    )

    # 4. Perform Remediation Actions if not dry run
    remediated_ec2 = []
    remediated_rds = []
    remediated_k8s = []
    remediated_ebs = []
    remediated_eip = []
    remediated_ddb = []
    remediated_logs = []

    if not dry_run:
        logger.info("Executing active remediation actions...")

        ec2_to_stop = [
            r for r in actionable_resources if r["resource_type"] == "EC2"
        ]
        if ec2_to_stop:
            remediated_ec2 = stop_ec2_instances(ec2_to_stop)

        rds_to_stop = [
            r for r in actionable_resources if r["resource_type"] == "RDS"
        ]
        if rds_to_stop:
            remediated_rds = stop_rds_instances(rds_to_stop)

        k8s_to_scale = [
            r for r in actionable_resources
            if r["resource_type"] == "KubernetesDeployment"
        ]
        if k8s_to_scale:
            remediated_k8s = scale_down_k8s_deployments(k8s_to_scale)

        delete_ebs_flag = (
            os.environ.get("DELETE_UNUSED_EBS", "false").lower() == "true"
        )
        ebs_to_del = [
            r for r in actionable_resources if r["resource_type"] == "EBS"
        ]
        if delete_ebs_flag and ebs_to_del:
            remediated_ebs = delete_unattached_ebs_volumes(ebs_to_del)

        release_eip_flag = (
            os.environ.get("RELEASE_UNUSED_EIP", "false").lower() == "true"
        )
        eip_to_rel = [
            r for r in actionable_resources if r["resource_type"] == "EIP"
        ]
        if release_eip_flag and eip_to_rel:
            remediated_eip = release_unused_eips(eip_to_rel)

        ddb_to_convert = [
            r for r in actionable_resources if r["resource_type"] == "DynamoDB"
        ]
        if ddb_to_convert:
            remediated_ddb = convert_dynamodb_to_ondemand(ddb_to_convert)

        logs_to_remediate = [
            r for r in actionable_resources if r["resource_type"] == "CloudWatchLogs"
        ]
        if logs_to_remediate:
            remediated_logs = enforce_cloudwatch_log_retention(logs_to_remediate)
    else:
        logger.info("Dry-run mode is active. No remediation executed.")

    # 5. Generate Savings Reports
    report_summary = {}
    try:
        report_summary = generate_reports(
            all_detected_resources, dry_run=dry_run
        )
    except Exception as e:
        logger.error(f"Failed to generate reports: {e}")

    # 6. Publish Observability Metrics to CloudWatch
    remediated_counts = {
        "ec2": len(remediated_ec2),
        "rds": len(remediated_rds),
        "k8s": len(remediated_k8s),
        "ebs": len(remediated_ebs),
        "eip": len(remediated_eip),
        "dynamodb": len(remediated_ddb),
        "cloudwatch_logs": len(remediated_logs),
    }
    publish_finops_metrics(
        detected_resources=all_detected_resources,
        remediated_counts=remediated_counts,
        total_savings=report_summary.get("total_savings", 0.0),
        dry_run=dry_run,
    )

    # 7. Send Notifications (SNS and Slack)
    if report_summary:
        try:
            send_sns_notification(report_summary, dry_run=dry_run)
        except Exception as e:
            logger.error(f"Failed to send SNS: {e}")

        try:
            send_slack_notification(report_summary, dry_run=dry_run)
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")

    total_savings = report_summary.get("total_savings", 0.0)
    return {
        "statusCode": 200,
        "body": {
            "message": "AWS Cost Optimization execution finished.",
            "dry_run": dry_run,
            "detected_resources_count": len(all_detected_resources),
            "protected_resources_count": len(protected_resources),
            "estimated_monthly_savings": total_savings,
            "remediated_resources": {
                "ec2": remediated_ec2,
                "rds": remediated_rds,
                "kubernetes_deployments": remediated_k8s,
                "ebs_volumes": remediated_ebs,
                "elastic_ips": remediated_eip,
                "dynamodb_tables": remediated_ddb,
                "cloudwatch_logs": remediated_logs,
            },
            "s3_html_report": report_summary.get("s3_html_url"),
            "s3_json_report": report_summary.get("s3_json_url"),
        },
    }


if __name__ == "__main__":
    os.environ["DRY_RUN"] = os.environ.get("DRY_RUN", "true")
    response = main_handler({"dry_run": True}, None)
    import pprint
    pprint.pprint(response)
