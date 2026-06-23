import os
from datetime import datetime, timedelta, timezone
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Standard hourly pricing estimates for RDS DB instances in us-east-1 (Single-AZ, db.t3/m5 Postgres)
RDS_HOURLY_PRICING = {
    "db.t3.micro": 0.017, "db.t3.small": 0.034, "db.t3.medium": 0.068, "db.t3.large": 0.136,
    "db.m5.large": 0.175, "db.m5.xlarge": 0.350, "db.m5.2xlarge": 0.700,
    "db.r5.large": 0.240, "db.r5.xlarge": 0.480, "db.r5.2xlarge": 0.960,
}
DEFAULT_RDS_HOURLY_PRICE = 0.10  # fallback roughly $72/month


def get_estimated_monthly_savings(instance_class: str) -> float:
    """Calculates estimated monthly savings based on RDS DB instance class."""
    hourly_rate = RDS_HOURLY_PRICING.get(instance_class, DEFAULT_RDS_HOURLY_PRICE)
    return round(hourly_rate * 24 * 30, 2)


def is_rds_idle(cw_client, db_id: str, connections_threshold: int, idle_hours: int) -> bool:
    """
    Checks if an RDS instance has database connections below threshold (default 0)
    over the idle period (default 48 hours).
    """
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=idle_hours)
    
    try:
        response = cw_client.get_metric_statistics(
            Namespace='AWS/RDS',
            MetricName='DatabaseConnections',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=['Maximum']
        )
        
        datapoints = response.get('Datapoints', [])
        if not datapoints:
            logger.warning(f"No DatabaseConnections metrics found for DB {db_id}. Assuming potentially idle.")
            return True
            
        # Check if maximum connection count in any hour is greater than threshold
        max_connections = max([dp['Maximum'] for dp in datapoints])
        logger.debug(f"RDS DB {db_id} maximum connections over {idle_hours}h: {max_connections}")
        
        return max_connections <= connections_threshold

    except ClientError as e:
        logger.error(f"Error fetching CloudWatch DatabaseConnections for DB {db_id}: {e}")
        return False


def detect_idle_rds_instances() -> list:
    """
    Scans for RDS DB instances with 0 connections for the last 48 hours.
    Excludes RDS instances with opt-out tag: CostOptimizerOptOut=true.
    """
    logger.info("Starting idle RDS instance detection...")
    
    rds_client = get_aws_client('rds')
    cw_client = get_aws_client('cloudwatch')
    
    connections_threshold = int(os.environ.get("RDS_CONNECTION_THRESHOLD", 0))
    idle_hours = int(os.environ.get("RDS_IDLE_HOURS", 48))
    
    idle_rds = []
    
    try:
        paginator = rds_client.get_paginator('describe_db_instances')
        pages = paginator.paginate()
        
        for page in pages:
            for db_instance in page.get('DBInstances', []):
                db_id = db_instance.get('DBInstanceIdentifier')
                db_class = db_instance.get('DBInstanceClass')
                db_status = db_instance.get('DBInstanceStatus')
                tags = db_instance.get('TagList', [])
                
                # Convert tag list to dict
                tag_dict = {tag['Key']: tag['Value'] for tag in tags}
                
                if db_status != 'available':
                    logger.debug(f"Skipping RDS instance {db_id} as status is '{db_status}' (not available).")
                    continue
                
                if tag_dict.get('CostOptimizerOptOut') == 'true':
                    logger.info(f"RDS instance {db_id} opted out of auto-stopping via tag.")
                    continue
                    
                if is_rds_idle(cw_client, db_id, connections_threshold, idle_hours):
                    monthly_savings = get_estimated_monthly_savings(db_class)
                    
                    logger.info(
                        f"Detected Idle RDS Instance: ID={db_id}, Class={db_class}, "
                        f"Estimated Savings=${monthly_savings}/mo"
                    )
                    
                    idle_rds.append({
                        'resource_id': db_id,
                        'resource_type': 'RDS',
                        'name': db_id,
                        'details': {
                            'engine': db_instance.get('Engine'),
                            'engine_version': db_instance.get('EngineVersion'),
                            'db_instance_class': db_class,
                            'status': db_status,
                            'arn': db_instance.get('DBInstanceArn')
                        },
                        'estimated_monthly_savings': monthly_savings,
                        'opt_out_tag': False
                    })
                    
    except ClientError as e:
        logger.error(f"Error describing RDS instances: {e}")
        raise e
        
    logger.info(f"RDS scanning completed. Found {len(idle_rds)} idle DB instances.")
    return idle_rds
