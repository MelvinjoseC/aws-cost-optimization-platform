# --- CloudWatch FinOps Executive Dashboard ---
resource "aws_cloudwatch_dashboard" "finops_dashboard" {
  dashboard_name = "${var.project_name}-finops"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["CostOptimization/Metrics", "EstimatedMonthlySavings", "Environment", var.environment, "ExecutionMode", "Active", { stat = "Maximum", label = "Active Savings ($/mo)" }],
            ["CostOptimization/Metrics", "EstimatedMonthlySavings", "Environment", var.environment, "ExecutionMode", "DryRun", { stat = "Maximum", label = "Potential Savings ($/mo)" }]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "Estimated Monthly Cost Savings ($ USD)"
          period  = 86400
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["CostOptimization/Metrics", "IdleResourcesDetected", "Environment", var.environment, "ExecutionMode", "Active", { stat = "Sum", label = "Active Detected" }],
            ["CostOptimization/Metrics", "RemediatedResourcesCount", "Environment", var.environment, "ExecutionMode", "Active", { stat = "Sum", label = "Remediated" }]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "Idle vs Remediated Resource Counts"
          period  = 86400
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["CostOptimization/Metrics", "SavingsByCategory", "Environment", var.environment, "ResourceType", "EC2", { stat = "Average", label = "EC2 ($/mo)" }],
            ["CostOptimization/Metrics", "SavingsByCategory", "Environment", var.environment, "ResourceType", "RDS", { stat = "Average", label = "RDS ($/mo)" }],
            ["CostOptimization/Metrics", "SavingsByCategory", "Environment", var.environment, "ResourceType", "EBS", { stat = "Average", label = "EBS ($/mo)" }],
            ["CostOptimization/Metrics", "SavingsByCategory", "Environment", var.environment, "ResourceType", "DynamoDB", { stat = "Average", label = "DynamoDB ($/mo)" }],
            ["CostOptimization/Metrics", "SavingsByCategory", "Environment", var.environment, "ResourceType", "EFS", { stat = "Average", label = "EFS ($/mo)" }],
            ["CostOptimization/Metrics", "SavingsByCategory", "Environment", var.environment, "ResourceType", "CloudWatchLogs", { stat = "Average", label = "Logs ($/mo)" }]
          ]
          view    = "pie"
          region  = var.aws_region
          title   = "Monthly Savings Breakdown by Cloud Domain"
          period  = 86400
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.optimizer.function_name, { stat = "Sum", label = "Invocations" }],
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.optimizer.function_name, { stat = "Sum", label = "Errors", color = "#d62728" }],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.optimizer.function_name, { stat = "Average", label = "Avg Duration (ms)" }]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "Cost Optimizer Lambda Execution Health"
          period  = 3600
        }
      }
    ]
  })
}
