import argparse
import csv
import json
import os
import sys
from typing import Dict, List

from src.utils.logger import get_logger, set_correlation_id
from src.detectors.ec2_detector import detect_idle_ec2_instances
from src.detectors.ec2_rightsizing_detector import detect_overprovisioned_ec2_instances
from src.detectors.rds_detector import detect_idle_rds_instances
from src.detectors.ebs_detector import detect_unattached_ebs_volumes
from src.detectors.eip_detector import detect_unused_eips
from src.detectors.elb_detector import detect_idle_elb_instances
from src.detectors.k8s_detector import detect_idle_k8s_deployments
from src.detectors.k8s_resource_optimizer import detect_overprovisioned_k8s_workloads
from src.detectors.snapshot_detector import detect_stale_ebs_snapshots
from src.detectors.nat_gateway_detector import detect_idle_nat_gateways
from src.detectors.elasticache_detector import detect_idle_elasticache_clusters
from src.detectors.dynamodb_detector import detect_idle_dynamodb_tables
from src.detectors.efs_detector import detect_idle_or_untiered_efs
from src.detectors.cloudwatch_logs_detector import detect_unexpired_or_abandoned_log_groups

from src.actions.stop_ec2 import stop_ec2_instances
from src.actions.stop_rds import stop_rds_instances
from src.actions.scale_down import scale_down_k8s_deployments
from src.actions.delete_ebs import delete_unattached_ebs_volumes
from src.actions.release_eip import release_unused_eips
from src.actions.convert_dynamodb import convert_dynamodb_to_ondemand
from src.actions.enforce_log_retention import enforce_cloudwatch_log_retention
from src.actions.restore_ec2 import restore_ec2_instances
from src.actions.restore_rds import restore_rds_instances
from src.actions.restore_k8s import restore_k8s_deployments
from src.reports.generator import generate_reports

__version__ = "2.5.0"
logger = get_logger("cost-optimizer-cli")

AVAILABLE_SERVICES = {
    "ec2": [detect_idle_ec2_instances],
    "rds": [detect_idle_rds_instances],
    "ebs": [detect_unattached_ebs_volumes],
    "eip": [detect_unused_eips],
    "elb": [detect_idle_elb_instances],
    "k8s": [detect_idle_k8s_deployments],
    "snapshot": [detect_stale_ebs_snapshots],
    "nat": [detect_idle_nat_gateways],
    "elasticache": [detect_idle_elasticache_clusters],
    "dynamodb": [detect_idle_dynamodb_tables],
    "efs": [detect_idle_or_untiered_efs],
    "logs": [detect_unexpired_or_abandoned_log_groups],
}


def print_ascii_table(resources: List[dict]):
    """Renders an ASCII table of detected resources to stdout."""
    print("\n" + "=" * 82)
    header = (
        f"{'TYPE':<16} | {'NAME / ID':<26} | {'SAVINGS/MO':<12} | {'REGION'}"
    )
    print(header)
    print("-" * 82)
    for r in resources:
        rtype = str(r.get("resource_type", ""))[:14]
        name = str(r.get("name") or r.get("resource_id", ""))[:24]
        savings = f"${float(r.get('estimated_monthly_savings', 0)):.2f}"
        region = r.get("details", {}).get("region", "global")
        print(f"{rtype:<16} | {name:<26} | {savings:<12} | {region}")
    print("=" * 82 + "\n")


