import json
import os
from datetime import datetime, timezone
from botocore.exceptions import ClientError
from jinja2 import Template
from src.utils.aws_client import get_aws_client
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Clean, professional HTML template for the savings report
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AWS Cost Optimization Report - {{ date }}</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f8f9fa;
            color: #333333;
            margin: 0;
            padding: 40px;
        }
        .container {
            max-width: 1100px;
            margin: 0 auto;
            background: #ffffff;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        }
        h1 {
            color: #1a365d;
            margin-top: 0;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 15px;
        }
        .meta {
            color: #718096;
            font-size: 0.9em;
            margin-bottom: 30px;
        }
        .summary-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: #ebf8ff;
            border-left: 4px solid #3182ce;
            padding: 20px;
            border-radius: 4px;
        }
        .card.savings {
            background: #f0fff4;
            border-left-color: #38a169;
        }
        .card h3 {
            margin: 0 0 10px 0;
            color: #4a5568;
            font-size: 0.9em;
            text-transform: uppercase;
        }
        .card .value {
            font-size: 1.8em;
            font-weight: bold;
            color: #2d3748;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            margin-bottom: 40px;
        }
        th, td {
            text-align: left;
            padding: 12px 15px;
            border-bottom: 1px solid #e2e8f0;
        }
        th {
            background-color: #f7fafc;
            color: #4a5568;
            font-weight: 600;
        }
        tr:hover {
            background-color: #f8fafc;
        }
        .badge {
            display: inline-block;
            padding: 4px 8px;
            font-size: 0.75em;
            font-weight: bold;
            border-radius: 4px;
        }
        .badge-ec2 { background-color: #feebc8; color: #c05621; }
        .badge-rds { background-color: #e2e8f0; color: #4a5568; }
        .badge-ebs { background-color: #fed7d7; color: #9b2c2c; }
        .badge-eip { background-color: #e9d8fd; color: #553c9a; }
        .badge-k8s { background-color: #e6fffa; color: #234e52; }
        .dry-run-banner {
            background-color: #fffaf0;
            border: 1px solid #feebc8;
            color: #c05621;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 30px;
            font-weight: 500;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>AWS Cost Optimization Report</h1>
        <div class="meta">Generated on {{ date }} UTC | Mode: {% if dry_run %}DRY-RUN (No actions taken){% else %}EXECUTION (Resources optimized){% endif %}</div>
        
        {% if dry_run %}
        <div class="dry-run-banner">
            <strong>Dry-Run Mode Active:</strong> Listed below are idle resources that were detected. No resources were stopped or scaled down.
        </div>
        {% endif %}

        <div class="summary-cards">
            <div class="card savings">
                <h3>Est. Monthly Savings</h3>
                <div class="value">${{ "%.2f"|format(total_savings) }}</div>
            </div>
            <div class="card">
                <h3>Total Idle Resources</h3>
                <div class="value">{{ total_resources }}</div>
            </div>
            <div class="card">
                <h3>Action Status</h3>
                <div class="value">{% if dry_run %}Previewed{% else %}Remediated{% endif %}</div>
            </div>
        </div>

        <h2>Detected Resource Breakdown</h2>
        <table>
            <thead>
                <tr>
                    <th>Type</th>
                    <th>Resource ID / Name</th>
                    <th>State/Details</th>
                    <th>Est. Savings/Month</th>
                </tr>
            </thead>
            <tbody>
                {% for res in resources %}
                <tr>
                    <td>
                        <span class="badge badge-{{ res.resource_type.lower() if res.resource_type != 'KubernetesDeployment' else 'k8s' }}">
                            {{ res.resource_type }}
                        </span>
                    </td>
                    <td><strong>{{ res.name }}</strong><br><small style="color: #718096;">{{ res.resource_id }}</small></td>
                    <td>
                        {% for k, v in res.details.items() %}
                            {% if k != 'arn' %}
                            <strong>{{ k }}:</strong> {{ v }}<br>
                            {% endif %}
                        {% endfor %}
                    </td>
                    <td>${{ "%.2f"|format(res.estimated_monthly_savings) }}</td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="4" style="text-align: center; color: #718096; padding: 30px;">
                        No idle resources detected. Great job!
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""


def generate_reports(resources: list, dry_run: bool) -> dict:
    """
    Calculates monthly savings, creates JSON and HTML report files,
    and uploads them to S3 bucket with a date-based prefix.
    Returns a dictionary of execution metadata.
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    timestamp_str = now.isoformat()
    
    total_savings = sum(res.get('estimated_monthly_savings', 0) for res in resources)
    total_resources = len(resources)
    
    report_data = {
        "generated_at": timestamp_str,
        "dry_run": dry_run,
        "total_estimated_monthly_savings": round(total_savings, 2),
        "total_idle_resources_count": total_resources,
        "resources": resources
    }
    
    # 1. Render HTML report
    template = Template(HTML_TEMPLATE)
    html_content = template.render(
        date=date_str,
        dry_run=dry_run,
        total_savings=total_savings,
        total_resources=total_resources,
        resources=resources
    )
    
    # 2. Convert JSON report
    json_content = json.dumps(report_data, indent=2, default=str)
    
    # 3. Convert CSV report
    import csv
    import io
    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer)
    csv_writer.writerow(["ResourceType", "ResourceID", "Name", "EstimatedMonthlySavings", "Details"])
    for res in resources:
        details_str = "; ".join(f"{k}={v}" for k, v in res.get("details", {}).items())
        csv_writer.writerow([
            res.get("resource_type"),
            res.get("resource_id"),
            res.get("name"),
            res.get("estimated_monthly_savings"),
            details_str
        ])
    csv_content = csv_buffer.getvalue()
    
    s3_bucket = os.environ.get("S3_BUCKET_NAME")
    s3_json_key = f"reports/{now.year}/{now.month:02d}/{now.day:02d}/report_{date_str}.json"
    s3_html_key = f"reports/{now.year}/{now.month:02d}/{now.day:02d}/report_{date_str}.html"
    s3_csv_key = f"reports/{now.year}/{now.month:02d}/{now.day:02d}/report_{date_str}.csv"
    
    s3_json_url = None
    s3_html_url = None
    s3_csv_url = None
    
    if s3_bucket:
        s3_client = get_aws_client('s3')
        try:
            logger.info(f"Uploading JSON report to s3://{s3_bucket}/{s3_json_key}")
            s3_client.put_object(
                Bucket=s3_bucket,
                Key=s3_json_key,
                Body=json_content,
                ContentType='application/json'
            )
            s3_json_url = f"https://{s3_bucket}.s3.amazonaws.com/{s3_json_key}"
            
            logger.info(f"Uploading HTML report to s3://{s3_bucket}/{s3_html_key}")
            s3_client.put_object(
                Bucket=s3_bucket,
                Key=s3_html_key,
                Body=html_content,
                ContentType='text/html'
            )
            s3_html_url = f"https://{s3_bucket}.s3.amazonaws.com/{s3_html_key}"
            
            logger.info(f"Uploading CSV report to s3://{s3_bucket}/{s3_csv_key}")
            s3_client.put_object(
                Bucket=s3_bucket,
                Key=s3_csv_key,
                Body=csv_content,
                ContentType='text/csv'
            )
            s3_csv_url = f"https://{s3_bucket}.s3.amazonaws.com/{s3_csv_key}"
            
            logger.info("Successfully uploaded reports to S3.")
        except ClientError as e:
            logger.error(f"Failed to upload reports to S3 bucket {s3_bucket}: {e}")
    else:
        logger.warning("S3_BUCKET_NAME environment variable not set. Skipping S3 report uploads.")
        
        # Save locally in a temp file or output directly to log in development
        local_dir = "/tmp" if os.name != 'nt' else os.environ.get('TEMP', '.')
        local_json = os.path.join(local_dir, f"report_{date_str}.json")
        local_html = os.path.join(local_dir, f"report_{date_str}.html")
        local_csv = os.path.join(local_dir, f"report_{date_str}.csv")
        try:
            with open(local_json, 'w') as f:
                f.write(json_content)
            with open(local_html, 'w') as f:
                f.write(html_content)
            with open(local_csv, 'w', newline='', encoding='utf-8') as f:
                f.write(csv_content)
            logger.info(f"Saved reports locally: {local_json}, {local_html}, {local_csv}")
            s3_json_url = local_json
            s3_html_url = local_html
            s3_csv_url = local_csv
        except Exception as e:
            logger.error(f"Could not save reports locally: {e}")
 
    return {
        "total_savings": round(total_savings, 2),
        "total_resources": total_resources,
        "s3_json_url": s3_json_url,
        "s3_html_url": s3_html_url,
        "s3_csv_url": s3_csv_url,
        "report_date": date_str
    }
