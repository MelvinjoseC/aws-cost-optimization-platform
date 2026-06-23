# --- Archive the Code for Lambda Deployment ---
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/.."
  output_path = "${path.module}/lambda_function_payload.zip"
  
  excludes = [
    "terraform",
    ".github",
    ".git",
    "k8s",
    "tests",
    "venv",
    ".venv",
    ".env",
    "__pycache__"
  ]
}

# --- AWS Lambda Function ---
resource "aws_lambda_function" "optimizer" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "${var.project_name}-optimizer"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda/handler.main_handler"
  runtime          = "python3.11"
  timeout          = 300 # 5 minutes timeout for metric scans
  memory_size      = 256
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      DRY_RUN                  = var.dry_run
      SNS_TOPIC_ARN            = aws_sns_topic.alerts.arn
      S3_BUCKET_NAME           = aws_s3_bucket.reports.id
      EC2_CPU_THRESHOLD        = "5.0"
      EC2_IDLE_HOURS           = "72"
      RDS_CONNECTION_THRESHOLD = "0"
      RDS_IDLE_HOURS           = "48"
      K8S_REQUESTS_THRESHOLD   = "0"
      K8S_IDLE_HOURS           = "24"
    }
  }
}

# Allow CloudWatch to write logs to CloudWatch logs group (Implicit but good to specify log group retention)
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.optimizer.function_name}"
  retention_in_days = 14
}
