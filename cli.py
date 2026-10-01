import argparse
import os
from typing import List

from src.utils.logger import get_logger, set_correlation_id
from src.detectors.ec2_detector import detect_idle_ec2_instances
from src.detectors.rds_detector import detect_idle_rds_instances
from src.detectors.ebs_detector import detect_unattached_ebs_volumes
from src.detectors.eip_detector import detect_unused_eips
from src.detectors.elb_detector import detect_idle_elb_instances
from src.detectors.k8s_detector import detect_idle_k8s_deployments
from src.detectors.snapshot_detector import detect_stale_ebs_snapshots
from src.detectors.nat_gateway_detector import detect_idle_nat_gateways
from src.detectors.elasticache_detector import detect_idle_elasticache_clusters
from src.actions.stop_ec2 import stop_ec2_instances
from src.actions.stop_rds import stop_rds_instances
from src.actions.scale_down import scale_down_k8s_deployments
from src.actions.delete_ebs import delete_unattached_ebs_volumes
from src.actions.release_eip import release_unused_eips
from src.actions.restore_ec2 import restore_ec2_instances
from src.actions.restore_rds import restore_rds_instances
from src.actions.restore_k8s import restore_k8s_deployments
from src.reports.generator import generate_reports

logger = get_logger("cost-optimizer-cli")


def print_ascii_table(resources: List[dict]):
    """Renders an ASCII table of detected resources to stdout."""
    print("\n" + "=" * 78)
    header = (
        f"{'TYPE':<14} | {'NAME / ID':<26} | {'SAVINGS/MO':<12} | {'REGION'}"
    )
    print(header)
    print("-" * 78)
    for r in resources:
        rtype = r.get("resource_type", "")[:12]
        name = (r.get("name") or r.get("resource_id", ""))[:24]
        savings = f"${r.get('estimated_monthly_savings', 0):.2f}"
        region = r.get("details", {}).get("region", "global")
        print(f"{rtype:<14} | {name:<26} | {savings:<12} | {region}")
    print("=" * 78 + "\n")


def build_parser() -> argparse.ArgumentParser:
    """Builds CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="AWS Cost Optimization Platform CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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
    return parser


def main():
    """Main CLI entrypoint."""
    set_correlation_id()
    parser = build_parser()
    args = parser.parse_args()

    if args.regions:
        os.environ["AWS_REGIONS"] = args.regions

    dry_run = args.dry_run
    os.environ["DRY_RUN"] = str(dry_run).lower()

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
        return

    # Scan mode
    detected = []
    print("[*] Scanning resources across services...")
    for scanner in [
        detect_idle_ec2_instances,
        detect_idle_rds_instances,
        detect_unattached_ebs_volumes,
        detect_unused_eips,
        detect_idle_elb_instances,
        detect_idle_k8s_deployments,
        detect_stale_ebs_snapshots,
        detect_idle_nat_gateways,
        detect_idle_elasticache_clusters,
    ]:
        try:
            detected.extend(scanner())
        except Exception as e:
            logger.error(f"Detector error in {scanner.__name__}: {e}")

    print_ascii_table(detected)
    total_savings = sum(
        r.get("estimated_monthly_savings", 0) for r in detected
    )
    print(f"[+] Total Resources: {len(detected)}")
    print(f"[+] Potential Monthly Savings: ${total_savings:.2f}")

    if args.action == "remediate" and not dry_run:
        print("[*] Executing remediation...")
        ec2_res = [r for r in detected if r["resource_type"] == "EC2"]
        rds_res = [r for r in detected if r["resource_type"] == "RDS"]
        ebs_res = [r for r in detected if r["resource_type"] == "EBS"]
        eip_res = [r for r in detected if r["resource_type"] == "EIP"]
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
        if k8s_res:
            scale_down_k8s_deployments(k8s_res)

    report_summary = generate_reports(detected, dry_run=dry_run)
    print(f"[+] Reports generated: {report_summary.get('report_date')}")


if __name__ == "__main__":
    main()
