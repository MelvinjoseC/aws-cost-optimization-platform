import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client, get_target_regions
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Standard hourly pricing estimates for ElastiCache nodes (us-east-1)
ELASTICACHE_PRICING = {
    "cache.t2.micro": 0.017,
    "cache.t2.small": 0.034,
    "cache.t2.medium": 0.068,
    "cache.t3.micro": 0.017,
    "cache.t3.small": 0.034,
    "cache.t3.medium": 0.068,
    "cache.t4g.micro": 0.013,
    "cache.t4g.small": 0.026,
    "cache.t4g.medium": 0.052,
    "cache.m5.large": 0.156,
    "cache.r5.large": 0.228,
}
DEFAULT_CACHE_HOURLY_PRICE = 0.035  # ~$25.20/month fallback


def get_estimated_monthly_savings(node_type: str, num_nodes: int) -> float:
    """Calculates monthly savings for an ElastiCache cluster."""
    hourly_rate = ELASTICACHE_PRICING.get(
        node_type, DEFAULT_CACHE_HOURLY_PRICE
    )
    return round(hourly_rate * 24 * 30 * num_nodes, 2)


def is_elasticache_idle(
    cw_client, cluster_id: str, idle_hours: int
) -> bool:
    """
    Checks if ElastiCache cluster has 0 client connections over the window.
    """
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=idle_hours)

    try:
        response = cw_client.get_metric_statistics(
            Namespace="AWS/ElastiCache",
            MetricName="CurrConnections",
            Dimensions=[{"Name": "CacheClusterId", "Value": cluster_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=["Maximum"],
        )

        datapoints = response.get("Datapoints", [])
        if not datapoints:
            return True

        max_connections = max(dp.get("Maximum", 0) for dp in datapoints)
        return max_connections == 0

    except ClientError as e:
        logger.error(
            f"Error fetching CloudWatch metrics for cache {cluster_id}: {e}"
        )
        return False


def detect_idle_elasticache_clusters() -> List[Dict]:
    """
    Scans for ElastiCache Redis and Memcached clusters with 0 connections.
    Excludes clusters with opt-out tag: CostOptimizerOptOut=true.
    Supports multi-region scanning.
    """
    logger.info("Starting idle ElastiCache cluster detection...")

    idle_hours = int(os.environ.get("ELASTICACHE_IDLE_HOURS", 72))
    idle_clusters: List[Dict] = []
    target_regions = get_target_regions()

    for region in target_regions:
        logger.info(f"Scanning ElastiCache clusters in region: {region}")
        ec_client = get_aws_client("elasticache", region_name=region)
        cw_client = get_aws_client("cloudwatch", region_name=region)

        try:
            paginator = ec_client.get_paginator("describe_cache_clusters")
            pages = paginator.paginate(ShowCacheNodeInfo=True)

            for page in pages:
                for cluster in page.get("CacheClusters", []):
                    cluster_id = cluster.get("CacheClusterId")
                    node_type = cluster.get("CacheNodeType")
                    engine = cluster.get("Engine")
                    num_nodes = cluster.get("NumCacheNodes", 1)
                    status = cluster.get("CacheClusterStatus")
                    arn = cluster.get("ARN")

                    if status != "available":
                        continue

                    # Fetch tags
                    try:
                        tags_resp = ec_client.list_tags_for_resource(
                            ResourceName=arn
                        )
                        tag_list = tags_resp.get("TagList", [])
                    except ClientError:
                        tag_list = []

                    tag_dict = {t["Key"]: t["Value"] for t in tag_list}
                    if tag_dict.get("CostOptimizerOptOut") == "true":
                        continue

                    if is_elasticache_idle(cw_client, cluster_id, idle_hours):
                        monthly_savings = get_estimated_monthly_savings(
                            node_type, num_nodes
                        )

                        logger.info(
                            f"[{region}] Detected Idle ElastiCache: "
                            f"ID={cluster_id}, Type={node_type}, "
                            f"Engine={engine}, Savings=${monthly_savings}/mo"
                        )

                        idle_clusters.append({
                            "resource_id": cluster_id,
                            "resource_type": "ElastiCache",
                            "name": cluster_id,
                            "details": {
                                "region": region,
                                "node_type": node_type,
                                "engine": engine,
                                "num_nodes": num_nodes,
                                "status": status,
                                "arn": arn,
                            },
                            "estimated_monthly_savings": monthly_savings,
                            "opt_out_tag": False,
                        })

        except ClientError as e:
            logger.error(
                f"Error describing ElastiCache clusters in {region}: {e}"
            )
            continue

    logger.info(
        f"ElastiCache scan completed. Found {len(idle_clusters)} "
        f"idle clusters across targeted regions."
    )
    return idle_clusters
