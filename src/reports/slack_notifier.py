import json
import os
import urllib.error
import urllib.request
from typing import Dict
from src.utils.logger import get_logger

logger = get_logger(__name__)


def send_slack_notification(
    report_summary: Dict, dry_run: bool
) -> bool:
    """
    Sends a formatted Slack Block Kit alert to the configured webhook URL.
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.info("SLACK_WEBHOOK_URL not configured. Skipping Slack alert.")
        return False

    env = os.environ.get("ENVIRONMENT", "production")
    mode_str = "DRY-RUN (Preview)" if dry_run else "ACTIVE (Remediated)"
    savings = report_summary.get("total_savings", 0.0)
    count = report_summary.get("total_resources", 0)
    html_url = report_summary.get("s3_html_url", "N/A")
    date_str = report_summary.get("report_date", "Today")

    fallback_text = (
        f"AWS Cost Optimization - {date_str} (${savings:.2f}/mo)"
    )
    payload = {
        "text": fallback_text,
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "💰 AWS Cost Optimization Summary",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Environment:*\n`{env}`"},
                    {"type": "mrkdwn", "text": f"*Mode:*\n`{mode_str}`"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Monthly Savings:*\n*${savings:.2f}*",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Resources:*\n`{count} detected`",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"📊 *Full S3 Report:* <{html_url}|View HTML Report>\n"
                        f"_Generated automatically by AWS Cost Optimizer._"
                    ),
                },
            },
        ],
    }

    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                logger.info("Successfully posted summary to Slack.")
                return True
            logger.warning(f"Slack webhook returned status: {response.status}")
            return False
    except urllib.error.URLError as e:
        logger.error(f"Error posting notification to Slack: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending Slack alert: {e}")
        return False
