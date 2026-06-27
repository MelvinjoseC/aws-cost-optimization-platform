import os
from datetime import datetime, timedelta, timezone
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Standard AWS hourly rate for load balancers (us-east-1 ALB/CLB base cost is ~$0.0225/hour)
ELB_HOURLY_PRICING = 0.0225
ELB_MONTHLY_PRICING = round(ELB_HOURLY_PRICING * 24 * 30, 2)  # ~$16.20

def is_elb_idle(cw_client, namespace: str, dimension_name: str, dimension_value: str, idle_hours: int) -> bool:
    """
    Checks if the sum of RequestCount metrics over the idle period is 0.
    """
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=idle_hours)
    
    try:
        response = cw_client.get_metric_statistics(
            Namespace=namespace,
            MetricName='RequestCount',
            Dimensions=[{'Name': dimension_name, 'Value': dimension_value}],
            StartTime=start_time,
            EndTime=end_time,
            Period=idle_hours * 3600,  # one single period covering the whole range
            Statistics=['Sum']
        )
        
        datapoints = response.get('Datapoints', [])
        if not datapoints:
            # If no metrics are returned, it has had no requests.
            return True
            
        total_requests = sum(dp.get('Sum', 0.0) for dp in datapoints)
        logger.debug(f"Load balancer {dimension_value} total requests over {idle_hours}h: {total_requests}")
        return total_requests == 0

    except ClientError as e:
        logger.error(f"Error fetching CloudWatch metrics for load balancer {dimension_value}: {e}")
        return False

def detect_idle_elb_instances() -> list:
    """
    Scans for Application Load Balancers and Classic Load Balancers with 0 requests for the idle period (default 7 days / 168 hours).
    Excludes load balancers with opt-out tag: CostOptimizerOptOut=true.
    """
    logger.info("Starting idle Load Balancer detection...")
    
    elbv2_client = get_aws_client('elbv2')
    elb_client = get_aws_client('elb')
    cw_client = get_aws_client('cloudwatch')
    
    idle_hours = int(os.environ.get("ELB_IDLE_HOURS", 168))
    idle_elbs = []
    
    # 1. Scan Application Load Balancers (ELB v2)
    try:
        paginator = elbv2_client.get_paginator('describe_load_balancers')
        pages = paginator.paginate()
        
        for page in pages:
            for lb in page.get('LoadBalancers', []):
                lb_arn = lb.get('LoadBalancerArn')
                lb_name = lb.get('LoadBalancerName')
                lb_type = lb.get('Type')
                
                # We primarily focus on Application Load Balancers (ALBs)
                if lb_type != 'application':
                    continue
                    
                # Fetch tags for ELB v2
                try:
                    tags_response = elbv2_client.describe_tags(ResourceArns=[lb_arn])
                    tags = tags_response.get('TagDescriptions', [{}])[0].get('Tags', [])
                except ClientError as e:
                    logger.error(f"Error fetching tags for ALB {lb_name}: {e}")
                    tags = []
                    
                tag_dict = {tag['Key']: tag['Value'] for tag in tags}
                if tag_dict.get('CostOptimizerOptOut') == 'true':
                    logger.info(f"ALB {lb_name} opted out of auto-deletion via tag.")
                    continue
                
                # CloudWatch ALB Dimension format requires parsing the ARN suffix
                # e.g., app/my-load-balancer/50dc6c495c0c9188
                arn_parts = lb_arn.split(':loadbalancer/')
                if len(arn_parts) > 1:
                    lb_dimension = arn_parts[1]
                else:
                    lb_dimension = lb_name
                    
                if is_elb_idle(cw_client, 'AWS/ApplicationELB', 'LoadBalancer', lb_dimension, idle_hours):
                    logger.info(
                        f"Detected Idle Application Load Balancer: Name={lb_name}, ARN={lb_arn}, "
                        f"Estimated Savings=${ELB_MONTHLY_PRICING}/mo"
                    )
                    
                    idle_elbs.append({
                        'resource_id': lb_arn,
                        'resource_type': 'ELB',
                        'name': lb_name,
                        'details': {
                            'load_balancer_type': 'application',
                            'dns_name': lb.get('DNSName'),
                            'scheme': lb.get('Scheme'),
                            'arn': lb_arn
                        },
                        'estimated_monthly_savings': ELB_MONTHLY_PRICING,
                        'opt_out_tag': False
                    })
                    
    except ClientError as e:
        logger.error(f"Error describing ELBv2 load balancers: {e}")
        
    # 2. Scan Classic Load Balancers (ELB v1)
    try:
        # Note: describe_load_balancers for Classic ELB doesn't support get_paginator in standard boto3
        response = elb_client.describe_load_balancers()
        for lb in response.get('LoadBalancerDescriptions', []):
            lb_name = lb.get('LoadBalancerName')
            
            # Fetch tags for Classic ELB
            try:
                tags_response = elb_client.describe_tags(LoadBalancerNames=[lb_name])
                tags = tags_response.get('TagDescriptions', [{}])[0].get('Tags', [])
            except ClientError as e:
                logger.error(f"Error fetching tags for Classic ELB {lb_name}: {e}")
                tags = []
                
            tag_dict = {tag['Key']: tag['Value'] for tag in tags}
            if tag_dict.get('CostOptimizerOptOut') == 'true':
                logger.info(f"Classic ELB {lb_name} opted out of auto-deletion via tag.")
                continue
                
            if is_elb_idle(cw_client, 'AWS/ELB', 'LoadBalancerName', lb_name, idle_hours):
                logger.info(
                    f"Detected Idle Classic Load Balancer: Name={lb_name}, "
                    f"Estimated Savings=${ELB_MONTHLY_PRICING}/mo"
                )
                
                idle_elbs.append({
                    'resource_id': lb_name,
                    'resource_type': 'ELB',
                    'name': lb_name,
                    'details': {
                        'load_balancer_type': 'classic',
                        'dns_name': lb.get('DNSName'),
                        'scheme': lb.get('Scheme'),
                    },
                    'estimated_monthly_savings': ELB_MONTHLY_PRICING,
                    'opt_out_tag': False
                })
                
    except ClientError as e:
        logger.warning(f"Error describing Classic load balancers: {e}. (This service may not be available/mocked)")
        
    logger.info(f"ELB scanning completed. Found {len(idle_elbs)} idle load balancers.")
    return idle_elbs
