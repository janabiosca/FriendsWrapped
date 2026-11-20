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
run "custom_environment" {
  command = plan
  variables {
    aws_region        = "eu-west-1"
    name_prefix       = "sfw-test"
    table_name        = "test-listening"
    group_id          = "test-group"
    spotify_client_id = "test-client"
  }
  assert {
    condition     = aws_lambda_function.connect.environment[0].variables.TABLE_NAME == "test-listening"
    error_message = "The function must use the configured table rather than the Academy table."
  }
  assert {
    condition     = aws_lambda_function.connect.function_name == "sfw-test-connect"
    error_message = "The function name must follow the configured prefix."
  }
}
