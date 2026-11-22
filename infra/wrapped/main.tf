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

data "archive_file" "wrapped" {
  type        = "zip"
  source_dir  = "${path.module}/.build/package"
  output_path = "${path.module}/.build/wrapped.zip"
  excludes    = ["__pycache__", "**/__pycache__/**", "**/*.pyc"]
}

resource "aws_cloudwatch_log_group" "wrapped" {
  name              = "/aws/lambda/${var.name_prefix}-wrapped"
  retention_in_days = 7
}

resource "aws_lambda_function" "wrapped" {
  function_name = "${var.name_prefix}-wrapped"
  role          = data.aws_iam_role.lab.arn
  tracing_config {
    mode = "Active"
  }
  runtime          = "python3.13"
  handler          = "wrapped.handler"
  filename         = data.archive_file.wrapped.output_path
  source_code_hash = data.archive_file.wrapped.output_base64sha256
  timeout          = 120
  memory_size      = 256
  environment {
    variables = {
      TABLE_NAME       = var.table_name
      RAW_BUCKET       = var.raw_bucket_name
      GROUP_ID         = var.group_id
      NOTICE_TOPIC_ARN = aws_sns_topic.wrapped_notices.arn
      DASHBOARD_URL    = var.dashboard_url
    }
  }
  depends_on = [aws_cloudwatch_log_group.wrapped]
}

resource "aws_sfn_state_machine" "wrapped" {
  name     = "${var.name_prefix}-weekly-wrapped"
  role_arn = data.aws_iam_role.lab.arn
  type     = "STANDARD"
  tracing_configuration {
    enabled = true
  }
  definition = jsonencode({
    StartAt        = "PrepareWeeklySnapshot"
    TimeoutSeconds = 600
    States = {
      PrepareWeeklySnapshot = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.wrapped.arn
          Payload = {
            action             = "prepare"
            "request.$"        = "$"
            "reference_time.$" = "$$.Execution.StartTime"
          }
        }
        OutputPath = "$.Payload"
        Retry = [{
          ErrorEquals     = ["States.TaskFailed"]
          IntervalSeconds = 2
          MaxAttempts     = 3
          BackoffRate     = 2
        }]
        Next = "ArchiveWeeklyWrapped"
      }
      ArchiveWeeklyWrapped = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.wrapped.arn
          Payload = {
            action       = "archive"
            "snapshot.$" = "$"
          }
        }
        OutputPath = "$.Payload"
        Retry = [{
          ErrorEquals     = ["States.TaskFailed"]
          IntervalSeconds = 2
          MaxAttempts     = 3
          BackoffRate     = 2
        }]
        Next = "NotifyWeeklyWrapped"
      }
      NotifyWeeklyWrapped = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.wrapped.arn
          Payload = {
            action       = "notify"
            "snapshot.$" = "$"
          }
        }
        OutputPath = "$.Payload"
        Retry = [{
          ErrorEquals     = ["States.TaskFailed"]
          IntervalSeconds = 30
          MaxAttempts     = 3
          BackoffRate     = 2
        }]
        End = true
      }
    }
  })
}

resource "aws_sns_topic" "wrapped_notices" {
  name              = "${var.name_prefix}-wrapped-notices"
  kms_master_key_id = "alias/aws/sns"
}

resource "aws_sns_topic_subscription" "wrapped_email" {
  for_each  = var.wrapped_notice_emails
  topic_arn = aws_sns_topic.wrapped_notices.arn
  protocol  = "email"
  endpoint  = each.value
}

resource "aws_sqs_queue" "scheduler_dlq" {
  count                     = var.scheduler_dlq_enabled ? 1 : 0
  name                      = "${var.name_prefix}-wrapped-scheduler-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_scheduler_schedule" "wrapped" {
  name                         = "${var.name_prefix}-weekly-wrapped"
  schedule_expression          = "cron(0 9 ? * MON *)"
  schedule_expression_timezone = "Europe/Madrid"
  flexible_time_window {
    mode = "OFF"
  }
  target {
    arn      = aws_sfn_state_machine.wrapped.arn
    role_arn = data.aws_iam_role.lab.arn
    input    = "{}"
    dynamic "dead_letter_config" {
      for_each = aws_sqs_queue.scheduler_dlq
      content {
        arn = dead_letter_config.value.arn
      }
    }
    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 3
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "wrapped_failed" {
  alarm_name          = "${var.name_prefix}-weekly-wrapped-failed"
  alarm_description   = "The weekly Wrapped generation failed. Review its Step Functions execution."
  namespace           = "AWS/States"
  metric_name         = "ExecutionsFailed"
  dimensions          = { StateMachineArn = aws_sfn_state_machine.wrapped.arn }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alarm_topic_arn]
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.wrapped.arn
}
