from typing import Dict

# Standard AWS Regional Pricing Defaults (USD)

EBS_MONTHLY_PER_GB: Dict[str, float] = {
    "gp3": 0.08,
    "gp2": 0.10,
    "io1": 0.125,
    "io2": 0.125,
    "standard": 0.05,
    "sc1": 0.015,
    "st1": 0.045,
}

EIP_HOURLY_RATE: float = 0.005  # $0.005/hr unassociated IPv4 charge
NAT_GATEWAY_HOURLY_RATE: float = 0.045  # $0.045/hr base gateway fee
EBS_SNAPSHOT_MONTHLY_PER_GB: float = 0.05  # Standard snapshot storage
CLOUDWATCH_LOGS_MONTHLY_PER_GB: float = 0.03  # Standard log storage
EFS_STANDARD_PER_GB: float = 0.30  # Standard storage
EFS_IA_PER_GB: float = 0.025  # Infrequent access storage
DYNAMODB_WCU_HOURLY: float = 0.00065  # Per WCU-hour
DYNAMODB_RCU_HOURLY: float = 0.00013  # Per RCU-hour

EC2_HOURLY_PRICING: Dict[str, float] = {
    "t2.nano": 0.0058,
    "t2.micro": 0.0116,
    "t2.small": 0.023,
    "t2.medium": 0.0464,
    "t2.large": 0.0928,
    "t2.xlarge": 0.1856,
    "t2.2xlarge": 0.3712,
    "t3.nano": 0.0052,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "t3.2xlarge": 0.3328,
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "m5.2xlarge": 0.384,
    "c5.large": 0.085,
    "c5.xlarge": 0.17,
    "c5.2xlarge": 0.34,
    "r5.large": 0.126,
    "r5.xlarge": 0.252,
    "r5.2xlarge": 0.504,
}

RDS_HOURLY_PRICING: Dict[str, float] = {
    "db.t3.micro": 0.017,
    "db.t3.small": 0.034,
    "db.t3.medium": 0.068,
    "db.t3.large": 0.136,
    "db.m5.large": 0.171,
    "db.m5.xlarge": 0.342,
    "db.r5.large": 0.24,
    "db.r5.xlarge": 0.48,
}

ELASTICACHE_HOURLY_PRICING: Dict[str, float] = {
    "cache.t2.micro": 0.017,
    "cache.t3.micro": 0.017,
    "cache.t3.small": 0.034,
    "cache.t3.medium": 0.068,
    "cache.m5.large": 0.136,
    "cache.r5.large": 0.228,
}


def calculate_ebs_savings(size_gb: int, volume_type: str = "gp3") -> float:
    """Calculates monthly cost of an EBS volume."""
    rate = EBS_MONTHLY_PER_GB.get(volume_type.lower(), 0.08)
    return round(size_gb * rate, 2)


def calculate_ec2_monthly_savings(
    instance_type: str, hours_per_month: int = 720
) -> float:
    """Calculates monthly idle cost for an EC2 instance."""
    hourly = EC2_HOURLY_PRICING.get(instance_type, 0.05)
    return round(hourly * hours_per_month, 2)


def calculate_rds_monthly_savings(
    instance_class: str, hours_per_month: int = 720
) -> float:
    """Calculates monthly idle cost for an RDS database instance."""
    hourly = RDS_HOURLY_PRICING.get(instance_class, 0.08)
    return round(hourly * hours_per_month, 2)


def calculate_eip_monthly_savings(hours_per_month: int = 720) -> float:
    """Calculates monthly cost for an unassociated Elastic IP."""
    return round(EIP_HOURLY_RATE * hours_per_month, 2)


def calculate_nat_gateway_monthly_savings(
    hours_per_month: int = 720,
) -> float:
    """Calculates monthly base cost for an idle NAT Gateway."""
    return round(NAT_GATEWAY_HOURLY_RATE * hours_per_month, 2)


def calculate_snapshot_monthly_savings(size_gb: int) -> float:
    """Calculates monthly cost for stored EBS snapshots."""
    return round(size_gb * EBS_SNAPSHOT_MONTHLY_PER_GB, 2)


def calculate_dynamodb_monthly_savings(
    read_capacity: int, write_capacity: int, hours_per_month: int = 720
) -> float:
    """Calculates monthly idle provisioned DynamoDB capacity cost."""
    monthly_rcu = read_capacity * DYNAMODB_RCU_HOURLY * hours_per_month
    monthly_wcu = write_capacity * DYNAMODB_WCU_HOURLY * hours_per_month
    return round(monthly_rcu + monthly_wcu, 2)


def calculate_efs_lifecycle_savings(size_gb: float) -> float:
    """Calculates potential monthly savings by transitioning EFS to IA tier."""
    savings_per_gb = EFS_STANDARD_PER_GB - EFS_IA_PER_GB
    return round(size_gb * savings_per_gb, 2)


def calculate_cloudwatch_log_storage_cost(size_gb: float) -> float:
    """Calculates monthly storage cost for CloudWatch log group."""
    return round(size_gb * CLOUDWATCH_LOGS_MONTHLY_PER_GB, 2)
