import os
import pytest
import boto3
from datetime import datetime, timezone
from moto import mock_aws

# Ensure we configure dummy credentials for boto3 testing before importing tools
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["DRY_RUN"] = "true"
os.environ["S3_BUCKET_NAME"] = "test-cost-reports-bucket"
os.environ["SNS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:123456789012:test-alerts"

from src.detectors.ec2_detector import detect_idle_ec2_instances
from src.detectors.rds_detector import detect_idle_rds_instances
from src.detectors.ebs_detector import detect_unattached_ebs_volumes
from src.detectors.eip_detector import detect_unused_eips
from src.detectors.elb_detector import detect_idle_elb_instances
from src.actions.stop_ec2 import stop_ec2_instances
from src.actions.stop_rds import stop_rds_instances
from src.reports.generator import generate_reports
from src.reports.notifier import send_sns_notification


@pytest.fixture
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@mock_aws
def test_detect_idle_ec2(aws_credentials):
    """Test EC2 detector handles running/idle instance and filters appropriately."""
    ec2_client = boto3.client('ec2', region_name='us-east-1')
    cw_client = boto3.client('cloudwatch', region_name='us-east-1')
    
    # 1. Create a mock running instance
    # Need AMI to create instance
    images = ec2_client.describe_images()
    image_id = images['Images'][0]['ImageId'] if images.get('Images') else 'ami-12345678'
    
    reservation = ec2_client.run_instances(
        ImageId=image_id,
        MinCount=1,
        MaxCount=1,
        InstanceType='t3.micro'
    )
    instance_id = reservation['Instances'][0]['InstanceId']
    
    # 2. Add CloudWatch low CPU metrics (e.g. 2.5% average)
    cw_client.put_metric_data(
        Namespace='AWS/EC2',
        MetricData=[
            {
                'MetricName': 'CPUUtilization',
                'Dimensions': [{'Name': 'InstanceId', 'Value': instance_id}],
                'Value': 2.5,
                'Unit': 'Percent'
            }
        ]
    )
    
    # Run detector
    idle_instances = detect_idle_ec2_instances()
    
    assert len(idle_instances) == 1
    assert idle_instances[0]['resource_id'] == instance_id
    assert idle_instances[0]['resource_type'] == 'EC2'


@mock_aws
def test_stop_ec2(aws_credentials):
    """Test EC2 stop action stops instance and applies tag metadata."""
    ec2_client = boto3.client('ec2', region_name='us-east-1')
    
    reservation = ec2_client.run_instances(
        ImageId='ami-12345678',
        MinCount=1,
        MaxCount=1,
        InstanceType='t3.micro'
    )
    instance_id = reservation['Instances'][0]['InstanceId']
    
    # Run action (non-dry run)
    os.environ["DRY_RUN"] = "false"
    stopped = stop_ec2_instances([instance_id])
    
    assert instance_id in stopped
    
    # Verify state is stopping or stopped in mock
    status = ec2_client.describe_instances(InstanceIds=[instance_id])
    state = status['Reservations'][0]['Instances'][0]['State']['Name']
    assert state in ['stopping', 'stopped']
    
    # Verify tags
    tags = status['Reservations'][0]['Instances'][0]['Tags']
    tag_dict = {tag['Key']: tag['Value'] for tag in tags}
    assert tag_dict.get('CostOptimizer') == 'true'
    assert 'CostOptimizerStopTimestamp' in tag_dict


@mock_aws
def test_detect_unattached_ebs(aws_credentials):
    """Test unattached EBS volume detection."""
    ec2_client = boto3.client('ec2', region_name='us-east-1')
    
    # Create an available (unattached) volume
    volume = ec2_client.create_volume(
        AvailabilityZone='us-east-1a',
        Size=20,
        VolumeType='gp3'
    )
    volume_id = volume['VolumeId']
    
    detected = detect_unattached_ebs_volumes()
    
    assert len(detected) == 1
    assert detected[0]['resource_id'] == volume_id
    assert detected[0]['estimated_monthly_savings'] == 1.60  # 20 * 0.08


@mock_aws
def test_detect_unused_eip(aws_credentials):
    """Test unused Elastic IP address detection."""
    ec2_client = boto3.client('ec2', region_name='us-east-1')
    
    # Allocate EIP (by default it is unassociated/unused)
    allocation = ec2_client.allocate_address(Domain='vpc')
    allocation_id = allocation['AllocationId']
    
    detected = detect_unused_eips()
    
    assert len(detected) == 1
    assert detected[0]['resource_id'] == allocation_id
    assert detected[0]['estimated_monthly_savings'] == 3.60


@mock_aws
def test_report_generation_and_upload(aws_credentials):
    """Test report HTML/JSON rendering and S3 bucket upload."""
    s3_client = boto3.client('s3', region_name='us-east-1')
    bucket_name = os.environ["S3_BUCKET_NAME"]
    s3_client.create_bucket(Bucket=bucket_name)
    
    mock_resources = [
        {
            'resource_id': 'i-12345678',
            'resource_type': 'EC2',
            'name': 'Dev-Web',
            'details': {'instance_type': 't3.medium', 'state': 'running'},
            'estimated_monthly_savings': 30.00
        }
    ]
    
    summary = generate_reports(mock_resources, dry_run=True)
    
    assert summary['total_savings'] == 30.00
    assert summary['total_resources'] == 1
    assert bucket_name in summary['s3_html_url']
    assert bucket_name in summary['s3_csv_url']
    
    # Check if files exist in the S3 bucket
    objects = s3_client.list_objects_v2(Bucket=bucket_name)
    keys = [obj['Key'] for obj in objects.get('Contents', [])]
    assert len(keys) == 3  # one JSON, one HTML, and one CSV
    assert any(k.endswith('.html') for k in keys)
    assert any(k.endswith('.json') for k in keys)
    assert any(k.endswith('.csv') for k in keys)


@mock_aws
def test_sns_notification(aws_credentials):
    """Test publishing alerts to SNS topic."""
    sns_client = boto3.client('sns', region_name='us-east-1')
    topic = sns_client.create_topic(Name="test-alerts")
    topic_arn = topic['TopicArn']
    os.environ["SNS_TOPIC_ARN"] = topic_arn
    
    report_summary = {
        "total_savings": 50.00,
        "total_resources": 2,
        "s3_html_url": "s3://mock/report.html",
        "s3_json_url": "s3://mock/report.json",
        "report_date": "2026-06-23"
    }
    
    success = send_sns_notification(report_summary, dry_run=True)
    assert success is True


@mock_aws
def test_detect_idle_elb(aws_credentials):
    """Test ELB detector finds idle load balancers and filters appropriately."""
    elbv2_client = boto3.client('elbv2', region_name='us-east-1')
    cw_client = boto3.client('cloudwatch', region_name='us-east-1')
    
    # Create a mock VPC and Subnets to satisfy create_load_balancer requirement
    ec2_client = boto3.client('ec2', region_name='us-east-1')
    vpc = ec2_client.create_vpc(CidrBlock='172.28.7.0/24')
    subnet1 = ec2_client.create_subnet(VpcId=vpc['Vpc']['VpcId'], CidrBlock='172.28.7.0/26', AvailabilityZone='us-east-1a')
    subnet2 = ec2_client.create_subnet(VpcId=vpc['Vpc']['VpcId'], CidrBlock='172.28.7.64/26', AvailabilityZone='us-east-1b')
    
    # Create a mock Application Load Balancer
    lb = elbv2_client.create_load_balancer(
        Name='test-alb',
        Subnets=[subnet1['Subnet']['SubnetId'], subnet2['Subnet']['SubnetId']],
        Type='application'
    )
    lb_arn = lb['LoadBalancers'][0]['LoadBalancerArn']
    
    # CloudWatch Dimension expects suffix part of the ARN
    arn_parts = lb_arn.split(':loadbalancer/')
    lb_dimension = arn_parts[1]
    
    # Put CloudWatch metrics indicating 0 requests
    cw_client.put_metric_data(
        Namespace='AWS/ApplicationELB',
        MetricData=[
            {
                'MetricName': 'RequestCount',
                'Dimensions': [{'Name': 'LoadBalancer', 'Value': lb_dimension}],
                'Value': 0.0,
                'Unit': 'Count'
            }
        ]
    )
    
    # Run detector
    idle_elbs = detect_idle_elb_instances()
    
    assert len(idle_elbs) == 1
    assert idle_elbs[0]['resource_id'] == lb_arn
    assert idle_elbs[0]['resource_type'] == 'ELB'
    assert idle_elbs[0]['estimated_monthly_savings'] == 16.20
