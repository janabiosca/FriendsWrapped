resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = {
    connect = aws_lambda_function.connect.function_name
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

resource "aws_cloudwatch_metric_alarm" "api_errors" {
  alarm_name          = "${var.name_prefix}-connect-api-5xx"
  alarm_description   = "The connect HTTP API returned a server error."
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  dimensions          = { ApiId = aws_apigatewayv2_api.connect.id, Stage = aws_apigatewayv2_stage.connect.name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alarm_topic_arn]
}
resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name                            = "${var.name_prefix}-connect-api-latency"
  alarm_description                     = "The connect API p95 latency exceeded 3 seconds in two of three five-minute windows."
  namespace                             = "AWS/ApiGateway"
  metric_name                           = "Latency"
  dimensions                            = { ApiId = aws_apigatewayv2_api.connect.id, Stage = aws_apigatewayv2_stage.connect.name }
  extended_statistic                    = "p95"
  period                                = 300
  evaluation_periods                    = 3
  datapoints_to_alarm                   = 2
  threshold                             = 3000
  comparison_operator                   = "GreaterThanThreshold"
  evaluate_low_sample_count_percentiles = "ignore"
  treat_missing_data                    = "notBreaching"
  alarm_actions                         = [var.alarm_topic_arn]
}
