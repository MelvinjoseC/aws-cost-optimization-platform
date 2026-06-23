import os
from datetime import datetime, timedelta, timezone
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Standard hourly pricing estimate for monthly savings calculation
# (Approximate values for standard Linux instances in us-east-1)
EC2_HOURLY_PRICING = {
    "t2.nano": 0.0058, "t2.micro": 0.0116, "t2.small": 0.023, "t2.medium": 0.0464, "t2.large": 0.0928,
    "t3.nano": 0.0052, "t3.micro": 0.0104, "t3.small": 0.0208, "t3.medium": 0.0416, "t3.large": 0.0832,
    "t3.xlarge": 0.1664, "t3.2xlarge": 0.3328,
    "m5.large": 0.096, "m5.xlarge": 0.192, "m5.2xlarge": 0.384,
    "c5.large": 0.085, "c5.xlarge": 0.170, "c5.2xlarge": 0.340,
    "r5.large": 0.126, "r5.xlarge": 0.252, "r5.2xlarge": 0.504,
}
DEFAULT_HOURLY_PRICE = 0.05  # fallback roughly $36/month


def get_estimated_monthly_savings(instance_type: str) -> float:
    """Calculates estimated monthly savings based on instance type."""
    hourly_rate = EC2_HOURLY_PRICING.get(instance_type, DEFAULT_HOURLY_PRICE)
    return round(hourly_rate * 24 * 30, 2)


def is_instance_idle(ec2_client, cw_client, instance_id: str, threshold: float, idle_hours: int) -> bool:
    """
    Queries CloudWatch to check if average CPU utilization is below threshold
    for the specified idle period (default 72 hours).
    """
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=idle_hours)
    
    try:
        # We query with 1-hour periods.
        # If the metric does not exist, or average CPU across the window is < threshold, it's idle.
        response = cw_client.get_metric_statistics(
            Namespace='AWS/EC2',
            MetricName='CPUUtilization',
            Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=['Average']
        )
        
        datapoints = response.get('Datapoints', [])
        if not datapoints:
            logger.warning(f"No CPU metrics found for instance {instance_id}. Assuming potentially idle.")
            return True
            
        averages = [dp['Average'] for dp in datapoints]
        overall_average = sum(averages) / len(averages)
        
        logger.debug(f"Instance {instance_id} average CPU utilization over {idle_hours}h: {overall_average:.2f}%")
        return overall_average < threshold

    except ClientError as e:
        logger.error(f"Error fetching CloudWatch metrics for instance {instance_id}: {e}")
        # Return False to avoid action on errors
        return False


def detect_idle_ec2_instances() -> list:
    """
    Scans for EC2 instances running with CPU < threshold (default 5%) for the last 72 hours.
    Excludes instances with opt-out tag: CostOptimizerOptOut=true.
    """
    logger.info("Starting idle EC2 instance detection...")
    
    ec2_client = get_aws_client('ec2')
    cw_client = get_aws_client('cloudwatch')
    
    cpu_threshold = float(os.environ.get("EC2_CPU_THRESHOLD", 5.0))
    idle_hours = int(os.environ.get("EC2_IDLE_HOURS", 72))
    
    idle_instances = []
    
    try:
        paginator = ec2_client.get_paginator('describe_instances')
        # Only check running instances
        pages = paginator.paginate(
            Filters=[
                {'Name': 'instance-state-name', 'Values': ['running']}
            ]
        )
        
        for page in pages:
            for reservation in page.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    instance_id = instance.get('InstanceId')
                    instance_type = instance.get('InstanceType')
                    tags = instance.get('Tags', [])
                    
                    # Convert tag list to dict
                    tag_dict = {tag['Key']: tag['Value'] for tag in tags}
                    
                    # Check for opt-out tag
                    if tag_dict.get('CostOptimizerOptOut') == 'true':
                        logger.info(f"EC2 instance {instance_id} opted out of auto-stopping via tag.")
                        continue
                        
                    name = tag_dict.get('Name', 'Unnamed')
                    
                    # Check CPU metrics
                    if is_instance_idle(ec2_client, cw_client, instance_id, cpu_threshold, idle_hours):
                        monthly_savings = get_estimated_monthly_savings(instance_type)
                        
                        logger.info(
                            f"Detected Idle EC2 Instance: ID={instance_id}, Name={name}, "
                            f"Type={instance_type}, Estimated Savings=${monthly_savings}/mo"
                        )
                        
                        idle_instances.append({
                            'resource_id': instance_id,
                            'resource_type': 'EC2',
                            'name': name,
                            'details': {
                                'instance_type': instance_type,
                                'launch_time': instance.get('LaunchTime').isoformat(),
                                'state': instance.get('State', {}).get('Name')
                            },
                            'estimated_monthly_savings': monthly_savings,
                            'opt_out_tag': False
                        })
                        
    except ClientError as e:
        logger.error(f"Error describing EC2 instances: {e}")
        raise e
        
    logger.info(f"EC2 scanning completed. Found {len(idle_instances)} idle instances.")
    return idle_instances
