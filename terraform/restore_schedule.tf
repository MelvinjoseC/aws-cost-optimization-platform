# --- EventBridge Morning Restore Schedule ---
resource "aws_cloudwatch_event_rule" "morning_restore" {
  count               = var.enable_morning_restore ? 1 : 0
  name                = "${var.project_name}-morning-restore"
  description         = "Automatically triggers resource restoration every weekday morning"
  schedule_expression = var.morning_restore_schedule
}

resource "aws_cloudwatch_event_target" "restore_target" {
  count     = var.enable_morning_restore ? 1 : 0
  rule      = aws_cloudwatch_event_rule.morning_restore[0].name
  target_id = "TriggerMorningRestoration"
  arn       = aws_lambda_function.optimizer.arn

  input = jsonencode({
    action  = "restore"
    dry_run = var.dry_run
  })
}

resource "aws_lambda_permission" "allow_cloudwatch_restore" {
  count         = var.enable_morning_restore ? 1 : 0
  statement_id  = "AllowExecutionFromCloudWatchRestore"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.optimizer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.morning_restore[0].arn
}
