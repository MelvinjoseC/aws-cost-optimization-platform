from datetime import datetime, timedelta, timezone
import os
import boto3
import pytest
from moto import mock_aws
from src.detectors.snapshot_detector import detect_stale_ebs_snapshots
from src.detectors.nat_gateway_detector import detect_idle_nat_gateways
from src.detectors.elasticache_detector import detect_idle_elasticache_clusters
from src.utils.governance import (
    filter_actionable_resources,
    is_resource_protected,
)


@mock_aws
def test_detect_stale_ebs_snapshots():
    """Test detection of orphaned EBS snapshots older than retention."""
    ec2 = boto3.client("ec2", region_name="us-east-1")

    # Create volume and snapshot
    vol = ec2.create_volume(
        AvailabilityZone="us-east-1a", Size=15, VolumeType="gp3"
    )
    vol_id = vol["VolumeId"]
    snap = ec2.create_snapshot(VolumeId=vol_id, Description="Temporary backup")
    snap_id = snap["SnapshotId"]

    # Delete volume so snapshot becomes orphaned
    ec2.delete_volume(VolumeId=vol_id)

    # Set snapshot age threshold to 0 days for testing
    os.environ["SNAPSHOT_MAX_AGE_DAYS"] = "0"
    stale = detect_stale_ebs_snapshots()

    assert len(stale) >= 1
    target = next((s for s in stale if s["resource_id"] == snap_id), None)
    assert target is not None
    assert target["details"]["is_orphaned"] is True
    assert target["estimated_monthly_savings"] == round(15 * 0.05, 2)


@mock_aws
def test_detect_idle_nat_gateways():
    """Test detection of NAT Gateways with 0 active connections."""
    ec2 = boto3.client("ec2", region_name="us-east-1")
    cw = boto3.client("cloudwatch", region_name="us-east-1")

    vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc["Vpc"]["VpcId"]
    subnet = ec2.create_subnet(VpcId=vpc_id, CidrBlock="10.0.1.0/24")
    subnet_id = subnet["Subnet"]["SubnetId"]
    eip = ec2.allocate_address(Domain="vpc")

    nat_gw = ec2.create_nat_gateway(
        SubnetId=subnet_id, AllocationId=eip["AllocationId"]
    )
    nat_id = nat_gw["NatGateway"]["NatGatewayId"]

    # Put 0 active connection metrics
    cw.put_metric_data(
        Namespace="AWS/NATGateway",
        MetricData=[
            {
                "MetricName": "ActiveConnectionCount",
                "Dimensions": [{"Name": "NatGatewayId", "Value": nat_id}],
                "Value": 0.0,
                "Unit": "Count",
            }
        ],
    )

    idle_gws = detect_idle_nat_gateways()
    assert len(idle_gws) >= 1
    target = next((g for g in idle_gws if g["resource_id"] == nat_id), None)
    assert target is not None
    assert target["resource_type"] == "NATGateway"
    assert target["estimated_monthly_savings"] > 30.0


def test_governance_guardrails():
    """Test safety guardrails prevent automated actions on production resources."""
    os.environ["ALLOW_PRODUCTION_REMEDIATION"] = "false"

    prod_resource = {
        "resource_id": "i-prod-database",
        "resource_type": "EC2",
        "tags": {"Environment": "production", "Name": "DB-Primary"},
    }
    opt_out_resource = {
        "resource_id": "vol-critical",
        "resource_type": "EBS",
        "tags": {"CostOptimizerOptOut": "true"},
    }
    dev_resource = {
        "resource_id": "i-dev-sandbox",
        "resource_type": "EC2",
        "tags": {"Environment": "development", "Name": "Sandbox"},
    }

    actionable, protected = filter_actionable_resources([
        prod_resource,
        opt_out_resource,
        dev_resource,
    ])

    assert len(protected) == 2
    assert len(actionable) == 1
    assert actionable[0]["resource_id"] == "i-dev-sandbox"

    # Verify protection reasons
    is_prot, reason = is_resource_protected({"Environment": "prod"})
    assert is_prot is True
    assert "protected environment" in reason
