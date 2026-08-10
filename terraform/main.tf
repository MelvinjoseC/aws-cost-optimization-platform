terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# --- S3 Bucket for Savings Reports ---
resource "aws_s3_bucket" "reports" {
  bucket        = var.s3_bucket_name
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "reports_versioning" {
  bucket = aws_s3_bucket.reports.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "reports_lifecycle" {
  bucket = aws_s3_bucket.reports.id

  rule {
    id     = "90-day-expiration"
    status = "Enabled"

    filter {}

    expiration {
      days = 90
    }
  }
}

resource "aws_s3_bucket_public_access_block" "reports_security" {
  bucket = aws_s3_bucket.reports.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# --- KMS Key for Encryption ---
resource "aws_kms_key" "kms_key" {
  description             = "KMS Customer Managed Key for S3 and SNS encryption in Cost Optimizer"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_kms_alias" "kms_key_alias" {
  name          = "alias/${var.project_name}-key"
  target_key_id = aws_kms_key.kms_key.key_id
}

resource "aws_s3_bucket_server_side_encryption_configuration" "reports_encryption" {
  bucket = aws_s3_bucket.reports.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.kms_key.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_policy" "reports_policy" {
  bucket = aws_s3_bucket.reports.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnforceTLSRequestsOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.reports.arn,
          "${aws_s3_bucket.reports.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}


# --- SNS Topic for Alert Notifications ---
resource "aws_sns_topic" "alerts" {
  name              = "${var.project_name}-alerts"
  kms_master_key_id = aws_kms_key.kms_key.id
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.sns_alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.sns_alert_email
}

