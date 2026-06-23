# --- IAM Role for Lambda ---
resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# --- Least-Privilege IAM Policy for Cost Optimization ---
resource "aws_iam_policy" "lambda_policy" {
  name        = "${var.project_name}-lambda-policy"
  description = "Least privilege permissions for AWS Cost Optimization Lambda function"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logging
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # CloudWatch Metrics Read
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:GetMetricData",
          "cloudwatch:ListMetrics"
        ]
        Resource = "*"
      },
      # EC2/EBS/EIP Scan, Stop, and Tag
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeVolumes",
          "ec2:DescribeAddresses",
          "ec2:StopInstances",
          "ec2:CreateTags"
        ]
        Resource = "*"
      },
      # RDS Scan, Stop, and Tag
      {
        Effect = "Allow"
        Action = [
          "rds:DescribeDBInstances",
          "rds:StopDBInstance",
          "rds:AddTagsToResource"
        ]
        Resource = "*"
      },
      # S3 PutObject to Report Bucket
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.reports.arn}/*"
      },
      # SNS Publish Alerts
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.alerts.arn
      },
      # EKS describe (to fetch Kubeconfig details if configuring connection from outside cluster)
      {
        Effect = "Allow"
        Action = [
          "eks:DescribeCluster",
          "eks:ListClusters"
        ]
        Resource = "*"
      }
    ]
  })
}

# --- Attach IAM Policy to Role ---
resource "aws_iam_role_policy_attachment" "lambda_attach" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}
