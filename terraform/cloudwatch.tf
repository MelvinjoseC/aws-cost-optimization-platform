# --- CloudWatch / EventBridge Schedule Rule ---
resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "${var.project_name}-schedule"
  description         = "Triggers the cost optimization lambda daily on a scheduled cron"
  schedule_expression = var.lambda_schedule
}

# --- CloudWatch Target for Lambda ---
resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.schedule.name
  target_id = "TriggerCostOptimizationLambda"
  arn       = aws_lambda_function.optimizer.arn
}

# --- Lambda Permission to Allow CloudWatch Rule Triggers ---
resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.optimizer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}
