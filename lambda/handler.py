import os
import sys

# Ensure the parent directory is in python path so that src.* imports work inside Lambda
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.logger import get_logger
from src.detectors.ec2_detector import detect_idle_ec2_instances
from src.detectors.rds_detector import detect_idle_rds_instances
from src.detectors.ebs_detector import detect_unattached_ebs_volumes
from src.detectors.eip_detector import detect_unused_eips
from src.detectors.k8s_detector import detect_idle_k8s_deployments
from src.actions.stop_ec2 import stop_ec2_instances
from src.actions.stop_rds import stop_rds_instances
from src.actions.scale_down import scale_down_k8s_deployments
from src.reports.generator import generate_reports
from src.reports.notifier import send_sns_notification

logger = get_logger("cost-optimizer-handler")


def main_handler(event: dict, context) -> dict:
    """
    AWS Lambda entrypoint. Coordinates scanning, actions, report generation, and notifications.
    """
    logger.info("Starting AWS Cost Optimization Platform run...")
    
    # 1. Determine execution mode (Dry Run / Active Execution)
    # Event parameter overrides the DRY_RUN environment variable
    dry_run_env = os.environ.get("DRY_RUN", "true").lower() == "true"
    
    if event and 'dry_run' in event:
        dry_run = str(event.get('dry_run')).lower() == 'true'
        logger.info(f"Dry-run mode overridden by event payload: {dry_run}")
    elif event and 'DRY_RUN' in event:
        dry_run = str(event.get('DRY_RUN')).lower() == 'true'
        logger.info(f"Dry-run mode overridden by event payload: {dry_run}")
    else:
        dry_run = dry_run_env
        logger.info(f"Dry-run mode loaded from environment: {dry_run}")
        
    # Sync environmental variable so child functions inherit overridden event values
    os.environ["DRY_RUN"] = str(dry_run).lower()

    # 2. Run Resource Detectors
    all_detected_resources = []
    
    # EC2
    try:
        ec2_resources = detect_idle_ec2_instances()
        all_detected_resources.extend(ec2_resources)
    except Exception as e:
        logger.error(f"Failed to scan EC2: {e}")
        ec2_resources = []
        
    # RDS
    try:
        rds_resources = detect_idle_rds_instances()
        all_detected_resources.extend(rds_resources)
    except Exception as e:
        logger.error(f"Failed to scan RDS: {e}")
        rds_resources = []
        
    # EBS
    try:
        ebs_resources = detect_unattached_ebs_volumes()
        all_detected_resources.extend(ebs_resources)
    except Exception as e:
        logger.error(f"Failed to scan EBS: {e}")
        
    # Elastic IPs
    try:
        eip_resources = detect_unused_eips()
        all_detected_resources.extend(eip_resources)
    except Exception as e:
        logger.error(f"Failed to scan Elastic IPs: {e}")
        
    # Kubernetes Deployments
    try:
        k8s_resources = detect_idle_k8s_deployments()
        all_detected_resources.extend(k8s_resources)
    except Exception as e:
        logger.error(f"Failed to scan Kubernetes: {e}")
        k8s_resources = []

    logger.info(f"Scanning complete. Total idle resources found: {len(all_detected_resources)}")

    # 3. Perform Actions if not dry run
    remediated_ec2 = []
    remediated_rds = []
    remediated_k8s = []
    
    if not dry_run:
        logger.info("Executing active scale-down/stopping remediation actions...")
        
        # Stop EC2 instances
        ec2_ids_to_stop = [res['resource_id'] for res in ec2_resources]
        if ec2_ids_to_stop:
            remediated_ec2 = stop_ec2_instances(ec2_ids_to_stop)
            
        # Snapshot & Stop RDS instances
        if rds_resources:
            remediated_rds = stop_rds_instances(rds_resources)
            
        # Scale-down Kubernetes deployments
        if k8s_resources:
            remediated_k8s = scale_down_k8s_deployments(k8s_resources)
    else:
        logger.info("Dry-run mode is enabled. No remediation actions will be executed.")

    # 4. Generate Savings Reports
    report_summary = {}
    try:
        report_summary = generate_reports(all_detected_resources, dry_run=dry_run)
    except Exception as e:
        logger.error(f"Failed to generate reports: {e}")

    # 5. Send SNS Summary Notification
    if report_summary:
        try:
            send_sns_notification(report_summary, dry_run=dry_run)
        except Exception as e:
            logger.error(f"Failed to send notifications: {e}")

    # 6. Construct Lambda Response
    return {
        "statusCode": 200,
        "body": {
            "message": "AWS Cost Optimization execution finished successfully.",
            "dry_run": dry_run,
            "detected_resources_count": len(all_detected_resources),
            "estimated_monthly_savings": report_summary.get("total_savings", 0.0),
            "remediated_resources": {
                "ec2": remediated_ec2,
                "rds": remediated_rds,
                "kubernetes_deployments": remediated_k8s
            },
            "s3_html_report": report_summary.get("s3_html_url"),
            "s3_json_report": report_summary.get("s3_json_url")
        }
    }


if __name__ == "__main__":
    # Local CLI testing fallback
    os.environ["DRY_RUN"] = os.environ.get("DRY_RUN", "true")
    # Simulate basic event
    response = main_handler({"dry_run": True}, None)
    print("Execution output:")
    import pprint
    pprint.pprint(response)
