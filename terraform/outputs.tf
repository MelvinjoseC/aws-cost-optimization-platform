output "s3_bucket_name" {
  description = "The name of the S3 bucket created for cost reports"
  value       = aws_s3_bucket.reports.id
}

output "sns_topic_arn" {
  description = "The ARN of the SNS topic for alerts"
  value       = aws_sns_topic.alerts.arn
}

output "lambda_arn" {
  description = "The ARN of the cost optimization Lambda function"
  value       = aws_lambda_function.optimizer.arn
}
