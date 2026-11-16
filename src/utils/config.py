import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class FinOpsConfig:
    """Strongly-typed configuration container with validation for FinOps."""

    dry_run: bool = True
    allow_production_remediation: bool = False
    protected_environments: List[str] = field(
        default_factory=lambda: ["prod", "production", "live", "critical"]
    )
    protected_tag_keys: List[str] = field(
        default_factory=lambda: [
            "CostOptimizerOptOut",
            "DoNotStop",
            "Protected",
            "Production",
        ]
    )
    regions: List[str] = field(default_factory=lambda: ["us-east-1"])
    ec2_cpu_threshold: float = 5.0
    ec2_observation_days: int = 3
    ec2_rightsizing_max_cpu: float = 20.0
    rds_idle_hours: int = 48
    snapshot_max_age_days: int = 30
    nat_gw_idle_hours: int = 168
    elasticache_idle_hours: int = 72
    dynamodb_idle_days: int = 14
    efs_idle_days: int = 14
    cloudwatch_log_retention_days: int = 90
    delete_unused_ebs: bool = False
    release_unused_eip: bool = False
    s3_bucket_name: Optional[str] = None
    sns_topic_arn: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    log_format: str = "text"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "FinOpsConfig":
        """Instantiates config dynamically reading environment variables."""
        dry_run_raw = os.environ.get("DRY_RUN", "true").strip().lower()
        dry_run = dry_run_raw in ("true", "1", "yes")

        allow_prod_raw = os.environ.get(
            "ALLOW_PRODUCTION_REMEDIATION", "false"
        ).strip().lower()
        allow_prod = allow_prod_raw in ("true", "1", "yes")

        del_ebs_raw = os.environ.get(
            "DELETE_UNUSED_EBS", "false"
        ).strip().lower()
        delete_unused_ebs = del_ebs_raw in ("true", "1", "yes")

        rel_eip_raw = os.environ.get(
            "RELEASE_UNUSED_EIP", "false"
        ).strip().lower()
        release_unused_eip = rel_eip_raw in ("true", "1", "yes")

        regions_raw = os.environ.get("AWS_REGIONS", "").strip()
        if regions_raw:
            regions = [r.strip() for r in regions_raw.split(",") if r.strip()]
        else:
            default_reg = os.environ.get(
                "AWS_DEFAULT_REGION", "us-east-1"
            ).strip()
            regions = [default_reg] if default_reg else ["us-east-1"]

        prot_env_raw = os.environ.get("PROTECTED_ENVIRONMENTS", "").strip()
        if prot_env_raw:
            protected_envs = [
                e.strip().lower() for e in prot_env_raw.split(",") if e.strip()
            ]
        else:
            protected_envs = ["prod", "production", "live", "critical"]

        try:
            ec2_cpu = float(os.environ.get("EC2_CPU_THRESHOLD", 5.0))
        except ValueError:
            ec2_cpu = 5.0

        try:
            snap_age = int(os.environ.get("SNAPSHOT_MAX_AGE_DAYS", 30))
        except ValueError:
            snap_age = 30

        try:
            nat_idle = int(os.environ.get("NAT_GW_IDLE_HOURS", 168))
        except ValueError:
            nat_idle = 168

        try:
            ec_idle = int(os.environ.get("ELASTICACHE_IDLE_HOURS", 72))
        except ValueError:
            ec_idle = 72

        return cls(
            dry_run=dry_run,
            allow_production_remediation=allow_prod,
            protected_environments=protected_envs,
            regions=regions,
            ec2_cpu_threshold=ec2_cpu,
            snapshot_max_age_days=snap_age,
            nat_gw_idle_hours=nat_idle,
            elasticache_idle_hours=ec_idle,
            delete_unused_ebs=delete_unused_ebs,
            release_unused_eip=release_unused_eip,
            s3_bucket_name=os.environ.get("S3_BUCKET_NAME") or None,
            sns_topic_arn=os.environ.get("SNS_TOPIC_ARN") or None,
            slack_webhook_url=os.environ.get("SLACK_WEBHOOK_URL") or None,
            log_format=os.environ.get("LOG_FORMAT", "text").lower(),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        )


_config_instance: Optional[FinOpsConfig] = None


def get_config(reload: bool = False) -> FinOpsConfig:
    """Returns singleton FinOpsConfig instance."""
    global _config_instance
    if _config_instance is None or reload:
        _config_instance = FinOpsConfig.from_env()
    return _config_instance
