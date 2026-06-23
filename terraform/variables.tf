variable "aws_region" {
  description = "AWS Region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name of the project to prefix resources"
  type        = string
  default     = "aws-cost-optimization"
}

variable "environment" {
  description = "Target deployment environment"
  type        = string
  default     = "production"
}

variable "s3_bucket_name" {
  description = "Globally unique S3 bucket name for saving cost reports"
  type        = string
}

variable "sns_alert_email" {
  description = "Email address to receive cost reports. Leave blank to skip subscription."
  type        = string
  default     = ""
}

variable "dry_run" {
  description = "Global dry-run flag for the lambda cost optimizer execution"
  type        = string
  default     = "true"
}

variable "lambda_schedule" {
  description = "CloudWatch Events schedule expression for triggering the Lambda function"
  type        = string
  default     = "cron(0 2 * * ? *)" # Daily 2 AM UTC
}
