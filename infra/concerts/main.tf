terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project   = "spotify-friends-wrapped"
      ManagedBy = "terraform"
    }
  }
}

data "aws_iam_role" "lab" {
  name = var.lab_role_name
}
data "archive_file" "concerts" {
  type        = "zip"
  source_dir  = "${path.module}/../../src"
  output_path = "${path.module}/.build/concerts.zip"
  excludes    = ["__pycache__", "**/__pycache__/**", "**/*.pyc"]
}
resource "aws_cloudwatch_log_group" "concerts" {
  name              = "/aws/lambda/${var.name_prefix}-concerts"
  retention_in_days = 7
}
resource "aws_lambda_function" "concerts" {
  function_name    = "${var.name_prefix}-concerts"
  role             = data.aws_iam_role.lab.arn
  runtime          = "python3.13"
  handler          = "concerts.handler"
  filename         = data.archive_file.concerts.output_path
  source_code_hash = data.archive_file.concerts.output_base64sha256
  timeout          = 300
  memory_size      = 256
  tracing_config {
    mode = "Active"
  }
  environment {
    variables = {
      TABLE_NAME          = var.table_name
      GROUP_ID            = var.group_id
      TICKETMASTER_SECRET = "${var.name_prefix}/ticketmaster"
    }
  }
  depends_on = [aws_cloudwatch_log_group.concerts]
}
resource "aws_scheduler_schedule" "concerts" {
  name                         = "${var.name_prefix}-concerts"
  state                        = var.concerts_enabled ? "ENABLED" : "DISABLED"
  schedule_expression          = "cron(15 9 * * ? *)"
  schedule_expression_timezone = "Europe/Madrid"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_lambda_function.concerts.arn
    role_arn = data.aws_iam_role.lab.arn
    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 1
    }
  }
}
resource "aws_cloudwatch_metric_alarm" "concerts_errors" {
  alarm_name          = "${var.name_prefix}-concerts-errors"
  alarm_description   = "The concert scan failed; the last complete result remains available."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.concerts.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alarm_topic_arn]
}
output "concerts_enabled" { value = var.concerts_enabled }
