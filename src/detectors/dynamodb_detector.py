from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client, get_target_regions
from src.utils.config import get_config
from src.utils.logger import get_logger
from src.utils.pricing import calculate_dynamodb_monthly_savings

logger = get_logger(__name__)


def get_table_consumed_capacity(
    cw_client, table_name: str, metric_name: str, days: int
) -> float:
    """Queries CloudWatch for consumed DynamoDB capacity units over observation window."""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    try:
        response = cw_client.get_metric_statistics(
            Namespace="AWS/DynamoDB",
            MetricName=metric_name,
            Dimensions=[{"Name": "TableName", "Value": table_name}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,
            Statistics=["Sum"],
        )
        datapoints = response.get("Datapoints", [])
        if not datapoints:
            return 0.0
        return sum(dp.get("Sum", 0.0) for dp in datapoints)
    except ClientError as e:
        logger.warning(
            f"Could not retrieve {metric_name} for DynamoDB table {table_name}: {e}"
        )
        return 0.0


def get_table_tags(dynamodb_client, table_arn: str) -> Dict[str, str]:
    """Retrieves resource tags for a DynamoDB table."""
    try:
        response = dynamodb_client.list_tags_of_resource(ResourceArn=table_arn)
        tags = response.get("Tags", [])
        return {tag["Key"]: tag["Value"] for tag in tags}
    except ClientError as e:
        logger.debug(f"Could not fetch tags for DynamoDB {table_arn}: {e}")
        return {}


def detect_idle_dynamodb_tables() -> List[Dict]:
    """
    Scans for provisioned DynamoDB tables with zero consumed capacity over observation window.
    Calculates cost savings if converted to Pay-Per-Request (On-Demand) billing.
    """
    logger.info("Starting idle DynamoDB table detection...")
    cfg = get_config(reload=True)
    target_regions = get_target_regions()
    detected_tables = []

    for region in target_regions:
        logger.info(f"Scanning DynamoDB tables in region: {region}")
        ddb_client = get_aws_client("dynamodb", region_name=region)
        cw_client = get_aws_client("cloudwatch", region_name=region)

        try:
            paginator = ddb_client.get_paginator("list_tables")
            for page in paginator.paginate():
                for table_name in page.get("TableNames", []):
                    try:
                        desc = ddb_client.describe_table(TableName=table_name)
                        table_data = desc.get("Table", {})
                    except ClientError as e:
                        logger.warning(f"Could not describe table {table_name}: {e}")
                        continue

                    billing_summary = table_data.get("BillingModeSummary", {})
                    billing_mode = billing_summary.get("BillingMode", "PROVISIONED")

                    # If table is already PAY_PER_REQUEST, idle tables cost $0
                    if billing_mode == "PAY_PER_REQUEST":
                        continue

                    throughput = table_data.get("ProvisionedThroughput", {})
                    rcu = throughput.get("ReadCapacityUnits", 0)
                    wcu = throughput.get("WriteCapacityUnits", 0)

                    if rcu == 0 and wcu == 0:
                        continue

                    table_arn = table_data.get("TableArn", "")
                    tags = get_table_tags(ddb_client, table_arn) if table_arn else {}

                    if tags.get("CostOptimizerOptOut") == "true":
                        logger.info(f"DynamoDB table {table_name} opted out via tag.")
                        continue

                    # Query consumed units over observation window
                    consumed_read = get_table_consumed_capacity(
                        cw_client, table_name, "ConsumedReadCapacityUnits", cfg.dynamodb_idle_days
                    )
                    consumed_write = get_table_consumed_capacity(
                        cw_client, table_name, "ConsumedWriteCapacityUnits", cfg.dynamodb_idle_days
                    )

                    if consumed_read == 0.0 and consumed_write == 0.0:
                        monthly_savings = calculate_dynamodb_monthly_savings(rcu, wcu)
                        logger.info(
                            f"[{region}] Detected Idle Provisioned DynamoDB Table: {table_name}, "
                            f"RCU={rcu}, WCU={wcu}, Estimated Savings=${monthly_savings}/mo"
                        )
                        detected_tables.append(
                            {
                                "resource_id": table_name,
                                "resource_type": "DynamoDB",
                                "name": table_name,
                                "details": {
                                    "region": region,
                                    "table_arn": table_arn,
                                    "read_capacity": rcu,
                                    "write_capacity": wcu,
                                    "billing_mode": billing_mode,
                                    "item_count": table_data.get("ItemCount", 0),
                                    "size_bytes": table_data.get("TableSizeBytes", 0),
                                },
                                "tags": tags,
                                "estimated_monthly_savings": monthly_savings,
                            }
                        )

        except ClientError as e:
            logger.error(f"Failed scanning DynamoDB tables in region {region}: {e}")

    logger.info(f"Completed DynamoDB detection. Found {len(detected_tables)} idle tables.")
    return detected_tables
