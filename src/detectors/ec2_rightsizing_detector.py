import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client, get_target_regions
from src.utils.logger import get_logger
from src.detectors.ec2_detector import EC2_HOURLY_PRICING

logger = get_logger(__name__)

# Standard recommended downsize mapping for common instance families
DOWNSIZE_MAP: Dict[str, str] = {
    "m5.2xlarge": "m5.large",
    "m5.xlarge": "m5.large",
    "c5.2xlarge": "c5.large",
    "c5.xlarge": "c5.large",
    "r5.2xlarge": "r5.large",
    "r5.xlarge": "r5.large",
    "t3.2xlarge": "t3.large",
    "t3.xlarge": "t3.medium",
    "t3.large": "t3.small",
    "t3.medium": "t3.micro",
    "t2.large": "t2.small",
    "t2.medium": "t2.micro",
}


def get_rightsizing_target(
    current_type: str, max_cpu: float
) -> Optional[Tuple[str, float]]:
    """
    Determines recommended target instance type and monthly savings delta.
    """
    recommended_type = DOWNSIZE_MAP.get(current_type)
    if not recommended_type:
        return None

    current_price = EC2_HOURLY_PRICING.get(current_type, 0.10)
    target_price = EC2_HOURLY_PRICING.get(recommended_type, 0.05)

    monthly_delta = round((current_price - target_price) * 24 * 30, 2)
    if monthly_delta > 0:
        return recommended_type, monthly_delta
    return None


def get_instance_max_cpu(
    cw_client, instance_id: str, days: int
) -> Optional[float]:
    """
    Fetches the maximum CPU utilization recorded over the observation window.
    """
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    try:
        response = cw_client.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName="CPUUtilization",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=["Maximum"],
        )
        datapoints = response.get("Datapoints", [])
        if not datapoints:
            return None
        return max(dp.get("Maximum", 0.0) for dp in datapoints)
    except ClientError as e:
        logger.error(
            f"Failed to query max CPU for instance {instance_id}: {e}"
        )
        return None


def detect_overprovisioned_ec2_instances() -> List[Dict]:
    """
    Identifies running EC2 instances whose peak CPU remains below threshold
    (default 20%) over 7 days, indicating opportunities for downsizing.
    Excludes instances with opt-out tag: CostOptimizerOptOut=true.
    Supports multi-region scanning.
    """
    logger.info("Starting EC2 rightsizing / overprovisioning analysis...")

    max_cpu_threshold = float(os.environ.get("RIGHTSIZING_CPU_MAX", 20.0))
    observation_days = int(os.environ.get("RIGHTSIZING_OBSERVATION_DAYS", 7))
    recommendations: List[Dict] = []
    target_regions = get_target_regions()

    for region in target_regions:
        logger.info(f"Analyzing EC2 rightsizing in region: {region}")
        ec2_client = get_aws_client("ec2", region_name=region)
        cw_client = get_aws_client("cloudwatch", region_name=region)

        try:
            paginator = ec2_client.get_paginator("describe_instances")
            filters = [{"Name": "instance-state-name", "Values": ["running"]}]
            pages = paginator.paginate(Filters=filters)

            for page in pages:
                for reservation in page.get("Reservations", []):
                    for inst in reservation.get("Instances", []):
                        instance_id = inst.get("InstanceId")
                        instance_type = inst.get("InstanceType")
                        tags = inst.get("Tags", [])

                        tag_dict = {t["Key"]: t["Value"] for t in tags}
                        if tag_dict.get("CostOptimizerOptOut") == "true":
                            continue

                        name = tag_dict.get("Name", f"ec2-{instance_id}")

                        peak_cpu = get_instance_max_cpu(
                            cw_client, instance_id, observation_days
                        )

                        # If peak CPU is measured and below threshold
                        if (
                            peak_cpu is not None
                            and peak_cpu < max_cpu_threshold
                        ):
                            rightsizing = get_rightsizing_target(
                                instance_type, peak_cpu
                            )
                            if rightsizing:
                                rec_type, delta_savings = rightsizing
                                logger.info(
                                    f"[{region}] Rightsizing: {instance_id}, "
                                    f"{instance_type} -> {rec_type}, "
                                    f"Peak={peak_cpu:.1f}%, "
                                    f"Savings=${delta_savings}/mo"
                                )

                                recommendations.append({
                                    "resource_id": instance_id,
                                    "resource_type": "EC2Rightsizing",
                                    "name": name,
                                    "details": {
                                        "region": region,
                                        "current_type": instance_type,
                                        "recommended_type": rec_type,
                                        "peak_cpu_percent": round(peak_cpu, 1),
                                        "observation_days": observation_days,
                                    },
                                    "estimated_monthly_savings": delta_savings,
                                    "opt_out_tag": False,
                                })

        except ClientError as e:
            logger.error(
                f"Error analyzing rightsizing in {region}: {e}"
            )
            continue

    logger.info(
        f"Rightsizing scan completed. Found {len(recommendations)} "
        f"overprovisioned instances across targeted regions."
    )
    return recommendations
