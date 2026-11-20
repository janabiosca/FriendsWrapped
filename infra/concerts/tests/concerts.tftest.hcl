mock_provider "aws" {
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
variables {
  name_prefix     = "sfw-test"
  table_name      = "test-listening"
  alarm_topic_arn = "arn:aws:sns:us-east-1:123456789012:test-alarms"
}
run "disabled_until_provider_is_connected" {
  command = plan
  assert {
    condition     = aws_scheduler_schedule.concerts.state == "DISABLED"
    error_message = "No remote scans may run before Ticketmaster is connected."
  }
  assert {
    condition     = aws_lambda_function.concerts.environment[0].variables.TICKETMASTER_SECRET == "sfw-test/ticketmaster"
    error_message = "Only a secret identifier, not the provider key, belongs in function configuration."
  }
  assert {
    condition     = aws_lambda_function.concerts.environment[0].variables.TABLE_NAME == "test-listening"
    error_message = "Concert storage must use the configured table."
  }
}
run "explicit_activation" {
  command = plan
  variables { concerts_enabled = true }
  assert {
    condition     = aws_scheduler_schedule.concerts.state == "ENABLED"
    error_message = "The scan should be enabled only by explicit configuration."
  }
}
