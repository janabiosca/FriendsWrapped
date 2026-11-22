mock_provider "aws" {
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:eu-west-1:123456789012:test-notices" }
  }
  mock_resource "aws_sqs_queue" {
    defaults = { arn = "arn:aws:sqs:eu-west-1:123456789012:test-dlq" }
  }
  mock_data "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/TestRole" }
  }
  mock_resource "aws_lambda_function" {
    defaults = {
      arn        = "arn:aws:lambda:eu-west-1:123456789012:function:test-function"
      invoke_arn = "arn:aws:apigateway:eu-west-1:lambda:path/2015-03-31/functions/arn:aws:lambda:eu-west-1:123456789012:function:test-function/invocations"
    }
  }
  mock_resource "aws_cognito_user_pool" {
    defaults = { arn = "arn:aws:cognito-idp:eu-west-1:123456789012:userpool/eu-west-1_TestPool" }
  }
  mock_resource "aws_sfn_state_machine" {
    defaults = { arn = "arn:aws:states:eu-west-1:123456789012:stateMachine:test-wrapped" }
  }
}

mock_provider "archive" {}
run "custom_environment" {
  command = apply
  variables {
    scheduler_dlq_enabled = true
    wrapped_notice_emails = ["recipient@example.com"]
    dashboard_url         = "https://dashboard.example.com/"
    aws_region            = "eu-west-1"
    name_prefix           = "sfw-test"
    table_name            = "test-listening"
    group_id              = "test-group"
    raw_bucket_name       = "test-analytics-raw"
    alarm_topic_arn       = "arn:aws:sns:eu-west-1:123456789012:test-alarms"
  }
  assert {
    condition     = jsondecode(aws_sfn_state_machine.wrapped.definition).States.ArchiveWeeklyWrapped.Next == "NotifyWeeklyWrapped"
    error_message = "Notifications must run after archival, not before the PDF exists."
  }
  assert {
    condition     = aws_lambda_function.wrapped.environment[0].variables.DASHBOARD_URL == "https://dashboard.example.com/"
    error_message = "The notice must link to the configured authenticated dashboard."
  }
  assert {
    condition     = aws_lambda_function.wrapped.tracing_config[0].mode == "Active"
    error_message = "Application functions must enable tracing."
  }

  assert {
    condition     = aws_sfn_state_machine.wrapped.tracing_configuration[0].enabled
    error_message = "Weekly orchestration must enable tracing."
  }

  assert {
    condition     = aws_lambda_function.wrapped.environment[0].variables.TABLE_NAME == "test-listening"
    error_message = "The function must use the configured table rather than the Academy table."
  }
  assert {
    condition     = aws_lambda_function.wrapped.function_name == "sfw-test-wrapped"
    error_message = "The function name must follow the configured prefix."
  }
  assert {
    condition     = aws_lambda_function.wrapped.environment[0].variables.RAW_BUCKET == "test-analytics-raw"
    error_message = "The function must use the configured raw bucket."
  }
  assert {
    condition     = contains(aws_cloudwatch_metric_alarm.wrapped_failed.alarm_actions, "arn:aws:sns:eu-west-1:123456789012:test-alarms")
    error_message = "Alarm notifications must use the configured topic."
  }
  assert {
    condition = (
      aws_lambda_function.wrapped.environment[0].variables.NOTICE_TOPIC_ARN == aws_sns_topic.wrapped_notices.arn &&
      aws_sns_topic_subscription.wrapped_email["recipient@example.com"].topic_arn == aws_sns_topic.wrapped_notices.arn &&
      aws_sns_topic.wrapped_notices.arn != var.alarm_topic_arn
    )
    error_message = "Subscribers and weekly notices must use the dedicated topic."
  }
  assert {
    condition = (
      one(aws_scheduler_schedule.wrapped.target[0].dead_letter_config).arn == aws_sqs_queue.scheduler_dlq[0].arn &&
      contains(aws_cloudwatch_metric_alarm.scheduler_dlq[0].alarm_actions, var.alarm_topic_arn)
    )
    error_message = "Scheduler delivery failures must reach the operations alarm through the DLQ."
  }
}