def export_resources(resources: List[dict], output_format: str, output_path: str = None):
    """Exports detected resources to table, JSON, or CSV."""
    if output_format == "json":
        data = json.dumps(resources, indent=2, default=str)
        if output_path:
            with open(output_path, "w") as f:
                f.write(data)
            print(f"[+] Output written to {output_path}")
        else:
            print(data)
    elif output_format == "csv":
        fieldnames = ["resource_type", "resource_id", "name", "estimated_monthly_savings", "region"]
        rows = []
        for r in resources:
            rows.append({
                "resource_type": r.get("resource_type"),
                "resource_id": r.get("resource_id"),
                "name": r.get("name"),
                "estimated_monthly_savings": r.get("estimated_monthly_savings", 0),
                "region": r.get("details", {}).get("region", "global"),
            })
        if output_path:
            with open(output_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            print(f"[+] Output written to {output_path}")
        else:
            writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        print_ascii_table(resources)


def build_parser() -> argparse.ArgumentParser:
    """Builds CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="AWS Cost Optimization Platform CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--action",
        choices=["scan", "remediate", "restore"],
        default="scan",
        help="Action: scan for idle resources, remediate, or restore",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Simulate execution without modifying resources",
    )
    parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Actively stop, release, or delete detected resources",
    )
    parser.add_argument(
        "--regions",
        type=str,
        default="",
        help="Comma-separated target AWS regions (e.g. us-east-1,us-west-2)",
    )
    parser.add_argument(
        "--services",
        type=str,
        default="",
        help="Comma-separated services to scan (e.g. ec2,rds,ebs,dynamodb,efs,logs)",
    )
    parser.add_argument(
        "--include-rightsizing",
        action="store_true",
        default=False,
        help="Include EC2 and Kubernetes container rightsizing detectors in scan",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output display or export format",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default="",
        help="Optional file path to write results",
    )
    return parser


def main(argv: List[str] = None):
    """Main CLI entrypoint."""
    set_correlation_id()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.regions:
        os.environ["AWS_REGIONS"] = args.regions

    dry_run = args.dry_run
    os.environ["DRY_RUN"] = str(dry_run).lower()

    if args.format == "table":
        print("[*] AWS Cost Optimization Platform CLI")
        print(f"[*] Action: {args.action.upper()} | Dry Run: {dry_run}")

    if args.action == "restore":
        print("[*] Executing restoration of previously stopped resources...")
        restored_ec2 = restore_ec2_instances()
        restored_rds = restore_rds_instances()
        restored_k8s = restore_k8s_deployments()
        print(f"[+] Restored EC2: {len(restored_ec2)}")
        print(f"[+] Restored RDS: {len(restored_rds)}")
        print(f"[+] Restored K8s: {len(restored_k8s)}")
        return 0

    # Determine detectors to run based on --services filter
    detectors = []
    if args.services:
        requested = [s.strip().lower() for s in args.services.split(",") if s.strip()]
        for req in requested:
            if req in AVAILABLE_SERVICES:
                detectors.extend(AVAILABLE_SERVICES[req])
            else:
                logger.warning(f"Unknown service '{req}' specified.")
    else:
        for funcs in AVAILABLE_SERVICES.values():
            detectors.extend(funcs)

    if args.include_rightsizing:
        detectors.extend([
            detect_overprovisioned_ec2_instances,
            detect_overprovisioned_k8s_workloads,
        ])

    detected = []
    if args.format == "table":
        print(f"[*] Scanning {len(detectors)} resource detectors across regions...")

    for scanner in detectors:
        try:
            detected.extend(scanner())
        except Exception as e:
            logger.error(f"Detector error in {scanner.__name__}: {e}")

    export_resources(detected, args.format, args.output_file or None)

    total_savings = sum(
        float(r.get("estimated_monthly_savings", 0)) for r in detected
    )
    if args.format == "table":
        print(f"[+] Total Resources: {len(detected)}")
        print(f"[+] Potential Monthly Savings: ${total_savings:.2f}")

    if args.action == "remediate" and not dry_run:
        print("[*] Executing active remediation...")
        ec2_res = [r for r in detected if r["resource_type"] == "EC2"]
        rds_res = [r for r in detected if r["resource_type"] == "RDS"]
        ebs_res = [r for r in detected if r["resource_type"] == "EBS"]
        eip_res = [r for r in detected if r["resource_type"] == "EIP"]
        ddb_res = [r for r in detected if r["resource_type"] == "DynamoDB"]
        logs_res = [r for r in detected if r["resource_type"] == "CloudWatchLogs"]
        k8s_res = [
            r for r in detected if r["resource_type"] == "KubernetesDeployment"
        ]

        if ec2_res:
            stop_ec2_instances(ec2_res)
        if rds_res:
            stop_rds_instances(rds_res)
        if ebs_res:
            delete_unattached_ebs_volumes(ebs_res)
        if eip_res:
            release_unused_eips(eip_res)
        if ddb_res:
            convert_dynamodb_to_ondemand(ddb_res)
        if logs_res:
            enforce_cloudwatch_log_retention(logs_res)
        if k8s_res:
            scale_down_k8s_deployments(k8s_res)

    report_summary = generate_reports(detected, dry_run=dry_run)
    if args.format == "table":
        print(f"[+] Reports generated: {report_summary.get('report_date')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
