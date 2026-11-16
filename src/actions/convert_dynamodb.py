from datetime import datetime, timezone
from typing import Dict, List
from botocore.exceptions import ClientError
from src.utils.aws_client import get_aws_client
from src.utils.config import get_config
from src.utils.governance import filter_actionable_resources
from src.utils.logger import get_logger

logger = get_logger(__name__)


def convert_dynamodb_to_ondemand(resources: List[Dict]) -> List[str]:
    """
    Converts idle provisioned DynamoDB tables to PAY_PER_REQUEST (On-Demand) billing.
    Respects governance guardrails and DRY_RUN mode.
    """
    if not resources:
        logger.info("No DynamoDB tables provided for remediation.")
        return []

    cfg = get_config(reload=True)
    actionable, protected = filter_actionable_resources(resources)

    if protected:
        logger.info(
            f"Skipped {len(protected)} DynamoDB tables due to governance protection."
        )

    if not actionable:
        logger.info("No actionable DynamoDB tables to convert.")
        return []

    converted = []

    for res in actionable:
        table_name = res.get("resource_id")
        region = res.get("details", {}).get("region", "us-east-1")
        ddb_client = get_aws_client("dynamodb", region_name=region)

        if cfg.dry_run:
            logger.info(
                f"[DRY RUN] Would convert DynamoDB table '{table_name}' in {region} "
                "from PROVISIONED to PAY_PER_REQUEST billing."
            )
            converted.append(table_name)
            continue

        try:
            logger.info(
                f"Converting DynamoDB table '{table_name}' in {region} to PAY_PER_REQUEST..."
            )
            ddb_client.update_table(
                TableName=table_name,
                BillingMode="PAY_PER_REQUEST",
            )
            converted.append(table_name)
            logger.info(f"Successfully converted DynamoDB table '{table_name}'.")

            # Tag with audit trail
            table_arn = res.get("details", {}).get("table_arn")
            if table_arn:
                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                ddb_client.tag_resource(
                    ResourceArn=table_arn,
                    Tags=[
                        {"Key": "CostOptimizerRemediated", "Value": "true"},
                        {"Key": "PreviousBillingMode", "Value": "PROVISIONED"},
                        {"Key": "RemediationTimestamp", "Value": now_str},
                    ],
                )
        except ClientError as e:
            logger.error(f"Failed converting DynamoDB table '{table_name}': {e}")

    return converted
