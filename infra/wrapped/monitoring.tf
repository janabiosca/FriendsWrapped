resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = {
    wrapped = aws_lambda_function.wrapped.function_name
  }
  alarm_name          = "${var.name_prefix}-${each.key}-errors"
  alarm_description   = "The ${each.key} Lambda failed. Inspect its CloudWatch logs and X-Ray trace."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = each.value }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alarm_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "scheduler_dlq" {
  count               = var.scheduler_dlq_enabled ? 1 : 0
  alarm_name          = "${var.name_prefix}-wrapped-scheduler-dlq"
  alarm_description   = "The weekly schedule exhausted its attempts to start the Wrapped workflow."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.scheduler_dlq[0].name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alarm_topic_arn]
}
