import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client, get_target_regions
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Standard AWS hourly price for NAT Gateway: $0.045/hr -> ~$32.40/month base
NAT_GW_HOURLY_PRICE = 0.045
NAT_GW_MONTHLY_PRICE = round(NAT_GW_HOURLY_PRICE * 24 * 30, 2)


def is_nat_gateway_idle(
    cw_client, nat_gw_id: str, idle_hours: int
) -> bool:
    """
    Queries CloudWatch to verify if the NAT Gateway has had 0 active
    connections or 0 bytes processed during the idle period.
    """
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=idle_hours)

    try:
        response = cw_client.get_metric_statistics(
            Namespace="AWS/NATGateway",
            MetricName="ActiveConnectionCount",
            Dimensions=[{"Name": "NatGatewayId", "Value": nat_gw_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=idle_hours * 3600,
            Statistics=["Sum", "Maximum"],
        )

        datapoints = response.get("Datapoints", [])
        if not datapoints:
            return True

        max_connections = max(dp.get("Maximum", 0) for dp in datapoints)
        return max_connections == 0

    except ClientError as e:
        logger.error(
            f"Error fetching CloudWatch metrics for NAT GW {nat_gw_id}: {e}"
        )
        return False


def detect_idle_nat_gateways() -> List[Dict]:
    """
    Scans for AWS NAT Gateways with 0 active connections over idle threshold.
    Excludes NAT Gateways with opt-out tag: CostOptimizerOptOut=true.
    Supports multi-region scanning.
    """
    logger.info("Starting idle NAT Gateway detection...")

    idle_hours = int(os.environ.get("NAT_GW_IDLE_HOURS", 168))
    idle_gateways: List[Dict] = []
    target_regions = get_target_regions()

    for region in target_regions:
        logger.info(f"Scanning NAT Gateways in region: {region}")
        ec2_client = get_aws_client("ec2", region_name=region)
        cw_client = get_aws_client("cloudwatch", region_name=region)

        try:
            paginator = ec2_client.get_paginator("describe_nat_gateways")
            pages = paginator.paginate(
                Filters=[{"Name": "state", "Values": ["available"]}]
            )

            for page in pages:
                for nat in page.get("NatGateways", []):
                    nat_id = nat.get("NatGatewayId")
                    vpc_id = nat.get("VpcId")
                    subnet_id = nat.get("SubnetId")
                    tags = nat.get("Tags", [])

                    tag_dict = {t["Key"]: t["Value"] for t in tags}
                    if tag_dict.get("CostOptimizerOptOut") == "true":
                        continue

                    name = tag_dict.get("Name", f"nat-{nat_id}")

                    if is_nat_gateway_idle(cw_client, nat_id, idle_hours):
                        logger.info(
                            f"[{region}] Detected Idle NAT Gateway: "
                            f"ID={nat_id}, VPC={vpc_id}, "
                            f"Savings=${NAT_GW_MONTHLY_PRICE}/mo"
                        )

                        idle_gateways.append({
                            "resource_id": nat_id,
                            "resource_type": "NATGateway",
                            "name": name,
                            "details": {
                                "region": region,
                                "vpc_id": vpc_id,
                                "subnet_id": subnet_id,
                                "created_time": (
                                    nat.get("CreateTime").isoformat()
                                    if nat.get("CreateTime") else None
                                ),
                            },
                            "estimated_monthly_savings": NAT_GW_MONTHLY_PRICE,
                            "opt_out_tag": False,
                        })

        except ClientError as e:
            logger.error(
                f"Error describing NAT Gateways in region {region}: {e}"
            )
            continue

    logger.info(
        f"NAT Gateway scan completed. Found {len(idle_gateways)} "
        f"idle gateways across targeted regions."
    )
    return idle_gateways
