resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = {
    dashboard = aws_lambda_function.dashboard.function_name
    signup    = aws_lambda_function.signup.function_name
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
  alarm_name          = "${var.name_prefix}-dashboard-api-5xx"
  alarm_description   = "The dashboard HTTP API returned a server error."
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  dimensions          = { ApiId = aws_apigatewayv2_api.dashboard.id, Stage = aws_apigatewayv2_stage.dashboard.name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alarm_topic_arn]
}
resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name                            = "${var.name_prefix}-dashboard-api-latency"
  alarm_description                     = "The dashboard API p95 latency exceeded 3 seconds in two of three five-minute windows."
  namespace                             = "AWS/ApiGateway"
  metric_name                           = "Latency"
  dimensions                            = { ApiId = aws_apigatewayv2_api.dashboard.id, Stage = aws_apigatewayv2_stage.dashboard.name }
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

resource "aws_cloudwatch_dashboard" "operations" {
  dashboard_name = "${var.name_prefix}-operations"
  dashboard_body = jsonencode({
    widgets = concat([
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6
        properties = {
          title = "Dashboard API requests and server errors", region = var.aws_region, period = 300, stat = "Sum"
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiId", aws_apigatewayv2_api.dashboard.id],
            ["AWS/ApiGateway", "5xx", "ApiId", aws_apigatewayv2_api.dashboard.id]
          ]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6
        properties = {
          title   = "Dashboard API p95 latency (ms)", region = var.aws_region, period = 300, stat = "p95"
          metrics = [["AWS/ApiGateway", "Latency", "ApiId", aws_apigatewayv2_api.dashboard.id]]
        }
      }
      ], [for i, name in ["dispatcher", "collector", "connect", "signup", "dashboard", "wrapped"] : {
        type = "metric", x = (i % 2) * 12, y = 6 + floor(i / 2) * 6, width = 12, height = 6
        properties = {
          title = "${name}: errors and throttles", region = var.aws_region, period = 300, stat = "Sum"
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", "${var.name_prefix}-${name}"],
            ["AWS/Lambda", "Throttles", "FunctionName", "${var.name_prefix}-${name}"]
          ]
        }
    }])
  })
}
